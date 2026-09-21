# r1 v1.0 Implementation Review

**Reviewer:** Claude (Sonnet 5), September 2026.
**Scope:** Full v1.0 implementation review against `plans/v1.0/` and
`ALGORITHM_DESIGN.md`/`IMPLEMENTATION_DESIGN.md`/`README.md`, focused on algorithm and
mechanism soundness rather than code style, with the explicit goal of assessing whether
the system can plausibly beat the market. Covered `src/marketlab/regime.py`,
`src/marketlab/market_signals.py`, `src/marketlab/policy.py`, `src/marketlab/regime_export.py`,
the `plans/v1.0/` design-review thread (r1-r3), and the current `workbooks/` outcome exports.

---

## Overall assessment

The setup/confirm/action lifecycle redesign is implemented correctly and matches the design
docs closely: no look-ahead bias in the pressure percentiles, correct snapshot-indexed arm/decay
windows, real (not decorative) geometric-mean gating, and enforced phase exclusivity between
protect and redeploy. Every "must-fix" item raised across the `plans/v1.0/` r1-r3 review thread
is resolved in the shipped code. However, there is one significant mechanism gap that undercuts
the point of the redesign, one place where the eliminated "geometric compensation" failure mode
has quietly reappeared one layer up, and the backtest evidence — while reported honestly by the
project's own docs — is not yet strong enough to support a "beats the market" claim.

---

## Critical

### 1. Posture persistence was built but never wired into the live policy path

Files: `src/marketlab/regime.py:5979-6067` (`derive_regime_postures`),
`src/marketlab/policy.py:947` (`_policy_state_from_action`).

`ALGORITHM_DESIGN.md`'s "Problem: Action Events Are Not Portfolio Posture" section requires that
`no_change` days following a protect or redeploy call keep the prior posture until an explicit
reset or opposite signal. `derive_regime_postures()` implements exactly that: a correct, tested
stateful engine that holds `protected`/`redeploying` posture across `no_change` days. It is used
by `regime_export.py` (workbook posture columns) and by `regime outcomes --by posture` for
research replay.

It is not used by `policy.py`. `_policy_state_from_action` derives `policy_state` from that single
day's `regime_action_state` alone; there is no import of the posture engine anywhere in the file,
and no test in `tests/test_policy.py` exercises cross-day persistence. `./bin/marketlab regime
policy` and `daily` — the commands that actually drive the operational report — still evaporate a
protect/redeploy call on the very next `no_change` day. This reintroduces the same same-day-only
fragility that the entire v1.0 lifecycle redesign was built to eliminate, one layer higher in the
stack (policy instead of action state).

This is not just a completeness gap — it likely makes `compute_portfolio_policy_outcomes`'s
protect/redeploy backtest numbers look weaker than the underlying signal really is, since exposure
is only credited for a single day per event instead of the full held posture episode. Given the
project's stated goal, this is the highest-leverage fix before v1.0 can be considered functionally
complete: wire `derive_regime_postures()` (or equivalent state) into `policy.py`'s state derivation,
add persistence tests, and rerun the policy outcome replay before trusting its numbers.

---

## Notable

### 2. Strength/confidence scoring reintroduces the compensation pattern the setup gates eliminated

File: `src/marketlab/regime.py:3905-3918` (`_action_module_average`).

The setup gates correctly prevent one extreme input from faking extension or washout: both legs
must individually clear 0.50 before a geometric mean is even computed
(`_structured_extension_setup_score`, `_structured_washout_setup_score`, `regime.py:5546-5595`).
But `deterioration_score`/`stabilization_score` — which feed `extension_strength = sqrt(memory *
deterioration_score)` and `redeploy_strength = sqrt(current_washout * stabilization_score)` —
are computed by averaging only the **top 3 nonzero module scores**, not all modules that were
evaluated. The action *gates* still require independent family counts
(`_confirming_families`), so this cannot fabricate a protect/redeploy call by itself. But the
reported *strength* of a call can be pulled up by one or two loud families even when most
families are quiet — the "Problem: Geometric Compensation Hides Weak Setup" failure mode,
reintroduced at the confidence layer instead of the gate layer. Worth either averaging over all
evaluated modules or explicitly documenting that strength is a "loudest evidence" metric, not a
broad-confirmation metric.

