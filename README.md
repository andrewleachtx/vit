# vit

vit is a minimal CLI tool for attaching visuals to Git commits. It is read-only on your Git history; vit cannot change anything related to your Git commits or tracked files.

I felt like I wanted to record the visual improvements my commits were making where they existed in my graphics work, so I made this tool.

Vit requires you are in a Git repository, and stores itself purely locally copies in `.git/vit/` - the cost of storage you pay is up to how much you would like to track!

## Installation

The planned Homebrew package is `vit-cli`. Installation instructions will be added here when the release is available. The command you run stays `vit`:

```bash
vit attach render.png
vit show
```

## Attach and show

From any Git repository with at least one commit:

```bash
vit attach render.png
vit attach comparison.gif demo.mp4
vit show
```

Both commands use your latest commit (`HEAD`) by default. To choose an older commit, supply its full hash or a unique prefix:

```bash
vit attach render.png comparison.gif --hash a83f4c2
vit show --hash a83f4c2
```

`vit show` lists the saved files, with clickable names in terminals that support links. When redirected, it includes file URLs you can open or copy.

## Example

```bash
git add src/
git commit -m "Increase epsilon for shadow acne"

vit attach reflection.png demo.mp4
vit show
```

vit keeps its own copies locally within the `.git/`

Attaching the same filename and contents again safely skips that file. To attach a different file with the same name, rename it first. If any file is missing or conflicts with an existing attachment, none of the requested files are attached.

Run `vit --help` or `vit attach --help` for command help.

## Development

You will need [uv](https://docs.astral.sh/uv/). It manages the development interpreter and dependencies:

```bash
git clone https://github.com/andrewleachtx/vit.git
cd vit
uv sync
uv run pytest
uv run vit --help
```

Use `uv run vit attach <file>` to test any of your local dev changes. Build a distribution with `uv build`.

Python 3.11 or newer is supported. The CLI uses only the Python standard library at runtime.

## License

[MIT](LICENSE.md)
