# MarketLab Implementation Plan

`DESIGN.md` is the architecture source of truth. This file tracks implementation progress as milestone gates, not a queue of tiny utilities.

## Product Direction

MarketLab has two coordinated research engines:

- **Market regime engine:** detect rare stretched/de-risk and bloodbath/re-risk zones so the portfolio can adjust marginal SPY/QQQ beta, dry powder, and options overlays while maintaining the core.
- **Single-name opportunity engine:** decide which large, liquid candidates deserve multi-month tactical research attention.

The market regime engine is now the primary implementation focus. Bulltard is one evidence source for the single-name engine; it is not the basis for the overall market regime. Every milestone below must improve market exposure decisions, especially stretch/bottoming posture changes, single-name opportunity selection, or measured forward outcome feedback.

## Operating Rules

- Build milestone-deliverable chunks. A slice is useful only if it moves an exit criterion.
- Prefer simple local files while the schema is still evolving; add heavier storage only when queries demand it.
- Keep commands deterministic and inspectable. No hidden agent reasoning in the core data path.
- Avoid archiving/crawling infrastructure unless it preserves information we actually use.
- Treat generic risk-on/risk-off as an intermediate label; the valuable output is whether to scale down/protect or scale up/redeploy within bounded policy limits.
- Bias the portfolio output toward `no_change`; alerts should be rare and focused on top-like stretch or bottom-like washout conditions.
- Keep the engines separate but connected: regime controls risk budget and posture; Bulltard/opportunity signals help choose where tactical risk goes and can be evaluated by active regime state.
- Commit implementation slices, but judge progress by milestone exit criteria.

## Current Baseline

Implemented shared foundation:

- Python package skeleton with `uv`, Typer CLI, Loguru logging, tests, and a local `bin/marketlab` symlink.
- Shared snapshot identity model using `{source, view, date}`.
- Daily price observation fetch from Yahoo Finance through `yfinance` into local JSONL.
- Local daily OHLCV CSV import into the same price observation format.

Implemented single-name / Bulltard foundation:

- Bulltard recap inspection that extracts signed Substack source URLs from saved HTML email.
- Bulltard ranked option trades ingest from the live app route.
- Trades Of Interest parsing from the recap email.
- Ticker-detail fetch and parser for flow history pages.
- Candidate review that prioritizes recap interest over raw ranked rows.
- Daily Bulltard orchestration that captures ranked rows, recap interest, ticker details, candidate prices, validation snapshots, and outcome summaries.
- Bulltard candidate validation snapshots using price, volume, trend, drawdown, and relative-strength features.
- Bulltard outcome replay summaries over saved validation snapshots.

Implemented market-regime foundation:

- Market regime snapshots using SPY/QQQ trend, SPY volatility/VIX, RSP/IWM participation, and HYG/TLT risk appetite.
- Market regime outcome replay summaries over saved regime snapshots.

Implemented market-signal expansion:

- Dedicated market-signal snapshots under `data/snapshots/market/signals/`.
- Scalar market-series observations under `data/observations/market/series/`.
- FRED fetch support for high-yield credit spreads, NFCI financial conditions, and 10Y/2Y Treasury yields.
- `regime snapshot` now prints family-level signal rows beside the component table.
- `^VVIX` is tracked as a volatility / vol-of-vol signal when available.
- FRED-backed `credit_spread`, `financial_conditions`, and `yield_curve` rows are tracked when available.
- Missing independent signal sources are explicit and reduce headline confidence.
- `regime signal-outcomes` replays saved market-signal rows against forward SPY/QQQ returns and drawdowns.

Implemented regime calibration/action-state foundation:

- `regime snapshot` now derives `no_change`, `scale_down_protect`, or `scale_up_redeploy`.
- Daily snapshots include stretch score, washout score, action confidence, and action reason.
- `regime action-outcomes` replays rare action states against forward SPY/QQQ returns and drawdowns.
- Action-state frequency is reported so the model can be judged on whether it stays quiet most days.
- Daily snapshots include normalized stretch/washout pressure scores from rolling point-in-time percentiles.
- `regime pressure-outcomes` replays top pressure buckets against forward SPY/QQQ returns and drawdowns.
- `regime backfill` computes daily regime and market-signal snapshots over historical SPY trading dates.

