# MarketLab Algorithm Design

**Status:** pre-debut research design, current as of September 2026.

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

The regime engine should keep three views separate:

| View | Purpose | Portfolio question |
| --- | --- | --- |
| Directional regime | Summarize whether the current tape is risk-on, neutral, or risk-off. | Should marginal beta be above, near, or below neutral? |
| Protect setup pressure | Detect extension, complacency, narrow participation, or early funding weakness. | Is the tape vulnerable enough to watch for deterioration? |
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

The current v0.0 implementation computes:

- Directional regime score from family-level market signals.
- Stretch/washout pressure from rolling percentile-normalized features.
- Deterioration/stabilization action evidence from bounded modules across trend, volatility,
  breadth, credit, and liquidity.
- Rare action states: `no_change`, `scale_down_protect`, `scale_up_redeploy`.
- A provisional portfolio policy mapping from action state to marginal beta/cash/overlay posture.

This is useful research scaffolding, not a finished model.

## Setup, Confirmation, Action

The preferred conceptual model is:

```text
setup != action
setup + confirmation => action
```

For protect:

```text
protect_setup    = stretched / extended / complacent tape
protect_confirm  = later breadth, credit, volatility, or term-structure deterioration
protect_action   = setup was armed and confirmation appears
```

For redeploy:

```text
redeploy_setup   = washed-out / stressed tape
redeploy_confirm = volatility cools, breadth stabilizes, credit stops worsening
redeploy_action  = setup was armed and confirmation appears
```

Stretch alone is not bearish. It often means strong risk-on momentum. Washout alone is not
automatically bullish. It becomes actionable only when stabilization appears.

## Research Observations and Proposals

This section is a working research notebook for model problems and possible fixes. It should give
future reviewers, collaborators, and coding agents enough context to challenge the assumptions
rather than blindly tuning thresholds. These observations come from initial local outcome replays
and recent snapshot reviews. They are not implemented guarantees.

### Problem: Stretch Is Not Bearish By Itself

Initial outcome replays show that high stretch pressure has often been followed by positive
SPY/QQQ forward returns and modest drawdown. That means stretch is frequently strong risk-on
momentum, not a standalone de-risk signal.

Proposals:

- Treat stretch as `protect_setup`, not `protect_action`.
- Rename or explain the concept more clearly in outputs, for example `risk_on_extension` or
  `protect_setup`.
- Validate stretch as a setup-only bucket before using it to change portfolio posture.

### Problem: Protect Currently Mixes Different States

Same-day `scale_down_protect` has not separated bad forward windows well enough. The current
action state can mean several different things:

- pre-correction extension with emerging deterioration;
- stress that is already visible;
- a false warning during a strong tape;
- event-volatility premium before a scheduled macro catalyst.

Proposals:

- Split protect research into `protect_setup`, `protect_confirmation`, and `protect_action`.
- Require setup plus confirmation for action, but study each component separately.
- Report why protect fired: price extension, breadth damage, credit damage, vol turn, event-vol,
  or some combination.

### Problem: Same-Day Setup And Confirmation Are Too Rigid

The current protect rule effectively requires stretch setup and deterioration evidence to exist on
the same snapshot date. That can miss the intended pattern: the market gets extended first, then
breadth, credit, or volatility deteriorates days or weeks later.

Proposals:

- Add an armed setup state: high stretch arms protect for a bounded number of trading days.
- Let the armed setup decay over time rather than disappear immediately.
- Trigger protect only when confirmation appears while setup is armed.
- Compare decay windows, such as 10, 20, and 40 trading days, against correction episodes.

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
- Split volatility evidence into generic deterioration and event-premium components.
- In output, distinguish `vol rising before known event` from `vol rising with broad internal
  deterioration`.

### Problem: Washout Is A Setup, Not An Automatic Buy

Washout pressure is associated with realized drawdown, but forward returns can also be strong.
That makes washout closer to a redeploy setup than a bearish warning or a mechanical buy signal.

Proposals:

- Treat washout as `redeploy_setup`.
- Require stabilization confirmation before redeploy: volatility cooling, breadth stabilizing, or
  credit no longer worsening.
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

- first warning date;
- worst start date;
- trough date;
- prior 5/10/20 trading-day setup and confirmation history;
- action/posture active at each phase;
- whether the episode is ordinary, shock-driven, or unclear.

## Portfolio Translation

The action output controls only the tactical sleeve:

| State | Intent | Typical bounded response |
| --- | --- | --- |
| `no_change` | Evidence is too balanced or incomplete. | Maintain current posture. |
| `scale_down_protect` | Stretched setup has confirmed deterioration. | Reduce marginal beta, rebuild cash, sell covered calls, avoid fresh long calls. |
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

1. Build correction episode diagnostics with shock-window labeling.
2. Split current protect/redeploy outputs into setup, confirmation, and action research buckets.
3. Test armed setup decay windows for protect and redeploy.
4. Add stateful posture replay.
5. Add stronger breadth, sentiment, and positioning sources only when their histories are replayable.
6. Expand Bulltard candidate outcomes from triage labels into lifecycle episodes.
