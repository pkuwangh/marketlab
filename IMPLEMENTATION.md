# MarketLab Implementation Plan

`DESIGN.md` is the architecture source of truth. This file tracks implementation progress as milestone gates, not a queue of tiny utilities.

## Product Direction

MarketLab should become a deterministic market research system that answers three useful questions:

- What is the market regime and marginal risk budget?
- Which large, liquid candidates deserve attention now?
- Did prior signals work against forward returns, drawdowns, and relative returns?

Bulltard is one evidence source for candidate generation. It is not the final decision engine, and duplicating the Bulltard email is not enough. Every milestone below must make the workflow more useful than reading the email directly.

## Operating Rules

- Build milestone-deliverable chunks. A slice is useful only if it moves an exit criterion.
- Prefer simple local files while the schema is still evolving; add heavier storage only when queries demand it.
- Keep commands deterministic and inspectable. No hidden agent reasoning in the core data path.
- Avoid archiving/crawling infrastructure unless it preserves information we actually use.
- Commit implementation slices, but judge progress by milestone exit criteria.

## Current Baseline

Implemented:

- Python package skeleton with `uv`, Typer CLI, Loguru logging, tests, and a local `bin/marketlab` symlink.
- Shared snapshot identity model using `{source, view, date}`.
- Bulltard recap inspection that extracts signed Substack source URLs from saved HTML email.
- Bulltard ranked option trades ingest from the live app route.
- Trades Of Interest parsing from the recap email.
- Ticker-detail fetch and parser for flow history pages.
- Candidate review that prioritizes recap interest over raw ranked rows.
- Daily Bulltard orchestration that captures ranked rows, recap interest, ticker details, candidate prices, validation snapshots, and outcome summaries.
- Daily price observation fetch from Yahoo Finance through `yfinance` into local JSONL.
- Local daily OHLCV CSV import into the same price observation format.
- Bulltard candidate validation snapshots using price, volume, trend, drawdown, and relative-strength features.
- Bulltard outcome replay summaries over saved validation snapshots.
- Market regime snapshots using SPY/QQQ trend, SPY volatility/VIX, RSP/IWM participation, and HYG/TLT risk appetite.
- Market regime outcome replay summaries over saved regime snapshots.

Verified live on `2026-08-26`:

- Ranked option trade rows: 40
- Trades Of Interest tickers: `META`, `XAR`, `SRRK`, `DKS`, `QXO`
- Ticker detail fetches: 5
- Ticker detail failures: 0

Generated observations are written under `data/observations/`. Debug HTML under `data/debug/` is only parser evidence and is not part of the product surface.

## Current Useful Commands

```bash
./bin/marketlab --help
./bin/marketlab bulltard --help
./bin/marketlab bulltard inspect-recap data/inbox/bulltard/recap-2026-08-26.html
./bin/marketlab bulltard daily --date 2026-08-26 data/inbox/bulltard/recap-2026-08-26.html
./bin/marketlab bulltard daily --date 2026-08-26 data/inbox/bulltard/recap-2026-08-26.html --top-ranked 3
./bin/marketlab bulltard candidates --date 2026-08-26
./bin/marketlab bulltard ticker META data/inbox/bulltard/recap-2026-08-26.html --date 2026-08-26
./bin/marketlab bulltard daily --date 2026-08-28 data/inbox/bulltard/recap-2026-08-28.html --fetch-prices --regime --validate --outcomes
./bin/marketlab bulltard refresh-prices --date 2026-08-26 --start 2025-01-01
./bin/marketlab regime snapshot --date 2026-08-28 --fetch-prices
./bin/marketlab regime outcomes --start 2026-08-01 --end 2026-08-28
./bin/marketlab prices fetch-yahoo META,XAR,SRRK,DKS,QXO,SPY,QQQ --start 2025-01-01 --end 2026-08-27
./bin/marketlab prices import-csv META ~/Downloads/META.csv --source manual
./bin/marketlab bulltard validate --date 2026-08-26
./bin/marketlab bulltard daily --date 2026-08-26 data/inbox/bulltard/recap-2026-08-26.html --validate
./bin/marketlab bulltard outcomes --start 2026-08-01 --end 2026-08-26
```

Development checks:

```bash
uv run ruff format
uv run ruff check --fix
uv run pytest -q
```

## Milestones

| Milestone | Status | Goal | Exit Criterion |
| --- | --- | --- | --- |
| 1. Bulltard Candidate Capture | Complete | Capture the daily Bulltard candidate set before signed links expire. | One command produces ranked trades, recap interest, ticker-flow observations, and a candidate table without manual JSONL inspection. Achieved for `2026-08-26`. |
| 2. Candidate Validation & Outcome MVP | Complete | Make the workflow better than the email by adding independent market data and measuring forward results. | One daily command can capture candidates, refresh prices, write validation snapshots, and replay forward outcome summaries. |
| 3. Market Regime MVP | Complete | Size marginal exposure independently from single-name ideas. | Regime snapshots score market context, save point-in-time records, and replay buckets against forward SPY/QQQ returns and drawdowns. |
| 4. Portfolio Policy MVP | Planned | Convert regime plus validated opportunities into a bounded risk posture. | Daily output states marginal beta/cash posture and candidate watch/active context. |
| 5. Visualization & Reporting MVP | Planned | Make regime changes, candidate episodes, and outcome evidence visually inspectable. | CLI-generated charts show price, signals, lifecycle markers, and forward evaluation layers from versioned inputs. |
| 6. Evidence Expansion & Agents | Later | Add fundamentals, estimates, catalysts, richer options data, storage, and bounded agent workers only when they improve measured decisions. | Each added evidence family improves out-of-sample metrics or gets retired. |

