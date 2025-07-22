import datetime
import json
import shutil
import subprocess
from git import Repo
import typer
from vit.config import initConfig, loadConfig
from pathlib import Path

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
    typer.secho(f"Test worked!", fg=typer.colors.GREEN)

@app.command()
def commit(
    message: str = typer.Option(..., "-m", help="Commit message"),
    attach: list[Path] = typer.Option([], "--attach",  exists=True, file_okay=True,  dir_okay=True,  help="Media files to attach, i.e. vit commit -m \"my commit message!\" --attach a.gif b.png c.mp4")
):
    """
    Commits changes, and attaches media files (images, gifs, videos, etc.) to the commit hash

    Should be run after `git add` -- this runs `git commit` under the hood.
    """
    # Grab the config paths & media storage metadata
    config = loadConfig()

    # Actually run git commit
    try:
        subprocess.run(f"git commit -m {message}".split(), check=True)
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
        "message" : message,
        "time" : datetime.datetime.now().isoformat(),
        "attachments" : paths
    }

    timeline.append(entry)
    timelinePath.write_text(json.dumps(timeline, indent=2))
    typer.secho(f"Updated timeline at {timelinePath}", fg=typer.colors.GREEN)

if __name__ == "__main__":
    app()