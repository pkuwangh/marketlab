# R3 Review: Broader Opportunities, Not Weaker Signals

**Author:** Codex
**Date:** September 20, 2026
**Status:** design proposal for discussion; not implemented or an amendment to the accepted R2 baseline.

## 1. The Problem Is Scope, Not A Target Event Count

The central observation from section 3 of
[the backtest investigation](backtest-investigate-codex.md#3-are-the-events-too-rare-and-are-their-returns-good)
is:

> Rare actions are acceptable for a tactical sleeve around a permanently invested core. They are
> not enough if the intended product is a general opportunity engine. More events should result
> from a distinct economic opportunity, not from a target event count or a lower cutoff.

These are different objectives:

| Objective | What a quiet model means | Appropriate test |
| --- | --- | --- |
| Rare-event tactical overlay | Usually leave the invested core alone; act only around unusual dislocations. | Does the overlay improve the core's return/risk tradeoff after realistic holding periods and costs? |
| Broader market opportunity engine | Recognize several economically different reasons to increase or reduce marginal exposure. | Does each additional path contribute useful opportunities beyond the existing paths and the invested core? |

The permanent core already participates in ordinary market gains. Missing a tactical scale-up
is therefore not equivalent to missing the entire rally. Nevertheless, an engine that can only
increase risk after panic has a narrow opportunity set by construction.

V1.0 has eight redeploy events across 2,617 sessions. Its 20-day SPY mean is +5.06% versus +1.27%
for all days, but longer-horizon advantages weaken. That is neither proof that eight is enough
nor a reason to demand twenty. The right question is **which economically justified opportunities
are outside the model's scope, and whether capturing them adds value**.

**Recommendation:** retain the permanent-core architecture, but evolve the tactical engine toward
a small number of distinct opportunity paths. Do not turn it into an always-active market timer.

## 2. Separate Three Decisions

| Decision | Meaning | Requires a positive scale-up thesis? |
| --- | --- | --- |
| Retain normal exposure | Continue the core and the declared normal tactical allocation. | No. This is the baseline, not a daily bullish prediction. |
| Restore normal exposure | End an earlier defensive reduction because its causal evidence has recovered. | No. Ending protection is not the same as establishing an opportunity for extra risk. |
| Add tactical exposure | Increase exposure above that normal baseline for a bounded opportunity. | Yes. Require a named setup, confirmation, and invalidation. |

The actual exposure amounts belong to policy, not the signal model. "Normal" must be an explicit
research baseline, not a number inferred from whichever action last appeared.

The immediate priority is still the R2 posture repair: protection must be able to end without
a subsequent crash and panic-redeploy signal. Otherwise, adding another bullish entry path can
hide a broken defensive exit rather than improve opportunity detection.

## 3. Proposed Opportunity Paths

### A. Washout Recovery: Keep The Distinct Thesis

**Hypothesis:** a substantial stress episode can create a temporary opportunity when selling
pressure releases and independent evidence confirms stabilization.

Retain remembered stress, genuine release, and owned confirmation. Fix their numerical and
lifecycle defects before evaluating broader eligibility. Improve this existing path separately
from adding orderly pullback recovery; do not label every ordinary dip a washout.

#### Arming And Confirmation Have Different Jobs

| Stage | Question | Proposed evidence |
| --- | --- | --- |
| Arm washout | Has meaningful stress occurred? | Meaningful equity-price damage plus elevated volatility stress. |
| Confirm redeploy | Is that stress resolving into an actionable recovery? | Genuine stress release and strong improvement across two distinct, source-owned evidence families. |

Arming means a potential opportunity exists and should be watched. It does **not** authorize
additional exposure. This permits broader recognition of a legitimate setup while keeping the
action selective.

Count evidence families, not ticker or indicator counts. SPY and QQQ damage are predominantly
one price-family observation; VIX and VVIX stress belong to one volatility family. Multiple
related indicators may improve measurement without supplying independent confirmations.
Distinct source ownership also does not imply statistical independence between families.

The proposed washout experiment still requires **both price damage and volatility stress**.
It removes mandatory additional breadth/credit deterioration, not the requirement for multiple
economic dimensions. Relative outperformance can coexist with substantial absolute damage,
as October 2022 demonstrates. Breadth and credit remain useful context and recovery evidence;
funding-risk checks remain separate, with missing inputs treated explicitly rather than as calm.

One extreme indicator alone is **not sufficient by default**. For example, volatility stress
without meaningful equity damage could reflect anticipated event risk rather than an already
created recovery opportunity. Single-family arming would require its own hypothesis and test,
not an implicit extension of this proposal. Keep persistence and episode-memory semantics
explicit; broader eligibility does not mean every one-day spike becomes a new opportunity.

#### Falling Fear Is Not The Same As An Exhausted Opportunity

November 2023 illustrates a different problem: washout memory was armed and confirmation was
strong, but fear had already fallen below the current-washout requirement. Memory alone cannot
solve this while entry still requires substantial fear on the confirmation day.

The candidate decision should instead distinguish:

```text
recent, unused washout episode
AND genuine stress release
AND strong confirmation from two distinct evidence families
AND price opportunity not already exhausted
AND funding-risk checks passed
```

Stress release should support the recovery thesis. Whether entry is now too late should be
tested through a separately defined, causal price-recovery measure and bounded episode expiry,
not by demanding continued fear. Track any episode low using only observations available at
that EOD, never the retrospective trough labels from the investigation.

This requires examining **both** the current-washout floor and its role in
`sqrt(current_washout * stabilization)`. Removing only the explicit floor leaves an implicit
current-fear requirement in the strength gate. Freeze the replacement opportunity rule before
replay; no price-distance cutoff or expiry window is selected here. Keep this experiment
separate from removing mandatory breadth/credit transmission.

#### Confirmation Uses The Same Evidence Principle, Not The Same Setup Test

Implement the R2 source-owned family maxima and second-highest-family confirmation. A weaker
additional reading must not dilute a stronger eligible reading within its family; duplicated
transformations must not create additional family votes. Preserve the declared coverage rules.

The confirmation families need not match the arming families. Price damage and volatility
stress could establish the setup; price recovery and improving participation could later
confirm it. Two strong confirmation families do not require every observed indicator to agree.

The shared principle is meaningful evidence without redundant requirements. The distinction is
**past stress levels versus current recovery evidence**. April 2026 motivates repairing the
aggregation semantics, not lowering a strength threshold just enough to admit that date.
November 2018 and early-2022 failed rebounds must remain in the evaluation alongside missed
recoveries.

Failure means the recovery thesis breaks, not simply that the washout score falls. This is a
recovery trade hypothesis, not a promise that a durable market bottom has formed. Retain the
R2 held-posture work: genuine thesis failure, a valid opposite action, or the declared holding
limit should determine exit. Evaluate the exposure actually held, not just forward-return labels.
Section 4 additionally proposes explicit opportunity-completion semantics for R3; do not silently
add that exit to the repaired R2 baseline before defining and evaluating it separately.

### B. Orderly Pullback Recovery: The Next Path To Study

**Hypothesis:** a temporary correction within a previously established trend can offer attractive
marginal exposure when price and participation recover, even without widespread panic or credit
stress. Requiring systemic damage would reject the very context this path is intended to capture.

Its proposed contract is:

| Stage | Required meaning | What it must not become |
| --- | --- | --- |
| Prior context | An established, observable price trend before the pullback, with its longer-term structure still sufficiently intact. | A gate based on the coarse headline regime score, or today's bounce retrospectively proving an uptrend. |
| Setup | A distinct local pullback or consolidation that interrupts that trend. | An entry on every rising day, or a retrospective trough only identifiable after the rally. |
| Confirmation | Renewed price strength plus source-owned participation or another justified non-price confirmation. | Several transformations of the same price movement counted as independent evidence. |
| Opportunity remaining | Entry is still close enough to the developing recovery to justify the incremental risk. | Requiring continued panic, or chasing a move after most of the hypothesized opportunity has passed. |
| Invalidation | Renewed price deterioration with supporting evidence that the pullback is becoming a broader break. | Automatically waiting for a major washout, or calling every temporary adverse move a failed thesis. |
| Lifecycle | One bounded opportunity episode, with explicit completion, failure, and expiry. | Repeated entries counted as independent discoveries, or an indefinite bullish posture. |

Start with existing price, volatility, breadth, and credit observations. No new data subscription,
sentiment feed, or generic model framework is required to specify the hypothesis.

Expose this as the separate action **`redeploy-confirm`**, with **`redeploy-washout`** naming the
washout-recovery action. Evaluate it as a second-pass opportunity when the washout path does not
qualify. It must not require a preceding washout action or armed washout episode; that would
preserve the coverage restriction this path is intended to address. Both actions require
confirmation: the names distinguish their setups, not confirmed versus unconfirmed entries.

October 2021 and April 2024 illustrate the intended opportunity; December 2021 and early 2022
are necessary counterexamples. Being above a moving average does not prevent an impending
trend break. These cases motivate the hypothesis but cannot select its parameters.

This is **not yet an executable rule specification**. Before replay, freeze the causal trend,
pullback, recovery-distance, confirmation, and failure definitions in one bounded experiment.
Reuse existing feature horizons where appropriate; do not introduce a grid of alternatives and
choose the combination that catches these named examples.

### C. Trend Resumption: Defer Until B Is Measured

**Hypothesis:** a consolidation followed by renewed price and participation strength can support
continuation without preceding panic or a meaningful correction.

This may eventually cover another opportunity class, but it overlaps with orderly pullback
recovery and risks becoming a generic momentum rule. Do not implement both at once. First ask
whether B leaves a distinct, economically coherent gap that C would address.

The design does not need a symmetric number of protect and scale-up paths. Every path must earn
its place through a distinct mechanism and incremental evidence, not visual balance in a diagram.

### D. Market Break: Promote To A Separate Protect Action

The requested R3 direction includes **`protect-break`** as an actual defensive action, alongside
**`protect-extension`** for deterioration after remembered extension. This explicitly expands
the R2 proposal, which leaves regime-break warning-only; the R2 document is not changed here.

The weak protect outcomes in the investigation belong to the existing extension-unwind action.
They are not a backtest of `protect-break`: the existing regime-break path only emitted warnings.
Neither its promotion nor a large displayed protect-strength score establishes a useful new action.

`protect-break` must be able to act without prior optimism or an intact long-term uptrend. Its
thesis is that an established price trend is breaking with supporting source-owned deterioration,
not that it predicted the original peak. Define direct damage, confirmation/persistence, recovery,
and expiry before implementation. Also define its interaction with an armed washout so that it
neither inherits an unexplained blanket veto nor becomes an automatic seller after severe damage.

Do not promote the existing `regime_break_warning` predicate unchanged merely by renaming its
output. Its fragility input mixes economic meanings and was not validated as an entry/exit rule.
The intended deliverable is a separately specified action capable of changing held exposure,
not another warning row. Evaluate ordinary declining markets, false breaks, late entries, and
recovery opportunity cost; predicting an initial exogenous shock is not its objective.

The starting hypothesis is:

```text
meaningful price-trend damage
AND supporting deterioration from another distinct, source-owned evidence family
AND evidence that the break is persisting
```

Use direct damage rather than a mixture of complacency and relative weakness as the entry
foundation. Neither the coarse headline regime score nor a requirement to remain above MA200
should decide eligibility. Define one simple persistence rule before replay. Persistence may
reduce false alarms but delays protection; measure that cost instead of adding exceptions until
every historical correction is captured. Exact damage and persistence thresholds remain to be
specified, not selected from the named cases.

High stress alone should neither trigger nor veto this action. Distinguish continuing damage
from a recovery being confirmed. Also distinguish a proposed new defensive entry from retaining
an already justified protected posture: an armed washout must not automatically cancel either
decision without evaluating the relevant evidence. Freeze these interaction rules before replay.

### E. Extension Protection: Repair The Sequence

The intended mechanism is sequential:

```text
prior extension
-> weakening internal support
-> price deterioration confirms the risk
```

Treat internal divergence as bounded setup evidence that can precede price damage. Confirmation
must use current, source-owned deterioration that does not disappear simply because price
momentum turns negative. The August 2025 example shows why a positive-price-momentum gate must
not erase earlier divergence and then reactivate protection on the rebound.

Implement the R2 binary-gate repair first: a passed condition must not inflate an owned score
through a square root. Then separately test remembered divergence followed by damage rather
than requiring divergence and damage on the same day. Preserve causal episode identity and
explicit recovery/expiry; do not retain old divergence indefinitely or introduce an unrelated
memory subsystem merely for this feature.

Separate setup eligibility/expiry from freshness scoring. Investigate whether an explicitly
armed setup plus current confirmation is sufficient, rather than additionally requiring a
product with a decaying setup score. The July-August 2023 case shows that an armed flag can
otherwise remain true while its effective strength becomes unusable. This is a separate test,
not permission to extend memory until a desired historical signal fires.

To reduce false positives, test requiring actual price deterioration for the executable action,
instead of allowing two divergence readings alone to trigger protection. Divergence can remain
an early setup warning. This sacrifices some advance notice, potentially including the useful
July 2024 call; compare timing, losses avoided, and false alarms rather than assuming the stricter
rule is unconditionally better. Moving the August 2025 call earlier would not itself establish
an economic benefit either, because that market rebounded.

## 4. Explicit Actions, Shared Exposure Management

Make the economic mechanisms distinct **action types**, not just reasons beneath a generic
protect/redeploy action. These are proposed new-version names, not claims about current v1.0
labels or permission to relabel historical artifacts:

| Action | Economic mechanism | Exposure intent |
| --- | --- | --- |
| `redeploy-washout` | Significant prior stress releases and recovery is confirmed. | Add bounded tactical exposure. |
| `redeploy-confirm` | An orderly pullback in an established trend confirms recovery without requiring panic. | Add bounded tactical exposure. |
| `protect-extension` | Remembered extension/optimism is followed by deterioration. | Reduce marginal exposure. |
| `protect-break` | A market trend breaks with supporting deterioration, without requiring prior extension. | Reduce marginal exposure. |

Retain a no-new-action result when none qualifies. Four action types do not require four
independent portfolios: they feed the same normal, protected, and increased-exposure posture
categories. Restoring normal exposure remains distinct from authorizing extra risk.

Several hypotheses must not produce several competing portfolio controllers.

- Keep setup, confirmation, and causal entry evidence attributable to their named path.
- Feed eligible paths into one deterministic posture/policy decision under the same bounded
  tactical risk budget. Two agreeing bullish paths must not automatically double exposure.
- Distinguish a repeated confirmation, a new opportunity, a return to normal, and an increase
  above normal in replay. They are not interchangeable events.
- Preserve the selected action type and causal entry evidence through snapshots, held posture,
  exports, policy, and outcomes. A later same-direction signal from another path must not silently
  rewrite the original entry attribution, create a second trade, or restart the holding clock.
- Freeze conflict handling before combining paths. An active, valid protect thesis should not
  be canceled merely because a bullish path has a larger score on a different scale. Ending
  protection and authorizing extra exposure require their respective conditions.
- Do not combine different setup scores into an opaque universal "opportunity score." Their
  economic meanings and invalidation conditions differ.

### Redeploy Holding And Exit Contracts

Separate entry actions also need explicit holding theses. Sharing an increased-exposure posture
does not mean that every action must use an identical exit predicate or promise the same horizon.

| Action | Holding thesis | Failure to detect |
| --- | --- | --- |
| `redeploy-washout` | Participate in a confirmed rebound after stress; the longer-term trend may still be damaged. | Renewed price deterioration with supporting evidence that stress/recovery conditions are worsening. |
| `redeploy-confirm` | Participate as an established trend resumes after an orderly pullback. | The attempted resumption fails and supporting deterioration indicates a broader trend break. |

Do not require washout recovery to prove that a durable bull market has begun. Conversely, do
not let a brief rebound alone establish the intact-trend thesis of `redeploy-confirm`. March
2022 illustrates the distinction: a useful short rebound can coexist with poor 40/65-day labels.
Neither fact alone establishes the quality of the actual held trade.

Specify the economic exit conditions per action before replay. Reuse lifecycle machinery and
parameters where their meaning is genuinely shared; separate action names are not a reason to
invent different holding limits or optimize each path's duration against past returns.

Record distinct exit reasons:

- **Thesis failed:** observable evidence invalidates the recovery or trend-resumption thesis.
- **Opportunity completed:** a predeclared, causal condition says the temporary reason for extra
  exposure has been exhausted. This is not simply a falling washout score, a missing entry signal,
  or a hindsight profit target. Define and test this condition before enabling it.
- **Holding period expired:** the declared exposure limit is reached, even if the thesis has
  neither clearly failed nor completed.
- **Valid opposite action:** a separately eligible defensive action causes a transition under
  the explicit conflict rules; preserve that cause rather than reporting a generic reset.

Falling fear can mean the recovery is working. It must not by itself force an exit. Renewed
deterioration can invalidate a recovery while its original setup remains armed; setup memory
is not permission to ignore new evidence. Completion and expiry normally return extra exposure
to normal, not to a protected posture without a valid defensive reason.

### Protect Holding And Recovery Contracts

Record the causal entry evidence, then assess recovery of that evidence rather than continued
presence of a broad setup or fragility score:

| Action | What justifies continued protection | What recovery must assess |
| --- | --- | --- |
| `protect-extension` | The deterioration that confirmed the remembered extension remains unresolved. | Recovery of the actual entry-confirming damage under the declared recovery rule. |
| `protect-break` | The directly observed market break remains unresolved. | Repair of the break and its supporting deterioration under a separately specified rule. |

Low credit spreads, loose financial conditions, complacency, and an old extension setup must
not independently keep protection active after its causal deterioration has recovered. January
2024 illustrates the opportunity cost of that behavior. Conversely, the July 2024 early exit
shows that a useful entry does not establish an adequate holding rule.

Keep the R2 causal-family recovery repair as the initial extension baseline. Define break repair
explicitly rather than assuming that copying the extension exit is economically appropriate.
Missing required evidence is not proof of recovery. Neither action should require a subsequent
redeploy signal merely to restore normal exposure.

### Restore Normal Exposure Independently

Ending a defensive reduction does not require either redeploy action. When the causal reasons
for protection have recovered under the specified exit rule, and no other valid defensive
condition requires protection, return to the declared normal tactical exposure. Additional risk
still requires its own eligible action. This avoids waiting for an exceptional buying opportunity
merely to undo an obsolete defensive position.

### Signal Eligibility Is Not Position Size

Keep action eligibility in the regime engine and actual exposure sizing in policy. A strong
recovery signal does not establish low remaining risk; the 2020 washout entry combined attractive
forward returns with substantial early adverse movement.

Do not interpret a normalized strength score as a probability or scale exposure proportionally
to it by default. Evaluate action changes first under the same declared sizing policy and bounded
tactical risk budget. Any later risk-sensitive sizing experiment must have its own assumptions
and attribution; it must not obscure whether the entry/exit mechanism improved.

### Selection And Backtest Attribution

- `regime outcomes --by action` should show the four named action types separately, including
  zero-event types, with event counts and forward outcomes. Held-exposure results must also retain
  the entry type so that signal quality and actual holding performance can be compared.
- For the redeploy second pass, prefer `redeploy-washout` when eligible; otherwise evaluate
  `redeploy-confirm` for selection. Compute and retain both paths' eligibility for diagnostics,
  even when the first path supplies the selected action.
- Record all qualifying paths, but select at most one exposure transition per date. Specify a
  deterministic rule for simultaneous protect paths and opposing directions before combined
  replay; do not choose by the largest score across differently defined mechanisms.
- Selected-action event cohorts have one primary attribution. Standalone eligible-path cohorts
  may overlap and must be labeled as such; their returns or counts cannot simply be added.
- Report the combined exposure result without double counting overlapping signals or repeated
  confirmations. Separately show what each path adds when evaluated alone and in combination.

**Workflow remains unchanged:** `daily`, `regime snapshot`, `regime outcomes`, and the existing
export workflow. Path detail belongs in the normal output and diagnostics. The user should not
have to select a model path every morning. No trade execution is proposed.

## 5. How To Decide Whether The Broader Engine Is Better

Compare systems under the same exposure budget and execution assumptions:

1. The permanent core with a fixed normal tactical policy.
2. That baseline plus the repaired rare-event overlay.
3. The same overlay plus orderly pullback recovery.
4. The repaired overlay plus direct-market-break protection, without the new pullback path.
5. The repaired overlay with both new action types.

Each addition must justify its incremental complexity relative to system 2; the combined system
must also expose interactions between the additions. A higher number of signals or a positive
forward return does not satisfy that requirement. Increasing average
market exposure can raise returns without demonstrating timing skill; include a comparable
average-exposure control rather than attributing all additional gains to the new path.

Evaluate net held-exposure returns, portfolio drawdown, adverse excursions, time exposed,
turnover, and protection opportunity cost. Show timing and performance of new-only entries,
overlapping entries, and failures. Preserve fixed-horizon event labels as diagnostics, not as
the primary portfolio result. A shorter-horizon path should not be judged as if it promised a
65-day bottom call.

Add explicit lifecycle acceptance cases alongside historical comparisons:

| Case | Required behavior |
| --- | --- |
| Washout falls while recovery remains valid and no other exit qualifies. | Do not exit solely because fear or the original entry score subsides. |
| Recovery fails while the original setup remains armed. | Apply the defined failure rule; arming cannot override invalidation. |
| Protection's recovery rule passes, neither redeploy action qualifies, and no other protection is required. | Restore normal tactical exposure without adding extra risk. |
| A distinct completion condition or the holding limit is reached. | Preserve the specific exit cause and original entry-action attribution. |
| A valid opposite action or multiple exit conditions occur together. | Use a frozen transition priority and retain the evidence behind the selected reason. |
| Another same-direction action appears during a held episode. | Do not silently restart its age, rewrite entry attribution, or double exposure. |
| Earlier divergence is followed by negative price momentum and current damage. | Do not erase remembered setup evidence solely because the original price-context condition changed. |
| Prior extension is absent but direct break evidence qualifies. | Allow `protect-break` under its own rules; do not inherit extension or above-MA200 entry gates. |
| Washout is armed during continuing damage or a developing recovery. | Apply the declared entry/holding/conflict rules; high stress alone neither authorizes nor cancels protection. |
| Causal protective evidence recovers while complacency or broad fragility remains elevated. | Do not retain protection solely because those non-causal conditions remain. |

Report realized holding duration and results by entry action and exit reason. Compare how much
of useful recoveries was held and how much downside followed failed recoveries, without using
hindsight turning points to determine live exits. Measure these changes before adding a third
trend-continuation entry path.

For protect, isolate evidence/exit repairs, divergence sequencing, setup-decay eligibility, and
the new direct-break action instead of changing them all in one attribution run. Use ordinary
2018, 2022, and 2023 declines alongside the January 2024 and August 2025 false calls; retain
July 2024 as an early-warning tradeoff case. Group the two 2020 protect entries as exposure to
one common crash for concentration analysis, not two independent successes. Do not target
prediction of initial exogenous shocks.

Judge protection by subsequent loss avoided relative to false-alarm cost, missed upside,
turnover, and restoration delay. A larger correction count or an attractive distant drawdown
label is insufficient. The existing results do not yet establish a positive net benefit.

Keep the input profile fixed, execute after the signal's EOD, account for financing/cash and
costs, and group dependent entries by episode. Use chronological and concentration checks;
the dates already examined are research data, not a fresh holdout. Freeze candidate rules before
new observations. Historical replay can reject a weak hypothesis but cannot establish future alpha.

**Do not set a minimum action frequency.** If a clean pullback hypothesis adds mostly weak or
redundant opportunities, reject it. Remaining selective is better than manufacturing activity.

## 6. Proposed Scope Decision

1. Keep the accepted R2 correctness and held-exposure work as the baseline release work.
2. Retain its isolated transmission experiment: test price damage plus volatility stress without
   mandatory breadth/credit deterioration. This is not approval for single-indicator arming.
3. Separately test replacing the existing current-fear entry requirements with a causal measure
   of remaining price opportunity and episode expiry. Keep genuine release and owned confirmation.
4. Specify and implement orderly pullback recovery as the separate second-pass action
   `redeploy-confirm`, alongside `redeploy-washout`, not another relaxation of panic eligibility.
5. Specify and promote direct-market-break protection to the actual action `protect-break`,
   separate from `protect-extension`. Freeze its entry, recovery, and conflict rules rather than
   merely activating the old warning predicate. Repair protect evidence and exits first; test
   sequential extension confirmation and direct-break protection separately, including the
   tradeoff from requiring price damage. Keep setup-decay changes separately attributable.
6. Carry all four action identities into existing outcomes and held-exposure reporting, without
   new daily commands or duplicate exposure. Specify action-specific holding theses and explicit
   failure/completion/expiry/opposite-action reasons; test restoration to normal independently
   of redeploy eligibility. Keep signal and sizing experiments separate.
7. Defer trend resumption until the incremental opportunities, holding behavior, and costs of
   these actions have been measured. Improving how successful and failed recoveries are held
   takes priority over introducing another entry pattern.

The important change is the objective: **seek broader coverage by recognizing different
opportunities, not by asking one rare-event detector to become less selective.** Keep the
investment core, the daily workflow, and the number of numerical moving parts constrained.
