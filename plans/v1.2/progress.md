# V1.2 Work Log

One topic at a time: change, tests, same-window replay, results, commit. V1.2 data is replaceable;
v1.1 snapshots and exports stay unchanged. No new CLI paths or model-management workflow.

## Comparison

Use 2016-01-04 through 2026-06-01, canonical observations, core and reduced numerical profiles,
the existing next-open account/cost assumptions, and full/2022/post-2020 cohorts. Check changed
entries, actual holdings, and concentration outside the March 2020 recovery, not just forward
labels. This is previously studied development history, not out-of-sample validation.

V1.1 core starting point: net +402.43%, portfolio drawdown -29.81%, matched-exposure control
+426.15%; 21 break, 5 extension, 12 washout, 0 confirm entries. Untimed net +474.41%.

## 1. Extension Persistence

Before replay: repair interrupted three-of-ten arming after expiry. Clear obsolete hits once
when cooling permits renewal, not on every subsequent quiet day. Keep thresholds, fixed age,
continuous-run renewal restriction, and all other action rules unchanged. This is a correctness
repair regardless of its historical return effect.

Result: core net +390.63% (down 11.80 percentage points), drawdown -29.81%, matched +421.41%;
20 break / 7 extension / 12 washout / 0 confirm entries. New extension entries are 2019-05-07,
2023-02-10, and 2023-04-25; the changed holding timeline absorbs the old 2019-05-21 break and
2023-06-26 extension entries. Reduced net +389.68%, drawdown -29.81%. Core post-2020 net
+103.54%; 2022 unchanged at -25.94%. Washout holdings unchanged. Correctness restored, not alpha.

All ten existing variants were rerun in both profiles under
`data/research/regime/v1.2/01-persistence/`. Full suite: 280 tests; lint passes.

## 2. Relative Volatility Direction

Before replay: require an actual VVIX rise for the relative-lead deterioration reading. Preserve
low-VIX/rising-VVIX warning and high-VIX/cooling-VVIX recovery, scales, ownership, and all exits.
Two falling indexes must not count as fresh stress solely because VIX falls faster. Measure
holding/exit changes and both profiles; do not add an exit-delay parameter.

Result: core net +398.04% versus +390.63%, drawdown -29.06% versus -29.81%, matched +431.12%.
Reduced net +400.28% versus +389.68%, but drawdown worsens slightly to -29.94%. Core 2022
improves to -25.15% and post-2020 to +108.90%; reduced 2022 is slightly worse at -25.94%.
Washout's mean held return does not improve (+0.81%, -0.16% excluding the March 2020 entry);
the aggregate benefit includes changed protection and restoration. Retain the directional
correction without claiming it fixes washout performance. Traces: `02-volatility/`.

## 3. Renewed Washout Damage

Before replay: use the existing normalized five-session price damage, not max(5d,20d) residual
damage, in washout thesis failure. Keep the 0.35 damage threshold, volatility threshold, rising
stress conjunction, entries, holding caps, and all other exits unchanged. Save the short damage
reading in lifecycle state so the exit is auditable. Test a strong recovery still carrying old
20-day losses, followed by actual renewed selling; do not introduce a delayed-exit parameter.

Tested rule: replace the trend-family failure check with
`mean(clip(-SPY_5d/0.03), clip(-QQQ_5d/0.04)) >= 0.35`, requiring both inputs. Synthetic
recovery/new-selling regression passed. Replay core net fell to +391.41%, drawdown -29.47%;
reduced net +393.62%, drawdown -30.34%. Only two core holdings changed: February 2022 exit
delayed Feb 11 -> Feb 14 (SPY -1.34% -> -3.42%), March 2025 exit delayed Mar 27 -> Mar 31
(-0.63% -> -3.67%). Post-2020 and 2022 both worsen. The 5d-only hypothesis is not retained;
production remains topic 2's rules. Detailed replay remains under `03-washout-failure/`.

## 4. New Damage After A Consumed Opportunity

Before replay: allow at most two entries per washout/break setup, only when both indexes make
new lows below the lows known at the previous holding's exit. Washout also requires a new
qualifying stress observation; break still needs persistent direct damage. No retry while
holding the same direction, no daily renewal, and no reset of an active holding's cap. Keep
setup identity for diagnostics; entry dates already distinguish executed attempts. This is a
single bounded-retry hypothesis, not a search over retry counts or new price thresholds.