Not yet implemented:

- VIX term structure, fear/greed or sentiment/positioning observations.
- Stronger breadth, sentiment/positioning, VIX term structure, and richer credit/liquidity calibration.
- Long-history threshold calibration and portfolio policy.

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
./bin/marketlab bulltard daily --date 2026-08-28 data/inbox/bulltard/recap-2026-08-28.html --fetch-prices --validate --outcomes
./bin/marketlab bulltard refresh-prices --date 2026-08-26 --start 2025-01-01
./bin/marketlab regime snapshot --date 2026-08-28 --fetch-prices
./bin/marketlab regime backfill --start 2020-01-01 --end 2026-08-28 --fetch-prices --fetch-market-series
./bin/marketlab market-series fetch-fred --start 2026-08-20 --end 2026-08-28
./bin/marketlab regime snapshot --date 2026-08-28 --fetch-prices --fetch-market-series --market-series-start 2026-08-20 --market-series-end 2026-08-28
./bin/marketlab regime outcomes --start 2026-08-01 --end 2026-08-28
./bin/marketlab regime signal-outcomes --start 2026-07-31 --end 2026-07-31 --horizons 20
./bin/marketlab regime action-outcomes --start 2026-08-01 --end 2026-08-28 --horizons 20,40,65
./bin/marketlab regime pressure-outcomes --start 2026-08-01 --end 2026-08-28 --horizons 20,40,65
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

| Milestone | Status | Engine | Goal | Exit Criterion |
| --- | --- | --- | --- | --- |
| 1. Bulltard Candidate Capture | Complete | Single-name | Capture the daily Bulltard candidate set before signed links expire. | One command produces ranked trades, recap interest, ticker-flow observations, and a candidate table without manual JSONL inspection. Achieved for `2026-08-26`. |
| 2. Candidate Validation & Outcome MVP | Complete | Single-name | Make the candidate workflow better than the email by adding independent price/liquidity context and measuring forward results. | One daily command can capture candidates, refresh prices, write validation snapshots, and replay forward outcome summaries. |
| 3. Market Regime Foundation | Complete | Market regime | Create a first deterministic market context from available OHLCV proxies. | Regime snapshots score SPY/QQQ trend, realized volatility/VIX, breadth proxy, credit proxy, and replay buckets against forward SPY/QQQ returns/drawdowns. |
| 4. Market Signal Expansion | Complete | Market regime | Add independent volatility-structure, sentiment/positioning, stronger breadth, and liquidity/credit signal families. | `regime snapshot` shows family-level market signals, missing-source status, contradictions, and replayable evidence beyond simple trend. |
| 5. Regime Calibration & Backtest | Complete v2 backfill tooling | Market regime | Decide whether the expanded regime families identify rare stretched/de-risk and bloodbath/re-risk zones with useful forward risk/reward separation. | Backfill, action states, normalized pressure scores, and replay tables exist; long-history calibration still needed before policy. |
| 6. Portfolio Policy MVP | Next | Portfolio | Convert calibrated regime plus validated opportunities into bounded beta/cash/overlay posture. | Daily output states whether to maintain, scale down/protect, or scale up/redeploy, with candidate watch/active context, engine-interaction logic, and fixed-benchmark evaluation. |
| 7. Visualization & Reporting MVP | Planned | Shared | Make regime changes, candidate episodes, and outcome evidence visually inspectable. | CLI-generated charts show price, signals, lifecycle markers, and forward evaluation layers from versioned inputs. |
| 8. Evidence Expansion & Agents | Later | Shared | Add fundamentals, estimates, catalysts, richer options data, storage, and bounded agent workers only when they improve measured decisions. | Each added evidence family improves out-of-sample metrics or gets retired. |

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

## Milestone 3 - Market Regime Foundation

Current status: complete for the v0 research loop.

Goal: establish a deterministic, point-in-time market-regime baseline before adding richer independent market signals.

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
- Keep the market-regime workflow on the independent `regime` command surface.

Current implementation notes:

- `regime snapshot --fetch-prices` refreshes the regime proxy price set and writes a snapshot.
- `regime outcomes` replays saved regime snapshots against forward SPY/QQQ behavior.
- `bulltard daily` no longer accepts `--regime`; combined daily orchestration should be top-level later, not nested under Bulltard.
- Regime outcome tables report available forward rows separately and omit empty horizons from the default display.

