# R4 Code Review: Staged V1.1 Implementation Against r2/r3-proposal.md

**Author:** Claude (Sonnet 5), September 2026.
**Scope:** Review of the staged (uncommitted) git changes implementing the v1.1 candidate —
`src/marketlab/regime_lifecycle.py`, `regime_exposure.py`, `regime_research.py` (new modules),
plus diffs to `regime.py`, `policy.py`, `regime_export.py`, `versions.py` — against the contracts
agreed in [r2-proposal.md](r2-proposal.md), [r2-discussion.md](r2-discussion.md),
[r3-proposal.md](r3-proposal.md), and [r3-discussion.md](r3-discussion.md). Also verifies the
self-reported claims in [implementation-progress.md](implementation-progress.md) and
[implementation-results.md](implementation-results.md) rather than taking them on faith.

**Method:** five parallel code-review passes, each independently checking a scoped set of specific,
named contracts against the actual code (not just structure), plus direct re-execution of the test
suite, lint, and a sample of the empirical claims.

---

## Overall Verdict

Solid, faithful implementation of the agreed architecture. Four of five review areas came back
clean against every contract checked. One review area found a genuine correctness bug with a
specific, traceable impact on part of the reported comparison table — not on the headline economic
conclusion, but on the transmission-gate experiment's ability to cleanly attribute cause. Two minor,
non-blocking notes and one open verification gap round out the findings.

---

## Critical: Transmission Leg (`X`) Does Not Degrade To A Single Available Leg

In `regime_lifecycle.py`'s `setup_readings`:

```python
x = max(b, c) if b is not None and c is not None else None
```

Per the agreed coverage contract (`r2-proposal.md §2`, reaffirmed in `r3-proposal.md §3`), `X`
(breadth/credit transmission) is supposed to be an **alternative pool** — a lower bound provable
from whichever leg is available, not a value that requires every declared leaf present. This line
requires **both** breadth and credit non-missing before computing anything. If credit data is
absent — which `implementation-results.md` itself discloses is true for roughly 74% of the 10-year
sample (only 677 of 2,617 dates have exact OAS evidence) — `X` becomes `None` and the transmission
gate fails outright, even on days where breadth alone would have cleared 0.35.

**This is live in the actual reported comparison table, not a theoretical edge case.** `R2-A` and
`R2-B` both use `transmission=True`. The controlled A/B/C study exists specifically to isolate "does
removing the mandatory transmission requirement matter" by comparing `R2-B` (transmission required)
against `R2-C` (transmission dropped) — the entry-count jump between them (3 washout entries at
`R2-B` → 11 at `R2-C`) is exactly the number this experiment was built to attribute cleanly. With
this bug, part of that jump could be an artifact of missing-OAS-data mishandling rather than a clean
signal about whether the transmission requirement itself matters, since most of the qualifying dates
where `R2-B` fails could be failing for coverage reasons rather than genuine absence of breadth/
credit transmission.

**What this does not affect:** the headline economic conclusion in `implementation-results.md`
(combined v1.1 underperforms both the untimed baseline by 72pp and the exposure-matched control by
24pp). Every configuration from `R2-C` onward already drops the transmission gate in its inherited
chain, so the final reported numbers for `W-opportunity` through `Combined` are not directly
affected by this bug.

**Recommendation:** fix `X` to compute from whichever of breadth/credit washout is actually present
(`None` only when *both* are missing), re-run `R2-A`/`R2-B` specifically, and check whether their
entry counts and the resulting A/B/C attribution change materially before treating that comparison
as clean.

---

## Verified Clean: Evidence And Confirmation Layer

Reviewed `owned_evidence`, `maximum_evidence`, `second_family`, `confirmation_gate`, `funding_veto`
in `regime_lifecycle.py` against 7 contracts. All 7 verified correct:

1. **Monotonicity** — `maximum_evidence` is a pure `max()` over observed leaves; adding a weaker or
   missing reading can never lower a family's score, and `second_family` (a monotone order statistic
   over already-monotone family maxima) preserves this.
2. **Boolean gate pass-through, no `sqrt(1×score)` inflation** — every `sqrt()` call site combines
   two genuinely graded values; final gate resolution treats only `True` as a pass, so an unresolved
   (`None`) dependency can never silently pass as satisfied.
3. **Second-highest-family aggregation** — operates on family-level maxima, not feature-level;
   duplicate leaves within one family are already collapsed before this function sees them.
