# Market Regime & Large-Cap Opportunity Research System

**High-Level Design - Version 1.0**
**Status:** Two-engine, local-first research loop with Gmail recap acquisition, reproducible snapshots, rare-action regime policy, and rebuildable DuckDB query state
**Primary audience:** coding/research agents and the human researcher

> **Purpose:** Build a durable, testable research process that (1) sizes marginal market exposure while maintaining a permanent long-term core in SPY/QQQ and (2) identifies unusually attractive multi-month opportunities in large, fundamentally viable, options-liquid individual stocks.

| **Core philosophy:** Stay invested and do nothing most days. The highest-value signal is not a daily BUY/SELL label. It is a rare exposure-control alert: when the market is stretched enough to raise cash or overwrite upside, and when panic/bloodbath conditions are washed out enough to redeploy cash or add defined convex exposure. |
|-------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

| **Layer**      | **Role**                                                         | **Typical instruments**                                          |
|----------------|------------------------------------------------------------------|------------------------------------------------------------------|
| Core           | Permanent long-term compounding exposure                         | SPY / QQQ shares or equivalent index exposure                    |
| Beta amplifier | Raise effective exposure when expected reward/risk is attractive | Long-dated calls / LEAPs                                         |
| Single-name tactical | Deploy bounded marginal risk into validated large-cap opportunities | Shares, LEAPs, short puts/spreads, risk reversals as permitted    |
| Dry powder     | Preserve flexibility and reduce portfolio beta                   | Cash / cash equivalents                                          |
| Overlay        | Monetize or reshape exposure around the core                     | Covered calls, cash-secured puts, defined-risk option structures |

This document stays at the system-design level while including the implementation architecture needed for reproducibility: Python orchestration, bounded agents, immutable time snapshots, local-first storage, an incremental Codex-to-API runtime path, and a visualization layer designed for both exploratory research and auditable backtests. The research system has two coordinated engines: a SPY/QQQ market-regime engine and a large-cap single-name opportunity engine.

The market-regime engine is the current implementation priority. Bulltard is useful candidate-generation evidence for the single-name engine, but it is not the source of truth for overall market regime. Market regime should be built primarily from independent market inputs such as index price structure, volatility structure, breadth, credit/liquidity, and sentiment/positioning.

## Practical Operating Objective

The portfolio maintains a permanent SPY/QQQ-oriented core. The regime system controls only the marginal tactical layer around that core. Most daily outputs should recommend no portfolio move. Its most useful output should identify two actionable zones:

| **Zone** | **Question** | **Typical bounded response** |
|---|---|---|
| Stretched / de-risk | Has upside become crowded or overextended while downside risk is rising? | Keep the core, scale down tactical beta, rebuild cash, sell covered calls against part of existing exposure, and avoid adding fresh long calls unless the setup is exceptional. |
| Bloodbath / re-risk | Has a broad selloff likely moved forward reward/risk into a favorable zone? | Keep the core, deploy cash in tranches, consider 60-90 DTE calls or call spreads, and consider cash-secured puts or defined-risk put spreads when assignment/risk budget is acceptable. |
| Normal / mixed | Is the evidence too balanced to justify a strong posture change? | Stay near neutral policy beta, preserve flexibility, and let single-name opportunities compete for only a bounded sleeve. |

These are research-policy states, not automatic trade orders. The system should make the posture decision inspectable; execution remains manual and must respect option liquidity, tax, assignment, and position-size constraints.

## Decision Cadence

The system should be biased toward inactivity. The baseline daily answer is "maintain current posture" unless evidence is strong enough to move the tactical sleeve.

| **Cadence state** | **Meaning** | **Expected action** |
|---|---|---|
| No change | Evidence does not justify changing tactical exposure. | Keep core and tactical posture roughly unchanged; keep observing. |
| Scale down / protect | Market looks near a local top or stretched enough that forward reward/risk is unattractive. | Preserve the core, reduce tactical beta, raise cash, and/or sell covered calls against part of existing exposure. |
| Scale up / redeploy | Market has suffered a major correction/bloodbath and evidence suggests forced selling is exhausting. | Preserve the core, deploy cash in tranches, and consider 60-90 DTE calls/call spreads or bounded put underwriting. |

