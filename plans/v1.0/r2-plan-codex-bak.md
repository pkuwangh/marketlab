# Market-Regime V2 Design Plan

**Status:** pre-implementation research plan, current as of September 2026.

This plan builds on `ALGORITHM_DESIGN.md`, `v1-plan-codex.md`, `v1-ideas-chatgpt.md`, and the
current workbook export under `workbooks/`. The workbook data is used for diagnosis and falsification,
not for curve fitting.

## Goal

Turn market-regime actions into a small lifecycle model:

```text
setup -> memory / context -> confirmation -> action -> posture -> reset
```

The main target is `scale_down_protect`, because current replay says it is not yet a reliable
correction-warning signal. `scale_up_redeploy` looks more promising empirically, but it should also
be expressed as setup plus confirmation instead of a one-day blended score.

## First Principles

1. A correction warning is a lifecycle problem, not a same-day classification problem.

   Markets often become extended first, then deteriorate later. If setup and confirmation must happen
   on the same date, the model will miss the intended pattern.

2. Extension is vulnerability, not bearish evidence.

   A strong SPY/QQQ tape can remain strong. High price extension and low volatility should arm a later
   check, but should not by itself reduce risk.

3. Deterioration needs breadth.

   Volatility can rise for scheduled events or temporary hedging demand. Normal protect should require
   support from non-volatility evidence such as breadth, credit, liquidity, or trend damage.

4. Some corrections are not extension unwinds.

   A separate regime-break path is needed for broad deterioration without prior extension. This path
   should be harder to trigger than extension-unwind protect.

5. Washout is a redeploy setup, not an automatic buy.

   Stress can keep worsening. Redeploy should require evidence that volatility, breadth, credit, or
   trend is stabilizing.

6. Action events are not portfolio posture.

   A one-day `no_change` after protect should not mean neutral exposure again. The model should
   eventually replay protected / redeploying posture episodes with explicit resets.

7. The model should stay interpretable.

   Prefer family gates, state memory, and named paths over a dense weighted score. Tune fewer knobs,
   and require every knob to have a market-structure reason.

## Local Data Observations

These observations are from the current `workbooks/regime.csv` export and outcome summaries. They
should guide design pressure, but they are not threshold targets.

- Current actions cover 2,617 daily rows from 2016-01-04 through 2026-06-01: 2,481 `no_change`,
  88 `scale_down_protect`, and 48 `scale_up_redeploy`.
- `scale_down_protect` forward returns are not defensive: 20d SPY was +1.8% versus +1.3% for all
  days; 40d SPY was +2.8% versus +2.5% for all days.
- High stretch buckets were not bearish. `stretch:p90` had positive forward returns and lower
  drawdowns than the full sample.
- High washout buckets had strong forward returns but larger path drawdowns. That supports
  treating washout as a redeploy setup that still needs stabilization.
- A simple SPY correction scan found 15 episodes of at least 5% drawdown. Current protect appeared
  between 20 trading days before the peak and the first -5% crossing in 5 of 15 episodes; a 40-day
  window covered 7 of 15.
- Current protect is volatility-heavy. At a 0.4 family threshold, 29 of 88 protect days were
  volatility-only.
- Current protect is not cleanly extension-driven. Average protect-day extension proxy was 0.35,
  while the fragility proxy was 0.57. 58 of 88 protect days had extension proxy below the full-sample
  p80.
- A naive diagnostic rule using armed extension memory plus broad confirmation covered more correction
  episodes, but it also over-fired badly. For example, an extension-p90, 40-day memory, and broad
  confirmation proxy produced 73 signal clusters, 57 of which had no 5% SPY drawdown in the next
  40 trading days.

Interpretation: v2 should not try to find a magic protect threshold. The current model is mixing
extension, fragility, volatility-event premium, stress, and posture into one daily score.

## Cross-Check Against `v1-plan-claude.md`

`v1-plan-claude.md` agrees with the main architecture: split extension from fragility, block
volatility-only protect, use two protect paths, add event-volatility context, evaluate correction
episodes, and add posture replay.

It also adds useful refinements that V2 should adopt:

- The fragility split should come before armed memory. If breadth, credit, liquidity, and rates are
  removed from `extension_setup`, many late or weak protect signals should fail before decay logic is
  needed.
- Redeploy should be protected from scope creep. The current redeploy/washout behavior is the best
  empirical part of v0.0. V2 should mainly make the setup/confirmation labels cleaner and verify that
  redeploy still works.
- Non-volatility confirmation must be concrete. VIX, VVIX, and term-structure moves should not count
  as multiple independent families that satisfy broad confirmation by themselves.
