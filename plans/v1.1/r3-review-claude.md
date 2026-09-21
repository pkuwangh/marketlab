# r3 Review: Redeploy Coverage Gaps Beyond The Agreed Correctness Baseline

**Author:** Claude (Sonnet 5), September 2026.
**Scope:** Findings from [backtest-investigate-claude.md](backtest-investigate-claude.md), each
checked against [r2-proposal.md](r2-proposal.md) to confirm it is not already covered:

1. Current-washout/stabilization non-alignment blocks 44% of armed episodes; a genuine same-day
   timing clash accounts for 31% of that (5 of 16 episodes), corrected from an earlier looser framing.
2. A second, warning-only "broad stabilization without a prior washout" path, mirroring `regime_break`.
3. `regime_break_warning` behaves as a contrarian indicator at 20-65 session horizons in this sample
   (correction: not at 5-10 sessions, see the correction note in Topic 3) — diagnosed down to its
   root cause, and, per the user's direction, redesigned into a proposal for a genuine `protect_break`
   action path.
4. Reporting each action path separately in backtest output — a cross-cutting reporting change that
   applies to both the protect-side (Topic 3) and redeploy-side (Topic 2) path proposals.
5. Phase-exclusivity (`not washout_memory.armed`) may be too blunt for protect — originally claimed
   as the single best-evidenced finding in this document; corrected in Topic 5 after
   `r3-proposal.md §2` disputed it (the true count is one confirmed case, not seven).

---

# Topic 1: Current-Washout/Stabilization Non-Alignment (Timing Clash Is A Subset, Not All Of It)

**Wording correction, September 2026:** the title and summary line below originally said "clash"
and "44% structurally blocked" as if all 7 non-aligning episodes were the same timing-clash
mechanism. `r3-proposal.md §2` and its T10/T1 discussion replies caught that this conflates two
different things even though the body of this topic already distinguished them correctly two
paragraphs down: 44% (7 of 16) is the **non-alignment** rate; **5 of 16 (31%)** is the genuine
timing-clash subset specifically, with the other 2 being a different, single-threshold failure. The
detailed breakdown below was already right; only the title and headline framing overstated it.
Retitled and reworded the summary line to match the detailed breakdown rather than the loose
version of it.

## Is this covered by r2-proposal.md?

No. I grepped the proposal for every reference to the redeploy entry gate's "current opportunity"
condition. The only relevant text is in §4:

> Retain current broad washout at least **0.35**, release at least **0.05**, confirmation, strength,
> and funding checks for redeploy. Missing/changed coverage cannot count as relief. Peak and current
> stress must use the same definition and comparable input set.

