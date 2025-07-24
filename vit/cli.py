from datetime import datetime
import json
import shutil
import subprocess
from git import Repo
import typer
from vit.config import initConfig, loadConfig
from pathlib import Path

from vit.utils import makeClickableFileLink, getDirSize, bytesToHuman

app = typer.Typer()

@app.command()
def init(
    overwrite: bool = typer.Option(False, "--overwrite", "-o", help="If set, replaces any .vit/config.json and timeline.json as if they did not exist. Use at your own caution!")
):
    """
    Initializes the current Git repo for vit usage.  
    """

    try:
        initConfig(overwrite=overwrite)
    except Exception as e:
        typer.secho(f"Failed to initialize vit: {e} -- are you inside a git repository?", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    
@app.command()
def test():
    """
    Test command
    """
    typer.secho(f"Test worked! Run vit init --help for a list of commands.", fg=typer.colors.GREEN)

# FIXME: Guarantee this is atomic; i.e. the commit shouldn't go through if --attach has erroneous args 
@app.command()
def commit(
    message: str = typer.Option(..., "-m", help="Commit message"),
    attach: list[Path] = typer.Option([], "--attach",  exists=True, file_okay=True,  dir_okay=True,  help="Media files to attach, i.e. vit commit -m \"my commit message!\" --attach a.gif b.png c.mp4")
):
    """
    Commits changes, and attaches media files (images, gifs, videos, etc.) to the commit hash.

    Should be run after `git add` -- this runs `git commit` under the hood.

    Simply copies attachments to ./vit/media/ and stores sparse metadata (commit & attachments)
    """
    # Grab the config paths & media storage metadata
    config = loadConfig()

    # Actually run git commit
    try:
        subprocess.run(["git", "commit", "-m", message], check=True)
    except subprocess.CalledProcessError as e:
        typer.secho(f"Git commit failed: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    
    repo = Repo(config.repoPath)
    commitHash = repo.head.commit.hexsha[:7]
    typer.secho(f"Committed as {commitHash}", fg=typer.colors.GREEN)

    # Search for attachments and attach them
    paths = []
    if attach:
        mediaDir = config.storageDir / config.mediaSubdir
        dstDir = mediaDir / commitHash
        dstDir.mkdir(parents=True, exist_ok=True)

        for src in attach:
            # FIXME: metadata not fully copied https://docs.python.org/3/library/shutil.html
            shutil.copy(src, dstDir / src.name)
            paths.append(str(Path(config.mediaSubdir) / commitHash / src.name))

        typer.secho(f"Attached {len(attach)} file(s) to {dstDir}", fg=typer.colors.GREEN)
    
    # Update the timeline
    timelinePath = config.storageDir / config.timelineFile
    timelineData = {}
    if timelinePath.exists():
        timelineData = json.loads(timelinePath.read_text())

    timelineData[commitHash] = {
        "attachments" : paths
    }

    timelinePath.write_text(json.dumps(timelineData, indent=2))
    typer.secho(f"Updated timeline at {timelinePath}", fg=typer.colors.GREEN)

@app.command()
def timeline(
    count: int = typer.Option(30, "--count", "-n", help="Number of commits from most recent to show")
):
    """
    Displays an in-terminal timeline of all git commits, and displays clickable links to files
    that were attached.

    Essentially an extension to `git log --parents`.
    """
    config = loadConfig()
    repoPath = config.repoPath
    timelinePath = config.storageDir / config.timelineFile

    timelineData = {}
    if timelinePath.exists():
        timelineData = json.loads(timelinePath.read_text())
    else:
        typer.secho(f"Failed to locate timeline path \"{timelinePath}\", have you run `vit init`?", fg=typer.colors.RED)
        raise typer.Exit(code=1)

    fmt = f"%h|%cI|%s|%P"
    rawOutput = subprocess.check_output(
        ["git", "log", f"-n{count}", f"--pretty=format:{fmt}"],
        cwd=repoPath,
        text=True
    )

    for line in rawOutput.splitlines():
        hash, isoDate, message, parents = line.split('|', 3)

        formattedDate = datetime.strptime(isoDate, "%Y-%m-%dT%H:%M:%S%z")
        prettyDate = formattedDate.strftime("%b %d, %Y %I:%M %p")

        typer.secho(f"commit [{hash}]: ", fg=typer.colors.YELLOW, nl=False)
        typer.secho(f"\"{message}\"", fg=typer.colors.GREEN, nl=False)
        typer.secho(f" @ {prettyDate}")

        if parents.strip():
            typer.secho(f"Parent Commit(s): {parents[:7]}", fg=typer.colors.CYAN)

        attachments = timelineData.get(hash, {}).get("attachments", [])
        if attachments:
            typer.secho("Attachments:", fg=typer.colors.BLUE)
            for relPath in attachments:
                absPath = (config.storageDir / relPath).resolve()
                fileUrl = f"file://{absPath}"
                linkText = makeClickableFileLink(Path(relPath).name, fileUrl)
                typer.echo(f"\t- {linkText} ({fileUrl})")
        
        typer.echo()

@app.command()
def overhead():
    """
    Returns how much disk .vit/ is using, including media.
    """

    config = loadConfig()
    vitDir = config.storageDir
    mediaDir = vitDir / config.mediaSubdir

    if not vitDir.exists():
        typer.secho("No .vit/ directory found, run `vit init` first.", fg=typer.colors.RED)
    
    totalVitSize = getDirSize(vitDir)
    mediaSize = getDirSize(mediaDir)
    metaSize = totalVitSize - mediaSize

    typer.secho("Total .vit/ size (with directory sizes): ", fg=typer.colors.GREEN, nl=False)
    typer.secho(bytesToHuman(totalVitSize), fg=typer.colors.CYAN, nl=False)

    typer.echo(" (", nl=False)
    typer.secho(f"Metadata: {bytesToHuman(metaSize)}", fg=typer.colors.MAGENTA, nl=False)
    typer.echo(", ", nl=False)
    typer.secho(f"Media: {bytesToHuman(mediaSize)}", fg=typer.colors.BLUE, nl=False)
    typer.echo(")")

@app.command()
def undo(
    number: int = typer.Option(1, "--number", "-n", help="Number of commits to undo"),
    mode: str = typer.Option("mixed", "--mode", help="Reset mode, i.e. soft, mixed, or hard (like `git reset`).")
):
    """
    Undo the last `number` commit(s), which rolls back both git and the vit media/timeline as if it never happened.

    By default, does --mixed, otherwise can do --soft or --hard.
    """
    config = loadConfig()
    repoPath = config.repoPath
    timelinePath = config.storageDir / config.timelineFile

    timelineData = {}
    if timelinePath.exists():
        timelineData = json.loads(timelinePath.read_text())
    else:
        typer.secho(f"Failed to locate timeline path, have you run `vit init`?", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    
    # We shouldn't undo n commits from our timeline, but n git commits -- of them, remove from our timeline any that also show up.
    lastHashes = []
    try:
        raw = subprocess.check_output(
            ["git", "log", f"-n{number}", "--pretty=format:%h"],
            cwd=repoPath, text=True
        )
        lastHashes = raw.splitlines()
    except subprocess.CalledProcessError as e:
        typer.secho(f"Failed `git log`: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    
    if number != len(lastHashes):
        typer.secho(f"Only found {len(lastHashes)} commits; --number was {number}", fg=typer.colors.RED)
        raise typer.Exit(1)

    typer.secho(f"Undoing these Git commit(s):", fg=typer.colors.YELLOW)
    for h in lastHashes:
        typer.secho(f"\t [{h}]", fg=typer.colors.YELLOW)

    if not typer.confirm("Proceed with `git reset --{mode} HEAD~{number}`?"):
        typer.secho("Aborted `vit undo`", fg=typer.colors.CYAN)
        raise typer.Exit(code=0)
    
    # Actually git reset
    try:
        subprocess.run(
            ["git", "reset", f"--{mode}", f"HEAD~{number}"],
            check=True
        )
    except subprocess.CalledProcessError as e:
        typer.secho(f"Failed `git reset`: {e}", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    
    # Remove hashes and their data
    mediaDir = config.storageDir / config.mediaSubdir
    for h in lastHashes:
        if h in timelineData:
            h = "d2ac47a"
            folder = mediaDir / h
            if folder.exists():
                shutil.rmtree(folder)
            timelineData.pop(h)

    timelinePath.write_text(json.dumps(timelineData, indent=2))
    typer.secho(f"Successfully deleted {number} commits.", fg=typer.colors.GREEN)

@app.command()
def modify():
    """
    TODO:
    
    Attach/detach images to an arbitrary commit. This will have to linear search for the correct spot in our json file,
    which may be very slow as we don't store time.
    """

@app.command()
def graph():
    """
    TODO:

    Visualizes timeline including commits not in timeline.json
    """

if __name__ == "__main__":
    app()