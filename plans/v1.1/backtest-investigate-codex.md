# V1.0 Backtest Investigation

**Author:** Codex
**Date:** September 20, 2026
**Status:** research before implementation; no model, observations, snapshots, or versions changed.

## 1. Main Conclusions

1. **Eight is the number of redeploy events, not all events or all market corrections.** The
   report contains eight redeploy and fourteen protect events across 2,617 sessions. Both are
   sparse; their effective independent sample sizes are smaller still.
2. **Redeploy has a promising short-horizon result, not an established general exposure edge.**
   Its SPY 20-session mean is +5.06% versus +1.27% for all days. At 65 sessions the difference
   narrows, adverse excursions worsen, and two entries into the 2021-2022 transition lose badly.
   The current posture simulation often exits much earlier than those report horizons.
3. **There are genuine missed recoveries, but not every rejected rebound was a mistake.**
   October 2022, November 2023, and April 2026 illustrate different problems: a setup never
   arms, opportunity disappears numerically before confirmation, and confirmation is diluted
   just enough to fail a compound threshold. November 2018 is an important counterexample:
   a superficially similar near-pass correctly stayed out before another decline.
4. **Protect does not currently implement both proposed economic cases.** All 27 protect days
   use `extension_unwind`. The fifteen `regime_break_warning` days remain `no_change`.
   A model that requires an old extension and both indexes above their 200-day averages cannot
   also be expected to protect throughout an established declining market.
5. **Protect's apparent long-horizon success is concentrated, and several entries are plainly
   costly in hindsight.** Two 2020 entries share the same subsequent crash. Excluding 2020
   signal dates, the mean 40-session SPY return after protect is +3.73%, versus +2.43% for
   the corresponding all-days baseline. January 2024 and August 2025 expose concrete mechanisms,
   not just disappointing averages.
6. **The next additional scale-up hypothesis should be an orderly pullback recovery, not a
   weaker definition of panic.** Separately, returning from protected exposure to the normal
   core should not require a major washout. A later trend-continuation path deserves its own
   hypothesis and controls; none of these paths has established alpha yet.

The current v1.1 correctness work remains necessary. It is **not sufficient evidence** that
v1.1 will fix these coverage and economic-design problems.

## 2. Data And Reproduction Boundary

### What Was Compared

- Export: [regime-v1.0.csv](../../workbooks/regime-v1.0.csv), January 4, 2016 through June 1,
  2026, 2,617 rows.
- Report: [outcomes-action-v1.0.txt](../../workbooks/outcomes-action-v1.0.txt).
- Canonical daily decisions: `data/snapshots/regime/market/<date>/eod/v1.0/regime.json`.
- Underlying market-signal artifacts:
  `data/snapshots/market/signals/<date>/eod/v1.0/market-signals.jsonl`.
- Outcome prices: canonical SPY/QQQ daily observations under `data/observations/prices/daily`.
  SPY/QQQ currently cover June 30, 2014 through September 18, 2026. Later prices are outcome
  labels only, never inputs to an earlier decision.

I loaded the explicitly selected v1.0 snapshots, used the production `_action_event_dates`
grouping, and independently recalculated SPY forward returns and adverse excursions from
`DailyPriceObservation.return_close`. The results reproduce the report at its displayed
precision. They are **signal-close forward labels**, not executable portfolio returns.

The export matches canonical snapshots in the audited action state/path, stretch/washout
pressure, extension/washout setup, deterioration/stabilization, protect/redeploy strength, and
armed booleans. However, exported memory dates are not a reliable substitute for saved state:

| Exported field | Different from canonical snapshot | Of these, while canonical memory is armed |
| --- | ---: | ---: |
| `washout_armed_since` | 2,139 rows | 24 rows |
| `extension_armed_since` | 1,757 rows | 0 rows |

Most differences are historical dates retained after disarming versus cleared snapshot fields.
The 24 active washout differences are more consequential: full-export reconstruction and bounded
snapshot reconstruction disagree on identity. Use saved decisions and episode fields for this
audit, not a new event grouping inferred from the CSV. This supports the already proposed single
lifecycle implementation; it does not establish that all eight recorded events are independent.

### Coverage Limits

Direct S&P 500 participation observations (`INDEX_S5FI` and `INDEX_S5TH`) have only seventeen
local rows, August 26 through September 18, 2026. Neither direct breadth feature exists in this
report's sample. Credit-spread raw values occur in 682 snapshots, first September 12, 2023;
only two of eight redeploy events have that input. Most historical breadth/credit evidence is
therefore RSP/SPY, IWM/SPY, and HYG/TLT, not direct participation and credit spreads.

