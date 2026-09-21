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

## E2: Internal Breakdown Before Index Damage

Before replay: retain remembered extension, prior divergence, intact MA200 trend, and
current volatility deterioration. Permit confirmation by price damage OR both breadth
and credit deteriorating now with both having diverged previously. A single same-day
relative move is not enough. Reuse existing family thresholds and divergence memory;
no parameter search. Attribute new internal-only entries to their actual causal families.
Exit rules and other paths remain unchanged. Compare against E1 and frozen starting v1.2.

Result: retain this earlier-warning path. Relative to E1, add July 10 2024; move August 1
2025 to July 31. The August 6 2024 break entry is absorbed into the existing extension
holding. Those are ALL changed events, in both profiles. Washout is unchanged.

Core extension 10 events: SPY -0.6/+0.1/+2.2%, QQQ -0.8/+1.4/+4.0%,
SPY drawdowns -3.5/-6.2/-6.6%, QQQ -4.2/-6.3/-7.3% (20/40/65d).
Without pandemic-overlapping labels: SPY -0.32/+2.85/+3.39% versus
E1 +0.73/+3.72/+3.69%. Pre-2020 events are unchanged; post-2020 SPY means change
from +1.37/+4.55/+4.79% to -0.64/+2.81/+4.02%. Reduced extension agrees exactly.

This restores an ordinary-correction warning but is not broad validation: only two new
entry dates drive the incremental result. July 2025 is still a false alarm followed by
gains, January 2024 is retained, and there are no extension entries during 2022.
The 40d non-pandemic return remains positive. Keep these limitations visible.

## B1: Fresh Breakdown With Internal Corroboration

Before replay: preserve the existing persistent MA50/20d damage setup and 5d damage
threshold. Entry additionally needs both indexes below their prior five closing prices
and breadth OR credit deterioration at the existing family gate. Volatility responding
to falling prices alone does not establish transmission. This tests fresh continuation
of selling, not just elapsed time below moving averages. Missing prior prices are unknown.
Keep retry limits, washout, and exits unchanged; use the actual internal entry cause.

Result: do not keep the combined B1 rule. Core breaks shrink 28 -> 18; SPY
20/40/65d +0.6/+3.0/+6.1%, QQQ +0.5/+4.0/+7.5%, SPY DD -4.9/-6.7/-7.2%.
The 40/65d averages worsen despite removing several recovery-day alerts. January and
September 2022 warnings are delayed by requiring weak breadth/credit proxies; price
weakness can be broad without relative breadth weakness, and HYG/TLT also embeds rates.
Reduced produces only 15 entries and different results, reinforcing input sensitivity.

## B2: Isolate Fresh Price Follow-Through

Before replay: remove B1's new breadth/credit-only restriction and causal-family change.
Keep only the new five-session joint closing low. This is a direct ablation of the failed
combined hypothesis, not a threshold search. All original non-price families can corroborate.

Result: also discard B2. Core/reduced break entries are identical: 23 events, SPY
+1.8/+3.7/+7.1%, QQQ +1.6/+4.5/+8.3%, SPY DD -4.0/-5.6/-6.1%.
Fresh lows remove some bounce-day false alarms but do not identify whether selling will
continue. Requiring simultaneous new lows delays useful warnings and can concentrate
entries near exhaustion. Neither trial fixes break entry selection. Production break
rules are unchanged, not silently tightened. All trial date changes, labels, and gate
reasons remain in the entry replay artifacts; report this topic as unresolved.

## C1: Continuation From A Price Base

Before replay: retain distinct below-MA50 pullback after an established uptrend, intact
MA200 structure, and the 20-session setup lifetime. Replace panic-style trend strength
and half-recovery requirements with: each index has avoided a new/equal episode low for
the existing three-session persistence, both close above their preceding five closes,
both have nonnegative 5d returns, and both remain below their pre-pullback anchors.
Require an independent non-price stabilization family at the existing ordinary 0.35
family gate, not panic-strength 0.75. Funding remains required. This is a small base
breakout with remaining continuation room, not just an MA50 reclaim or a forced V bounce.
Washout and exit rules are unchanged. No fit to specific near-miss percentages.

