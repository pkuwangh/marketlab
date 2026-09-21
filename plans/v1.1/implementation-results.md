# V1.1 Implementation Results

## Decision

The R3 mechanism is implemented as the current research candidate, not accepted as improved
market timing. **The combined model fails the initial economic comparison.** Correctness fixes,
explicit action identities, persisted state, and executable accounting are useful independently
of whether the chosen entry/exit rules add value.

The initial specification is frozen in [implementation-progress.md](implementation-progress.md).
No thresholds were adjusted after inspecting these comparisons. Do not choose R2-B simply
because it has the largest historical return in this table. This is previously reviewed history,
not an untouched validation set. Nothing here introduces trade execution.

## Scope And Reproduction

- Canonical v1.1 snapshots: 2,693 SPY sessions, 2016-01-04 through 2026-09-18.
  Policy v0.1 outputs were backfilled for the same sessions.
- Scored comparison: 2,617 EOD decisions, 2016-01-04 through 2026-06-01; 2,616 following-session
  account valuations. Later prices supply fixed forward labels only.
- Sources: `data/observations`; canonical calculated results: `data/snapshots`. Workbooks are
  outputs, never inputs to the transition or comparison.
- Each variant has its own complete chronological state. The internal runner is
  `marketlab.regime_research.compare`, called with the dates above and `input_profile="core"`
  or `"reduced"`. Its fixed configurations are in `comparison_configs`.
- Machine-readable comparisons are under `data/research/regime/v1.1/comparison-{profile}.json`.
  Each `{profile}/{configuration}/daily.jsonl` contains every setup, gate, missing input,
  consumed opportunity, entry, and exit. `holdings.json` records actual execution windows.
- Standard outputs are `workbooks/regime-v1.1.xlsx`, `regime-v1.1.csv`, and
  `outcomes-action-v1.1.txt`, with separate protect, redeploy, and posture diagnostic reports.
  Old versioned outputs are not replaced.

The declared core profile does not imply complete ten-year OAS history: only **677 of 2,617**
dates have exact credit-owned evidence. Trend, volatility, price-proxy breadth, and liquidity
are exact on all these dates. Missing alternative credit leaves remain lower bounds, not calm
readings. Fourteen dates have an unresolved funding veto. The reduced profile excludes OAS from
the credit vote, not from the funding veto. Direct participation remains supplementary. FRED
history is current-vintage local history, not original-release data.

## Executable Comparison

An 80% permanent equity core plus 0/20/40% tactical exposure is rebalanced at the next adjusted
open, equally across SPY and QQQ. The old exposure owns the overnight gap. Cash earns zero,
borrowing costs 5% annually on ACT/365, and one-way turnover costs 5 bp. Adjusted open is raw
open times adjusted-close/raw-close. This is an ETF research approximation, not an options test.
Policy and accounting share the same weights from `POLICY_POSTURE_EXPOSURES`.

| Core-profile account | Net return | Portfolio drawdown | Average exposure |
| --- | ---: | ---: | ---: |
| Combined v1.1 | +402.43% | -29.81% | 0.944 |
| Untimed normal exposure | +474.41% | -30.86% | 1.000 |
| Untimed, same average exposure | +426.15% | -29.35% | 0.944 |

Timing loses 71.99 percentage points of cumulative return against normal exposure and 23.72
against the exposure-matched control. Its slightly smaller drawdown than normal exposure is not
evidence of timing skill: the matched control has both better return and smaller drawdown.
There are 820 reduced-exposure sessions and 87 increased-exposure sessions. Gross return is
+409.29%; summed daily turnover is 20.451 times equity, transaction charges 1.023% of daily
equity, and financing charges 0.337%. The latter sums are not terminal-wealth return differences.

In 2022 the combined account returns **-25.94%**, versus **-25.64%** untimed and **-25.05%**
exposure-matched. From 2021 through the comparison end, it returns **+109.36%**, versus
**+131.22%** untimed and **+122.48%** exposure-matched. Excluding the 2020 recovery does not
rescue the result. Open holdings are not force-closed to improve statistics.

### Fixed Treatments

Returns below are net total returns, not annualized. Configurations inherit the preceding
treatment except `R-confirm` and `P-break`, which separately branch from `P-resolution`;
`combined` enables both. Counts use core-profile executed entries in order
break / extension / washout / confirm.

