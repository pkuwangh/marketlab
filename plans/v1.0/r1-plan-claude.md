# v1 Improvement Plan

**Prepared:** September 2026. Based on ALGORITHM_DESIGN.md, IMPLEMENTATION_DESIGN.md,
v1-ideas-chatgpt.md, full code review of `regime.py`, and direct analysis of
`workbooks/regime.csv` (2617 snapshots, 2016-01-04 to 2026-06-01).

---

## Empirical starting point

Before proposing changes, these are the numbers to beat:

| Bucket | 20d SPY | 40d SPY | 20d drawdown | 40d drawdown |
|---|---|---|---|---|
| All days (baseline) | +1.3% | +2.5% | -2.5% | -3.5% |
| `scale_down_protect` (88 days) | +1.8% | +2.8% | -2.5% | -4.0% |
| `scale_up_redeploy` (48 days) | +5.0% | +9.3% | -4.0% | -4.6% |
| Stretch p90 (241 days) | +1.0% | +2.3% | -1.7% | -2.4% |
| Washout p95 (154 days) | +2.7% | +5.4% | -4.9% | -6.0% |

Key observations:
- **Protect fires 88 times and produces essentially baseline forward returns.** It is a false
  positive generator, not a correction warning. Forward drawdown at 40d (-4.0%) is actually
  *worse* than baseline (-3.5%), meaning protect tends to fire as the market softens but
  before any serious damage, which then recovers.
- **Redeploy is working well.** 40d returns of +9.3% (SPY) and +12.1% (QQQ) are 3-4x
  baseline. The washout pressure percentiles confirm this — p95 washout gives +5.4% / +8.6%
  at 40d/65d, with higher drawdown risk (expected, since washout follows real stress).
- **High stretch pressure has no return premium.** p90 stretch at 40d (+2.3%) matches baseline
  (+2.5%). The stretch signal in the current form is measuring momentum, which has a positive
  carry, not extension with imminent risk. This is the core design flaw in protect.
- **Protect stretch is weak by construction.** Mean stretch pressure on protect days is 0.49.
  47 of 88 protect days had stretch below 0.49 (below the empirical p90). The geometric
  mean `sqrt(stretch * deterioration)` is letting strong deterioration compensate for weak
  setup routinely.
- **Risk-off regime has surprisingly strong forward returns** (+2.4% 20d, +5.7% 40d) — much
  better than risk_on (+0.9% / +1.8%). This is not a bug; it reflects mean reversion after
  stress. But it means the regime score alone is not a de-risk signal either.

---

## What the ChatGPT plan got right

v1-ideas-chatgpt.md correctly identifies the core structural problems and the right remedies:

1. Splitting `stretch_pressure` into `extension_setup` (trend extension + vol complacency only)
   and `fragility_context` (breadth, credit, liquidity weakness) is the correct separation.
   The breadth/credit/liquidity features in the current `stretch_pressure` score are fragility
   indicators, not extension indicators. They should be confirmation context, not setup.

2. Two protect paths (extension-unwind and regime-break) are the right architecture. Some
   corrections have no prior extension (6 of 14 non-COVID corrections per the analysis). A
   single path cannot handle both cases cleanly.

3. Hard gates replacing the geometric mean is the right fix. The `sqrt(stretch * deterioration)`
   formula is the mechanism that lets 47/88 protect days fire with sub-p90 stretch.

4. Volatility-only protect is empirically invalidated (9/10 vol-only clusters had no 5%
   drawdown in 40d) and the event-volatility flag is the right treatment.

5. Armed setup state with decay is necessary to catch the 2018 Q4 pattern (extension Aug,
   deterioration Oct) that the current same-day requirement misses.

---

## Where I disagree or see gaps

### 1. Redeploy does not need redesign — it needs protection from scope creep

The ChatGPT plan wisely says "leave redeploy largely unchanged." I want to be more explicit
about why: the washout signal is demonstrably working. The washout pressure at p95 gives +8.6%
SPY at 65d vs +4.1% baseline. The 48 redeploy days give +9.3% / +11.9% at 40d/65d.