### 3. Shock-vs-ordinary cohort split is proposed but not delivered

`ALGORITHM_DESIGN.md`'s "Problem: Shock Windows Distort Ordinary Correction Research" and backlog
item 1 call for separating ordinary corrections from shock-driven episodes before treating protect
performance as validated. `_correction_episode_event_context` classification exists in code
(`regime.py:7914-7933`, confirmed populated, not the `"unclassified"` placeholder flagged in the
prior `plans/v1.0/r3-review-claude.md` review — that item is resolved). But the exported outcome
reports in `workbooks/` do not yet present a shock-excluded protect/redeploy cohort view. At face
value, protect's apparent edge is dominated by 3 COVID-adjacent clusters out of 18 total
(`workbooks/outcomes-protect-v1.0.txt`); excluding them, most 2016-19 and 2021-25 protect clusters
show flat-to-positive forward returns, the opposite of what protect is supposed to predict.
Redeploy's strong 65-day figure (+11.4% vs +4.1% baseline) is likewise COVID-concentrated, and the
design doc itself notes the three 2021-2024 redeploy events have negative average 40/65-day
returns. Before any "beats the market" claim, add the shock-excluded cohort table the design doc
already calls for and evaluate it on its own.

### 4. Sample size is too small to support a statistical edge claim yet

Current replay (2016-01-01 to 2026-06-01): 14 protect events / 29 redeploy action days across 8
armed events, matching `ALGORITHM_DESIGN.md`'s own narrative numbers exactly (no drift between
docs and code). That is a reasonable count for research iteration but not for a market-beating
claim: single digits to teens of largely non-independent episodes, several sharing one 2020 shock,
with a 67% cluster-level false-alert rate on protect (`regime_protect_cluster_outcome_count=54`,
`false_alert_cluster_outcome_count=36`) even after the redesign halved protect frequency. No
confidence intervals or significance testing accompany the saved reports. This is consistent with
the design doc's own "not validated" framing and does not need to block v1.1 work, but should
block any messaging stronger than "promising research scaffold."

### 5. Missing-data fallback can silently produce a synthetic moderate score

File: `src/marketlab/regime.py:3891-3898` (`_action_setup_score` fallback).

When a pressure score is `None` (insufficient history, gated by `MIN_PRESSURE_FEATURE_SAMPLES =
20`), the code substitutes `fallback_evidence_count / 5.0` rather than propagating "unknown."
This mainly affects the first ~20 trading snapshots of a fresh backfill, but it means a genuine
data gap can present as a moderate signal instead of a flagged gap. Consider surfacing this case
explicitly in snapshot output (e.g. a `data_incomplete` flag) rather than folding it into the
score.

### 6. Minor window off-by-one

File: `src/marketlab/regime.py:4046` (`age <= spec.max_age_days`).

The inclusive comparison gives a 41-snapshot extension-memory window and a 16-snapshot
washout-memory window, one snapshot longer than the documented "40" and "15" in README.md and
ALGORITHM_DESIGN.md. Immaterial to behavior, but worth aligning code and docs so the stated
numbers are exact.

### 7. Some pressure features feed both stretch and washout identically

File: `src/marketlab/regime.py:5691-5693` (`low_weakness_pressure` mode in
`_pressure_scores_from_normalized_score`).