The design standard is not "emit an opinion every day." It is "stay quiet most days, but be useful at the tails."

## Implementation Bias

Build the shortest end-to-end loop that can teach us whether the system helps make better market decisions. A new module, schema, capture layer, crawler, cache, or abstraction is justified only when it directly supports one of these near-term outcomes:

- Produce a current market-regime view.
- Produce a structured large-cap candidate list.
- Compare candidates or regimes to forward returns and drawdowns.
- Preserve exactly the source observation needed to reproduce a specific claim.

Do not build infrastructure just because the eventual system might need it. Start with one useful path, measure what it produces, then generalize only around repeated pressure from real research tasks.

# 1. Problem Statement

A long-term investor who intends to remain structurally long SPY/QQQ faces two recurring tactical questions: **when is the market close enough to a tactical top or bottom to justify changing marginal exposure, and where should that marginal risk be deployed when action is justified?** The first question is handled by a repeatable evidence-based market-regime signal. The second is handled by a large-cap opportunity engine focused on catching multi-month re-ratings, cyclical accelerations, and catalyst/momentum inflections in liquid names rather than speculative small-cap lottery tickets.

| **What success looks like:** The system does not need to forecast an exact market or stock price. It should (1) separate future SPY/QQQ 2-3 month return/drawdown distributions well enough to improve exposure sizing and (2) identify a subset of large-cap candidates whose multi-month forward return/asymmetry is materially better than comparable names and benchmarks after realistic implementation costs. |
|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

## Primary decisions the system should inform

- How much incremental beta should be carried above or below the neutral portfolio target?

- How much of the cash reserve should remain undeployed versus be used to add exposure?

- Is the market stretched enough to start scaling down tactical exposure, rebuilding cash, or selling covered calls against part of the core?

- Is the market washed out enough after a broad selloff to start scaling up through cash deployment, 60-90 DTE calls/call spreads, or put underwriting?

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

## Engine separation and current priority

The two engines answer different questions and should not be blended prematurely:

| Engine | Primary question | Primary evidence | Current priority |
|---|---|---|---|
| Market regime | Is the market stretched enough to scale down/protect, washed out enough to scale up/redeploy, or quiet enough to do nothing? | Trend, VIX/VVIX/volatility term structure, breadth, credit/liquidity, sentiment/positioning | Primary near-term engine |
| Single-name opportunity | Which large, liquid stocks have multi-month asymmetric opportunities worth using the tactical risk budget on? | Bulltard signals, price/relative strength, fundamentals, catalysts, options liquidity | Secondary until regime evidence is credible |

Portfolio policy exists as a bounded v0 research proxy, but it remains provisional until the market-regime engine has longer-history calibration and real portfolio accounting. The single-name engine can continue collecting candidates in parallel, but it should not drive aggregate market exposure.

## Engine Interaction

The two engines should help each other without collapsing into one score.

| **Interaction** | **Rule** |
|---|---|
| Regime controls sizing | A strong single-name setup can be smaller, delayed, or expressed more conservatively when the market is stretched or deteriorating. |
| Regime controls aggressiveness | In a validated bloodbath/re-risk state, the same high-quality setup may justify faster cash deployment, 60-90 DTE calls/call spreads, or put underwriting. |
| Single-name tape informs context | A cluster of high-quality large-cap opportunities after a broad selloff can support a re-risk watch state; a lack of clean setups during a stretched tape can reinforce patience. |
| Subscription evidence remains bounded | Bulltard can generate candidates and may provide an external market overlay, but it must not override independent regime evidence without measured outcome support. |
| Outcomes are joint | Candidate outcomes should be evaluated by both opportunity features and the market-regime state active at discovery/validation. |

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

