# https://gist.github.com/egmontkob/eb114294efbcd5adb1944c9f3cb5feda
def makeClickableFileLink(text: str, url: str) -> str:
    """
    Helper to convert text into a OSC 8 embedded hyperlink.

    The goal is that we should be able to click a file and it open in the explorer.
    """
    return f"\x1b]8;;{url}\x1b\\{text}\x1b]8;;\x1b\\"