- Volatility feature entries should be collapsed into a single `volatility` family for confirmation
  counting. VIX, VVIX, and VIX term structure are useful evidence, but they are too correlated to
  count as independent families.
- The headline regime should not be used as a standalone de-risk signal or a hard regime-break gate.
  The current outcome table makes it look almost contrarian: `risk_off` has had stronger forward
  returns than `risk_on`, likely because it often appears after stress is already visible. For
  regime-break protect, headline regime should be reported as background context and later studied as
  a consistency variable, not used to block an otherwise valid deterioration signal now.
- Episode diagnostics and posture replay are not reporting polish. They are required before judging
  whether protect is useful.

V2 intentionally differs in two places:

- Hard numerical targets, such as a specific false-alert rate or correction-coverage threshold, should
  be treated as sanity checks rather than optimization goals. They are useful for rejecting bad models,
  but they should not become fitting targets.
- A dedicated `regime episodes` command may be useful, but the design requirement is the structured
  episode diagnostic itself. CLI shape can stay flexible until the implementation is clearer.

## What V2 Changes From Earlier Plans

The earlier plans correctly identified armed extension, broad confirmation, and a separate
regime-break path. V2 makes four changes:

1. Add an explicit anti-overfit requirement.

   The plan should not jump from "memory would have helped some misses" to "memory is the model."
   Simple memory proxies can over-fire, so the first implementation must measure clusters, false
   alerts, late signals, and posture cost.

2. Treat volatility event premium as a first-class context.

   VIX/VVIX and term-structure moves before CPI, FOMC, payrolls, expiration, or other known events
   can be hedging premium rather than broad deterioration. That state should be visible but should
   not trigger protect by itself.

3. Make posture replay part of the design, not a later reporting nice-to-have.

   The action event only tells us when a state changes. The real portfolio question is whether holding
   a protected or redeploying posture improves drawdown, opportunity cost, and tactical-sleeve return
   after friction.

4. Prioritize semantic cleanup before state memory.

   First make `extension_setup`, `fragility_context`, and confirmation families mean the right things.
   Then add decay/memory. Otherwise the state machine will preserve a noisy mixed signal for longer.

## V2 State Vocabulary

| State | Meaning | Action role |
| --- | --- | --- |
| `extension_setup` | Price extension and volatility complacency are elevated. | Arms future protect checks. |
| `fragility_context` | Breadth, credit, liquidity, rates, trend, or volatility are weakening. | Confirms or contextualizes risk. |
| `vol_event_warning` | Volatility rises without broad non-vol confirmation, especially near known events. | Warning only. |
| `broad_deterioration_confirm` | At least two evidence families deteriorate, including one non-vol family. | Can trigger extension-unwind protect. |
| `regime_break_confirm` | Strong broad deterioration without requiring prior extension. | Can trigger harder protect path. |
| `washout_setup` | Stress, panic, forced selling, or oversold pressure is elevated. | Marks a redeploy watch. |
| `stabilization_confirm` | Volatility, breadth, credit, or trend stops worsening. | Can trigger redeploy. |
| `posture_state` | Current tactical stance: neutral, protected, redeploying. | What portfolio replay should hold over time. |

Family-vote counting and leaf-signal scoring are separate concepts. VIX, VVIX, and VIX term
structure count as one `volatility` family for cross-family confirmation, but the individual
volatility leaf signals still matter. For example, VIX high while VVIX cools can be strong
volatility stabilization evidence for redeploy, and VVIX rising ahead of VIX can remain an early
protect warning. The family-vote rule prevents false breadth; it does not remove useful within-family
patterns.

## Protect V2

Protect should have two named paths.

### Path A: Extension Unwind

```text
extension_setup high
    -> arm protect for a bounded window
    -> broad deterioration confirms
    -> scale_down_protect
```

Design rules:

- `extension_setup` should be based only on price extension and volatility complacency.
- Use rolling percentile language, such as high relative to recent history, instead of fixed absolute
  scores where possible.
- Keep armed setup alive for a bounded 20-40 trading-day window with decay.
- Require broad confirmation while the setup is armed.
- Require at least two confirming families and at least one non-volatility internal family. Volatility
  sub-signals such as VIX, VVIX, and VIX term structure count collectively as one `volatility`
  family, not separate independent families. The non-volatility family should be breadth, credit,
  liquidity, or trend.
- Do not allow extreme deterioration to compensate for missing extension on this path.
- Label the fired path as `extension_unwind`, and report the armed date, age, decay, and confirming
  families.