FRED's OAS notes explicitly limit downloads to three years starting April 2026; requesting an
earlier start is not a solution. FRED backfills here are current-vintage local history, meaning
today's available historical series, not necessarily the values originally published on each
signal date. These are limits on historical validation, not evidence that missing credit was
healthy. [FRED series notes](https://fred.stlouisfed.org/series/BAMLH0A0HYM2).

### Measurement Definitions

For adjusted close `P[t]` and horizon `h` trading sessions:

```text
forward_return = P[t+h] / P[t] - 1
entry_MAE = min(0, min(P[t+1], ..., P[t+h]) / P[t] - 1)
```

`entry_MAE` is the worst closing loss relative to entry. The report calls this `spy_dd`; it is
not a running-peak drawdown and excludes intraday lows. All percentages below use these
definitions unless explicitly described as a peak-to-trough decline or held-span index move.

## 3. Are The Events Too Rare, And Are Their Returns Good?

### Signal-Level Results

| Cohort | Samples | SPY 20d | SPY 40d | SPY 65d | MAE 20d | MAE 65d |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| All days | 2,617 | +1.27% | +2.54% | +4.07% | -2.45% | -4.44% |
| Redeploy events | 8 | +5.06% | +5.35% | +6.34% | -1.87% | -4.61% |
| Redeploy, excluding 2020 entries | 7 | +4.59% | +4.24% | +4.80% | -1.31% | -4.45% |
| All days, excluding 2020 entries | 2,364 | +1.22% | +2.43% | +3.68% | -2.24% | -4.10% |
| Redeploy, 2021 onward | 4 | +3.82% | +2.28% | +1.42% | -1.63% | -7.12% |
| All days, 2021 onward | 1,358 | +1.19% | +2.35% | +3.81% | -2.58% | -4.55% |
| Protect events | 14 | +0.55% | +0.44% | +0.22% | -1.85% | -7.42% |
| Protect, excluding 2020 entries | 12 | +0.76% | +3.73% | +2.74% | -1.96% | -3.47% |

Lower subsequent returns are favorable to protection, but neither a negative return nor a large
future drawdown proves the actual protection was held at the right time. Similarly, a positive
redeploy forward return does not mean its held exposure earned that return.

Redeploy's 20-day median is +4.85%; all eight returns are positive, but December 2021 is only
+0.014%, before costs. At 65 days only six of eight are positive. QQQ tells the same broad story:
redeploy averages +5.1%/+5.8%/+7.1% versus all-days +1.7%/+3.4%/+5.5%, while 65-day entry MAE is
worse (-6.4% versus -5.5%). This is not simply a SPY reporting artifact.

Eight observations are too few for a robust superiority claim. The all-days rows overlap
heavily, so 2,617 is not an independent comparison sample either. Excluding 2020 is a
concentration check, not an event-causality classifier or a substitute for uncertainty estimates.

### All Eight Redeploy Entries

| Entry | SPY 20d | SPY 40d | SPY 65d | MAE 20d | Interpretation |
| --- | ---: | ---: | ---: | ---: | --- |
| 2016-02-18 | +6.53% | +8.73% | +7.53% | -0.05% | Useful recovery entry. |
| 2019-01-07 | +7.36% | +9.02% | +13.83% | 0.00% | Useful recovery, after rejecting earlier rebounds. |
| 2019-08-21 | +2.95% | +2.81% | +6.58% | -2.60% | Useful forward label; current posture exits after three sessions at a loss. |
| 2020-03-26 | +8.33% | +13.11% | +17.07% | -5.76% | Strong rebound with substantial early adverse movement. |
| 2021-12-08 | +0.01% | -4.10% | -10.87% | -2.76% | Brief relief, not durable recovery. |
| 2022-03-15 | +3.16% | -7.56% | -13.70% | 0.00% | Tradable short rebound, poor longer-horizon recovery label. |
| 2024-08-12 | +2.91% | +7.81% | +12.28% | 0.00% | Useful recovery entry. |
| 2025-04-11 | +9.19% | +12.95% | +17.97% | -3.76% | Useful entry despite a subsequent retest. |

The March 2022 event is not unambiguously an incorrect short-horizon action: the existing
redeploying span ends March 31 with SPY up 6.31% from entry. Conversely, the August 2019 span
ends August 26 with SPY down 1.52%, despite positive 20/40/65-day labels. These are close-to-close
index moves over reconstructed posture spans, **not** next-open, cost-adjusted portfolio P&L.
They demonstrate why fixing held-exposure measurement is essential before optimizing entries.

### Where The Frequency Goes

The sequential redeploy gate audit over all 2,617 canonical snapshots is:

| Cumulative requirement | Remaining days |
| --- | ---: |
| Washout memory armed | 458 |
| Also current broad washout at least 0.35 | 276 |
| Also remembered setup release at least 0.05 | 179 |
| Also stabilization aggregate at least 0.75 | 37 |
| Also at least two stabilization families at 0.35 | 34 |
| Also strength at least 0.55 | 29 |
| Group those action days using saved setup identities | 8 events |

The 29 final candidates match the 29 recorded redeploy days; the funding veto removes none of
these candidates in this saved sample. That does not validate its missing-data behavior.
This is an ordered attrition table, not a unique causal allocation: multiple gates can fail
on the same date, and changing their order changes their marginal counts.

The strength gate contains another opportunity requirement:

```text
redeploy_strength = sqrt(current_broad_washout * stabilization)
strength >= 0.55 implies current_broad_washout * stabilization >= 0.3025
```

At stabilization 0.75, washout must actually be at least 0.4033, not merely 0.35. At washout
0.35, stabilization must reach 0.8643. These conditions intentionally select a narrow overlap
between continuing stress and recovery. Memory alone does not remove that same-day constraint.

Rare actions are acceptable for a tactical sleeve around a permanently invested core. They are
not enough if the intended product is a general opportunity engine. More events should result
from a distinct economic opportunity, not from a target event count or a lower cutoff.

## 4. Turning-Point Inventory Independent Of Model Signals

I used canonical adjusted SPY closes to identify local price legs, rather than selecting
bottoms where the model happened to work:

1. Start from the first local price observation, retaining pre-2016 history.
2. Track the running peak until a closing decline reaches 5%.
3. Track the subsequent low until a closing rebound from that low reaches 5%.
4. Record peak, trough, first 5% loss, and rebound-confirmation date. Resume peak tracking from
   the confirmation close. Keep troughs inside the export sample whose confirmation occurs by
   June 1, 2026; unfinished legs are not counted as confirmed recoveries.

This produces **35 local decline/recovery legs**, not 35 independent bear markets. For example,
March 2020 contains several large failed rebounds; October 2022 is the final leg inside a much
larger decline. The broad September-December 2018 decline was -19.35%, January-October 2022
-24.50%, and July-October 2023 -9.97%.

Peaks and troughs are hindsight research labels, **never entry prices or live features**.
The confirmation date is observable at its EOD, but trading it still requires next-session
timing. Forward labels from that close are a diagnostic comparator, not a strategy backtest.

For coverage, assign a new redeploy event to the interval from each trough through twenty
subsequent sessions, capped before the next trough. This prevents the March 26, 2020 entry
from being counted as catching several earlier failed bottoms. Seven of the 35 legs have a
new event; two more have continuing redeploy actions from an already counted episode. The eighth
new event, December 8, 2021, follows a pullback too small for this 5% inventory.

Using 3% and 8% directional-change definitions instead gives 61 and 13 legs, with eight and six
assigned new redeploy events. This is labeling sensitivity, not threshold selection. No exact
bottom-capture percentage should become the model objective.

### Simple Recovery Comparator

| First 5% rebound confirmation after... | Legs | SPY 20d | SPY 40d | SPY 65d | MAE 20d |
| --- | ---: | ---: | ---: | ---: | ---: |
| Any inventory decline | 35 | +1.19% | +4.47% | +6.34% | -4.83% |
| A decline of at least 8% within that inventory | 20 | +0.20% | +4.41% | +6.33% | -6.99% |
| A decline between 5% and 8% | 15 | +2.52% | +4.54% | +6.36% | -1.95% |

These cohorts overlap in calendar time and cluster within crises. The last row is a reason to
study ordinary recoveries, not proof of a profitable rule. It includes failed rebounds too.
The twenty larger legs here are selected from the **5% inventory**; they are not the thirteen
legs obtained by changing the whole segmentation algorithm to 8%.

Notably, the unfiltered rebound comparator has almost the same 65-day mean as redeploy, but
much worse early adverse movement. v1.0 may be doing more useful short-term filtering than its
long-term mean alone suggests. That benefit must survive a realistic holding/execution test.

## 5. Missed Redeploy Opportunities And Why

In this section `T` is trend washout, `V` volatility washout, `X` the larger of breadth/credit
washout, `W` broad washout, and `S` stabilization. Values come from saved pressure/action modules.
The snapshot links are the canonical evidence, not reconstructed workbook state.

### A. No Panic Setup Despite A Real Equity Decline

| Date / case | Saved evidence | What blocks the path |
| --- | --- | --- |
| 2019-06-03 | T 0.769, V 0.466, X 0.988 | Volatility leg below 0.50. May-June has only one setup observation above 0.60, insufficient to arm. |
| 2020-10-30 | T 0.669, V 0.648, X 0.000 | Transmission gate fails despite a 7.3% local correction and both price/volatility legs passing. |
| 2021-10-04 | T 0.987, V 0.521, X 0.067 | Transmission fails during a 5.1% pullback; both indexes remain above their 200-day averages. |
| 2022-10-12 | T 0.839, V 0.577, X 0.006 | Transmission fails at the final low of the 24.5% broad decline. September-October contains just one setup hit above 0.60. |
| 2023-03-13 | T 0.244, V 0.617, X 0.956 | Severe relative participation/credit weakness, but index trend washout fails. No qualifying setup across February-March. |
| 2024-04-19 | T 0.856, V 0.576, X 0.101 | Transmission fails during a 5.4% pullback; SPY/QQQ remain 6.82%/4.98% above their 200-day averages. |

Examples: [October 2022 snapshot](../../data/snapshots/regime/market/2022-10-12/eod/v1.0/regime.json),
[April 2024 snapshot](../../data/snapshots/regime/market/2024-04-19/eod/v1.0/regime.json).

The relative proxies can tell a different economic story from absolute damage. On October 12,
2022, SPY/QQQ 20-day returns were -9.27%/-11.11%, yet RSP/SPY was +0.30%, IWM/SPY +1.16%, and
HYG/TLT +3.56%. Relative outperformance does not mean constituents or credit are undamaged.

HYG owns high-yield corporate debt and TLT long-duration Treasuries. Their relative return also
reflects different interest-rate exposures; it is not a pure credit-spread measurement. This
is a structural limitation, not proof that all of a particular day's move came from rates.
[HYG fund description](https://www.ishares.com/us/products/239565/isharesiboxx-high-yield-corporate-bond-etf),
[TLT fund description](https://www.ishares.com/us/products/239454/ishares-20-year-treasury-bond-etf).

**Implication:** test the already proposed transmission alternatives. Also distinguish a
market-wide panic from an ordinary equity pullback. Do not force both through the same panic
setup, and do not assume removing transmission alone resolves every later gate.

### B. The Recovery Removes Its Own Opportunity Qualification

On [November 2, 2023](../../data/snapshots/regime/market/2023-11-02/eod/v1.0/regime.json):

- Washout memory is armed; the qualifying October 23/27 setups were 0.654/0.671.
- Stabilization is 0.971, with adequate confirming families and setup release.
- Broad washout has already fallen to 0.200, below 0.35; strength is only 0.440.
- No redeploy action occurs. The next day's observable 5% rebound confirmation is followed
  by SPY returns of +5.1%/+8.3%/+15.1% over 20/40/65 sessions.

This is not missing memory. The model remembers the stress but requires that the recovery
not have removed too much of it. The same mechanism blocks February 15, 2018: armed memory,
S 0.843, W 0.226. That recovery's subsequent returns are much less attractive, so broadening
eligibility would have costs as well as benefits.

**Proposal:** distinguish **entry opportunity still available** from **fear still elevated**.
Recent unused stress plus release and confirmation can remain an opportunity after fear falls.
A bounded anti-chasing condition could refer to price recovery from a causally tracked episode
low, not to re-elevating a fear score. Its economic definition must be frozen before a replay;
do not choose a price-distance cutoff to capture November 2023.

The existing v1.1 proposal preserves both W >= 0.35 and `sqrt(W*S) >= 0.55`. Its transmission
experiment will therefore leave this issue partly untouched. Test this as a **separate later
ablation**, after correctness repairs, not simultaneously with the transmission experiment.

### C. A Near Miss Does Not Justify Lowering The Threshold

On [April 7, 2026](../../data/snapshots/regime/market/2026-04-07/eod/v1.0/regime.json), memory,
current W 0.3836, release, S 0.7868, and family-count gates pass. Strength is **0.54936** versus
the required 0.55. The next day's rebound confirmation precedes strong forward returns.

Do **not** set the gate to 0.549. There is a more general scoring issue: saved family
stabilization is trend 1.000, volatility 0.772, credit 0.588. The volatility and credit families
each contain an owned raw reading of 1.000 diluted by other readings. The proposed owned
max-per-family/second-highest design addresses that problem independently of this outcome.
Whether this exact entry survives the complete repaired lifecycle and coverage rules needs replay.

The same old strength gate rejected November 5, 2018 at 0.5453. After the November 7 rebound
confirmation, SPY lost 6.2%/8.1% over 20/40 days. Both dates belong in any regression panel.

### D. Some Rejections Were Useful

- November 2018 rebounds: insufficient stabilization/strength avoided the next selloff.
- February 2, 2022: S 1.000 and W 0.513, but setup only 0.592 and unarmed. The February 1
  rebound-confirmation label is -3.3% at 20 days and -8.4% at 65 days.
- May 2022 rebound: no armed setup; May 27 confirmation is followed by -7.9% at 20 days.
- Early March 2020 rebounds: continuing peak stress and/or weak confirmation blocked entry
  until March 26. These are useful bottom/recovery stress tests, not an expectation that
  the system should have predicted the initial shock.

"We missed the eventual low" must not turn into "every intervening rebound should fire."

## 6. Protect: Missing Coverage And Incorrect Warnings

### Only One Actionable Mechanism Exists

`_protect_gate_result` requires armed extension, both indexes above MA200, sufficient decayed
extension times deterioration, volatility confirmation, internal divergence, and either price
rollover or two divergence families. An armed washout subsequently blocks late protection.

`regime_break_warning` deliberately returns no protect path. It is not a second protection
engine hiding inside the aggregate score. Also, displayed protect strength is the maximum of
extension and fragility-based strengths, so a large number need not imply an actionable path.

### Ordinary Declines Expose Structural Gaps

| Decline | Snapshot diagnosis | Interpretation |
| --- | --- | --- |
| January-February 2018 | On January 26, trend stretch is 0.996 but volatility stretch is 0.000; extension is unarmed. The prior forty-session window has only two >=0.60 setup hits, not three. | Strong price extension does not guarantee simultaneous percentile-defined complacency. |
| September-December 2018 | No extension setup in the forty-session window ending September 20. On October 5, all tested protect prerequisites except arming/its strength pass. On October 10, deterioration is strong, divergence is zero, and washout is already armed. | There is neither a fresh optimism setup nor a separate direct-break action. |
| January-October 2022 | Extension memory expires by January 5. Falling 20-day momentum disables divergence; QQQ then crosses below MA200 by January 20. There are no protect events during 2022. | An established declining regime falls outside the only executable protect path. |
| July-October 2023 | Extension is armed initially, but its effective strength decays from 0.336 on August 2 to 0.158 on August 15. Internal divergence fails, becoming zero as price momentum turns negative. | Delayed deterioration is not captured merely by retaining a boolean armed flag. |

These are the main protect research examples; no need to design around predicting COVID,
tariff announcements, or war. No causal news labels were inferred from price moves.

The January 2018 example also cautions against treating rolling percentiles as absolute risk:
VIX is 11.08 but at its 59.3rd trailing percentile; VVIX is at the 83.5th percentile. All five
volatility stretch contributions are zero even though index extension is exceptional.
That is valid percentile arithmetic, but a narrow definition of an optimism setup.
[January 26 snapshot](../../data/snapshots/regime/market/2018-01-26/eod/v1.0/regime.json).

### False Or Poorly Timed Protection

| Entry | SPY 20d / 40d | MAE 40d | Diagnosis |
| --- | --- | ---: | --- |
| 2016-04-05 and 04-07 | +1.0%/+3.0%; +0.5%/+3.1% | -0.12%; 0.00% | Two reported identities inside one continuously protected span. Event count overstates independent evidence. |
| 2023-04-25 | +2.0%/+7.9% | -0.42% | Short-term trend/volatility deterioration and two divergence gates pass during a continuing recovery. Already inside the February protected span. |
| 2024-01-04 | +5.8%/+9.6% | 0.00% | A brief multi-family pullback is interpreted as actionable deterioration; the held state then persists during a strong advance. |
| 2025-08-04 | +1.4%/+5.8% | -0.51% | Price-conditioned divergence turns protection on after the rebound, not on the preceding down day. |

There are useful ordinary successes too: May 7, 2019 precedes a 4.64% entry loss, February 9,
2023 a 5.34% loss, and July 10, 2024 a 7.83% loss within forty sessions. However, ten of the
twelve non-2020 protect entries never reach a 5% closing loss from entry within forty sessions.
That diagnostic threshold is not a demand to catch exactly 5%, nor does it make May 2019 useless.

The two 2020 protect events have 40-day SPY returns of -6.88% and -31.79%. They share one crash
and one continuous protected span. Do not count them as two independent validations of top detection.

### A Concrete Inverted Timing Gate

Compare [August 1](../../data/snapshots/regime/market/2025-08-01/eod/v1.0/regime.json) and
[August 4, 2025](../../data/snapshots/regime/market/2025-08-04/eod/v1.0/regime.json):

- August 1: SPY/QQQ 20-day returns are -0.58%/-0.42%. Trend deterioration is 0.678 and
  volatility 0.998, but both price-conditioned divergence readings are zero. No protect.
- August 4: SPY/QQQ 20-day returns recover to +1.69%/+2.19%. The condition turns on;
  breadth/credit divergence becomes 0.523/0.788. Protect fires although trend deterioration
  has fallen to 0.240; the two-divergence branch supplies confirmation instead.

This supports studying **remembered divergence followed by damage**, or a separate owned-damage
confirmation. It does not justify deleting every price-context gate. A benign leadership
rotation and genuine internal deterioration can look similar; removing the condition can add
many false positives. Moving this particular warning back to August 1 would not establish a
profitable warning either: the market rebounded. The example proves awkward timing semantics,
not that every earlier damage reading deserves protection.

The v1.1 binary-gate fix also matters here. Breadth's owned deterioration on August 4 is 0.274;
the old square-root pass-through boosts the divergence to 0.523. Passing it through unchanged
would fail the 0.35 breadth-divergence condition. This is a local causal explanation, not a
claim about the result of the whole unimplemented v1.1 replay.

### Exit Behavior Is A Separate Failure

January 4-April 1, 2024 remains protected while SPY rises **12.09%**. By March 28, protect
strength is only 0.255 and extension setup is zero, but fragility is 0.385 and prevents the
old recovery reset. Low credit spreads/loose financial conditions can sustain that fragility
measure. The withheld portfolio fraction, not the whole index move, determines opportunity cost.

At the other extreme, July 2024 protection ends July 31, before the August 5 trough. Good
entry labels do not establish good held protection. Keep the accepted causal-entry-family
recovery redesign and measure it directly.

## 7. Scale-Up Opportunities Beyond Panic Redeployment

### Distinguish Restoration From Additional Risk

**Restoring the normal core after protection** is the first priority. It is a posture exit,
not evidence that above-normal exposure is attractive. March 2023 is a useful example: the
market begins recovering, no washout episode arms, and the current protected span persists
until May. Requiring a panic redeploy to undo every defensive reduction would be structurally wrong.

**Taking above-normal exposure** needs an additional positive opportunity thesis. Low fear
alone, or the absence of deterioration, does not establish that thesis.

### Candidate Mechanisms

| Path | First-principles hypothesis | Setup and confirmation to investigate | Main failure mode |
| --- | --- | --- | --- |
| Washout recovery | Forced selling/hedging pressure can abate before damaged prices fully recover. | Recent stress episode, genuine release, independently owned stabilization, opportunity not already exhausted. | A bear-market rally mistaken for durable recovery; stress indicators normalize before price downside ends. |
| Orderly pullback recovery | A temporary correction inside an intact trend can reset positioning without a market-wide credit/panic event. | Pre-existing price trend; a local pullback/consolidation; renewed price strength with participation or other owned confirmation; no unresolved broad deterioration. | Trend appears intact just before it breaks; every ordinary dip becomes an entry. |
| Trend resumption after consolidation | Persistent demand can support continuation without a preceding washout. | Established trend, a bounded consolidation, renewed price/participation expansion; do not require historical fear. | Late-cycle breakout, leadership concentration, and paying up after most of the move. |

Study **orderly pullback recovery first**, with October 2021 and April 2024 as mechanism examples,
and December 2021/early 2022 as necessary failures. November 2023 and October 2022 are more
about repairing a damaged trend; do not silently relabel every missed bottom as an intact-trend dip.

For trend resumption, a distinct setup must prevent a signal on every rising day. No new
thresholds are selected here. A price breakout, rolling drawdown, or episode low must be defined
from data available on that date, never the retrospective turning-point labels above.

Momentum research provides a reason to investigate continuation independently of panic recovery:
Moskowitz, Ooi, and Pedersen document time-series momentum across futures markets. Its horizons
and instruments do not validate a new daily SPY entry rule.
[Original research](https://www.aqr.com/Insights/Research/Journal-Article/Time-Series-Momentum).

There is also a serious counterargument to simply buying more whenever fear is high:
Moreira and Muir find benefits from reducing exposure when volatility is high. Expected return
and risk both matter. A washout-recovery overlay must demonstrate why its confirmation and
holding rules improve the tradeoff, rather than assuming high fear guarantees a quick rebound.
[Volatility-managed portfolios](https://www.nber.org/papers/w22208).

First principles generate testable hypotheses; they do not guarantee market-beating returns.

## 8. Should The Two Protect Cases Be Separate Downstream?

**Yes as economic paths, entry evidence, and evaluation cohorts; not necessarily as different
top-level exposure commands.** The CLI can remain unchanged.

| Path | Intended job | What must remain separate |
| --- | --- | --- |
| Extension unwind | Reduce tactical risk as prior optimism loses support. | Remembered setup/divergence, confirmation delay, early-warning precision, recovery of entry evidence. |
| Trend/market break | Reduce exposure while an established deterioration continues, even without prior optimism. | Direct owned damage, persistence and recovery criteria, drawdown control, whipsaw/opportunity cost. |

Keep a common `scale_down_protect` exposure intent if that remains useful, but preserve the path
and causal evidence through snapshots, posture, exports, policy, and outcomes. Report both the
union and path-specific cohorts; one exposure transition must not become two independent trades
when both paths agree. Similarly, distinguish future washout recovery from pullback recovery
under a shared scale-up intent.

Do **not** simply activate the current `regime_break_warning`. Its fragility input mixes several
economic meanings, and its warning rule was not validated as an entry/exit system. A direct-break
path needs a separate specification. By design it will sometimes act after losses have begun
and sometimes sell a false breakdown; judge continued-loss avoidance against those costs, not
whether it predicted a peak.

This would expand the current v1.1 scope, which explicitly leaves regime-break warning-only.
Keep it as an explicit research decision, not an implementation detail or an assumed agreement.

## 9. Recommended Sequence Before Expanding The Model

1. **Repair the measurement and evidence baseline already agreed for v1.1.** Owned monotone
   family votes, correct binary gates, continuous release, canonical lifecycle, and real held
   exposure. Preserve the v1.0 artifacts. These repairs may change frequency in either direction.
2. **Run the declared transmission experiments with other economic gates fixed.** Attribute
   the difference between a weaker transmission score and removing transmission eligibility.
   Keep complete/reduced input profiles explicit; do not substitute missing history as calm.
3. **Then isolate the remaining-current-washout requirement.** Test whether recent stress,
   release, confirmation, and a predeclared opportunity-expiry rule explain entries better
   than demanding continued broad fear. Both the explicit W floor and its role in strength
   must be accounted for; deleting only one is not a clean experiment.
4. **Study orderly pullback recovery as a separate scale-up path.** Keep the panic path intact
   while measuring incremental entries, false recoveries, overlap, and added portfolio risk.
   Do not add trend-break protection and multiple new scale-up paths in the same attribution run.
5. **Investigate protect divergence sequencing, then a separate direct-break hypothesis.**
   First establish what the evidence/exit repairs fix. Compare remembered divergence with owned
   damage confirmation before adding another long-lived setup. Keep shock prediction out of
   the objective and retain the normal-decline cases above.

Items 1-2 are within the existing proposal. Items 3-5 are additional research recommendations,
not a request to silently rewrite its accepted baseline. Basic return/risk diagnostics and
path attribution should be accessible through existing outputs, not new daily workflow commands.

### Evaluation Contract

- Preserve event diagnostics, but add actual exposure-path performance against the always-held
  core and simple price-based controls. Use next-session execution, cash/financing assumptions,
  transaction costs, and explicit old/new exposure treatment over the overnight gap.
- Report coverage, confirmation delay, time exposed, turnover, opportunity cost, return tails,
  and peak-to-trough portfolio drawdown. Do not optimize only average forward return or event count.
- Show every new/removed action with failed/passed gates. Include bad recoveries and benign
  pullbacks, not just lows the new rule happens to catch. Evaluate false protect calls even
  when a distant unrelated crash makes their 65-day label favorable.
- Group nearby entries by common market episode for dependence/concentration diagnostics;
  do not make two January 2020 warnings two independent crash predictions. Distinguish a new
  entry from an already-held posture and from repeated daily confirmation.
- Use SPY and QQQ, multiple horizons, and chronological blocks. Dates already studied here
  are in-sample research, even if subsequently called a holdout. Freeze rules before genuinely
  new observations; use walk-forward and leave-one-period-out checks without retuning each split.
- Compare candidate paths on common dates and fixed input profiles. The three-year OAS window
  and absent historical direct breadth prevent claiming a fully validated ten-year full-input model.
- Treat the one-entry-per-setup-episode rule as a deliberate tradeoff. If it suppresses a second
  useful recovery after a failed first attempt, measure that explicitly before inventing retries.
- Keep percentile adaptation visible: the same raw VIX can receive different contextual ranks.
  That is useful context, but not a substitute for absolute price damage, financing stress,
  or a defined risk budget.

## Appendix A. Complete 5% Local Turning-Point Inventory

`New` means a saved new redeploy event in the bounded post-trough window defined in section 4.
`Held` means repeated redeploy actions from an earlier episode, not another independent entry.
`None` is absence of a redeploy action in that window, **not** a declaration that buying was wise.
Forward returns are from the observable confirmation close, not the trough.

| Peak | Trough | Decline | 5% rebound confirmed | Redeploy coverage | SPY +20d / +40d / +65d |
| --- | --- | ---: | --- | --- | --- |
| 2015-11-03 | 2016-02-11 | -12.8% | 2016-02-17 | New 02-18 | +5.4% / +8.4% / +6.4% |
| 2016-06-08 | 2016-06-27 | -5.5% | 2016-07-01 | None | +3.3% / +4.0% / +2.8% |
| 2018-01-26 | 2018-02-08 | -10.1% | 2018-02-15 | None | +0.8% / -1.7% / +0.5% |
| 2018-03-09 | 2018-04-02 | -7.3% | 2018-04-18 | None | +0.7% / +3.1% / +3.9% |
| 2018-09-20 | 2018-10-29 | -9.7% | 2018-11-07 | None | -6.2% / -8.1% / -1.6% |
| 2018-11-07 | 2018-11-23 | -6.3% | 2018-12-03 | None | -12.1% / -2.7% / +0.3% |
| 2018-12-03 | 2018-12-24 | -15.6% | 2018-12-26 | New 2019-01-07 | +8.0% / +13.5% / +16.6% |
| 2019-05-03 | 2019-06-03 | -6.6% | 2019-06-10 | None | +3.3% / +0.1% / +4.4% |
| 2019-07-26 | 2019-08-05 | -6.0% | 2019-09-06 | New 08-21 | -0.8% / +3.2% / +5.8% |
| 2020-02-19 | 2020-02-28 | -12.4% | 2020-03-04 | None | -20.9% / -6.6% / +2.7% |
| 2020-03-04 | 2020-03-09 | -12.3% | 2020-03-10 | None | -7.5% / -0.9% / +4.8% |
| 2020-03-10 | 2020-03-12 | -14.0% | 2020-03-13 | None | +3.0% / +9.2% / +16.9% |
| 2020-03-13 | 2020-03-16 | -10.9% | 2020-03-17 | None | +10.5% / +12.0% / +24.1% |
| 2020-03-17 | 2020-03-23 | -11.3% | 2020-03-24 | New 03-26 | +14.8% / +22.1% / +27.0% |
| 2020-03-30 | 2020-04-01 | -5.9% | 2020-04-06 | Held | +8.1% / +17.9% / +19.2% |
| 2020-06-08 | 2020-06-11 | -7.0% | 2020-07-06 | None | +3.7% / +10.2% / +6.1% |
| 2020-09-02 | 2020-09-23 | -9.4% | 2020-10-05 | None | -2.8% / +7.7% / +12.1% |
| 2020-10-12 | 2020-10-30 | -7.3% | 2020-11-04 | None | +6.7% / +7.8% / +14.1% |
| 2021-09-02 | 2021-10-04 | -5.1% | 2021-10-19 | None | +4.1% / +4.4% / -2.5% |
| 2022-01-03 | 2022-01-27 | -9.7% | 2022-02-01 | None | -3.3% / +1.6% / -8.4% |
| 2022-02-09 | 2022-03-08 | -9.0% | 2022-03-17 | New 03-15 | -0.4% / -8.6% / -14.3% |
| 2022-03-29 | 2022-05-19 | -15.6% | 2022-05-27 | None | -7.9% / -3.0% / -4.4% |
| 2022-06-02 | 2022-06-16 | -12.2% | 2022-06-24 | None | +1.4% / +6.0% / -6.5% |
| 2022-08-16 | 2022-09-06 | -9.1% | 2022-09-12 | None | -12.0% / -7.2% / -1.8% |
| 2022-09-12 | 2022-09-30 | -12.7% | 2022-10-04 | None | +1.7% / +7.9% / +3.1% |
| 2022-10-04 | 2022-10-12 | -5.7% | 2022-10-24 | None | +4.1% / +0.9% / +7.6% |
| 2022-11-30 | 2022-12-28 | -7.2% | 2023-01-11 | None | +2.9% / -2.4% / +5.1% |
| 2023-02-02 | 2023-03-13 | -7.5% | 2023-03-30 | None | +3.0% / +4.0% / +10.2% |
| 2023-07-31 | 2023-10-27 | -10.0% | 2023-11-03 | None | +5.1% / +8.3% / +15.1% |
| 2024-03-27 | 2024-04-19 | -5.4% | 2024-05-09 | None | +2.7% / +7.2% / +4.5% |
| 2024-07-16 | 2024-08-05 | -8.4% | 2024-08-14 | New 08-12 | +2.8% / +6.3% / +9.5% |
| 2025-02-19 | 2025-04-08 | -19.0% | 2025-04-09 | New 04-11 | +3.0% / +9.2% / +13.7% |
| 2025-04-09 | 2025-04-21 | -6.3% | 2025-04-24 | Held | +6.7% / +10.1% / +16.5% |
| 2025-10-29 | 2025-11-20 | -5.1% | 2025-12-05 | None | +1.2% / +0.4% / -2.6% |
| 2026-01-27 | 2026-03-30 | -8.9% | 2026-04-08 | None | +8.6% / +12.0% / +11.1% |

## Appendix B. Implementation References

All references describe the current v1.0 implementation, not a proposed future replay:

- [regime.py](../../src/marketlab/regime.py): `derive_regime_action_state`,
  `_structured_washout_setup_score`, `_structured_extension_setup_score`,
  `_protect_gate_result`, `_price_stable_or_rising_score`, `_gated_score`,
  `_action_module_average`, `_action_event_dates`, `derive_regime_postures`,
  `_forward_return`, and `_forward_max_drawdown`.
- [regime_export.py](../../src/marketlab/regime_export.py): exported memory reconstruction.
- [r2-proposal.md](r2-proposal.md) and [r2-discussion.md](r2-discussion.md): accepted repairs
  and clarifications; their experiments are not treated as already implemented here.

No parameter search or alternative production replay was performed for this investigation.
The turning-point inventory, gate audit, and numerical comparisons are descriptive research;
the additional paths and opportunity-expiry alternatives remain hypotheses to specify and test.
