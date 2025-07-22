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
        # subprocess.run(f"git commit -m \"{message}\"".split(), check=True)
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
            # TODO: metadata https://docs.python.org/3/library/shutil.html
            shutil.copy(src, dstDir / src.name)
            paths.append(str(Path(config.mediaSubdir) / commitHash / src.name))

        typer.secho(f"Attached {len(attach)} file(s) to {dstDir}", fg=typer.colors.GREEN)
    
    # Update the timeline
    timelinePath = config.storageDir / config.timelineFile
    try:
        timeline = json.loads(timelinePath.read_text())
    except json.JSONDecodeError:
        timeline = []

    entry = {
        "commit" : commitHash,
        "attachments" : paths
    }

    timeline.append(entry)
    timelinePath.write_text(json.dumps(timeline, indent=2))
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
    if timelinePath:
        entries = json.loads(timelinePath.read_text())
        timelineData = {
            entry["commit"] : entry.get("attachments", []) for entry in entries
        }

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

        typer.secho(f"commit {hash}: ", fg=typer.colors.YELLOW, nl=False)
        typer.secho(f"\"{message}\"", fg=typer.colors.GREEN, nl=False)
        typer.secho(f" @ {prettyDate}")

        if parents.strip():
            typer.secho(f"Parent Commit(s): {parents[:7]}", fg=typer.colors.CYAN)

        attachments = timelineData.get(hash, [])
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

if __name__ == "__main__":
    app()