Verified live:

- `regime snapshot --date 2026-08-28 --fetch-prices` fetched all seven regime proxies and produced `risk_on` with score `4`.
- `regime outcomes --start 2026-08-28 --end 2026-08-28` replayed the saved regime snapshot; same-day forward horizons correctly showed zero available rows.
- `bulltard daily --date 2026-08-28 data/inbox/bulltard/recap-2026-08-28.html --fetch-prices --validate --outcomes` runs the single-name candidate workflow without regime side effects.

First useful M3 outputs:

```bash
./bin/marketlab regime snapshot --date 2026-08-28 --fetch-prices
./bin/marketlab regime outcomes --start 2026-08-01 --end 2026-08-28
```

Known limitations:

- This is a useful foundation, not a credible final market model.
- Volatility is currently represented by VIX level plus SPY realized volatility, not VIX term structure or vol-of-vol.
- Breadth and credit/liquidity are ETF proxies, not full market breadth or financing-condition datasets.
- Sentiment/positioning is not implemented.
- The current composite has not been calibrated across enough history to support portfolio policy.

Non-goals for this milestone:

- No portfolio sizing policy.
- No trade automation.
- No optimization loop over thresholds.

## Milestone 4 - Market Signal Expansion

Current status: complete v0.

Goal: make the market-regime engine richer than simple SPY/QQQ trend by adding independent market signal families that directly affect marginal exposure decisions.

Target v0 scope:

- Add a market-signal snapshot layer under `data/snapshots/market/signals/` or an equivalent local path.
- Represent signal rows with date, family, name, value, status, source, availability date/time, and feature version.
- Add volatility-structure observations:
  - VIX level and change
  - VIX term structure where data is practical
  - realized-vs-implied volatility
  - VVIX or a vol-of-vol proxy if source access is reliable
- Add sentiment/positioning observations:
  - fear/greed-style risk appetite, initially via manual import if needed
  - put/call or positioning proxies later when source access is clear
- Strengthen breadth beyond ETF proxies:
  - percentage above moving averages
  - new highs/lows
  - advance/decline or equivalent breadth series if practical
- Improve credit/liquidity evidence only after the above exists.
- Update `regime snapshot` to consume these market-signal snapshots and display family-level evidence, missing-source status, and contradictions.

Exit criterion:

- A regime snapshot shows independent market signal families, not just index price features.
- Missing signal families are explicit and reduce confidence rather than silently disappearing.
- Each family can be replayed against forward SPY/QQQ returns and drawdowns.

First implementation slice:

- Create the signal-row model, writer/loader, and compact table formatter.
- Wire current regime component evidence into this market-signal snapshot format without changing the composite score yet.
- Add one new signal family after the snapshot contract exists, starting with volatility structure if a stable source is available, otherwise a manual import path.

Non-goals for this milestone:

- No portfolio policy yet.
- No source shopping rabbit hole before the signal snapshot format exists.
- No large data warehouse migration.
- No Bulltard-driven market model.

Completed scope:

- Created the market-signal row model, writer/loader, and compact table formatter.
- `regime snapshot` writes signal JSONL snapshots and displays family/name/status/score/value/source evidence.
- Current deterministic regime components are mirrored into signal rows for replayability.
- Added `^VVIX` as the first independent volatility / vol-of-vol signal where Yahoo data is present.
- Added `market-series fetch-fred` for FRED scalar observations.
- Added FRED-backed credit spread, financial-conditions, and yield-curve signal rows.
- `regime snapshot --fetch-market-series` refreshes the default FRED source set in the same command.
- Missing `^VVIX` is shown as `volatility / vol_of_vol / missing` and lowers headline confidence one notch.
- `regime snapshot` reports positive/negative market-signal contradictions when both sides are present.
- Added `regime signal-outcomes` to summarize forward SPY/QQQ returns and drawdowns by signal family/name/status.

Completion evidence:

