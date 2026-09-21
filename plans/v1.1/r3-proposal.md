# V1.1 Round-3 Proposal: Distinct Actions, Causal Lifecycles, Measurable Exposure

**Author:** Codex
**Date:** September 21, 2026
**Status:** mechanism-level agreement recorded in R3 discussion T12; section 12 specifications
remain open. Not implemented. No active versions or artifacts change here.

This builds on [r2-proposal.md](r2-proposal.md) and the final agreements in
[r2-discussion.md](r2-discussion.md), incorporating both R3 reviews and the user's subsequent
decisions. Where this document explicitly changes R2, the R3 direction takes precedence for the
next implementation plan. Otherwise, retain the R2 correctness contracts summarized below.
Keep progress tracking in a separate document.

## 1. Objective And Scope

Improve marginal market exposure around a permanent SPY/QQQ-oriented core. Rare tactical actions
are acceptable, but broader opportunity coverage should come from distinct economic mechanisms,
not a lower cutoff or a target action count. More exposure is not automatically better timing.

The target has four explicit action types:

| Action | Economic thesis | Shared exposure intent |
| --- | --- | --- |
| `redeploy-washout` | Significant prior stress releases and recovery is confirmed. | Increase tactical exposure. |
| `redeploy-confirm` | An orderly pullback in an established trend confirms recovery without requiring panic. | Increase tactical exposure. |
| `protect-extension` | Prior extension and weakening support are followed by confirmed deterioration. | Reduce marginal exposure. |
| `protect-break` | Direct market-trend damage persists with supporting deterioration, without prior extension. | Reduce marginal exposure. |

`no_change` remains a no-new-action result, not a command to reset holdings. The normal, protected,
and increased-exposure postures remain shared; four mechanisms do not create four portfolios.
Returning from protection to normal exposure is separate from authorizing above-normal risk.

These are actual proposed action identities, not warning-only labels or explanatory text beneath
generic protect/redeploy buckets. Neither new path requires a preceding action from the old path.
Exact new predicates must be frozen before their implementation/replay step; open definitions are
listed in section 12 rather than hidden behind apparently executable prose.

### Changes From R2

| Area | R2 baseline retained for comparison | R3 direction |
| --- | --- | --- |
| Evidence and state | Owned votes, coverage semantics, continuous stress, stable episodes. | Carry forward, including the R2 discussion clarifications. |
| Washout setup | Controlled A/B/C transmission experiment. | Continue it; price damage plus volatility is the preferred hypothesis, not single-indicator arming. |
| Washout entry | Current broad washout and geometric strength remain mandatory. | Separately test price-opportunity expiry instead of continued fear. |
| Additional scale-up | No second executable path. | Add `redeploy-confirm` for a defined orderly pullback, not generic stabilization. |
| Extension protection | Existing entry predicate with correctness repairs. | Test remembered divergence followed by damage and separately test setup-decay eligibility. |
| Market break | Warning-only. | Redesign as the actual `protect-break` action; do not activate the old warning predicate unchanged. |
| Conflict handling | Armed washout suppresses protect entry. | Evaluate paths independently; resolve actual candidates, not setup flags or held-posture vetoes. |
| Measurement | Real held-exposure replay plus signal diagnostics. | Preserve four-action attribution and explicit overlap/exit diagnostics. |

Out of scope: trade execution, options payoff modeling, new sentiment subscriptions, fitted event
frequency, Bulltard-driven aggregate exposure, a generic model framework, automatic posture renewal,
and a third trend-continuation redeploy action. Correctness repairs should remain useful even if
the additional mechanisms do not demonstrate improved performance.

## 2. Evidence Audit And Review Disposition

The common reference window is **2016-01-04 through 2026-06-01**, the 2,617 rows in the reviewed
v1.0 export. Canonical v1.0 snapshots determine saved actions/state; canonical adjusted SPY
observations determine outcome labels. Workbooks are comparison exports, not model inputs.
Later prices through September 2026 supply labels only. Do not confuse this export window with
longer snapshot windows mentioned in earlier notes.

The record has eight redeploy lifecycle events and fourteen protect events. Redeploy mean SPY
returns are +5.056%/+5.346%/+6.336% at 20/40/65 sessions. These are signal-close forward labels,
not executable returns. Protect events all use extension unwind; regime-break has never been an
executed action in this record. Nearby events are not necessarily independent economic episodes.

### Findings Rechecked For This Consolidation

This table preserves the original claims and their audit trail. Claude subsequently corrected
the phase-veto count, return-horizon claim, and timing-clash summary in the source review, and
marked the peak-fear replacement as superseded. See R3 discussion T10-T12; these are no longer
unresolved disagreements between the reviews.

