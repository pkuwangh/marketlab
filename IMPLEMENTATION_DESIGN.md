# MarketLab Implementation Design

**Status:** local-first pre-debut implementation, current as of September 2026.

This document describes how the current tool runs. It should stay factual and concise. For model
theory and research proposals, see [ALGORITHM_DESIGN.md](./ALGORITHM_DESIGN.md).

## Application Shape

MarketLab is a conventional Python research application with a Typer CLI. Deterministic Python
code owns data acquisition, feature calculation, snapshot writing, outcome replay, policy mapping,
chart/report rendering, and DuckDB refresh. Agent-style work is limited to future bounded
extraction or analysis tasks; the database and JSON/JSONL files are the project memory.

Current source modules:

| Module | Responsibility |
| --- | --- |
| `marketlab.cli` | Command surface and output wiring. |
| `marketlab.prices` | Yahoo, CBOE, Stooq, and CSV daily price observations. |
| `marketlab.market_series` | FRED credit/liquidity/rates observations. |
| `marketlab.market_signals` | Calculated market-signal snapshots. |
| `marketlab.regime` | Market-regime snapshots, pressure/action evidence, backfills, outcomes, reports. |
| `marketlab.regime_export` | Refreshable XLSX exports for regime snapshot research and manual charting. |
| `marketlab.policy` | Portfolio-policy snapshots, backfills, outcomes, daily policy report. |
| `marketlab.bulltard.*` | Recap parsing, app-view ingestion, candidate review, validation, outcomes. |
| `marketlab.gmail` | Read-only Gmail OAuth and recap acquisition. |
| `marketlab.charts` | Regime and opportunity chart rendering. |
| `marketlab.store` | Rebuildable DuckDB query store. |
| `marketlab.snapshots` | Shared snapshot path/version helpers. |

## Command Surface

Top-level commands are grouped by user intent:

| Command group | Role |
| --- | --- |
| `marketlab daily` | Routine market + Bulltard daily workflow. |
| `marketlab regime ...` | Market-regime pillar: snapshots, backfills, outcomes, reports, charts, policy. |
| `marketlab bulltard ...` | Bulltard capture, parsing, candidate validation, outcomes, charts. |
| `marketlab data ...` | Source data download/import and local store utilities. |
| `marketlab tools ...` | External integrations and one-off helpers, currently Gmail. |

Important CLI principles:

- no-argument command groups show help;
- normal daily use should go through `marketlab daily`;
- `data prices` and `data market-series` are source-download utilities, not normal research
  commands;
- `tools gmail` is an integration setup/debug surface, not a pillar.

## Routine Workflow

The routine daily path is:

```text
refresh market sources
    -> write market-signal snapshots
    -> write regime snapshot
    -> derive portfolio-policy snapshot/report
    -> fetch Bulltard recap from Gmail when authorized
    -> ingest/validate Bulltard candidates
    -> refresh DuckDB query store
```

Focused workflows can run only one pillar, for example `regime snapshot`, `regime outcomes`,
`bulltard daily`, or `bulltard outcomes`.

## Data Layout

JSON/JSONL files are the durable local source of truth. DuckDB is rebuildable query state.

```text
data/
  inbox/
    bulltard/                         # Gmail-cached recaps
  observations/
    prices/daily/                     # source daily OHLCV/index rows
    market/series/                    # source FRED rows
    bulltard/                         # parsed subscription observations
  snapshots/
    market/signals/YYYY-MM-DD/eod/v0/
    regime/market/YYYY-MM-DD/eod/v0/
    portfolio/policy/YYYY-MM-DD/eod/v0/
    bulltard/candidates/YYYY-MM-DD/eod/v0/
reports/
marketlab.duckdb
secrets/
```

Generated data, reports, DuckDB files, debug payloads, inbox files, and credentials are gitignored.

## Observation and Snapshot Semantics

Use these terms consistently:

| Term | Meaning |
| --- | --- |
| Observation | Source data row collected from Yahoo, CBOE, FRED, Gmail, Bulltard, CSV, etc. |
| Snapshot | Calculated MarketLab output for a source date, signal time, and version. |
| `source_date` | Date represented by the calculation. |
| `signal_time` | Timing label, currently `eod` for supported official workflows. |
| `snapshot_version` | Output-contract version such as `v0`. |
| `feature_version` | Feature definition version used inside a snapshot. |
| `model_version` | Model or rule version used inside a snapshot. |