| Configuration | Core net | Reduced net | Core portfolio drawdown | Core entries |
| --- | ---: | ---: | ---: | --- |
| R2-A: TVX stress, transmission gate | +489.96% | +503.23% | -30.86% | 0 / 3 / 3 / 0 |
| R2-B: TV stress, transmission gate | +508.69% | +512.64% | -30.86% | 0 / 3 / 10 / 0 |
| R2-C: TV stress, no transmission gate | +495.36% | +495.36% | -31.16% | 0 / 3 / 11 / 0 |
| W-opportunity | +482.54% | +476.20% | -31.25% | 0 / 3 / 12 / 0 |
| P-sequence | +473.39% | +467.14% | -31.25% | 0 / 2 / 12 / 0 |
| P-decay | +457.74% | +441.93% | -30.38% | 0 / 6 / 12 / 0 |
| P-resolution | +457.74% | +441.93% | -30.38% | 0 / 6 / 12 / 0 |
| R-confirm | +457.74% | +441.93% | -30.38% | 0 / 6 / 12 / 0 |
| P-break | +402.43% | +389.62% | -29.81% | 21 / 5 / 12 / 0 |
| Combined | +402.43% | +389.62% | -29.81% | 21 / 5 / 12 / 0 |

Exact entry-date/action overlaps expose changes without pretending shifted dates are independent
economic events. Against its parent, W-opportunity adds 7 entries, removes 6, and retains 8;
P-sequence adds 2, removes 3, retains 12; P-decay adds 6, removes 2, retains 12. P-resolution
changes no entries. P-break adds 21, removes 1 extension entry, and retains 17. R-confirm adds
none.

### R4 Coverage Correction

The original core R2-B row incorrectly required both breadth and credit-pressure observations
before accepting transmission, even when observed breadth alone proved `X >= 0.35`. After
repairing that gate and rerunning all ten configurations in both profiles over the same dates,
only core R2-B changes: washout entries rise from 3 to 10 and net return from +499.92% to +508.69%.
The B/C washout-count gap is now 10 versus 11, not 3 versus 11. Most of the original count gap
was a coverage bug, not evidence for dropping transmission. No thresholds were changed.

R2-A remains unchanged because its TVX continuous stress, peak, and release require both
components resolved; an observed maximum with a missing alternative is only a lower bound.
Core A/B therefore mixes arithmetic coverage with score geometry and must not be read as a clean
geometry comparison. The explicit reduced profile has complete numerical inputs and remains
unchanged: A/B/C have 9/10/11 washout entries. Reduced credit excludes OAS from its declared
numerical profile, not from the funding veto. Every combined-model result and its negative
economic conclusion remain unchanged. Canonical snapshots and workbook outputs need no backfill.

## Events, Holdings, And Misses

| Path | Raw eligible dates | Distinct raw path episodes | Actual entries | SPY 20d label | SPY mean actual closed holding |
| --- | ---: | ---: | ---: | ---: | ---: |
| protect-break | 324 | 26 | 21 | +1.6% | +1.94% |
| protect-extension | 27 | 7 | 5 | +4.2% | +3.43% |
| redeploy-washout | 71 | 12 | 12 | +2.5% | +0.90% |
| redeploy-confirm | 0 | 0 | 0 | unavailable | unavailable |

Raw eligible dates are not independent calls. Supporting same-direction opportunities are
consumed without a new position or renewed cap. Break, extension, and washout have 152, 22,
and 14 same-direction supporting dates respectively. There are no unresolved opposing-unused
conflicts in this historical replay, though conflict and valid-opposite transitions are tested.
All 38 selected holding episodes are closed by the scored end: 11 opposite-action exits,
11 protection repairs, 9 redeploy thesis failures, and 7 timeouts.

V1.0 read-only replay retains its original 14 protect and 8 redeploy native lifecycle events.
Using the same diagnostic rule on both versions, clustering same-direction signal days separated
by no more than 20 sessions gives 11/8 protect/redeploy clusters in v1.0 and 26/12 in v1.1.
This is a label-count sensitivity check, not a claim of statistical independence.

### Full Frozen Turning-Point Inventory

Use the 35-leg 5% inventory in the investigation's Appendix A unchanged. Assign a new redeploy
entry from the trough through twenty subsequent SPY sessions, capped before the next trough.
This produces eight matched new entries, versus seven under v1.0. Failed rebounds count too;
one more matched leg does not establish a better filter. The four other v1.1 redeploy entries
are 2016-01-27, 2021-09-27, 2022-05-03, and 2025-03-21, before later inventory troughs.

