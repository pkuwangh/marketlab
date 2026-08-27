# MarketLab Implementation Plan

`DESIGN.md` is the architecture source of truth. This file tracks implementation progress as milestone gates, not a queue of tiny utilities.

## Product Direction

MarketLab should become a deterministic market research system that answers three useful questions:

- What is the market regime and marginal risk budget?
- Which large, options-liquid candidates deserve attention now?
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
- Daily Bulltard orchestration that captures ranked rows, recap interest, ticker details, and a candidate table.

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
| 2. Candidate Validation & Outcome MVP | Next | Make the workflow better than the email by adding independent market data and measuring forward results. | We can replay candidate dates, apply basic universe/liquidity/price gates, attach forward returns/drawdowns, and summarize which Bulltard-derived cohorts have edge. |
| 3. Market Regime MVP | Planned | Size marginal exposure independently from single-name ideas. | SPY/QQQ regime buckets show forward return and drawdown separation, or clearly show no edge. |
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

This is the next major milestone.

Goal: for each Bulltard candidate, add enough independent evidence and outcome tracking to tell whether the idea deserves attention and whether this signal family has worked historically.

Initial scope:

- Ingest daily OHLCV history for candidate tickers plus `SPY` and `QQQ`.
- Add basic candidate gates:
  - large/liquid underlying
  - enough price history for trend and relative-strength features
  - options-liquidity status remains `unknown` until a real options source is wired in
- Compute deterministic validation features:
  - latest close and dollar volume
  - 5, 20, and 60 trading-day returns
  - distance from 20, 50, and 200-day moving averages
  - drawdown from recent highs
  - relative strength versus `SPY` and `QQQ`
  - basic volume/trend flags
- Persist the point-in-time candidate snapshot before outcomes are known.
- Attach forward 20, 40, 65, and 126 trading-day returns and max drawdowns when enough future data exists.
- Compare cohorts such as Trades Of Interest versus ranked-only, repeated flow versus one-off flow, and price-confirmed versus price-unconfirmed candidates.
- Extend `bulltard daily` or add a candidate command so the final table shows validation status, not just Bulltard evidence.

Non-goals for this milestone:

- No portfolio construction.
- No automated trade recommendations.
- No broad database abstraction unless JSONL stops being workable for these replay queries.
- No LLM interpretation in the core scoring path.

First "real thing" output:

```bash
./bin/marketlab bulltard daily --date 2026-08-26 data/inbox/bulltard/recap-2026-08-26.html --validate
./bin/marketlab bulltard outcomes --start 2026-08-01 --end 2026-08-26
```

The exact command names can change during implementation, but the deliverable cannot: candidate validation plus measured outcomes.

## Milestone 3 - Market Regime MVP

Goal: answer whether the current market supports more exposure, less exposure, or selectivity only.

Scope:

- Build a basic regime score from major index trend, volatility, and breadth proxies.
- Store regime observations by date.
- Evaluate regime buckets against forward market returns and drawdowns.
- Use Bulltard broad-market commentary later as an overlay, not as the first implementation.

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