## Milestone 1 - Bulltard Candidate Capture

Current status: complete.

Completed scope:

- Bootstrap Bulltard app access from the saved recap email.
- Retrieve and parse ranked option trades.
- Parse Trades Of Interest tickers and reasoning from the recap.
- Retrieve ticker detail pages and parse flow history.
- Produce one daily command that gathers the above into local observations.

Completion evidence:

- Unit and CLI tests cover recap extraction, ranked ingest, Trades Of Interest parsing, ticker-detail ingest, candidate review, and the daily orchestration contract.
- The live `2026-08-26` recap produced ranked observations, Trades Of Interest observations, ticker-flow observations, and a candidate table in one command.

Future changes here should be limited to bugs or sharp edges found while using the workflow. Do not expand this into a general archive system.

## Milestone 2 - Candidate Validation & Outcome MVP

Current status: complete for the v0 research loop.

Goal: for each Bulltard candidate, add enough independent evidence and outcome tracking to tell whether the idea deserves attention and whether this signal family has worked historically.

Implemented v0 scope:

- Fetch Yahoo Finance daily OHLCV history through `yfinance`, or import local daily OHLCV CSVs, for candidate tickers plus `SPY` and `QQQ` into local JSONL.
- Apply basic candidate gates:
  - stock dollar-volume liquidity as the current overall liquidity proxy
  - enough price history for trend and relative-strength features
  - options-liquidity evidence is not part of the visible gate until a real options source is useful
- Compute deterministic price validation features:
  - latest close and dollar volume
  - 5, 20, and 60 trading-day returns
  - distance from 20, 50, and 200-day moving averages
  - drawdown from recent highs
  - relative strength versus `SPY` and `QQQ`
- Persist the point-in-time candidate snapshot before outcomes are known.
- Attach forward 1, 5, 20, 40, 65, and 126 trading-day returns and max drawdowns when enough future data exists.
- Summarize cohorts by Bulltard source bucket, validation status, and whether ticker-flow detail was fetched.
- Print validation summary counts so the daily output is readable without opening JSONL.
- Extend `bulltard daily` with `--fetch-prices`, `--validate`, and `--outcomes` so one command can run the M2 loop.

Current implementation notes:

- `prices fetch-yahoo` writes independent daily OHLCV observations under `data/observations/prices/daily/`.
- `prices fetch` keeps the Stooq path available for keyed/manual-provider use, but it is not the preferred M2 source.
- `prices import-csv` writes local CSV price observations to the same location, which avoids blocking on a live provider during bring-up.
- `bulltard refresh-prices` refreshes Yahoo prices for the captured candidate set plus `SPY` and `QQQ`.
- `bulltard validate` reads Bulltard candidates plus local price observations, writes snapshots under `data/snapshots/bulltard/candidates/`, and prints a validation table.
- `bulltard daily --fetch-prices --validate --outcomes` runs capture, price refresh, validation, and outcome replay in one workflow.
- Daily outcome replay defaults to the earliest saved validation snapshot through the current `--date`, so prior signals are evaluated as history accumulates.
- `bulltard outcomes` reads saved validation snapshots and local price observations to summarize forward results by source/status/detail cohorts.
- Outcome tables report both attempted signal rows and rows with enough forward price data; default tables hide horizons with no available forward data.

Verified live:

- `prices fetch-yahoo META,XAR,SRRK,DKS,QXO,SPY,QQQ --start 2025-01-01 --end 2026-08-27` fetched 414 rows for each symbol.
- Additional Yahoo fetches completed price coverage for the ranked `2026-08-26` candidate table.
- `bulltard validate --date 2026-08-26` produced 12 validation rows with complete price coverage.
- `regime snapshot --date 2026-08-28 --fetch-prices` fetched all seven regime proxies and produced `risk_on` with score `4`.
- `regime outcomes --start 2026-08-28 --end 2026-08-28` replayed the saved regime snapshot; same-day forward horizons correctly showed zero available rows.

Follow-up calibration work:

- Run the v0 path on real saved recaps and real price history.
- Keep watching yfinance/Yahoo reliability; move to a keyed provider only if this path becomes unstable or insufficient.
- Calibrate the basic liquidity and trend thresholds using outcome summaries instead of intuition.
- Add repeated-flow cohorts once we have multiple days of ticker-flow observations.
- Add a real options-liquidity source only if it improves outcome analysis; until then, stock dollar volume is the liquidity gate.

Non-goals for this milestone:

- No portfolio construction.
- No automated trade recommendations.
- No broad database abstraction unless JSONL stops being workable for these replay queries.
- No LLM interpretation in the core scoring path.