### Path B: Regime Break

```text
strong broad deterioration
    -> scale_down_protect
```

Design rules:

- No prior extension is required.
- The gate must be stricter than extension-unwind confirmation.
- Require trend damage plus at least one or two of breadth, credit, liquidity, or volatility
  deterioration.
- Volatility-only deterioration cannot fire this path.
- If the headline regime is still strongly `risk_on`, report that in the action explanation and
  episode diagnostics. Do not use headline regime as a hard gate; it is a simple background summary
  and has behaved closer to a lagging or contrarian read than a reliable action signal. Direct
  pressure and confirmation evidence should dominate the headline label.
- Label the fired path as `regime_break`, and report why it bypassed extension setup.

### Warning-Only Volatility

Volatility-only signals should remain visible, but should not trigger normal protect.

```text
volatility deterioration without broad confirmation
    -> warning / context
    -> no protect action
```

Near known event dates, such as CPI, FOMC, payrolls, major expiration, or major company-specific
index events, the output should distinguish event premium from broad market deterioration.

## Redeploy V2

Redeploy should stay close to the current behavior but become a lifecycle. This is a cleanup and
validation effort, not a full redesign.

```text
washout_setup high
    -> stabilization confirms
    -> scale_up_redeploy
```

Design rules:

- Washout can mark a redeploy watch, but should not automatically buy.
- Do not force redeploy through the same armed-memory machinery as protect. Washout is already the
  setup; the main question is whether stabilization has arrived.
- Do not require a non-volatility family gate for redeploy. VIX-high / VVIX-cooling and volatility
  term-structure normalization can be valid stabilization evidence by themselves, though severe
  funding or credit stress should still block premature redeploy.
- Stabilization can come from volatility cooling, breadth improving, credit no longer worsening, or
  trend reclaiming short-term structure.
- Preserve existing severe-funding-stress blocks or equivalent guardrails. Redeploy should not fire
  just because price is down if funding or credit stress is still accelerating.
- Redeploy can be staged. The first signal may only restore part of the tactical sleeve.
- Track whether redeploy fired during continuing stress or after actual stabilization.
- Validate redeploy separately from protect; do not let protect redesign break a better-performing
  recovery signal.

## Portfolio Posture

V2 should distinguish action events from held posture, but posture should not add a new required
daily workflow.

```text
neutral
    -> protect event
    -> protected posture
    -> reset / redeploy event
    -> neutral or redeploying posture
```

Required posture concepts:

- `protected_since`
- `protect_reason`
- `protect_path`
- `posture_age`
- `max_drawdown_since_posture`
- `reset_reason`
- `redeploy_since`

This matters because a later `no_change` should usually mean maintain the prior posture, not reset
to neutral.

CLI/workflow rule:

- `regime snapshot` should remain the normal daily read.
- `regime outcomes` may include posture replay when evaluating history.
- Workbook export may include posture columns for analysis.
- Do not add a required `regime posture` daily command unless debugging demand clearly justifies it.

## Outcome Research

Before changing many thresholds, build diagnostics that evaluate the lifecycle directly.

### Correction Episodes

For each SPY correction episode, report:

- peak date;
- first -3% and -5% drawdown crossing;
- trough date and max drawdown;
- whether protect was armed before the peak;
- whether protect fired before -3%, before -5%, after -5%, or not at all;
- first warning date and lead time;
- whether the episode looked ordinary, scheduled-event-driven, or shock-driven;
- whether redeploy appeared before stabilization or after stabilization.

Ordinary corrections and shock windows should be evaluated separately. COVID-style crashes,
tariff headlines, wars, and surprise policy shocks are more useful for washout/redeploy research
than for calibrating ordinary protect warnings.

### False Alerts

For each protect cluster, report:

- path: `extension_unwind`, `regime_break`, or warning-only;
- whether a 5% drawdown happened within 20 / 40 / 65 trading days;
- whether the signal was late because SPY was already down more than 5% from a trailing high;
- how many confirming families were present;
- whether confirmation was volatility-only;
- realized opportunity cost if the portfolio entered protected posture.

### Setup And Confirmation Buckets

Replay the components independently:

- extension setup only;
- fragility / deterioration only;
- armed extension plus confirmation;
- regime-break confirmation;
- washout setup only;
- washout setup plus stabilization.

The key question is not whether one bucket has a prettier average return. The key question is whether
the lifecycle rule improves timing, drawdown avoided, and opportunity cost versus a simple benchmark.

## Anti-Overfit Rules

