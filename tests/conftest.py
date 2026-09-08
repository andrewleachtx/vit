from pathlib import Path
import subprocess

import pytest

from vit.cli import main


def git(cwd: Path, *args: str, input: str | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, input=input, text=True,
        capture_output=True, check=True,
    ).stdout.strip()


# pytest.fixture 
@pytest.fixture
def repo(tmp_path, monkeypatch):
    # Ignore system/personal Git config, monkeypatch restores these env vars after the test exits
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(tmp_path / "no-global-config"))

    # Clear overrides that could make Git use a repository outside our temporary one
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR"):
        monkeypatch.delenv(name, raising=False)

    # Create a real Git repository inside pytest's temporary directory
    path = tmp_path / "repo"
    path.mkdir()
    git(path, "init", "-q")

    # Configure only this temporary repo so commits need no personal identity or signing key
    git(path, "config", "user.name", "Vit Test")
    git(path, "config", "user.email", "vit@example.invalid")
    git(path, "config", "commit.gpgsign", "false")

    # Give HEAD a commit that tests can attach files to
    git(path, "commit", "--allow-empty", "-qm", "First render")

    # Run the test from this repo; monkeypatch restores the previous directory afterward
    monkeypatch.chdir(path)
    return path


@pytest.fixture
def cli(capsys):
    # Tests can call cli("attach", "render.png") and inspect the result
    def invoke(*args):
        # Call vit's entry point directly in this Python process, not a subprocess
        code = main(list(args))

        # Collect printed output and errors, then reset capture for the next call
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    # Supply the callable helper to any test that requests the cli fixture
    return invoke
