# MarketLab Versions

This file records the current research versions. Code constants live in
`src/marketlab/versions.py`; this document is the human-readable ledger.

## Current Versions

| Pillar | Current version | Snapshot version | Derived labels |
| --- | --- | --- | --- |
| Market regime | `v1.2` | `v1.2` | `market_signals_v1.2`, `market_signals_model_v1.2`, `market_regime_features_v1.2`, `market_regime_score_v1.2`, `regime_pressure_v1.2`, `regime_action_v1.2`, `regime-v1.2.xlsx`, `regime-v1.2.csv`, `outcomes-action-v1.2.txt`, `outcomes-posture-v1.2.txt`, `outcomes-redeploy-v1.2.txt`, `outcomes-protect-v1.2.txt`, `outcomes-cluster-v1.2.txt`, `outcomes-pressure-v1.2.txt`, `outcomes-regime-v1.2.txt`, `outcomes-episode-v1.2.txt` |
| Bulltard | `v0.0` | `v0.0` | `bulltard_html_parsers_v0.0`, `bulltard_ingest_v0.0`, `bulltard_candidate_validation_v0.0`, `bulltard_candidate_validation_rules_v0.0`, `candidate_validation_only_v0.0` |
| Portfolio policy | `v0.1` | `v0.1` | `portfolio_policy_v0.1` |

## Bump Rules

- Same-version outputs may be overwritten while the project is pre-debut research.
- Do not bump for formatting, report/export changes, logging, or bug fixes that do not change signal meaning.
- Bump the affected pillar version when a change meaningfully changes generated signals, action/policy decisions, candidate validation labels, or outcome comparability.
- Each pillar's default snapshot version must stay tied to that pillar's current version in
  `src/marketlab/versions.py`. For example, when `REGIME_VERSION` becomes `v0.1`,
  `REGIME_SNAPSHOT_VERSION` must also resolve to `v0.1`.
- Keep old versioned snapshots for side-by-side outcome replay when comparing a new version against an older one.

## Version Ownership

- Market regime owns market-signal snapshots, headline regime, pressure, and action evidence.
- Bulltard owns Gmail/app parsing, Bulltard observations, candidate validation, and candidate outcome cohorts.
- Portfolio policy owns portfolio posture mapping across pillars.
