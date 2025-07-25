from pathlib import Path
import typer
import json
from types import SimpleNamespace

from vit.utils import findGitRoot

DEFAULT_CONFIG = {
    "repoPath" : "",
    "storageDir" : ".vit",
    "mediaSubdir" : "media",
    "timelineFile" : "timeline.json"
}

def initConfig(overwrite=False):
    """
    Helper that initializes the config files (config.json and timeline.json) and directory structure.
    """

    # Search for the git project root
    repoPath = findGitRoot()

    # Build the .vit/ directory at that location
    vitDir = repoPath/DEFAULT_CONFIG["storageDir"]
    vitDir.mkdir(exist_ok=True)

    # Create the config.json with our default config
    configPath = vitDir / "config.json"
    configToWrite = {
        **DEFAULT_CONFIG,
        "repoPath" : str(repoPath)
    }

    if configPath.exists():
        if overwrite:
            backupConfig = vitDir / "config.json.backup"
            configPath.replace(backupConfig)
            typer.secho(f"Overwriting - if this was a mistake, one copy of your timeline.json and config.json are backed up to {backupConfig}!", fg=typer.colors.YELLOW)
        else:
            typer.secho(f"Already initialized at {configPath}, ignoring. Add --overwrite to delete your existing timeline data and reinit!", fg=typer.colors.YELLOW)
            return
    if not configPath.exists() or overwrite:
        configPath.write_text(json.dumps(configToWrite, indent=2))
        typer.secho(f"Wrote config to {configPath}", fg=typer.colors.GREEN)

    # 4) Create skeleton for timeline.json, as well as media/
    timelinePath = vitDir / DEFAULT_CONFIG["timelineFile"]
    if timelinePath.exists():
        if overwrite:
            backupTimeline = vitDir / (DEFAULT_CONFIG["timelineFile"] + ".backup")
            timelinePath.replace(backupTimeline)
            typer.secho(f"Backed up existing timeline to {backupTimeline}", fg=typer.colors.YELLOW)
        else:
            typer.secho(f"Already initialized at {timelinePath}, ignoring. Add --overwrite to delete your existing timeline data and reinit!", fg=typer.colors.YELLOW)
    if not timelinePath.exists() or overwrite:
        timelinePath.write_text("{}")
        typer.secho(f"Created empty timeline at {timelinePath}", fg=typer.colors.GREEN)

    mediaDir = vitDir / DEFAULT_CONFIG["mediaSubdir"]
    mediaDir.mkdir(exist_ok=True)

def loadConfig() -> SimpleNamespace:
    """
    Loads the relevant project metadata from .vit/config.json
    """
    repoPath = findGitRoot()
    configPath = repoPath / ".vit" / "config.json"
    if not configPath.exists():
        typer.secho("Please run `vit init` in the repository first!", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    
    data = json.loads(configPath.read_text())

    for key in DEFAULT_CONFIG.keys():
        if key not in data:
            raise Exception(f"Missing key \"{key}\" in config.json")
    
    storage = Path(data["storageDir"])
    if not storage.is_absolute():
        storage = Path(data["repoPath"]) / storage
    
    return SimpleNamespace(
        repoPath = Path(data["repoPath"]),
        storageDir = storage,
        mediaSubdir = data["mediaSubdir"],
        timelineFile = data["timelineFile"]
    )