| Review claim | Canonical check | Disposition |
| --- | --- | --- |
| Washout and stabilization often fail to align. | 458 armed days, sixteen continuous armed periods, thirty-nine days meeting both old W >= 0.35 and S >= 0.75. Seven periods never align; five cross both thresholds separately, while two never cross one threshold. | Agree with Claude's detailed five-plus-two breakdown and corrected summary: 7/16 (44%) non-alignment, including 5/16 (31%) timing mismatch. Neither count predicts how many entries a challenger would produce. |
| Seven protect misses were caused solely by armed washout. | None of the seven cited dates passes all other extension-protect prerequisites. Across the window, only 2021-11-30 passes the local protect predicate and is then blocked by armed washout. | Reject the causal count and its claimed priority. Retain phase interaction as a legitimate design question. |
| March 10, 2020 was the COVID top, blocked only by old washout memory. | It is a later rebound; saved washout began February 24. Long-term trend, extension strength, and divergence also fail. On the actual February 19 peak, washout is unarmed. | Do not use this example as evidence of a stale, unrelated washout veto. |
| All fifteen regime-break warnings have positive returns at every 5-65d horizon. | All have positive 20/40/65d labels; their means are +4.189%/+5.936%/+7.227%. Seven date/horizon observations are negative at 5d or 10d, e.g. 2017-06-21 at 10d (-0.99%). | Accept poor evidence for the old bearish interpretation; reject the exception-free short-horizon claim and any validated contrarian-edge conclusion. |
| Generic strong stabilization is enough for another rare path. | The old-score rule `not armed AND S >= 0.75` matches 128 dates. A price-conditioned tightening was then selected around a few historical episodes. | Require an independently specified setup; do not adopt thresholds because they retain October 2022. |

The seven cited phase cases were 2016-01-20, 2018-03-23, 2018-12-07, 2018-12-19, 2020-03-10,
2022-03-07, and 2022-03-28. Missing extension arming, a broken long-term trend, insufficient
extension strength, and/or absent divergence independently block them. Displayed protect strength
is a maximum over different components, not proof that an actionable path passed.

The phase audit evaluates the prerequisites in `_protect_gate_result` from saved v1.0 state,
then the washout exclusion in `derive_regime_action_state`, both in
[regime.py](../../src/marketlab/regime.py). The single veto-only row is explicitly labeled
`washout_blocks_protect` in the
[2021-11-30 snapshot](../../data/snapshots/regime/market/2021-11-30/eod/v1.0/regime.json).
This is an audit of existing predicates, not a counterfactual performance replay. A redesigned
break path could interact with washout much more often; the corrected count does not settle that
future design question.

The studies' 5% and 6% turning-point inventories answer related but different questions. Do not
merge their denominators or use overlapping pivot windows to claim independent successful trades.
Use the corrected dates and full gate traces, not a nearby maximum-strength date described as the
actual trough. Both reviews contain useful hypotheses; neither supplies untouched validation.
Use the Codex investigation's Appendix A as the shared diagnostic inventory, with its declared
segmentation; retain Claude's inventory as a separate cross-check, not another denominator.
Positive warning-cohort returns do not establish a tradable contrarian edge: overlapping dates,
small episode counts, and the unconditional equity return remain relevant comparisons.

### Specific Recommendations Accepted Or Rejected

- **Accept:** the same-day fear/confirmation problem, compound strength barrier, wrong economic
  signs in fragility-based protection, distinct action reporting, and a separate 2022 cohort.
- **Reject as the preferred fix:** another trailing-K maximum of broad washout. It adds a second
  stress-memory window, does not measure remaining price opportunity, and leaves the strength
  restriction unless that is changed too. Retain one episode memory and current confirmation.
- **Reject:** remembered stabilization as a substitute for current confirmation. Old improvement
  must not authorize new risk after deterioration resumes.
- **Reject:** the proposed 60-day return <= -5%, S >= 0.85, three-family warning as
  `redeploy-confirm`. It targets repair after damage, not the agreed intact-trend pullback thesis;
  60-day return is already a price input, not an independent evidence family. Its selected
  thresholds and old aggregate-score meaning do not transfer to repaired confirmation.
- **Accept the diagnosis, reject the shortcut:** do not build `protect-break` merely by swapping
  fragility's stretch legs for washout legs. Direct price damage is the foundation; mandatory broad
  credit/funding extremes could again make entries late. Genuine credit/liquidity deterioration
  may corroborate; complacency must not be called damage.
- **Reject:** `posture != redeploying` as the protect gate. A held recovery can fail and require
  protection. This replacement would conflict with R2's valid-opposite-action transition.
- **Reject:** requiring negative average forward returns as the sole protect release criterion.
  Temporary risk reduction can be useful even when prices eventually recover. Test actual avoided
  losses against missed upside, costs, and restoration delay.

## 3. Evidence, Coverage, And Source Contract

Preserve deterministic Python-owned calculations and EOD inputs. Preserve source artifacts,
availability/provenance, and same-date volatility-ratio requirements. FRED remains current-vintage
local history, not a reconstruction of original releases. No silently selected latest version.

Distinguish observed zero, unavailable/insufficient/stale evidence, determinable eligibility, and
unvalidated eligibility. Declare each rule's input profile once, not anew according to the sources
available that day. Descriptive readings can remain supplementary without changing the rule.

