# R2 Implementation Progress

**Status:** in progress.
**Source plan:** `r2-plan-codex.md`.

This file tracks implementation progress separately from the design plan. Do not use
`r2-plan-codex.md` as a progress log.

## Progress

- [x] Bump market-regime research version to `v1.0`.
- [x] Version workbook and canonical outcome artifacts.
- [x] Split `extension_setup` from `fragility_context`.
- [x] Add correction-episode diagnostics.
- [ ] Replace protect with gated paths.
- [ ] Make volatility-only protect warning-only.
- [ ] Add event-volatility context.
- [ ] Export armed setup memory as research output.
- [ ] Add posture replay in outcomes/export flows.
- [ ] Validate redeploy separately.

## Notes

- Keep same-version overwrite behavior for generated artifacts.
- Keep posture inside outcomes/export workflows; do not add a required daily command path.
