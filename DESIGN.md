# Market Regime & Large-Cap Opportunity Research System

**High-Level Design - Version 0.6**
**Status:** Core-first design baseline for implementation
**Primary audience:** coding/research agents and the human researcher

> **Purpose:** Build a durable, testable research process that (1) sizes marginal market exposure while maintaining a permanent long-term core in SPY/QQQ and (2) identifies unusually attractive multi-month opportunities in large, fundamentally viable, options-liquid individual stocks.

| **Core philosophy:** Stay invested. Use the signal to decide how much extra beta to carry, how much cash to deploy, and how aggressively to use options overlays-not whether to be in or out of the market. |
|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

| **Layer**      | **Role**                                                         | **Typical instruments**                                          |
|----------------|------------------------------------------------------------------|------------------------------------------------------------------|
| Core           | Permanent long-term compounding exposure                         | SPY / QQQ shares or equivalent index exposure                    |
| Beta amplifier | Raise effective exposure when expected reward/risk is attractive | Long-dated calls / LEAPs                                         |
| Single-name tactical | Deploy bounded marginal risk into validated large-cap opportunities | Shares, LEAPs, short puts/spreads, risk reversals as permitted    |
| Dry powder     | Preserve flexibility and reduce portfolio beta                   | Cash / cash equivalents                                          |
| Overlay        | Monetize or reshape exposure around the core                     | Covered calls, cash-secured puts, defined-risk option structures |

This document stays at the system-design level while including the implementation architecture needed for reproducibility: Python orchestration, bounded agents, immutable time snapshots, local-first storage, an incremental Codex-to-API runtime path, and a visualization layer designed for both exploratory research and auditable backtests. The research system has two coordinated engines: a SPY/QQQ market-regime engine and a large-cap single-name opportunity engine.

## Implementation Bias

Build the shortest end-to-end loop that can teach us whether the system helps make better market decisions. A new module, schema, capture layer, crawler, cache, or abstraction is justified only when it directly supports one of these near-term outcomes:

- Produce a current market-regime view.
- Produce a structured large-cap candidate list.
- Compare candidates or regimes to forward returns and drawdowns.
- Preserve exactly the source observation needed to reproduce a specific claim.

Do not build infrastructure just because the eventual system might need it. Start with one useful path, measure what it produces, then generalize only around repeated pressure from real research tasks.

# 1. Problem Statement

A long-term investor who intends to remain structurally long SPY/QQQ faces two recurring tactical questions: **when should marginal exposure be increased, held neutral, or reduced; and where should that marginal risk be deployed?** The first question is handled by a repeatable evidence-based market-regime signal. The second is handled by a large-cap opportunity engine focused on catching multi-month re-ratings, cyclical accelerations, and catalyst/momentum inflections in liquid names rather than speculative small-cap lottery tickets.

| **What success looks like:** The system does not need to forecast an exact market or stock price. It should (1) separate future SPY/QQQ 2-3 month return/drawdown distributions well enough to improve exposure sizing and (2) identify a subset of large-cap candidates whose multi-month forward return/asymmetry is materially better than comparable names and benchmarks after realistic implementation costs. |
|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Primary decisions the system should inform

- How much incremental beta should be carried above or below the neutral portfolio target?

- How much of the cash reserve should remain undeployed versus be used to add exposure?

- Should existing long exposure be left uncapped, partially overwritten with covered calls, or supplemented with put-selling / defined-risk structures?

- How aggressively should new LEAP exposure be initiated or maintained?

- When market conditions are mixed, should the portfolio remain near neutral rather than forcing a directional view?

- Which large, liquid individual stocks deserve research attention because subscription-derived signals, price action, fundamentals, and option-market evidence are aligning?

- When a strong single-name setup exists, what size/risk budget is justified by the broader SPY/QQQ regime and what instrument best expresses the view?

## Non-goals

- No all-in/all-out market timing.

- No requirement to predict daily or weekly moves.

- No single "magic indicator."

- No optimization for headline directional accuracy if it does not improve realized portfolio outcomes.

- No automated trade execution.

- No attempt to scan the entire equity market for obscure microcaps, distressed turnarounds, or illiquid option chains.

- No assumption that a Bulltard mention, unusual option trade, or scanner hit is itself a buy signal; subscription data is candidate-generation evidence that must be independently validated.

# 2. Portfolio Control Model

Think of the portfolio as a stable core plus bounded tactical sleeves. The market-regime engine controls the **aggregate marginal risk budget**; the single-name engine helps decide **where a portion of that risk budget may be deployed**. Neither engine can redefine the permanent long-term core.

| **Component**            | **Neutral state**               | **Risk-on adjustment**                  | **Risk-off adjustment**                                |
|--------------------------|---------------------------------|-----------------------------------------|--------------------------------------------------------|
| Core SPY/QQQ             | Always owned                    | Usually unchanged                       | Usually unchanged                                      |
| LEAP calls               | Moderate, pre-budgeted exposure | Add / roll into more delta if justified | Allow delta to decay, trim, or avoid adding            |
| Single-name tactical     | Small/bounded opportunity sleeve | Allocate to validated high-quality setups within risk budget | Reduce size/new entries; prefer conservative structures or watchlist |
| Cash                     | Permanent reserve               | Deploy a measured portion               | Rebuild / preserve reserve                             |
| Covered calls            | Selective                       | Lighter overwrite / farther OTM         | Heavier overwrite / closer strikes where appropriate   |
| Short puts / put spreads | Selective                       | More willing to underwrite pullbacks    | Demand better entry levels / lower size / defined risk |

The exact neutral beta target and allowable tactical range should be specified later (for example, a neutral portfolio near beta 1.0 with a bounded band around it). The important design rule is that the model may move the portfolio within that band, but not redefine the long-term investment policy.

# 3. System Architecture

| **Stage / engine**              | **Function**                                                                                               | **Output**                                           |
|---------------------------------|------------------------------------------------------------------------------------------------------------|------------------------------------------------------|
| 1. Shared data                  | Collect index, single-name, volatility, breadth, fundamentals, options, sentiment, and external research | Point-in-time normalized observations                |
| 2. Market regime engine         | Score trend, volatility, breadth, liquidity/credit, sentiment, and external market evidence               | SPY/QQQ regime score + confidence + forward outcomes |
| 3. Single-name opportunity engine | Gate the universe, ingest Bulltard candidates, validate fundamentals/liquidity, and rank setups          | Candidate lifecycle + opportunity score              |
| 4. Forward-distribution engine  | Map market regimes and single-name setups to historical future returns/drawdowns                           | Expected return / drawdown distributions             |
| 5. Portfolio policy engine      | Translate market regime into risk budget, then allocate marginal research attention/exposure to setups    | Beta / cash / position-risk guidance                 |
| 6. Research journal             | Store signals, state transitions, rationale, realized outcomes, and model changes                          | Audit trail for iteration                            |