For a declared alternative pool such as `credit = max(HYG/TLT, OAS)`:

- An observed 0.80 with the other leg missing establishes a lower bound of 0.80, not an exact score.
- A positive threshold can be proven from that bound where the operation is monotone. Two distinct
  family bounds can prove a second-highest confirmation threshold.
- A low observed value cannot prove recovery below a threshold. Exact stress arithmetic, changes,
  and release require comparable resolved inputs. Proving one predicate does not validate the
  complete action or erase coverage metadata. No general interval-arithmetic framework is required.

Funding veto remains `OAS stressed AND NFCI tight`: both true blocks redeploy; either known false
resolves it false; otherwise it is unresolved, not passed. This applies to both redeploy actions.
Absence of a new validated action is not automatically a posture reset when inputs are missing.

The investigated sample has no direct S&P participation observations, and credit-spread raw
values first appear in its snapshots on 2023-09-12. Six of eight redeploy events lack OAS.
Define complete and explicitly reduced-input research profiles; compare augmentations on common
dates. Do not claim full-input ten-year validation or silently replace missing OAS with calm.
An earlier fetch request is not a solution to the provider's historical-coverage limit documented
in R2. Preserve valid older local observations if they exist.

Keep descriptive pressure/fragility composition unchanged in the correctness baseline, including
intentional dual-use weakness features. Correct its consumers: remove fragility as a blanket
posture-reset veto and NFCI from credit-owned action helpers. New action predicates do not inherit
descriptive fragility simply because it already exists.

## 4. Canonical Confirmation

Carry forward R2's family ownership and numerical changes:

| Family | Owned numerical evidence |
| --- | --- |
| Trend | Existing short/medium SPY/QQQ momentum reading. |
| Volatility | Maximum of eligible VIX, VVIX, term-structure, and `vvix_vs_vix` readings, separately by direction. |
| Breadth | Participation turn under the fixed input profile. |
| Credit | Maximum of eligible HYG/TLT and OAS turns; no NFCI vote here. |
| Liquidity | NFCI turn. |

Paired explanations remain visible. Volatility-normalization and cross-family concordance do not
create extra votes. Preserve the high-VIX/cooling-VVIX recovery pattern inside volatility.
Source ownership prevents double counting; it does not assert statistical independence.

Boolean gates pass the owned score unchanged when true, zero when false, and preserve unresolved
dependencies. Graded pairs retain their explicitly named geometric operation where appropriate.
No `sqrt(1 * score)` inflation for a boolean condition. Audit callers by meaning.

Use the second-highest eligible family reading for aggregate deterioration/stabilization. Retain
R2's 0.75 strong stabilization threshold and 0.35 named-family confirmation threshold as research
starting constants, not probabilities. Do not increase thresholds to reproduce v1.0 frequency.
New paths must also satisfy their named evidence requirements; an aggregate cannot substitute for
required price damage, price recovery, or a missing setup.

The R2 repaired control preserves its 0.55 strength checks. R3 explicitly studies removing the
redundant current-fear/decayed-setup eligibility constraints below; it does not quietly remove
them from that control. Headline regime remains descriptive, never an extra action gate.

## 5. Setup State And Episode Identity

Retain the existing starting defaults for the extension/washout setup experiment:

| Parameter | Extension | Washout |
| --- | --- | --- |
| Strong hit | Setup >= 0.75 | Setup >= 0.75 |
| Persistent hits | >= 0.60 on 3 of 10 sessions | >= 0.60 on 2 of 5 sessions |
| Baseline required legs | Trend extension and volatility complacency each >= 0.50 | Trend/volatility washout each >= 0.50; breadth or credit washout >= 0.35 |
| Memory | 40 elapsed sessions from arm | 15 elapsed sessions from last qualifying hit |

Age zero is the arm/hit day; eligibility includes the final configured session. Eligibility and
a freshness weight reaching zero at that boundary are different facts. Do not silently change
one to match the other. Single extreme indicators do not establish washout by default.

Preserve episode start/identity and peak across interrupted qualifying hits. Washout qualifying
hits refresh the grace clock, not identity; extension retains its fixed-age rule. Track setup
start, last hit, continuous-stress peak, and actual posture entry separately. Posture exit does
not reset setup history. Comparable stress can update the episode peak while it is active.

Continuous stress is defined independently of categorical eligibility. In the repaired control:

```text
T = trend washout; V = volatility washout
X = max(breadth washout, credit washout)
stress = (T * V * X) ** (1/3)
eligible_hit = T >= 0.50 AND V >= 0.50 AND X >= 0.35
release = max(0, episode_peak_stress - current_stress)
```

Initialize peaks from the qualifying observations that establish an episode. Crossing a setup
threshold cannot manufacture release by zeroing stress; lost/changed coverage cannot establish
relief or worsening. Each research variant owns its own continuous stress, peak, and state.