The main risk in v1 is breaking redeploy while fixing protect. The redesign should
explicitly preserve the washout pressure calculation and the redeploy action path, making
only minimal changes:
- Add stabilization-confirmation gate (already partially present, keep).
- Add the severe-funding-stress block (already in code, keep).
- The redeploy path should not be forced through any new "armed setup" gate — washout is
  itself the setup; the confirmation is already the stabilization evidence.

### 2. The `fragility_context` separation is more important than the armed-state mechanism

The ChatGPT plan presents armed-state memory and the fragility split roughly equally. Based
on the data, the fragility split is more valuable. Here's why:

The 8 protect clusters that fired after SPY was already >5% below trailing 40d high all had
weak trend-extension and vol-complacency but still had breadth/credit/liquidity weakness
contributing to their "stretch" score. If we strip breadth/credit/liquidity out of the
extension_setup score, most of these late-fire protect days would fail the setup gate before
we even need a time-decay mechanism.

Priority: fix what's counted in extension_setup *first*, then layer on armed-state memory.

### 3. Multi-family confirmation gate needs a concrete minimum rule, not just "breadth"

Both plans correctly say volatility-only protect should be blocked. But "require at least
two families" is not enough — consider two weak volatility sub-signals (VIX + VVIX) counting
as two families. The rule needs to be explicit:

> For normal protect to fire, at least one non-volatility internal family must confirm:
> breadth (RSP/SPY, IWM/SPY, or S&P500 breadth) OR credit (HYG/TLT or HY OAS) OR
> liquidity (NFCI), and volatility alone cannot satisfy the confirmation requirement even
> if both VIX and VVIX confirm.

For the regime-break path, require trend damage (SPY below 50d MA, or recent return < −5%)
plus at least one of volatility/breadth/credit.

### 4. The regime score itself needs a separate check

The current headline regime (`risk_on` / `neutral` / `risk_off`) is a 4-component score from
trend, volatility, breadth, and credit price proxies. The `risk_off` regime has the *best*
forward returns (+5.7% / +7.2% at 40d/65d) because it catches washed-out conditions that then
mean-revert. This is a feature for redeploy, but it means the headline regime is not useful
as a standalone de-risk signal — which the design already says. But it also means that
`scale_down_protect` firing in a `risk_on` regime without prior extension is a near-certain
false positive. Consider gating regime-break protect to require at minimum a `neutral` or
`risk_off` headline regime.

### 5. Correction coverage must be the primary evaluation metric, not forward returns

The current outcome replay focuses on average forward returns (SPY 20d/40d). This is the
wrong primary metric for a protect signal. What matters is:

- How many ≥5% SPY corrections had a protect signal ≥1 trading day before the first -5%
  crossing (or within 20/40 days of the peak)?
- What is the false-alert rate (protect fired, no ≥5% drawdown within 40d)?

The current protect false-alert rate is approximately 32/42 cluster-deduplicated events
(~76%). That is the headline failure, not the mean return. Before declaring v1 an improvement,
the episode-level correction coverage table needs to be built and used as the pass/fail gate.

### 6. Stateful posture replay is a prerequisite for real backtesting, not a later feature

The current action-event table treats each day independently. A protected state should
persist until redeploy fires. Without this, we cannot measure the actual portfolio cost
of false positives (opportunity cost of being defensive when the market keeps rising) or the
actual benefit of true positives (avoided drawdown during protection). This should be built
alongside the protect redesign, not after.

---

## v1 Implementation Plan

### Phase 1: Separate extension_setup from fragility_context

**Goal:** Clean up what stretch_pressure measures so the protect setup gate is meaningful.

**Changes to `regime.py`:**

1. Split `PRESSURE_FEATURE_SPECS` into two logical groups:
   - `extension_setup_features`: `spy_return_20d`, `spy_return_60d`, `qqq_return_20d`,
     `spy_ma50_distance`, `qqq_ma50_distance`, `spy_realized_vol_20d`, `vix_close`,
     `vvix_close`, `vix9d_vix_ratio`, `vix_vix3m_ratio`.
     (Pure extension and complacency — high means the tape is stretched.)
   - `fragility_context_features`: `rsp_spy_relative_20d`, `iwm_spy_relative_20d`,
     `sp500_above_50d`, `sp500_above_200d`, `hyg_tlt_relative_20d`, `credit_spread`,
     `financial_conditions`.
     (Internal weakness — high means the tape is fragile/deteriorating inside.)
   - `yield_curve` stays in its own category (only contributes stretch, not washout).

