"""Read-only Git operations used by vit

Each GitRepository has its current working directory, but also
"""

from dataclasses import dataclass
from pathlib import Path
import re
import subprocess

from vit.errors import VitError


@dataclass(frozen=True)
class Commit:
    hash: str
    subject: str

    @property
    def short_hash(self) -> str:
        return self.hash[:7]


class GitRepository:
    def __init__(self, cwd: Path):
        self.cwd = cwd

        # Look for the repo and pass back the stripped path 
        result = self._run("rev-parse", "--path-format=absolute", "--git-common-dir")
        if result.returncode:
            raise VitError("not inside a Git repository")
        
        self.common_dir = Path(result.stdout.strip())

    def _run(self, *args: str, input: str | None = None) -> subprocess.CompletedProcess:
        try:
            return subprocess.run(
                ["git", *args], cwd=self.cwd, input=input,
                text=True, encoding="utf-8", errors="replace", capture_output=True,
            )
        except FileNotFoundError:
            raise VitError(
                "could not start Git; check that Git is on PATH and the working directory still exists"
            ) from None

    def _output(self, *args: str, input: str | None = None) -> str:
        result = self._run(*args, input=input)
        if result.returncode:
            raise VitError("could not read Git history; check that the repository is accessible")
        return result.stdout.strip()

    def resolve(self, commit_hash: str | None = None) -> Commit:
        if commit_hash is None:
            result = self._run("rev-parse", "--verify", "HEAD^{commit}")
            if result.returncode:
                raise VitError("this repository has no commits; create a Git commit first")
            resolved = result.stdout.strip()
        else:
            if not re.fullmatch(r"[0-9a-fA-F]{1,64}", commit_hash):
                raise VitError(f'no commit matches "{commit_hash}"; use a full or partial commit hash')
            prefix = commit_hash.lower()
            if len(prefix) < 4:
                objects = self._output("cat-file", "--batch-all-objects", "--batch-check=%(objectname) %(objecttype)")
            else:
                candidates = self._output("rev-parse", f"--disambiguate={prefix}")
                objects = self._output(
                    "cat-file", "--batch-check=%(objectname) %(objecttype)",
                    input=candidates + "\n",
                ) if candidates else ""
            matches = [
                line.split()[0] for line in objects.splitlines()
                if line.endswith(" commit") and line.startswith(prefix)
            ]
            if not matches:
                raise VitError(f'no commit matches "{commit_hash}"')
            if len(matches) > 1:
                raise VitError(f'commit hash "{commit_hash}" is ambiguous; use a longer hash')
            resolved = matches[0]
        subject = self._output("show", "-s", "--format=%s", resolved, "--")
        return Commit(resolved, subject)