Use one transition implementation for chronological backfill, incremental snapshots, policy,
exports, and replay. Validate continuity against canonical SPY trading sessions. Explain missing
intermediate snapshots with a backfill instruction; distinguish deliberate initialization from a
hole in an established chain. Persist enough state to resume without replaying all history daily.
Exports display saved state, not a competing full-history memory reconstruction.

Track the export defect explicitly in `regime_export.py`, as part of lifecycle repair rather than
only a general replay test. Compare saved episode identity, armed flag, age, peak, last hit, and
consumption where present against full and date-sliced CSV/XLSX output. Warm-state handling must
not invent a different episode at the export boundary. Matching armed booleans on checked dates
does not prove identity parity; differing identity dates do not by themselves invalidate same-day
boolean/score findings. Older artifacts remain faithful to their saved fields, without silently
reconstructing missing state using v1.1 rules.

The two new paths also require causal setup/episode definitions. Reuse this state machinery,
not necessarily identical arming rules. Neither a daily boolean flip nor a new action name may
create a fresh opportunity merely to bypass episode consumption.

## 6. Four Action Contracts

### 6.1 Redeploy-Washout

Arming recognizes prior stress; confirmation authorizes action. The preferred setup hypothesis
requires meaningful equity damage **and** volatility stress, without mandatory breadth/credit
deterioration. Relative resilience can coexist with absolute damage. Test this through the R2
transmission controls before claiming a better model.

The R3 entry challenger is:

```text
recent eligible washout episode
AND genuine release of comparable continuous stress
AND current strong confirmation from two distinct owned families
AND remaining price opportunity
AND funding veto resolved false
```

For exposure entry, the episode must also be unused. Retain release >= 0.05 and the declared
confirmation gate while testing the opportunity treatment. Historical improvement alone cannot
replace today's confirmation. Confirmation families need not be the same families that armed.

Replace the economic meaning of "still washed out today" with "not already too late to enter."
The opportunity rule must use causal episode price anchors, recovery distance, and bounded expiry.
Freeze the exact anchor/window, metric, and bound before replay. Do not use hindsight troughs or
select a bound to recover November 2023. No additional trailing-K fear window is proposed.

Remove both `W >= 0.35` and `sqrt(W * S) >= 0.55` as eligibility conditions in this challenger;
otherwise the same current-fear restriction survives indirectly. Keep W and the old strength
visible as diagnostics, not a replacement sizing probability. The repaired R2 control keeps both.

This can capture a rebound while the longer-term trend remains damaged. It does not promise a
65-day bottom or require the market already to have established a new uptrend. Falling washout
alone is not an exit. Candidate opportunity-completion exits are separate from entry expiry.

### 6.2 Redeploy-Confirm

An actual second-pass action for an orderly pullback, not generic stabilization without setup:

```text
previously established price trend and a distinct local pullback/consolidation
AND longer-term structure remains sufficiently intact
AND current price recovery with source-owned non-price confirmation
AND remaining price opportunity
AND funding veto resolved false
```

It requires neither armed washout nor a previous redeploy action. Evaluate it even when washout
is armed but the washout action fails; this is a different setup, not a `not armed` mirror rule.
Prefer `redeploy-washout` for the primary label if both qualify, while retaining both diagnostics.

Define prior-trend, pullback, recovery, opportunity-expiry, and episode-reset conditions before
implementation. Reuse existing observations and horizons where meaningful. Use owned trend
recovery plus a distinct non-price family; do not count SPY/QQQ or several volatility leaves as
independent confirmations. The starting confirmation contract is two strong families at the R2
threshold, including trend; no empirically selected 0.85/three-family escalation.

Price context must precede the recovery being judged. October 2021/April 2024 illustrate the
intended mechanism; December 2021/early 2022 are failure cases. October 2022 and November 2023
must not be relabeled intact-trend pullbacks merely because a broader definition would catch them.
Evaluate those damaged-trend cases primarily against `redeploy-washout`, including both failure
to arm and later entry restrictions. This is a diagnostic assignment, not a requirement that the
revised washout path fire on either date. Restoring normal exposure after protection needs neither
this intact-trend setup nor permission to add tactical exposure.

The holding thesis is trend resumption, not just a brief rebound. Its failure rule must identify
failed resumption and supporting deterioration; do not blindly copy a panic-specific stress test.

### 6.3 Protect-Extension

Preserve prior extension as the setup, but test the intended sequence explicitly:

```text
remembered extension
-> weakening internal support recorded within that episode
-> current price deterioration with supporting owned evidence
```

First apply R2's evidence fixes. Then test bounded remembered divergence followed by current
damage rather than requiring positive-momentum-conditioned divergence on the damage date.
Record causal families and recovery of their owned evidence; a price decline must not erase
previously observed divergence just because its original context condition becomes false.
Specify divergence validity/reset within the existing bounded episode before implementation.

Test requiring price deterioration for execution instead of the existing two-divergence-only
alternative. Preserve volatility/internal confirmation as named evidence in this comparison.
This can reduce false warnings but delay useful ones, including July 2024. Do not present that
tradeoff as an unconditional improvement or move an August 2025 warning earlier and call it alpha.

