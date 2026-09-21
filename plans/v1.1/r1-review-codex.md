# V1.1 Improvement Review: V1.0 Algorithm And Implementation

Reviewed against commit `8fe414a`, using the local observations and versioned snapshots available
on September 16, 2026. This is a review, not an implementation proposal accepted for execution.
Production calculations, snapshots, and workbook files were not changed during this review.

## Assessment

V1.0 improves the vocabulary and separates setup from confirmation, but it has not established an
edge over buy-and-hold. Redeploy has promising short-horizon evidence. Protect remains weak outside
the COVID window. Several mechanism defects and an incomplete portfolio evaluation prevent a
stronger conclusion, even though all 233 existing tests pass.

The priority is to repair score semantics, lifecycle consistency, and measurement before changing
thresholds again. First-principles explanations are necessary, but repeatedly choosing rules after
viewing the same outcomes still creates selection bias.

## Findings

### 1. [P1] Stronger confirmation can turn an action off

Locations: `src/marketlab/regime.py:3905` and `src/marketlab/regime.py:4549`.

Both family aggregation and feature aggregation average up to three strictly positive scores.
Zero scores disappear from the denominator. With stabilization in trend/volatility/breadth:

| Family scores | Aggregate | Redeploy confirmation gate |
| --- | ---: | --- |
| 0.80, 0.80, 0.00 | 0.80 | Pass |
| 0.80, 0.80, 0.01 | 0.537 | Fail |
| 0.80, 0.80, 0.60 | 0.733 | Fail |

The family-count requirement passes in all three examples. Adding positive breadth evidence alone
removes confirmation. The same behavior within volatility means a small additional confirming
signal can dilute a strong existing signal. Missing features can also make the aggregate stronger.

This violates the intended monotonic interpretation: stronger evidence in the same direction should
not lower confidence in that direction. It affects both protect strength and redeploy eligibility.

Recommendation: define a monotone aggregation contract, with explicit treatment of observed zero,
missing, and opposing evidence. Fixed-denominator aggregation or an order statistic combined with
family-count gates are possible implementations; choose semantics before evaluating returns. Test
zero-to-positive changes, missing-to-observed changes, and duplicate correlated evidence.

### 2. [P1] The historical backtest and current model have different input sets

Locations: `src/marketlab/regime.py:5222`, `src/marketlab/regime.py:5503`, and source coverage.

Local source coverage is:

| Input | First observation | Consequence |
| --- | --- | --- |
| SPY | 2014-06-30 | Adequate warmup before the 2016 review window |
| HY OAS, BAMLH0A0HYM2 | 2023-09-11 | Missing throughout most of the reviewed history |
| S&P 500 percent above 50d/200d | 2026-08-26 | Absent from the entire workbook evaluation window |

Six of eight redeploy events lack OAS. Eighteen of 29 redeploy action days and 23 of 27 protect
action days lack it. These are not hypothetical data gaps.

The credit pressure module averages available inputs, so HYG/TLT is the entire module before OAS
arrives, and approximately half of it afterward. Direct breadth participation will likewise change
the breadth calculation when sufficient history accumulates. This changes the meaning of fixed
thresholds without changing the version label.

The severe-funding veto requires both OAS=`stressed` and NFCI=`tight`. Missing OAS makes the veto
false, not unknown. Consequently historical results do not validate that safeguard. This does not
prove a specific historical action would have been blocked with complete data; for example, the
saved NFCI status on 2020-03-26 is neutral, which independently prevents the veto.

Recommendation: evaluate a fixed historically available input set and an explicitly identified
augmented set separately, or acquire adequate source history before pooling their results. Give
required veto inputs an explicit unknown-data policy. Show input coverage with outcomes; lowering
the confidence label alone does not correct performance comparisons. Preserve the documented
current-vintage limitation for revised FRED data.

### 3. [P1] Fragility retains the wrong credit/liquidity direction and delays re-entry

Locations: `src/marketlab/regime.py:5386`, pressure feature definitions near line 1257, and
`src/marketlab/regime.py:6087`.

`fragility_context_score` averages the **stretch** sides of breadth, credit, liquidity, and rates.
For credit spread and NFCI, stretch means compressed spreads and unusually loose conditions. These
are complacency readings; they are not evidence of deteriorating funding conditions. The planned
semantic separation is therefore incomplete.

This matters even though regime-break protect is now warning-only. Protected posture cannot clear
until fragility drops below 0.35. Improving liquidity can therefore keep the model protected.

Observed example: protection starts on 2024-01-04 and ends on 2024-04-01. SPY gains 12.09% between
those closes. On 2024-03-28, protect strength is only 0.255 and extension is zero, but fragility is
0.385, preventing reset. Breadth and rates contribute zero; credit stretch is 0.627 and liquidity
stretch is 0.913. NFCI is -0.437, which the signal table correctly labels loose.

