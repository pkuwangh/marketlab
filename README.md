# MarketLab

MarketLab is a local-first research system for market-regime analysis and large-cap opportunity tracking.

The implementation follows `DESIGN.md`: point-in-time observations, deterministic calculations, bounded agent outputs, and reproducible reports.

See `IMPLEMENTATION.md` for milestone status and the next research deliverables.

## Current Baseline

Milestones 1 through 7 are complete at v0 depth: the repo can capture the daily Bulltard candidate set, refresh independent price history, validate candidates, compute market regime, derive bounded portfolio policy, refresh a local DuckDB research store, replay forward outcomes, and render reproducible reports/charts.

Implemented:

- Python package skeleton with `uv`, Typer CLI, Loguru logging, and focused tests.
- Repo-local `bin/marketlab` command shim.
- Snapshot identity model.
- Snapshot identity fields on regime, market-signal, candidate-validation, and policy snapshot payloads.
- Canonical versioned snapshot paths by date, signal time, snapshot version, and artifact version, with legacy flat-file loaders retained for migration.
- Bulltard recap source URL extraction against local text or HTML recap artifacts.
- Bulltard ranked option trades ingest.
- Bulltard ingest metadata sidecars that link parsed rows to retrieval context and parser version.
- Trades Of Interest parsing from the recap.
- Ticker detail retrieval and flow-history parsing.
- Candidate review table that combines ranked rows, recap interest, and any fetched ticker-flow detail.
- One-command daily Bulltard workflow for candidate capture, optional price refresh, validation, and outcome replay.
- Daily OHLCV price fetch from Yahoo Finance through `yfinance` into local observations.
- Price and scalar market-series observations with availability/retrieval metadata and non-overwrite guards for same-date corrections.
- Local daily OHLCV CSV import into the same price observation format.
- Bulltard candidate validation against independent price, volume, trend, drawdown, and relative-strength features.
- Bulltard outcome replay summaries from saved validation snapshots.
- Market regime snapshots from SPY/QQQ trend, SPY volatility/VIX, RSP/IWM participation, and HYG/TLT risk appetite.
- Market regime outcome replay summaries against forward SPY/QQQ returns and drawdowns.
- Expanded market-signal snapshots including VVIX and FRED-backed credit/liquidity/rates rows when available.
- Market regime and policy computation consume saved market-signal snapshots as the v0 evidence boundary when available; generated signal rows carry structured numeric details for replay.
- Normalized stretch/washout pressure scores and rare action states.
- Portfolio policy snapshots that map regime action states into bounded marginal beta, cash, overlay, and single-name risk posture.
- Daily policy reports that combine regime state, market signals, policy posture, and Bulltard candidate context.
- Local DuckDB research store refresh from JSON/JSONL source observations, Bulltard ingest rows, and snapshots, with optional Parquet exports.
- Self-contained HTML/SVG regime chart generation from saved price, regime, market-signal, and policy snapshots.
- Self-contained HTML/SVG opportunity chart generation for one saved Bulltard candidate.

Current limitations:

- Legacy flat snapshot files are still supported for read compatibility; there is no migration command yet to move old files into the canonical layout.
- Portfolio policy remains a hard-threshold v0 mapper, not a fully calibrated policy with hysteresis/cooldowns.
- Candidate validation is not yet the full opportunity engine: options-liquidity, fundamental viability, instrument suitability, lifecycle episodes, thesis, and invalidation are still future work.
- Market-signal production still uses hard-coded v0 feature thresholds; richer calibrated signal families are future work.

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

## Normal Daily Use

The routine operating path is one command:

```bash
./bin/marketlab daily
```

By default it uses today's local date, refreshes market sources, writes the regime snapshot,
uses `data/inbox/bulltard/recap-YYYY-MM-DD.html` when that recap file exists, validates
captured candidates, renders the daily policy report and regime chart, and refreshes the
local DuckDB store. If the recap file is missing, the market-regime and policy loop still
runs and Bulltard is skipped.

For a specific date:

```bash
./bin/marketlab daily --date 2026-08-31
```

The lower-level `regime`, `bulltard`, `policy`, `chart`, and `store` commands remain available
for debugging, backfills, and focused research.

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

Run the full daily Bulltard candidate loop:

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

## Market Regime

Compute the market regime directly:

```bash
./bin/marketlab regime snapshot --date 2026-08-28 --fetch-prices
```

Market regime is intentionally separate from Bulltard. Bulltard may generate single-name
candidates, but it is not the basis for the overall market-regime score.

The v0 score uses:

- SPY/QQQ trend and moving-average posture.
- SPY realized volatility and VIX.
- RSP/SPY and IWM/SPY participation.
- HYG/TLT risk appetite.

Replay saved regime snapshots against forward SPY/QQQ returns and drawdowns:

```bash
./bin/marketlab regime outcomes --start 2026-08-01 --end 2026-08-28
```

Backfill market-regime and market-signal snapshots over local price dates:

```bash
./bin/marketlab regime backfill \
  --start 2025-01-02 \
  --end 2026-08-28
```

Replay rare action states or normalized pressure buckets:

```bash
./bin/marketlab regime action-outcomes --start 2025-01-02 --end 2026-05-22 --horizons 20,40,65
./bin/marketlab regime pressure-outcomes --start 2025-01-02 --end 2026-05-22 --horizons 20,40,65
```

## Portfolio Policy

Create a policy snapshot from a saved regime snapshot and any saved Bulltard candidate validation snapshot:

```bash
./bin/marketlab policy snapshot --date 2026-08-28
```

Render the daily human-facing report:

```bash
./bin/marketlab report daily --date 2026-08-28
```

Backfill and replay policy snapshots against the fixed v0 benchmark proxy:

```bash
./bin/marketlab policy backfill --start 2025-01-02 --end 2026-08-28
./bin/marketlab policy outcomes --start 2025-01-02 --end 2026-05-22 --horizons 20,40,65
```

The v0 policy keeps the permanent SPY/QQQ core conceptually unchanged. It only maps the marginal tactical sleeve:

- `maintain`: target roughly neutral tactical beta and make no forced change.
- `protect`: reduce marginal beta, preserve or raise cash, and consider covered calls.
- `redeploy`: add exposure in tranches after washout conditions, including possible 60-90 DTE calls/call spreads or bounded put underwriting.

## Visualization

Generate reproducible charts from saved snapshots and observations:

```bash
./bin/marketlab chart regime --start 2026-08-28 --end 2026-08-28
./bin/marketlab chart opportunity --date 2026-08-28 MRVL
```

By default these write `reports/regime-START-END.html` and
`reports/opportunity-SYMBOL-DATE.html`.

The regime chart shows indexed SPY/QQQ price, regime action-state shading, stretch/washout
pressure, component scores, market-signal family scores, and the latest market-signal table.
The opportunity chart shows the candidate versus SPY/QQQ, Bulltard flow-premium event bars,
20d relative strength, the point-in-time validation snapshot, and a separate forward-outcome
table that stays marked `waiting` until enough future local price rows exist.

## Local Research Store

Refresh the local DuckDB store from saved observations and snapshots:

```bash
./bin/marketlab store refresh
```

Optionally also export each table as Parquet:

```bash
./bin/marketlab store refresh --parquet-root data/warehouse/parquet
```

Inspect or query the store:

```bash
./bin/marketlab store tables
./bin/marketlab store query "select source_date, policy_state, marginal_beta_target from policy_snapshots order by source_date desc limit 10"
```

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