## Top-level application model

The top-level system should be a conventional Python research application. It owns workflow, data provenance, model execution, portfolio calculations, opportunity-state transitions, and persistence. Agents are invoked as bounded analytical workers inside that application rather than acting as the system of record or deciding the control flow themselves. The market-regime and single-name engines are peer research modules that share data, point-in-time semantics, backtesting infrastructure, and the portfolio-policy layer.

| Component            | Primary responsibility                                                                                                      | Design rule                                                     |
|----------------------|-----------------------------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------|
| Python orchestrator  | Run ingestion, validation, snapshot creation, shared feature calculation, regime scoring, opportunity gating/ranking, lifecycle transitions, portfolio policy, and report generation. | Owns deterministic control flow. |
| Quant / feature code | Compute prices, breadth, volatility, fundamentals-derived features, option liquidity, relative strength, forward returns, beta, option delta, backtests, and model outputs. | If the question is "what is the number?", prefer code. |
| Agent workers        | Extract messy research, identify/canonicalize Bulltard candidates, compare narratives, critique signals, investigate contradictions, and write research memos. | If the question is "what does this mean?", an agent may help. |
| Research store       | Persist raw observations, universe history, normalized data, feature/opportunity snapshots, model versions, Bulltard extractions, lifecycle transitions, and outcomes. | Database state-not agent memory-is the project memory. |
| Scheduler            | Optionally launch stable pipelines on a cadence after the manual workflow is trusted.                                       | Cron is a trigger only; it contains no investment intelligence. |

## Bounded agent contract

Agent calls should have explicit inputs and structured outputs. For example, a Bulltard extraction worker receives the recap text, database snapshot, and prior-day state, then returns validated fields such as market view, key levels, book changes, trade ideas, unusual flow, catalysts, and confidence language. A separate candidate-analysis worker may summarize the thesis or identify missing evidence, but deterministic code owns universe eligibility, liquidity calculations, feature values, lifecycle state rules, and backtest labels. The Python layer validates and stores agent output. A Regime Critic may explain bull/bear contradictions, but it should not silently rewrite the numerical regime score.

## Execution model

Development should begin as an explicitly invoked research workflow (CLI and/or notebook), not as an automated trading service. Once ingestion and snapshot semantics are stable, selected collection jobs may be scheduled. A typical deterministic run is: ingest → validate → build snapshot → compute shared features → score SPY/QQQ regime → extract/refresh Bulltard candidates → gate/rank single-name opportunities → invoke bounded critics/research agents → calculate portfolio posture/risk budget → persist → render report.

| Mode                | Typical invocation                 | Behavior                                                                                       |
|---------------------|------------------------------------|------------------------------------------------------------------------------------------------|
| Manual research     | marketlab regime --date YYYY-MM-DD | Reproduce a specific historical official signal from frozen data.                              |
| Live preview        | marketlab regime --live            | Calculate a provisional intraday view without changing the official historical record.         |
| Scheduled ingestion | cron → run_daily_pipeline.py       | Collect data and create snapshots after the workflow is stable; no autonomous trade execution. |

## Suggested initial storage

A lightweight local research stack such as DuckDB + Parquet is appropriate initially. Raw observations should be immutable; normalized tables and feature tables should reference the source snapshot and version that produced them. Suggested logical tables include market_prices, volatility, breadth, macro, sentiment, security_master, universe_membership, security_fundamentals, option_liquidity, daily_features, regime_snapshots, single_name_features, opportunity_snapshots, candidate_state_transitions, bulltard_recaps, bulltard_signals, portfolio_snapshots, research_experiments, model_versions, and signal_outcomes.

# 4. Time, Snapshots & Reproducibility

Time consistency is a first-class requirement. A model run must never mean "fetch whatever is latest and calculate." Every official regime or single-name opportunity calculation must consume a named, frozen as-of snapshot so that the same historical state can be reproduced later.

## Canonical time modes

| Mode             | Purpose                                                                                      | Status / rule                                                              |
|------------------|----------------------------------------------------------------------------------------------|----------------------------------------------------------------------------|
| Prior close      | Pre-market research using only information available through the previous completed session. | Stable once the prior session closes.                                      |
| Intraday preview | Understand how the regime may be evolving during the current session.                        | Provisional; allowed to change and never treated as the scientific record. |
| End of day (EOD) | Canonical daily regime **and opportunity state** for research, backtests, and longitudinal performance tracking. | Official; frozen after the defined market-close/data-availability cutoff. |

## Official signal semantics

- The canonical daily regime and opportunity state should use a clearly defined EOD/data-availability cutoff because the project targets multi-month horizons; intraday fluctuations should not continuously rewrite the strategic research record.

- A historical request for an official date must return the same result regardless of when the program is run later, provided the same snapshot, feature version, and model version are selected.

- The regime and opportunity engines receive snapshot objects. They should not themselves query external sources for "latest" values.

- Live previews should be visibly labeled provisional and should be compared with-not overwrite-the latest official EOD regime.

## Timestamp alignment

Inputs have different natural timestamps. Market prices, VIX/VVIX, breadth, macro data, and Bulltard commentary must therefore retain both observation time and availability time. Bulltard recaps may arrive during the trading session and discuss same-day conditions; the system must not accidentally combine that narrative with a data cutoff that implies it was known earlier. Research datasets should enforce point-in-time availability when backtesting to avoid look-ahead bias.

## Immutable snapshots and version identifiers

| Field            | Example                        | Meaning                                         |
|------------------|--------------------------------|-------------------------------------------------|
| signal_date      | 2026-08-24                     | Trading date represented by the signal.         |
| signal_time      | EOD                            | Canonical mode or explicit intraday timestamp.  |
| snapshot_version | marketdata_v1 / 2026-08-24_eod | Exact frozen observations used.                 |
| universe_version | largecap_v1 / 2026-08-24 | Exact point-in-time eligible universe and gate configuration. |
| feature_version  | features_v4                    | Exact feature definitions and transformations.  |
| model_version    | regime_v3                      | Exact regime logic / fitted parameters.         |
| opportunity_version | opportunity_v2               | Exact single-name eligibility/ranking/lifecycle logic. |
| policy_version   | exposure_v2                    | Exact mapping from regime to portfolio posture. |

