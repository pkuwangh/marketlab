# V1.0 Backtest Investigation

**Author:** Claude (Sonnet 5), September 2026.
**Scope:** A fresh empirical pass over `workbooks/outcomes-action-v1.0.txt` and
`workbooks/regime-v1.0.csv`, cross-referenced against `data/snapshots/regime/market/*/eod/v1.0/`,
requested ahead of implementing the [r2-proposal.md](r2-proposal.md) correctness repairs. This is
not a repeat of the mechanism-correctness review in [r1-discussion.md](r1-discussion.md) — it asks
a different question: independent of whether the code is internally correct, **how much of the
market's real behavior does the v1.0 model actually see**, and where does it look in the wrong
place or too rarely?

**Method note on independence:** every "turning point" in this document is derived purely from
`SPY_close` in `regime-v1.0.csv` using a price-only zigzag algorithm (detailed in §3) — not from the
model's own `action_state`, `regime`, or any other model output. This avoids the circularity of
using the model's own labels to judge the model. All action/state columns were read from the
`v1.0`-labeled rows only, since a prior research note in this same `plans/v1.1/` folder
([r1-debug-claude.md](r1-debug-claude.md)) was corrected after conflating the local DuckDB store's
stale v0.0 rows with v1.0 — a mistake worth restating here so it isn't repeated.

---

## 1. Is 8 events in 10 years actually too quiet, and are the forward returns bad?

`workbooks/outcomes-action-v1.0.txt` shows 2,617 trading days, 97.9% `no_change`, and forward
returns for the two action states that mostly trail or barely beat the `baseline:all_days` row at
20/40/65 sessions. Two independent facts explain most of this, not just conservative thresholds:

- **Most real market turns don't clear the model's full gate chain at all**, not because the
  thresholds are miscalibrated but because the *prerequisite conditions* (an armed extension setup
  for protect, an armed washout setup for redeploy) frequently never occur before or during a real
  turn. Section 3 and 4 below quantify this precisely: only 2 of 25 independently-identified market
  tops over 2016-2026 produced a genuinely well-timed protect call, and only 9 of 26 independently-
  identified market bottoms produced a redeploy call. The system isn't quiet because it's cautious
  about acting on borderline evidence — it's quiet because the two-stage setup-then-confirm
  lifecycle structurally requires a *specific kind* of turn (a prior extended/complacent stretch for
  protect, a sharp volatility-spike capitulation for redeploy), and most real turns aren't that kind.
- **A meaningful share of the events that did fire are false alarms**, which drags the average
  forward return down even though the well-timed events look good in isolation. Section 3 below
  classifies the 13-14 protect events into hits, early-but-correct calls, and false alarms; roughly
  half are false alarms by a fairly generous standard (no real 6%+ correction followed within a
  reasonable window).

So "too quiet and not great forward returns" are the same underlying problem seen from two ends:
the model is quiet because its gates are narrow, and the returns are mediocre because a meaningful
fraction of what does fire is timing-unrelated to any real subsequent move. Loosening thresholds
without addressing *which* real turns the gates structurally cannot see (Sections 3-4) would likely
make both numbers worse, not better — more false alarms without necessarily catching more real
turns, since the false alarms and the missed turns come from different mechanisms.

---

## 2. Beyond "redeploy after a major correction": what else could scale-up capture?

The parallel to protect's two-path structure (extension turning bad, or the market outright
breaking) is a good frame, and Section 4 below shows exactly which real bottoms the current
single washout-capitulation path structurally cannot see: **17 of 26 real bottoms never armed
washout at all**, and among those, the largest specific failure mode (5 of the 17) shows
`stabilization is visible, but washout setup is not armed` — meaning the market visibly turned up
and the model's own confirmation machinery agreed, but there was never a capitulation-style setup
to confirm *into*. That's not a threshold problem; it's a missing entry path.

Four candidate paths, in rough order of how directly they're supported by what Section 4 found:

1. **Broad stabilization without a prior deep washout** (most directly supported by the data). Mirror
   protect's `extension_unwind` vs `regime_break` split on the redeploy side: keep the existing
   washout-capitulation path (fast, VIX-spike-led, good at V-shaped panics per the Aug 2024/April
   2025/COVID hits below) and add a second path keyed on broad, multi-family stabilization evidence
   *without* requiring an armed washout memory first — essentially the redeploy-side mirror of
   `regime_break`. This is exactly what the 2019-06, 2020-06, 2022-01, 2022-10, and 2023-03 misses
   in Section 4 have in common: stabilization confirmed, no armed setup to attach it to. This is the
   same direction as the transmission experiment already scoped in
   [r2-proposal.md §7](r2-proposal.md), but broader — that experiment relaxes *one* gate (breadth/
   credit transmission) within the existing single path; this proposes a genuinely second path with
   its own (looser, but still gated) requirements, the same way protect has two.