2. Compute two separate scores: `extension_setup_score` and `fragility_context_score`, in
   addition to the existing unified `stretch_pressure_score` and `washout_pressure_score`.

3. The washout score does not change — it continues to pull from all features with
   `high_washout` modes, which naturally includes breadth/credit/liquidity weakness.

4. Write both new scores into `RegimePressureSnapshot` and the snapshot JSON. Keep the
   existing `stretch_pressure_score` for backwards compatibility during transition.

**Validation:** Re-run the pressure outcomes bucketed by `extension_setup_score` vs
`fragility_context_score`. Extension-only p90 should show lower average stretch values
than the current stretch p90, and the cohort of protect days with sub-p90 extension
should shrink materially.

---

### Phase 2: Add armed setup state with decay

**Goal:** Allow setup and confirmation to occur on different days, as in the 2018 Q4 pattern.

**Changes to `regime.py`:**

1. Add `compute_regime_armed_state(snapshot, prior_snapshots)` that:
   - Sets `armed = True` when `extension_setup_score >= p90_threshold` (rolling percentile,
     not fixed, initialized from the trailing 252-day window).
   - Maintains the armed state for up to 40 trading days with linear decay (1.0 at trigger,
     0.0 at 40 days, contributing a weighted setup signal for protect).
   - Resets armed state if extension_setup falls back below p50 (meaning the extension
     genuinely unwound, not a correction setup).

2. The armed state requires reading prior snapshots during snapshot computation. The backfill
   path already has access to prior history; the daily snapshot path needs the trailing 40
   saved snapshots available.

3. The armed state value (0.0 to 1.0 decayed) becomes the `extension_setup_score` input to
   the hard-gate protect logic, not just the current-day extension score.

**Note:** Armed state is only needed for Path 1 (extension-unwind protect). Path 2
(regime-break) does not use it.

---

### Phase 3: Replace geometric mean with hard gates

**Goal:** Prevent strong deterioration from compensating for weak setup.

**Changes to `derive_regime_action_state()` in `regime.py`:**

Replace:
```python
protect_strength = math.sqrt(stretch_setup_score * deterioration_score)
```

With two explicit paths:

```python
# Path 1: extension-unwind protect
# Requires armed setup AND broad multi-family confirmation (non-vol required)
extension_gate = armed_setup_score >= EXTENSION_SETUP_GATE_THRESHOLD  # ~p90
non_vol_confirmation = _non_vol_deterioration_score(action_modules)
broad_confirmation_gate = (
    non_vol_confirmation >= BROAD_CONFIRMATION_THRESHOLD
    and _active_deterioration_family_count(action_modules, exclude_volatility=True) >= 1
)
extension_protect_strength = (
    (armed_setup_score + deterioration_score) / 2.0
    if extension_gate and broad_confirmation_gate
    else 0.0
)

# Path 2: regime-break protect
# Requires no prior setup, but requires trend damage plus a second internal family
trend_damage_gate = _trend_damage_score(snapshot) >= TREND_DAMAGE_THRESHOLD
regime_break_confirmation = (
    _active_deterioration_family_count(action_modules) >= 2
    and trend_damage_gate
)
regime_break_protect_strength = (
    deterioration_score
    if regime_break_confirmation
    else 0.0
)

protect_strength = max(extension_protect_strength, regime_break_protect_strength)
```

The `ACTION_STRENGTH_THRESHOLD` may need recalibration after gates are added, since
strength scores will be zero when gates fail rather than small non-zero values.

---

### Phase 4: Event volatility flag

**Goal:** Prevent scheduled-event premium from masquerading as broad deterioration.

**Changes:**
1. Add a `macro_event_calendar.py` module with a simple hardcoded list of known FOMC, CPI,
   payrolls, and major expiration dates. Keep it minimal — just the dates, no external API.

2. In `derive_regime_action_state()`, check whether `source_date` falls within 1 trading day
   of a known macro event. If so, set `event_vol_context = True`.

3. When `event_vol_context = True`, require non-volatility deterioration to be present for
   any protect signal to fire. A volatility-only protect on an event date is reclassified as
   `no_change` with a reason note: "vol rise near scheduled event; non-vol confirmation
   required."

