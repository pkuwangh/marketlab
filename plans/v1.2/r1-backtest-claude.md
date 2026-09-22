# R5 Backtest Investigation: Action-By-Action Review Of workbooks/outcomes-action-v1.1.txt

**Author:** Claude (Sonnet 5), September 2026.
**Scope:** A fresh pass over each of the four v1.1 action types individually, following up on
`r4-code-review.md`'s implementation review with an economic/data investigation. Method continues
[backtest-investigate-claude.md](backtest-investigate-claude.md) and
[backtest-investigate-codex.md](backtest-investigate-codex.md)'s established approach — price-only
turning-point inventories, cross-referencing model state against real market action rather than
trusting aggregate headline numbers. Data sources: `workbooks/outcomes-action-v1.1.txt`,
`data/research/regime/v1.1/core/combined/daily.jsonl` (the full per-day gate/state trace),
`data/research/regime/v1.1/core/combined/holdings.json` (actual held-episode returns and exit
reasons), and canonical SPY/QQQ price observations.

**Headline numbers under review:**

```
action_state       count  20d      40d      65d
no_change (base)   2579   +1.3%    +2.5%    +4.1%
protect-break      21     +1.6%    +1.9%    +4.5%
protect-extension  5      +4.2%    +4.7%    +2.8%
redeploy-washout    12    +2.5%    +5.0%    +7.3%
redeploy-confirm    0     -        -        -
```

---

## 1. `redeploy-confirm`: Zero Events, Traced To A Precise Three-Stage Funnel Collapse

Already investigated in detail in this session; summarized here for completeness alongside the
other three actions.

Counting each of `redeploy-confirm`'s five required gates independently across all 2,617 days, then
intersecting step by step:

```
setup (pullback armed):                241 days
setup AND price_recovery:               25 days
+ opportunity (half-recovery rule):      1 day
+ confirmation (second family):          0 days
```

The single closest miss, **2019-08-30**: trend stabilization 0.815 (passes), but the best second
family is volatility at 0.652 — short of the 0.75 confirmation bar by about 0.10, with breadth/
credit/liquidity all at 0.0 that day. This date sits inside the already-successful Aug 2019
`redeploy-washout` episode (entered 2019-08-22), so even a clean pass here wouldn't have been a new
catch.

**Checked directly against the two cases this path was expected to help with:**

- **October 2022 — never in scope, confirmed structurally.** `established` (both indexes above
  MA50 *and* MA200 with positive 60-session returns beforehand — the precondition for a pullback to
  even arm) is `False` throughout all of 2022, including at the Oct 12 low. There was no intact
  uptrend to pull back *from*. Consistent with the r3 discussion's own clarification that Oct 2022
  is a `redeploy-washout`/transmission-gate target, not a `redeploy-confirm` target.
- **Aug-Oct 2023 correction — the real miss, and traceable to a specific cause.** A pullback
  episode genuinely armed on 2023-09-15 and tracked correctly through early October, but expired via
  the 20-session age cap around Oct 20 — days before the actual Oct 27 trough — and separately,
  SPY's distance to its 200-day MA went negative right around the real low (Oct 25: −0.68%, Oct 27:
  −2.36%), so the MA200-eligibility condition would have killed the episode within days regardless.
  By the time the real bottom and recovery arrived, no live pullback episode existed to confirm
  into, and re-arming requires rebuilding 60 sessions of sustained strength above both MAs first —
  a multi-month process, not something that can happen quickly after a real correction.

**Conclusion:** the path isn't malfunctioning — it's doing exactly what its frozen definition says.
But that definition (stays above MA200 the entire time, completes within 20 sessions) structurally
excludes corrections deep or slow enough to matter, which is precisely the class of case the
original investigation flagged as missing from washout coverage. There is a real, evidenced gap
between what `redeploy-washout` and `redeploy-confirm` each cover — not the overlapping safety net
the two-path design was implicitly expected to provide.

---

## 2. `redeploy-washout`: Headline Looks Fine, Underlying Data Tells A Different Story