The current operating path is an explicitly invoked CLI workflow, not an automated trading service. Once ingestion and snapshot semantics are stable over repeated use, selected collection jobs may be scheduled. A typical deterministic run is: refresh market sources → compute shared features and market-signal snapshots → score SPY/QQQ regime → fetch the Bulltard recap from Gmail or a saved artifact → extract/validate single-name candidates → calculate portfolio posture/risk budget → persist → render report/chart outputs.

| Mode                 | Typical invocation                                      | Behavior                                                                                       |
|----------------------|---------------------------------------------------------|------------------------------------------------------------------------------------------------|
| Routine daily run    | marketlab daily                                         | Refresh local observations, write current snapshots, fetch the recap when Gmail is authorized, render report/chart output, and rebuild DuckDB. |
| Historical/debug run | marketlab daily --date YYYY-MM-DD                       | Reproduce or rebuild a specific date from local/fetched sources using explicit snapshot identifiers where needed. |
| Focused research     | marketlab regime snapshot / bulltard daily / policy outcomes | Run one subsystem for backfills, debugging, or evidence review. |
| Scheduled ingestion  | cron → marketlab daily                                  | Optional later trigger after the workflow is stable; no autonomous trade execution. |

## Suggested initial storage

A lightweight local research stack is the default: JSON/JSONL snapshots are the durable source of truth, DuckDB is a rebuildable query layer, and Parquet exports are optional. Raw observations should be immutable; normalized tables and feature tables should reference the source snapshot and version that produced them. Suggested logical tables include market_prices, volatility, breadth, macro, sentiment, security_master, universe_membership, security_fundamentals, option_liquidity, daily_features, regime_snapshots, single_name_features, opportunity_snapshots, candidate_state_transitions, bulltard_recaps, bulltard_signals, portfolio_snapshots, research_experiments, model_versions, and signal_outcomes.

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

The regime label alone is insufficient. A strong index trend can be healthy or dangerously stretched; a weak market can be deteriorating or washed out. The market-regime engine should therefore produce three related but separate views:

| **View** | **Purpose** | **Portfolio question** |
|---|---|---|
| Directional regime | Summarize whether the current tape is risk-on, neutral, or risk-off. | Should marginal beta be above, near, or below neutral? |
| Stretch / de-risk pressure | Detect overextension, complacency, narrowing participation, or early credit/liquidity deterioration. | Should the portfolio raise cash, sell calls, or reduce new long-delta additions? |
| Washout / re-risk pressure | Detect forced-selling conditions, panic, broad capitulation, and stabilization after a selloff. | Should the portfolio start redeploying cash, adding convex upside, or underwriting lower entries? |

The stretch and washout views should be calibrated as rare tail alerts. A normal `risk_on` reading is not automatically a top warning, and a normal `risk_off` reading is not automatically a bottom signal.

Because these inputs use different units, the regime engine should not combine them by raw thresholds alone. Each feature should first be projected into a common point-in-time pressure space using its own historical distribution. A practical v0 approach is rolling percentile normalization:

- Convert each raw feature into a percentile versus the trailing as-of sample that would have been known on that date.
- Map the percentile into stretch pressure, washout pressure, or both based on the feature's economic meaning.
- Aggregate within each signal family first, then aggregate family scores so one dense family does not overwhelm sparse but important evidence.
- Use top pressure percentiles for calibration/backtests, while keeping any hard-threshold action classifier as a transparent baseline comparator rather than the final policy.