First useful M2 outputs:

```bash
./bin/marketlab bulltard daily --date 2026-08-28 data/inbox/bulltard/recap-2026-08-28.html --fetch-prices --validate --outcomes
./bin/marketlab bulltard outcomes --start 2026-08-01 --end 2026-08-28
```

The command names can change later, but the deliverable cannot: candidate validation plus measured outcomes.

## Milestone 3 - Market Regime MVP

Current status: complete for the v0 research loop.

Goal: answer whether the current market supports more exposure, less exposure, or selectivity only.

Implemented v0 scope:

- Refresh Yahoo Finance daily OHLCV history for regime proxies:
  - `SPY`, `QQQ`, `IWM`, `RSP`, `HYG`, `TLT`, `^VIX`
- Build a basic deterministic regime score from:
  - SPY/QQQ trend and moving-average posture
  - SPY realized volatility and VIX
  - RSP/SPY and IWM/SPY participation
  - HYG/TLT risk appetite
- Store one market regime snapshot per date under `data/snapshots/regime/market/`.
- Label the market as `risk_on`, `neutral`, or `risk_off` with a simple confidence level and component reasons.
- Evaluate regime buckets against forward SPY/QQQ returns and drawdowns.
- Integrate regime snapshot and regime outcome replay into `bulltard daily --regime`.

Current implementation notes:

- `regime snapshot --fetch-prices` refreshes the regime proxy price set and writes a snapshot.
- `regime outcomes` replays saved regime snapshots against forward SPY/QQQ behavior.
- `bulltard daily --fetch-prices --regime --validate --outcomes` now runs the combined candidate plus regime loop.
- Regime outcome tables report available forward rows separately and omit empty horizons from the default display.

First useful M3 outputs:

```bash
./bin/marketlab regime snapshot --date 2026-08-28 --fetch-prices
./bin/marketlab regime outcomes --start 2026-08-01 --end 2026-08-28
./bin/marketlab bulltard daily --date 2026-08-28 data/inbox/bulltard/recap-2026-08-28.html --fetch-prices --regime --validate --outcomes
```

Follow-up calibration work:

- Run the v0 regime score across enough saved days to see whether buckets separate returns or simply say "no edge."
- Tune thresholds only from replay evidence, not from today’s read.
- Add breadth/volatility/credit proxies only when they improve measured separation.
- Use Bulltard broad-market commentary later as an overlay, not as the first implementation.

Non-goals for this milestone:

- No portfolio sizing policy.
- No trade automation.
- No optimization loop over thresholds.

## Milestone 4 - Portfolio Policy MVP

Goal: translate research outputs into a daily risk posture.

Scope:

- Define exposure bands from regime and opportunity quality.
- Distinguish watch candidates from active candidates.
- Produce a concise daily report that includes:
  - market regime
  - marginal risk posture
  - validated Bulltard candidates
  - recent decision changes
  - outcome feedback from prior signals

## Milestone 5 - Visualization & Reporting MVP

Goal: make the research loop easy to inspect without turning the project into a dashboard-first build.

Scope:

- Generate the first regime chart from reproducible CLI inputs.
- Generate the first single-name opportunity chart with Bulltard event markers.
- Keep notebooks exploratory; make important charts reproducible from commands.
- Include forward evaluation layers only when clearly separated from point-in-time inputs.

## Milestone 6 - Evidence Expansion & Agents

Goal: add new evidence only when it answers a measured question.

Candidates:

- Fundamentals and estimates.
- Options liquidity and spread quality.
- Event and catalyst extraction.
- Sector and factor context.
- Richer storage such as DuckDB or Parquet.
- Worker orchestration for slower collectors.
- Bounded agent workers for qualitative extraction or contradiction review.

Rule: each expansion needs an expected use in validation, decision journaling, outcomes, or regime. Otherwise it waits.

## Recent Commits

- `68c38e8` - Add regime to Bulltard daily workflow
- `dc873b7` - Replay market regime outcomes
- `30a628c` - Add market regime snapshots
- `51fd905` - Replay saved outcomes from daily workflow
- `186fe71` - Run daily validation with price refresh
- `4cedf90` - Refresh candidate prices automatically
- `0d39f65` - Fetch daily prices with yfinance
- `ccdf91a` - Document price CSV import path
- `b6c23f6` - Import local daily price CSVs
- `c449f60` - Document candidate validation workflow
- `8af62a0` - Add Bulltard candidate validation workflow
- `03b9924` - Mark Bulltard capture milestone complete
- `5f8292d` - Refresh implementation milestones
- `e015a76` - Run Bulltard daily candidate workflow
- `b12f96c` - Handle missing ticker flow premiums
- `69ceec8` - Prioritize recap interest in candidate review
- `2660744` - Parse Bulltard trades of interest
- `7bd3922` - Review Bulltard candidates from observations
- `41db2e5` - Parse Bulltard ticker flow history
- `8900d8c` - Ingest Bulltard ranked observations
- `227ba8c` - Prepare Bulltard ingest plan
- `0d4f373` - Inspect Bulltard recap links
- `11030cb` - Scaffold marketlab CLI
