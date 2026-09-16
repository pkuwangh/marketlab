# r3 Reply - Codex

## Summary

I agree with the main review direction. The r2 implementation had the right shape, but a few fields
could mislead the research workflow if we started relying on them too heavily.

The important design clarification is that protect is not expected to catch every exogenous crash.
COVID-style fast shocks are acceptable false negatives for the protect model. The model should be
judged mainly on ordinary distribution-tail corrections and false-alert cost.

## Replies

1. `event_context` was static.
   Accepted. I added a basic episode classifier: `ordinary`, `scheduled_event_proxy`, and `shock`.
   `shock` is intentionally separated so protection false negatives from fast deep exogenous moves
   do not dominate the ordinary-correction review.

2. Armed memory re-armed indefinitely.
   Accepted. The workbook now separates `extension_elevated_*` from `extension_armed_*`. A continuous
   elevated run no longer resets the armed age to zero after the bounded window.

3. `_protect_path_from_reason` parsed human text.
   Accepted. `action_path` is now a first-class snapshot/action field. Reason parsing remains only as
   a legacy fallback for old saved snapshots.

4. Event-volatility context uses market proxies, not a calendar.
   Mostly intentional. I kept the VIX term-structure proxy because it is replayable and requires no
   manually maintained event calendar. The docs now state that it is not a calendar-based event label.

5. Duplicate armed thresholds.
   Accepted. The export and episode code now share the regime-level extension armed threshold.

6. Volatility-only warning can be suppressed when strength is mild.
   Intentional for now. Mild volatility-only deterioration is noisy; surfacing every small case would
   make the action read worse. We can add a below-threshold diagnostic later if the workbook suggests
   useful patterns there.

7. Posture age uses snapshot index, not calendar days.
   Accepted. The docs now call these trading/snapshot-row counts.

8. `washout_setup_score` equals aggregate washout pressure.
   Accepted as current v1.0 behavior. For now, washout pressure is already specific enough. We can
   split it later if redeploy diagnostics show that a narrower setup definition is useful.

9. False-alert cluster report was implicit.
   Accepted. `regime outcomes --by cluster` now groups consecutive protect days and reports whether
   each cluster was followed by a 5% SPY drawdown over the selected horizons.
