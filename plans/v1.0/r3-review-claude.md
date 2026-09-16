# r2 Implementation Review

**Reviewer:** Claude (Sonnet 4.6), September 2026.
**Scope:** 9 commits implementing `r2-plan-codex.md`:
```
0aa4bfd Version regime artifacts for v1.0
44559fa Expose regime setup context scores
0882273 Add regime correction episode outcomes
aef728c Gate regime protect actions
c042a2d Label regime event volatility context
867af37 Export regime armed setup memory
49c2a0a Add regime posture replay
e5f3192 Add regime redeploy validation outcomes
6ce5207 Mark r2 implementation complete
```

---

## Overall assessment

All 9 plan steps and all 7 done criteria are addressed. The code is well-structured, the
new lifecycle concepts (extension_unwind / regime_break paths, armed memory, posture replay)
are cleanly separated, and the tests are meaningful. I have two notable gaps and several
minor points worth reviewing before running the episode diagnostics seriously.

---

## Critical

None. All gated protect paths work, volatility-only protect is correctly suppressed, and
posture replay has been computed.

---

## Notable

### 1. `event_context` in correction episodes is always "unclassified"

File: `src/marketlab/regime.py`, line 6181.

```python
event_context="unclassified",
```

The plan required: "whether the episode looked ordinary, scheduled-event-driven, or
shock-driven." The `event_context` field exists on `RegimeCorrectionEpisode` and appears
in the formatted table, but the classification is never populated. Every row shows
"unclassified."

The plan also says: "Ordinary corrections and shock events are separate cohorts." This
cohort split is the reason the field exists — without it, the false-alert cluster analysis
conflates COVID-style crashes with ordinary distribution-tail corrections. The plan's
diagnostic intent is only partially satisfied while this classification is missing.

A minimal implementation: classify as `shock` if max drawdown exceeds some threshold (e.g.
15%) within a short window (e.g. 30 trading days); otherwise `ordinary`. A calendar-based
classification (COVID, 2022 rate shock, tariff headlines) would be more accurate but
requires more maintenance. Either is better than a static "unclassified" string.

### 2. Armed memory re-arms indefinitely when extension stays elevated

File: `src/marketlab/regime_export.py`, lines 452-455.

```python
if armed_index is not None and index - armed_index > ARMED_EXTENSION_MAX_AGE_DAYS:
    armed_since = snapshot.source_date  # reset clock
    armed_index = index
    source_strength = setup_score
```

The reset block fires when extension_setup_score stays ≥ 0.60 past 40 days. It resets
`armed_since` and `armed_index` to the current snapshot, which makes `extension_armed_age`
drop back to 0. This behavior is:

- **Invisible in the workbook:** a row that should show age=41 shows age=0, and
  `extension_armed_since` jumps to the current date. A reader sees the market as "just
  now armed" when it has been extended for months.
- **Unbounded:** the 40-day window only applies when the score goes inactive. If extension
  stays elevated, the decay column also resets to 1.0 (fresh armed), making old signals
  look fresh.

The plan says "Keep armed setup alive for a bounded 20-40 trading-day window with decay."
The intent of "bounded" is debatable — the re-arm behavior may be correct market logic
(still vulnerable if still extended) — but the workbook representation is misleading
because it erases the duration of the elevated state.

Suggested fix: track a separate `extension_elevated_since` date (the date the score first
rose above threshold in this run) alongside `extension_armed_since` (the last re-arm date),
so a workbook user can see both "this run started 70 days ago" and "currently active for
the last 5 days since re-arm."

---

## Minor

### 3. `_protect_path_from_reason` parses the action_reason string

File: `src/marketlab/regime.py`, lines 4703-4706.

```python
def _protect_path_from_reason(reason: str) -> str | None:
    for path in ("extension_unwind", "regime_break"):
        if reason.startswith(f"{path} protect"):
            return path
    if "volatility_only_warning" in reason:
        return "volatility_only_warning"
    return None
```

The posture replay extracts the protect path by pattern-matching the action_reason string.
This is fragile: if the reason text changes (e.g., a wording fix in `_protect_gate_result`),
path extraction silently returns None and posture rows show no protect path.

`protect_path` (or `action_path`) should be a first-class field on `RegimeActionState`,
set directly in `derive_regime_action_state()` from `protect_gate.path`. The string parse
is a workaround for not having that field.

### 4. Event-vol context uses market proxies, not a calendar

File: `src/marketlab/regime.py`, `_event_volatility_context()`.

The plan said: "Start simple: allow a small manually maintained event calendar or generated
known-event feed." The implementation instead uses VIX9D/VIX ratio and VIX9D/VIX 5d change
as market-signal proxies for near-term event premium. This is pragmatically better — no
calendar to maintain — but it has two gaps:

1. It only detects VIX front-end elevation. Payrolls, FOMC, and major expirations affect
   the VIX term structure; tariff announcements or earnings do not, and the proxy would
   miss those.
2. The label `near_term_event_premium` appears in the snapshot read, but it does not
   change whether protect fires. When there is non-vol confirmation alongside event premium,
   the label is `near_term_event_premium_with_confirmation` and protect can still fire
   normally. This is probably the right first-implementation choice, but should be noted
   so episode diagnostics can later check whether those signals are noisier than average.

No code change required, but the deviation from the plan should be documented so the episode
review can assess whether the proxy identifies the right dates.

### 5. Two separate threshold constants for the same "armed" cutoff