Certain context/weakness-only features return the same value for both `stretch_score` and
`washout_score`. This is defensible for features where weakness is symmetrically bad for both
setups, but it means extension and washout are not fully independently measured wherever this
mode is used, slightly diluting the "cleanly separated setups" claim from the "Problem: Stretch
Is Not Bearish By Itself" section. Worth confirming (a targeted read of
`PRESSURE_FEATURE_SPECS`/`PRESSURE_MODULE_SPECS`, `market_signals.py:1166-1333`, not yet fully
audited) how many features actually use this mode and whether that's intentional.

---

## Confirmed sound (no action needed)

- No look-ahead bias in pressure percentiles: `_pressure_feature` filters strictly to
  `asof_date <= source_date` over a trailing window (`regime.py:5598-5679`).
- Geometric-mean gating is real: both setup scores return `0.0` outright if any required leg is
  below its gate, only averaging after all gates pass (`regime.py:5546-5595`).
- Arm/decay/grace logic matches spec exactly, including snapshot-index-based (not calendar-day)
  aging and grace-refresh-on-requalify (`regime.py:3997-4072`, `4166-4209`).
- Bounded-replay window correctly backs up over a continuous hit-run to avoid misclassifying an
  ongoing setup as freshly armed (`regime.py:4125-4134`).
- Phase exclusivity is enforced in code: `protect_ready` is unconditionally `False` while washout
  is armed; `redeploy_ready` never depends on protect state (`regime.py:3663-3670`).
- `protect_action` and `redeploy_action` gates reproduce the documented rules exactly, including
  routing volatility-only confirmation to a separate warning path rather than firing protect
  (`regime.py:4299-4391`, `3663-3669`, `4429-4449`).
- Forward-return/drawdown computation uses strictly future indices and returns `None` rather than
  extrapolating past the end of history (`regime.py:8883-8917`).
- Threshold constants at the top of `regime.py` (lines 83-128) match README.md/ALGORITHM_DESIGN.md
  exactly; no drift found.
- All `plans/v1.0/` r1-r3 review "must-fix" items (event_context classification, armed-memory
  re-arm split, `action_path` as a first-class field, false-alert cluster reporting) are resolved
  in shipped code.
- FRED current-vintage-vs-point-in-time limitation is an acknowledged, disclosed limitation
  (README.md, ALGORITHM_DESIGN.md), not a newly discovered issue; observed revisions in
  `data/observations/market/series/_revisions/NFCI.jsonl` are rounding-level and not materially
  biasing.

---

## Not fully verified

- Individual per-signal feature functions (`_trend_turn_feature`, `_vix_turn_feature`, and
  similar, roughly `regime.py:4565-4990`) were not audited line-by-line for sign errors or
  wrong-column bugs.
- `market_signals.py` symbol-level feature computations (raw trend/vol/breadth/credit values
  feeding the pressure features) were not fully audited.
- `PRESSURE_FEATURE_SPECS`/`PRESSURE_MODULE_SPECS` (`market_signals.py:1166-1333`) mode
  assignments were not fully enumerated (see Notable #7).

---

## Suggested v1.1 priorities

1. Wire `derive_regime_postures()` (or equivalent held-state logic) into `policy.py` so the
   operational `regime policy`/`daily` path actually persists posture, then add a
   cross-day-persistence test and rerun `compute_portfolio_policy_outcomes`.
2. Deliver the shock-excluded ordinary-vs-shock cohort table in the exported outcome reports
   (`ALGORITHM_DESIGN.md` backlog item 1) and re-evaluate protect/redeploy performance on the
   ordinary-only cohort before any market-beating claim.
3. Decide and document whether `extension_strength`/`redeploy_strength` should average over all
   evaluated modules or remain a "loudest evidence" metric (Notable #2).
4. Align the `age <= max_age_days` window with the documented 40/15-snapshot figures (Notable #6),
   and surface the missing-data fallback explicitly instead of folding it into the setup score
   (Notable #5).
5. Continue collecting forward, out-of-sample evidence per the existing backlog; do not tune
   thresholds to improve the current small, COVID-concentrated sample.