Historical snapshots should never be silently overwritten. If a vendor corrects data, universe membership changes, or a bug is fixed, create a new snapshot, universe, feature, regime-model, or opportunity-model version and preserve the old result for auditability. This makes it possible to distinguish "what the system knew then" from "what we know now."

# 5. Market Regime Model

The model should be ensemble-like: several independent families vote on the regime. A feature is valuable when it contributes incremental information, not merely because it is popular.

| **Family**              | **Candidate inputs**                                                               | **Question answered**                                                           |
|-------------------------|------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| Trend / structure       | Price vs. moving averages, slope, distance from highs, term trend, momentum        | Is the market structurally advancing or deteriorating?                          |
| Volatility              | VIX, VVIX, term structure, realized vs. implied vol, vol-of-vol                    | Is risk being cheaply or expensively priced, and is volatility stress building? |
| Breadth                 | Advance/decline, % above key averages, new highs/lows, equal-weight vs. cap-weight | Is participation confirming the index?                                          |
| Liquidity / credit      | Credit spreads, rates, financial conditions, dollar, liquidity proxies             | Is the macro financing backdrop supportive or restrictive?                      |
| Sentiment / positioning | Fear/greed, put/call, surveys, flows, CTA/positioning proxies, social sentiment    | Are investors euphoric, fearful, crowded, or under-positioned?                  |
| External research       | Bulltard market commentary, database statistics, recurring option-flow patterns    | Does an independent discretionary/data source confirm or contradict the regime? |

## Regime output

Avoid a binary BUY/SELL output. A useful daily snapshot should look more like:

| **Field**                   | **Example interpretation**                                                              |
|-----------------------------|-----------------------------------------------------------------------------------------|
| Regime score                | -2 = risk-off, -1 = cautious, 0 = neutral, +1 = constructive, +2 = risk-on              |
| Confidence                  | How aligned the feature families are and how familiar the current state is historically |
| Forward return distribution | Historical distribution for SPY/QQQ over roughly 40-65 trading days                     |
| Drawdown distribution       | Expected/max adverse excursion under comparable regimes                                 |
| Contradictions              | Important families that disagree with the composite                                     |
| Change flag                 | Whether the regime is stable, improving, or deteriorating                               |

The output should prefer calibrated uncertainty over false precision. "Moderately cautious, 62% confidence" is more useful than "QQQ will fall 7.3%."

# 6. Translation From Signal to Portfolio Posture

The highest-value design decision is the mapping layer between a statistical regime and an actual portfolio action. This mapping should be explicit, bounded, and backtested separately from the signal itself.

| **Regime**      | **Portfolio intent**             | **Illustrative posture (not final rules)**                                                    |
|-----------------|----------------------------------|-----------------------------------------------------------------------------------------------|
| Strong risk-on  | Carry modestly more beta         | Deploy some dry powder; favor maintaining/adding long delta; lighter call overwrite           |
| Constructive    | Slightly above neutral           | Normal core + measured LEAP exposure; selective put-selling on pullbacks                      |
| Neutral / mixed | Stay near policy beta            | Preserve flexibility; avoid forcing directional options trades                                |
| Cautious        | Slightly below neutral           | Preserve more cash; monetize some upside; demand better put-sale entry                        |
| Strong risk-off | Defend tactical sleeve, not core | Keep core invested; lower incremental delta; heavier but bounded overwrite; retain dry powder |

| **Design constraint:** The tactical layer must have hard exposure limits. A model failure should be able to hurt performance, but it should not be able to destroy the long-term portfolio thesis. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

# 7. Bulltard Research Module

The subscription should be treated as a structured research source rather than a stream of ephemeral trade ideas. It serves two roles: (1) an external market/regime input and (2) the primary candidate generator for the single-name opportunity engine. The objective is to learn which parts of the service contain persistent information and which are noise; a mention or flow event does not automatically pass our own eligibility or validation gates.

## Bulltard observations to ingest

- Market regime / SPY commentary and key technical levels.

- Changes to the author's open book, including adds, closes, sizing language, and stated thesis.

- Trades of interest: ticker, option structure, expiry, strike, flow size, technical context, catalyst, and alternative implementation.

- Scanner / momentum signals and the daily database snapshot.

- Repeated signals across multiple days (for example, recurrent put-selling or repeated call accumulation).

The goal is not to archive the Bulltard app or mirror its database. The app is an interface to a subscription data source. MarketLab should retrieve the specific views needed for a research question, parse them into structured observations, and store only the observations and provenance needed to reproduce our own analysis.

Because the daily database/link may be ephemeral, **data ingestion may eventually be automated even though trading remains manual**. The desired automation boundary is ingest/extract only: use the recap link while it is valid, pull a narrow set of relevant rows, and make those rows available for testing candidate quality. There is no broker integration or autonomous order path.

## Confirmed daily-access mechanics

A direct capture test on a current recap materially simplified the ingestion design. The recap contains a signed Substack redirect URL. Opening that original signed URL in a fresh browser succeeds, while opening the clean `https://app.jamesbulltard.com/` destination directly in a fresh browser is blocked. The correct working assumption is therefore **capability/bootstrap access from the original daily email link**, not a persistent personal-browser profile.

The application currently exposes useful server-rendered views without browser automation, including:

- `/ranked_option_trades` - Rankings.
- `/daily_option_trades` - Daily Chart.
- `/bullish_gainers` - Bullish Flow Top Gainers.
- `/sector_rankings` - Sectors.
- `/tickers/<TICKER>` - individual ticker pages.
- `/scanner/?access_token=...` - Scanner, with a separate short-lived access token surfaced by the application page.

Those views contain table values and ticker links rather than only an empty JavaScript shell. Therefore, **plain HTTP with one short-lived session is the v0 default**; Playwright is only a fallback if a concrete required view cannot be read with plain HTTP.

### Deterministic ingest flow

```text
Gmail recap
    ↓
extract original signed Substack database URL
    ↓
create fresh httpx.Client(follow_redirects=True)
    ↓
GET signed URL and establish the daily access session
    ↓
request one named Bulltard view needed for the current research task
    ↓
parse table rows/signals from that view
    ↓
store structured observations with retrieval metadata
    ↓
compare candidates/signals to independent features and future outcomes
```

