# MarketLab Algorithm Design

**Status:** pre-debut research design, current as of September 2026.

- [MarketLab Algorithm Design](#marketlab-algorithm-design)
  - [Portfolio Objective](#portfolio-objective)
  - [Non-Goals](#non-goals)
  - [Market-Regime Views](#market-regime-views)
  - [Evidence Families](#evidence-families)
  - [Current Market-Regime Model](#current-market-regime-model)
  - [Setup, Confirmation, Action](#setup-confirmation-action)
  - [Research Observations and Proposals](#research-observations-and-proposals)
    - [Data-Driven Protect Review](#data-driven-protect-review)
    - [Problem: Stretch Is Not Bearish By Itself](#problem-stretch-is-not-bearish-by-itself)
    - [Problem: Protect Currently Mixes Different States](#problem-protect-currently-mixes-different-states)
    - [Problem: Geometric Compensation Hides Weak Setup](#problem-geometric-compensation-hides-weak-setup)
    - [Problem: Same-Day Setup And Confirmation Are Too Rigid](#problem-same-day-setup-and-confirmation-are-too-rigid)
    - [Problem: Event Volatility Can Masquerade As Deterioration](#problem-event-volatility-can-masquerade-as-deterioration)
    - [Problem: Washout Is A Setup, Not An Automatic Buy](#problem-washout-is-a-setup-not-an-automatic-buy)
    - [Problem: Shock Windows Distort Ordinary Correction Research](#problem-shock-windows-distort-ordinary-correction-research)
    - [Problem: Action Events Are Not Portfolio Posture](#problem-action-events-are-not-portfolio-posture)
  - [Outcome Research](#outcome-research)
  - [Portfolio Translation](#portfolio-translation)
  - [Bulltard and Single-Name Research](#bulltard-and-single-name-research)
  - [Backtesting Standards](#backtesting-standards)
  - [Near-Term Algorithm Backlog](#near-term-algorithm-backlog)

MarketLab is a local research system for two related alpha questions:

1. How should marginal SPY/QQQ exposure be managed around a permanent long-term core?
2. Which large, liquid single-name opportunities deserve research attention when the market
   regime allows tactical risk?

This document describes the research model. It is not a trading policy and does not define
implementation storage or CLI behavior. See [IMPLEMENTATION_DESIGN.md](./IMPLEMENTATION_DESIGN.md)
for that.

## Portfolio Objective

The portfolio keeps a permanent SPY/QQQ-oriented core. MarketLab controls only the marginal
tactical layer around that core.

| Layer | Role | Typical instruments |
| --- | --- | --- |
| Core | Permanent compounding exposure | SPY / QQQ shares or equivalent exposure |
| Beta amplifier | Add convex or higher-beta exposure when reward/risk is attractive | LEAPs, long calls, call spreads |
| Single-name tactical | Bounded risk in validated large-cap opportunities | Shares, LEAPs, short puts/spreads, risk reversals |
| Dry powder | Preserve optionality and reduce beta | Cash / cash equivalents |
| Overlay | Monetize or reshape core exposure | Covered calls, cash-secured puts, defined-risk options |

The system should be biased toward inactivity. Most days should produce `no_change`. The valuable
output is a rare, explainable posture alert: protect after a stretched tape begins to deteriorate,
or redeploy after a washed-out tape begins to stabilize.

## Non-Goals

- No all-in/all-out market timing.
- No automated trade execution.
- No requirement to forecast daily moves.
- No single magic indicator.
- No assumption that Bulltard flow or commentary is itself a buy signal.
- No optimization for pretty historical fit if the signal does not improve realized portfolio
  outcomes after friction.

## Market-Regime Views

The regime engine should keep the main views separate:

| View | Purpose | Portfolio question |
| --- | --- | --- |
| Directional regime | Summarize whether the current tape is risk-on, neutral, or risk-off. | Should marginal beta be above, near, or below neutral? |
| Protect extension setup | Detect price extension and volatility complacency. | Is the tape extended enough to arm a later protect check? |
| Protect fragility setup | Detect vulnerable breadth, credit, liquidity, and rates context. | Is the backdrop fragile enough for a regime-break protect check? |
| Action confirmation | Track recent deterioration or stabilization across trend, volatility, breadth, credit, and liquidity. | Is a protect or redeploy setup now being confirmed? |
| Redeploy setup pressure | Detect stress, forced selling, panic, and broad washout. | Is the tape washed out enough to watch for stabilization? |

The headline regime is background context. It is not the action. A strong `risk_on` market can be
healthy or dangerously extended. A weak `risk_off` market can be deteriorating or washed out.

## Evidence Families

| Family | Candidate inputs | Question answered |
| --- | --- | --- |
| Trend / structure | SPY/QQQ momentum, moving-average distance, highs/lows | Is the market advancing, weakening, or damaged? |
| Volatility | VIX, VVIX, realized volatility, VIX9D/VIX, VIX/VIX3M | Is risk cheaply priced, stressed, rising, or normalizing? |
| Breadth | RSP/SPY, IWM/SPY, percent above 50d/200d, new highs/lows | Is participation confirming the index? |
| Credit / liquidity | HYG/TLT, high-yield spreads, NFCI, rates | Is funding supportive or defensive? |
| Sentiment / positioning | NAAIM, AAII, put/call, flows, CTA/dealer positioning | Are investors crowded, fearful, or under-positioned? |
| External overlay | Bulltard broad market notes and recurring flow patterns | Does outside research add incremental context? |

Do not add a signal just because it is famous. Add it only when source availability, update lag,
history length, and licensing are clear enough for replay.

## Current Market-Regime Model

The current v1.0 implementation computes:

- Directional regime score from family-level market signals.
- Stretch/washout pressure from rolling percentile-normalized features.
- Structured extension and washout setup scores whose required legs cannot compensate for one
  another.
- Deterioration/stabilization action evidence from bounded modules across trend, volatility,
  breadth, credit, and liquidity.
- Rare action states: `no_change`, `scale_down_protect`, `scale_up_redeploy`.
- A provisional portfolio policy mapping from action state to marginal beta/cash/overlay posture.

This is useful research scaffolding, not a finished model. The current implementation is v1.0
research code. It separates extension setup, fragility setup, deterioration confirmation,
and stabilization confirmation, and it uses saved same-version regime snapshots as the
extension and washout action-memory chain. Thresholds and decay windows are still research
assumptions, not calibrated production policy.

## Setup, Confirmation, Action

The preferred conceptual model is:

```text
setup != action
setup + confirmation => action
```

For protect:

```text
extension_setup   = price extension / volatility complacency
fragility_context = breadth, credit, liquidity, volatility, or trend weakness
protect_confirm   = broad deterioration; volatility-only is not enough by itself
protect_action    = armed extension setup + volatility turn + internal divergence
                    + (price rollover or breadth-and-credit divergence)
```

For redeploy:

```text
redeploy_setup   = washed-out / stressed tape
redeploy_confirm = volatility cools, breadth stabilizes, credit stops worsening
redeploy_action  = setup was armed and confirmation appears
```

Stretch alone is not bearish. It often means strong risk-on momentum. Washout alone is not
automatically bullish. It becomes actionable only when stabilization appears. Protect and
redeploy are phase-exclusive: once washout is armed, late protect evidence cannot override a
valid redeploy transition.

## Research Observations and Proposals

This section is a working research notebook for model problems and possible fixes. It should give
future reviewers, collaborators, and coding agents enough context to challenge the assumptions
rather than blindly tuning thresholds. These observations come from initial local outcome replays
and recent snapshot reviews. They are not implemented guarantees.

### Data-Driven Protect Review

The first protect review showed that the pre-redesign `scale_down_protect` was not a reliable
correction warning:

- 88 protect days collapsed into 42 distinct signal clusters using a 5-trading-day grouping rule.
- 32 of 42 clusters had no 5% SPY drawdown in the next 40 trading days.
- Protect forward returns looked baseline rather than defensive: 20d +1.8% versus +1.3% for all
  days, and 40d +2.8% versus +2.5% for all days.
- 10 of 42 clusters were volatility-only confirmation; 9 of those 10 had no 5% drawdown in the
  next 40 trading days.
- 8 of 42 clusters started after SPY was already more than 5% below its trailing 40-day high.
- Excluding COVID, only 4 of 14 SPY corrections of at least 5% had protect between 20 trading days
  before the peak and the first -5% crossing. A 40-day window covered only 6 of 14.
- Fast deep shock episodes should be reported separately from ordinary corrections. Missing a
  COVID-style shock is an acceptable protect false negative; the protect model is mainly trying to
  catch deterioration/divergence after extension, not every exogenous crash.

The lifecycle redesign materially improves the full 2016-2026 replay without tuning to maximize
historical returns: protect falls from 81 to 27 daily action rows, while 40-day SPY forward return
moves from +1.2% to -2.9% versus +2.5% on all dates. However, the post-2020 slice is only modestly
better than baseline (+1.3% versus +2.4% at 40 days), and the full-sample result is influenced by
the COVID window. Protect is therefore improved but not validated. Do not add filters merely to
make this sample prettier; improve inputs and test future data.

### Problem: Stretch Is Not Bearish By Itself

Initial outcome replays show that high stretch pressure has often been followed by positive
SPY/QQQ forward returns and modest drawdown. That means stretch is frequently strong risk-on
momentum, not a standalone de-risk signal.

Implemented v1.0 direction:

- Split current stretch pressure into cleaner `extension_setup` and `fragility_context` features.
- Keep price extension and volatility complacency in `extension_setup`.
- Move breadth, credit, liquidity, and trend weakness into fragility/confirmation context.
- Treat extension as an arming condition, not an immediate portfolio action.
- Validate extension-only buckets before using them to change portfolio posture.

### Problem: Protect Currently Mixes Different States

Pre-redesign same-day `scale_down_protect` did not separate bad forward windows well enough. The
action state could mean several different things:

- pre-correction extension with emerging deterioration;
- stress that is already visible;
- a false warning during a strong tape;
- event-volatility premium before a scheduled macro catalyst.

Implemented v1.0 direction:

- Keep one actionable path, `extension_unwind`: extension setup was armed, then lifecycle
  deterioration appears while SPY and QQQ remain above their 200-day trends.
- Require volatility deterioration, at least one breadth/credit divergence, and either short-term
  price rollover or divergence in both breadth and credit.
- Treat broad `regime_break` deterioration without prior extension as warning context, not action.
- Treat volatility-only confirmation as warning/context, not a normal `scale_down_protect`.
- Report which path fired and which families confirmed it.
- Diagnose protect by exclusive setup/confirmation buckets and by independent clusters of
  consecutive protect-action days; use correction episodes separately to measure missed events.

### Problem: Geometric Compensation Hides Weak Setup

The original protect strength was approximately:

```text
protect_strength = sqrt(stretch * deterioration)
```

This lets very strong deterioration compensate for mediocre setup. More than half of current
protect days have stretch below the empirical stretch p90, around 0.49 in the reviewed sample.
That explains many false positives: the signal can fire from one extreme input even when the setup
is not actually extended.

Implemented v1.0 direction:

- Extension setup requires both trend extension and volatility complacency to be at least 0.50;
  its score is their geometric mean only after both gates pass.
- Extension-unwind path: `armed_extension AND long_term_uptrend AND lifecycle_confirmation`.
- Regime-break evidence is diagnostic context only.
- Redeploy path: `armed_washout_gate AND stabilization_gate`.
- Strength scores remain useful after the gates pass, but cannot substitute for a missing setup
  or confirmation gate.

### Problem: Same-Day Setup And Confirmation Were Too Rigid

The v0.0 protect rule effectively required stretch setup and deterioration evidence to exist on
the same snapshot date. That missed the intended pattern: the market gets extended first, then
breadth, credit, or volatility deteriorates days or weeks later.

Implemented v1.0 direction:

- Add an armed setup state: high extension setup arms protect for a bounded number of trading days.
- Let the armed setup decay over time rather than disappear immediately.
- Trigger protect only when confirmation appears while setup is armed.
- Avoid noisy one-day arming: default v1.0 parameters arm from either
  `extension_setup >= 0.75` on one snapshot or `extension_setup >= 0.60` on at least
  3 of the last 10 saved trading snapshots.
- Apply the same sequencing principle to redeploy with faster parameters: arm washout from either
  `washout_setup >= 0.75` on one snapshot or `washout_setup >= 0.60` on at least 2 of the last
  5 saved trading snapshots, retain it for up to 15 snapshots with decay, and require current
  stabilization of at least `0.75` across at least two families. Each family begins confirming at
  `0.35`.
- Arm once per continuous setup run. A setup that remains elevated past expiration cannot silently
  re-arm as the history window advances; it must first reset below the persistence threshold.

Open research:

- Use a rolling percentile threshold, roughly p90, instead of a fixed score.
- Compare decay windows, such as 20 and 40 trading days, against correction episodes.

### Problem: Event Volatility Can Masquerade As Deterioration

The September 10, 2026 snapshot is a useful example. It signaled `scale_down_protect` with VIX,
VVIX, and VIX term-structure deterioration one day before the August CPI release scheduled for
September 11, 2026. Some or all of that volatility move may have been scheduled event-risk premium
rather than broad market deterioration.

Proposals:

- Add an `event_vol` context flag for known CPI, FOMC, payrolls, major expiration, and other
  scheduled macro/event dates.
- Downweight volatility-turn confirmation near scheduled events unless breadth, credit, trend, or
  liquidity also confirms.
- Do not let volatility-only deterioration activate normal protect.
- Split volatility evidence into generic deterioration and event-premium components.
- In output, distinguish `vol rising before known event` from `vol rising with broad internal
  deterioration`.

### Problem: Washout Is A Setup, Not An Automatic Buy

Washout pressure is associated with realized drawdown, but forward returns can also be strong.
That makes washout closer to a redeploy setup than a bearish warning or a mechanical buy signal.

Implemented v1.0 direction:

- Treat washout as `redeploy_setup`.
- Require concurrent trend damage, volatility stress, and at least one transmission channel from
  breadth, credit, or liquidity; unrelated neutral modules no longer dilute a valid setup.
- Require strong, broad stabilization confirmation before redeploy. The current gate requires an
  aggregate score of at least `0.75` across at least two of trend, volatility, breadth, credit, and
  liquidity; one strong family cannot trigger redeploy alone.
- Arm washout setup before applying stabilization and strength gates so high stabilization cannot
  geometrically compensate for a setup that never existed.
- Let valid redeploy confirmation win once washout is armed; an ineligible raw protect score does
  not block the phase transition.
- An intermediate 2016-2026 replay increased redeploy from 11 COVID-concentrated action rows to
  148 rows, but their lower forward return and larger adverse excursion showed that the gate had
  become too permissive. Requiring strong multi-family stabilization reduces the reviewed replay
  to 39 action rows across 19 washout runs. This is broader coverage, not proof of profitability.

Open research:

- Track whether redeploy signals fire too early during continuing stress.

### Problem: Shock Windows Distort Ordinary Correction Research

COVID, tariff announcements, wars, and similar headline shocks can dominate drawdown statistics.
They are useful for studying panic/bottom behavior, but they are poor calibration examples for
ordinary correction warning.

Proposals:

- Maintain episode diagnostics that can exclude or separately label shock-driven trough windows.
- Evaluate ordinary corrections and shock events as separate cohorts.
- Use shock events mainly to study washout/redeploy behavior, not ordinary protect warning.

### Problem: Action Events Are Not Portfolio Posture

Daily action outcomes are not a full portfolio backtest. `no_change` should eventually mean keep
the previous posture, not neutral today.

Proposals:

- Add stateful posture replay after episode diagnostics.
- Preserve protected/redeploying posture until an explicit reset or opposite signal appears.
- Measure both signal precision and actual portfolio effect after friction.

## Outcome Research

Forward replay should evaluate each layer separately:

- Setup-only buckets: does extension or washout change future return/drawdown distributions?
- Confirmation-only buckets: does deterioration or stabilization matter without a prior setup?
- Setup-plus-confirmation buckets: does the intended lifecycle rule improve drawdown/return tradeoffs?
- Active posture episodes: does maintaining a protected or redeploying state improve portfolio
  outcomes after friction?

Use episode-level diagnostics for corrections. Daily overlapping forward windows are useful, but
they can overcount one event. A correction episode report should show:

- correction threshold, such as 5% or 8%;
- whether warning arrived before the first -3% or -5% drawdown crossing;
- first warning date;
- warning lead time in trading days;
- worst start date;
- trough date;
- whether the signal was early, timely, or already late;
- false-alert rate, defined as no 5% SPY drawdown within 40 trading days;
- prior 5/10/20 trading-day setup and confirmation history;
- action/posture active at each phase;
- whether the episode is ordinary, shock-driven, or unclear.

## Portfolio Translation

The action output controls only the tactical sleeve:

| State | Intent | Typical bounded response |
| --- | --- | --- |
| `no_change` | Evidence is too balanced or incomplete. | Maintain current posture. |
| `scale_down_protect` | Armed extension has confirmed a volatility turn plus price/internal deterioration. | Reduce marginal beta, rebuild cash, sell covered calls, avoid fresh long calls. |
| `scale_up_redeploy` | Washout setup has confirmed stabilization. | Deploy cash in tranches, consider 60-90 DTE calls/call spreads, underwrite lower entries with defined risk. |

Future posture replay must make state persistent. After protect activates, later `no_change` dates
should remain protected until redeploy or an explicit reset. The current action-event table is not
that backtest.

## Bulltard and Single-Name Research

Bulltard is candidate-generation evidence for the single-name engine. It is not the market-regime
source of truth and does not override independent regime evidence.

The v0.0 candidate strategy is:

- capture Bulltard evidence with provenance;
- rank source attention before validation;
- validate candidates against independent price, volume, trend, drawdown, and relative-strength
  data;
- classify candidates as `confirm`, `watch`, or `avoid`;
- apply market-regime context after validation as a risk-budget modifier;
- replay candidate outcomes over 40- and 65-trading-day windows before inventing a complex score.

The single-name engine should eventually track lifecycle episodes:

```text
DISCOVERED -> WATCHING -> VALIDATED -> ACTIVE_SETUP -> PLAYED_OUT / INVALIDATED
```

Each episode should preserve thesis, catalyst, invalidation, option-liquidity suitability, market
context, and realized outcome.

## Backtesting Standards

- Use walk-forward or out-of-sample evaluation where possible.
- Measure drawdown and adverse excursion, not only terminal return.
- Evaluate SPY and QQQ separately.
- Track precision, recall, timing, false positives, and opportunity cost.
- Model transaction costs, option spreads, taxes, assignment, and roll behavior before treating a
  portfolio policy as credible.
- Keep a simple benchmark, such as buy-and-hold core plus fixed tactical policy.
- Reject models that require many hand-tuned parameters to look better.

## Near-Term Algorithm Backlog

1. Collect forward out-of-sample evidence for the current protect lifecycle; do not optimize the
   remaining weak post-2020 result in sample.
2. Study whether the fixed extension arm threshold should become a rolling p90 threshold.
3. Compare 20 and 40 trading-snapshot decay windows for extension-unwind memory.
4. Tighten event-volatility handling so scheduled macro premium does not masquerade as broad
   deterioration.
5. Add stronger breadth, sentiment, and positioning sources only when their histories are replayable.
6. Measure redeploy by independent episodes and tranches, not overlapping daily action rows alone.
7. Expand Bulltard candidate outcomes from triage labels into lifecycle episodes.
