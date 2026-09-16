# v2 Plan Review

**Reviewer:** Claude (Sonnet 4.6), September 2026.
**Document under review:** `v2-plan-codex.md`.
**Prior context:** `ALGORITHM_DESIGN.md`, `v1-ideas-chatgpt.md`, `v1-plan-claude.md`,
and direct analysis of `workbooks/regime.csv` (2,617 snapshots, 2016-01-04 to 2026-06-01).

---

## Overall verdict

`v2-plan-codex.md` is the best current synthesis of the design. The first-principles section
is well-stated, the state vocabulary is clean, and the anti-overfit rules are a necessary
addition that the earlier plans lacked. The implementation sequence is right in its broad
strokes. I have four substantive comments and will update my position on one of them.

---

## What is strong and should be adopted as-is

**Anti-overfit rules as a named section.** This is the most important addition over the
earlier plans. Having an explicit list of anti-overfit constraints — rolling percentiles
over fitted weights, coarse threshold categories, episode-level evaluation over overlapping
return windows, reject-if-vocabulary-gets-worse — makes the design discipline legible to
anyone who later implements a step. Keep it exactly as written.

**Armed memory as research output before it controls actions (Step 6).** The naive diagnostic
result cited in the Local Data section (73 clusters, 57 false alerts with extension p90 +
40-day memory + broad confirmation proxy) is the key empirical argument. My v1 plan proposed
implementing decay directly as a control mechanism. That was wrong given this result. The
v2-codex ordering — compute and export armed state, inspect it in the episode workbook, only
then let it gate production signals — is correct and I adopt it.

**Lifecycle framing throughout.** "Correction warning is a lifecycle problem, not a same-day
classification problem" is a cleaner statement than anything in the earlier plans. Anchoring
every design decision to the lifecycle prevents the drift back toward treating each snapshot
independently.

**Redeploy validation as a separate, final step.** The empirical case is clear: washout p95
gives +8.6% SPY at 65d versus +4.1% baseline. Redeploy should be validated after protect is
redesigned, not touched during it. This is stated correctly.

**Posture replay as part of the design, not reporting.** This matches my v1 position and is
stated clearly in v2-codex. Good.

---

## Comment 1: The multi-family confirmation rule needs to be more precise — but must not lose the VIX/VVIX divergence

**The gap.** Section "Path A: Extension Unwind" says: "Require at least two confirming
families and at least one non-volatility internal family. Volatility sub-signals such as VIX,
VVIX, and VIX term structure cannot satisfy this by themselves."

This is close but underspecified. The current codebase has three separate action features in
the volatility family: `vix_turn`, `vvix_turn`, and `term_structure_turn`. An implementation
that counts feature entries rather than family names could accidentally satisfy "two families"
with just vix_turn and vvix_turn, since they each have a `family="volatility"` tag but are
stored as separate entries. The design text should close this.

**Proposed clarification.** VIX, VVIX, and VIX term-structure collectively count as *one
family vote* toward the two-family confirmation requirement, regardless of how many of the
three fire. The second required family must come from breadth (RSP/SPY, IWM/SPY, or S&P 500
breadth participation), credit (HYG/TLT or HY OAS), or liquidity (NFCI). Trend damage is
also non-vol and counts for the regime-break path.

**The VIX/VVIX divergence pattern is preserved.** The current code already captures the
VIX-high / VVIX-cooling bottom signal as `_vvix_vs_vix_feature` with
`evidence_kind="divergence"`. This feature computes `stabilization_score` gated on
`_high_vix_context_score` — meaning it produces a meaningful redeploy signal when VIX is
elevated and VVIX starts cooling, exactly the pattern where smart-money vol positioning stops
accelerating before the headline index recovers. It also captures the deterioration direction:
VVIX leading VIX (rising faster than VIX while VIX is still low) as an early warning.

Collapsing VIX, VVIX, and term-structure into one family vote does *not* remove this:
- The `vvix_vs_vix` feature still runs and contributes its deterioration and stabilization
  scores to the action module calculation.
- "One family vote" only constrains the protect *confirmation gate count*, not what the
  volatility evidence contributes to the action score.
- For **redeploy**, the non-vol gate does not apply — VIX high + VVIX cooling is valid
  stabilization evidence on its own, and the redeploy path should stay that way.
- For **protect**, a VIX/VVIX divergence without breadth, credit, or liquidity
  confirmation is correctly treated as warning-only. The divergence information is still
  visible in the output; it just cannot by itself trigger `scale_down_protect`.

**Disposition.** Implementation precision point, add to design before Step 3. For redeploy
stabilization, confirm the non-vol gate is explicitly not required.

---

## Comment 2: Exact metrics should be stated as rejection thresholds, not dropped entirely

**The question.** Section "Hold Off For Now" says: "Exact target metrics, such as
'false-alert rate below X,' should be used as rejection checks, not as an optimization
objective." My v1 plan set concrete targets (false-alert rate ≤50%, correction coverage
≥6/14). The v2-codex position is that these are in-sample numbers and optimizing to them
is curve-fitting.

**Agreement.** I accept this argument. The numbers come from the same 2016-2026 dataset
being used for development. Declaring them done-criteria is curve-fitting by another name.

