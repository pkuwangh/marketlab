# MarketLab

MarketLab is a local-first research system for market-regime analysis and large-cap opportunity tracking.

The implementation follows `DESIGN.md`: immutable source captures, point-in-time snapshots, deterministic calculations, bounded agent outputs, and reproducible reports.

## Current Baseline

This repository currently contains only the first contracts:

- Python package skeleton.
- Minimal `marketlab` CLI entrypoint.
- Snapshot identity model.
- Bulltard capture manifest and raw artifact models.
- Bulltard recap source URL extraction and app-route discovery against local artifacts.
- Loguru-based CLI logging with informative context fields.
- Focused tests for URL extraction, hashes, manifests, and snapshot serialization.

## Development

```bash
python -m pytest -q
```

or, with `uv`:

```bash
uv run pytest -q
```

Format, lint, and autofix:

```bash
uv run ruff format
uv run ruff check --fix
```

## Local Bin

Repo-local command shims live in `bin/`. The `marketlab` executable is linked there:

```bash
./bin/marketlab --help
```

The link points into `.venv/bin/`, so run `uv sync` or `uv run ...` first on a fresh checkout.

## Bulltard Utilities

Inspect a local recap and print the signed source URL:

```bash
uv run marketlab bulltard inspect-recap tests/fixtures/bulltard/recap.html
```

If you save the whole Gmail web page, the file may contain only Gmail/Substack shell links rather
than the database link. For this command, use a saved message artifact or a small local text file
containing the copied link address for the recap's database/app button. Gmail may wrap the useful
Substack redirect as a `https://www.google.com/url?q=...` link; the tool unwraps that form.

CLI logging uses Loguru. Set verbosity with:

```bash
uv run marketlab --log-level DEBUG bulltard inspect-recap tests/fixtures/bulltard/recap.html
```

The live research database, raw captures, generated reports, and credentials are intentionally gitignored.