The ingester should not require a persistent Chrome profile, copy browser cookies, manufacture tokens, or attempt to bypass expiry. If the server sets cookies during the redirect chain, `httpx.Client` may carry them automatically for that capture session; they are an implementation detail rather than project state. Every trading day should bootstrap from that day's original signed email URL.

For v0, the durable product is structured observation rows, not copied application pages. Raw HTML/network payloads may be kept as local debug cache when parser development needs them, but they are not the research artifact and should not drive the design.

### Targeted query boundary

Bulltard ingestion should be query-shaped, not crawler-shaped:

- Request one named view at a time, starting with the view most likely to produce candidate rows.
- Expand to another view only when it supports a concrete research question.
- Fetch ticker pages only for candidates that pass the large-cap/options-liquidity gate or are needed to debug that gate.
- Do not attempt to reconstruct or mirror the full Bulltard database.
- Preserve query parameters supplied by the application, including scanner access tokens, but never generate or alter access tokens.
- Record source date, retrieval time, view name, final URL/context, parser version, and row count for every ingested observation set.

This ingester is deterministic infrastructure, **not an agent browsing task**. Python should acquire and normalize the source observations first. Agents operate on structured rows afterward so research is reproducible and does not depend on a live expiring link.

### Credential and source handling

The original signed Substack URL and scanner token should be treated as short-lived capabilities. They must never be committed to Git or exposed in generated public reports. Local operational logs may show exact temporary URLs when useful for debugging; redaction belongs in public/exported artifacts or explicit commands, not as a default feature that obscures local bring-up.

A suggested v0 local layout is:

```text
data/inbox/bulltard/
└── recap-2026-08-24.html        # saved email/input, gitignored

data/observations/bulltard/
└── ranked_option_trades/
    └── 2026-08-24.jsonl         # parsed rows + minimal provenance, gitignored
```

Move to DuckDB/Parquet when the row volume or query patterns justify it. Do not introduce a database solely to make the skeleton look complete.

### Ingest command contract

The first implementation should expose a boring, repeatable command such as:

```bash
marketlab bulltard ingest --date 2026-08-24 --view ranked-option-trades data/inbox/bulltard/recap-2026-08-24.html
```

Its responsibility is only to: read the requested recap, extract the signed link, establish daily access, retrieve one named view, parse rows, write structured observations, and report what it produced. Candidate scoring is a separate step. A failed ingest should fail visibly and should not be filled from a later date.

## Research questions

| **Question**                                                                                              | **Why it matters**                                                          |
|-----------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| Do repeated large put sales predict better forward returns or merely identify lower desired entry levels? | Separates useful underwriting information from false bullish interpretation |
| Are ideas stronger when technical momentum agrees with option flow?                                       | Tests signal combination rather than anecdotes                              |
| Do open-book, high-conviction positions outperform "trades of interest"?                                  | Identifies where the author's actual edge may reside                        |
| Which implementation works best: common stock, long calls, risk reversals, or short puts?                 | Separates thesis quality from instrument selection                          |
| Does his broad market caution/optimism add information to our independent regime model?                   | Potential external ensemble feature                                         |

# 8. Large-Cap Single-Name Opportunity Engine

The single-name engine is designed to catch substantial multi-month moves in established, liquid companies: fundamental/catalyst re-ratings, cyclical accelerations, and sustained momentum/positioning inflections. It is **not** a general stock picker and is not optimized for finding tiny speculative names. The target is to participate in a meaningful middle portion of a 3-9 month move rather than identify the exact bottom or top.

## Engine separation

The two research engines answer different questions and should not be collapsed into one composite score:

| Engine | Primary question | Typical output |
|---|---|---|
| Market regime | How much marginal risk should the portfolio carry? | Risk-on / neutral / cautious regime, confidence, beta/risk-budget band |
| Single-name opportunity | Where does the best large-cap asymmetric opportunity currently exist? | Ranked candidates, lifecycle state, opportunity score, preferred research/expression |

A strong single-name setup can exist in a cautious market. In that case the broader regime may reduce initial size, favor more conservative option structures, or require more confirmation; it should not automatically invalidate the stock thesis.

## Eligible-universe gate

The opportunity engine starts with a deliberately narrow universe. Exact thresholds are configuration, not hard-coded design constants, and should be calibrated using observed liquidity rather than intuition alone.

| Gate | Intent |
|---|---|
| Size / institutional quality | Focus on large, widely followed companies and major liquid ADRs; use an initial market-cap floor or membership list as a configurable filter. |
| Underlying liquidity | Require substantial daily dollar volume so entries/exits are not dependent on thin trading. |
| Options liquidity | Require robust listed options, usable open interest/volume around relevant strikes/expirations, acceptable bid/ask spreads, and practical multi-month/LEAP expirations where the strategy requires them. |
| Fundamental viability | Reject names with severe balance-sheet, accounting, financing, solvency, or binary-survival risk unless explicitly studied as a separate strategy. Cyclical weakness or a credible turnaround is allowed; "fundamentally viable" does not mean current earnings must be perfect. |
| Instrument suitability | The name must support at least one implementation that fits the portfolio policy: shares, LEAPs, short puts/put spreads, covered calls, or risk reversals as allowed. |

The fundamental gate is intended to remove structurally broken/speculative situations, not to create a full DCF stock-selection model. Deeper fundamental strength, estimate revisions, valuation, and catalysts can then be features used in ranking.

## Candidate generation

Bulltard is the primary candidate generator in v0. Candidates may be created from:

- Unusual call buying or large put selling.
- Repeated option flow across multiple sessions.
- Momentum/database scanner appearances.
- Open-book positions, additions, exits, and unusually strong conviction/sizing language.
- Explicit catalysts, technical setups, risk reversals, or institutional-sized option structures.

Later, independent scanners may generate candidates too, but they should enter the same validation/lifecycle pipeline rather than create a parallel ad-hoc process.

## Opportunity feature families

A candidate that passes the hard universe gate is independently evaluated. Candidate feature families may include:

| Family | Candidate evidence | Question |
|---|---|---|
| Subscription / positioning | Bulltard signal type, flow size, repeat count, open-book status, conviction language | Is there unusual informed-looking interest and is it persistent? |
| Price / momentum | Trend, breakout/reclaim, relative strength vs. SPY/QQQ/sector, momentum inflection, volume | Is price action confirming the thesis rather than fighting it? |
| Fundamentals | Revenue/earnings trajectory, estimate revisions, margins, balance sheet, FCF, major business inflections | Is there a plausible fundamental engine for a multi-month re-rating? |
| Catalyst / narrative | Earnings setup, product cycle, customer win, capacity cycle, regulatory change, capital allocation, industry cycle | What could cause the market to revise expectations? |
| Valuation / expectations | Multiples vs. history/peers, implied expectations, prior derating | Is enough bad news priced in or is the upside already crowded? |
| Option market | Implied vol, skew, term structure, OI/volume, spread quality, repeated strike/expiry activity | Is the options market liquid enough and does positioning add evidence? |
| Market / sector regime | SPY/QQQ regime plus sector/industry relative state | Is the macro tape helping, neutral, or creating a sizing headwind? |

Avoid adding many correlated variants of the same signal. As with the regime engine, family-level evidence should matter more than indicator count.

## Candidate lifecycle

A candidate is a stateful research object, not a static watchlist row:

```text
DISCOVERED
    ↓
WATCHING
    ↓
VALIDATED
    ↓
ACTIVE_SETUP
   ↙      ↘
PLAYED_OUT  INVALIDATED
```

Suggested semantics:

- **DISCOVERED:** a qualifying external/internal signal creates the candidate.
- **WATCHING:** candidate passes universe gates but lacks enough confirmation or an attractive entry/expression.
- **VALIDATED:** evidence across independent families is strong enough to define a testable thesis, catalyst, invalidation condition, and preferred horizon.
- **ACTIVE_SETUP:** risk/reward and implementation are currently attractive enough for portfolio consideration.
- **PLAYED_OUT:** the expected re-rating/catalyst has substantially occurred or asymmetry is no longer compelling.
- **INVALIDATED:** fundamental, technical, catalyst, or market evidence breaks the thesis.

Every transition is timestamped and immutable. Re-entry after invalidation or played-out status should create a new opportunity episode rather than silently reuse the old one.

## Opportunity output

A daily candidate snapshot should be explainable rather than merely emit a rank:

| Field | Meaning |
|---|---|
| Eligibility | Pass/fail plus failed hard gates |
| Lifecycle state | Discovered / Watching / Validated / Active Setup / Played Out / Invalidated |
| Opportunity score | Normalized score or percentile from independent feature families |
| Confidence | Degree of agreement and amount/quality of available evidence |
| Horizon | Expected thesis window, typically multi-month |
| Bulltard evidence | Signal type, repeats, flow, open-book/conviction context |
| Fundamental/catalyst thesis | What must improve or be recognized by the market |
| Technical/relative-strength state | Whether price is confirming or diverging |
| Option liquidity score | Practical tradability of the desired structures |
| Invalidation | Conditions that would make the thesis wrong or no longer attractive |
| Market-regime modifier | Risk-budget/sizing context, separate from opportunity quality |
| Candidate expressions | Research-only comparison of shares/LEAPs/short puts/spreads/etc., subject to policy |

## Portfolio translation

The market engine controls **risk budget**; the opportunity engine controls **opportunity selection**; an instrument-selection layer controls **payoff shape**. Keep these separations explicit.

For example, a high-scoring stock in a strong risk-on regime may justify more long delta or a more convex expression, while the same stock in a cautious regime may justify smaller initial delta, more dry powder, a lower strike short-put/defined-risk structure, or simply continued observation. These are policy choices to be backtested; they are not baked into the opportunity score itself.

# 9. Research & Backtesting Methodology

The project should be built to resist overfitting from day one. The standard is not "can we find a pretty historical chart?" but "does the relationship survive reasonable changes in sample, parameters, and market regime?"

- Use walk-forward / out-of-sample evaluation. Never tune and score on the same period.

- Keep feature families small initially; add complexity only when it improves out-of-sample results.

- Measure forward 40-, 50-, and 65-trading-day returns rather than one arbitrary horizon.

- Measure drawdowns and adverse excursion, not only terminal returns.

- Evaluate SPY and QQQ separately; a useful signal may behave differently across index composition and beta.

- Evaluate single-name opportunities at multiple horizons appropriate to re-ratings (for example 20/40/65/126 trading days), including absolute return, return relative to SPY/QQQ/sector, maximum adverse excursion, maximum favorable excursion, and time-to-peak.

- Evaluate candidate state transitions and feature combinations, not only the final opportunity score: e.g. Bulltard flow alone versus flow + relative-strength inflection versus flow + revisions + momentum.

- Use survivorship-aware point-in-time universe membership and fundamentals/options availability wherever practical; do not backtest today's eligible universe as if it existed unchanged historically.

- Model transaction costs, option spreads, taxes, and assignment/roll behavior when evaluating portfolio overlays.

- Track calibration: high-confidence signals must actually be more reliable than low-confidence signals.

- Maintain a frozen benchmark: e.g., buy-and-hold core plus a simple fixed tactical policy, so every model iteration must earn its complexity.

## Primary evaluation metrics

| **Level**  | **Metrics**                                                                                                |
|------------|------------------------------------------------------------------------------------------------------------|
| Regime signal | Forward return spread by regime, hit rate, rank correlation, drawdown separation, calibration          |
| Opportunity | Forward absolute/relative returns, hit rate, MFE/MAE, time-to-peak, lifecycle precision, score calibration |
| Overlay    | CAGR / total return, max drawdown, Sharpe/Sortino, beta, realized volatility, turnover, option income/cost |
| Robustness | Out-of-sample persistence, parameter stability, performance across bull/bear/sideways periods              |

# 10. Data & Research Record

Every live signal should be recorded before the outcome is known. This turns the project into a longitudinal experiment and prevents hindsight from rewriting the thesis.

| **Record**            | **Minimum fields**                                                                |
|-----------------------|-----------------------------------------------------------------------------------|
| Daily regime snapshot | Date, family scores, composite, confidence, contradictions, SPY/QQQ levels        |
| Portfolio posture     | Neutral beta target, tactical beta target, cash reserve %, option overlay stance  |
| Bulltard extraction   | Market view, book changes, ideas, database/scanner signals, notable repeated flow |
| Opportunity snapshot  | Ticker, eligibility gates, family scores, lifecycle state, thesis, horizon, liquidity, invalidation |
| Candidate transition  | Ticker, old/new lifecycle state, timestamp, evidence/reason, opportunity/model version |
| Decision journal      | What action was considered/taken and why                                          |
| Outcome               | 40/50/65d returns, max drawdown, realized vol, trade/overlay P&L where applicable |
| Iteration log         | Feature/rule changed, reason, date frozen, before/after performance               |

