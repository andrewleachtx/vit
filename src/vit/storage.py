"""Immutable artifact batches with one atomic manifest update per attachment.

Files are staged before publication. A process lock serializes writers; readers
see either the old manifest or the complete new one and never need a lock.
"""

from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
import uuid

from vit.errors import VitError

# Turns our generator into something you can use with 'with'
@contextmanager
def writer_lock(path: Path):
    """
    Grab the file descriptor from path.open("a+b") (append r/w binary) and try to acquire a lock
    on that file descriptor based on OS.

    If we acquire, we yield to the caller and they continue from there, while the lock is still in scope.

    After the caller downstream exits, we issue a LOCK_UN to release the lock and exit.
    """
    with path.open("a+b") as handle:
        try:
            # Windows NT uses msvcrt.locking() while macOS/Linux use fcntl.flock()
            if os.name == "nt":
                import msvcrt

                handle.seek(0, os.SEEK_END)
                if handle.tell() == 0:
                    handle.write(b"\0")
                    handle.flush()
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                # Acquire an exclusive lock and error if another writer is holding it, do not wait (no block)
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise VitError("another vit attachment is in progress; try again shortly") from None

        # If we successfully locked, we can yield to the caller's 'with' block while we own the file descriptor lock still in scope here
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


class ArtifactStore:
    def __init__(self, common_dir: Path):
        self.common_dir = common_dir
        self.root = common_dir / "vit"

    def _read(self, commit: str) -> list[dict[str, str]]:
        # Look for .git/vit/<full-commit-hash>.json manifest and return its list of all dicts (one dict per attachment)
        manifest = self.root / f"{commit}.json"
        if not manifest.exists():
            return []
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or data.get("version") != 1:
                raise ValueError
            entries = data["attachments"]
            if not isinstance(entries, list):
                raise ValueError
            names = set()
            for entry in entries:
                if not isinstance(entry, dict) or not all(
                    isinstance(entry.get(key), str) for key in ("name", "path", "sha256")
                ):
                    raise ValueError
                name = entry["name"]
                path = Path(entry["path"])
                if (
                    not name or name in names or path.name != name
                    or not re.fullmatch(r"[0-9a-f]{64}", entry["sha256"])
                    or path.is_absolute() or ".." in path.parts
                    or not (self.root / path).resolve().is_relative_to(self.root.resolve())
                ):
                    raise ValueError
                names.add(name)
            return entries
        except (ValueError, KeyError, TypeError):
            raise VitError("could not read saved attachments; restore them from a backup before attaching more files") from None

    def show(self, commit: str) -> list[tuple[str, Path]]:
        artifacts = []
        for entry in self._read(commit):
            path = self.root / entry["path"]
            if not path.is_file():
                raise VitError(f'saved file is missing: {entry["name"]}; restore it from a backup')
            artifacts.append((entry["name"], path))
        return artifacts

    def attach(self, commit: str, sources: list[Path]) -> tuple[list[str], list[str]]:
        # Stage on the same filesystem as the destination so rename is atomic.
        with tempfile.TemporaryDirectory(prefix=".vit-stage-", dir=self.common_dir) as temporary:
            staging = Path(temporary)
            batch = staging / "files"
            batch.mkdir()
            
            proposed_entries = []
            for index, source in enumerate(sources):
                destination = batch / str(index) / source.name
                destination.parent.mkdir()
                shutil.copyfile(source, destination)

                # Grab a unique digest hash for filename + fingerprint to avoid dupes later
                with destination.open("rb") as handle:
                    digest = hashlib.file_digest(handle, "sha256").hexdigest()
                proposed_entries.append((source.name, digest, destination.relative_to(batch)))

            # Acquire a lock around the common directory to write a new manifest.json for this commit - we copy all previous entries in a commit's attachment.
            # this is a bit of a n^2 operation because technically we don't append in place, we copy previous metadata (not entries!) into memory here and
            # add in the proposed set
            with writer_lock(self.common_dir / "vit.lock"):
                # This commit can have entries already associated. We need to merge in the new ones while avoiding duplicates
                existing_entries = self._read(commit)

                # Python upserts by default, but we know that entries for the existing commit would have already handled that case, so no dupes can happen here
                known = {entry["name"]: entry["sha256"] for entry in existing_entries}
                added, skipped = [], []
                batch_id = uuid.uuid4().hex
                target = self.root / "batches" / batch_id

                # For each proposed entry filename, hash, and relative path add where possible
                for name, digest, relative in proposed_entries:
                    if name in known:
                        # If we have a dupe filename, but it has the same file contents, we have to raise an error. Otherwise skip and use the first seen file as it is a true dupe
                        if known[name] != digest:
                            raise VitError(f'a different file named "{name}" is already attached or requested; rename the new file and try again')
                        if name not in added and name not in skipped:
                            skipped.append(name)

                        # Remove the dupe's temporary copy for this file
                        (batch / relative).unlink()
                        (batch / relative).parent.rmdir()
                        continue

                    # Otherwise, record the filename and hash and append to existing_entries for the updated manifest.
                    known[name] = digest
                    added.append(name)
                    existing_entries.append({
                        "name": name,
                        "sha256": digest,
                        "path": (Path("batches") / batch_id / relative).as_posix(),
                    })
                if not added:
                    return added, skipped

                # Create the manifest file within the temp staging location and dump to it
                manifest = staging / "manifest.json"
                with manifest.open("w", encoding="utf-8") as handle:
                    json.dump({"version": 1, "attachments": existing_entries}, handle, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())

                # Create a permanent storage and move temp to there
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(batch, target)
                    os.replace(manifest, self.root / f"{commit}.json")
                except OSError:
                    if target.exists():
                        shutil.rmtree(target)
                    # Remove newly created, empty directories after failure
                    for directory in (target.parent, self.root):
                        try:
                            directory.rmdir()
                        except OSError:
                            pass
                    raise
                
                # An asynchronous interruption must not delete the batch: the
                # manifest replacement may already have committed the operation
                return added, skipped
