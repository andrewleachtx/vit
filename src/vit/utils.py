import os
from pathlib import Path

def findGitRoot() -> Path:
    """
    Walks up looking for a `.git` directory - the first one found is our projects "root" 
    when vit init or other commands are used.
    """

    cur = Path.cwd()
    while cur != cur.parent:
        if (cur/".git").exists():
            return cur
        cur = cur.parent
    raise RuntimeError("Could not find a Git repository")

def bytesToHuman(nbytes: int) -> str:
    for unit in ("B","KiB","MiB","GiB","TiB"):
        if nbytes < 1024:
            return f"{nbytes:.1f}{unit}"
        nbytes /= 1024
    return f"{nbytes:.2f}PiB"

def getDirSize(path: Path) -> int:
    """
    Traverses the directory starting at path/ and sums the file sizes (in bytes).

    https://stackoverflow.com/a/1392549/27629759
    """
    nbytes = 0

    for root, dirs, files in os.walk(path):
        for filename in files:
            nbytes += (Path(root) / filename).stat().st_size
        nbytes += Path(root).stat().st_size
    
    return nbytes

def addToGitignore(repoRoot: Path) -> None:
    """
    Helper that adds .vit/ to the .gitignore and creates it if not existing.
    """
    gitignore = repoRoot / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text(".vit/\n")
    else:
        lines = gitignore.read_text().splitlines()
        if ".vit/" not in lines:
            with gitignore.open("a") as f:
                f.write("\n.vit/\n")