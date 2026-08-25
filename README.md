# MarketLab

MarketLab is a local-first research system for market-regime analysis and large-cap opportunity tracking.

The implementation follows `DESIGN.md`: immutable source captures, point-in-time snapshots, deterministic calculations, bounded agent outputs, and reproducible reports.

## Current Baseline

This repository currently contains only the first contracts:

- Python package skeleton.
- Minimal `marketlab` CLI entrypoint.
- Snapshot identity model.
- Bulltard capture manifest and raw artifact models.
- URL redaction helpers for credential-bearing capture URLs.
- Focused tests for redaction, hashes, manifests, and snapshot serialization.

## Development

```bash
python -m pytest -q
```

or, with `uv`:

```bash
uv run pytest -q
```

## Local Bin

Repo-local command shims live in `bin/`. The `marketlab` executable is linked there:

```bash
./bin/marketlab --help
```

The link points into `.venv/bin/`, so run `uv sync` or `uv run ...` first on a fresh checkout.

The live research database, raw captures, generated reports, and credentials are intentionally gitignored.
