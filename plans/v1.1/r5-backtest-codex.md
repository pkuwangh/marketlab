# R5 Backtest Investigation: Four V1.1 Actions

**Author:** Codex  
**Date:** September 21, 2026  
**Baseline:** commit `7d77258`, including the R4 transmission correction.  
**Status:** investigation only. No algorithm, thresholds, versions, observations, canonical
snapshots, or workbook outputs changed. Proposed repairs below have not been replayed as a strategy.

## 1. Main Findings

1. **`redeploy-confirm` has a mechanically narrow opportunity window, not a reporting omission.**
   Fourteen pullback episodes provide 241 armed days. Only 25 pass price recovery; only one also
   retains half the original recovery distance; that day's independent confirmation is unresolved.
   The intended October 2021 and April 2024 examples demonstrate this conflict directly.
2. **`redeploy-washout` improves some coverage but spends opportunities on earlier rebounds.**
   Twelve entries become only 3.5 sessions of exposure at the median. Nine exit through thesis
   failure. An important subset of those failures mistakes lingering past damage and two falling
   volatility indexes for fresh deterioration. Episode consumption then prevents a later attempt.
3. **`protect-extension` has both a newly identified implementation bug and genuine design losses.**
   After expiry, a quiet day repeatedly clears the persistence window, accidentally changing
   three-of-ten arming into consecutive-hit arming. Separately, the fixed episode lifetime loses
   recent setups, stricter price damage removes advance warnings, and removing the decayed-strength
   gate admits costly ordinary pullbacks. Correct deduplication alone does not explain the result.
4. **`protect-break` is not merely late; its holding and reset rules compound poor entry selection.**
   Fourteen of 21 actual protective windows have positive SPY returns. Conversely, useful protection
   can end on an early washout rebound, after which both opportunities are consumed and neither
   direction can act again during the same decline. There are 133 otherwise-eligible break days
   with neutral held posture and an already-consumed break episode.
5. **Do not start with a threshold search.** Repair the arming contract, separate new deterioration
   from residual damage, and define what an episode permits after an intervening failed thesis.
   Then study a pullback-specific opportunity/confirmation contract. These are distinct changes.

The combined account remains +402.43% versus +474.41% untimed and +426.15% at matched average
exposure. The useful engineering and measurement changes in v1.1 have not established timing alpha.

## 2. Data And Measurement

The common window is **2016-01-04 through 2026-06-01**, 2,617 saved EOD dates. Sources:

- [V1.1 action outcomes](../../workbooks/outcomes-action-v1.1.txt) and
  [v1.0 action outcomes](../../workbooks/outcomes-action-v1.0.txt).
- Explicitly versioned `data/snapshots/regime/market/<date>/eod/v1.0/regime.json` and `v1.1/regime.json`.
- SPY/QQQ observations under `data/observations/prices/daily`, using `return_close` for labels.
- `data/research/regime/v1.1/core/combined/daily.jsonl` and `holdings.json`, plus the fixed
  comparison variants. Every combined trace state/action was checked against its canonical snapshot:
  **zero mismatches** across the common window.
- The earlier [Codex](backtest-investigate-codex.md) and [Claude](backtest-investigate-claude.md)
  investigations. Their hypotheses are useful, but their causal claims are rechecked rather than
  inherited. The accepted corrections in [R3](r3-proposal.md) still apply.

I recomputed forward returns and entry-relative losses from the raw adjusted closes, used the
production `_action_event_dates` grouping for v1.0, and inspected v1.1's persisted gates and episodes.
The workbook tables reproduce at their displayed precision. Workbooks are outputs, not model inputs.

**Keep these quantities distinct:**

| Quantity | Meaning |
| --- | --- |
| Signal date | EOD decision date; all event dates below use this unless labeled execution. |
| Execution date | Following observed session's adjusted open. |
| 20/40/65d return | Adjusted-close return from the signal close, irrespective of actual exit. |
| `spy_dd` / entry MAE | Minimum subsequent closing return from that signal price, capped at zero; not running-peak drawdown. |
| Held ETF return | Entry-open to exit-open underlying return, not tactical portfolio P/L. |
| Portfolio return/drawdown | The executable account with exposure, overnight ownership, costs, and financing. |

