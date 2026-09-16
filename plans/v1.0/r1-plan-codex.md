# Market-Regime Protect Redesign Plan

**Status:** pre-implementation plan, current as of September 2026.

This document translates the protect review in
[ALGORITHM_DESIGN.md](./ALGORITHM_DESIGN.md) into an implementation sequence. The goal is to
improve `scale_down_protect` before tuning thresholds or treating it as a portfolio policy.

## Problem Summary

The current protect action is not a reliable correction-warning signal yet:

- most protect clusters did not precede a 5% SPY drawdown within 40 trading days;
- volatility-only confirmation has been especially weak;
- the current `sqrt(stretch * deterioration)` style score lets extreme deterioration compensate
  for weak setup;
- many real corrections are missed because extension and deterioration often happen on different
  dates;
- some corrections are regime breaks without prior extension, so armed extension alone is not
  enough.

## Design Direction

Protect should become a gated lifecycle model instead of a same-day blended score.

```text
extension_unwind:
    extension_setup_gate
    -> armed setup memory with decay
    -> broad_confirmation_gate
    -> protect

regime_break:
    strong_broad_deterioration_gate
    -> protect
```

Volatility-only deterioration should raise warning/context, but should not trigger normal protect
without support from breadth, credit, liquidity, or trend.

## Implementation Plan

1. Build correction episode diagnostics.

   Add an outcome view that identifies SPY correction episodes, including 5% and 8% thresholds,
   first -3% and -5% drawdown crossings, trough date, lead time from first warning, false-alert
   rate, and shock/event labels.

2. Split protect pressure into cleaner components.

   Separate `extension_setup` from `fragility_context`. Price extension and volatility complacency
   belong in extension setup. Breadth, credit, liquidity, volatility turns, and trend damage belong
   in fragility/confirmation context.

3. Add armed extension memory.

   Use a rolling percentile threshold, roughly p90, to arm protect after high extension. Keep that
   state alive for a bounded 20-40 trading-day window with decay.

4. Replace geometric compensation with hard gates.

   Stop using a single score where extreme deterioration can rescue weak setup. For the
   extension-unwind path, require both an active extension setup and broad confirmation. Compute
   strength only after the gates pass.

5. Add broad confirmation rules.

   Require at least two deterioration families for normal protect, with at least one non-volatility
   internal family such as breadth, credit, liquidity, or trend. Keep volatility-only output as a
   warning/context reason.

6. Add a harder regime-break path.

   Allow protect without prior extension only when deterioration is materially broader and stronger,
   for example trend damage plus volatility and at least one internal/funding confirmation.

7. Re-run episode-level validation before tuning.

   Compare coverage of ordinary corrections, late signals, false-alert rate, and lead time before
   changing thresholds. Daily 20d/40d forward returns should be secondary.

8. Add stateful posture replay.

   After action events improve, replay posture episodes where protect remains active until a reset,
   redeploy signal, or other explicit exit condition appears.

9. Leave redeploy mostly unchanged for now.

   Redeploy has looked stronger empirically than protect. Validate it separately, but avoid mixing
   redeploy redesign into the first protect cleanup.

## Done Criteria

- `regime outcomes` can evaluate correction episodes, not only daily overlapping windows.
- Snapshot output explains whether protect came from `extension_unwind`, `regime_break`, or
  warning-only volatility context.
- Volatility-only deterioration does not produce normal `scale_down_protect`.
- Outcome reports show coverage, lead time, late signals, and false-alert rate for protect.
- The implementation remains versioned under the current market-regime pillar version until we
  deliberately bump it.
