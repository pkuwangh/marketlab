# V1.1 Proposal: Correct Evidence, Stable Lifecycles, Measurable Exposure

**Status:** consolidated design proposal; not implemented.
**Date:** September 17, 2026.
**Basis:** the final convergence proposal and agreement in
[r1-discussion.md](r1-discussion.md#codex---agreement-recorded).

This document consolidates the accepted direction from the Codex/Claude discussion. Earlier
alternatives and retracted findings are not implementation requirements. Progress tracking belongs
in a separate document, not edits to this proposal's specification.

## 1. Objective And Scope

Make the market-regime research loop internally consistent before judging incremental alpha:

1. Remove non-monotone scoring and duplicate cross-family evidence.
2. Separate setup eligibility, continuous stress, lifecycle memory, and held posture.
3. Measure actual held exposure as well as forward signal returns.
4. Test whether mandatory breadth/credit transmission unnecessarily excludes useful recoveries.

The fourth item is a conditional research experiment, not approval to relax the default model.
Ship correctness repairs even if that experiment is inconclusive. Preserve the permanent core,
local research workflow, Python-owned deterministic calculations, and EOD signal semantics.

Out of scope: automated execution, options payoff modeling, fitted action-frequency targets,
new sentiment inputs, a parallel slow-decline lifecycle, automatic posture renewal, generic
stop-loss optimization, and Bulltard-driven aggregate exposure. Protect divergence-memory versus
direct-damage entry experiments remain a later research task; do not change both entry models
while trying to attribute the washout experiment.

## 2. Evidence And Coverage Contract

Canonical observations and explicitly versioned snapshots are the calculation boundary. Workbooks
are exports, not model inputs. If DuckDB is used, verify its represented versions, dates, and
source refresh before analysis. An absent requested version must not silently select another.

Distinguish:

| State | Meaning |
| --- | --- |
| Observed zero | Valid inputs were evaluated and do not support this direction. |
| Unknown | Required inputs are unavailable, stale, insufficiently warmed up, or incompatible. |
| Eligible / ineligible | A rule's conditions have a determinable result. |
| Unvalidated | Required evidence leaves eligibility unresolved; do not emit a new validated action. |

Declare the input set of every scored family and setup module before replay. Never silently
average a different set of inputs when a source disappears. Optional readings may remain visible
without changing that declared rule. Fixed-input reduced-history/reduced-input research must be
identified separately from a complete-input model; compare augmentations on common dates.

Coverage follows rule dependencies, including SPY/QQQ, volatility indexes and same-date ratios,
RSP/IWM, HYG/TLT, OAS, NFCI, and any direct breadth actually selected. The exact historical input
profiles are a prerequisite deliverable, not permission to fill missing observations with zeros.

Funding veto remains `OAS stressed AND NFCI tight`, with three-valued logic:

- Both true: block redeploy.
- Either known false: the conjunction is false, even if the other input is unknown.
- Otherwise: unresolved; print evidence and coverage, but do not assume the veto passed.

The official [FRED OAS notes](https://fred.stlouisfed.org/series/BAMLH0A0HYM2) limit the available
series to three years starting in April 2026. An earlier request date is not a historical-data
solution. Investigate authorized sources or provenance-backed local history separately; do not
assume availability or purchase access implicitly. Valid older local observations do not expire
because the provider's current download window is shorter. Direct breadth coverage also needs
verification. Keep the current-vintage FRED limitation visible.

## 3. Confirmation And Evidence Ownership

### One Vote Per Family

For each direction, take the maximum of a family's eligible, source-owned alternative readings.
This measures its strongest supported turn, not the number of feature rows that fire. Duplicate
or weaker additional readings cannot increase or reduce that maximum. Coverage is checked under
the declared input contract before treating the score as valid.

| Family | Numerical vote | Context and paired evidence |
| --- | --- | --- |
| Trend | Existing short/medium SPY/QQQ momentum feature. | No new trend feature in this round. |
| Volatility | Max of VIX turn, VVIX turn, term-structure turn, and `vvix_vs_vix`, separately by direction. | Preserve both VIX/VVIX divergence directions. Volatility-normalization concordance remains visible but adds no vote. |
| Breadth | Participation turn from the fixed input set. | Price/breadth divergence remains a conditioned protect gate, not a second numerical reading. |
| Credit | Max of HYG/TLT turn and OAS turn under the coverage contract. | Remove NFCI from credit-owned helpers. Price/credit divergence conditions owned credit damage; cross-family concordance/contradiction is explanatory, not another credit vote. |
| Liquidity | NFCI turn. | No additional NFCI vote through credit helpers. |

Keep paired-signal explanations and diagnostics. Do not create a separately voting signal-pair
family or a runtime graph for estimating input independence. Distinct family ownership prevents
duplicated derived votes; it does not establish statistical independence among market indicators.

### Binary Conditions Versus Graded Pairs

Replace the overloaded `_gated_score` operation with explicitly different semantics:

- Boolean condition: true passes the owned score unchanged; false returns zero. Preserve unknown
  dependencies when the result cannot be determined. Do not apply a square root to a passed score.
- Graded pair: retain a separately named geometric combination where both inputs are graded,
  including high VIX with cooling VVIX. Preserve unknown coverage rather than treating it as calm.

Audit every caller by its input meaning. `sqrt(1 * 0.25) = 0.5` is not a valid binary pass-through.
A graded geometric mean requires positive legs but can still compensate between unequal legs;
explicit substantive setup gates remain separate.

### Cross-Family Confirmation

Aggregate deterioration and stabilization using the second-highest eligible family score. Keep
insufficient coverage distinguishable from two evaluated families failing to confirm.

- Redeploy: second-highest stabilization at least **0.75**, meaning two strong family readings.
- Protect: preserve named volatility/internal-divergence gates at **0.35**, armed extension,
  long-term uptrend, and rollover-or-broad-divergence requirements.
- Preserve the **0.55** action-strength checks and the separate setup/current-opportunity gates.
  Strength remains a summary after prerequisites, not a substitute for them.
- Headline regime remains descriptive, not an additional action gate. Regime-break stays warning
  context, not a new protect action.

These are declared research constants, not probabilities or calibrated optimal thresholds. Their
new score meaning changes decisions; report that instead of fitting constants to restore old counts.

## 4. Setup Memory And Continuous Release

### Preserve The Existing Arming Defaults

| Parameter | Extension | Washout |
| --- | --- | --- |
| Strong observation | Setup at least 0.75 | Setup at least 0.75 |
| Persistent observations | At least 0.60 on 3 of 10 sessions | At least 0.60 on 2 of 5 sessions |
| Required setup legs | Trend and volatility each at least 0.50 | Trend and volatility each at least 0.50; breadth or credit at least 0.35 |
| Memory | 40 elapsed sessions from arm | 15 elapsed sessions from last qualifying stress hit |

Age zero is the arm/hit session; a memory interval includes its final configured elapsed session
and expires afterward. Armed eligibility and a freshness weight that reaches zero at that boundary
are distinct fields. Do not silently reinterpret one as the other.

### Stable State

- Preserve episode identity/start and remembered peak until expiry or an explicitly specified
  setup reset. A sub-threshold day cannot replace the peak or create a new episode.
- A qualifying washout hit refreshes its grace clock, not episode identity. A quiet day advances
  elapsed age without refreshing grace. Extension retains its separate fixed-age rule.
- Track episode start, last qualifying hit, and posture entry separately. Repeated actions do
  not reset any entry identity. Posture exit does not implicitly erase setup history.
- Track the continuous-stress peak separately from gated setup/source strength. Initialize from
  the qualifying observations that establish the episode and update with comparable stress
  observations while the episode remains active; never read future observations.
- Use one deterministic state transition for ordered backfill and incremental computation.
  Export the state that produced the action, not a separately reconstructed competing state.
- Validate continuity against trading sessions in the canonical SPY history. Missing required
  intermediate snapshots produce a clear backfill instruction. Explicit backfill initialization
  and feature warmup are not the same as an unexplained hole in an established chain.

Preserve enough state to resume an active episode without silently truncating its identity or
peak to the latest bounded lookback. Do not require replay from the beginning for routine daily use.

### Repaired Baseline Release

```text
T = continuous trend washout
V = continuous volatility washout
X = max(continuous breadth washout, continuous credit washout)
stress = (T * V * X) ** (1/3)
setup_eligible = T >= 0.50 AND V >= 0.50 AND X >= 0.35
release = max(0, active_episode_peak_stress - current_stress)
```

Categorical eligibility determines qualifying arming observations. Continuous stress remains
defined independently of that gate when inputs are available. Crossing a setup threshold must
not manufacture a large release by replacing the score with zero. A genuinely zero component
can still produce zero continuous stress; fixing the threshold discontinuity does not validate
the full economic model.

Retain current broad washout at least **0.35**, release at least **0.05**, confirmation, strength,
and funding checks for redeploy. Missing/changed coverage cannot count as relief. Peak and current
stress must use the same definition and comparable input set.

## 5. Held Posture And Episode Consumption

Posture is the intended research exposure, not a record of the user's holdings. Preserve original
entry date, episode, and risk reference while holding; daily confirmations are not new entries.

### Protect Recovery

Exit protection after **three consecutive trading sessions** on each of which:

1. SPY and QQQ five-session returns are both nonnegative.
2. Every causally contributing entry family's ungated, owned deterioration is below **0.35**.

Record volatility and the internal families actually used by the entry predicate, plus trend when
the rollover branch supplies confirmation. Do not record every positive feature as a required
exit dependency. Specify deterministic branch attribution when multiple entry branches pass.
Unknown required evidence breaks the streak. Remove fragility, extension, and complacency as
independent reasons to retain protection; disappearing price-gated divergence is not recovery.

### Redeploy Failure

Exit redeploy on one session where all three conditions hold:

```text
owned trend deterioration >= 0.35
AND owned volatility deterioration >= 0.35
AND continuous stress today > continuous stress on the prior trading session
```

Use comparable stress under that variant's definition. Missing evidence cannot establish this
exit. A renewed qualifying stress hit alone is not failure: entry intentionally occurs while
washout remains elevated. Falling washout alone is not an exit either. No new episode identity,
percentage stop-loss, or extra persistence parameter is required.

Otherwise hold until timeout or a valid opposite action. This is thesis invalidation, not a
guaranteed risk stop. Measure its historical frequency and delay after testing reachability with
synthetic sequences; do not loosen it merely because few historical examples fire.

### Priority And Re-Entry

Allow at most **one posture entry per direction per setup episode**. Remember the episode consumed
at entry across recovery, failure, timeout, and opposite-action exit. A next-day action cannot
reuse it. A new entry requires a genuinely new episode under the lifecycle rules, not a renamed
active episode. The cost of missing a second rebound within one long episode is an explicit
tradeoff to measure, not a reason to add hidden retry logic.

Apply this EOD transition order:

1. Valid opposite action from an eligible unused episode: transition to the opposite posture.
2. Otherwise, held age at least **65 sessions protected / 20 redeploying**: exit to neutral,
   including days with another same-direction action.
3. Otherwise, apply protect recovery or redeploy failure and record its specific reason.
4. Otherwise, retain posture and original entry. From neutral, enter only on a valid action from
   an unused episode; do not re-enter during the same transition that exits a posture.

Timeout is an administrative exit, not presumed success. Preserve raw signal/action diagnostics
even when a consumed episode prevents a new exposure entry; report the blocked transition reason.

## 6. Policy, Replay, And Storage

One canonical posture transition must feed snapshots, policy targets, exports, and replay.
`no_change` preserves the held target unless an explicit posture reset occurs. Do not wire policy
to the existing defective posture implementation before repairs. Bulltard remains a secondary
single-name input, never an implicit driver of aggregate exposure.

Add a deterministic daily exposure return stream and completed-posture attribution alongside
the existing signal-return tables. Use the permanent core plus a declared fixed tactical sleeve,
and compare with the same fixed allocation without timing. Start with ETF exposure, not option
payoffs or optimized allocation sizes.

Freeze executable timing, exposure weights, cash return, financing, turnover costs, and valuation
convention before scored comparisons. Recommended timing is next-session open; the prior exposure
owns the overnight return before that open. Use a consistent adjusted-price basis and explicitly
handle the final open episode rather than silently treating it as completed.

Distinguish entry adverse excursion (minimum closing return from entry) from running-peak
drawdown, and both from portfolio drawdown. Fixed-horizon returns grouped by posture are not
realized posture returns. Keep action-event, daily-diagnostic, and held-exposure denominators clear.

Store source observations under `data/observations`, calculated state under versioned
`data/snapshots`, and versioned XLSX/CSV/outcome exports under `workbooks`. Preserve v1.0 artifacts
for comparison. Use the central regime version `v1.1` when implementation starts writing the new
model; policy behavior changes require their own policy-version bump under `VERSIONS.md`.
Do not bump Bulltard. Same-version replacement remains allowed; no new overwrite/version flags.

The ordinary `daily`, `regime snapshot`, `report`, `outcomes`, and export workflows stay intact.
Use existing views for posture/gate diagnostics, not new required CLI paths or manual state inputs.
Research variants must be identifiable and isolated from canonical v1.0/v1.1 outputs, not three
different algorithms overwriting the same version/date. Keep test configuration internal.

## 7. Transmission Experiment

Freeze the corrected coverage/scoring/lifecycle/posture baseline before comparing variants:

| Variant | Continuous stress / qualifying arming score | Required setup legs | Comparison purpose |
| --- | --- | --- | --- |
| A: repaired baseline | `(T * V * X) ** (1/3)` | T, V, X | Existing three-leg contract with correctness repairs. |
| B: score control | `sqrt(T * V)` | T, V, X | A versus B exposes the combined change in score/release geometry. |
| C: transmission challenger | `sqrt(T * V)` | T, V | B versus C isolates relaxing the transmission gate. |

B still cannot qualify a day whose X leg fails. Each variant retains its ungated stress for release
and failure measurement, and its own episode peak. B/C use identical constants, hit rules, grace,
confirmation, posture rules, and source inputs. Keep current broad opportunity and the funding veto
fixed; those can still block redeploy after setup becomes eligible.

Do not frequency-match thresholds or optimize a pre-2022 sample to reproduce A's arming rate.
Report score trajectories, eligibility, arming, and actions separately. Constants across A/B are
research starting assumptions, not asserted equivalent calibrations. Direct breadth/OAS augmentation
is a separate same-date coverage comparison, not a hidden improvement supplied only to C.

Relaxing washout arming also affects protect: armed washout currently suppresses protect even
without a redeploy action. Evaluate both sides of the held policy, not only redeploy returns.

Variant A remains the default unless the study supports a coherent alternative. More coverage
alone is not better if it materially increases adverse excursion, churn, or withheld upside.
Do not select C because it catches one known bottom or delivers the highest in-sample average.

## 8. Evaluation And Corrected Reference Cases

Use a fixed, model-independent correction/recovery inventory. Include local recovery legs within
long underwater periods rather than waiting only for a new all-time high. Freeze its annotation
rule before comparing models. Future prices may define evaluation labels but never input signals.
Model-generated event-premium labels do not establish an event's causal origin.

For every episode, trace setup legs, input availability, qualifying hits, arm/expiry, stress/release,
confirmation, current opportunity, funding veto, raw action, and posture transition. Report all
failed/unknown gates, not just the first convenient explanation. Count unmatched alerts too.

The corrected v1.0 reference contains 29 redeploy days and eight lifecycle events over
2016-01-01 through 2026-09-01. Canonical event mean SPY returns are 5.056%, 5.346%, and 6.336%
over 20/40/65 sessions. The debug note's older averages and v0.0 action list were retracted;
its +11.4% 65-session daily-row statistic is not the event mean or portfolio return.

| Reference case | Required interpretation/check |
| --- | --- |
| February 2018 | Genuine missed recovery; trace its own failed gates rather than assuming the October 2022 cause. |
| December 2018 / January 2019 | v1.0 redeployed January 7, not December 12. A delayed entry is not automatically a complete miss. |
| October 12, 2022 | Trend 0.839 and volatility 0.577 passed; breadth 0.006 and credit 0 failed transmission. Direct breadth/OAS were unavailable. |
| October 21, 2022 | Stabilization 0.941 across three families, but washout unarmed. Check other current gates before claiming C would enter. |
| March and October 2023 | Diagnose each missed recovery separately; do not generalize one date's failure to the entire period. |
| December 8, 2021 / March 15, 2022 | Real entries with negative 40/65-session returns. March first gained about 3.2% at 20 sessions; distinguish early rebound, later failure, and held-position results. |
| March 13, 2023 | Warning plus `no_change`, not a protect misfire. Preserve warning/action separation. |
| March 4, 2020 / February 2, 2022 | v0.0 calls, not v1.0 calls. Check whether broader arming reintroduces premature entries. |

These are diagnostic cases, not a handpicked fitting sample. Include successful events, shocks,
false starts, added/removed entries, and no-action episodes. Report entry delay, 20/40/65-session
returns, adverse excursion, running-peak drawdown, turnover, and held-sleeve return/opportunity cost.
Use common clustering for cross-version comparisons and native lifecycle events as an additional
diagnostic. Keep coverage windows and overlapping economic episodes explicit.

Shock-excluded and leave-one-episode-out results are concentration checks, not untouched validation.
The reviewed 2016-2026 history has already influenced design. Freeze the selected specification
for prospective observation; inconclusive research is not permission for endless parameter search.

## 9. Implementation Sequence

| Step | Deliverable | Completion check |
| --- | --- | --- |
| 1. Coverage and reference audit | Rule/input matrix, historical coverage profiles, canonical generated event table, source/cache provenance. | Required versus supplementary inputs are explicit; no silent zero or version substitution. |
| 2. Evidence repair | Source-owned family votes, binary/graded helpers, second-family aggregates, coverage-aware gates. | Monotonicity, duplicate invariance, ownership, and missing-input tests pass. |
| 3. Lifecycle repair | Stable episode/peak/hit state, continuous stress/release, session checks, shared incremental transition. | Full backfill, resumed computation, and exports agree. |
| 4. Posture and policy | Explicit exits, fixed entry, episode consumption, transition attribution, policy integration. | All transition priorities, unknown cases, timeouts, and no-retry rules pass. |
| 5. Measurement | Daily exposure replay, posture attribution, separate MAE/drawdown, gate traces and stable cohorts. | Accounting reconciles with toy paths and an unchanged-exposure benchmark. |
| 6. Controlled research | Frozen A/B/C comparison, complete/reduced-input labels, per-episode tradeoffs. | No score/coverage/threshold changes between variants other than those declared. |
| 7. Release | Selected regime/policy versions, regenerated new-version artifacts, accurate docs and existing CLI views. | Correctness accepted separately from any claim of improved performance. |

Likely code ownership: `regime.py` for scores/state/actions; `market_signals.py` and source modules
for input/availability contracts; `policy.py` for consistent posture mapping and exposure research;
`regime_export.py` and `store.py` for faithful saved-state views; `cli.py` for existing report wiring;
`versions.py` for pillar versions. Extract focused helpers only where they remove duplicated logic;
do not make this a broad architecture rewrite.

## 10. Verification And Release Gates

Separate current-defect reproductions from new target-contract tests:

- Increasing same-direction evidence cannot reduce either family or aggregate confirmation;
  duplicate leaves cannot manufacture another family or strengthen a max.
- Flat credit with improving breadth/NFCI cannot create owned credit confirmation. Preserve the
  VIX-high/VVIX-cooling numerical pattern within volatility.
- True binary gate preserves 0.25; false produces zero; unknowns remain distinguishable. Graded
  combinations retain their specified behavior and cannot bypass substantive setup gates.
- Crossing 0.501 to 0.499 in a setup leg cannot create a large artificial release; coverage loss
  cannot create relief or a false stress increase.
- Interrupted persistence preserves identity/peak; only qualifying washout hits refresh grace;
  boundary ages, holidays, chain gaps, and initialized backfills behave as specified.
- Full and incremental replay match actions, episode identities, peaks, posture, and export state.
- Protect recovery requires all three sessions and actual owned entry-family damage checks;
  unknown evidence breaks the streak. Fragility/complacency cannot retain protection alone.
- Valid redeploy followed by simultaneous trend/volatility deterioration and rising stress exits;
  continuing elevated washout or fading pressure alone does not.
- Test every transition priority tie, original-entry preservation, 65/20-session caps, opposite
  actions, and no same-day or next-day reuse of a consumed episode.
- Next-open execution does not assign overnight returns to future exposure. Cash/financing/costs,
  entry adverse excursion, peak drawdown, and open episodes reconcile on deterministic paths.
- Preserve existing no-args-help behavior and ordinary commands. New-version writes leave older
  snapshots/workbooks intact; reports use the selected artifacts rather than reinterpreting them.

Run focused tests at each step, then the full suite and lint for the combined workflow/model change.
Code correctness is required to release the repaired baseline; improved alpha is a separate claim
requiring the declared evaluation and prospective evidence. If the challenger is inconclusive,
retain A and report its limitations.

## 11. Details To Freeze Before Their Implementation Step

The discussion agreed mechanisms, not every data or accounting choice. Resolve and record these
without tuning to outcomes:

- Per-rule required inputs, historical evaluation profiles, freshness/warmup treatment, and how
  incomplete research rows are excluded/labeled. Do not assume OAS or direct breadth backfills exist.
- Deterministic causal-family attribution when both protect confirmation branches pass, and the
  minimal persisted state needed for resumed lifecycle and episode-consumption parity.
- Exposure weights, execution/valuation convention, cash/financing/cost assumptions, and the
  model-independent recovery annotation rule before scored comparisons.
- Separate policy version and isolated research-variant artifact naming before writing outputs.

This proposal itself changes no code, active version, observations, snapshots, or workbooks.
Update README, ALGORITHM_DESIGN, IMPLEMENTATION_DESIGN, and VERSIONS to match delivered behavior
during implementation, not to describe these proposals as already implemented.