`all_days` includes all 2,617 dates, including action dates, not only the 2,579 `no_change` dates.
Overlapping horizons and related episodes are not independent samples. Historical FRED values
remain current-vintage data; credit coverage is incomplete before September 2023, and historical
direct S&P participation is absent in this window. No news-causality labels are inferred here.

### Reproduced SPY Results

| Cohort | Events/dates | 20d return / MAE | 40d return / MAE | 65d return / MAE | Mean held ETF return |
| --- | ---: | ---: | ---: | ---: | ---: |
| All days | 2,617 | +1.27% / -2.45% | +2.54% / -3.50% | +4.07% / -4.44% | Not an event cohort |
| Protect-extension | 5 | +4.21% / -0.15% | +4.75% / -0.15% | +2.82% / -2.53% | +3.43% |
| Protect-break | 21 | +1.58% / -2.63% | +1.95% / -4.30% | +4.48% / -5.34% | +1.94% |
| Redeploy-washout | 12 | +2.47% / -3.63% | +4.95% / -5.04% | +7.26% / -5.09% | +0.90% |
| Redeploy-confirm | 0 | Unavailable | Unavailable | Unavailable | Unavailable |

Protect-break's 40d return is lower than all days, but its 20d/65d returns are higher. Its MAE
is **more negative**, not better, at all three horizons. A large potential loss can identify a
risky environment without demonstrating that the held protection actually avoided that loss.

## 3. Redeploy-Confirm: Confirmation And Opportunity Disagree

### Actual Gate Funnel

| Cumulative predicate | Days |
| --- | ---: |
| Pullback armed | 241 |
| Also price recovery | 25 |
| Also remaining half-recovery opportunity in both indexes | 1 |
| Also independent non-price confirmation | 0 |
| Also funding clear | 0 |

This is an ordered intersection, not an exclusive attribution of failed gates. Independently,
127 armed days have opportunity, 102 have confirmed non-price support, 47 fail non-price support,
and 92 have unresolved non-price support. Funding is clear on every armed date. The zero is
upstream of consumption, path priority, or competing protection.

The only recovery-plus-opportunity date is **2019-08-30**:

- Trend stabilization 0.815; SPY/QQQ have recovered 47.4%/46.3% of their episode damage.
- Best observed non-price stabilization is volatility at 0.652, below 0.75.
- Missing OAS makes the complete confirmation predicate **unknown**, not proven false.
- Held posture is neutral. The preceding washout holding ended on August 26; it is the same
  broad recovery episode, but not an already-held redeploy position that mechanically blocks entry.

### Why The Gates Rarely Intersect

Price recovery requires positive five-session returns in both indexes and trend stabilization
at least 0.75. Trend stabilization is the maximum of normalized 5d and 20d averages. Its 5d full
scales are 3% for SPY and 4% for QQQ. For example, gains of 2.25% and 3% produce a 0.75 reading.
This is a substantial burst relative to a shallow pullback, especially while the trailing window
still contains down days. Simultaneously, each index must remain below the midpoint between its
episode low and its pre-pullback anchor.

That is not a universal mathematical impossibility, but it asks a modest correction to provide
both a strong absolute rally and a still-cheap entry. The earlier expected examples show it:

| Date | Trend stabilization | Best other family | SPY/QQQ fraction recovered | Block |
| --- | ---: | ---: | --- | --- |
| 2021-10-07 | 0.545 | 1.000 | 43.4% / 35.6% | Price recovery not strong enough. |
| 2021-10-18 | 0.977 | 1.000 | 80.3% / 68.9% | Price recovery arrives after opportunity expires. |
| 2024-04-23 | 0.070 | 1.000 | 37.5% / 32.8% | Price recovery not strong enough. |
| 2024-04-26 | 0.934 | 1.000 | 46.8% / 51.5% | QQQ has crossed the halfway limit. |
| 2023-08-23 | 0.355 | 1.000 | 31.3% / 39.9% | Price recovery not strong enough. |
| 2023-08-29 | 0.811 | 1.000 | 59.9% / 60.5% | Both have crossed halfway. |

The 51.5% example is an explanation, **not a proposal to tune the limit to 52%**.