## Minimum provenance carried by every calculated signal

- Observation timestamps and availability timestamps for every external input family.

- Named snapshot identifier and whether the result is prior-close, intraday-preview, or official EOD.

- Feature, universe, regime-model, opportunity-model, and portfolio-policy versions.

- Execution timestamp, code revision / experiment identifier, and any agent worker versions or extraction schema versions used.

# 11. Development Plan

Build the simplest version that can teach us something, then add sophistication only when justified. A valid implementation slice should increase decision feedback: better candidate rows, better regime evidence, better outcome measurement, or a clearer rejection of a weak idea. Status files, generic storage layers, crawlers, broad manifests, and agent wrappers are secondary unless they unblock that feedback loop.

| **Phase** | **Scope** | **Exit criterion** |
|---|---|---|
| 0. Design / bootstrap | Agree on objectives, portfolio constraints, and a minimal local CLI | Design baseline accepted; deterministic CLI runs locally |
| 1. Bulltard signal-ingest MVP | Ingest one useful Bulltard view into structured candidate rows; define the smallest signal taxonomy needed for those rows | We can produce a daily candidate list from a real recap and inspect the rows |
| 2. Candidate outcome MVP | Add large-cap gate, option-liquidity gate, basic price/relative-strength context, and forward return/drawdown labels | We can replay historical candidates and measure 20/40/65/126d outcomes |
| 3. Regime MVP | Trend + volatility + breadth; simple interpretable composite for SPY/QQQ | Clear out-of-sample separation of forward outcomes or explicit "no edge" result |
| 4. Portfolio policy | Map regime to bounded beta/cash risk budget and combine with validated single-name opportunities | Policy adds risk-adjusted value vs. fixed-policy benchmark |
| 5. Expand evidence | Liquidity/credit, sentiment, richer fundamentals/revisions, Bulltard-derived features, sector context | Each added family shows incremental out-of-sample value |
| 6. Iterate | Periodic review, feature retirement, parameter freezes, candidate/outcome monitoring | Stable research cadence without constant curve-fitting |

# 12. Key Design Risks

| **Risk**                                     | **Mitigation**                                                                                                    |
|----------------------------------------------|-------------------------------------------------------------------------------------------------------------------|
| Overfitting / indicator soup                 | Small feature set, walk-forward testing, frozen baselines, explicit feature retirement                            |
| False precision                              | Use regimes and distributions, not point forecasts                                                                |
| Correlated indicators                        | Score families first; avoid counting five versions of the same information as five votes                          |
| Options complexity overwhelms signal         | Test signal and implementation separately; keep structures bounded and comparable                                 |
| Model causes excessive trading               | Use hysteresis / minimum-change rules and tactical exposure bands                                                 |
| Narrative bias from newsletters/social media | Record signals before outcomes; statistically score repeated patterns                                             |
| Regime shifts                                | Monitor degradation; allow "unknown/low confidence" rather than forcing a view                                    |
| Time inconsistency / look-ahead bias         | Immutable as-of snapshots, explicit availability timestamps, official EOD semantics, and point-in-time backtests. |
| Subscription anchoring / authority bias      | Bulltard creates candidates, not decisions; compare against independent features and measure incremental value. |
| Illiquid option implementation               | Hard liquidity gates, spread/OI/volume diagnostics, and realistic slippage assumptions before strategy testing. |
| Fundamental distress masquerades as value    | Separate hard viability gate from upside scoring; require explicit invalidation conditions and episode tracking. |
| Watchlist hindsight / cherry-picking         | Persist every candidate and lifecycle transition before outcomes are known, including rejected/failed candidates. |

# 13. Open Questions

- What is the desired neutral portfolio beta, and what tactical beta range is acceptable (e.g., roughly 0.8-1.2, 0.9-1.3, etc.)?

- How much cash should be structurally reserved as dry powder even in a strong risk-on regime?

- How large may the LEAP sleeve become as a percentage of portfolio value / delta-adjusted exposure?

- Should SPY and QQQ receive separate regime scores or one shared macro score plus index-specific modifiers?

- Which option strategies are permitted in the tactical layer, and which are explicitly off-limits?

- What historical period should be considered representative enough for the first backtest?

- How much historical Bulltard source content is still retrievable, given that the daily signed access link is explicitly ephemeral?

- What initial large-cap universe should be used (market-cap floor, index membership, or a curated liquid list), and how should historical universe membership be reconstructed?

- What option-liquidity thresholds define a tradable candidate for shares, multi-month options, and LEAP-based expressions?

- What constitutes a hard fundamental viability failure versus a temporary cyclical/turnaround weakness?

- Should the single-name opportunity horizon default to 3-6 months, or support multiple thesis classes up to roughly 9-12 months?

- Which independent fundamental/estimate-revision data sources are practical and point-in-time enough for v0?

| Recommended immediate next step: implement one end-to-end Bulltard candidate path. From a saved recap, use the signed link to retrieve one useful view, parse candidate rows, save those rows locally, then inspect whether they are the right inputs for large-cap filtering and forward-return testing. |
|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

# 14. Implementation Infrastructure

The initial infrastructure should optimize for iteration speed and scientific reproducibility, not production-scale operations. The project should remain easy to run on a personal machine and easy to migrate later if continuous unattended execution becomes valuable.

| **Concern**             | **v0 choice**             | **Reason**                                                                                                                           |
|-------------------------|---------------------------|--------------------------------------------------------------------------------------------------------------------------------------|
| Source control          | Private GitHub repository | Code, configuration, schemas, tests, research notes, and model definitions belong in Git; changing market-data files do not.         |
| Active analytical store | Local DuckDB              | Fast SQL over local research data with almost no operational overhead.                                                               |
| Observation history     | Local JSONL/Parquet first | Simple, inspectable storage for ingested observations and research snapshots; move to richer storage when queries require it.         |
| Backup                  | Personal Google Drive     | Simple off-machine backup for observation files, DB checkpoints, and generated reports.                                              |
| Cloud infrastructure    | None initially            | S3/GCS and hosted compute are unnecessary until the system must run while the laptop is offline or serve multiple machines/services. |

