from pathlib import Path
import typer
import json

DEFAULT_CONFIG = {
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

def initConfig():
    """
    1. Search for the git project root
    2. Build the .vit/ directory at that location
    3. Create the config.json with our default config
    4. Create skeleton for timeline.json, as well as media/ ?
    """

    # 1)
    projectRoot = findGitRoot()

    # 2)
    vitDir = projectRoot/DEFAULT_CONFIG["storageDir"]
    vitDir.mkdir(exist_ok=True)

    # 3)
    configPath = vitDir/"config.json"
    if configPath.exists():
        typer.secho(f"Already initialized at {configPath}, ignoring", fg=typer.colors.YELLOW)
    else:
        configPath.write_text(json.dumps(DEFAULT_CONFIG, indent=2))
        typer.secho(f"Wrote config to {configPath}", fg=typer.colors.GREEN)

    # 4)
    timelinePath = vitDir/DEFAULT_CONFIG["timelineFile"]
    if not timelinePath.exists():
        timelinePath.write_text("[]")
        typer.secho(f"Created empty timeline at {timelinePath}", fg=typer.colors.GREEN)