- Do not optimize many thresholds against 2016-2026 daily outcomes.
- Prefer rolling percentiles and family counts over fitted weights.
- Use exact workbook numbers only as diagnostics and sanity checks.
- Keep threshold families coarse: normal, elevated, extreme.
- Require monotonic intuition: more deterioration should not make a setup look safer unless the
  signal is explicitly a washout/redeploy signal.
- Evaluate with episode-level timing, not only overlapping forward-return rows.
- Separate ordinary corrections from shock events.
- Keep the action explanation short enough that a human can audit it from the snapshot table.
- Reject changes that improve one historical output but make the state vocabulary less clear.

## Hold Off For Now

- Sentiment and positioning sources such as NAAIM, AAII, put/call, fund-manager surveys, and flow
  data should wait until the gate structure is cleaner and the source history is replayable.
- Multiple protect confidence tiers such as warning, alert, and urgent are premature. First prove that
  the binary protect event is useful.
- Bulltard/single-name regime modifiers should stay unchanged until market-regime protect is less
  noisy. Passing a noisy market signal into ticker scoring would compound the problem.
- Exact target metrics, such as "false-alert rate below X," should be used as rejection checks, not as
  an optimization objective.
- Before declaring v2 ready for live use, false-alert rate should be materially lower than the current
  roughly 76% cluster false-alert baseline, and correction coverage should be materially higher than
  the current 5 of 15 episode coverage in the simple 20-day pre-peak scan. These numbers are rejection
  checks, not calibration targets.

## Implementation Sequence

1. Split extension setup from fragility context.

   Add explicit columns for `extension_setup`, `fragility_context`, `washout_setup`,
   `broad_deterioration_confirm`, `regime_break_confirm`, and `stabilization_confirm`. Keep the
   underlying evidence families visible. Preserve the current washout/redeploy calculation until the
   new fields have been validated.

2. Add correction-episode diagnostics.

   Build `regime outcomes` support for SPY correction episodes. Start with 5% and 8% drawdown
   thresholds, first -3% / -5% crossing dates, trough dates, warning coverage, late signals, and
   false-alert clusters.

3. Replace protect with gated paths.

   Implement `extension_unwind` and `regime_break` protect paths using current-day setup first. Remove
   geometric compensation as the trigger mechanism. Compute strength after gates pass, not before.

4. Make volatility-only confirmation warning-only.

   Keep the information in the output, but prevent normal `scale_down_protect` unless non-volatility
   evidence confirms.

5. Add event-vol context.

   Start simple: allow a small manually maintained event calendar or generated known-event feed. The
   first implementation only needs to label context and suppress volatility-only protect near events.

6. Add armed setup memory as research output first.

   Compute armed extension state after gates are explicit. Export age, decay, source date, and source
   strength so the behavior can be inspected in Excel before it controls production actions. Do not add
   a separate armed-memory requirement to redeploy unless diagnostics show it helps.

   Armed memory should only be promoted into the production protect gate if episode diagnostics show
   a better lifecycle tradeoff than the non-memory gate. That can mean better correction coverage,
   earlier warning, fewer late signals, lower posture cost, or lower false-alert rate, but it should
   not materially worsen false alerts or posture cost just to catch more episodes. Armed days must
   also show visible price-extension evidence in the workbook. If those checks fail, keep armed memory
   as research/export context only.

7. Add posture replay.

   Replay protected and redeploying posture states with resets. Compare portfolio-level behavior after
   friction against buy-and-hold core plus a fixed tactical sleeve. Keep this inside outcomes/export
   flows rather than adding another normal daily command path.

8. Validate redeploy separately.

   Keep redeploy mostly stable until protect is cleaner, then test whether washout-plus-stabilization
   improves timing versus the current redeploy action.

9. Add new data sources only after the lifecycle model is clear.

   Better breadth, sentiment, and positioning data can help, but only if the source has enough history
   and can be replayed point-in-time.

## Done Criteria

- Snapshot output can explain whether protect is `extension_unwind`, `regime_break`, or warning-only.
- Volatility-only deterioration does not produce normal protect.
- Outcome reports include correction episodes, signal clusters, late signals, and false alerts.
- Workbook export includes setup, confirmation, action, and posture fields that can be charted.
- Posture replay has been computed: protected and redeploying episodes are reconstructed from action
  events with explicit resets, and posture-episode outcomes such as drawdown avoided, opportunity
  cost, and episode length are visible in the outcome report or workbook.
- A human can inspect a protect signal and understand why it fired without reading code.
- The design improves conceptual consistency before any version bump or threshold tuning.