2. **Credit-led re-risk without an index-level drawdown.** A mid-cycle case where HYG/TLT and OAS
   broadly improve, breadth participation is expanding, and volatility is already calm — i.e. the
   market resuming a risk-on trend after a shallow pause rather than recovering from a real
   correction. This wasn't directly evidenced in Section 4 (all 26 identified bottoms follow a real
   6%+ local decline, since that's how they were found), but it's a plausible instrument-appropriate
   opportunity family the current design doesn't attempt to detect at all, since both protect and
   redeploy are framed entirely around index-level stretch/washout.
3. **Breadth-thrust / follow-through confirmation**, independent of how washed out the prior decline
   was — a classic technical pattern (broad, high-participation rally shortly off a low) that could
   serve as a *third*, purely confirmation-driven trigger layered on top of whichever setup (or no
   setup) preceded it. This overlaps meaningfully with proposal 1 above; I'd treat 1 and 3 as the
   same underlying idea (broad participation confirming a turn) rather than two separate paths.
4. **Volatility-regime normalization without a large drawdown** (VIX easing from a moderately
   elevated-but-not-extreme level, with confirming breadth) — a smaller, more speculative fourth
   idea; I don't have direct evidence for it from this pass and would treat it as lower priority than
   1-3.

I'd sequence 1 first: it has the clearest data support, the clearest mirror to a pattern (protect's
two-path structure) the project has already built and reasoned about, and it directly explains the
single largest missed-bottom category found below. It should be scoped as its own setup/confirm/
action path with its own gates — not as a further loosening of the existing washout path's
transmission requirement, which the transmission experiment already covers separately.

---

## 3. Should protect's two cases be separated downstream, in the action itself?

Short answer: the data says the more urgent problem is upstream of that question. I looked for how
often `regime_break` evidence (the "market is fragile/breaking" case) appears at all, expecting it
to be the dominant reason for missed tops given the parallel the question draws. It isn't:

```text
"regime_break" appears in action_reason on only 15 of 2,617 days (0.6%) across all of 2016-2026,
and only 2 of those 15 coincide with an independently-identified major turning point
(2018-12-21/24, which is the trough of the Dec 2018 correction, not a top; and 2023-03-13, the SVB
bottom). Zero of the 15 coincide with one of the 25 independently-identified tops.
```

`regime_break` is rare and, when it fires, tends to cluster with *bottoms* (broad deterioration
that's already reached a trough), not with the tops the "market breaking" framing suggests. So
separating `extension_unwind` from `regime_break` further downstream wouldn't have caught more of
the missed tops in Section 4 below — `regime_break` essentially never overlaps with them in the
first place.

**The actual dominant cause of missed protect calls at real tops is phase-exclusivity, not the
extension_unwind/regime_break split.** Of the 20 clean misses found in Section 4 (excluding 2 hits
and 3 tops immediately superseded by a fast crash into a redeploy signal), **7 were blocked because
`washout_memory.armed` was `True` at the time** — i.e. `protect_ready = protect_gate.path is not
None and not washout_memory.armed` (`regime.py:3670`) suppressed protect evaluation entirely,
independent of whether protect's own gates would have passed. In one case (2020-02-19, the COVID
top) `extension_armed` was also `True` at the same time — the setup for protect was fully armed, and
protect still couldn't fire, purely because washout memory from an earlier, unrelated bottom hadn't
decayed yet.

This is worth treating as the higher-priority question over the extension_unwind/regime_break split:
**should washout memory being armed suppress protect evaluation entirely, or only block the final
protect *action* (letting the model still report what protect would have said)?** The original
design intent for phase-exclusivity (documented in `ALGORITHM_DESIGN.md`) was "late protect evidence
cannot override a valid redeploy transition" — preventing protect from firing *instead of* a
redeploy that's actively in progress. But 7 of 20 misses show this rule also suppressing protect at
a *later, independent* top, after the redeploy episode that armed washout memory has nothing to do
with the new top. The 15-session washout grace window is long enough that a completely separate
market top can fall inside it.

I'd frame this as two separable questions rather than one:

1. **(Higher priority, more directly evidenced) Should phase-exclusivity block protect *evaluation*,
   or only block it from *overriding an active redeploy posture*?** If washout memory is armed but
   there's no *currently held* redeploying posture (e.g., the prior redeploy episode already timed
   out or the market has since made a new high), there's no active redeploy call left to protect
   from overriding — so evaluating and reporting protect diagnostics in that window seems safe, even
   if the actual action-firing rule keeps its current suppression. This would at minimum surface the
   near-miss for reporting, and is worth testing as an actual action-eligibility relaxation once
   [r2-proposal.md §5](r2-proposal.md)'s posture engine is wired in and can distinguish "washout
   memory is armed" from "we are currently holding a redeploying posture."