| **Family**              | **Candidate inputs**                                                               | **Question answered**                                                           |
|-------------------------|------------------------------------------------------------------------------------|---------------------------------------------------------------------------------|
| Trend / structure       | Price vs. moving averages, slope, distance from highs, term trend, momentum        | Is the market structurally advancing or deteriorating?                          |
| Volatility              | VIX, VVIX, term structure, realized vs. implied vol, vol-of-vol                    | Is risk being cheaply or expensively priced, and is volatility stress building? |
| Breadth                 | Advance/decline, % above key averages, new highs/lows, equal-weight vs. cap-weight | Is participation confirming the index?                                          |
| Liquidity / credit      | Credit spreads, rates, financial conditions, dollar, liquidity proxies             | Is the macro financing backdrop supportive or restrictive?                      |
| Sentiment / positioning | Fear/greed, put/call, surveys, flows, CTA/positioning proxies, social sentiment    | Are investors euphoric, fearful, crowded, or under-positioned?                  |
| External overlay        | Discretionary market commentary, app-level statistics, recurring option-flow patterns | Does outside research confirm or contradict the independent regime model? |

## Market-Regime Hypotheses To Study

These are research candidates, not trusted rules. Each one must be written as a dated
point-in-time signal, replayed against forward SPY/QQQ returns and drawdowns, and either kept,
reweighted, or retired.

- Volatility interaction:
  - `VIX high + VVIX high`: panic is still expanding; avoid treating the first selloff as a durable bottom.
  - `VIX high + VVIX falling/contained`: headline fear is elevated, but volatility-of-volatility may be stabilizing; candidate re-risk signal if credit/liquidity is not broken and breadth stops deteriorating.
  - `VIX low + VVIX low + stretched trend`: complacency plus price extension; candidate scale-down/protect signal.
  - `VIX low + VVIX rising`: quiet index tape with rising vol-of-vol; candidate early-warning signal.

- Breadth and participation:
  - Current proxies are `RSP/SPY` and `IWM/SPY`, which ask whether equal-weight large caps and small caps are confirming the cap-weighted index.
  - Stronger candidates include percentage of stocks above 50d/200d moving averages, new highs minus new lows, advance/decline lines, and McClellan-style breadth/volume summation.
  - Breadth should affect confidence and stretch/washout pressure more than the headline directional label. A narrow uptrend is not automatically bearish, but it should reduce confidence and raise de-risk pressure.

- Sentiment and positioning:
  - NAAIM Exposure Index: active manager equity exposure; useful for testing whether professional managers are crowded long, de-risked, or rapidly changing exposure.
  - AAII Sentiment Survey: individual-investor bullish/neutral/bearish expectations; useful mainly as a contrarian input at extremes.
  - AAII Asset Allocation Survey: individual-investor stock/bond/cash positioning; useful because actual allocation can diverge from stated sentiment.
  - CNN Fear & Greed Index: broad composite sentiment/risk-appetite gauge. Treat it carefully because it already includes inputs similar to momentum, breadth, put/call, junk-bond demand, VIX, and stock/bond relative performance.
  - Put/call ratios, fund-flow data, CTA positioning, and dealer/gamma positioning are candidates only if the source has clear historical availability and licensing.

- Policy-modeling theory:
  - Keep the current hard-threshold policy as the baseline comparator because it is simple, inspectable, and hard to overfit accidentally.
  - Study smoother alternatives only if the threshold model proves too jumpy or leaves obvious forward-return/drawdown separation unused.
  - A better model does not have to be a separate forecast layer. It could be a small scored-state model, percentile-bucket lookup, or regularized utility score that directly maps evidence to `maintain`, `protect`, or `redeploy`.
  - Any replacement must reduce operational ambiguity: fewer arbitrary knobs, clearer state transitions, lower churn, and better walk-forward outcomes after realistic friction.
  - If a model needs many hand-tuned parameters to beat the threshold baseline, reject it.

- Admission standard:
  - Do not add a signal just because it is famous. Add it only when source availability, update lag, history length, and licensing are clear enough for replay.
  - Prefer raw component series over opaque composite scores when possible, because raw series make double-counting and threshold drift easier to audit.
  - Every new family must be tested both alone and in combination with current regime state, especially during disagreement regimes such as strong trend with weakening breadth or high VIX with improving VVIX.

## Regime output

Avoid a binary BUY/SELL output. A useful daily snapshot should look more like:

