# MarketLab

MarketLab is a local-first research system for market-regime analysis and large-cap opportunity tracking.

The implementation follows `DESIGN.md`: point-in-time observations, deterministic calculations, bounded agent outputs, and reproducible reports.

See `IMPLEMENTATION.md` for current implementation status and the next small slices.

## Current Baseline

This repository currently contains only the first useful contracts:

- Python package skeleton.
- Minimal `marketlab` CLI entrypoint.
- Snapshot identity model.
- Bulltard recap source URL extraction against local recap artifacts.
- Bulltard ingest for the first targeted ranked-trades view.
- Loguru-based CLI logging with informative context fields.
- Focused tests for URL extraction and snapshot serialization.

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

Retrieve and parse the first targeted view:

```bash
uv run marketlab bulltard ingest \
  --date 2026-08-24 \
  --view ranked-option-trades \
  data/inbox/bulltard/recap-2026-08-24.html
```

The current `ingest` command resolves the recap, signed access link, and view route, retrieves the
view into `data/debug/bulltard/...` for parser troubleshooting, and writes parsed rows to
`data/observations/bulltard/...`.

Retrieve the Bulltard detail page for one ticker from the same signed recap access:

```bash
uv run marketlab bulltard ticker \
  INTC \
  --date 2026-08-24 \
  data/inbox/bulltard/recap-2026-08-24.html
```

Ticker pages are currently saved under `data/debug/bulltard/tickers/<SYMBOL>/`.

If you save the whole Gmail web page, the file may contain only Gmail/Substack shell links rather
than the database link. For bring-up, use a saved message artifact or a small local text file
containing the copied link address for the recap's database/app button. Gmail may wrap the useful
Substack redirect as a `https://www.google.com/url?q=...` link; the tool unwraps that form.

CLI logging uses Loguru. Set verbosity with:

```bash
uv run marketlab --log-level DEBUG bulltard inspect-recap tests/fixtures/bulltard/recap.html
```

The live research database, inbox files, generated observations, debug payloads, reports, and credentials are intentionally gitignored.