2. **(Lower priority given the 15-vs-0-of-25-tops finding above) Whether to promote `regime_break`
   into a distinct, separately-actionable state.** Given how rarely it fires and how little it
   overlaps with real tops in this sample, I would not prioritize this over item 1 — there isn't
   enough evidence here that `regime_break`'s current warning-only treatment is costing missed
   protect calls, whereas phase-exclusivity demonstrably is.

---

## 4. Turning-point cross-reference: methodology, misses, and mismarks

### Methodology

Independent turning points were found with a standard zigzag algorithm on `SPY_close` from
`regime-v1.0.csv`, using a 6% minimum swing threshold (chosen because it's below the project's usual
8-10% "major correction" bar, so it also surfaces the kind of local turn — SVB, the Aug-Oct 2023
correction, the 2019 mini-corrections — that a pure "8% drawdown from an all-time-high" method
merges into one long multi-year episode; a straight running-maximum-drawdown pass over the same data
found only 9 corrections over 2016-2026, because it can't see local turns inside a still-underwater
multi-year period like 2022-2023). This produced **51 pivots: 25 tops (H) and 26 bottoms (L)** across
2016-01 through 2026-06.

For each pivot, I pulled a window from `regime-v1.0.csv` (peak/trough date ±5 to +20 trading
sessions) and checked: did a matching action fire in that window, and if not, what was
`extension_armed`/`washout_armed`/`protect_strength`/`redeploy_strength` and the `action_reason`
text on the day of peak strength in that window.

### 4.a Missed tops (protect)

Of 25 independently-identified tops:

| Outcome | Count | Examples |
| --- | --- | --- |
| Clean, well-timed hit | 4 | 2019-05-07 (dist 2 sessions from the 2019-05-03 top), 2020-01-24 to 01-31 cluster (COVID top), 2023-02-09/10, 2024-07-10 |
| Early but directionally correct (real drawdown followed, just not aligned to a discrete local pivot) | 3 | 2019-12-03, 2020-01-03 (both pre-COVID), 2021-11-11 to 11-29 (ahead of the Jan 2022 top) |
| Top immediately superseded by a fast crash into a redeploy call before any protect window closed | 3 | 2020-03-13, 2024-07-16 (double-counted with the 2024-07-10 hit above — same episode), 2025-04-09 |
| Clean miss, no signal of any kind | 20 (of which 7 specifically phase-blocked, 1 `volatility_only_warning`, 9 never armed, 3 armed-but-unconfirmed) | see breakdown below |

Breakdown of the 20 clean misses by cause:

- **7 blocked by `washout_memory.armed == True`** (phase-exclusivity; discussed in Section 3):
  2016-01-05, 2018-03-09, 2018-11-07, 2018-12-03, 2020-02-19, 2022-02-09, 2022-03-29.
- **1 blocked by the volatility-only rule** (working as designed, but still a miss): 2018-01-26 —
  `volatility_only_warning: volatility deterioration is visible, but normal protect requires non-vol
  confirmation`.
- **9 where extension never armed at all** (no stretch/complacency pattern preceded the top, so the
  setup precondition was never met): 2018-09-20, 2020-06-08, 2020-09-02, 2020-10-12, 2022-01-03,
  2022-06-02, 2022-08-16, 2025-02-19, 2026-01-27. Five of these are 2022 interim tops (Jan, Jun, Aug)
  — consistent with 2022 being a grinding, multi-leg decline that never re-extended between legs, the
  same underlying market character that Section 4.a's redeploy side and the earlier
  [r1-debug-claude.md](r1-debug-claude.md) investigation identified as a structural blind spot for
  washout.