4. Add `event_vol_context` as a field on `RegimeActionState` and in snapshot JSON so it is
   visible in outcomes replay.

---

### Phase 5: Episode-level correction diagnostics

**Goal:** Replace average-return forward windows as the primary evaluate metric with
episode-level correction coverage and false-alert rate.

**Changes to `regime.py` / new `regime_episodes.py`:**

1. Add `compute_correction_episodes(snapshots, price_history, threshold=0.05)` that:
   - Identifies all peak-to-trough SPY corrections ≥ threshold (default 5%, also test 8%).
   - For each episode, records: peak date, trough date, first -3% crossing, first -5%
     crossing, whether a protect signal fired in the prior 20/40 trading days, first warning
     date, lead time, whether the episode is shock-driven (define heuristically: >15% SPY
     drawdown in <30 trading days), and posture at each phase.
   - Returns a structured table plus summary: correction_count, warned_count, miss_count,
     false_alert_count.

2. Add `marketlab regime episodes` CLI command that prints this table.

3. Target metrics for v1 protect to be considered viable:
   - False-alert rate (protect with no ≥5% drawdown in 40d): below 50% (currently ~76%).
   - Correction coverage at 20-day pre-peak window: above 40% (currently ~29%).

---

### Phase 6: Stateful posture replay

**Goal:** Make `no_change` mean "maintain prior posture," enabling real episode-level
portfolio backtesting.

**Changes:**

1. Add `compute_posture_episodes(snapshots)` that processes snapshots chronologically
   and maintains a running `posture` state (`maintain`, `protect`, `redeploy`) that only
   changes when a non-`no_change` action fires.

2. The posture resets on the opposite signal: `protect` → reset on `scale_up_redeploy`
   or explicit posture-reset condition; `redeploy` → reset on `scale_down_protect` or
   similar.

3. Outcome replay for episodes: measure SPY/QQQ return and drawdown from the posture-change
   date through posture reset, versus the corresponding buy-and-hold period.

4. This makes the opportunity cost of false positives visible: a false protect episode
   that lasts 40 days costs roughly 1.3% SPY return on average.

---

## Priority order

| Order | Phase | Blocker dependency |
|---|---|---|
| 1 | Phase 1: extension_setup / fragility split | None — can run immediately |
| 2 | Phase 5: correction episode diagnostics | Needs backfill of snapshots (already done) |
| 3 | Phase 3: hard gates | Needs Phase 1 (extension_setup score) |
| 4 | Phase 4: event vol flag | Needs Phase 3 (gate refactor) |
| 5 | Phase 2: armed setup state | Needs Phase 3 (gates needed to use decay properly) |
| 6 | Phase 6: stateful posture replay | Needs Phase 3 (gates stabilized) |

---

## What to hold off on

**Sentiment and positioning inputs (NAAIM, AAII, put/call):** Mentioned in ALGORITHM_DESIGN
as candidate evidence. These are valuable for confirming washout/redeploy, but their
availability, update lag, and replayable history must be established before adding them.
The current signals already have enough inputs to cause false positives — adding noisy
external sentiment sources before the gate structure is fixed would compound the problem.

**Multiple protect confidence tiers (warning / alert / urgent):** Tempting but premature.
The episode diagnostics (Phase 5) need to show that the new gate structure reliably produces
a useful binary protect signal before adding confidence-level nuance.

**Single-name regime context modifier:** Leave the Bulltard regime context modifier
unchanged until the headline regime and protect signals are more reliable. A broken market
signal passed into single-name scoring just introduces noise.

---

## North star metrics for declaring v1 complete

Before tagging v1.0, the following must be true in backfill replay:

1. **Protect false-alert rate ≤ 50%** (≥5% SPY drawdown within 40d; currently ~76%).
2. **Protect covers ≥ 6 of 14 non-COVID SPY corrections ≥5%** in the 20-day pre-peak window
   (currently 4/14 per ALGORITHM_DESIGN.md).
3. **Redeploy 40d average SPY return ≥ +7%** (currently +9.3%; ensure the redesign
   does not degrade this).
4. **Episode diagnostics command working** and showing correction-level coverage table.
5. **Stateful posture replay** showing episode-level SPY outperformance (or honest null
   result if not outperforming).
