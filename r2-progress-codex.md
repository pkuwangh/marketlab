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
- [x] Replace protect with gated paths.
- [x] Make volatility-only protect warning-only.
- [x] Add event-volatility context.
- [x] Export armed setup memory as research output.
- [x] Add posture replay in outcomes/export flows.
- [ ] Validate redeploy separately.

## Notes

- Keep same-version overwrite behavior for generated artifacts.
- Keep posture inside outcomes/export workflows; do not add a required daily command path.
