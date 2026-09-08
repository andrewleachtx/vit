# AI generated these test
import hashlib
from pathlib import Path
import shutil
import subprocess
import sys
from urllib.parse import unquote, urlparse

import pytest

from conftest import git
from vit.repository import Repository
from vit.storage import writer_lock


def artifact(repo, name="render.png", contents=b"picture"):
    path = repo / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(contents)
    return path


def saved(repo, commit=None):
    repository = Repository(repo)
    return repository.show(repository.git.resolve(commit))


# Attaching an image leaves Git unchanged, deleting that original image keeps vit's copy (we make deep copies)
def test_attach_head_preserves_git_and_original_can_be_deleted(repo, cli):
    source = artifact(repo)
    git(repo, "add", source.name)
    before = {args: git(repo, *args) for args in [
        ("rev-parse", "HEAD"), ("status", "--porcelain"),
        ("ls-files", "--stage"), ("reflog", "--format=%H %gs"),
    ]}
    code, out, err = cli("attach", source.name)
    assert code == 0 and err == ""
    assert 'Attached 1 file to ' in out and '"First render"' in out
    assert "  render.png" in out
    for args, expected in before.items():
        assert git(repo, *args) == expected
    source.unlink()
    assert saved(repo)[0][1].read_bytes() == b"picture"
    assert not (repo / ".vit").exists()
    assert not (repo / ".gitignore").exists()


# Attach three files, then check that each link from vit show opens the right one
def test_attach_multiple_and_show_links(repo, cli):
    names = ["render.png", "comparison.gif", "demo with space.mp4"]
    for name in names:
        artifact(repo, name, name.encode())
    assert cli("attach", *names)[0] == 0
    code, out, err = cli("show")
    assert code == 0 and not err
    assert "Attachments for" in out
    assert [name for name, _ in saved(repo)] == names
    urls = [line.strip() for line in out.splitlines() if line.strip().startswith("file:")]
    assert len(urls) == 3
    for url, name in zip(urls, names):
        assert Path(unquote(urlparse(url).path)).read_bytes() == name.encode()


# Let users choose a commit by its full or shortened hash, even after a newer commit exists
@pytest.mark.parametrize("length", [1, 4, 7, 40])
def test_attach_old_commit_by_hash(repo, cli, length):
    old = git(repo, "rev-parse", "HEAD")
    artifact(repo)
    # A one-character hash is unique while there is only one commit.
    assert cli("attach", "render.png", "--hash", old[:length].upper())[0] == 0
    git(repo, "commit", "--allow-empty", "-qm", "Next render")
    head = git(repo, "rev-parse", "HEAD")
    assert saved(repo) == []
    assert cli("show", "--hash", old)[0] == 0
    assert saved(repo, old)[0][0] == "render.png"
    artifact(repo, "second.gif")
    assert cli("attach", "second.gif", "--hash", old)[0] == 0
    assert git(repo, "rev-parse", "HEAD") == head
    assert len(saved(repo, old)) == 2


# If the hash is invalid or matches no commit, explain the error and save nothing
@pytest.mark.parametrize("value, message", [
    ("f" * 40, "no commit matches"),
    ("not-a-hash", "invalid commit hash format"),
    ("--all", "invalid commit hash format"),
    ("HEAD~1", "invalid commit hash format"),
])
def test_invalid_hash_does_not_initialize(repo, cli, value, message):
    artifact(repo)
    code, _, err = cli("attach", "render.png", f"--hash={value}")
    assert code == 1 and message in err
    assert not (repo / ".git" / "vit").exists()


# If two commits start with the same four characters, that short hash must cause an error
def test_ambiguous_hash_uses_real_git_objects(repo, cli):
    tree = git(repo, "rev-parse", "HEAD^{tree}")
    seen = {}
    for number in range(10000):
        content = (f"tree {tree}\nauthor Test <test@example.invalid> 0 +0000\n"
                   f"committer Test <test@example.invalid> 0 +0000\n\n{number}\n")
        raw = content.encode()
        digest = hashlib.sha1(f"commit {len(raw)}\0".encode() + raw).hexdigest()
        prefix = digest[:4]
        if prefix in seen:
            for candidate in (seen[prefix], content):
                git(repo, "hash-object", "-w", "-t", "commit", "--stdin", input=candidate)
            break
        seen[prefix] = content
    else:
        pytest.fail("could not generate hash collision")
    artifact(repo)
    code, _, err = cli("attach", "render.png", "--hash", prefix)
    assert code == 1 and f'commit hash "{prefix}" is ambiguous' in err
    assert not (repo / ".git" / "vit").exists()


