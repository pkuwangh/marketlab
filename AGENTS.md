# MarketLab Agent Rules

These rules apply to the whole repository.

- Read `README.md` for current commands and `DESIGN.md` for system intent before changing workflow behavior.
- Keep the market-regime engine primary. Bulltard is a secondary single-name candidate source and must not silently drive aggregate market exposure.
- Treat this as a local research system, not an automated trading system. Never add trade execution paths.
- Keep canonical numerical calculations deterministic, testable, and owned by Python code. Agents may summarize or extract bounded structured fields, but they must not rewrite scores, snapshots, or backtest results.
- Preserve point-in-time semantics. Official date-level market research uses EOD signal timing unless timestamp-aware inputs and labels are explicitly introduced.
- Keep source artifacts and external observations reproducible. Derived regime outputs and market-signal artifacts belong under `data/derived` and are replaceable by their producing workflow.
- Do not resolve an ambiguous snapshot/model artifact by silently choosing the latest. Require an explicit artifact version when multiple same-date artifacts exist.
- Treat signed Bulltard recap URLs, scanner access tokens, Gmail tokens, and OAuth client secrets as private capabilities. Redact them in normal CLI output, logs, reports, and docs; reveal them only through explicit debug options.
- Label FRED backfills clearly as current-vintage local history unless true point-in-time vintage data is introduced.
- Prefer compact, interpretable regime action logic: regime describes the backdrop, setup pressure describes stretch/washout, and action evidence describes deterioration/stabilization.
- Keep edits scoped to the active research loop. Avoid broad support infrastructure until it unlocks a concrete measurement or daily workflow.
- Run focused tests for changed behavior; run the full suite and lint before finalizing broad workflow or model changes when practical.
