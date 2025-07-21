import typer
from vit.config import initConfig

app = typer.Typer()

@app.command()
def init():
    """
        Initializes the current Git repo for vit usage.  
    """

    try:
        initConfig()
    except Exception as e:
        typer.secho(f"Failed to initialize vit: {e} -- are you inside a git repository?", fg=typer.colors.RED)
        raise typer.Exit(code=1)
    
@app.command()
def test():
    """
        Test command
    """
    typer.secho(f"Test worked!", fg=typer.colors.GREEN)

if __name__ == "__main__":
    app()