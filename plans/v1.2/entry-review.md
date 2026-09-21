# V1.2 Entry Review

Scope: improve the event table, not the simulated account. Keep v1.2, exits, and washout
rules unchanged. Work on extension, break, and confirm separately. No threshold search.

## Measurement

Frozen starting point: commit `28ff460`, 2016-01-04 through 2026-06-01, 2,617 EOD dates.
The entry-only replay reproduces every baseline lifecycle/action and the displayed table.
It uses canonical saved pressure/input observations and production forward-label functions,
not workbook inputs. Each trial runs its own chronological state in core and reduced profiles.
Results, all event labels, added/removed events with before/after gates, and chronological
cohorts are under `data/research/regime/v1.2/entries/`. The reproducer is `entry_research.py`.
Previously studied history remains development data; different versions and nearby events
are not independent samples. Show 20/40/65d SPY/QQQ returns and entry-relative drawdowns.

## Extension Inventory

V1.0's fourteen event dates compared with current v1.2:

| Dates | Current reason |
| --- | --- |
| 2016-04-05, 2016-04-07, 2019-11-19 | Price damage fails; these old alerts preceded gains. |
| 2019-05-07, 2019-12-03, 2021-11-11, 2023-02-09, 2024-01-04 | Retained. |
| 2020-01-03, 2020-01-24 | Price damage fails and the December setup is consumed. |
| 2023-04-25 | Raw gates pass but setup is consumed; old alert preceded gains. |
| 2023-06-22 | Price/volatility confirmation fails and setup is consumed. |
| 2024-07-10 | Price damage fails; this loses an ordinary-correction warning. |
| 2025-08-04 | Current model entered August 1; remaining setup consumed. |

Current entries not on the old event dates: 2016-06-13, 2017-03-22, 2019-07-19, 2025-08-01.
The v1.0 40d mean includes January 2020 returns of -6.88% and -31.79%; these related warnings
must not be treated as independent evidence of ordinary-correction precision.

## E1: Repair The Original Divergence

Before replay: a remembered divergence can repair when its original observed leaves remain
below 0.35 for the existing three sessions. Missing unrelated alternatives are not evidence
that the original divergence persists. Missing the original leaf still prevents proving repair.
Core currently requires every credit alternative to be present, so absent OAS can keep a repaired
HYG/TLT warning alive. This changes entry memory only; no exit, arming, or threshold change.

Result: core extension stays at 9 events. SPY 20/40/65d returns change from
+1.21/+3.82/+2.23% to +0.33/+0.63/+2.30%; drawdowns change from
-2.4/-2.4/-4.1% to -2.8/-5.8/-6.3%. QQQ returns become +0.7/+2.7/+5.0%.
Every changed entry: May 7 -> May 8 2019, December 3 2019 -> January 27 2020,
February 9 -> February 10 2023. Clearing repaired divergence delays the first and
third entries; removing the December entry leaves the setup unused for January.
Break, washout, and confirm entries do not change. Reduced-profile entries do not change.

This is a correctness fix, not evidence that extension precision is solved. Excluding
2020 entry dates, SPY returns are +0.73/+3.72/+3.69%, versus +1.21/+3.82/+2.23%
before. Even that sensitivity retains December 2019 labels extending into the crash;
the replay also reports labels that do not overlap February 20-April 30 2020.
Retain the repair for consistent evidence semantics, not for the attractive full-period mean.