- **3 where extension armed successfully but confirmation never arrived before the arming window
  decayed**: 2022-11-30, 2023-07-31, 2026-06-01 — the setup/confirm split working exactly as
  designed (setup existing without action isn't a bug), but still a real top the model had no
  further evidence about once the arm window lapsed.

### 4.b Missed and mismarked bottoms (redeploy)

Of 26 independently-identified bottoms, 9 produced a matching redeploy call
(2016-02-11, 2018-12-24, 2019-08-05, 2020-03-12/23, 2022-03-08, 2024-08-05, 2025-04-08/21 — several
of these share one episode). Of the 17 misses:

- **5 where stabilization confirmed but washout never armed** (the largest category, and the
  strongest evidence for the new path proposed in Section 2): 2019-06-03, 2020-06-11, 2022-01-27,
  2022-10-12, 2023-03-13. `action_reason` text is explicit on each: *"Stabilization is visible, but
  washout setup is not armed."* This is the model's own confirmation machinery agreeing the market
  had turned, with no setup to attach that agreement to.
- **3 where washout armed but stabilization confirmation stayed below its gate**: 2018-02-08,
  2018-04-02, 2018-11-23.
- **2 very close misses where setup and confirmation both passed but the strength gate (0.55) alone
  blocked the call**: 2018-10-29, 2026-03-30.
- **1 where setup pressure existed but never accumulated enough persistence/single-snapshot strength
  to arm**: 2023-10-27.
- **5 with no signal of any kind, neither setup nor confirmation**: 2020-09-23, 2020-10-30,
  2022-05-19, 2022-06-16, 2022-12-28. Three of these (May/Jun/Dec 2022) sit inside the same 2022
  grinding decline identified above.
- **1 unaccounted for in the strict recount** (rounding in clustering, not a distinct new case).

### 4.b (continued) Mismarked actions — protect/redeploy calls far from any real turning point

I measured, for every fired protect/redeploy row, its distance in trading sessions to the nearest
independently-identified pivot of the matching type. Distance alone isn't a reliable false-alarm
signal on its own — three clusters that are 27-35 sessions from the nearest discrete pivot
(2019-12-03, 2020-01-03, 2021-11-11 to 11-29) turn out to be early-but-genuine warnings once
cross-checked against whether a real drawdown followed (they're the "early but correct" row in the
table above) — so the classification below combines distance with the previously-computed cluster
outcome data from `workbooks/outcomes-protect-v1.0.txt`:

| Classification | Count (of ~13 protect clusters) | Clusters |
| --- | --- | --- |
| Hit | 4 | 2019-05-07, 2020-01-24 to 01-31, 2023-02-09/10, 2024-07-10 |
| Early but correct | 3 | 2019-12-03, 2020-01-03, 2021-11-11 to 11-29 |
| Clean false alarm (far from any pivot, no real drawdown followed) | 6 | 2016-04-05 to 04-08, 2019-11-19, 2023-04-25/26, 2023-06-22/26, 2024-01-04/05, 2025-08-04 |

The 2024-01-04/05 cluster is the most extreme mismark in the sample: 109-110 trading sessions (about
five and a half months) from the nearest 6%+ top, with SPY up 11.5% and essentially no drawdown
(0.0%) over the following 65 sessions. On the redeploy side, only one cluster is a clear mismark by
the same test: **2021-12-08/10**, 32-34 sessions from the nearest bottom, with a -10.9% 65-day
forward return — a redeploy call into a market that kept falling for two more months before the
real Jan-Oct 2022 decline. This matches the false positive already identified in
[r1-review-claude.md](r1-review-claude.md) and [r1-debug-claude.md](r1-debug-claude.md).

---

## 5. Summary and how this fits the v1.1 plan

None of this changes the correctness fixes already agreed in
[r2-proposal.md](r2-proposal.md) — nothing here found a bug in what's implemented; it's a coverage
and design-scope question about what the setup/confirm lifecycle can structurally see, layered on
top of the mechanism review already done. Three concrete additions worth folding into the v1.1
backlog, roughly in priority order:

1. **Investigate loosening phase-exclusivity from "washout memory armed" to "an active redeploying
   posture is held"** (Section 3), once the posture engine from `r2-proposal.md §5` exists to make
   that distinction. This is the best-evidenced single change here — 7 of 20 clean protect misses
   trace directly to it, including one (2020-02-19) where protect's own setup was fully armed and
   still couldn't fire.
2. **Design a second, broad-stabilization redeploy path**, mirroring protect's `extension_unwind`/
   `regime_break` structure, gated independently of washout-memory arming (Section 2). This is
   distinct from and broader than the existing transmission-relaxation experiment in
   `r2-proposal.md §7` — that experiment loosens one gate inside the existing path; this proposes a
   second path with its own gates, motivated directly by the 5-of-17 "stabilization confirmed, no
   setup to attach to" miss category in Section 4.b.
3. **Treat 2022 explicitly as its own cohort in the shock/ordinary evaluation split** already planned
   in `r2-proposal.md §8` — five of the nine "no signal of any kind" misses (both protect and
   redeploy) fall inside the 2022 grinding decline, reinforcing the [r1-debug-claude.md](r1-debug-claude.md)
   finding that this specific market character (multi-leg decline, no single sharp capitulation or
   extension) is a structural blind spot distinct from ordinary corrections and shocks alike.

I did not find evidence supporting a downstream split of protect's two paths (Section 3) as a
priority item — `regime_break` is too rare and too poorly aligned with real tops in this sample to
be the explanation for the missed-top pattern; phase-exclusivity is.