**Storage rule:** GitHub stores definitions and code, not the live market database. Google Drive is a backup target, not the location from which DuckDB should be actively opened and mutated.

## Local data layout

- repo/: source code, tests, notebooks, configs, migration/schema definitions, AGENTS.md, and documentation.

- data/inbox/: user-supplied inputs such as saved recaps. Preserve acquisition/availability timestamps when known.

- data/observations/: structured rows ingested from market data, option-liquidity sources, fundamentals, and external research signals.

- data/debug/: optional raw payload cache for parser replay or troubleshooting. This is not the main research product.

- data/snapshots/: named prior-close, intraday-preview, and official-EOD snapshots, including eligible-universe and opportunity state.

- marketlab.duckdb: active local metadata/query database; periodically checkpoint or export for backup.

- reports/: reproducible daily reports, research figures, and experiment summaries.

## Agent runtime strategy

The project should expose one internal agent interface while allowing the implementation backend to change. During early research, a local Codex invocation is a useful bridge between fully manual analysis and a production API integration.

| **Stage**          | **Agent backend**                     | **Use**                                                                                                                                           |
|--------------------|---------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------|
| v0 exploratory     | Codex interactively in the repository | Ad-hoc investigation, code changes, backtest interpretation, and prompt/context discovery.                                                        |
| v0 scripted        | Local codex exec / Codex harness      | Programmatic low-volume qualitative analysis using the same local repository and research packets; suitable while the workflow is still evolving. |
| later standardized | OpenAI API                            | Strict schemas, explicit model/runtime contracts, batch extraction, retries, logging, unattended scheduled runs, and cloud execution.             |

The application should depend on an abstract ResearchAgent contract rather than on Codex-specific behavior. This permits a later backend swap without changing the quant pipeline, data schema, or research-report interface.

- Codex remains an agent harness, not a local inference engine; it still uses OpenAI-hosted models and the user's applicable Codex allowance.

- Canonical quantitative calculations must never depend on an agent choosing arbitrary tool paths. Agents consume frozen research packets and return bounded outputs.

- Move a task to the API when the application itself must own a stable machine-to-machine contract: strict JSON schemas, large batch jobs, deterministic retry/error handling, or unattended execution.

- Secrets and credentials remain local and gitignored; never store API keys, account tokens, or service credentials in Git, even in a private repository.

## Migration trigger for S3/GCS or hosted compute

Cloud object storage should be introduced only after a concrete requirement appears: the pipeline must run when the personal machine is offline, multiple machines/services need a shared authoritative dataset, dataset scale makes local backup inconvenient, or scheduled execution requires a hosted runtime. At that point, S3 or GCS can replace the archive/authoritative object-store role without changing the logical snapshot model.

# 15. Visualization & Research UI

Visualization is a core research instrument. The objective is not to create a decorative dashboard; it is to make regime changes, component disagreements, single-name candidate lifecycles, subscription signals, historical analogs, and forward outcomes visually inspectable while preserving exact as-of semantics.

## Recommended v0 visualization stack

| **Need**                          | **Tool**                                             | **Role**                                                                                            |
|-----------------------------------|------------------------------------------------------|-----------------------------------------------------------------------------------------------------|
| Interactive exploration           | Plotly                                               | Zoom, hover, synchronized time axes, regime shading, event markers, and local HTML output.          |
| Canonical/static research figures | Matplotlib                                           | Stable plots for experiment artifacts, versioned reports, tests, and publication-quality snapshots. |
| Exploratory workspace             | Jupyter notebook                                     | Fast iteration on signals, event studies, factor decomposition, and visual diagnostics.             |
| Optional later UI                 | Local lightweight app (e.g. Streamlit or equivalent) | Useful only after the core charts and research questions stabilize; not required for v0.            |

## Canonical regime-versus-price view

The primary daily research view should use aligned panels with a shared time axis:

- Panel 1 - SPY or QQQ price curve, optionally with major moving averages and drawdown. Shade the background by official regime bucket; do not use live-preview states in historical official charts.

- Panel 2 - Continuous composite regime score. Show threshold bands and explicit regime-transition markers so the viewer can distinguish gradual deterioration from discrete policy changes.

- Panel 3 - Component-family scores (trend, volatility, breadth, liquidity/credit, sentiment, Bulltard overlay). Normalize or standardize them so visual scale differences do not imply false importance.

- Panel 4 - Portfolio-policy state: target beta band, estimated current delta-adjusted beta, cash reserve, and major tactical actions. This separates "what the market model said" from "what the portfolio policy did."

**Important:** avoid a misleading dual-axis chart where a rescaled signal is visually forced to match SPY. Shared time axes are useful; arbitrary y-axis rescaling is not evidence of predictive value.

## Views that test whether a signal is real

Every attractive overlay chart should be paired with quantitative visual diagnostics:

- Forward-return buckets: group signal values into quintiles/deciles and plot the 40/50/65-day forward-return distributions for SPY and QQQ.

- Drawdown buckets: compare maximum adverse excursion and maximum favorable excursion after different regime levels.

- Event studies: align market paths around discrete regime transitions (for example, Neutral → Cautious) and show median plus percentile bands.

- Scatter / calibration plots: signal score versus future return, ideally with monotonic smoothing and sample counts rather than an overfit regression curve.

- Rolling diagnostics: rolling rank correlation, regime hit rates, and performance by market era to expose deterioration or dependence on one historical period.

- Component disagreement view: highlight dates where trend, breadth, and volatility materially disagree; these are often the most valuable cases for qualitative agent review.

## Canonical single-name opportunity view

For an individual candidate, use aligned panels with a shared time axis:

- Panel 1 - Price, major trend levels, volume, and relative strength vs. SPY/QQQ/sector. Mark Bulltard signal dates and lifecycle transitions (Discovered, Validated, Active, Invalidated/Played Out).
- Panel 2 - Continuous opportunity score plus independent family scores (subscription/positioning, momentum, fundamentals, catalyst/valuation, option market, market/sector context).
- Panel 3 - Option-liquidity diagnostics and major observed flow events: IV/skew/term structure where available, OI/volume, and spread quality.
- Panel 4 - Forward evaluation layer for research mode: subsequent relative return, MFE/MAE, and event-window outcomes. This layer must be visually separated from information that was available at the signal date.

