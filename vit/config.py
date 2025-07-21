from pathlib import Path
import typer
import json
from types import SimpleNamespace

DEFAULT_CONFIG = {
    "repoPath" : "",
    "storageDir" : ".vit",
    "mediaSubdir" : "media",
    "timelineFile" : "timeline.json"
}

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

def initConfig(overwrite=False):
    """
    1. Search for the git project root
    2. Build the .vit/ directory at that location
    3. Create the config.json with our default config
    4. Create skeleton for timeline.json, as well as media/
    """

    # 1)
    repoPath = findGitRoot()

    # 2)
    vitDir = repoPath/DEFAULT_CONFIG["storageDir"]
    vitDir.mkdir(exist_ok=True)

    # 3)
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

    # 4)
    timelinePath = vitDir / DEFAULT_CONFIG["timelineFile"]
    if timelinePath.exists():
        if overwrite:
            backupTimeline = vitDir / (DEFAULT_CONFIG["timelineFile"] + ".backup")
            timelinePath.replace(backupTimeline)
            typer.secho(f"Backed up existing timeline to {backupTimeline}", fg=typer.colors.YELLOW)
        else:
            typer.secho(f"Already initialized at {timelinePath}, ignoring. Add --overwrite to delete your existing timeline data and reinit!", fg=typer.colors.YELLOW)
    if not timelinePath.exists() or overwrite:
        timelinePath.write_text("[]")
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