Separately test explicit armed eligibility plus confirmation without multiplying by decayed setup
strength. Keep expiry fixed; do not compensate by extending memory. The R2 control retains its
original strength requirement so the decay treatment has identifiable effects.

Retain the control's long-term-uptrend condition for this extension experiment. Once the market
is breaking without the required extension context, `protect-break` supplies the distinct thesis.
No change to extension arming geometry or volatility-complacency thresholds is bundled here.

### 6.4 Protect-Break

Redesign into an actual action rather than promoting the current warning unchanged:

```text
meaningful direct price-trend damage
AND deterioration from at least one other distinct owned family
AND a predeclared persistence condition
```

Do not require prior extension, a positive headline regime, or both indexes above MA200.
Neither high descriptive fragility nor high washout alone proves a breaking market. Genuine
credit/liquidity deterioration can support the price evidence; tight spreads or easy conditions
cannot stand in for damage. Do not require systemic credit/funding extremes for every price break.

Freeze direct damage, persistence, break episode identity, repair, and expiry before implementing
this path. Begin from existing owned evidence and the common named-family threshold; any added
price-structure condition must be causal and economically explained. Persistence trades earlier
coverage for fewer brief scares; no parameter is selected to eliminate the 2017 examples.

Assess remaining deterioration versus confirmed recovery when stress is high. Do not copy either
`not washout_armed` or `posture != redeploying` into this path. New protective entry and retention
of an existing protected posture are separate decisions. Define repair of the actual break, not
just a decline in the score that originally announced it.

## 7. Candidate Resolution, Held Posture, And Exits

### Independent Evaluation Before Resolution

Compute all four raw path predicates and failed/unknown gates before applying consumption or
conflict rules. A held position or armed setup must not hide what a path says. Distinguish:
raw eligibility, selected action, permitted exposure transition, and held posture.

Four-action integration must be explicit, not implemented by new strings falling through old
defaults. Define one version-aware action-to-direction mapping used by policy, posture, event
identity, reporting, and exports; retain each action's distinct setup and exit contract. Recognize
the saved v1.0 labels only in their versioned interpretation. Unknown action identities must fail
clearly rather than silently mean `maintain` or disappear from frequency tables.

Policy-decoupled research is acceptable only through an explicit internal experiment configuration:
retain raw eligibility and separately report whether exposure is enabled. Do not publish a selected
executable action while silently ignoring it in posture/policy. The four-action candidate replay
must exercise all four mappings; research-only diagnostics are not evidence of an implemented
exposure strategy. No additional daily CLI mode is required.

For same-direction overlap, use a fixed non-fitted priority for the primary action label:
`redeploy-washout` before `redeploy-confirm`; `protect-break` before `protect-extension` because
direct break is the applicable defensive thesis when both qualify. Keep all eligible paths and
their causal evidence. This priority is attribution, not added exposure or proof of superiority.

Apply episode consumption before resolving conflicts between new exposure entries. A consumed
same-direction signal may remain diagnostically true, but it cannot veto an otherwise valid
opposite entry. Same-direction evidence arriving while held is supporting, not another allocation.

For simultaneous opposing exposure-eligible directions, do not compare unlike strength scores. The
initial conflict contract is **no new directional entry while both remain eligible**. Report
the conflict and still evaluate the held posture's failure/recovery/timeout. An uncontested,
eligible opposite action can transition the posture under the order below. Test this explicitly;
do not let ambiguity freeze a failed position indefinitely. Retain the old phase veto only in
the repaired R2 comparison profile, not as a hidden rule in the R3 resolver.

### Fixed Identity And No Automatic Renewal

Persist entry date, action type, setup episode, causal families, price/risk reference, and selected
input profile. Repeated same-direction evidence does not restart age, create another trade, or
rewrite entry attribution. Maintain at most one exposure entry per direction per setup episode,
including after failure, timeout, or an opposite exit.

At entry, record same-direction overlapping eligible episodes as consumed for exposure allocation
so an alternative label cannot immediately re-enter the same opportunity. An overlapping signal
that arrives while exposure is already held must also be recorded as supporting rather than a new
allocation opportunity. Preserve raw diagnostics and report consumption reasons. Exact cross-path
episode association and any explicit thesis handoff are a freeze item before combined replay;
no implicit handoff may change entry attribution, restart the cap, or bypass the no-renewal rule.

### R2 Exit Baseline

Carry these repairs forward unchanged for the corrected comparison baseline:

- **Protect recovery:** three consecutive sessions with SPY and QQQ 5-session returns nonnegative
  and every causally contributing entry family's ungated owned deterioration below 0.35.
  Missing required evidence breaks the streak. Record only families actually used by the entry
  branch; define deterministic attribution if multiple branches pass.
- **Redeploy failure:** action-family trend deterioration >= 0.35 AND action-family volatility
  deterioration >= 0.35 AND comparable setup continuous stress rising from the prior session.
  These are deliberately two pipelines, not three pressure-level tests. Missing evidence cannot
  establish the conjunction. A renewed stress hit or fading washout alone is not failure.
