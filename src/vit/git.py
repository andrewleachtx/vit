"""Read-only Git operations used by vit

Each GitRepository has its current working directory, but also where the repo is mounted (where .git/ and thus .git/vit/ is)
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
                "could not run Git; check that Git is on PATH and the working directory still exists"
            ) from None

    def _output(self, *args: str, input: str | None = None) -> str:
        result = self._run(*args, input=input)
        if result.returncode:
            raise VitError("could not read Git history; check that the repository is accessible")
        return result.stdout.strip()

    # A user can provide no, or a prefixed commit hash. We need to find the exact commit
    def resolve(self, commit_hash: str | None = None) -> Commit:
        if commit_hash is None:
            # Grab the most recent commit hash
            result = self._run("rev-parse", "--verify", "HEAD^{commit}")
            if result.returncode:
                raise VitError("this repository has no commits; create a Git commit first")
            resolved = result.stdout.strip()
        else:
            # We require a valid hash to be passed
            if not re.fullmatch(r"[0-9a-fA-F]{1,64}", commit_hash):
                raise VitError(f'invalid commit hash format: "{commit_hash}"; should use 1–64 hexadecimal characters (0–9, a–f)')
            
            prefix = commit_hash.lower()
            if len(prefix) < 4:
                # List each object, commit, blob (files), tree (directories), and tag (rare, 'git tag' annotated tags)
                objects = self._output("cat-file", "--batch-all-objects", "--batch-check=%(objectname) %(objecttype)")
            else:
                # Git offers a way to grab objects and filter for us
                candidates = self._output("rev-parse", f"--disambiguate={prefix}")
                objects = self._output(
                    "cat-file", "--batch-check=%(objectname) %(objecttype)",
                    input=candidates + "\n",
                ) if candidates else ""

            # Keep only commit hashes that start with the user given prefix
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
