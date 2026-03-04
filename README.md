# nopywer

Visit the homepage of the project: https://vfinel.github.io/nopywer/

Nopywer analyses power grids to compute current flowing through cables, 3-phase balance, and voltage drop. It also includes a cable-layout optimizer (MST + cost-based local search) exposed via a FastAPI server.

## Setup

Requires Python ≥ 3.12 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

This installs all runtime and dev dependencies (ruff, pytest, pre-commit…) in a local `.venv`.

### Input data

Nopywer reads a GeoJSON file containing nodes and cables. A spreadsheet (`.ods`) can optionally be provided for equipment inventory.

The spreadsheet must comply with the following rules:
- `.ods` format
- Columns: `Project` (must match node names), `which phase(1, 2, 3, T, U or Y)`, `worstcase power [W]`
- No notes or comments on cells

## Usage

```bash
nopywer-analyze input.geojson
```

See `nopywer-analyze --help` for all options.

To start the optimization API server:

```bash
nopywer-server
```

## Contributing

Contributions are welcome! See also [CONTRIBUTING.md](docs/CONTRIBUTING.md) for guidelines on reporting bugs, suggesting features, and submitting PRs.

### Lint

The project uses [ruff](https://docs.astral.sh/ruff/) for linting and formatting (line length: 100, see `pyproject.toml` for the full config).

```bash
uv run ruff check .
```

Pre-commit hooks are configured to run ruff automatically on each commit. To install them:

```bash
uv run pre-commit install
```

### Test

Tests use [pytest](https://docs.pytest.org/).

```bash
uv run pytest
```

### CI

A GitHub Actions workflow runs on every pull request and on pushes to `main`/`develop`. It checks:
1. `ruff check .` — lint
2. `pytest` — tests

## Troubleshooting

If you have errors, please reach out (include the complete console output).

- Loads not using power appear on the "on map but missing on spreadsheet" list → add them to the spreadsheet
- Loads not using power appear on the "on spreadsheet but missing on map" list → remove them from the spreadsheet

## Disclaimer

While efforts have been made to ensure this project's functionality, it is provided "as is" without any warranties.