`CORRECTION_EPISODE_ARMED_SETUP_THRESHOLD = 0.60` is defined in `regime.py` and used by
`_first_armed_setup_date()` to determine whether a snapshot counts as "armed" for episode
diagnostics.

`ARMED_EXTENSION_SETUP_THRESHOLD = 0.60` is defined in `regime_export.py` and used by
`_armed_extension_memory_rows()` for the workbook armed columns.

Both values are 0.60 today. If one is tuned without updating the other, the workbook and
the episode table will disagree on which days were armed. They should share a single
constant (export can import from regime, or both can import from a shared location).

### 6. Volatility-only warning has a strength threshold that can suppress the label

File: `src/marketlab/regime.py`, lines 3135-3138.

```python
warning_only = volatility_only and (
    extension_strength >= ACTION_STRENGTH_THRESHOLD
    or regime_break_strength >= ACTION_STRENGTH_THRESHOLD
)
```

`volatility_only` is true when `confirming_families == ("volatility",)`. But if the
volatility family barely clears ACTION_CONFIRMATION_THRESHOLD (0.35) while both
extension_strength and regime_break_strength are below ACTION_STRENGTH_THRESHOLD (0.55),
the condition is `True and False = False` — neither protect nor warning fires. A mild vol
deterioration spike without breadth/credit/liquidity support generates no visible output,
not even a warning label.

This is a design choice (low-confidence vol signals should be noise) but it means
`event_volatility_context == "none"` can be ambiguous: either no vol deterioration or vol
deterioration below warning strength. Worth confirming this is intentional; otherwise add a
"volatility_below_threshold" context value.

### 7. Posture age uses snapshot index, not calendar days

File: `src/marketlab/regime.py`, `derive_regime_postures()`.

```python
posture_age = index - posture_start_index if posture_start_index is not None else None
```

`PROTECTED_POSTURE_MAX_AGE_DAYS = 65` is compared against this index difference. If the
snapshot series has trading-day gaps (holiday weeks, data gaps), the index count
understates calendar days slightly. For typical usage (≈252 trading days per 365 calendar
days) over 65 days, the difference is small (~20 calendar days). But a 2-week gap in
snapshot history would extend a protected posture by ~10 extra trading days before timeout.
Low severity; document that age is in snapshot indices, not calendar days.

### 8. `washout_setup_score` is the full aggregate, not a washout-specific split

Commit 44559fa computes `washout_setup_score` as:

```python
washout_setup_score = _aggregate_pressure_score(modules, field_name="washout_score")
```

This aggregates all modules' washout scores identically to `washout_pressure_score`. The
existing washout_pressure_score is then set to the same value. So `washout_setup` is not
split to a specific subset of modules the way `extension_setup` (trend_extension +
vol_complacency) and `fragility_context` (breadth + credit + liquidity + yield_curve) are.

This may be intentional — washout signals are already relatively specific per module — but
the plan's vocabulary entry for `washout_setup` implies a distinct concept worth naming
separately. At minimum, the equivalence should be documented so a future split can be done
cleanly.

---

## Done criteria check

| Criterion | Status |
| --- | --- |
| Snapshot explains extension_unwind / regime_break / warning-only | ✓ action_reason includes path + families |
| Volatility-only deterioration does not produce normal protect | ✓ implemented in `_protect_gate_result` |
| Outcome reports include correction episodes, signal clusters, late signals, false alerts | Partial — episodes ✓; false-alert cluster report for each path is implicit in the episode "timing" column, not an explicit cluster table |
| Workbook includes setup, confirmation, action, posture fields | ✓ all columns present |
| Posture replay computed: episodes reconstructed with explicit resets and outcomes visible | ✓ `compute_regime_posture_outcomes` + `--by posture` CLI path |
| Human can audit a protect signal without reading code | ✓ action_reason, path, confirming families in snapshot read |
| Design improves conceptual consistency before threshold tuning | ✓ |

The one partial: the plan listed "false-alert clusters" as a required outcome report
element ("for each protect cluster, report path, 40d drawdown, whether confirmation was
volatility-only..."). The current `--by episode` output shows timing per correction episode
(protect fired before/after first -3%/-5%, or not at all) and the `--by action` output
shows forward return averages by action state. But there is no explicit cluster report
grouping consecutive protect days into a cluster and reporting 40d drawdown presence per
cluster. This is the most actionable diagnostic for assessing false-alert rate. Consider
adding a `--by cluster` mode to `regime outcomes`.

---

## Summary

**Notable (should fix before running diagnostic conclusions):**
1. `event_context` is always "unclassified" — episode cohort split is required for the
   plan's anti-overfit evaluation.
2. Armed memory re-arms silently — workbook will mislead a reader reviewing long extension
   runs.

**Minor (can fix incrementally):**
3. `_protect_path_from_reason` string parse is fragile; add `protect_path` as a typed field.
4. Event-vol proxy deviation from plan: document and track which episodes it flags.
5. Duplicate armed threshold constants in regime.py and regime_export.py.
6. Vol-warning suppression when below strength threshold — confirm intentional or add label.
7. Posture age in snapshot indices — document units.
8. washout_setup_score not split from the full washout aggregate — document or split.

**Missing from done criteria:**
- False-alert cluster report (explicit per-protect-cluster table with 40d drawdown) —
  consider `regime outcomes --by cluster` before drawing v1.0 diagnostic conclusions.