"Retain... at least 0.35" carries the existing same-day requirement forward unchanged. The proposal
does give `release` a remembered-peak treatment (`release = max(0, active_episode_peak_stress -
current_stress)`, §4), decoupling *that* condition from "today specifically" — but it does not extend
the same treatment to the `current_washout_score >= 0.35` condition itself, and nothing in §3
(confirmation) or §5 (posture) addresses same-day alignment between `current_washout_score` and
`stabilization_score` either. The one place the proposal comes close is the October 21, 2022
reference case in §8 ("Stabilization 0.941 across three families, but washout unarmed. Check other
current gates before claiming C would enter") — which flags that *other* gates might still block
entry, but doesn't diagnose this specific mechanism or propose a fix. This is a new finding, not a
restatement of anything already scoped for v1.1.

---

## The problem

`redeploy_ready` (`regime.py:3663-3669`) requires, on one snapshot date:

```text
washout_memory.armed              # persists up to 15 sessions (has memory)
AND current_washout_score >= 0.35 # recomputed fresh every day (no memory)
AND washout_release >= 0.05       # references a remembered peak (has memory)
AND stabilization_score >= 0.75   # recomputed fresh every day (no memory)
AND redeploy_strength >= 0.55     # = sqrt(current_washout_score * stabilization_score)
```

Only `washout_memory.armed` and `washout_release` reference persisted state. `current_washout_score`
and `stabilization_score` are both same-day-only reads with no memory of their own, and they are
**anti-correlated by construction**: `current_washout_score` is a levels/percentile read of how
stressed the market is *right now*; `stabilization_score` measures how much conditions have
*improved over the last 5 days* (VIX falling, breadth turning up, etc.). As an episode plays out from
panic toward calm, the first mechanically falls as the second mechanically rises. Requiring both to
clear their thresholds on the identical calendar day asks for two quantities moving in opposite
directions to be simultaneously extreme.

## Empirical scope

I scanned every `washout_armed == True` day across the full 2016-2026 v1.0 history (458 days) and
grouped them into the 16 distinct continuous armed episodes:

- 39 of 458 armed days have `current_washout_score >= 0.35` and `stabilization_score >= 0.75`
  simultaneously.
- At the episode level: **9 of 16 episodes see the two conditions align on at least one day**, and
  of those 9, **8 actually fire** (the remaining gates — release, strength, funding — mostly pass
  once the core two align, confirming this pair is the binding constraint, not the others).
- **7 of 16 episodes (44%) never see the two conditions align on any single day, and none of them
  fire — of these 7, 5 (31% of all 16) are the genuine timing-clash mechanism this topic is about;
  the other 2 are a different, single-threshold failure (see the table below), not a timing clash.**

The 7 non-aligning episodes:

| Episode | Fired? | Failure mode |
| --- | --- | --- |
| 2016-11-02 → 11-28 | No | Both thresholds individually crossed on different days, never together |
| 2017-04-13 → 05-09 | No | Both thresholds individually crossed on different days, never together |
| 2017-08-10 → 09-12 | No | `stabilization_score` never reached 0.75 at all — a different, single-threshold failure, not a timing clash |
| 2018-02-12 → 03-06 | No | Both thresholds individually crossed on different days, never together (concrete numbers below) |
| 2018-03-21 → 05-02 | No | Both thresholds individually crossed on different days, never together (concrete numbers below) |
| 2023-10-27 → 11-17 | No | Both thresholds individually crossed on different days, never together |
| 2024-12-19 → 2025-01-14 | No | `current_washout_score` never reached 0.35 — the mirror single-threshold failure |

Five of the seven are genuine same-day timing clashes (both conditions individually satisfiable,
never simultaneously); two are simple single-threshold misses unrelated to timing and are set aside
here. Concrete numbers from two of the five, read directly from `regime-v1.0.csv`:

```text
2018-02-15  washout_armed=True  current_washout=0.226  stabilization=0.843   (stabilization clears 0.75; current_washout has already collapsed below 0.35)
2018-04-18  washout_armed=True  current_washout=0.304  stabilization=0.757   (same pattern: stabilization just clears 0.75, current_washout just missed 0.35)
```

Both examples show the same signature: the day `stabilization_score` clears its gate,
`current_washout_score` has already fallen below its own floor in that identical snapshot.

**Note on the earlier `2018-11-23` example I gave in conversation before this scan**: it does not
belong on the "never aligned" list above. It's a sub-window inside the longer 2018-10-10 →
2019-01-25 episode, which *did* eventually align later (the Dec 24, 2018 low into the Jan 7/8, 2019
redeploy) and fired correctly. Flagging the correction here so it doesn't propagate into the record
alongside the seven genuine cases.

---

## Why this matters for the v1.1 backlog

This directly compounds the largest single miss category already documented in
[backtest-investigate-claude.md §4.b](backtest-investigate-claude.md) ("stabilization is visible,
but washout setup is not armed," 5 of 17 missed bottoms) — but it's a distinct mechanism. That
category is about washout never *arming* in the first place. This finding is about washout having
*already armed*, and then the entry gate itself being unable to fire because two of its same-day
conditions are structurally opposed. Fixing the arming path (the transmission experiment or the
broad-stabilization second path already proposed) does not fix this — all 7 non-aligning episodes
here had `washout_memory.armed == True`; arming was never the problem for them.

## Proposed fix (superseded by r3-proposal.md — see note below)

**Superseded, September 2026:** `r3-proposal.md §2` explicitly rejected the peak-referencing
approach below as the preferred fix ("Reject as the preferred fix: another trailing-K maximum of
broad washout. It adds a second stress-memory window, does not measure remaining price opportunity,
and leaves the strength restriction unless that is changed too") and Codex's T3 discussion reply
sharpened why: a remembered peak proves prior stress occurred, not that a *tradeable opportunity*
still remains after the rebound — those are different claims, and my design only addressed the
former. The proposal's actual direction (`§6.1`) removes both `current_washout_score >= 0.35` and
its role in `redeploy_strength` entirely, replacing them with a separately specified, causal
remaining-opportunity condition (a price anchor, distance metric, and bounded expiry, frozen before
replay — `§12` item 2). I'm leaving my original proposal below for the record, since the empirical
scope and mechanism diagnosis above are still correct and were the basis for the proposal's own
"accept the same-day fear/confirmation problem" disposition — only the *fix* was superseded, not the
finding.

Give `current_washout_score`'s entry-gate check the same kind of peak-referencing treatment
`washout_release` already has, rather than requiring today's value specifically:

```text
current_washout_ready = max(current_washout_score over the trailing K sessions) >= 0.35
```

instead of `current_washout_score >= 0.35` evaluated only on today's snapshot. This is not a new
design pattern for this codebase — `release = max(0, active_episode_peak_stress - current_stress)`
(`r2-proposal.md §4`) already decouples "peak" from "today" for a directly adjacent quantity in the
same gate. Extending the same treatment to `current_washout_ready` is consistent with that existing
precedent, not a new kind of compensation.

I'd keep this deliberately narrow to avoid reintroducing the "geometric compensation hides weak
setup" failure mode the v0.0 → v1.0 redesign was built to eliminate (per `ALGORITHM_DESIGN.md`
and the r1 discussion's repeated caution against letting one extreme leg substitute for a missing
one): `current_washout_ready` should remain a **hard, independent gate** — either satisfied within
the trailing window or not — not blended or averaged with `stabilization_score` into a single
compensating score. `stabilization_score` still has to independently clear 0.75 on its own same-day
reading; only the washout side gets the short lookback. `K` should be small — a handful of sessions,
not the full 15-session arming grace window — specifically to bound how far a compensating "it was
washed out a week ago" claim is allowed to reach, while still covering the 1-2 week lag the concrete
examples above show between a washout peak and stabilization catching up.

**Open questions, not resolved here, consistent with the project's "predeclare, don't fit to
reproduce old frequency" discipline:**

1. What should `K` be? I don't have a principled value yet — it should be chosen from the shape of
   the lag in cases like the two above (roughly 1-3 weeks), not tuned to make these specific 7
   episodes fire.
2. Should the same treatment apply symmetrically to `stabilization_score` (a trailing "stabilization
   reached 0.75 recently and hasn't reversed" check) instead of, or in addition to, giving
   `current_washout_score` the memory? I lean toward washout-side-only, since stabilization is
   already the *forward-looking* confirmation signal in the setup-then-confirm framing this project
   uses throughout, and giving it a backward-looking allowance too risks blurring "conditions are
   improving now" into "conditions improved at some point recently," which is a different claim.
   But I don't have strong evidence either way yet.
3. This should be evaluated the same way the transmission experiment in `r2-proposal.md §7` is
   scoped — as a variant with its own frozen constants, tested against the existing baseline on
   added/removed events, false-start rate, and adverse excursion, not adopted by inspection of these
   7 episodes alone.

## Addendum: a second, compounding barrier even when the two conditions do align

Checking `backtest-investigate-claude.md §4.b`'s two "very close miss" dates
(2018-10-29, 2026-03-30) against the raw data surfaced a related but distinct finding, plus a small
correction to that doc's own description.

**Correction:** `backtest-investigate-claude.md` describes 2018-10-29 and 2026-03-30 themselves as
the near-miss dates. Checked directly: on 2018-10-29 itself, `stabilization_score = 0.15`, nowhere
near its 0.75 gate — that description doesn't match this exact date (likely picked up from the
peak-strength day in a nearby window rather than the zigzag date itself, the same kind of date
imprecision already corrected once in this document's Topic 1 write-up for `2018-11-23`).

**What does hold, precisely, a few sessions after the 2026-03-30 bottom:** on **2026-04-07**,
`current_washout_score = 0.384` (clears 0.35) and `stabilization_score = 0.787` (clears 0.75) —
both conditions genuinely align, resolving the Topic 1 problem for that day. But
`redeploy_strength = sqrt(0.384 * 0.787) = 0.549` — **0.001 short of the 0.55 strength gate.** The
system's own generated text confirms it exactly: *"Redeploy setup and confirmation passed, but
strength is below its gate."* This is a second, compounding barrier: even once the anti-correlation
problem above is fixed (or simply resolves itself for a day), the geometric mean of two values that
each just barely clear their own floor can still fall just short of the strength threshold, because
`sqrt(0.35 * 0.75) ≈ 0.512` — meaning any pair of values close to their individual minimums is
mathematically likely to miss 0.55 even when both individually pass. Worth folding into whichever
variant addresses the main same-day clash — if a peak-referencing window fixes the alignment problem
but the strength gate still blocks marginal cases like this one, that would show up as "arming
improved, firing didn't," a distinguishable and useful diagnostic outcome.

**Also worth correcting:** `backtest-investigate-claude.md §4.b` describes **2023-10-27** as "setup
pressure present, but never accumulated enough persistence/single-snapshot strength to arm." Checked
directly: `washout_armed` is `False` on 2023-10-23 (matching that description, but for a different
date) and flips to `True` starting exactly on 2023-10-27 and stays armed through 2023-11-17. Once
armed, this episode shows an unusually explicit confirming example of Topic 1's main finding —
`stabilization_score` climbs from 0.65 (2023-11-01) to 0.97 (2023-11-02) while `current_washout`
falls from 0.26 to 0.20 in the same two sessions, and the system's own text on 2023-11-02 through
11-08 says, verbatim: *"Washout setup and stabilization are present, but current broad washout has
already cleared."* That's the system naming this document's Topic 1 mechanism in its own words. This
episode belongs in Topic 1's evidence base, not as a separate "never armed" case.

## Recommendation (finding stands, fix direction superseded)

The finding (non-alignment blocks 44% of armed episodes, a genuine timing clash for 31%) is a named
item in the v1.1 backlog — it's a third, independent lever on redeploy coverage, orthogonal to both
the transmission experiment and the broad-stabilization second path (transmission changes whether
washout *arms* at all; this changes whether an already-armed episode can ever *fire*). The specific
fix direction is now `r3-proposal.md §6.1`'s remaining-opportunity redesign, not the peak-referencing
proposal above — see the superseded note. It should still be evaluated as its own frozen variant
(`W-opportunity` in the proposal's `§8` experiment table), rather than folded into the repaired
baseline by default — consistent with the project's
existing discipline of not changing more than one declared thing at a time when attributing which
change produced which effect.

---

# Topic 2: Broad Stabilization Without A Prior Washout, Mirroring `regime_break`

## Is this covered by r2-proposal.md?

No, and this one needs more care than Topic 1 before treating it as a straightforward gap to close.
I grepped for "broad stabilization," "second path," "mirror," and "regime_break" — the only hit is
the existing protect-side line, "Regime-break stays warning context, not a new protect action"
(§3). There is no redeploy-side equivalent anywhere in the document.

**But this isn't simply absent — it sits close to something the discussion already deliberately
excluded.** Two things are worth stating plainly before the proposal itself:

1. `r2-proposal.md §1`'s out-of-scope list names **"a parallel slow-decline lifecycle"**. §7's
   transmission experiment (the one washout-coverage item that *is* in scope) is deliberately
   narrower than a new path — it relaxes one gate inside the existing single washout path, not a
   second, independently-triggered one.
2. This is adjacent to an idea I proposed and **withdrew** in the r1 discussion
   ([r1-discussion.md D10](r1-discussion.md#d10-slow-grind-bear-markets-are-structurally-invisible-to-washout-arming)):
   a second washout-arming path keyed on cumulative drawdown duration. Codex's pushback there was
   correct and I conceded it — duration/depth is conceptually a trend-leg signal, and the real
   question was whether breadth/credit transmission is a necessary condition or corroboration,
   which is exactly what §7 now tests. What follows here is a different mechanism (a
   confirmation-triggered path that doesn't require washout to arm at all, rather than a wider
   definition of arming), but it's the same *category* of change, and the honest framing is that it
   reopens a question rather than closes an uncontested gap.

There's also a self-consistency risk worth naming directly, since the user asked for this to mirror
`regime_break`: `regime_break` is warning-only specifically because the v0.0 to v1.0 redesign found
"broad deterioration without prior extension" too false-positive-prone as a real protect action. The
same logic plausibly applies to "broad stabilization without prior washout" on the redeploy side —
which the evidence below confirms is a real risk, not a hypothetical one.

## Evidence

### The naive mirror is noisy, not rare

I first tested the most literal mirror of `regime_break`'s framing: `not washout_memory.armed AND
stabilization_score >= 0.75`. This fires on **128 of 2,617 days (4.9%), across 63 distinct
episodes** over 2016-2026 — nothing like `regime_break`'s 15 total days. Adding the same
family-count requirement the real redeploy gate already uses (`stabilization` confirmed across
`>= 2` of the five families) barely helps: 120 days, 59 episodes. Requiring some recent
`deterioration_score` elevation as a "this is recovering from something" precondition doesn't help
much either, for the same reason `deterioration_score` itself is noisy day to day.

The reason is structural, not a tuning problem: `regime_break` is rare because broad, multi-family
*deterioration* is rare — most days aren't broadly bad. But broad *stabilization* is not rare in the
same way, because most days in a market that spends most of its time trending up look like
"stabilization" by a same-day, model-derived measure. A same-day mirror of `regime_break` doesn't
inherit its rarity for free.

### A genuine price-based precondition fixes this, and catches the highest-value miss

Replacing the model-derived "prior deterioration" precondition with a real, independent one — SPY's
own 60-day return, not any of the model's own scores — changes the picture completely:

```text
condition = NOT washout_memory.armed
            AND stabilization_score >= 0.75
            AND stabilization confirmed across >= 2 families
            AND spy_return_60d <= -5%
```

This fires on **12 days across 5 episodes** over the full 10-year history — comparable rarity to
`regime_break`'s own 15 days. Three of the five episodes (all in May 2020) fall inside the already-
successful COVID redeploy episode and add no new value. But **two of the five, October 18-19 and
October 21-25, 2022, fall exactly inside the single highest-value miss identified in
[backtest-investigate-claude.md §4.b](backtest-investigate-claude.md)** — the Oct 12, 2022 bottom,
SPY's -24.5% drawdown, the largest capitulation in the sample after COVID, which never armed washout
at all and never fired redeploy. This matches the existing diagnostic in the doc almost exactly
("October 21, 2022: stabilization 0.941 across three families, but washout unarmed").

**This is a partial fix, not a complete one, and I want to be precise about that rather than oversell
it.** It does not recover the other four cases from the original "stabilization confirmed, no setup
to attach to" miss category (2019-06-03, 2020-06-11, 2022-01-27, 2023-03-13) — none of those show a
60-day SPY return at or below -5% at the relevant date, so this specific precondition is too strict
to catch them. I did not find a single precondition that recovers all five without also reintroducing
the noise problem above; that would need its own separate investigation rather than a guess.

## Proposed design

Given the self-consistency risk, I'd propose the *same* treatment `regime_break` already gets, not
an asymmetric one — a new warning label, not a new action:

```text
broad_stabilization_warning:
  fires when NOT washout_memory.armed
             AND stabilization_score >= ACTION_REDEPLOY_STABILIZATION_THRESHOLD (0.75)
             AND stabilization confirmed across >= 2 families
             AND spy_return_60d <= -0.05
  reported as context, not scale_up_redeploy — mirrors "regime_break_warning: broad deterioration
  without prior extension is context, not a de-risk action"
```

This reuses every scoring primitive already computed for the real redeploy gate (`stabilization_score`,
the per-family confirmation count) plus one new, independent, already-available input
(`spy_return_60d`, already a pressure feature). It adds a reporting branch, not a new action branch
or a new scored lifecycle — closer in footprint to "add a diagnostic label" than to "a parallel
slow-decline lifecycle," which I think meaningfully narrows the scope-boundary concern above, though
it doesn't eliminate it. Promotion from warning to a real action, if ever justified, should wait
until this warning accumulates its own out-of-sample track record — the same evidentiary bar
`regime_break` would need before being promoted on the protect side, which I understand from
`r1-review-codex.md` was deliberately never done "just to improve this sample."

### Correction: the confirmation bar above is too weak relative to what it's replacing

The design above reuses Path 1's exact confirmation numbers (`0.75`, `>= 2` families) even though its
setup precondition (`spy_return_60d <= -5%`) is far weaker than Path 1's setup (an armed, gated,
multi-condition capitulation). That's backwards. I checked what `stabilization_score` actually looks
like at the moment of firing across all 29 historical Path 1 redeploy rows:

```text
min 0.78   25th pct 0.85   median 0.88   75th pct 0.96   max 1.00
```

Every historical Path 1 fire happens with stabilization already well past its 0.75 floor — typically
0.85-1.00, never "barely crossing it." Path 1 gets this near-for-free from the mechanics Topic 1
documents (current_washout and stabilization are anti-correlated, so by the time the harder,
later-arriving `current_washout` condition clears, stabilization has usually already run well past
its own floor). Path 2 has no equivalent `current_washout_ready` condition to piggyback on, so it
can't assume the same dynamic will bail it out — reusing Path 1's stated `0.75`/`2`-family bar as
written would mean Path 2 demands *less total evidence* than Path 1 typically delivers, despite
starting from a strictly weaker setup prior. The right design principle: the weaker the setup side,
the more the confirmation side has to explicitly carry, not implicitly inherit.

Tightening the confirmation bar to `stabilization >= 0.85` and `>= 3` families — closer to what
Path 1 empirically requires anyway — and re-running the scan: **8 days across the same 5 episodes**,
still catching Oct 2022 cleanly (both 2022-10-19 and 2022-10-21 survive), with no episodes lost
relative to the looser `0.75`/`2` version. The tightened design:

```text
broad_stabilization_warning:
  fires when NOT washout_memory.armed
             AND stabilization_score >= 0.85
             AND stabilization confirmed across >= 3 families
             AND spy_return_60d <= -0.05
```

This is the version I'd actually propose going forward, not the one first drafted above.

## Recommendation

This is evidence, not a decision — I'm proposing it because the user asked me to, and because I
think the evidence is genuinely good (a rare, targeted signal that catches the single highest-value
miss in the whole study), not because I think it should bypass discussion given where it sits
relative to the agreed scope. Concretely, before this goes anywhere near implementation, I'd want:

1. Codex to weigh in on whether a warning-only, reuses-existing-primitives version like this still
   falls inside "a parallel slow-decline lifecycle," or whether that exclusion was aimed
   specifically at the drawdown-duration arming idea I withdrew in D10 and doesn't extend to a
   diagnostic-only addition like this one.
2. If accepted at all, it should ship as a warning label alongside the v1.1 correctness baseline,
   not as a promoted action, and specifically *not* bundled into the frozen A/B/C transmission study
   — it's a different mechanism (confirmation without any armed setup, versus relaxing one setup
   leg) and mixing them would make it hard to attribute which change did what, the same concern
   already raised for Topic 1.

---

# Topic 3: `regime_break_warning` Behaves As A Near-Perfect Contrarian Indicator

## Is this covered by r2-proposal.md?

No — grepped for "contrarian" and "reversed," no hits. Nothing in the proposal discusses the
*direction* of `regime_break_warning`'s predictive content, only that it should stay warning-only
rather than become an action (§3). This finding is about something more specific than that: not
just "don't promote it," but "if it were ever used as a bearish signal, the data says it's pointing
the wrong way."

## Evidence

I pulled forward SPY returns at 5/10/20/40/65 sessions from all 15 `regime_break_warning` days in
the corrected v1.0 history:

```text
                  5d       10d      20d      40d      65d
mean           +1.31%   +2.08%   +4.19%   +5.94%   +7.23%
median            -        -     +2.92%   +4.87%   +5.05%
minimum           -        -     +1.16%   +0.06%   +0.19%
baseline (all days) mean:
               +0.32%   +0.63%   +1.28%   +2.52%   +3.97%
```

**Correction, September 2026:** I originally wrote that all 15 days were positive "at every horizon
from 5 to 65 sessions, not one negative observation anywhere in the table." That's wrong, and
`r3-proposal.md §2` caught it — checked my own saved data directly: **4 of 15 are negative at 5
days, 3 of 15 are negative at 10 days.** Only 20/40/65 sessions are exception-free. All 15
`regime_break_warning` days — across 6 distinct episodes (2017-06, 2017-08, 2017-11, 2018-12,
2019-03, 2023-03) — show a **positive** forward return at 20, 40, and 65 sessions specifically, not
at every horizon down to 5 days. The mean at those three horizons is roughly **double the
unconditional baseline**, and this isn't an artifact of the two largest observations (the Dec 2018
cluster, which sits right at the bottom of that correction): excluding it entirely, the remaining 13
observations still average +3.1%/+4.2%/+5.4% at 20/40/65 days — still comfortably above baseline.
Even the *worst* single observation in the whole sample is positive at those three horizons
(+1.16%/+0.06%/+0.19%).

A signal built to mean "broad deterioration, market may be fragile/breaking" is, in this sample,
followed by *better-than-average* forward returns at the horizons that matter for a multi-week
posture decision, with no exceptions at 20 sessions or beyond. That's a real reversed-indicator
signature at those horizons — it is not exception-free at 5-10 days, and I should not have claimed
it was.

**Sample-size caveat, stated plainly:** 15 days collapse to 6 largely-independent episodes, which is
a small and somewhat clustered sample (three of the six episodes are 2017, a generally calm
risk-on year). I would not treat this as a validated, tradeable contrarian edge — but the
consistency (exception-free at 20-65 sessions across every episode, including after removing the
largest cluster) is well beyond what I'd expect from pure noise on 6 episodes, and it's directionally
consistent with the mechanism already noted in
[backtest-investigate-claude.md §3](backtest-investigate-claude.md) — `regime_break` fires when
broad deterioration has already spread across several families *without* a prior extension, which
by construction tends to mean the damage has already largely happened rather than being about to
start. Two of the six episodes (2018-12-21/24, 2023-03-13) sit exactly at independently-identified
market bottoms from the same zigzag analysis; the other four don't coincide with a major bottom but
still show consistently positive forward drift.

## Why this matters beyond "don't promote it to a protect action"

This is a stronger conclusion than the one already in `backtest-investigate-claude.md §3`, which
only said `regime_break` was too rare and poorly aligned with tops to explain the missed-protect
pattern. This finding says something more specific: **the evidence points toward `regime_break`
being weak corroborating evidence for the *other* side of the lifecycle, not neutral context.** That
connects directly to Topic 2 above — rather than only adding a *new*, separately-gated
`broad_stabilization_warning`, this suggests the existing `regime_break_warning` signal itself, when
it fires, could be surfaced as one input toward redeploy consideration (e.g., as one of the
corroborating families in a broad-stabilization gate, or simply reported alongside redeploy
diagnostics with its own historical forward-return context attached) rather than logged purely as
protect-side, action-suppressing context with no connection to the other lifecycle.

## Initial recommendation (superseded below)

My first instinct was not to act on this by flipping `regime_break` into a redeploy trigger outright
— 6 episodes is too small a sample to hang an action rule on, and doing so would repeat exactly the
mistake the v0.0 to v1.0 redesign was built to correct (adding action paths because a small backtest
sample looks good). I proposed instead: (1) report the forward-return context alongside
`regime_break_warning` in the daily/report output as a labeling-only change; (2) track it as a
candidate corroborating input for Topic 2's `broad_stabilization_warning` rather than building a
third mechanism for the same observation; (3) keep collecting forward evidence rather than treating
6 episodes as sufficient.

## Superseding direction: redesign it into a real action path

The user's direction supersedes the recommendation above: (1) promote it to a genuine protect action
path to expand protect's coverage, and (2) make the indicator itself actually useful before that
happens, since the evidence above established the current condition is contrarian. (The reporting
split between `extension_unwind` and this new path — and the equivalent split on the redeploy side —
applies to both protect and redeploy paths generally, so it's pulled out into its own topic below
rather than scoped to this one.)

**Promoting the current, unmodified condition to an action would be actively harmful** — the
forward-return evidence above showed it precedes positive returns with zero exceptions across the
sample. So (2) has to come first; (1) applies to the redesigned condition, not the current one.

## Root cause: two distinct defects, not one

Worth restating precisely before the diagnosis: `regime_break` has never fired an action in the
historical record — every occurrence has `action_state="no_change"`. This isn't just an empirical
observation; `_protect_gate_result` currently has no code branch that can return
`path="regime_break"` at all, only `path=None` with a `reason` string, so the redesign below has to
add that branch, not just relax an existing one.

I decomposed `fragility_context_score` into its four component modules
(`pressure_module__breadth_fragility__stretch`, `credit_risk_appetite__stretch`,
`liquidity_conditions__stretch`, `yield_curve_pressure__stretch`) for all 15 historical firing days.
Two separate problems are compounding:

1. **`credit_risk_appetite` (elevated on 13 of 15 days) blends two economically opposite readings
   into one averaged module score.** It's built from `hyg_tlt_relative_20d` (a genuine weakness
   read — HYG/TLT underperforming) and `credit_spread`'s *stretch* side (tight spreads —
   complacency, the D3-flagged sign issue). A high average can mean either "credit is stressed" or
   "credit is complacent"; the module score alone can't distinguish them.
2. **`liquidity_conditions` (NFCI stretch, confirmed complacency-flavored per D3) is the clearest
   tell.** It reads **0.0 and 0.20** on the two clusters that sit at genuine market troughs
   (Dec 2018, SVB March 2023 — both real tight-liquidity crises, correctly read as *not*
   complacent), but reads **>0.87 on every 2017 occurrence** — 2017 being a famously calm,
   low-volatility, easy-money year. This is the mechanism: the condition is mostly firing during
   *background complacency* hit by a brief, sharp deterioration blip — a shakeout-that-mean-reverts
   signature, not a structural breakdown signature.

Two structural factors compound both: **no persistence requirement** (a single day suffices, unlike
`extension_unwind`'s armed-memory chain — `ACTION_REGIME_BREAK_CONTEXT_THRESHOLD = 0.70` and
`ACTION_REGIME_BREAK_NON_VOL_MIN_FAMILIES = 2`, `regime.py:119-121`, are both same-day-only checks),
and **no exclusion for washout-armed periods** — 4 of the 15 firings (the Aug 2017 and Dec 2018
clusters) occur while `washout_memory.armed == True`, meaning those specific instances fire inside
territory the system already treats as washout/redeploy-candidate, on the wrong side of the
lifecycle. `extension_unwind` gets this exclusion (`protect_ready` requires `not
washout_memory.armed`); the `regime_break` routing at `regime.py:3707` does not check
`washout_memory.armed` at all before assigning its label.

## Proposed redesign

A `protect_break` path that's actually intended to catch structural breakdown, not
complacency-plus-shakeout:

1. **Replace `credit_risk_appetite`'s stretch side with a properly-owned weakness reading for this
   consumer.** Use `hyg_tlt_relative_20d` weakness alone, or `credit_spread`'s *washout* side (wide
   spreads = genuine stress) instead of its stretch side — not the blended average that currently
   conflates the two.
2. **Replace `liquidity_conditions`'s stretch side with its washout side** (tight NFCI = genuine
   funding stress) for this consumer specifically, consistent with the D3 finding but scoped here
   to `regime_break`'s own input rather than the general descriptive `fragility_context_score`,
   which `r2-proposal.md`'s P5 resolution deliberately left unchanged. This is a new, narrower fix:
   `regime_break` reads the raw descriptive `fragility_context_score` directly, so it is **not**
   touched by the already-agreed `r2-proposal.md` fixes (those only touch the posture-reset veto
   consumer and the credit-owned action helpers) — this consumer needs its own correction.
3. **Add a persistence requirement**, mirroring the arming pattern already used elsewhere (shorter
   than extension/washout's 40/15-session windows given "breaking" implies urgency — I'd propose
   researching something in the 3-5 session range, not guessing a final number here) — require the
   fragility-plus-deterioration condition to hold across multiple sessions, not a single snapshot,
   specifically to filter out the 1-3 day scares that the 2017 clusters show.
4. **Add the same `not washout_memory.armed` exclusion `extension_unwind` already has.** Given 4 of
   15 historical firings overlap with armed washout, this alone would have removed the Aug 2017 and
   Dec 2018 clusters — worth checking whether that materially changes the forward-return picture on
   the redesigned condition once (1)-(3) are also applied, rather than assuming it does.

This should go through the same discipline as the existing A/B/C transmission study: freeze the
redesigned condition's exact definition, backtest it as its own frozen variant, and confirm it
actually produces negative (or at least non-positive) forward returns before treating it as ready
to fire a real action — not promote it and observe, given how cleanly wrong the current version
turned out to be.

## Recommendation

Redesign and frozen-variant-test the condition first, confirm it behaves as intended (negative or
non-positive forward returns, not just "different from the current contrarian version"), and only
then give it a real action path. I would not skip straight to promoting it with the current
condition's inputs, given how unambiguous the evidence above is that doing so would fire a de-risk
action on days that have historically preceded above-average returns. See Topic 4 for the
reporting split once this path (and Topic 2's redeploy-side path) can actually fire.

---

# Topic 4: Report Each Action Path Separately In Backtest Output

This applies to both sides, not just the `protect_break` proposal in Topic 3 — pulled out into its
own topic for that reason rather than scoped under either Topic 2 or Topic 3.

**Protect side:** once Topic 3's redesigned `protect_break` condition can genuinely fire, it needs
its own path label distinct from `extension_unwind`. This is largely already supported, not a new
reporting system: `action_path` already exists as a field distinct from `action_state`, and the
cluster-level outcome tables (`workbooks/outcomes-protect-v1.0.txt`) already carry a `path` column
— every row currently shows `extension_unwind` because that's the only path that has ever produced a
fired action (`regime_break` has never fired one — see Topic 3). The work needed is giving
`_protect_gate_result` a real `return _ProtectGateResult(path="protect_break", ...)` branch instead
of always falling through to `path=None`; once that exists, it should appear in the same `path`
column automatically, and `regime outcomes --by protect` should already be able to break results
out by path with no new reporting machinery — worth confirming against the actual `--by protect`
implementation before assuming it, but I'd expect the grouping logic to already key off
`action_path` rather than something that needs rebuilding.

**Redeploy side, same treatment:** once Topic 2's `broad_stabilization` path exists, give it its own
explicit `action_path` value distinct from the existing washout-capitulation path, which currently
reports simply as `"redeploy"` — a generic label, not a specific one. I'd suggest renaming that
existing path's label at the same time, to something like `"washout_release"`, so both redeploy
paths have names as specific as protect's `extension_unwind`/`protect_break` pair, rather than one
specific name and one generic leftover default. `regime outcomes --by redeploy` should then be able
to break the two paths out the same way as the protect side.

## Recommendation

This is a reporting/labeling change riding on top of Topics 2 and 3's action-path work, not an
independent design decision — it doesn't need its own frozen-variant test or evidence gathering the
way Topics 2 and 3's underlying conditions do. Sequence it after whichever of those two paths is
implemented first; there's no dependency requiring both to land together.

---

# Topic 5: Phase-Exclusivity — Corrected, Weaker Than Originally Claimed

**Correction, September 2026, after `r3-proposal.md §2` disputed this topic's central claim.** The
original version of this topic (below the correction) claimed 7 of 20 clean protect misses traced
directly to `washout_memory.armed` blocking an otherwise-ready protect gate, ranked as the
"best-evidenced single change" in this whole document. That claim was substantially wrong, and I
verified the correction myself before accepting it rather than taking it on faith.

The error: `protect_ready = protect_gate.path is not None and not washout_memory.armed`
(`regime.py:3670`). I had checked `extension_armed`/`washout_armed`/`protect_strength` for my 7
dates and treated `washout_armed=True` as "the" cause whenever `extension_armed=False` — but
`protect_gate.path` is only non-`None` when the *full* `extension_ready` condition passes (armed
AND long-term-uptrend AND strength >= 0.55 AND volatility-confirming AND divergence AND lifecycle
confirmation), not `extension_armed` alone. I never checked the other four conditions. Going back to
the canonical `regime.json` files and reading the actual `action_reason` text for all 7 dates: six
of them (`2016-01-20`, `2018-03-23`, `2018-12-07`, `2018-12-19`, `2022-03-07`, `2022-03-28`) show
the redeploy-side diagnostic ("Washout setup is armed, but stabilization confirmation is below its
gate...") rather than the actual `washout_blocks_protect` text ("Protect confirmation arrived after
washout armed; do not de-risk late") — meaning `protect_gate.path` was already `None` on all six
before washout is ever consulted, since extension never fully armed. The seventh,
**`2020-03-10`** — the one I'd called "the sharpest example" because `extension_armed=True` there
too — shows the *same* redeploy-side text, not the `washout_blocks_protect` one, meaning some other
condition (long-term uptrend, strength, or divergence) failed there as well.

I searched every v1.0 snapshot for the literal `washout_blocks_protect` action_path. It occurs on
**exactly one day in the entire 2016-2026 record: `2021-11-30`.** That is the only case where a
fully-ready protect gate was actually vetoed by armed washout memory. One confirmed case is real
evidence that the phase-interaction question below is legitimate — it is not evidence that this is
the single best-evidenced finding in this document, and the "7 of 20, best-evidenced" framing is
withdrawn.

## The problem (as it now actually stands, evidenced by one case)

`protect_ready = protect_gate.path is not None and not washout_memory.armed` (`regime.py:3670`).
On `2021-11-30`, protect's own gate had genuinely passed — armed extension, long-term uptrend,
sufficient strength, volatility confirmation, and divergence all cleared — and it still didn't fire,
solely because `washout_memory.armed` was `True` at the time:

```text
2021-11-30  action_path=washout_blocks_protect
  "Protect confirmation arrived after washout armed; do not de-risk late"
```

## Why this is plausibly too blunt, on the evidence that actually supports it

The rule's documented intent (`ALGORITHM_DESIGN.md`) is "late protect evidence cannot override a
valid redeploy transition" — stopping protect from firing *instead of* a redeploy that's actively in
progress. Whether `2021-11-30` is a case of "we're still riding out an active redeploy" or "washout
memory is technically armed but we've moved on to an unrelated situation" isn't something I've
checked — that would require looking at what redeploy episode armed washout memory going into that
date and whether it was still an active, held posture at the time, which I haven't done. The design
question (should this exclusion key off `washout_memory.armed` or off an actively *held* redeploying
posture) is still worth asking, but on one case, not seven.

## Proposed fix (unchanged direction, weaker justification)

Narrow the exclusion from "washout memory is armed" to "a redeploying posture is currently held" —
`r3-proposal.md §2` separately points out a real flaw in my original phrasing of this
(`posture_state != "redeploying"` as a blanket replacement would incorrectly prevent protect from
ever interrupting a *failing* redeploy posture, conflicting with the valid-opposite-action
transition `r2-proposal.md §5` already requires). The proposal's own §7 candidate-resolution design
— compute all raw path predicates independently, then resolve with explicit priority rules that
still allow a valid opposite action to transition a held posture — is the better-specified version
of this idea; see `r3-discussion.md` T11.

## Recommendation

Downgraded from "highest priority, best-evidenced" to "a legitimate design question with one
confirmed supporting case, folded into `r3-proposal.md §7`'s resolution architecture rather than
pursued as a standalone fix." The original mistaken 7-case version of this topic is preserved in
this file's git history for the record; this section now states the corrected finding directly
rather than the withdrawn one. The fix itself should be evaluated as part of the proposal's broader
resolution design, not sequenced ahead of Topics 1-3 the way the original, wrong recommendation said.