# A Git hash can identify file contents too; vit must only accept hashes for commits
def test_blob_hash_is_not_commit(repo, cli):
    blob = git(repo, "hash-object", "-w", "--stdin", input="a blob")
    assert "no commit matches" in cli("show", "--hash", blob)[2]


# Request one real file and one missing file. Neither should be saved by vit
def test_missing_file_rejects_entire_batch(repo, cli):
    artifact(repo)
    code, out, err = cli("attach", "render.png", "missing.gif")
    assert code == 1 and not out and "file not found: missing.gif" in err
    assert not (repo / ".git" / "vit").exists()
    assert not list((repo / ".git").glob(".vit-stage-*"))


# Trying to attach a folder should give an error and save nothing.
def test_directory_rejected(repo, cli):
    assert "not a regular file" in cli("attach", ".")[2]
    assert not (repo / ".git" / "vit").exists()


# Running vit show before attaching anything should say there are no attachments and create no files.
def test_empty_show_does_not_initialize(repo, cli):
    code, out, err = cli("show")
    assert code == 0 and "No attachments for" in out and not err
    assert not (repo / ".git" / "vit").exists()
    assert not (repo / ".git" / "vit.lock").exists()


# Running attach or show outside a Git repo should say "not inside a Git repository".
@pytest.mark.parametrize("command", ["show", "attach"])
def test_outside_repository(tmp_path, monkeypatch, cli, command):
    monkeypatch.chdir(tmp_path)
    args = (command, "missing.png") if command == "attach" else (command,)
    assert cli(*args) == (1, "", "error: not inside a Git repository\n")


# In a repo with no commits yet, vit show should tell the user to make a commit first.
def test_repository_without_commits(tmp_path, monkeypatch, cli):
    git(tmp_path, "init", "-q")
    monkeypatch.chdir(tmp_path)
    assert "create a Git commit first" in cli("show")[2]


# Attaching the same file again should skip it. Adding another file should keep both.
def test_duplicate_is_noop_and_append_keeps_existing(repo, cli):
    artifact(repo)
    assert cli("attach", "render.png", "render.png")[0] == 0
    before = list((repo / ".git" / "vit").rglob("*"))
    code, out, _ = cli("attach", "render.png")
    assert code == 0 and "Already attached" in out
    assert list((repo / ".git" / "vit").rglob("*")) == before
    artifact(repo, "other.gif")
    assert cli("attach", "other.gif", "render.png")[0] == 0
    assert [name for name, _ in saved(repo)] == ["render.png", "other.gif"]


# Two different files named render.png must cause an error, and nothing new should be saved.
@pytest.mark.parametrize("existing", [True, False])
def test_same_name_different_contents_rejects_whole_batch(repo, cli, existing):
    artifact(repo)
    artifact(repo, "sub/render.png", b"different")
    artifact(repo, "new.mp4")
    if existing:
        assert cli("attach", "render.png")[0] == 0
        args = ("new.mp4", "sub/render.png")
    else:
        args = ("render.png", "new.mp4", "sub/render.png")
    code, _, err = cli("attach", *args)
    assert code == 1 and "rename the new file" in err
    assert [name for name, _ in saved(repo)] == (["render.png"] if existing else [])


# Make the second file copy fail. vit should remove the first temporary copy too.
def test_copy_failure_leaves_no_attachments(repo, cli, monkeypatch):
    artifact(repo)
    artifact(repo, "other.gif")
    original = shutil.copyfile
    def fail_second(source, destination):
        if source.name == "other.gif":
            raise OSError("simulated disk full")
        return original(source, destination)
    monkeypatch.setattr("vit.storage.shutil.copyfile", fail_second)
    code, _, err = cli("attach", "render.png", "other.gif")
    assert code == 1 and "simulated disk full" in err
    assert not (repo / ".git" / "vit").exists()
    assert not list((repo / ".git").glob(".vit-stage-*"))