**One refinement.** However, "rejection checks" should be defined well enough to be usable.
A rejection check that is never written down is no check at all. Suggest adding one sentence
to the plan: *"Before declaring v2 ready for live use, false-alert rate must be materially
lower than the current ~76% and correction coverage must be materially higher than the
current 5-of-15 — but neither number is a calibration target."* "Materially" deliberately
leaves room for judgment; what it prevents is calling a model done when the numbers are
indistinguishable from the v0.0 baseline.

**Disposition.** Minor addition, not a disagreement.

---

## Comment 3: The regime-break path needs a regime-consistency rule that is concrete, not advisory

**The gap.** Section "Path B: Regime Break" says: "If the headline regime is still strongly
`risk_on`, treat that as a consistency warning. The regime-break path should usually require
at least neutral/risk-off background unless trend and internal deterioration are extreme
enough to explain why the headline regime is lagging." The word "usually" leaves this
underspecified for implementation.

**The empirical reason to be specific.** The regime outcomes show that `risk_off` has
stronger forward returns (+5.7% / +7.2% at 40d/65d) than `risk_on` (+1.8% / +3.0%).
This means the headline regime is a lagging, not a leading, indicator — it often turns
`risk_off` *after* the damage has started. A regime-break protect that fires during
`risk_on` is likely to be early; one that fires during `risk_on` with strong trend damage
is more plausible. The regime label alone is not a useful gate.

**Proposed rule.** For regime-break protect, the headline regime does not gate the signal,
but it is reported and included in the action explanation. If the headline regime is
`risk_on` at the time of firing, the output should say so explicitly so it can be tracked
in the episode diagnostics. After enough episode data accumulates, a regime-consistency
condition can be added if it turns out `risk_on` regime-break signals are systematically
false positives. Adding it now is premature given the lagging nature of the regime score.

**Disposition.** The v2-codex text can stay; this is a clarification of how to implement
"treat as consistency warning" — it means log it, not gate on it.

---

## Comment 4: Step 6 (armed memory to production) needs an explicit inspection criterion

**The gap.** The sequence says: compute armed state (Step 5), then "Add armed setup memory
to protect path A gate after inspection confirms it helps without over-firing" (Step 6). But
"helps without over-firing" is not defined. Given the naive diagnostic showed armed memory
*increased* false alerts (78% vs 76%), the inspection needs a clear pass condition.

**Proposed inspection gate for Step 6.** Before promoting armed memory to control production
signals, the episode diagnostic must show:
1. Cluster false-alert rate with armed memory lower than without it (current ~76%).
2. Correction coverage with armed memory no worse than without it (current 5-of-15 at 20d).
3. The extension_setup signal on armed days visually shows elevated price extension in the
   workbook — not just fragility bleed-through.

If any of these is not satisfied after Step 5, armed memory stays as a research column and
does not advance to Step 6. This is consistent with the anti-overfit rules.

**Disposition.** Should be added to the implementation sequence at Step 6.

---

## Plan of record

The following is agreed across this review:

**Architecture:**
- Split `extension_setup` (price extension + vol complacency only) from `fragility_context`
  (breadth, credit, liquidity, rates, trend weakness). This comes first.
- Two protect paths: `extension_unwind` and `regime_break`. Label on every signal.
- Hard gates on both paths. No geometric compensation.
- Volatility sub-signals (VIX, VVIX, term-structure) count as one family collectively.
  Broad confirmation requires at least one non-vol family: breadth, credit, or liquidity.
- Event-vol context near known macro dates: volatility-only deterioration becomes
  warning-only, not protect confirmation.
- Headline regime is reported as context, not used as a gate.
- Redeploy: validate only, do not redesign during protect work.
- Posture replay: part of v2, not optional.

**Evaluation:**
- Correction episodes are the primary diagnostic, not overlapping daily forward returns.
- False-alert rate and correction coverage are rejection checks: v2 must show material
  improvement over v0.0 baseline, but they are not calibration targets.
- Ordinary corrections and shock events (>15% in <30 days) are separate cohorts.

**Anti-overfit:**
- Rolling percentiles over fitted weights.
- Coarse threshold categories: low, elevated, high, extreme.
- Reject changes that improve a metric but make the state vocabulary less clear.
- Armed memory is a research output first. It advances to control production signals only
  if episode diagnostics show lower false-alert rate, no worse correction coverage, and
  visible price extension on armed days in the workbook.

**Implementation order:**
1. Split extension_setup / fragility_context. Export both as columns.
2. Build correction-episode diagnostics.
3. Replace protect with gated paths (current-day setup, no memory yet).
4. Make volatility-only confirmation warning-only. Add event-vol calendar.
5. Export armed extension state as research columns. Inspect in episode output.
6. Promote armed memory to production gate only if inspection passes.
7. Add posture replay. Measure episode-level portfolio outcomes.
8. Validate redeploy separately after protect is stable.
9. New data sources (sentiment, positioning) after lifecycle model is clear.

**Done when:** Every protect signal reports its path, confirming families, and non-vol
confirmation presence. Volatility-only protect cannot fire. Episode diagnostics are in the
outcome report. Workbook includes extension_setup, fragility_context, confirmation, and
posture fields. A human can audit any signal from the snapshot table without reading code.
Redeploy is confirmed not degraded.
