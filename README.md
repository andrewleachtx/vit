# vit
A CLI tool for attaching visuals to git commits.

## Compatibility
Runs on Windows and Linux (without rigorous testing), **may** work with macOS.

## Dependencies
[uv](https://docs.astral.sh/uv/getting-started/installation/) and `python>=3.11`.

uv is very fast, it dropped command runtime from 0.5s -> 0.1s. Hence why I am using it over `poetry`.

uv will just install the needed packages, but if you would like, see the `pyproject.toml` for exacts.

## Installation
In project root:

```bash
uv lock && uv sync
uv build
```

Now you should have the sdist and wheel in `dist/`. If you are using a virtual env, you should run:

```
python -m venv .venv
source .venv/bin/activate
```

The most plug and play approach is just installing somewhere your PATH has access:

```
python -m pip install --user vit-0.1.0-py3-none-any.whl
```

## Usage
Run `vit --help` to see the commands. They are meant to be adjacent to `git` commands.

Meant to integrate with existing git repos, so only run `vit init` where repositories exist.

## License

This project is licensed under the MIT License. See [LICENSE.md](LICENSE.md) for more details.