### Setup Coverage Is A Separate Constraint

There are fourteen episodes: ten expire at age 21, two lose the MA200 condition, and two
complete by regaining their anchors. Ages start at zero, so a 20-session limit permits 21
inclusive armed dates. The September 15, 2023 episode expires on **October 16**, not around
October 20. The subsequent October 27 low also breaks the long-term trend requirement.

Arming additionally requires both indexes to move from above MA50 to below MA50 on the same
session, while staying above MA200 and having positive prior 60d returns. Staggered index
crossings can miss this transition. A positive 60d return is a trailing endpoint comparison,
not a requirement to rebuild sixty consecutive days of strength.

October 2022 and the final October 2023 trough are damaged-trend repair examples, not reasons
to silently redefine an intact-trend pullback. October 2021 and April 2024 were the more direct
examples proposed in the earlier Codex investigation, and the model does arm for both.

### Research Direction

Give this path its own economic definition of opportunity. A continuation thesis expects a
trend to resume, potentially beyond the old high; it need not buy the first half of the distance
back to that high. Conversely, simply accepting a weaker numerical stabilization score would
create a less selective version of the same contradiction.

Specify a structural recovery test and an entry-extension/risk-distance constraint appropriate
to continuation. Keep evidence of a distinct pullback and independent non-price confirmation.
Study staggered crossings separately from the recovery/opportunity conflict. Keep repaired bear
markets out of this path unless a separate thesis is explicitly approved. Freeze these choices
before examining their returns; neither extra events nor the October 2021 example is a target.

## 4. Redeploy-Washout: The Entry Label Is Not The Captured Recovery

### Every Entry

| EOD signal | SPY 20d / 65d label | Execution interval | Sessions | Held SPY | Exit |
| --- | --- | --- | ---: | ---: | --- |
| 2016-01-27 | +3.94% / +10.24% | Jan 28-Feb 2 | 3 | +1.05% | Thesis failed |
| 2018-11-02 | +2.73% / +0.06% | Nov 5-Nov 15 | 8 | -1.34% | Thesis failed |
| 2019-08-21 | +2.95% / +6.58% | Aug 22-Aug 26 | 2 | -2.03% | Thesis failed |
| 2020-03-25 | +13.08% / +22.12% | Mar 26-Apr 22 | 18 | +11.55% | Thesis failed |
| 2020-11-03 | +9.15% / +16.71% | Nov 4-Dec 3 | 20 | +7.57% | Holding expired |
| 2021-09-27 | +2.92% / +8.25% | Sep 28-Oct 1 | 3 | -1.98% | Opposite protection |
| 2022-02-01 | -3.33% / -8.36% | Feb 2-Feb 3 | 1 | -1.00% | Thesis failed |
| 2022-05-03 | -1.63% / -0.27% | May 4-May 10 | 4 | -3.02% | Thesis failed |
| 2022-10-04 | +1.73% / +3.15% | Oct 5-Oct 11 | 4 | -4.06% | Thesis failed |
| 2024-04-25 | +4.46% / +8.00% | Apr 26-May 24 | 20 | +4.25% | Holding expired |
| 2024-08-09 | +2.52% / +12.68% | Aug 12-Aug 13 | 1 | +0.43% | Thesis failed |
| 2025-03-21 | -8.88% / +7.97% | Mar 24-Mar 27 | 3 | -0.63% | Thesis failed |

Median holding is 3.5 sessions; median held SPY return is -0.82%. Five of twelve holdings
are positive. Of nine thesis-failure exits, **six**, not seven, have negative held SPY returns.

Excluding only the March 2020 entry, mean held SPY return falls to -0.07%; excluding both
2020 entries gives -0.83%. This is a concentration diagnostic, not a rule to delete shocks.
Do not extend that result to every fixed-horizon label: without the March 2020 signal, the
20/40/65d means are still +1.51%/+3.63%/+5.91%. The severe concentration claim concerns
**captured holding returns**, not a proof that every long-horizon label is a one-event artifact.

### A Concrete Failure-Signal Problem

Washout thesis failure requires trend deterioration, volatility deterioration, and increasing
continuous stress. Those names suggest renewed selling/hedging, but the underlying readings can
mean something different:

- Trend deterioration takes the maximum over 5d and 20d readings. Negative 20d returns can
  retain a large deterioration value while prices are recovering strongly over 5d.
- `vvix_vs_vix` deterioration includes `max(0, (VVIX_5d_return - VIX_5d_return) / 0.12)`.
  It does not require VVIX to rise. Both indexes falling, with VIX falling faster, can yield
  maximum deterioration. That is relative normalization speed, not necessarily renewed fear.
- Any increase in continuous stress qualifies, without requiring a new price failure. Normal
  fluctuations in a still-stressed recovery can therefore complete the exit predicate.

| Exit-decision date | SPY/QQQ 5d return | VIX / VVIX 5d return | Trend D / vol D | Stress change |
| --- | --- | --- | --- | --- |
| 2016-02-01 | +3.2% / +2.1% | -17.3% / -12.9% | 0.646 / 0.367 | 0.515 -> 0.546 |
| 2022-02-02 | +5.5% / +6.9% | -30.9% / -19.5% | 0.617 / 0.950 | 0.765 -> 0.769 |
| 2024-08-12 | +3.1% / +3.7% | -46.3% / -29.6% | 0.766 / 1.000 | 0.811 -> 0.882 |

In each row, all direct VIX/VVIX/term-structure deterioration leaves are zero; the relative pair
alone supplies volatility deterioration. Both index prices remain above their entry-episode
lows. On February 1, 2016 and August 12, 2024, the raw washout **entry** predicate also passes
on the same day that the held washout thesis **fails**. Strong stabilization and residual
deterioration can coexist mathematically, but this is an unresolved economic inconsistency.

This does not mean every exit was wrong. May 2022 genuinely broke the entry-episode lows of
both indexes, and exiting limited further losses. Nor does the February 2022 example prove
holding longer was profitable; the market subsequently deteriorated. The repair must be about
the meaning of the evidence, not protecting favorable historical returns from exit.

**Proposed study:** separate directional cases in the VIX/VVIX relationship, preserving high-VIX
and cooling-VVIX recovery evidence and actual VVIX-up divergence. Treat two falling indexes as
normalization context unless additional absolute deterioration is observed. Give residual
medium-term damage a different role from renewed short-term selling. Specify an entry/exit
consistency test, then compare exit behavior with entry rules frozen. Do not just lower the
failure threshold's sensitivity until August 2024 survives.

### Coverage And Consumption

Reproducing the earlier independent 5% decline/recovery inventory gives the same **35 local
legs**. Assign entries from the trough through twenty subsequent sessions, ending before the
next trough. V1.0 covers seven legs with new entries; v1.1 covers eight. That is only one more
covered leg despite twelve versus eight events, and it replaces some final recoveries with
earlier failed rebounds within the same broad decline.

| Later recovery | V1.0 new event | V1.1 state |
| --- | --- | --- |
| February 2016 low | Feb 18 | January entry already consumed; raw recovery passes again Feb 16-18. |
| December 2018 low | Jan 7, 2019 | November entry already consumed; raw recovery passes Dec 31 and Jan 7. |
| March 2022 low | Mar 15 | February entry already consumed; raw recovery passes Mar 14-15. |
| October 2022 final low | None | Oct 4 entry fails before Oct 12; raw recovery returns Oct 17-19, but episode is consumed. |
| April 2025 low | Apr 11 | March entry already consumed; raw recovery passes Apr 11, but cannot enter. |

These are diagnostic hindsight labels, not entry features or permission for unlimited retries.
One entry per stress episode avoids counting repeated confirmation as independent opportunities.
It also spends the entire episode on the first qualified bounce. A revised failure/recovery
cycle would need observable fresh damage, fresh release, a bounded attempt policy, and separate
episode/attempt identities. Study that only after making thesis failure economically coherent.

Missing OAS affects nine entry dates, but **only five** of those select credit among their two
recorded confirming families. Eight of twelve entries use credit in total. Missing exact credit
coverage is not the same as every entry depending on unobserved credit confirmation.

## 5. Protect-Extension: Four Different Sources Of Regression

The economic path matches v1.0's `extension_unwind`, but its confirmation, state identity,
entry deduplication, competing actions, and exits do not. Fourteen versus five is not a matched
experiment changing just one gate.