12 events. Cross-referencing the entry dates against the price-only turning-point inventories from
the prior investigation rounds: most land near a genuine local low (2020-03-26 fires 3 sessions
before the actual COVID bottom; 2020-11-04, 2021-09-28, 2024-04-26, 2024-08-12 are all within ±5
sessions of a real trough). But several fire well **before** the eventual bottom: 2016-01-28 (10
sessions early), 2018-11-05 (13 sessions early), 2022-02-02 (14 sessions early), 2022-05-04 (11
sessions early), 2025-03-24 (11 sessions early) — and these early entries are exactly the ones that
go on to fail.

**The headline "+2.5%/+5.0%/+7.3%, beats baseline" result is almost entirely carried by one
episode.** 9 of the 12 episodes exit via `thesis_failed`, most within 1-8 sessions (median ~3), and
**7 of those 9 exits are negative** (ranging from −0.63% to −4.06%). Only 2 exit via
`holding_expired` at the full 20-session cap (both strongly positive: +7.57%, +4.25%), and the
actual held-return average (+0.90%, matching the outcomes file exactly) is dominated by the single
2020-03-26 COVID entry (+11.55%). **Excluding that one episode, the remaining 11 average −0.07% —
essentially flat to negative.** This is the same COVID-concentration pattern found repeatedly
throughout every prior round of this investigation, now reproduced in the redesigned v1.1 path.

Digging into *why* `thesis_failed` behaves this way: it's mostly triggering on positions that are
already underwater from an early entry, not protecting a peak that later reverses. Concrete example:
the 2022-05-04 entry has a 40-day fixed-horizon *label* of −10.8% (a real number, since May 2022 kept
falling), but the actual *held* return is only −3.02%, because `thesis_failed` closed the position
after 4 sessions — the exit rule worked as a stop, it just entered too early into a decline that
hadn't finished.

**Coverage caveat:** 9 of the 12 signal dates have `credit.exact=False` (missing OAS — expected,
since OAS only exists from Sept 2023), meaning credit's contribution to those 9 confirmations is a
lower-bound proxy from HYG/TLT alone, not the fully-designed evidence set. Not a new bug, but a real
caveat on how much weight "credit confirmed" should carry for most of this action's history.

**Assessment:** the aggregate numbers in the outcomes file are technically correct but materially
misleading on their own — the mean is a COVID-single-episode artifact sitting on top of a roughly
flat-to-negative base rate for the other 11 entries, several of which enter measurably too early.

---

## 3. `protect-extension`: The 14→5 Drop Is Three Different Mechanisms, Not One Regression

v1.0's 14 protect episodes and v1.1's 5 `protect-extension` events were compared date-by-date, with
every dropped v1.0 date traced through the v1.1 gate trace to find the specific reason. Three
distinct mechanisms explain the drop — conflating them would have been the wrong diagnosis:

1. **Genuine, intentional gate tightening (~5-6 of 14 episodes).** 2016-04-05/07/08, 2019-11-19,
   2020-01-03, 2021-11-22, and 2024-07-10 all pass every other gate but fail `damage`, which now
   strictly requires current trend deterioration ≥ 0.35 (`config.sequence=True`). The v1.0-era path
   accepted trend damage **or** two-or-more divergence families; the new sequenced version requires
   damage specifically. This is exactly the tradeoff `r3-proposal.md §6.3` described and explicitly
   authorized testing ("sacrifices some advance notice... compare timing, losses avoided, false
   alarms") — implemented as specified, the single largest contributor to the drop, and a declared
   experiment result, not a bug.
2. **Not actually losses — correctly absorbed into an already-held posture (~4 of 14 episodes).**
   2020-01-24/27/29/31 are part of the same continuous defensive posture entered on 2019-12-04 (held
   through 2020-03-10 via the 65-session cap) — v1.0 counted this as two separate episodes; v1.1
   correctly treats it as one continuous hold, not a miss. Similarly, 2021-11-11/22/26/29 all show
   `eligible_candidates=[]` because a `protect-break` posture was *already* holding since 2021-09-30
   — six weeks earlier, via the other new path. This is v1.1 catching the episode **earlier** than
   v1.0 did, not missing it.
3. **Genuinely unexplained, needs its own dedicated check (~3 of 14 episodes).** 2019-05-07,
   2023-02-09/10, and 2023-04-25/26 show `setup=False` — the extension episode never arms at all in
   v1.1, which is a more fundamental difference than gate-tightening (never-armed vs. armed-but-
   blocked). This was not traced to a specific cause in this pass; it needs a direct comparison of
   `setup_readings`/`update_setup`'s extension-arming construction against what v1.0's
   `_structured_extension_setup_score` computed on these exact dates.

**The 5 remaining events, checked against actual held returns (not fixed-horizon labels):**

| Episode | Held SPY return | Entry loss (max adverse move during hold) |
| --- | ---: | ---: |
| 2019-12-03 → 2020-03-10 | **−7.94%** | −11.3% |
| 2017-03-22 → 2017-06-26 | +4.6% | −0.8% |
| 2023-06-26 → 2023-08-02 | +4.8% | **0.0%** |
| 2024-01-04 → 2024-03-05 | +9.1% | **0.0%** |
| 2025-08-04 → 2025-09-24 | +6.5% | **0.0%** |

Only the Dec 2019 entry is a genuine catch (correctly held into the actual COVID crash onset). The
other four are real net-negative calls, not a labeling artifact — three show **exactly zero entry
loss**: SPY never once traded below the entry price during the entire holding window before the
model itself recognized recovery and exited. That's a clean false-alarm signature independent of how
it's measured. The positive fixed-horizon average in the outcomes file compounds this with a second
effect: the 20/40/65-day labels measure a rigid window from entry regardless of when the position
actually exited, so for the three `protection_recovered` entries (25-40 actual held sessions), the
65-day label credits/blames the model for 25-40 extra sessions of market movement after it had
already defensively exited.

**Assessment:** not a regression from an inflation bug being fixed (no evidence the suppressed v1.0
episodes were false positives) — it's the declared sequencing experiment doing real, intended work,
combined with correct deduplication of overlapping protection, plus one genuinely unresolved arming
question. But the *quality* of what's left in this small sample is concerning on its own terms: 1
good call against 3 clean false alarms and 1 unexplained gap in coverage.

---

## 4. `protect-break`: Not The Old Sign-Error Bug, But A Different, Real Lag Problem

Checked whether the redesign (direct price-trend damage, deliberately avoiding
`fragility_context_score` entirely) actually fixed the contrarian behavior found in the old
`regime_break_warning` (`r3-review-claude.md` Topic 3: 15/15 occurrences positive at 20-65 day
horizons, traced to a sign/blending error in fragility's credit and liquidity legs).

**The old bug is confirmed gone** — `protect-break`'s entry condition uses only direct price-trend
damage and an owned corroborating family, never `fragility_context_score`. But the symptom persists
in a different, precisely diagnosed form:

**Timing check is the real finding.** For each of the 21 entries, computed where the entry-day price
ranks within a ±20-session window around it (0.00 = local minimum, 1.00 = local maximum): **12 of
21 entries (57%) fire within the bottom 10% of their surrounding price range** — essentially at a
local trough (2020-09-23, 2018-02-09, and 2023-08-17 are exact local minima; 2024-08-06 is one
session off the Aug 2024 low). **Not one of the 21 entries fires in the top half of its window** (max
observed percentile: 0.51, the exact midpoint). The mechanism: `protect-break` requires 3
*consecutive* sessions of confirmed price damage before firing — a trailing, persistence-confirmed
trigger that mechanically tends to mature alongside the decline itself, so that by the time it fires,
a moderate correction is often already near its low.

**Confirmed not a concentration artifact.** The 21 entries spread across 11 different calendar
years (nothing like the old `regime_break`'s 6-episode, 2017-heavy clustering). Excluding any single
year barely moves the mean: all years +1.94% → excl. 2016 +1.81% → excl. 2022 +2.49% → excl. 2024
+2.04%. The positive skew is broad-based.

**Confirmed not a fixed-horizon labeling illusion.** Actual held-episode returns from
`holdings.json` (mean +1.94%, median +2.25%, 14/21 positive, mean holding period 28 sessions) track
the fixed-horizon figures closely — unlike some other v1.1 actions in this review, held and labeled
returns tell the same story here, not different ones.

**Also positive, for the record:** the per-date return distribution isn't wholesale wrong — 2022's
three entries (Jan/Apr/Sep) are correctly negative, and the exit-reason mix (10 opposite-action, 8
protection-recovered, 3 timeout) looks like a normal, non-degenerate distribution.

**Assessment:** this is a real, structural finding distinct from the old bug — requiring sustained
confirmed damage as the sole primary trigger makes the signal inherently lagging, and empirically
that lag correlates with proximity to the eventual local bottom rather than the top. It's not a data
artifact and it isn't explained away by held-vs-labeled return differences. Whether this is
acceptable (a defensive action that still reduces exposure into genuine declines, just later than
ideal) or disqualifying (a "protect" signal that's more often a coincident-or-lagging indicator than
a leading one) is a design judgment call, not something this investigation resolves — but the
evidence is now precise enough to make that call deliberately rather than by inspecting the aggregate
mean.

---

## Cross-Cutting Observations

- **Every action's headline aggregate number required checking against per-episode data to
  interpret correctly.** `redeploy-washout`'s "beats baseline" result is a single-episode artifact;
  `protect-extension`'s "worse than v1.0" result is three different mechanisms bundled into one
  number, one of which is a real improvement (mechanism 2) and one a declared tradeoff (mechanism 1);
  `protect-break`'s "still positive like the old bug" appearance has a confirmed-different, real
  cause. None of the four headline numbers in `outcomes-action-v1.1.txt` mean what they look like
  they mean without this level of decomposition.
- **`thesis_failed` and early entries are a recurring theme across both redeploy paths.**
  `redeploy-washout`'s early-entry-then-`thesis_failed` pattern (Section 2) and `redeploy-confirm`'s
  narrow, easily-exhausted opportunity window (Section 1) both point toward the same underlying
  tension: entering while conditions are still resolving costs more than it saves, and the current
  exit machinery mostly registers that after the fact rather than avoiding it at entry.
- **Coverage gaps (missing OAS) are load-bearing, not cosmetic, for `redeploy-washout` specifically**
  — 9 of 12 entries rely on a HYG/TLT-only lower-bound proxy for credit confirmation.

## Suggested Follow-Up

1. Resolve `protect-extension`'s unexplained 3-episode arming gap (2019-05, 2023-02, 2023-04-25) —
   compare `update_setup`'s extension-arming construction against v1.0's on those exact dates.
2. Given `protect-break`'s lag is now precisely characterized, decide explicitly whether a leading-
   indicator requirement (relaxing the 3-consecutive-session persistence, or adding a shorter-fuse
   alternative trigger) is worth testing as its own frozen variant, following the project's existing
   discipline of not tuning post-hoc — this would need to be specified and tested, not adopted from
   this investigation's findings directly.
3. `redeploy-washout`'s COVID-single-episode dependency and early-entry pattern reinforce (rather
   than resolve) the sample-size caution already on record from every prior round of this project's
   backtest investigation — worth stating plainly in any future summary that cites this action's
   aggregate numbers.

---

## 5. Follow-Up: Mechanism Diagnoses And Improvement Proposals

Four direct questions, each checked against data rather than answered from impression.

### Q1. `redeploy-confirm`: is it wrong in principle to expect a major run right off a pullback?

Not wrong to want to catch trend continuation — but the current implementation conflates "wants a
continuation" with "requires an immediate fast bounce right off the pullback low," and the funnel
data supports the intuition that this is the actual defect, not just a threshold-tuning problem.
Recall from Section 1: `setup AND price_recovery` co-occurs only 25 of 241 armed days, and of those
25, `opportunity` (the half-recovery-distance budget) survives in only 1. **The mechanism is that a
fast price bounce burns through the recovery-distance budget faster than multi-family confirmation
can build** — `price_recovery` only needs a single day's 5-session-return-positive plus trend
stabilization, both of which move quickly, while genuine second-family confirmation (breadth,
credit, volatility) is structurally slower to build. By the time it catches up, price has usually
already retraced past the halfway point.

This lines up with the momentum/technical-analysis literature the original investigation cited
(`backtest-investigate-codex.md §7`, Moskowitz/Ooi/Pedersen) — genuine trend-continuation entries
are traditionally made off *base breakouts* (a consolidation period followed by a break to new
strength), not immediate V-shaped reversals off a low, which is closer to a mean-reversion trade
than the "orderly pullback, intact trend resumes" thesis this path is supposed to capture.

**Proposed direction:** decouple the opportunity budget from immediate price recovery. A genuine
base/consolidation period doesn't burn much of the recovery-distance budget on its own (price isn't
moving far during a base), so the current design should already tolerate a longer base in principle
— the actual fix is to stop requiring `price_recovery`'s fast, single-day trigger as the thing that
starts the confirmation clock, and instead confirm off a real breakout condition (e.g. price closing
above the base's own high, or a volatility-contraction-then-expansion signature) that can only
happen after a base has actually formed. This is a redesign of the entry trigger, not a threshold
change, and should be specified and frozen before testing, consistent with the project's existing
discipline.

### Q2. `redeploy-washout`: is it basically worse than v1.0 excluding COVID?

More nuanced than a flat "yes" — two different comparisons tell different stories, and the gap
between them is itself the finding.

**On a fixed-horizon label basis** (the only way v1.0 was ever measured, since it had no real exit
engine), re-computed v1.1's ex-COVID entries the same way: **+1.51%/+3.63%/+5.91%** at 20/40/65
sessions, versus v1.0's own ex-2020 figure of **+4.59%/+4.24%/+4.80%**
(`backtest-investigate-codex.md §3`). Modestly worse at 20d and 40d, but actually *better* at 65d —
not uniformly worse.

**On actual held returns** (only measurable for v1.1, since v1.0 never had a real exit mechanism):
Section 2 already found the ex-COVID average is roughly flat-to-negative (−0.07%), a materially
worse picture than the label comparison above.

**The gap between these two numbers is the real diagnosis: the raw signal is roughly comparable to
modestly worse than v1.0's, but the exit mechanism (`thesis_failed`) is doing more damage than the
entry logic is.** `thesis_failed` exits at a median of ~3 sessions and is negative 7 of 9 times for
the non-COVID episodes — it's cutting into recoveries that the fixed-horizon label shows would often
have continued. This reframes the fix target: the entry logic isn't clearly worse than v1.0's, but
the new, real exit logic — which v1.0 never had to get right, because it never held anything — is
currently costing more than it protects.

**Improvement directions, in priority order:**
1. Require `thesis_failed`'s trigger (trend + volatility deterioration ≥ 0.35 and rising stress) to
   persist for 2 consecutive sessions rather than firing same-day, to filter single-day noise that
   doesn't represent a genuine resumption of decline.
2. Address the premature-entry pattern directly (several entries fire 10-14 sessions before the real
   bottom) — possibly by requiring evidence that the decline's momentum has already stopped
   accelerating before allowing entry, not just that stabilization has crossed a threshold.
3. The credit coverage gap (9 of 12 entries rely on a HYG/TLT-only lower-bound proxy for credit
   confirmation) is a secondary lever — better credit coverage could reduce how often "confirmed"
   rests on a partial reading.

Each of these should be tested as its own frozen variant, not adopted together, to keep attribution
clean per the project's existing discipline.

### Q3. `protect-extension`: what is the problem exactly, and can it be improved?

Two distinct problems, not one — traced the previously-unresolved arming gap to a specific,
concrete mechanism this time rather than leaving it open.

**Problem A — a genuine memory-window timing race, root-caused for the 2023-02 case.** Pulled the
raw extension episode state day by day: the episode `extension:2022-12-02` was armed and building
through early February 2023 (`hit_count=6`, `peak=0.755` on 2023-02-01), but its fixed 40-session
memory window expired by **2023-02-08** — one session before v1.0's protect call fired on
2023-02-09/10. Despite `renewal_ready=True` (the re-arm cooldown was already satisfied), no fresh
qualifying hit was recorded that week to re-arm it, so the episode simply aged out one session too
early relative to when confirming evidence arrived. This is a timing race, not a design flaw in the
40-session constant itself — but it's a real race the v1.0-equivalent scoring apparently won and the
v1.1 owned-evidence redesign lost for this specific case, most likely because the new evidence
construction picks a different (and here, earlier) arming date for what is conceptually the same
underlying stretch. Worth checking whether this is a one-off or a systematic side effect of the
owned-evidence redesign shifting arming dates earlier in general (which would make the fixed
40-session window bite more often than it did under v1.0's scoring) — I did not check this across
all three unexplained cases, only 2023-02 in this pass.

**Problem B — precision, independent of coverage.** Of the 5 events that do fire, only 1 (Dec 2019)
is a real catch; 3 of 5 show exactly zero entry loss across their entire holding window — a clean
false-alarm signature, not a labeling artifact (Section 3).

**Improvement directions:**
1. For the timing race: consider whether re-arming after expiry should be easier when the underlying
   stretch is clearly still ongoing (e.g. a persistence-based re-arm rather than requiring a wholly
   fresh single-day 0.75 hit), rather than assuming the 40-session constant itself needs to change —
   the constant is inherited from v1.0 and wasn't the thing that changed.
2. For precision: add a short persistence requirement to the `damage` gate specifically (e.g. 2
   consecutive sessions of trend deterioration ≥ 0.35 while already armed) to filter one-day noise
   spikes — but keep this distinct from arming's own persistence count, unlike `protect-break`'s
   design (see Q4), where conflating the two is exactly what causes that path's lag problem.

### Q4. `protect-break`: proposal to make it useful?

Checked the actual gate structure before proposing anything, since the Section 4 finding (57% of
entries fire within the bottom decile of local price range) needed a mechanism, not just a
description. Confirmed in `regime_lifecycle.py`: `setup` (`br["armed"]`) and `persistent_damage`
(`break_streak >= config.persistence`) are **both gated behind the identical 3-consecutive-session
streak** — arming itself already requires the full persistence count, so there is no genuine
two-stage "arm early on a fast signal, confirm later" structure the way `protect-extension` and both
redeploy paths have. `protect-break`'s "confirmation" is effectively a restatement of its own arming
condition. That's the structural reason it lags: it cannot do anything until 3 straight bad days
have already elapsed, which mechanically tends to land close to a decline's end rather than its
start.

**Proposed redesign, following the pattern already proven elsewhere in this system:** separate
arming from firing. Arm a "break watch" memory off a faster, cheaper trigger (e.g. a single sharp
bad day, or 2-of-3 sessions rather than 3-of-3 consecutive), persist that as bounded memory (mirroring
extension/washout's existing arm-then-decay pattern), and let the actual fire condition be a
separate, current-day confirmation (the existing `trend`/`corroboration` gates) evaluated *while*
that memory is armed — decoupling "how much persistence proves this is real" from "how fast can we
act once persuaded." This should let it fire earlier in a decline, closer to when damage first
becomes credible, rather than waiting out the full 3 sessions regardless of how the confirming
evidence develops. This needs to be specified and tested as its own frozen variant before adoption,
not adopted from this diagnosis directly — it's a plausible fix for a precisely-identified mechanism,
not a validated one.

**A second, complementary idea, not a replacement for the first:** given `protect-break`'s current
form empirically behaves like a confirmed-capitulation detector rather than a peak detector, it may
have real value repurposed as a *corroborating* input into the redeploy paths' confirmation families
rather than only as a protect trigger — the same idea already raised for the old `regime_break` in
`r3-discussion.md` T3, now with much more precise, quantified support (57% bottom-decile firing,
broad-based across 11 years) for the new mechanism too. Worth investigating alongside the arm/confirm
redesign above, not instead of it — the two aren't mutually exclusive.

---

## 6. Follow-Up: `protect-break` Is Still Unresolved After V1.2's Entry Review

Checked `plans/v1.2/entry-review.md` and the live `regime_lifecycle.py` after the v1.2 entry-focused
round landed. `redeploy-confirm` and `protect-extension` both materially improved (Section 5's Q1/Q3
diagnoses were acted on in some form — `redeploy-confirm` now fires 13 times with a sequenced-pullback
redesign, and `protect-extension`'s return direction is now correctly negative at 20d). `protect-break`
did not improve, and the project's own research doc says so directly: *"Break remains unresolved and
the combined model makes its table worse... This is not a completed performance fix."*

### The numbers moved the wrong way

| | v1.1 | v1.2 |
| --- | ---: | ---: |
| entries | 21 | 30 |
| 20d / 40d / 65d vs baseline (+1.3/+2.5/+4.1%) | +1.6/+1.9/+4.5% | +1.5/+3.2/+6.2% |
| held return | +1.94% | +0.42% |

40d and 65d both moved further in the wrong direction (more positive, not less) despite held return
improving in absolute terms — more entries fired, not fewer, and the fixed-horizon story got worse
even as the held-return story got marginally better.

### Root cause confirmed unchanged in the live code

`setup` (arming) and `persistent_damage` are still both gated on the identical
`break_streak >= config.persistence` condition (`regime_lifecycle.py:500,602`) — the exact structural
issue diagnosed in Section 4 above. The one adopted production change (commit `d78261c`) added a new
`fresh_damage` gate checking only the 5-day leaf of trend evidence on top of the existing structure —
a recency filter, not a restructuring of when arming happens relative to confirmation. A bounded-retry
mechanism was also added (`66be59c`/`3cb06a1`), which explains the entry-count increase from 21 to 30,
but retries are gated on the same `break_streak >= persistence` condition, so they inherit the same lag
rather than correcting it.

**Verified the lag persists empirically in the actual v1.2 entries, not just inferred from the code.**
Checked each of the 12 entries new to v1.2 (not present in v1.1's list) for its percentile within a
±20-session local price window (0 = exact local low):

```
2022-10-12  0.00   <- the exact bottom of the entire 2022 bear market
2016-02-08  0.05
2019-08-07  0.15
2018-11-23  0.17
2022-05-09  0.20
2022-02-22  0.22
2022-12-29  0.24
2025-04-03  0.24
2020-02-27  0.39
2023-09-25  0.39
2022-09-01  0.41
2016-01-06  0.87   <- the one exception
```

11 of 12 sit in the lower half of their local range. `2022-10-12` is a particularly clean
confirmation: the model's defensive signal firing on literally the single best entry day of the
entire 10-year sample.

### What was tried, and why it didn't test the actual mechanism

`entry-review.md` documents two experiments aimed at `protect-break` specifically, both explicitly
rejected with the reasoning shown, not silently dropped:

- **B1** (require a fresh joint closing low plus specifically breadth/credit corroboration):
  worsened 40d/65d, discarded.
- **B2** (isolate just the fresh joint closing low ablation, no family restriction): also discarded
  — *"Neither trial fixes break entry selection... report this topic as unresolved."*

Both are **precision filters** on the existing trigger — narrowing which days satisfy a 3-consecutive-
session-damage condition. Neither tests **decoupling arm-speed from confirmation-speed**, which was
this document's Section 4 proposal: arm a "break watch" memory off a cheaper, faster signal (a single
sharp day, or 2-of-3 non-consecutive sessions), then let the existing `trend`/`corroboration` gates
confirm separately, on their own timing, while that memory is armed — the same setup-then-confirm
separation extension and washout already use successfully. B1/B2 made the trigger *stricter*; this
proposal would make it *faster*. A stricter trigger cannot fix a lag problem regardless of its outcome,
which is consistent with both trials failing to move the needle in the intended direction.

### Proposed next experiment (`B3`, continuing the doc's own naming convention)

```text
Arm a break-watch memory on: both indexes below MA50 for 1 session (or 2-of-3 non-consecutive),
  not the full 3-consecutive-session persistence requirement.
Confirm (fire) separately, on any subsequent day while armed, when:
  current trend deterioration >= family_gate (the existing `fresh_damage`/5d check)
  AND corroboration from another owned family >= family_gate (existing, unchanged)
Bound the armed-but-unconfirmed memory window (e.g. 5-10 sessions, mirroring washout's grace
  pattern) so a single bad day without follow-through expires rather than lingering indefinitely.
```

This should be specified precisely and run as its own frozen trial against the same frozen 2,617-date
window before any adoption decision, per the project's existing discipline — it is a plausible fix for
a precisely-identified mechanism, not a validated one. If it still fires late, that would be real
evidence the lag isn't fixable by timing alone and the corroborating-input repurposing idea (Section 4,
using `protect-break` as redeploy evidence rather than a protect trigger) deserves more weight instead.