Result: seven core/eight reduced confirm events. Core SPY +1.6/+1.0/+4.9%, QQQ
+1.8/+1.0/+5.4%, SPY DD -1.6/-3.0/-3.7%. No pandemic events; pre-2020
SPY +2.14/+1.58/+4.54%, post-2020 +1.43/+0.75/+5.02%. This removes zero
coverage, but 40d performance is weak. August 2023 and January 2026 are false starts.
October 2023 confirm also leads to a later break retry on October 27, an adverse
cross-path effect; washout entries and extension entries are unchanged from E2.

## C2: Track Sequential MA50 Crossings

Before replay: C1 still inherits an accidental synchronized-crossing requirement: the
immediately preceding day must have both indexes above MA50, then both must be below.
Start tracking at the first index's loss of MA50 after established trend. Require a
recorded day with both below MA50 before confirm eligibility. Do not reset the anchor,
clock, or lows when the second index crosses. Preserve the same lifetime and MA200 rule.
This models a joint pullback developing over days rather than requiring simultaneous crosses.

Result: retain C1+C2 as the continuation definition, with coverage restored but alpha
unproven. Core confirm grows 7 -> 13: SPY +1.3/+2.0/+5.4%, QQQ +1.9/+2.4/+7.4%,
SPY DD -1.5/-3.2/-4.3%, QQQ DD -2.1/-3.7/-5.0%. Reduced has 14 entries:
SPY +1.5/+2.4/+5.7%, with SPY DD -1.5/-3.1/-4.1%. None overlaps the pandemic
window. Pre-2020 SPY means are +1.85/+3.03/+6.37%; post-2020 +1.03/+0.93/+4.16%.
Recent-period weakness and small samples prevent a claim of reliable continuation alpha.

C2 adds April 5 2018, October 11 2019, September 28 2020, September 11 2024,
January 17 2025, and February 20 2026 to C1, with no removed confirm dates. All six
previously lacked setup/opportunity despite valid recovery evidence. Reduced additionally
has April 26 2024, which is a washout entry in core. The new February 2026 confirm leads
to a March 12 break retry after failure; this and the October 2023 retry worsen break's
entry averages despite unchanged break predicates. Do not hide this cross-path consequence.

## What Actually Changed

Same 2,617 dates; each return triplet is SPY 20/40/65d. This is the user's action-entry
summary, not account performance. Unchanged washout predicates also yield identical
washout event dates and labels in each profile. Exits are unchanged.

| Action | Starting v1.2 events / returns | Current v1.2 events / returns |
| --- | --- | --- |
| protect-extension | 9 / +1.2%, +3.8%, +2.2% | 10 / -0.6%, +0.1%, +2.2% |
| protect-break | 29 / +1.3%, +2.7%, +5.7% | 30 / +1.5%, +3.2%, +6.2% |
| redeploy-confirm | 0 / unavailable | 13 / +1.3%, +2.0%, +5.4% |
| redeploy-washout | 18 / +3.5%, +5.4%, +7.1% | Identical |
| all days | 2,617 / +1.3%, +2.5%, +4.1% | Identical |

Extension improves, although the evidence is sparse. Confirm works as a separate
continuation path, but 40d returns remain below all days. Break remains unresolved and
the combined model makes its table worse. This is not a completed performance fix.
Next research on break needs a mechanism distinguishing persistent selling from exhausted
selling; neither an additional fresh-low filter nor relative breadth/credit alone did that.
Do not keep testing nearby thresholds against these same dates until the averages look good.

### Audit And Verification

- `entry-event-changes.csv` contains EVERY added/removed event, all horizons, both input
  profiles, gate values, consumption state, and selected action before/after each trial.
  Returns/drawdowns there are decimal fractions. Failed B1/B2 trials are included.
- `entry_research.py audit` regenerates that comparison from frozen trial snapshots;
  replays use canonical Python calculations, never manually edited scores or labels.
- Production backfill recomputed 2,693 v1.2 dates through September 18 without fetching.
  All 2,617 comparison-date lifecycles, actions, and pressure features match the final
  research replay exactly. The complete CLI action summary also matches exactly.
- The 5,386 v1.1 regime/signal artifacts retain their pre-change combined path/content
  SHA-256: `dc19b94dd5b756bd48192c899fcce7e10380ea763f90fddf4a3999fccf86e152`.
- Full suite: 313 tests pass. Tests cover original-evidence repair, sequenced internal
  extension confirmation, sequential pullbacks, renewed lows, false breakouts, missing
  confirmation, structural invalidation, and washout/confirm overlap.