| **Field**                   | **Example interpretation**                                                              |
|-----------------------------|-----------------------------------------------------------------------------------------|
| Regime score                | -2 = risk-off, -1 = cautious, 0 = neutral, +1 = constructive, +2 = risk-on              |
| Stretch / de-risk score     | Whether conditions argue for raising cash, trimming tactical beta, or selling calls     |
| Washout / re-risk score     | Whether conditions argue for redeploying cash or adding bounded upside exposure         |
| Confidence                  | How aligned the feature families are and how familiar the current state is historically |
| Forward return distribution | Historical distribution for SPY/QQQ over roughly 40-65 trading days                     |
| Drawdown distribution       | Expected/max adverse excursion under comparable regimes                                 |
| Contradictions              | Important families that disagree with the composite                                     |
| Change flag                 | Whether the regime is stable, improving, or deteriorating                               |
| Policy posture              | Suggested marginal beta/cash/overlay posture inside predefined risk limits              |
| Action state                | `no_change`, `scale_down_protect`, or `scale_up_redeploy`                               |

The output should prefer calibrated uncertainty over false precision. "Moderately cautious, 62% confidence" is more useful than "QQQ will fall 7.3%."

# 6. Translation From Signal to Portfolio Posture

The highest-value design decision is the mapping layer between a statistical regime and an actual portfolio action. This mapping should be explicit, bounded, and backtested separately from the signal itself.

The mapping layer should be designed around marginal actions rather than whole-portfolio liquidation. In practice, the system should help answer:

- When to keep the core but begin scaling down tactical exposure.
- When to rebuild or preserve cash.
- When to monetize stretched upside by selling covered calls against part of existing exposure.
- When to start scaling back up after a bloodbath.
- When 60-90 DTE calls/call spreads offer better reward/risk than shares for tactical upside.
- When cash-secured puts or defined-risk put spreads are acceptable ways to underwrite lower entries.

| **Regime**      | **Portfolio intent**             | **Illustrative posture (not final rules)**                                                    |
|-----------------|----------------------------------|-----------------------------------------------------------------------------------------------|
| Strong risk-on  | Carry modestly more beta         | Deploy some dry powder; favor maintaining/adding long delta; lighter call overwrite           |
| Constructive    | Slightly above neutral           | Normal core + measured LEAP exposure; selective put-selling on pullbacks                      |
| Neutral / mixed | Stay near policy beta            | Preserve flexibility; avoid forcing directional options trades                                |
| Cautious        | Slightly below neutral           | Preserve more cash; monetize some upside; demand better put-sale entry                        |
| Strong risk-off | Defend tactical sleeve, not core | Keep core invested; lower incremental delta; heavier but bounded overwrite; retain dry powder |

| **Design constraint:** The tactical layer must have hard exposure limits. A model failure should be able to hurt performance, but it should not be able to destroy the long-term portfolio thesis. |
|----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

A stretched market is not the same as a bearish market. The system may say "trend still risk-on, but stretch pressure is high," which should map to protecting gains and slowing new risk additions rather than shorting the market. Likewise, a bloodbath/re-risk alert is not a claim that the exact bottom is known; it should map to staged deployment and bounded option risk.

Most days, portfolio posture should remain unchanged. Policy should include hysteresis, minimum-change thresholds, and cooldowns so the engine does not create activity merely because data updates daily.

# 7. Bulltard Research Module

The subscription should be treated as a structured research source rather than a stream of ephemeral trade ideas. Its primary role is candidate generation for the single-name opportunity engine. If broad market commentary is present, it may be captured later as an external discretionary overlay, but it must not be the foundation of the market-regime engine. The objective is to learn which parts of the service contain persistent information and which are noise; a mention or flow event does not automatically pass our own eligibility or validation gates.

## Bulltard observations to ingest

- Broad market / SPY commentary and key technical levels when present, as an external overlay only.

- Changes to the author's open book, including adds, closes, sizing language, and stated thesis.

- Trades of interest: ticker, option structure, expiry, strike, flow size, technical context, catalyst, and alternative implementation.