### Newly Identified Bug: Persistence Is Cleared After Every Quiet Day

In `update_setup`, an expired extension with an existing ID sets `renewal_ready=True` and
clears `hits` whenever the current score is below 0.60. It repeats the clearing even after
renewal is already allowed. This destroys interrupted qualifying observations within the
promised three-of-ten window.

A synthetic sequence reproduces the bug without market data or parameter changes:

```text
session 0:  0.80 -> initial episode arms
session 41: 0.00 -> old episode expired; renewal is allowed
session 42: 0.65 -> hits [42]
session 43: 0.00 -> hits []
session 44: 0.65 -> hits [44]
session 45: 0.00 -> hits []
session 46: 0.65 -> hits [46], still unarmed
```

Sessions 42/44/46 are three qualifying hits inside ten sessions. Before the first episode,
the same interrupted-hit pattern can arm; after expiry it cannot. This is an implementation
contract error, not an argument for a lower threshold.

**Real example:** April 5/8/12, 2019 have extension scores 0.740/0.677/0.663. April 9-11
clear the first two hits. April 22/23/26 repeat the same problem, with 0.635/0.722/0.644.
On May 7, v1.1 still retains an expired February 2017 identity and has no setup/divergence;
v1.0 has an April 26 armed setup and protects. The setup scores otherwise match on these dates.

Fixing persistence should clear the old episode's hits once when the renewal condition is
established, not clear every later non-hit. Preserve the separate prohibition on endlessly
re-arming uninterrupted elevated conditions. Test interrupted hits, boundary expiry, one strong
hit, and no automatic renewal. A corrected arm does not by itself prove a protect action or profit.

### Deliberate Fixed-Lifetime Losses Are Not The Same Bug

- **February 2023:** the December 2 episode reaches age 40 on February 1, despite a fresh
  0.755 score. February 3 reaches 0.765 after expiry but cannot re-arm without cooling first.
  Cooling arrives February 8; protection prerequisites arrive February 9 without a live setup.
- **April 2023:** the February 15 episode receives repeated April hits, but expires after
  April 14. April 17-18 remain elevated; cooling arrives April 19. April 25 has no live setup.

These obey the fixed age plus post-expiry reset rule. An identity/consumption clock is currently
also the evidence-validity clock: recent optimism can disappear from eligibility merely because
the episode began earlier. V1.0 repeatedly refreshed identities after interrupted hits; that had
its own double-counting problem. Study separating **evidence freshness** from **entry consumption**,
not indiscriminately restoring repeated old entries or increasing forty to an optimized number.

Across the sample, extension is armed on 732 v1.0 dates versus 495 v1.1 dates. The numerical
setup score differs on only two dates, July 1 and July 28, 2025. Lifecycle handling, not wholesale
changes to setup geometry, is the dominant place to investigate the coverage difference.

### What Happened To The Fourteen Old Event Dates

| V1.0 event dates | V1.1 diagnosis at those dates |
| --- | --- |
| 2016-04-05, 2016-04-07, 2019-11-19 | Price-damage gate fails. These old alerts were not valuable ordinary corrections. |
| 2019-05-07 | Setup/divergence absent; interrupted re-arming bug above. |
| 2019-12-03 | Retained as a new extension entry. |
| 2020-01-03, 2020-01-24 | Price damage fails; the account is already protected from Dec 3. No new entry is not absence of protection. |
| 2021-11-11 | All raw extension gates pass, but protection is already held under `protect-break` since Sep 30. |
| 2023-02-09, 2023-04-25 | Fixed-lifetime expiration above; setup and remembered divergence fail. |
| 2023-06-22 | Price damage fails; v1.1 enters on June 26 instead. |
| 2024-01-04 | Retained. |
| 2024-07-10 | Price-damage score is zero; an advance warning is lost. |
| 2025-08-04 | Price-damage gate fails after the bounce, but v1.1 already entered Aug 1. |

The November 2021 absorption is correct attribution, **not evidence that earlier protection was
better**: the held break window gains 10.90% in SPY. It also exits January 3, before much of the
2022 decline. A deduplicated warning can still belong to a poor exposure decision.