4. **Coverage semantics (lower bound vs. exact)** — verified at the actual consuming call site, not
   just in isolation: the recovery-check path explicitly requires `exact=True` before allowing a `<`
   test, so a lower-bound-only reading can prove a `>=` gate but is correctly barred from proving a
   recovery (`<`) gate.
5. **`funding_veto`** — three-valued logic matches spec exactly, and an unresolved veto correctly
   blocks raw eligibility downstream rather than defaulting to "clear."
6. **Credit family composition** — `max(HYG/TLT, OAS)` only; NFCI is exclusively routed to a
   separate `liquidity` family, no leakage.
7. **VIX-high/cooling-VVIX pattern preserved** — included as a genuine max-pool candidate in
   volatility's evidence, not dropped by the redesign.

Two non-blocking notes: `maximum_evidence({})` on an empty leaves dict would yield `exact=True` with
a `None` value (no current call site triggers this, but it's a sharp edge for a future caller); and
the VVIX "quiet market" 1.2× deterioration boost is carried forward unchanged from the old code —
worth someone confirming that's an intentional carry-forward rather than an oversight, since it's
the one place in this layer where a hand-tuned multiplier still scales a score outside the
family-max/second-family framework.

---

## Verified Clean: Resolver/Exit Transition Logic (Highest-Risk Function)

Reviewed the main `transition()` function in `regime_lifecycle.py` against 9 contracts from
`r3-proposal.md §7`. All 9 verified correct:

1. **Independent evaluation before resolution** — all four raw path predicates compute
   unconditionally before any consumption/conflict logic runs.
2. **Same-direction priority** — `ACTIONS = ("protect-break", "protect-extension",
   "redeploy-washout", "redeploy-confirm")` and selection preserves this order exactly.
3. **Consumption before conflict resolution** — verified the actual order of operations.
4. **Opposing-direction asymmetry** — traced carefully since this is exactly where my own earlier
   proposed fix (`posture != "redeploying"` as a blanket protect gate) was wrong: same-direction
   candidates are always pre-consumed before `eligible`/`selected` are computed, so a `selected`
   candidate during a held posture can only ever be the *opposite* direction; when both directions
   are simultaneously eligible for new entry, `conflict=True` blocks new entry in either direction,
   but held-posture failure/recovery/timeout still evaluates independently of that conflict; when
   only the opposite direction is eligible (uncontested), it correctly transitions the posture. This
   is the exact asymmetry required, implemented correctly.
5. **No same-bar reentry** — verified via a different but valid mechanism (same-direction candidates
   never reach `eligible` while already held, so there's no path for same-bar reentry).
6. **One entry per episode, no cap reset** — `held["age"]` recomputes from a fixed entry index never
   touched by repeated signals. One item not fully verified in this pass: whether the `consumed`
   flag persists correctly across days through `update_setup` over an episode's full lifetime.
7. **Transition order** — "opposite unused action, then cap, then thesis repair/failure" matches the
   actual `if`/`elif` chain exactly.
8. **`opportunity_completed` unreachable** — confirmed genuinely disabled, not silently wired up.
9. **Unknown action identities are errors** — `action_direction()` raises `ValueError` on any
   unrecognized string, and `policy.py` now routes through it instead of the old silent
   fallback-to-"maintain" pattern.

Other findings: the old `phase_veto` blanket washout-armed exclusion still exists as a
config-toggleable legacy comparison path, but `DEFAULT_CONFIG.phase_veto = False`, so the shipped
default correctly relies on the new resolver rather than the old blanket rule — confirms the
architecture is consistent under the actual default, with old behavior reachable only by
deliberately requesting a comparison variant.

---

## Verified Clean (After Re-Run): Exposure Accounting And Policy/Version Wiring

First review attempt on this area returned a degenerate non-result (the agent appeared to lose
track of its own directive) and had to be relaunched. The re-run checked all 8 contracts from
`r3-proposal.md §9`/`§10` against `regime_exposure.py`, `policy.py`, `regime_export.py`,
`versions.py` — all 8 verified correct:

1. **Next-open execution, overnight owned by old exposure** — the overnight move applies to
   yesterday's pre-rebalance weights before any target/cost logic runs; only then does rebalancing
   to the new target and the intraday open→close move apply.
2. **Adjusted-open formula, no close-price substitution** — `raw open × adjusted-close/raw-close`
   exactly; missing/invalid prices raise a named error rather than substituting a close.
3. **80%/0/20/40% fixed account, 5% ACT/365 financing, 5bp turnover** — `POLICY_POSTURE_EXPOSURES =
   {"protected": 0.8, "neutral": 1.0, "redeploying": 1.2}` and cost/financing constants match
   exactly; financing applies only when levered (negative cash), correctly zero when under-exposed.
4. **Warm-start/slice parity** — correct by construction (each day's return computed identically
   regardless of slice start, only re-based to `nav=1.0`); no explicit automated slice-vs-full-history
   test was found confirming this, worth adding.
5. **Open final holdings not force-closed** — confirmed; diagnostic mark-to-market is computed
   without reporting a synthetic completed exit.
6. **Independent version selectors** — `compute_portfolio_policy_snapshot` now takes distinct
   regime-input, candidate-input, and policy-output version parameters with an explicit guard
   against the old single-shared-string misuse.
7. **Unknown action identity hard-fail** — confirmed via `action_direction()` routing.
8. **`regime_export.py` displays saved state, no reconstruction** — the old
   `_armed_extension_memory_rows`/`_armed_washout_memory_rows` reconstruction-pass functions (the
   root cause of the T2 export bug found in the r3 discussion round) are **deleted outright**, not
   patched around. The replacement reads every persisted field directly off the canonical snapshot.

One minor note: an unreachable-in-practice branch in `policy.py`'s lifecycle-aware posture mapping
raises a plain `KeyError` on an unexpected posture value rather than a custom error — still hard-
fails, consistent with the "must fail clearly" intent, just a less informative error message.

---

## Verified Clean: Empirical Claims

1. **v1.0 preservation** — file count under `data/snapshots/**/eod/v1.0/` matches the claimed 5,386
   exactly; only 4 files are newer than the proposal docs, and all 4 are routine new-trading-day
   additions (2026-09-17/18), not modifications to historical files. The exact SHA256 could not be
   independently reproduced (unknown concatenation method), but nothing contradicts the claim.
2. **Test/lint counts** — `.venv/bin/pytest -q` reproduces exactly **258 passed**;
   `.venv/bin/ruff check src tests` passes clean.
3. **`regime_research.py` isolation** — confirmed genuinely isolated: `ActionConfig` has only
   immutable-type fields (no mutable-default-argument bug class possible), and each comparison
   variant reads only from its own accumulated state list, never another variant's. Only raw market
   observations are shared across variants, which is correct and expected.
4. **Spot-checked table entries** — two claimed redeploy-washout entries (2018-11-02, 2019-08-21)
   were checked directly against canonical `data/snapshots/.../eod/v1.1/regime.json` files and
   matched exactly.
5. **No post-hoc parameter selection evidence** — the frozen specification in
   `implementation-progress.md` contains no date-referencing language that would indicate a
   threshold chosen to hit a specific known historical case.

---

## Open Verification Gap

Whether `derive_regime_postures` (the old v1.0 posture-derivation function) is called from any
**live** v1.1 code path, versus only from v1.0 read-only replay. The evidence available so far
points toward replay-only (it's gated behind `LEGACY_ACTIONS`, and both the resolver and the
version-routing/export reviews came back clean with no sign of dual-maintained state), but no single
review pass directly confirmed this. Worth a direct check — grep for live call sites of
`derive_regime_postures` outside anything explicitly scoped to `snapshot_version="v1.0"` — before
closing this out.

---

## Summary Of Required Follow-Up

1. **Fix the transmission-leg (`X`) coverage bug** in `setup_readings` — required before trusting
   the `R2-A`/`R2-B` rows of the comparison table, and before treating the `R2-B` → `R2-C`
   transmission-removal attribution as clean.
2. **Confirm `derive_regime_postures` is replay-only**, not live-called.
3. Two non-blocking notes worth a follow-up decision, not a blocker: document (or remove) the
   undocumented extension re-arm cooldown (`renewal_ready`), and add an explicit automated test for
   exposure warm-start/slice parity.

None of the above changes the headline result already reported in `implementation-results.md`: the
combined v1.1 candidate does not outperform the untimed baseline or the exposure-matched control.
That conclusion is not an artifact of the bug found here — it survives independent of it, since the
final comparison chain (`R2-C` onward) does not use the affected code path.