- Scanner / momentum signals and the daily database snapshot.

- Repeated signals across multiple days (for example, recurrent put-selling or repeated call accumulation).

The goal is not to archive the Bulltard app or mirror its database. The app is an interface to a subscription data source. MarketLab should retrieve the specific views needed for a research question, parse them into structured observations, and store only the observations and provenance needed to reproduce our own analysis.

Because the daily database/link may be ephemeral, **recap acquisition and data ingestion are automated even though trading remains manual**. The automation boundary is ingest/extract only: use the recap link while it is valid, pull a narrow set of relevant rows, and make those rows available for testing candidate quality. There is no broker integration or autonomous order path.

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
Gmail recap fetched through read-only OAuth, or an equivalent saved recap artifact
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

The v0 local layout is:

```text
data/inbox/bulltard/
└── recap-2026-08-24.html        # Gmail-cached or manually saved recap input, gitignored

data/observations/bulltard/
└── ranked_option_trades/
    └── 2026-08-24.jsonl         # parsed rows + minimal provenance, gitignored
```

The local DuckDB database is a rebuildable query index over these files, not the canonical source of truth. Optional Parquet exports are for backup/interchange.

### Ingest command contract

The lower-level ingest command remains a boring, repeatable fallback for one saved recap:

```bash
marketlab bulltard ingest --date 2026-08-24 --view ranked-option-trades data/inbox/bulltard/recap-2026-08-24.html
```

Its responsibility is only to: read the requested recap, extract the signed link, establish daily access, retrieve one named view, parse rows, write structured observations, and report what it produced. The routine path is `marketlab daily`, which handles Gmail acquisition before calling the Bulltard workflow when a recap is available. A failed ingest should fail visibly and should not be filled from a later date.

## Research questions

| **Question**                                                                                              | **Why it matters**                                                          |
|-----------------------------------------------------------------------------------------------------------|-----------------------------------------------------------------------------|
| Do repeated large put sales predict better forward returns or merely identify lower desired entry levels? | Separates useful underwriting information from false bullish interpretation |
| Are ideas stronger when technical momentum agrees with option flow?                                       | Tests signal combination rather than anecdotes                              |
| Do open-book, high-conviction positions outperform "trades of interest"?                                  | Identifies where the author's actual edge may reside                        |
| Which implementation works best: common stock, long calls, risk reversals, or short puts?                 | Separates thesis quality from instrument selection                          |
| Does his broad market caution/optimism add information to our independent regime model?                   | Potential external ensemble feature                                         |

# 8. Large-Cap Single-Name Opportunity Engine

The single-name engine is designed to catch substantial multi-month moves in established, liquid companies: fundamental/catalyst re-ratings, cyclical accelerations, and sustained momentum/positioning inflections. It is **not** a general stock picker, not a daily trading engine, and not optimized for finding tiny speculative names. The target is to participate in a meaningful middle portion of a 3-9 month move rather than identify the exact bottom or top.

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

## Current v0 candidate strategy

The current implementation is a conservative research funnel:

- Capture Bulltard evidence with provenance from the recap, ranked option-trades view, Trades Of Interest section, and selected ticker-detail pages.
- Rank source attention before validation: Trades Of Interest names are reviewed first, then ranked option-trade names using score, premium, and available detail rows.
- Validate every candidate against independent market data instead of trusting the subscription signal. The v0 checks are underlying dollar-volume liquidity, recent absolute return, relative strength versus SPY/QQQ, 50-day trend position, and recent drawdown.
- Classify candidates as `confirm`, `watch`, or `avoid`. `confirm` means price action and liquidity are aligned enough for research; `watch` means the evidence is incomplete or mixed; `avoid` means missing data, thin trading, or weak trend/relative strength fails basic gates.
- Apply market-regime context after validation. Regime changes the attention and risk budget for a candidate, not the independent candidate label itself: protective regimes reduce or defer single-name risk, redeploy regimes make confirmed names more actionable for research, and neutral regimes keep them on a normal research/watch path.
- Store validation snapshots and later replay forward outcomes so the system can learn whether Bulltard evidence, independent validation, and regime context actually improve candidate quality.
- Treat each candidate/date pair as a point-in-time episode. The first learning target is 40- and 65-trading-day outcome quality, roughly the 60-90 calendar-day window the strategy cares about.
- Compare cohorts before inventing a score: put selling versus call buying, bullish versus bearish ranked side, Trades Of Interest versus ranked-only, repeated/detail-backed flow versus no-detail names, `confirm` versus `watch`, and each of those under the market regime active at signal time.