Recommendation: distinguish complacency/vulnerability from actual funding weakness. Reset should
respond to whether the protect thesis remains valid, not whether financial conditions remain
unusually supportive. The exact replacement requires a design decision; simply reversing every
stretch input would create a different mixture.

The economic sign is confirmed by the [Chicago Fed NFCI documentation](https://www.chicagofed.org/-/media/publications/nfci/nfci-faqs-pdf.pdf):
negative readings denote looser-than-average conditions. Whether loose conditions create eventual
vulnerability is a separate hypothesis from whether to remain defensively positioned today.

### 4. [P1] Posture evaluation does not yet measure the strategy the plan required

Locations: `src/marketlab/regime.py:5979`, `src/marketlab/regime.py:6380`,
`src/marketlab/regime.py:8107`, and `src/marketlab/policy.py:947`.

Posture states are reconstructed, but `--by posture` reports fixed-horizon index returns from every
day carrying a posture label. It does not measure entry-to-reset returns, actual exposure, cash,
turnover, financing, or costs. Overlapping windows again overweight long episodes. The plan's
posture-outcome done criterion is not satisfied by the presence of these columns.

For example, the 2022-03-15 redeploy event has a -13.70% 65-day SPY return. Its reconstructed
redeploy posture ends on 2022-03-31, after a +6.31% index move. Neither number alone is portfolio
alpha, but their difference demonstrates why event horizons cannot substitute for held exposure.

Using the existing state transitions, there are ten completed protected spans and eight redeploying
spans in the workbook window. Protected spans average 29.1 sessions; redeploying spans average
11.1. Repeated same-direction actions reset `posture_start_date`, `posture_age`, and the drawdown
reference even when the position has not changed. The 2020 redeploy span lasts 33 sessions despite
the nominal 20-session maximum because later signals restart the clock.

Daily policy also maps a subsequent `no_change` to beta target 1.00 independently of reconstructed
posture. Its instruction to maintain exposure and its numerical target can therefore disagree.

Recommendation: specify exposure and reset rules once, distinguish a repeated observation from a
new tranche, and measure a daily return stream against the same permanent core plus a fixed
tactical sleeve. Use the next executable session for entries and exits. Include cash/financing and
cost assumptions before describing the result as market outperformance. A return diagnostic may
still start at the signal close, but it must be labeled accordingly.

### 5. [P2] Washout release measures a threshold discontinuity as stress relief

Locations: `src/marketlab/regime.py:5546` and `src/marketlab/regime.py:4441`.

Structured washout becomes exactly zero whenever any required leg drops below its gate. Release
then subtracts this gated value from remembered peak setup. With volatility=0.90 and
transmission=0.90, changing trend washout from 0.501 to 0.499 changes:

- continuous geometric stress: 0.7404 to 0.7394;
- gated setup: 0.7404 to zero;
- measured release from that peak: approximately zero to 0.7404.

The actual stress improvement is about 0.001, yet the release gate of 0.05 passes by a large margin.
Sixteen of 29 actual redeploy action days have zero structured setup. On 2022-03-15, trend and
volatility washout remain 0.818 and 0.756, while the transmission legs are zero, so the structured
setup collapses. This is not proof that the action was wrong; it shows that the claimed release
measurement does not quantify how much stress abated.

Recommendation: retain gated eligibility for arming, but measure relief on a continuous stress
quantity or explicitly define a categorical transition. A numeric release threshold should not
quietly become automatic whenever a different gate switches off.

### 6. [P2] Setup lifecycle identity, remembered peak, and exported memory can diverge

Locations: `src/marketlab/regime.py:3997`, `src/marketlab/regime.py:4103`,
`src/marketlab/regime.py:6296`, and `src/marketlab/regime_export.py:488`.

There are three related problems:

- A brief dip below the hit threshold resets `setup_run_armed` even while memory is active. Renewed
  hits create a new `armed_since` and replace the remembered peak. For setup values
  `[0.90, 0.61, 0.61, 0.61, 0.61, 0.61, 0.59, 0.65, 0.55]`, the last two rows remember 0.65 rather
  than 0.90. The grace period never expired. The local history contains 13 washout re-arms while the
  previous memory was still active. Event deduplication uses this unstable identity.
- Snapshot computation uses a truncated replay, while export replays the full series. Across 24
  dates, active washout `armed_since` differs. On 2018-04-17 the saved snapshot and recomputed bounded
  path say 2018-03-22, while full replay and CSV say 2018-03-21. The bounded window lacks the earlier
  persistence votes. In the observed mismatches, armed/unarmed status agrees; no action-state change
  was demonstrated from this discrepancy alone.
- Prior-history validation only requires some earlier snapshot. With an armed snapshot from
  2025-01-02 and the next snapshot on 2026-01-02, the engine reports age=1 and effective extension
  0.8775. Saved-row counts cannot represent trading-session age when history has gaps.

Recommendation: define episode identity, peak, and last qualifying date as separate state; preserve
them until an explicit reset. Require full replay and incremental replay to agree, and export the
state actually used for the action. Detect missing required SPY sessions and give a backfill error
instead of silently stretching memory across them. This fits the existing CLI workflow.

### 7. [P2] Protect still requires a key earlier condition to hold on confirmation day

Locations: `src/marketlab/regime.py:4299`, `src/marketlab/regime.py:4893`, and
`src/marketlab/regime.py:4990`.

Extension is remembered, but internal divergence is not. Both breadth and credit divergence require
average SPY/QQQ 20-day return to remain nonnegative on the current day. Once price damage makes it
negative, divergence becomes zero even if internal deterioration continues. The protect gate still
requires that divergence, including its price-rollover branch.

Eight saved dates meet the other tested conditions (armed extension, no armed washout, long-term
uptrend, sufficient extension strength, volatility/trend/internal deterioration), but have negative
average 20-day return and therefore no required divergence. These include 2019-08-02 through
2019-08-07. They are diagnostic candidates, not eight proven profitable missed calls.

The original proposal also had a regime-break action path. Its later demotion to warning-only is
documented and intentional; I would not restore it just to improve this sample. However, together
with the requirement that both indexes remain above their 200-day averages, it materially narrows
the class of corrections the current protect model can address.

Recommendation: distinguish prior divergence from subsequent rollover in the protect thesis.
Evaluate a bounded divergence-to-rollover transition or a clearly defined direct-damage branch.
Keep explicit invalidation and do not add a remembered flag for every possible signal. Judge the
change by held exposure and false-alert cost, not only correction count.

### 8. [P2] Episode context does not separate ordinary corrections from external shocks

Location: `src/marketlab/regime.py:7914`.

In the actual v1.0 episode report, 13 of 14 corrections are `scheduled_event_proxy`; only COVID is
`shock`. The same historical dates under v0.0 mostly become `ordinary`, because the classifier
depends on an event-volatility field those snapshots did not have.

Rising front-end volatility accompanies many corrections. It does not establish that a scheduled
event caused them. The speed/depth rule similarly identifies fast deep drawdowns, not exogenous
causes. Therefore these labels cannot support the plan's intended ordinary-versus-shock validation.

Recommendation: label the mechanical properties literally, and keep a separate version-independent
research annotation for known events, with an unknown category. Agree cohort membership before
evaluating model performance. This does not require a daily event-calendar workflow.

### 9. [P2] Reported drawdown is loss from entry, not peak-to-trough drawdown

Locations: `src/marketlab/regime.py:8900` and `src/marketlab/regime.py:6102`.

`min(future_close) / entry_close - 1`, floored at zero, measures adverse excursion from entry.
For prices 100 -> 120 -> 105, it reports zero, although peak-to-trough drawdown is 12.5%.
That metric is useful for entry quality, but insufficient for deciding whether a held tactical
position improves portfolio risk. It also uses closing prices and misses intraday excursions.

Recommendation: retain and label entry-based adverse excursion, and calculate actual running-peak
drawdown on the held return stream. Do not interpret the current `spy_dd` as the latter.

## What The Data Supports

The main window is 2,617 snapshot dates, 2016-01-04 through 2026-06-01, with subsequent prices used
only for outcomes. Both committed CSVs cover that same window. I reproduced the committed action
report numbers from snapshots and raw observations.

| Event cohort | Events | SPY 20d | SPY 40d | SPY 65d |
| --- | ---: | ---: | ---: | ---: |
| v0.0 protect | 42 | +0.90% | +2.10% | +4.13% |
| v1.0 protect | 14 | +0.55% | +0.44% | +0.22% |
| v1.0 protect, exclude 2020 signals | 12 | +0.76% | +3.73% | +2.74% |
| v1.0 protect, 2021 onward | 7 | +0.21% | +3.29% | +4.63% |
| v0.0 redeploy | 16 | +1.51% | +5.10% | +6.13% |
| v1.0 redeploy | 8 | +5.06% | +5.35% | +6.34% |
| v1.0 redeploy, exclude 2020 signals | 7 | +4.59% | +4.24% | +4.80% |
| v1.0 redeploy, 2021 onward | 4 | +3.82% | +2.28% | +1.42% |

These are conditional index returns, not strategy returns. V0.0 uses five-gap clustering and v1.0
uses setup identities, so their default event definitions differ. Applying the same five-gap rule
to both versions leaves v1.0 redeploy unchanged; v1.0 protect's 40-day return becomes -0.08% over
14 events. Excluding 2020, that becomes +3.13%, versus +3.20% for v0.0. Thus the apparent protect
improvement outside 2020 is negligible under that common event definition.

Using that common rule, 40-session false-alert rates are 32/42 for v0.0 and 10/14 for v1.0.
Excluding 2020 signals: 32/39 versus 10/12. A false alert here means no 5% closing-price loss from
the alert's entry within 40 sessions. This is a diagnostic definition, not proof of economic loss.

In the current correction inventory, v1.0 has timely protect for two of 13 non-COVID episodes,
versus four for v0.0, using the existing 20-session pre-peak search. The inventory excludes the
drawdown already underway when local SPY history begins and combines successive legs until the
old peak recovers. These counts are specific to that definition, not an exhaustive recall measure.

The two v1.0 protect events on 2020-01-03 and 2020-01-24 contribute 40-day returns of -6.88% and
-31.79%. Their shared exposure to the COVID window explains much of the full-sample average; it
does not demonstrate two independent predictions of that shock. Consistent with the research
intent, missed exogenous shocks are acceptable, and coincidental successes should not validate
ordinary-correction protection either.

Redeploy's improved 20-day result survives removal of 2020. That is encouraging. Its eight events
are 2016-02-18, 2019-01-07, 2019-08-21, 2020-03-26, 2021-12-08, 2022-03-15, 2024-08-12, and
2025-04-11. The 2021-12 and 2022-03 entries lose at longer horizons, but the current posture exits
well before those horizons. This supports evaluating short tactical rebounds separately from a
claim that the final bear-market bottom has occurred.

A next-open entry sensitivity check, keeping the original exit dates, changes v1.0 redeploy's
20-day mean from +5.06% to +4.98%, and protect's 40-day mean from +0.44% to +0.55%. Same-close
entry is not the main source of the apparent edge in this particular sample. This check does not
include execution costs and is not a portfolio backtest.

## Plan Completion And Research Discipline

Implemented well: explicit setup/confirmation fields, family-level volatility treatment, saved
setup memory, event-oriented action reports, versioned artifacts, and accessible evidence tables.
Keep these foundations.

Changed from the original plan: regime-break is warning-only; redeploy now requires memory and
multiple confirming families; an event-volatility proxy replaced a calendar. These changes were
part of later iteration and are not automatically mistakes. They require evidence under their
current definitions rather than credit for satisfying the original two-path design.

Not complete: the required held-portfolio comparison, stable episode accounting, and credible
ordinary-versus-shock cohort separation. The progress document's complete status overstates the
research milestone, even though the planned CLI/reporting surfaces exist.

Repeated development against 2016-2026 means this window is development data. Removing 2020 and
looking at 2021 onward are sensitivity checks, not untouched validation sets. Choosing gates,
horizons, or aggregation after inspecting outcomes can overfit even when each choice has a
plausible explanation. See Bailey et al., [The Probability of Backtest Overfitting](https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf).

Recommended order:

1. Fix monotonic aggregation, coverage/veto semantics, lifecycle identity, and replay parity.
   Add property and sequence tests before recalculating history.
2. Resolve fragility direction and posture resets, then build entry-to-exit and daily exposure
   attribution. Compare against an identical permanent core and simple tactical benchmark.
3. Correct release measurement and study the divergence-to-rollover lifecycle with a small number
   of predeclared variants. Avoid searching for the most flattering thresholds.
4. Report per-event outcomes, opportunity cost, input coverage, and concentration. Separate
   independent market episodes from multiple alerts exposed to the same future selloff.
5. Freeze the chosen specification and collect forward evidence. Use untouched earlier history only
   where input coverage is comparable; require broad stability under coarse perturbations rather
   than a single best parameter combination.

Do not claim a covered-call or long-call edge from SPY/QQQ forward returns alone. Those instrument
policies require their own premiums, strikes, expiries, volatility exposure, and cost evaluation.

## Verification

- Read the design rounds, current design documents, regime calculation/replay/export code, and
  portfolio policy mapping.
- Recomputed action-event returns from saved versioned snapshots and raw adjusted-close histories.
- Checked common event grouping, exclusion of 2020, post-2020 events, next-open entry sensitivity,
  and actual posture transition spans without changing model parameters.
- Reproduced aggregation non-monotonicity, release discontinuity, lifecycle peak loss, sparse-history
  age distortion, and bounded-versus-full memory differences with deterministic calls.
- Ran `.venv/bin/python -m pytest -q`: 233 passed. Existing tests do not cover the failures above.

The canonical action and correction reports can be reproduced with:

```bash
./bin/marketlab regime outcomes --by action --start 2016-01-01 --end 2026-06-01 --horizons 20,40,65 --snapshot-version v1.0
./bin/marketlab regime outcomes --by episode --start 2016-01-01 --end 2026-06-01 --snapshot-version v1.0
```

Repeat with `--snapshot-version v0.0` for the saved prior version. These are read/replay commands;
no backfill or source refresh is needed for the reviewed artifacts.