- A no-write `2026-08-28` snapshot produced five market-signal rows and showed missing `^VVIX` explicitly.
- A live FRED smoke on `2026-08-29` fetched `BAMLH0A0HYM2`, `NFCI`, `DGS10`, and `DGS2` for `2026-08-20` through `2026-08-28`.
- A no-write `2026-08-28` snapshot using those FRED observations produced eight market-signal rows, including credit, financial conditions, and yield curve.
- A temporary `2026-07-31` signal snapshot replayed through `regime signal-outcomes --horizons 20` with family and signal-status buckets.
- Unit and CLI tests cover market-signal snapshots, VVIX signal rows, missing-source confidence handling, and signal-outcome replay.

Deferred expansion:

- VIX term structure is deferred until the Yahoo `^VIX3M` / `^VIX6M` behavior is reliable enough for daily use.
- Fear/greed-style sentiment should start as a manual import or stable source-specific importer.
- Stronger breadth should be added only when we have a practical source for percentage-above-average or new-high/new-low observations.
- Credit/liquidity now has a first FRED source; further work should calibrate thresholds and add richer series only if replay evidence improves.

## Milestone 5 - Regime Calibration & Backtest

Current status: complete for v2 backfill tooling; not yet trusted as portfolio policy.

Goal: decide whether the expanded regime evidence actually improves rare market exposure decisions: scaling down near top-like stretch and scaling up after bottom-like washout.

Scope:

- Replay each market-signal family against forward SPY and QQQ returns and drawdowns.
- Define explicit stretched/de-risk and bloodbath/re-risk state candidates from the existing signal rows.
- Define the baseline `no_change` state so most days do not imply a portfolio move.
- Measure family-level value before changing the composite:
  - forward return spread by signal bucket
  - max drawdown separation
  - hit rate
  - transition behavior
  - sample counts and missingness
- Evaluate disagreement states such as bullish trend with deteriorating volatility structure.
- Evaluate whether stretched states precede poor forward reward/risk or larger adverse excursions.
- Evaluate whether washout states improve 40-65 trading-day forward reward/risk after broad selloffs.
- Evaluate whether action states are rare enough to be operationally useful instead of becoming daily noise.
- Freeze simple threshold versions before comparing them.
- Retire signals that do not improve separation, calibration, contradiction handling, or interpretability.

Exit criterion:

- We know which regime families are pulling their weight.
- We know whether stretch/de-risk and bloodbath/re-risk alerts deserve explicit policy weight.
- We know how often the engine would say `no_change`, `scale_down_protect`, and `scale_up_redeploy`.
- The composite score has documented thresholds and a frozen version.
- Portfolio policy can consume regime output without pretending the market model is more mature than it is.

Implemented v0 scope:

- Added a deterministic rare-action classifier with three states:
  - `no_change`
  - `scale_down_protect`
  - `scale_up_redeploy`
- Added transparent stretch and washout scores to `regime snapshot`.
- Made `no_change` the default unless multiple pieces of evidence cross a rare-action threshold.
- Added a funding-stress guard so a severe credit/liquidity break blocks aggressive re-risk even when the market is washed out.
- Added `regime action-outcomes` to report:
  - action-state frequency
  - forward SPY/QQQ returns by action state
  - forward SPY/QQQ drawdowns by action state

Implemented pressure-scoring scope:

- Added `regime_pressure_v0`, a normalized scoring layer that projects heterogeneous signal values into a common `0.00` to `1.00` pressure space.
- Each feature is ranked against its own trailing point-in-time sample, then mapped into stretch pressure, washout pressure, or both depending on the feature's interpretation.
- Aggregation averages feature scores inside each family first, then averages family scores so one family with many correlated indicators does not dominate.
- `regime snapshot` prints pressure feature rows with raw value, percentile, stretch contribution, washout contribution, sample count, and basis.
- `regime pressure-outcomes` buckets saved snapshots by point-in-time pressure percentiles such as `stretch:top_10`, `stretch:top_5`, `washout:top_10`, and `washout:top_5`.
- The hard-threshold action classifier remains a baseline comparator, not the final portfolio policy.

Implemented historical backfill scope:

- Added `regime backfill` to compute one official snapshot per SPY observation date in a requested date range.
- The command can refresh Yahoo regime proxy prices and FRED market series once before computing the historical run.
- Backfill uses a warmup window before `--start` so moving averages, returns, and pressure percentiles have prior context.
- Backfill writes both regime snapshots and market-signal snapshots, which immediately feed `regime action-outcomes`, `regime signal-outcomes`, and `regime pressure-outcomes`.