# Make saving the updated attachment list fail. Earlier attachments should remain unchanged,
# and the new copies should be removed.
@pytest.mark.parametrize("existing", [False, True])
def test_publication_failure_rolls_back(repo, cli, monkeypatch, existing):
    import os
    artifact(repo)
    if existing:
        assert cli("attach", "render.png")[0] == 0
    artifact(repo, "other.gif")
    root = repo / ".git" / "vit"
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    original = os.replace
    def fail_manifest(source, target):
        if Path(target).suffix == ".json":
            raise OSError("simulated publication failure")
        return original(source, target)
    monkeypatch.setattr("vit.storage.os.replace", fail_manifest)
    assert cli("attach", "other.gif")[0] == 1
    after = {p.relative_to(root): p.read_bytes() for p in root.rglob("*") if p.is_file()}
    assert after == before
    assert root.exists() == existing
    assert not list((repo / ".git").glob(".vit-stage-*"))


# While another process holds the lock, attaching should fail with a retry message.
# Trying again after the lock is released should work.
def test_concurrent_writer_has_actionable_error_then_can_retry(repo, cli):
    artifact(repo)
    with writer_lock(repo / ".git" / "vit.lock"):
        result = subprocess.run(
            [sys.executable, "-m", "vit", "attach", "render.png"],
            cwd=repo, text=True, capture_output=True,
        )
    assert result.returncode == 1
    assert "another vit attachment is in progress" in result.stderr
    assert saved(repo) == []
    assert cli("attach", "render.png")[0] == 0


# Simulate Ctrl+C just after the new attachment list is saved. Keep the files it now lists.
def test_interrupt_after_publication_keeps_saved_artifacts(repo, cli, monkeypatch):
    import os
    artifact(repo)
    original = os.replace
    def interrupt_after_manifest(source, target):
        original(source, target)
        if Path(target).suffix == ".json":
            raise KeyboardInterrupt
    monkeypatch.setattr("vit.storage.os.replace", interrupt_after_manifest)
    code, _, err = cli("attach", "render.png")
    assert code == 130 and "run vit show" in err
    assert saved(repo)[0][1].read_bytes() == b"picture"


# Attaching from a folder inside the repo should work. A linked Git checkout should
# see those same attachments, and files attached there should appear in the original checkout.
def test_nested_directory_and_linked_worktree(repo, cli, monkeypatch, tmp_path):
    artifact(repo, "nested/render.png")
    monkeypatch.chdir(repo / "nested")
    assert cli("attach", "render.png")[0] == 0
    worktree = tmp_path / "linked"
    git(repo, "worktree", "add", "--detach", str(worktree), "HEAD")
    monkeypatch.chdir(worktree)
    assert "render.png" in cli("show")[1]
    artifact(worktree, "demo.mp4")
    assert cli("attach", "demo.mp4")[0] == 0
    assert len(saved(repo)) == 2


# Move the repo to another folder and check that vit can still find its saved files.
def test_repository_can_move(repo, cli, monkeypatch, tmp_path):
    artifact(repo)
    assert cli("attach", "render.png")[0] == 0
    destination = tmp_path / "moved"
    repo.rename(destination)
    monkeypatch.chdir(destination)
    assert cli("show")[0] == 0
    assert saved(destination)[0][1].read_bytes() == b"picture"


# Damage the saved attachment list. Both show and attach should report an error
# and leave that list untouched.
@pytest.mark.parametrize("contents", ["invalid", "[]", '{"version": 2}', '{"version": 1, "attachments": [null]}'])
def test_corrupt_manifest_fails_without_overwriting(repo, cli, contents):
    artifact(repo)
    assert cli("attach", "render.png")[0] == 0
    manifest = next((repo / ".git" / "vit").glob("*.json"))
    manifest.write_text(contents)
    assert "could not read saved attachments" in cli("show")[2]
    assert cli("attach", "render.png")[0] == 1
    assert manifest.read_text() == contents


# Delete vit's saved copy, then check that show names the missing file in its error.
def test_missing_saved_file_is_actionable(repo, cli):
    artifact(repo)
    assert cli("attach", "render.png")[0] == 0
    saved(repo)[0][1].unlink()
    assert "saved file is missing: render.png" in cli("show")[2]


# Old commands such as vit commit and vit undo should fail and leave the current commit unchanged.
@pytest.mark.parametrize("command", ["init", "commit", "modify", "undo", "timeline", "tl", "overhead", "test"])
def test_old_commands_are_removed(repo, cli, command):
    before = git(repo, "rev-parse", "HEAD")
    with pytest.raises(SystemExit) as error:
        cli(command)
    assert error.value.code == 2
    assert git(repo, "rev-parse", "HEAD") == before