### The Fixed Variants Identify Another Important Change

| Core variant | Extension entry dates |
| --- | --- |
| R2-C / W-opportunity | 2020-01-24, 2021-11-22, 2024-07-10 |
| P-sequence | 2020-01-27, 2021-11-26 |
| P-decay / P-resolution | 2017-03-22, 2019-12-03, 2021-11-11, 2023-06-26, 2024-01-04, 2025-08-01 |
| P-break / combined | Same as preceding row except November 2021 is absorbed by held break protection. |

Sequencing explicitly trades advance warning for price damage; July 2024 disappears. Removing
the decayed-strength requirement then admits all four costly non-crash entries that remain in
the final model. It also changes the earlier protective holding timeline. This is more precise
than blaming the entire regression on monotone family scoring or on corrected deduplication.
These controls share the newly found persistence bug, so their interpretation needs a corrected
replay before drawing a final model-selection conclusion.

### What The Five Remaining Entries Actually Did

| Signal | Execution exit | Sessions | Held SPY / QQQ | SPY entry loss | Exit |
| --- | --- | ---: | --- | ---: | --- |
| 2017-03-22 | 2017-06-26 | 65 | +4.61% / +9.13% | -0.76% | Timeout |
| 2019-12-03 | 2020-03-10 | 65 | -7.94% / -0.44% | -11.30% | Timeout |
| 2023-06-26 | 2023-08-02 | 25 | +4.83% / +5.57% | 0.00% | Recovery |
| 2024-01-04 | 2024-03-05 | 40 | +9.14% / +11.22% | 0.00% | Recovery |
| 2025-08-01 | 2025-09-24 | 36 | +6.50% / +7.37% | 0.00% | Recovery |

Zero entry loss means no sampled closing loss from execution entry, not that the ETF never
traded below entry intraday. The four rising windows are real opportunity costs, not just bad
fixed-horizon labels. December 2019 eventually overlaps a shock; it is not clean validation of
ordinary correction detection. The old v1.0 protect mean also depends heavily on overlapping
2020 crash labels, as the earlier investigation already documented.

Exits deserve their own study. The 2017 and December 2019 entries include credit among causal
families, but OAS is unavailable throughout their holdings. The requirement for exact whole-family
repair cannot pass, so they hold to the cap. In January 2024, trend is unrepaired on only two
subsequent held dates, but volatility blocks on 27 and breadth on 14; the holding lasts forty
sessions. A correction can be over while one maximum-of-alternatives family keeps interrupting
the three-day repair streak. These counts overlap and are not sole-cause assignments.

## 6. Protect-Break: Entry Lag Plus A Lifecycle Mismatch

### Every Executed Protective Window

| Signal | Sessions | Held SPY | Exit |
| --- | ---: | ---: | --- |
| 2016-01-06 | 14 | -2.75% | Opposite action |
| 2016-05-19 | 5 | +2.25% | Recovery |
| 2016-06-28 | 65 | +5.81% | Timeout |
| 2016-11-01 | 14 | +4.68% | Recovery |
| 2017-08-21 | 30 | +4.26% | Recovery |
| 2018-02-09 | 65 | +3.18% | Timeout |
| 2018-10-12 | 15 | -1.13% | Opposite action |
| 2019-05-21 | 64 | +3.23% | Opposite action |
| 2020-09-23 | 29 | +6.11% | Opposite action |
| 2021-09-30 | 64 | +10.90% | Recovery |
| 2022-01-18 | 10 | -0.57% | Opposite action |
| 2022-04-25 | 6 | -2.05% | Opposite action |
| 2022-09-01 | 22 | -6.33% | Opposite action |
| 2022-12-29 | 25 | +7.42% | Recovery |
| 2023-08-17 | 65 | +4.33% | Timeout |
| 2024-04-17 | 6 | +0.87% | Opposite action |
| 2024-08-06 | 3 | +1.09% | Opposite action |
| 2025-01-14 | 25 | +3.36% | Recovery |
| 2025-02-26 | 17 | -4.31% | Opposite action |
| 2025-11-19 | 8 | +1.14% | Recovery |
| 2026-02-17 | 37 | -0.70% | Recovery |