- **Holding caps:** 65 protected / 20 increased-exposure elapsed sessions, without reset on repeated
  signals. These are starting limits, not optimized durations or guarantees against loss.

Apply the transition order after resolving candidates: (1) valid unused opposite entry;
(2) holding cap; (3) specified recovery/failure; (4) retain posture. From normal, enter only an
unused resolved opportunity. Do not exit and re-enter in the same transition. Conflict does not
suppress administrative timeout or an independently established exit.

### R3 Holding Semantics

Use path-specific economic exit definitions with the shared transition machinery. Extension
protection assesses recovery of its entry deterioration; break protection assesses repair of the
break. Neither can remain active solely because complacency, loose conditions, or an old setup
persists. Returning to normal exposure does not require a redeploy signal or authorize extra risk.

Washout recovery may be a shorter-lived rebound; confirmed pullback recovery assumes a resuming
trend. Specify failure separately where those meanings differ, without optimizing durations by
action. Report `thesis_failed`, `protection_recovered`, `opportunity_completed`, `holding_expired`,
and `opposite_action` as distinct causes where applicable.

An opportunity-completion exit is not enabled until a causal condition and transition priority
are frozen. Falling fear, a missing entry signal, or a hindsight profit target is not sufficient.
Retain the R2 exit behavior in its control. Completion/expiry of extra exposure returns to normal,
not automatically to protection. Keep actual exposure sizing in policy; normalized action strength
is neither a probability nor a proportional position-size instruction.

## 8. Controlled Research, Not A Combined Parameter Search

Freeze correctness, sources, timing, sizing, and an input profile before comparisons. Every variant
replays its own episodes, peaks, consumption, posture, and exposure from the same observations.
Copying baseline state into a challenger is invalid even if most predicates are unchanged.

| Experiment | Fixed control | Declared treatment |
| --- | --- | --- |
| R2-A | Repaired three-leg baseline. | Stress `(T*V*X)^(1/3)`, T/V/X eligibility, original entry/phase gates. |
| R2-B | Same control rules and constants. | Stress/arming score `sqrt(T*V)`, still T/V/X eligibility. |
| R2-C | R2-B. | Drop mandatory X eligibility; retain T and V. |
| W-opportunity | One predeclared A/B/C setup profile. | Replace both current-fear gates with the frozen price-opportunity rule; preserve release and current confirmation. |
| P-sequence | Corrected extension entry. | Bounded divergence history followed by current price damage, with no two-divergence-only execution shortcut. |
| P-decay | One frozen extension predicate. | Armed eligibility/expiry replaces decayed-setup strength as an additional entry condition; expiry unchanged. |
| P-resolution | One frozen set of raw path predicates. | Compare old washout veto with R3 candidate/transition resolution; trace all predicates, not just armed flags. |
| R-confirm | One declared repaired/selected overlay. | Add only `redeploy-confirm`. |
| P-break | The same declared overlay. | Add only `protect-break`. |
| Combined | Individually specified paths and resolver. | Four-action exposure replay with overlap and interaction attribution. |

A/B separates score/release geometry; B/C isolates mandatory transmission. W-opportunity must not
silently change stress geometry or retain the old strength veto. P-sequence is a declared combined
sequencing/confirmation hypothesis, not proof of each subcondition's independent effect. P-decay
and P-resolution remain separately attributable. Do not sweep all combinations or choose a variant
by the highest historical average. Document the chosen parent configuration before each experiment.

R2-A is a research control and fallback repaired baseline, not permission to reinterpret saved
v1.0 outputs. The requested R3 deliverable includes four executable action types in a fully specified
candidate model, even if a type has zero events. That does not oblige a claim of superior alpha or
default adoption of every challenger. Keep correctness, implementability, and economic acceptance
as separate decisions; report inconclusive or unfavorable results rather than tuning them away.

## 9. Outcomes, Exposure Accounting, And Acceptance

Existing `regime outcomes --by action` must show the four canonical action names, including zero
counts. Do not retain generic scale-up/down as the only grouping. Preserve broad direction as
a helper for policy, not as a competing action label. Keep old-version outcomes under their own
saved labels; no retroactive relabeling or recomputation with the new algorithm.
Keep `--by protect` and `--by redeploy` as directional diagnostics spanning their two respective
action types, not substitutes for `--by action`. Attribute events to explicit path episode IDs,
not an unknown-label fallback gap heuristic.

Separate daily signal frequency, first signal per path episode, selected action events, actual
posture entries, and completed/open holding episodes. Raw eligible-path cohorts may overlap;
selected entry attribution is single-valued. Show added-only, removed, overlapping, blocked, and
unknown cases. Compare native lifecycle events and a common cross-version clustering rule.

Replay the permanent core plus a declared fixed tactical allocation against the same allocation
without timing. Include comparable-average-exposure controls, so increasing risk is not mistaken
for timing alpha. Start with ETF exposure, not options or optimized sizes.

