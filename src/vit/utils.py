import os
from pathlib import Path

# https://gist.github.com/egmontkob/eb114294efbcd5adb1944c9f3cb5feda
def makeClickableFileLink(text: str, url: str) -> str:
    """
    Helper to convert text into a OSC 8 embedded hyperlink.

    The goal is that we should be able to click a file and it open in the explorer.
    """
    return f"\x1b]8;;{url}\x1b\\{text}\x1b]8;;\x1b\\"

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