Fourteen of 21 underlying held returns are positive; median return is +2.25%; mean holding is
28.0 sessions. Three early-2022/September-2022 entries do reduce exposure during further losses,
so the path is not uniformly backwards. But benign breaks and restoration delays cost more
than its fixed-horizon averages reveal. The existing fixed experiment adding P-break to
P-resolution reduces total net account return from +457.74% to +402.43%. This is the whole
stateful treatment, including changed overlaps and exits, not additive per-trade attribution.

### Lag Is Real, But Shortening Three Sessions Is Not A Diagnosis

The path requires both indexes below MA50 with negative 20d returns for three consecutive
sessions, plus current owned trend damage and another family. That describes an existing loss,
not necessarily an impending persistent decline. In a mean-reverting correction it can mature
near a low; in a continuing decline it can still be useful. January/April/September 2022 illustrate
the latter. An early-warning requirement would change this path's intended role.

Using a deliberately explicit hindsight diagnostic, compute `(signal_close - window_min) /
(window_max - window_min)` over twenty sessions on each side. Six of 21 signals are in the
bottom tenth of that price range; seven are above its midpoint. This does not reproduce an
assertion that essentially every break entry is near a trough. Range location is not the rank
percentile of observations, and neither is a live signal. Signal-close and next-open analyses
also use different dates and prices.

Do not fit a faster persistence parameter to those lows. Compare against an equally delayed,
price-only broken-trend control to ask whether non-price evidence adds information. Distinguish
negative trailing returns from new structural deterioration, and measure restoration delay
separately from entry selection.

### Protection Can Become Unavailable During The Continuing Decline

The current resolver allows an opposite unused washout action to end protection. It then marks
that washout opportunity consumed. If the rebound fails, the portfolio returns to neutral;
the old break episode also remains consumed until the required price repair creates a new cycle.

```text
break enters -> rebound authorizes washout -> washout fails -> neutral
              break still armed but consumed; washout also consumed
```

Examples: October-November 2018, January-February 2022, April-May 2022, and September-October
2022. At the December 24, 2018, June 16, 2022, and October 12, 2022 lows, the account is neutral,
the raw break predicate passes, and the break episode is consumed. These ordinary-decline
examples are enough; no need to demand prediction of a shock announcement.

There are **133** such neutral/raw-break/consumed dates, including 60 in 2022. This is not a claim
that protection would earn money on every one: August 13, 2024 has the same state but precedes a
good recovery. It demonstrates a state contract that cannot express continuing defensive need
after an intervening failed risk-addition attempt.

**Design question:** should a direct-break exposure state be governed by sustained risk conditions,
rather than permanently spent like a one-shot recovery opportunity? Alternatives to study include
an explicit restoration of an interrupted defensive thesis, or a fresh failure transition that
permits a new bounded protection attempt. Preserve event/attempt attribution and fixed caps;
do not silently renew a position on every raw signal. Compare these state treatments with entry
predicates unchanged so their effect is measurable.

The opposite error also matters: protection can persist well into a recovery. Missing credit
coverage blocks exact repair throughout the June 2016 and September 2020 holdings. For the
September 2021 holding, volatility remains unrepaired on 51 of 64 subsequent held dates even
though SPY gains 10.90%. Whole-family maxima allow a different alternative leaf to keep a
position alive after the original causal leaf has repaired. Explore persisted leaf attribution
plus an explicit new-deterioration veto, not silently treating missing inputs as healthy.

## 7. What To Do Next Without Fitting Historical Dates