Use next-session-open execution; prior exposure owns the overnight move before that open. Freeze
weights, cash return, financing, costs, adjusted open/close valuation, and initial capital before
scored comparisons. An unavailable execution price must be reported, not replaced by a favorable
close. Carry warm state and consumed episodes across report boundaries; a sliced report must agree
with a whole-history replay initialized to the same valuation boundary. Do not close an open final
episode artificially to improve statistics.

Report held returns, turnover, time exposed, opportunity cost, entry adverse excursion, running-peak
drawdown, and portfolio drawdown distinctly. The existing `spy_dd` is closing loss from entry,
not intraday or running-peak drawdown. Preserve fixed 20/40/65-session labels as diagnostics, not
the realized performance of an action with a different holding period.

Use the full model-independent local decline/recovery inventory, including failed rebounds,
unmatched warnings, and multi-leg declines. Freeze its segmentation before comparisons; hindsight
labels cannot become live features. Report 2022 separately, and exclude/common-cluster 2020 entries
as concentration checks. Initial shock prediction is not the protect objective; shock recoveries
remain relevant to redeploy. Reviewed history is in-sample research, not a newly named holdout.

### Required Diagnostic Cases

| Cases | What must be explained |
| --- | --- |
| February/April 2018 and October-November 2023 | Armed stress versus later confirmation; do not conflate timing mismatch with failure to arm. |
| October 2022 | Absolute damage with resilient relative proxies; multiple gates can fail after transmission is relaxed. |
| November 2018 and early 2022 rebounds | Costs of broader recovery eligibility, not just missed eventual lows. |
| April 7, 2026 versus November 5, 2018 | Similar strength near-misses with different outcomes; no cutoff chosen to admit only the winner. |
| March 2022 and August 2019 | Fixed-horizon entry labels versus actual holding results. |
| January 2024 / August 2025 | Protection lingering after recovery, score inflation, and inverted divergence timing. |
| July 2024 | Early-warning benefit potentially lost by price confirmation; separately assess the early protective exit. |
| 2018 Q4 / 2022 / 2023 decline | Direct-break coverage, false breaks, restoration delay, and sustained damage without extension. |
| 2021-11-30 and the seven disputed phase dates | Distinguish a real final veto from failure of other prerequisites. |

No minimum action frequency, minimum number of recovered bottoms, or mandatory negative protect
forward mean. New paths must justify complexity through net exposure results and interpretable
tradeoffs. Freeze the chosen specification for prospective observations; no endless parameter
search if the historical comparison is inconclusive.

## 10. Storage, Versions, And Workflow

Regime target version is **v1.1**, portfolio policy **v0.1**, Bulltard **v0.0**. Bump only during
implementation. Preserve canonical v1.0 snapshots and versioned workbooks/outcomes. Same-version
replacement remains allowed. No new overwrite flags or daily path-selection requirements.

Source observations stay under `data/observations`; calculated state belongs under
`data/snapshots`; versioned exports under `workbooks`. Isolate internal research variants by
configuration/input-profile identity outside canonical version/date artifacts. Never overwrite a
canonical v1.1 output with an experimental algorithm sharing only the version string.

Use pillar defaults for ordinary workflows. Fix internal explicit-version calls so regime input,
Bulltard input, and policy output can select different versions and persist their dependencies.
The ordinary default path is not the defect; the existing single explicit override is. Test both
with older same-date artifacts present. No new required CLI arguments or silent latest selection.

Snapshots, policy, report, export, and outcomes must share the canonical saved state/transition.
The user continues using `daily`, `regime snapshot`, `report`, `outcomes`, and export. Preserve
no-args-is-help, strict requested-EOD source checks, and clean chain/backfill errors. Bulltard
remains secondary and its private capabilities remain redacted.

## 11. Implementation And Verification Sequence

| Step | Deliverable | Required check |
| --- | --- | --- |
| 1. Reference/coverage | Canonical event/gate audit, fixed source profiles, corrected evidence register. | No workbook/cache substitution, missing-as-zero, or unsupported phase causality. |
| 2. Evidence repair | Owned maxima, binary/graded split, second-family confirmation, coverage-aware predicates. | Monotonicity, duplicate invariance, cross-family ownership, preserved VIX/VVIX pattern. |
| 3. Lifecycle repair | Stable identity/peak/last-hit state and continuous release in one transition. | Interrupted hits, boundary ages, holidays, gaps, full/resumed/export parity. |
| 4. Posture/accounting | Correct R2 exits, episode consumption, mixed-version policy routing, exposure replay. | Fixed entry/caps, opposite-action transitions, warm-start parity, next-open accounting. |
| 5. Existing-path experiments | Frozen A/B/C, opportunity, extension-sequence/decay, resolution comparisons. | Isolated state and declared treatments; harmful and beneficial changes both reported. |
| 6. New paths | Frozen pullback and break definitions, four named actions, path-specific episode/exit rules. | Actual actions, not warning aliases; independent standalone comparisons. |
| 7. Combined candidate | Resolver, overlap attribution, four-action outcomes, faithful saved-state exports. | One exposure decision, no label-based renewal, all exit/conflict cases reachable. |
| 8. Release decision | Selected configuration/versions, regenerated new-version artifacts, accurate operational docs. | Correctness and performance conclusions stated separately; no historical overwrite. |