Source observations are the reproducibility boundary. Calculated snapshots are model outputs that
can be regenerated. During pre-debut iteration, same-version `v0` snapshots may be overwritten by
their producing workflow. After a workflow becomes a live research record, meaningful behavior
changes should bump the relevant version rather than silently rewriting history.

## Time Semantics

The current official mode is end-of-day daily data. `prior_close` and intraday preview modes are
not supported for official records until timestamp-aware observations exist.

Each source row should carry:

- observed date;
- availability date where known;
- retrieval metadata where useful;
- source symbol or series id;
- enough provenance to replay or explain the calculation.

Market calculations consume local observations. They should not silently fetch "latest" values
from external APIs during feature calculation.

## Source Handling

Current source behavior:

| Source | Current handling |
| --- | --- |
| Yahoo | Daily ETF/equity OHLCV cache with adjusted close used for returns when present. |
| CBOE | Historical CSVs for volatility indexes such as VIX, VVIX, VIX9D, VIX3M. |
| EODData/Stooq/manual CSV | Breadth or fallback price paths where configured. |
| FRED | Current-history credit/liquidity/rates series. Revision replacements are recorded locally. |
| Gmail | Read-only OAuth fetches Bulltard recaps into `data/inbox/bulltard/`. |
| Bulltard app | Uses the original signed recap link to retrieve targeted server-rendered views. |

FRED rows are current-vintage local history. In economic-data terminology, a vintage is the data as
it existed on a specific release date. MarketLab does not fetch true historical vintages yet, so
macro backtests using revised FRED rows must keep that limitation visible.

## Bulltard Access Boundary

The Bulltard ingester is query-shaped, not crawler-shaped:

- acquire the daily recap from Gmail or a saved file;
- extract the original signed Substack/app link;
- create one short-lived HTTP session;
- request one named app view or ticker page needed for the research task;
- parse table rows/signals into structured observations;
- redact capability URLs in normal logs and output.

The tool should not require a persistent Chrome profile, copied browser cookies, token generation,
or mirroring the full Bulltard application.

## Market-Regime Outputs

`regime snapshot` writes calculated market-signal and regime snapshots. By default it prints the
key-signals table. `--detail` adds:

- action evidence;
- market signals;
- pressure features.

`regime report` is a recent multi-day trend view over saved snapshots. `regime outcomes` replays
saved snapshots against forward SPY/QQQ returns and drawdowns. Its default grouping is action;
explicit `--by` options cover regime, pressure, signal, and policy. `regime export` writes saved
regime snapshots into stable `workbooks/regime.xlsx` and `workbooks/regime.csv` files so Excel
charts can be maintained manually and refreshed in place.

## Portfolio Policy Outputs

The v0 policy maps market-regime action states into provisional marginal posture:

- `maintain`;
- `protect`;
- `redeploy`.

It does not replace real portfolio accounting and does not execute trades. It is a research proxy
for outcome replay and report generation.

## Bulltard Outputs

Bulltard workflows produce:

- parsed ranked option-trade observations;
- parsed Trades Of Interest rows;
- selected ticker-flow observations;
- candidate review rows;
- validation snapshots with independent price/liquidity/relative-strength checks;
- outcome replays grouped by source, validation status, ranked side, ticker-flow subtype, and
  market regime where available.

Validation states are research triage labels:

- `confirm`: price/liquidity/relative strength are aligned enough for research;
- `watch`: evidence is incomplete or mixed;
- `avoid`: missing data, thin trading, or weak independent evidence fails basic checks.

## DuckDB Store

`marketlab data store refresh` rebuilds `marketlab.duckdb` from local observations and snapshots.
The DuckDB file is not canonical. It is a query index over JSON/JSONL source files and can be
deleted and rebuilt.

Optional Parquet export exists for local interchange:

```bash
marketlab data store refresh --parquet-root data/warehouse/parquet
```

## Testing and Code Change Expectations

- Keep implementation changes scoped to the active research question.
- Prefer existing local helper APIs and dataclasses over new abstractions.
- Add tests when behavior, output contracts, path semantics, or replay math changes.
- For source parsing, preserve raw enough debug context to diagnose parser failures without
  committing temporary capability URLs or credentials.
- Keep CLI output stable and human-readable because it is part of the research loop.

## Later Infrastructure Triggers

Do not add hosted storage, schedulers, or service infrastructure until local workflows repeatedly
show they are worth automating. Migration to S3/GCS, hosted compute, or cron should wait until:

- daily source acquisition is stable;
- snapshot/version semantics are trusted;
- outcome reports are useful enough to review regularly;
- secrets and capability URLs are safely bounded;
- the workflow can be rerun from clean local data.