Current v0 classifier:

- `scale_down_protect` requires at least three stretch signals such as strong SPY rally, extended QQQ momentum, extension above 50d trend, complacent volatility, weak participation in a risk-on tape, or credit/liquidity deterioration in a risk-on tape.
- `scale_up_redeploy` requires at least three washout signals such as major index selloff, price below intermediate trend, elevated volatility stress, visible trend damage, broad participation washout, or washout with credit/liquidity not broken.
- `no_change` is emitted when neither rare-action threshold is crossed or when stretch and washout evidence conflict.

First useful M5 outputs:

```bash
./bin/marketlab regime snapshot --date 2026-08-28 --fetch-prices --fetch-market-series --market-series-start 2026-08-20 --market-series-end 2026-08-28
./bin/marketlab regime backfill --start 2020-01-01 --end 2026-08-28 --fetch-prices --fetch-market-series
./bin/marketlab regime action-outcomes --start 2026-08-01 --end 2026-08-28 --horizons 20,40,65
./bin/marketlab regime pressure-outcomes --start 2026-08-01 --end 2026-08-28 --horizons 20,40,65
```

Known limitations:

- The current action thresholds are candidate rules, not calibrated portfolio policy.
- Existing local snapshots cover only a small recent sample unless a longer historical run is generated.
- This milestone measures market pressure/action states only; it does not yet choose exact cash percentages, covered-call overwrite levels, or 60-90 DTE option budgets.
- Pressure bucket replay needs longer saved history before top-decile rows are statistically meaningful.

## Milestone 6 - Portfolio Policy MVP

Goal: translate research outputs into a daily risk posture.

Scope:

- Define exposure bands from regime and opportunity quality.
- Make `no_change` the default posture unless calibrated evidence crosses a meaningful action threshold.
- Define bounded actions for stretched/de-risk conditions:
  - keep core invested
  - raise or preserve cash
  - scale down tactical beta
  - sell covered calls against part of existing exposure where appropriate
- Define bounded actions for bloodbath/re-risk conditions:
  - deploy cash in tranches
  - consider 60-90 DTE calls or call spreads
  - consider cash-secured puts or defined-risk put spreads only inside a fixed risk budget
- Distinguish watch candidates from active candidates.
- Let market regime modify single-name candidate sizing and instrument aggressiveness without changing the candidate's own quality score.
- Evaluate Bulltard/opportunity outcomes by the market-regime state active at discovery and validation.
- Produce a concise daily report that includes:
  - market regime
  - stretch/de-risk and washout/re-risk state
  - daily action state
  - marginal risk posture
  - validated Bulltard candidates
  - recent decision changes
  - outcome feedback from prior signals

Non-goals for this milestone:

- No automated trading.
- No policy rules until M5 has at least a basic calibration result.
- No single-name sizing that ignores aggregate market regime.
- No Bulltard-driven override of the independent market-regime engine.

## Milestone 7 - Visualization & Reporting MVP

Goal: make the research loop easy to inspect without turning the project into a dashboard-first build.

Scope:

- Generate the first regime chart from reproducible CLI inputs.
- Generate the first single-name opportunity chart with Bulltard event markers.
- Keep notebooks exploratory; make important charts reproducible from commands.
- Include forward evaluation layers only when clearly separated from point-in-time inputs.

## Milestone 8 - Evidence Expansion & Agents

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

- `a066a55` - Add VVIX market signal
- `70b88ec` - Add market signal snapshots
- `4a8146e` - Handle partial Yahoo daily bars
- `155c1b5` - Clean up outcome summary tables
- `20c952f` - Mark market regime milestone complete
- `68c38e8` - Add regime to Bulltard daily workflow
- `dc873b7` - Replay market regime outcomes
- `30a628c` - Add market regime snapshots
- `1754ccb` - Use stock volume as liquidity gate
- `5ed773c` - Mark candidate validation milestone complete
- `51fd905` - Replay saved outcomes from daily workflow
- `186fe71` - Run daily validation with price refresh
- `4cedf90` - Refresh candidate prices automatically
- `3466745` - Document yfinance price source
