# Break Protection: Transition, Not Accumulated Damage

Question: can break protection detect loss of support before a decline becomes a
washout candidate, instead of treating accumulated losses as fresh defensive information?
This follows the user's requested direction, not a parameter sweep around three-day persistence.

## Hypothesis Before Replay

The old setup can remain eligible deep into a decline. Its new-low retry rule can turn
a failed washout entry into protection near the eventual low. October 12 2022 is such a
retry, not a delayed initial three-day confirmation. Earlier arming alone cannot fix that.
This does not mean every deep decline should be bought: washout still needs release and
independent stabilization, and an existing protected holding keeps its unchanged exit rules.

Trial B3 changes the **entry opportunity** to a fresh loss of repaired support:

- Both indexes above MA50 for the existing three sessions establish repaired support.
- The first subsequent loss of MA50 by either index starts a five-session watch, including
  that session. Five is one trading week, not selected from a search over historical returns.
- Entry needs both indexes currently below MA50, the existing 5d price-damage strength
  >=0.35, and an existing non-price deterioration family >=0.35. Same-day confirmation is
  allowed; there is no reason to wait mechanically when distinct evidence already agrees.
- Negative 20d returns are not required: that is accumulated damage, not a support transition.
- Continued weakness cannot refresh the watch. After expiry or use, a new break opportunity
  needs repaired MA50 support again. Remove break's new-low retry, not washout's retry.
- An already-held protection is not forcibly ended at watch expiry. Exits, washout, extension,
  confirm, source data, and report definitions remain unchanged.

Bootstrap deliberately does not invent a repaired trend before the replay begins; initial
days under MA50 are not a fresh loss of observed support. Measure that boundary effect rather
than counting its dropped alert as proof of an improvement.

## Measurement

Reference is the completed entry review (`C2-sequential-pullback`, commit `a1efbf3` outputs),
not the older v1.1 model. Same 2,617 dates, 2016-01-04 through 2026-06-01, both core and
reduced profiles. Use canonical pressure/signals and observations, independent chronological
state, and production fixed-horizon event labels. Keep the user's 20/40/65d action table
primary; record all added/removed entries and cross-path effects. Check periods, pandemic
overlap, first entries versus retries, and remaining false alarms. No account optimization.
Repeatedly studied history is development evidence, not an out-of-sample test.

Attribution check, specified before running it: replay the previous model with only the
break retry call removed. Keep original arming and confirmation. This separates removing
late retries from the full transition definition; it is not a second production candidate.
`break_retry_ablation.py` uses the frozen pre-B3 code from commit `a1efbf3` and removes
that one call via Python's AST. Washout's retry call remains intact.

## Results

Return/drawdown triplets below are 20/40/65d. Core profile, same fixed-horizon event definition:

| Break variant | Events | SPY returns | QQQ returns | SPY drawdowns | QQQ drawdowns |
| --- | ---: | --- | --- | --- | --- |
| Previous v1.2 | 30 | +1.5/+3.2/+6.2% | +1.8/+4.1/+8.1% | -3.7/-5.1/-6.0% | -4.2/-5.9/-6.9% |
| Remove retries only | 22 | +0.7/+1.5/+4.8% | +1.0/+1.9/+6.7% | -3.7/-5.3/-6.3% | -4.1/-6.3/-7.3% |
| Support transition | 24 | +0.2/+0.9/+4.2% | +0.9/+1.7/+6.1% | -3.3/-4.7/-5.9% | -3.8/-5.4/-6.7% |
| All days | 2,617 | +1.3/+2.5/+4.1% | +1.7/+3.4/+5.5% | -2.5/-3.5/-4.4% | -3.1/-4.4/-5.5% |

The full B3 break dates/results agree exactly between core and reduced profiles. All other
actions retain their prior event dates/labels in each profile. Keeping their predicates
unchanged does not guarantee that generally; it is explicitly checked here.

### Did The Target Change?

- Eight old entries were retries. Removing only retries produces the middle row: it helps,
  but is not the full result. The support-transition definition also changes first entries.
- Break entries with washout already armed fall from 20/30 to 7/24. Mean continuous stress
  at entry falls from 0.656 to 0.561. This is descriptive evidence of earlier-phase entries,
  not a requirement that protect and washout can never share context.
- Warnings move earlier in February/October 2018, February 2020, April/August 2022, and
  February 2025. For example, April 25 -> April 11 2022 and September 1 -> August 30 2022.
- October 12 2022 is no longer a new protective entry. That decline already had an initial
  warning; a failed washout does not itself create a fresh support-loss opportunity.
- January 6 2016 disappears because the reference starts during damage, before an observed
  repair. Do not count this bootstrap effect as a successful false-alarm removal.

### Robustness And Costs

| Period | Old break SPY returns | B3 break SPY returns |
| --- | --- | --- |
| Before 2020 | +1.17/+3.08/+5.38% (9) | +2.01/+1.46/+4.25% (7) |
| After 2020 | +1.65/+2.65/+5.61% (18) | -0.15/-0.24/+3.02% (14) |
| 2022 | -0.05/-0.26/+1.49% (7) | -7.93/-5.10/-4.68% (2) |
| Labels not overlapping Feb 20-Apr 30 2020 | +1.98/+3.45/+6.31% (29) | +1.20/+1.36/+4.44% (23) |

Keep B3 as a more coherent entry definition with measured 20/40d improvement, not a solved
market-timing model. Its ex-pandemic 20d return is still close to all days, and 65d return
does not improve on all days. Before-2020 20d performance worsens. Two useful 2022 entries
are too few to establish reliable bear-market performance. No watch-window optimization was run.

Removing retries loses the useful November 23 2018 warning. Several benign pullbacks still
trigger protection, notably September/October 2020, September 2021, and April 2024.
September 20 and 29 2021 are separate repaired-support attempts within related market action,
not independent economic events. Lower forward returns also come with somewhat smaller
drawdowns than the old break sample; do not describe that as uniformly better risk capture.

The remaining problem is distinguishing an ordinary pullback from a durable support failure.
A future failed-recovery setup could address ongoing bear-market risk, but merely renewing
protection on new lows would undo the mechanism tested here. There is no automatic inversion
of old break signals into buys; redeploy still needs its own confirmation.

The complete event additions/removals and all horizons are in `entry-event-changes.csv`,
under `B3-support-transition` and `B3-retry-ablation`, with before/after gate and consumption
state. Full trial traces remain under `data/research/regime/v1.2/entries/`.
