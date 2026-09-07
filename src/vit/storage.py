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


@contextmanager
def writer_lock(path: Path):
    # Keep the lock file in place: unlinking it can let writers lock different
    # inodes. OS locks are released even when a process crashes.
    with path.open("a+b") as handle:
        try:
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

                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise VitError("another vit attachment is in progress; try again shortly") from None
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
            prepared = []
            for index, source in enumerate(sources):
                destination = batch / str(index) / source.name
                destination.parent.mkdir()
                shutil.copyfile(source, destination)
                with destination.open("rb") as handle:
                    digest = hashlib.file_digest(handle, "sha256").hexdigest()
                prepared.append((source.name, digest, destination.relative_to(batch)))

            with writer_lock(self.common_dir / "vit.lock"):
                entries = self._read(commit)
                known = {entry["name"]: entry["sha256"] for entry in entries}
                added, skipped = [], []
                batch_id = uuid.uuid4().hex
                target = self.root / "batches" / batch_id
                for name, digest, relative in prepared:
                    if name in known:
                        if known[name] != digest:
                            raise VitError(f'a different file named "{name}" is already attached or requested; rename the new file and try again')
                        if name not in added and name not in skipped:
                            skipped.append(name)
                        (batch / relative).unlink()
                        (batch / relative).parent.rmdir()
                        continue
                    known[name] = digest
                    added.append(name)
                    entries.append({
                        "name": name,
                        "sha256": digest,
                        "path": (Path("batches") / batch_id / relative).as_posix(),
                    })
                if not added:
                    return added, skipped

                manifest = staging / "manifest.json"
                with manifest.open("w", encoding="utf-8") as handle:
                    json.dump({"version": 1, "attachments": entries}, handle, indent=2)
                    handle.flush()
                    os.fsync(handle.fileno())
                try:
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(batch, target)
                    os.replace(manifest, self.root / f"{commit}.json")
                except OSError:
                    if target.exists():
                        shutil.rmtree(target)
                    # Remove newly created, empty directories after failure.
                    for directory in (target.parent, self.root):
                        try:
                            directory.rmdir()
                        except OSError:
                            pass
                    raise
                # An asynchronous interruption must not delete the batch: the
                # manifest replacement may already have committed the operation.
                return added, skipped