This is not yet a buy/no-buy opportunity engine. It is the data collection and triage layer that should make the later lifecycle, thesis, invalidation, options-liquidity, and instrument-selection work testable.

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
| 1. Market-regime foundation | Build point-in-time SPY/QQQ trend, realized volatility, basic VIX, breadth proxy, and credit proxy snapshots | We can create and replay daily regime snapshots against forward SPY/QQQ returns and drawdowns |
| 2. Market-regime signal expansion | Add independent volatility-structure, sentiment/positioning, stronger breadth, and liquidity/credit observations | We can inspect family-level signals and compare their forward outcome separation |
| 3. Regime calibration | Backtest family scores, disagreement states, transitions, stretched/de-risk states, and bloodbath/re-risk states before mapping them to portfolio policy | The regime model either separates forward risk/reward out of sample or explicitly records "no edge" |
| 4. Single-name candidate pipeline | Ingest Bulltard candidates and validate them with independent price, liquidity, fundamentals, catalysts, and outcomes | We can measure whether candidate subsets outperform comparable large-cap names and benchmarks |
| 5. Portfolio policy | Map calibrated regime to bounded beta/cash/overlay posture and combine with validated single-name opportunities | Policy adds risk-adjusted value vs. fixed-policy benchmark |
| 6. Visualization and reporting | Render regime components, disagreements, transitions, candidates, and outcomes from versioned inputs | Important charts and reports are reproducible from CLI commands |
| 7. Iterate | Periodic review, feature retirement, parameter freezes, candidate/outcome monitoring | Stable research cadence without constant curve-fitting |

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

- What exact action bands should stretched and bloodbath/re-risk states map to: cash reserve changes, covered-call overwrite percentage, 60-90 DTE call budget, and short-put/put-spread risk budget?

- What historical period should be considered representative enough for the first backtest?

- How much historical Bulltard source content is still retrievable, given that the daily signed access link is explicitly ephemeral?

- What initial large-cap universe should be used (market-cap floor, index membership, or a curated liquid list), and how should historical universe membership be reconstructed?

- What option-liquidity thresholds define a tradable candidate for shares, multi-month options, and LEAP-based expressions?

- What constitutes a hard fundamental viability failure versus a temporary cyclical/turnaround weakness?

- Should the single-name opportunity horizon default to 3-6 months, or support multiple thesis classes up to roughly 9-12 months?

- Which independent fundamental/estimate-revision data sources are practical and point-in-time enough for v0?

| Recommended immediate next step: run the fresh daily loop for several real sessions, then calibrate rare-action thresholds and policy bands against longer saved history before adding new signal families. |
|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|

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

- data/inbox/: Gmail-cached or manually supplied inputs such as Bulltard recaps. Preserve acquisition/availability timestamps when known.

- data/observations/: structured rows ingested from market data, option-liquidity sources, fundamentals, and external research signals.

- data/debug/: optional raw payload cache for parser replay or troubleshooting. This is not the main research product.

- data/snapshots/: named prior-close, intraday-preview, and official-EOD snapshots, including eligible-universe and opportunity state.

- marketlab.duckdb: rebuildable local metadata/query database generated from `data/`; periodically checkpoint or export only after the source files are worth preserving.

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

## Visualization stack

