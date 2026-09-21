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