| Frozen trough | New v1.1 redeploy in its bounded window |
| --- | --- |
| 2016-02-11 | None; earlier January entry consumed the episode. |
| 2016-06-27 | None |
| 2018-02-08 | None |
| 2018-04-02 | None |
| 2018-10-29 | 2018-11-02 |
| 2018-11-23 | None |
| 2018-12-24 | None; October episode already consumed. |
| 2019-06-03 | None |
| 2019-08-05 | 2019-08-21 |
| 2020-02-28 | None |
| 2020-03-09 | None |
| 2020-03-12 | None |
| 2020-03-16 | None |
| 2020-03-23 | 2020-03-25 |
| 2020-04-01 | None; already-used March episode. |
| 2020-06-11 | None |
| 2020-09-23 | None |
| 2020-10-30 | 2020-11-03 |
| 2021-10-04 | None; September entry already consumed the episode. |
| 2022-01-27 | 2022-02-01 |
| 2022-03-08 | None; January episode already consumed. |
| 2022-05-19 | None |
| 2022-06-16 | None |
| 2022-09-06 | None |
| 2022-09-30 | 2022-10-04 |
| 2022-10-12 | None; September episode already consumed. |
| 2022-12-28 | None |
| 2023-03-13 | None |
| 2023-10-27 | None |
| 2024-04-19 | 2024-04-25 |
| 2024-08-05 | 2024-08-09 |
| 2025-04-08 | None; February episode already consumed. |
| 2025-04-21 | None |
| 2025-11-20 | None |
| 2026-03-30 | None |

This assignment labels entries, not ongoing exposure. Do not infer flat positioning from a
"None" cell, or count March 2020's several local legs as independent crises. Full gate traces
include rejected dates and unmatched protection, not only the inventory successes.

### Mechanism-Level Findings

1. **Consumption can prevent a second legitimate attempt.** On 2016-02-18, 2019-01-07,
   2022-03-15, 2022-10-24, and 2025-04-11, the raw washout gates pass but the earlier episode
   has been consumed. A long multi-leg decline can remain one stress episode well after a failed
   entry. This is the specified one-entry-per-episode policy, not a stale-cache error. Re-entry
   would need an independently justified new-opportunity definition, not an arbitrary reset
   chosen to admit these dates.
2. **Price opportunity can disappear before confirmation.** On 2018-02-15, 2018-04-18,
   2023-11-03, and 2026-04-07 the washout path's other gates pass, but the half-recovery bound
   fails. The new bound is interpretable; it is not automatically less restrictive or better
   than continued fear. November 2018's accepted rebound remains a counterexample to broader
   entry eligibility, not a case to omit from the study.
3. **The pullback path is reachable but historically inactive.** It has 241 armed dates,
   443 price-recovery confirmations, and 127 opportunity-passing dates, but no complete
   conjunction. These counts are not mutually exclusive or conditional rates. The strong
   short-term recovery requirement can conflict with retaining half a shallow pullback's
   recovery distance. Synthetic source/transition tests prove execution reachability, not
   economic usefulness. Do not lower the gate merely to obtain a desired event count.
4. **Protection's costs dominate the combined account.** Break entries broaden coverage of
   2018 Q4, 2022, and 2023 damage, but protection also misses substantial upside. The 2024-01-04
   extension entry survives the redesign; July 24, 2024 has no new protective action. On
   2025-08-04 protection is already held rather than newly triggered after that rebound.
   Removing strength decay adds more protection but worsens cumulative returns here. The direct
   break path worsens both total and post-2020 returns; its modest drawdown reduction does not
   beat the exposure-matched control. Further work must study restoration delay and false breaks,
   not merely optimize forward bearish labels.
5. **Held returns differ materially from attractive long-horizon labels.** Washout's mean SPY
   65-day label is +7.3%, but its mean actual closed holding earns +0.90%. In particular, March
   2022 is no longer a new entry, while August 2019 is. Read the actual entry/exit trace before
   attributing a distant recovery to an exposure increase that already failed or expired.

## Follow-Up Boundary

Preserve these adverse results. Review the economics of opportunity expiry, consumed stress
episodes, and protection repair before proposing another change. A next proposal should state
what new observation establishes a genuinely new opportunity and why an action's confirmation
horizon matches its setup. Keep those decisions distinct from fixing a demonstrable coding bug.
No additional parameter search was performed as part of this implementation.
