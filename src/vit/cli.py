"""Command parsing and entry point for app

Internally we store git repo data and vit storage in separate modules.
"""

import argparse
from pathlib import Path
import sys

from vit import __version__
from vit.errors import VitError
from vit.repository import Repository


def readable(value: str) -> str:
    # Filenames and commit subjects must not inject terminal control sequences
    return "".join(c if c.isprintable() else repr(c)[1:-1] for c in value)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture what your Git commits changed visually.")
    parser.add_argument("--version", action="version", version=f"vit {__version__}")

    commands = parser.add_subparsers(dest="command", required=True)

    # Attach
    attach = commands.add_parser("attach", help="Attach files to a commit")
    attach.add_argument("files", nargs="+", type=Path, help="Images, GIFs, videos, or other files")

    # Show
    show = commands.add_parser("show", help="Show a commit's attached files")
    for command in (attach, show):
        command.add_argument("--hash", dest="commit_hash", help="Full or unique partial commit hash (default: HEAD)")
    args = parser.parse_args(argv)

    # Try loading the git/vit store (if it exists) otherwise fail
    try:
        # Look for our git/vit repository, exit if git throws "fatal: not a git repository (or any of the parent directories): .git"
        repository = Repository(Path.cwd())
        commit = repository.git.resolve(args.commit_hash)
        label = f'{commit.short_hash} "{readable(commit.subject)}"'
        if args.command == "attach":
            added, skipped = repository.attach(commit, args.files)
            if added:
                print(f"Attached {len(added)} {'file' if len(added) == 1 else 'files'} to {label}\n")
                for name in added:
                    print(f"  {readable(name)}")
            if skipped:
                print(f"Already attached to {label}: {', '.join(readable(n) for n in skipped)}")
        else:
            artifacts = repository.show(commit)
            if not artifacts:
                print(f"No attachments for {label}")
            else:
                print(f"Attachments for {label}\n")
                for name, path in artifacts:
                    if sys.stdout.isatty():
                        print(f"  \033]8;;{path.as_uri()}\033\\{readable(name)}\033]8;;\033\\")
                    else:
                        print(f"  {readable(name)}\n    {path.as_uri()}")
        return 0
    except VitError as error:
        print(f"error: {readable(str(error))}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("error: interrupted; run vit show to check saved attachments", file=sys.stderr)
        return 130
    except OSError as error:
        print(f"error: could not access files: {readable(error.strerror or str(error))}; check permissions and available disk space", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