The current v0 implementation uses self-contained HTML/SVG emitted by CLI commands because it is easy to diff, test, and archive locally. Plotly, Matplotlib, and notebooks remain useful expansion options when interactive exploration or publication-quality static figures become the bottleneck.

| **Need**                          | **Tool**                                             | **Role**                                                                                            |
|-----------------------------------|------------------------------------------------------|-----------------------------------------------------------------------------------------------------|
| Current reproducible reports      | Self-contained HTML/SVG                              | CLI-generated artifacts for daily inspection, tests, and local archiving.                           |
| Interactive exploration           | Plotly                                               | Later zoom, hover, synchronized time axes, regime shading, event markers, and local HTML output.    |
| Canonical/static research figures | Matplotlib                                           | Later experiment artifacts and publication-quality snapshots.                                      |
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

## Current and Future Command Surface

Visualization should be reproducible from the CLI rather than existing only inside a notebook. Example commands:

- marketlab daily

- marketlab daily --date 2026-08-24

- marketlab chart regime --start 2026-08-24 --end 2026-08-24

- marketlab chart opportunity --date 2026-08-24 MU

- marketlab report daily --date 2026-08-24

- marketlab regime pressure-outcomes --start 2025-01-02 --end 2026-05-22 --horizons 20,40,65

- marketlab policy outcomes --start 2025-01-02 --end 2026-05-22 --horizons 20,40,65

- marketlab store query "select source_date, policy_state, marginal_beta_target from policy_snapshots order by source_date desc limit 10"

Future command surfaces such as event studies, forward-bucket charts, and lifecycle-specific opportunity views should be added only after the underlying measurements are stable enough to justify them.

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

## Historical first repository skeleton

This skeleton is retained as design history. The current implementation uses a flatter package layout while v0 contracts are still moving; move to this deeper layout only when the module boundaries become stable enough to justify it.

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

- Keep the two-engine split explicit in code and documentation: `regime` owns aggregate market context, while `bulltard` and later `opportunity` own single-name candidate evidence.

- Keep hardening the market-signal snapshot layer as the evidence boundary for regime and policy. The current v0 consumes saved/generated signal rows; next steps are longer-history calibration, measured source expansion, and a standalone signal-production command only if the regime workflow becomes too coupled.

- Continue Market Signal Expansion only where source access is practical and measured outcome replay improves:
  - VIX term structure and realized-vs-implied volatility where the data source is reliable.
  - Fear/greed-style sentiment or equivalent risk-appetite observations from a stable source-specific importer.
  - Put/call or positioning proxies only after source semantics are clear.

- Strengthen breadth and credit/liquidity after the first policy loop reveals a measured weakness. Prefer one robust signal per family over many correlated variants.

- Keep `regime snapshot` showing family-level evidence, contradictions, and missing-source status. A missing external data family should lower confidence, not silently force a bullish or bearish conclusion.

- Replay each added market family and every policy revision against forward SPY/QQQ returns and drawdowns. Keep a feature only if it improves out-of-sample separation, calibration, contradiction handling, or interpretability.

- Leave Bulltard work focused on candidate generation and measured single-name outcomes. The portfolio policy consumes candidate context, but Bulltard must not drive aggregate market exposure.

- Continue extending the canonical regime/policy visualization: keep SPY/QQQ price, regime/action shading, stretch/washout pressure, component panels, and policy state visible; add real current portfolio beta/cash once portfolio accounting exists.

- Extend the first canonical single-name visualization after the opportunity engine exists: add lifecycle markers, opportunity-family scores, and option-liquidity panels beyond the current candidate-validation view.

- Keep JSON/JSONL snapshots as the durable local source of truth and DuckDB/Parquet as query/export layers. Ensure generated data paths remain gitignored except tiny test fixtures.

- Implement a ResearchAgent interface with a Codex CLI backend, but keep agent-derived outputs outside the canonical numerical signal until their value is demonstrated.

- Decide which Bulltard observation fields are legally/contractually appropriate to store locally for personal research before relying on them as a historical dataset.