| Priority | Change or experiment | First-principles reason | Required guardrail |
| --- | --- | --- | --- |
| 1 | Fix interrupted extension persistence after expiry. | Three-of-ten must mean the same thing before and after a prior episode. | Synthetic contract tests; no threshold change; rerun every fixed variant. |
| 2 | Separate relative-volatility normalization from absolute renewed stress, and residual damage from a new price turn. | A recovery should not fail solely because older losses remain in a trailing window and two fear indexes cool at different speeds. | Preserve genuine divergence/recovery quadrants; audit all exits, including harmful rebounds. |
| 3 | Specify entry/failure consistency and the meaning of consumed episodes after a failed opposite thesis. | One research episode can contain several economically distinct decisions without each day being a new independent event. | No unlimited retries or cap resets; distinguish episode, attempt, and held position. |
| 4 | Give orderly pullback recovery a distinct confirmation/opportunity contract. | Continuation opportunity differs from buying the first half of a panic rebound. | Do not tune halfway/confirmation cutoffs to the near-miss dates; retain failed pullbacks in evaluation. |
| 5 | Separate evidence freshness from fixed extension identity and evaluate protection repair at causal-leaf level. | Fresh setup evidence and repaired original causes should not be lost behind unrelated state bookkeeping or a new maximum leaf. | Keep missing coverage explicit; account for new genuine damage; do not remove conservative behavior merely because it lost upside. |
| 6 | Reassess direct-break entry evidence against simple price controls. | A slow damage detector must add useful risk information beyond already-observed losses. | Equal timing/costs/exposure controls, all events, and no demand to predict shock tops. |

Do not implement all six as one unmeasurable bundle. Correct the demonstrable arming bug first,
establish the new baseline, and freeze each subsequent mechanism before its replay. This study
does not recommend selecting the highest-return historical variant or reverting correctness fixes.

Evaluate each change using both fixed-horizon labels and actual next-open held exposure, with
SPY and QQQ, transaction/financing costs, neutral and exposure-matched accounts, and chronological
cohorts. Show the full added/removed entry inventory, exit reasons, days protected after price
recovery, and consumed-opportunity exclusions. Bootstrap or group by broad market episode when
estimating uncertainty; daily overlapping labels are not thousands of independent experiments.

Keep the 2018/2022 ordinary declines and failed recoveries visible. Use March 2020 as a recovery
stress case and concentration check, not an optimization target for protection. Previously
examined history is development data, not a new holdout simply because another round has begun.

## 8. Reconciliation With The Parallel R5 Review

The parallel [Claude review](../v1.2/r1-backtest-claude.md) correctly emphasizes the confirm funnel,
short washout holdings, lost extension warnings, and poor break economics. A few details should
not propagate into the next design:

- March 25, 2020 is the v1.1 signal; March 26 is execution, **after** the March 23 low, not before it.
- The August 2019 confirm near-miss is unknown due to OAS coverage and follows an already-closed
  washout holding. Missing exact credit on nine entries is not nine credit-dependent entries.
- Captured washout returns are highly concentrated; non-COVID fixed-horizon means do not vanish.
- The unexplained May 2019 extension gap is now traced to a persistence bug; the February/April
  2023 gaps are fixed-lifetime behavior. They should not be repaired by the same change.
- Correctly absorbing November 2021 extension evidence does not make the prior break entry good.
- Zero closing entry loss is not zero intraday loss. A positive 60d return is not sixty consecutive
  positive/established sessions. Neither distinction is cosmetic when defining a new model.
- The local-trough statistic needs a shared date/price/rank definition before using it to justify
  faster break entry. The unfavorable account evidence does not depend on that statistic.

## Reproduction References

Key implementation points at the audited commit:

- [regime_lifecycle.py](../../src/marketlab/regime_lifecycle.py): `owned_evidence`, `setup_readings`,
  `update_setup`, `price_opportunity`, and `transition`.
- [regime.py](../../src/marketlab/regime.py): `_vvix_vs_vix_feature`, `_action_event_dates`, and
  the forward-label helpers. The first defines the signed relative-volatility issue above.
- [regime_exposure.py](../../src/marketlab/regime_exposure.py): next-open account and holding windows.
- [regime_research.py](../../src/marketlab/regime_research.py): fixed variants with independent state.
- [Implementation results](implementation-results.md): corrected R4 comparison and account assumptions.

The audit loads exact per-day versions and recomputes labels as `P[t+h]/P[t]-1` and
`min(0, min(P[t+1:t+h+1])/P[t]-1)`. Its 5% inventory uses the algorithm and bounded coverage
window in section 4 of the earlier Codex investigation, retaining pre-2016 prices and counting
only confirmed legs in the shared report window. Gate counts come from saved booleans/unknowns,
not newly recomputed eligibility. Counts of repair blockers overlap. No altered-rule economic
backtest or parameter sweep was performed in this round.
