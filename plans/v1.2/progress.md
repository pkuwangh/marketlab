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