Useful cohort views include: Bulltard signals by type; repeated-flow episodes; candidates that moved Watching → Validated; opportunity-score quintiles; and winners/losers matched by market/sector regime. The same anti-self-deception rule applies: visual examples such as a large historical run are case studies, not evidence until the pattern is tested across the full recorded candidate set.

## Point-in-time rendering rules

- Charts must load data from named snapshot/universe/model versions rather than silently querying latest values.

- Official historical charts use only information available at the corresponding cutoff; future labels/outcomes may be added only as clearly separated evaluation layers.

- Live-preview charts must be visibly marked provisional and should show the last official EOD signal for comparison.

- Every exported figure should embed or accompany the date range, snapshot version, universe version when relevant, feature version, regime/opportunity model version, and code/experiment revision.

## Suggested command surface

Visualization should be reproducible from the CLI rather than existing only inside a notebook. Example commands:

- marketlab chart regime --symbol SPY --start 2024-01-01 --model regime_v3

- marketlab chart components --date 2026-08-24

- marketlab chart event-study --transition neutral,cautious --horizon 65

- marketlab chart forward-buckets --symbol QQQ --horizons 40,50,65

- marketlab opportunity show --symbol MU --date 2026-08-24

- marketlab chart opportunity --symbol MU --start 2026-01-01

- marketlab opportunity candidates --date 2026-08-24 --state validated,active_setup

- marketlab chart opportunity-buckets --horizons 20,40,65,126

- marketlab report --date 2026-08-24 --with-charts

This architecture makes visual research cheap during exploration while keeping the final claims auditable. A visual relationship is treated as a hypothesis generator; the forward-return and drawdown analyses decide whether the relationship survives statistical testing.

# 16. Coding-Agent Implementation Contract

Treat this document as the architectural source of truth unless a later design version explicitly supersedes it. When implementing:

- Implement the core research loop before support infrastructure. A feature is not done because it stores an artifact; it is done when it produces, scores, explains, or evaluates a market/regime/candidate observation.
- Keep canonical numerical calculations deterministic and testable. Do not let an LLM/agent silently modify a regime score, historical snapshot, or backtest result.
- Preserve point-in-time correctness. Every official signal must be reproducible from a named frozen snapshot and explicit feature/model/policy versions.
- Keep source observations reproducible, but do not equate reproducibility with copying every interface response. Store the smallest durable observations needed to support a research claim; keep raw payloads only when they are necessary for debugging, audit, or parser replay.
- Keep active research data out of Git. Only code, schemas, configuration, small test fixtures, and documentation belong in the repository.
- Hide agent implementation details behind a `ResearchAgent` interface so the v0 Codex CLI backend can later be replaced by an API backend.
- Treat agent output as bounded structured research input. Validate before persistence.
- Treat Bulltard as a candidate generator/feature source, never as the final decision authority. Persist all extracted candidates and rejected candidates needed for unbiased evaluation.
- Keep Bulltard acquisition deterministic and targeted: bootstrap each day from the original signed recap link, use a short-lived same-session HTTP client, retrieve named views needed by the current research question, and use Playwright only as an explicit fallback.
- Treat signed recap URLs and scanner access tokens as temporary capabilities: keep them out of Git and public reports, never synthesize or modify them, and avoid building credential-management features before they are needed.
- Keep hard single-name eligibility gates (fundamental viability and options liquidity) separate from soft opportunity ranking features.
- Model candidate lifecycle transitions as immutable episodes with point-in-time evidence; do not rewrite old states after outcomes are known.
- Prefer simple, interpretable models first. Add features only when they show incremental out-of-sample value.
- Make every important chart reproducible from a CLI command and versioned inputs; notebooks are exploratory, not the only implementation path.
- Never execute trades. The system produces research, exposure guidance, and portfolio-policy recommendations only.
- Add tests around the behavior being used now. Broaden tests for snapshot timing, look-ahead prevention, point-in-time universe membership, option-liquidity gating, candidate lifecycle transitions, feature calculation, model versioning, and persistence as those components enter the active research loop.

## Suggested first repository skeleton

```text
marketlab/
├── pyproject.toml
├── README.md
├── DESIGN.md
├── AGENTS.md
├── .gitignore
├── src/marketlab/
│   ├── cli.py
│   ├── config.py
│   ├── ingest/
│   ├── snapshots/
│   ├── features/
│   ├── regime/
│   ├── portfolio/
│   ├── universe/
│   ├── opportunity/
│   ├── options/
│   ├── fundamentals/
│   ├── bulltard/
│   │   ├── recaps.py        # signed-link extraction from saved recaps
│   │   ├── ingest.py        # targeted Bulltard view retrieval
│   │   ├── parsers.py       # deterministic normalization into observation rows
│   │   └── models.py        # Bulltard signal/candidate records
│   ├── agents/
│   ├── backtest/
│   ├── visualization/
│   └── storage/
├── tests/
├── notebooks/
├── migrations/
├── data/            # gitignored except tiny fixtures
└── reports/         # usually gitignored/generated
```

# 17. Near-Term Implementation Decisions

- Define the v0 large-cap eligible universe and keep its thresholds configurable; prefer a conservative liquid universe over broad coverage.

- Define the first option-liquidity score/gate: underlying dollar volume, option volume/OI, bid/ask quality, and usable multi-month expirations.

- Implement `marketlab bulltard ingest --date YYYY-MM-DD --view ranked-option-trades path/to/recap.html` using `httpx.Client(follow_redirects=True)`: bootstrap from the original signed email link, retrieve one useful view, parse structured candidate rows, and write local observations.

- Add tests for the actual first ingest path: recap link extraction, redirect/session continuity if required, parser behavior on a saved fixture, output row schema, and visible failure when the signed link is expired or the expected table is absent.

- Define only the Bulltard signal fields required by the first ingested view. Expand the taxonomy after multiple real examples show repeated structure.

- Choose the first canonical regime visualization: SPY price + regime shading + continuous score + component panels.

- Choose the first canonical single-name visualization: price/relative strength + Bulltard events/lifecycle markers + opportunity-family scores + option-liquidity panel.

- Define the first local directory/backup convention and ensure all generated data paths are gitignored except tiny test fixtures.

- Implement a ResearchAgent interface with a Codex CLI backend, but keep agent-derived outputs outside the canonical numerical signal until their value is demonstrated.

- Decide which Bulltard observation fields are legally/contractually appropriate to store locally for personal research before relying on them as a historical dataset.
