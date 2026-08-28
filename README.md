# MarketLab

MarketLab is a local-first research system for market-regime analysis and large-cap opportunity tracking.

The implementation follows `DESIGN.md`: point-in-time observations, deterministic calculations, bounded agent outputs, and reproducible reports.

See `IMPLEMENTATION.md` for milestone status and the next research deliverables.

## Current Baseline

Milestones 1 and 2 are complete: the repo can capture the daily Bulltard candidate set, refresh independent price history, validate candidates, and replay forward outcomes.

Implemented:

- Python package skeleton with `uv`, Typer CLI, Loguru logging, and focused tests.
- Repo-local `bin/marketlab` command shim.
- Snapshot identity model.
- Bulltard recap source URL extraction against local text or HTML recap artifacts.
- Bulltard ranked option trades ingest.
- Trades Of Interest parsing from the recap.
- Ticker detail retrieval and flow-history parsing.
- Candidate review table that combines ranked rows, recap interest, and any fetched ticker-flow detail.
- One-command daily Bulltard workflow for candidate capture, optional price refresh, validation, and outcome replay.
- Daily OHLCV price fetch from Yahoo Finance through `yfinance` into local observations.
- Local daily OHLCV CSV import into the same price observation format.
- Bulltard candidate validation against independent price, volume, trend, drawdown, and relative-strength features.
- Bulltard outcome replay summaries from saved validation snapshots.

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

Retrieve and parse the Bulltard detail page for one ticker from the same signed recap access:

```bash
uv run marketlab bulltard ticker \
  INTC \
  data/inbox/bulltard/recap-2026-08-24.html \
  --date 2026-08-24
```

Ticker pages are currently saved under `data/debug/bulltard/tickers/<SYMBOL>/`.
Ticker flow observations are written under
`data/observations/bulltard/ticker_flow/<SYMBOL>/`.

Parse the recap's Trades Of Interest section into local observations:

```bash
uv run marketlab bulltard trades-of-interest \
  --date 2026-08-26 \
  data/inbox/bulltard/recap-2026-08-26.html
```

Review ranked candidates and attach any ticker-flow detail already collected:

```bash
uv run marketlab bulltard candidates --date 2026-08-26
```

Run the daily Bulltard loop in one command:

```bash
uv run marketlab bulltard daily \
  --date 2026-08-26 \
  data/inbox/bulltard/recap-2026-08-26.html
```

By default, `daily` ingests the ranked database view, parses Trades Of Interest from the recap,
fetches ticker detail for the Trades Of Interest names, and prints the candidate review table.
Use `--top-ranked N` to also fetch detail for the top N ranked database names, or
`--no-ticker-details` to skip detail fetches.

Run the full M2 daily research loop:

```bash
./bin/marketlab bulltard daily \
  --date 2026-08-28 \
  data/inbox/bulltard/recap-2026-08-28.html \
  --fetch-prices \
  --validate \
  --outcomes
```

`--fetch-prices` refreshes Yahoo daily prices for the captured candidates plus `SPY` and `QQQ`.
The default price window starts 550 calendar days before `--date` and ends today. `--outcomes`
replays saved validation snapshots from the earliest saved snapshot through `--date` by default.
Use `--outcome-start` and `--outcome-end` to override that replay window.

## Candidate Validation

For normal daily use, let `bulltard daily --fetch-prices` refresh the candidate price set. To refresh a captured date explicitly:

```bash
./bin/marketlab bulltard refresh-prices \
  --date 2026-08-26 \
  --start 2025-01-01 \
  --end 2026-08-27
```

You can still fetch independent daily OHLCV history for arbitrary tickers:

```bash
./bin/marketlab prices fetch-yahoo META,XAR,SRRK,DKS,QXO,SPY,QQQ \
  --start 2025-01-01 \
  --end 2026-08-27
```

This uses the actively maintained `yfinance` package. It stores raw `close` and `adjusted_close`; MarketLab uses adjusted close for return/outcome calculations when available.

The older Stooq path remains available as `prices fetch`, but it may require a Stooq API key:

```bash
./bin/marketlab prices fetch META,SPY --start 2025-01-01 --end 2026-08-27
```

Or import a local CSV with `Date, Open, High, Low, Close, Volume` columns:

```bash
./bin/marketlab prices import-csv META ~/Downloads/META.csv --source manual
```

Validate a captured Bulltard candidate set from local price observations:

```bash
./bin/marketlab bulltard validate --date 2026-08-26
```

Or run capture, price refresh, validation, and saved-snapshot outcome replay together:

```bash
./bin/marketlab bulltard daily \
  --date 2026-08-28 \
  data/inbox/bulltard/recap-2026-08-28.html \
  --fetch-prices \
  --validate \
  --outcomes
```

Validation snapshots are written under `data/snapshots/bulltard/candidates/`.

Replay forward outcomes after enough future price rows exist:

```bash
./bin/marketlab bulltard outcomes --start 2026-08-01 --end 2026-08-26
```

If you save the whole Gmail web page, the file may contain only Gmail/Substack shell links rather
than the database link. For bring-up, use a saved message artifact or a small local text file
containing the copied link address for the recap's database/app button. Gmail may wrap the useful
Substack redirect as a `https://www.google.com/url?q=...` link; the tool unwraps that form.

CLI logging uses Loguru. Set verbosity with:

```bash
uv run marketlab --log-level DEBUG bulltard inspect-recap tests/fixtures/bulltard/recap.html
```

The live research database, inbox files, generated observations, debug payloads, reports, and credentials are intentionally gitignored.