Likely code ownership remains `regime.py`, market-signal/source modules, `policy.py`, export/store,
CLI wiring, and central versions. Extract focused helpers where shared transitions remove genuine
duplication; do not create a general-purpose strategy framework.

Additional named acceptance tests:

- A 0.501-to-0.499 eligibility crossing cannot create artificial stress release. Missing coverage
  cannot create relief or prove a protective recovery.
- Partial observed support may prove a positive threshold but not an exact score or a below-gate
  recovery; two readings from one family cannot prove two-family confirmation.
- Recompute an end-to-end synthetic setup, valid redeploy, and subsequent failure **before the
  twenty-session cap** from observations, not just three assigned scores. Test nearby non-failures.
- Falling fear during valid recovery does not exit by itself. A still-armed setup cannot override
  established failure. A genuinely valid protect action can interrupt a held redeploy posture.
- Recovery of protective causes restores normal exposure without either redeploy action.
  Complacency/fragility alone cannot keep protection active.
- Earlier divergence survives a negative-momentum context switch within its declared validity;
  it does not remain actionable indefinitely after repair/expiry.
- Break protection can qualify without extension or above-MA200 prices; high fear alone cannot
  authorize it, and an armed washout does not suppress its diagnostic evaluation.
- Both same-direction overlaps and opposing candidates preserve evidence and deterministic
  selection. Conflicts cannot suspend timeout/failure; repeated labels cannot reset entry age.
- Actual exposure and cost accounting reconcile with toy paths and unchanged-exposure benchmarks;
  final open holdings and sliced reports are handled explicitly.
- Old/new version coexistence, canonical/research isolation, zero-event action rows, no-args-help,
  and all ordinary workflows pass integration checks.
- Each of the four action identities reaches the intended policy direction, held transition,
  episode deduplication, diagnostic bucket, and export. Unknown identities fail; explicitly
  disabled research candidates remain visible without being counted as executed entries.
- Full and sliced CSV/XLSX exports preserve canonical lifecycle fields, including interrupted
  hits and an episode starting before the requested export window.

Run focused tests at each step, then the full suite and lint for the combined implementation.

## 12. Definitions To Freeze Before Their Step

This proposal selects mechanisms and experimental boundaries, not fitted new constants. Before
their implementation step, record the following compact specifications in the progress/design
record, with causal definitions and economic rationale, before looking at variant outcomes:

1. Required/supplementary input profiles, freshness/warmup, incomplete-score handling, and exact
   accounting assumptions. Preserve the accepted lower-bound versus exact-score distinction.
2. Remaining-opportunity price anchor, distance metric/bound, and expiry for each redeploy path.
   No separate K-session fear maximum or remembered confirmation substitute.
3. Prior-trend, pullback onset, intact-structure, recovery, failure, and episode-reset rules for
   `redeploy-confirm`; direct damage, persistence, repair, and episode identity for `protect-break`.
4. Bounded divergence validity/repair within extension episodes and the separately controlled
   setup-decay treatment. No memory extension selected to recover a named historical case.
5. Cross-path episode association, consumption of overlapping opportunities, and any explicit
   same-direction thesis handoff. Original entry attribution and holding caps cannot silently reset.
6. Path-specific exit attribution and any opportunity-completion predicate/priority. Leave that
   exit disabled until defined; do not silently invent a profit target during implementation.

These are blockers for the affected experiment, not reasons to delay the settled correctness
repairs. Do not present an unspecified combined model as ready for a canonical replay. Implement
the selected contracts without daily manual state inputs, extra command paths, or parameter sweeps.

## Sources And Relationship To Earlier Documents

- [R2 proposal](r2-proposal.md): correctness/control baseline.
- [R2 discussion](r2-discussion.md): accepted coverage, policy-version, reachability, version-routing,
  independent-state, and warm-start clarifications, now incorporated here.
- [Codex R3 review](r3-review-codex.md): user-requested four-action design and lifecycle refinements.
- [Claude R3 review](r3-review-claude.md): alignment analysis, fragility diagnosis, and alternative
  proposals; corrections and rejected recommendations are explicit in section 2.
- [R3 discussion](r3-discussion.md): topic-local replies and agreed clarifications, including
  export parity, action integration, and the distinction between agreed mechanisms and unfrozen rules.
- [Codex investigation](backtest-investigate-codex.md) and
  [Claude investigation](backtest-investigate-claude.md): empirical research, not untouched validation.

This proposal changes no code, active version, observations, snapshots, or workbooks. Update README,
ALGORITHM_DESIGN, IMPLEMENTATION_DESIGN, and VERSIONS to describe delivered behavior during
implementation, not to represent this proposal as already shipped.
