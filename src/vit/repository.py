"""Application operations shared by CLI commands.

Each Git "Repository" has its underlying git changes, and our vit storages that we should update

We essentially interface with the underlying GitRepository in git.py and write to our
internal stores through ArtifactStore in storage.py
"""

from pathlib import Path

from vit.errors import VitError
from vit.git import Commit, GitRepository
from vit.storage import ArtifactStore


class Repository:
    def __init__(self, cwd: Path):
        self.git = GitRepository(cwd)
        self.store = ArtifactStore(self.git.common_dir)

    def attach(self, commit: Commit, files: list[Path]) -> tuple[list[str], list[str]]:
        if not files:
            raise VitError("provide at least one file to attach")
        for path in files:
            if not path.exists():
                raise VitError(f"file not found: {path}")
            if not path.is_file():
                raise VitError(f"not a regular file: {path}")
            try:
                with path.open("rb"):
                    pass
            except OSError:
                raise VitError(f"cannot read file: {path}; check its permissions") from None
        return self.store.attach(commit.hash, files)

    def show(self, commit: Commit) -> list[tuple[str, Path]]:
        return self.store.show(commit.hash)