Result: after correcting the trial to retain every intervening holding low, core net +409.85%
versus +398.04%, drawdown -28.75% versus -29.06%, matched +434.06%. Reduced net +417.18%
versus +400.28%, drawdown -28.94%. Washout grows from 12 to 18 entries; mean held SPY return
+1.88%, or +1.31% without the March 2020 entry. Break grows from 21 to 26 entries. However,
core 2022 worsens (-26.15% versus -25.15%) and post-2020 falls slightly (+107.42% versus +108.90%).
Keep the bounded new-damage mechanism for restored coverage, not as a uniformly better filter.
The first trial incorrectly used only entry/exit lows and overstated the benefit; its corrected
results above replace it. Traces: `04-new-damage-retry/`. Full suite: 289 tests; lint passes.

## 5. Orderly Pullback Confirmation

Before replay: an intact-trend continuation needs both indexes back above MA50 with nonnegative
5d returns, plus the existing strong independent non-price family and clear funding. Replace
the panic-specific half-recovery budget with the causal pre-pullback highs as the entry ceiling
for both indexes. Keep the distinct below-MA50 setup, MA200 structure, 20-session setup lifetime,
failure rule, and holding cap. No change to washout's half-recovery gate; no fitted bounce cutoff.

Result: seven core/eight reduced confirm entries, but core mean held SPY -0.72%, reduced -0.15%.
Core net falls +409.85% -> +397.78%; reduced +417.18% -> +414.73%; drawdowns do not improve.
Core entry execution dates: 2017-08-31, 2018-02-16, 2019-05-17, 2020-10-06, 2023-08-30,
2025-11-26, 2026-01-27. Three reach the cap, three exit to protection, one fails structurally.
The 2023 continuation loses 4.21% in SPY; reclaiming MA50 is not enough to establish durable
recovery. Trial removed, rather than relaxing more gates to force coverage. Confirm remains an
unresolved path with zero historical entries under current rules. Traces: `05-pullback/`.

## 6. Extension Evidence Freshness

Before replay: measure extension expiry/decay from its last qualifying observation, not initial
arming. Keep identity, consumption, divergence ordering, and the fixed holding cap unchanged.
Freshness can extend an unused setup but cannot reset an already-used opportunity or holding.
No new lifetime parameter: keep the existing 40-session window.

Result: core net +428.17% versus +409.85%, reduced +424.66% versus +417.18%; drawdown and
2022 unchanged. Core post-2020 +113.36% versus +107.42%. Core 25 break / 8 extension /
18 washout entries. Mean held SPY during extension falls +2.86% -> +1.79%, still a missed-upside
cost on average. Keep the freshness/identity separation, not a claim that extension is solved.
Traces: `06-extension-freshness/`. Full suite: 289 tests; lint passes.

## 7. Protection Repairs Its Original Evidence

Before replay: persist the observed deteriorating leaves behind each protective entry, including
remembered divergence. Require those leaves to be observed and below the existing damage gate
for repair; an unused, missing alternative must not permanently block restoration. Retain positive
5d momentum, three-session persistence, break's MA50 repair, and fixed caps. Current corroborated
trend-plus-nonprice damage blocks restoration even if original leaves repaired. Missing original
evidence still blocks repair. No change to entry predicates or family aggregation.

Result: core net +438.78% versus +428.17%; matched +453.64%. Drawdown worsens -28.75% ->
-28.94%; core 2022 worsens slightly (-26.15% -> -26.21%). Post-2020 improves +113.36% ->
+117.13%. Reduced net +425.60% versus +424.66%. Core now has 30 break / 9 extension / 18
washout entries. All protection holdings end by repair/opposite action, none by the 65-session
cap. Washout holdings unchanged. Retain causal repair with coverage and new-damage safeguards;
this narrows the core/reduced coverage artifact but does not eliminate protection's upside cost.
Traces: `07-causal-repair/`. Full suite: 294 tests; lint passes.

## 8. Break Entry Requires Recent Selling

Before replay: replace break's max(5d,20d) trend-damage gate with its existing normalized 5d
price-damage reading at the same 0.35 threshold. Keep three-session below-MA50/negative-20d
persistence, independent corroboration, retries, and exits unchanged. This tests fresh damage
versus residual loss, not a faster persistence threshold or a prediction of shock announcements.

Result: core net +442.04% versus +438.78%, reduced +428.77% versus +425.60%; drawdowns,
2022, and post-2020 unchanged. One core/reduced break entry removed; remaining holdings unchanged.
Keep the direct-recent-selling requirement as a clearer break definition, with very limited
historical evidence of improvement. This is not proof that non-price corroboration adds alpha
over an equally delayed price-only strategy. Traces: `08-break-damage/`.
The removed signal is 2016-05-19. Full suite: 296 tests; lint passes.
