# V1.1 Implementation Record

## Status

- Reference audit and baseline: complete; 233 existing tests pass.
- Frozen specification: recorded below before challenger outcomes are inspected.
- Evidence and lifecycle implementation: complete, including partial-evidence gates and persisted state.
- Four actions, policy, exports, accounting: complete; focused lifecycle tests pass.
- Isolated comparisons: complete for core and reduced profiles, ten independent configurations each.
- Canonical v1.1 backfill: complete, 2,693 sessions from 2016-01-04 through 2026-09-18.
- Policy v0.1 backfill: complete for the same 2,693 sessions; allocation weights shared with replay.
- Integration verification, artifact-preservation audit, and operational docs: complete.
- Economic review: recorded in `implementation-results.md`; the candidate does not outperform
  the untimed or exposure-matched controls. No retrospective retuning or alpha claim.

The R3 proposal is unchanged. Existing staged research documents belong to the user.
Never write experiments into canonical v1.0/v1.1 paths or use workbook data as inputs.

## Frozen Initial Specification

These are causal research defaults, not fitted estimates. Unfavorable results do not authorize
silent threshold changes. The four-path candidate is not a claim of demonstrated alpha.

### Evidence And Coverage

- Daily canonical SPY sessions are the clock. EOD decisions execute at the following observed
  session's adjusted open. New snapshots persist sufficient state to resume the same transition.
- Core profile uses price-proxy breadth, VIX/VVIX/term structure, HYG/TLT plus OAS, and NFCI.
  Direct participation remains supplementary because its local history cannot support comparison.
  The explicitly reduced research profile omits OAS from numerical credit, not from the funding
  veto. Missing OAS plus known loose NFCI can resolve that AND-veto false; otherwise it is unknown.
- Each family is the maximum of its owned leaves. Within a multi-input leaf, all declared inputs
  must exist. Missing alternative leaves make the family a lower bound, not an exact score.
  Two observed family bounds may prove strong confirmation; recovery below a gate requires exact
  evidence for every causal family. Boolean gates pass the score unchanged; explanatory paired
  features do not create votes. Aggregate confirmation is the second-highest family.
- Setup arithmetic uses fixed feature sets, never changing available-only denominators. Missing
  setup evidence cannot create a hit, release, stress increase, or repair. Preserve descriptive
  pressure tables separately. FRED observations remain current-vintage local history.

### Setups And Price Opportunity

- Keep extension 0.75 single / 0.60 three-of-ten, 40-session fixed memory; washout 0.75 single /
  0.60 two-of-five, 15 sessions from last qualifying hit. Endpoints are inclusive. Interrupted hits
  preserve identity and peak. Expiry, not a missed hit, starts a genuinely later episode.
- A/B/C use the proposal's distinct stress geometry/transmission gates. The candidate uses C:
  sqrt(trend * volatility), both >= 0.50. Continuous stress is not zeroed by these gates.
- Washout price reference is each index's trailing 20-session closing high at the first qualifying
  hit used to arm. Track the running low from those qualifying hits onward without hindsight.
  Opportunity remains only while both indexes have genuine anchor-to-low damage and have recovered
  no more than half that distance. This retains at least as much recovery distance to the old high
  as downside to the observed low, not a promise that either is a target or support. Existing
  15-session stress grace bounds entry; no second fear-memory window. Stress release >= 0.05,
  current second-family stabilization >= 0.75, resolved funding veto, and unused episode required.
- Orderly pullback: both indexes were above MA50 and MA200 with positive 60-session returns on
  the preceding session; then both close below MA50 while remaining above MA200. That transition
  arms a pullback, with the same trailing-20 high anchors and running lows. It expires after 20
  sessions, loses eligibility if either closes below MA200, and completes when both regain anchors.
  Re-arm requires a fresh established-trend-to-pullback transition, not a daily boolean flicker.
  Entry requires positive current 5-session returns in both indexes, owned trend stabilization
  >= 0.75 plus another strong family, the same half-recovery opportunity rule, and funding clear.

### Protection And Exits

- Extension divergence is remembered within its existing episode for at most ten sessions, using
  breadth/credit owned deterioration >= 0.35 under nonnegative average index 20-session momentum.
  Clear a family's memory after three exact below-0.35 sessions. Execution requires a prior-day
  divergence, current trend and volatility deterioration >= 0.35, and both above MA200. No
  two-divergence-only execution and no additional decayed-strength veto in the candidate.
- Break: both indexes below MA50 with negative 20-session returns on three consecutive sessions,
  plus current trend deterioration >= 0.35 and a distinct owned family >= 0.35. Three sessions
  distinguish persistence from a one-day scare; MA50 is the existing intermediate trend horizon.
  No extension, headline-regime, or MA200-uptrend requirement. Episode identity persists until
  both regain MA50 for three sessions; missing observations break streaks, not episodes.
- Protect repair: three consecutive sessions of both nonnegative 5-session returns and all causal
  entry families' exact owned deterioration < 0.35; break additionally requires both above MA50.
  Record deterministic minimal causal families (highest corroborator, family-name tie-break).
- Washout failure: current trend and volatility deterioration >= 0.35 plus comparable continuous
  stress rising. Pullback failure: either below MA200 or both below the saved entry episode lows,
  plus trend and one non-price deterioration family >= 0.35. Falling fear alone never exits.
- Caps remain 65 protected / 20 increased sessions. No opportunity-completion exit in this release.
  Opposite unused action, then cap, then thesis repair/failure, otherwise hold. No same-bar reentry.

### Resolution And Accounting

- Raw gates for all paths remain visible. Same-direction primary labels: break before extension,
  washout before confirm. Consume every overlapping eligible same-direction episode on entry and
  when it qualifies while already held. No same-direction thesis handoff or cap reset. New paths
  arriving after exit are subject to their own causal episode identity, never a label-gap heuristic.
- Remove consumed opportunities before opposing-direction conflict resolution. Opposing unused
  directions mean no new entry; independent exit/cap still runs. Restoring normal is not redeploy.
- Policy maps saved held posture, not a fresh action string. Regime v1.1, policy v0.1, Bulltard
  v0.0 have independent input/output version selectors. Unknown action names are errors.
- Research account: 80% permanent equity core; 0/20/40% tactical exposure for protected/normal/
  increased posture; equal SPY/QQQ equity weights. Fixed fractional exposures rebalance daily.
  Cash earns zero; borrowing costs 5% annualized ACT/365; one-way turnover costs 5 bp. Report
  gross and net, untimed normal exposure and same-average-exposure controls. These assumptions
  are explicit research controls, not execution or broker claims. Prior exposure owns overnight;
  changes execute at adjusted open (raw open times adjusted-close/raw-close factor).
- Saved state before report start initializes posture/consumption; account valuation rebases at
  the requested boundary. Missing next-open prices are unavailable, not close substitutions.
  Open final holdings stay open. Fixed forward labels are separate from held/portfolio returns.

## Verification Record

- Baseline: `.venv/bin/pytest -q`: 233 passed.
- Final full suite: `.venv/bin/pytest -q`: **258 passed**.
- `.venv/bin/ruff check src tests`: passed. `git diff --check`: passed.
- Focused coverage includes source-observation setup/entry/failure, canonical versus resumed
  transitions, missing intermediate sessions, JSON round trips, full/sliced exports, ownership
  and partial-evidence predicates, opposing and consumed opportunities, fixed holding caps,
  four-path reachability, next-open gaps/costs/financing, and warm-account slice parity.
- Mixed-version policy tests preserve independent dependencies and reject old output versions.
  Daily policy uses held posture and the same 80/100/120% weights as exposure replay.
- Ordinary snapshot, recent report, export, action/protect/redeploy/posture outcomes, policy
  report, and policy backfill were exercised against local canonical data. No source refresh
  or external account access was needed. No new required CLI flags or command paths were added.
- Generated `workbooks/regime-v1.1.xlsx` and `.csv`: 2,693 rows, 268 columns. Saved versioned
  action, protect, redeploy, and posture outcome reports. Existing versioned workbooks unchanged.
- V1.0 read-only outcomes retain 14 native protect and 8 redeploy events. SHA256 over sorted
  v1.0 snapshot paths and contents, before and after: 5,386 files,
  `e2f29420a3c1e77cdf9b3f4a954f1b77a78199a3a3f0d6388fca89062297a27d`.
- The R3 proposal/discussion and other user-staged research documents were not edited. Progress
  and comparison results are separate documents.

## Delivered Boundaries

- `regime_lifecycle.py`: deterministic owned evidence, setup memories, four paths, resolver,
  and one resumable held-state transition. Old action evaluation is not an active production path.
- `regime_exposure.py`: next-open ETF accounting and actual holding windows, not trade execution.
- `regime_research.py`: fixed, isolated comparisons; no parameter search or workbook inputs.
- `regime.py`, policy, exports, and reports use saved lifecycle state. Detail tables distinguish
  numerical family votes from their inputs and non-voting explanations; recent reports show
  both new action and held posture. Zero-event action rows remain visible.
- Regime defaults to v1.1, policy to v0.1, Bulltard stays v0.0. Same-version replacement remains
  supported; older artifacts are replayed without recomputing their algorithm.

## Reporting Follow-Up

Redeploy diagnostics now distinguish both paths, rather than using washout-oriented columns
for every redeploy date. Per-path status rows retain zero entries, separate known and unknown
blockers, and show distinct setup counts alongside daily forward labels. The all-days baseline
is counted once. A separate gate table includes consumed episodes and resolver checks in its
sole-blocker counts, avoiding false attribution to missing funding inputs.

Regenerated `workbooks/outcomes-redeploy-v1.1.txt` over the original window: all fourteen unknown-
funding washout dates also have a consumed episode, so none is funding-only. The confirm path
has 241 armed dates and zero entries; its failed and unknown checks are now visible. No model,
snapshot, allocation, or version changes were needed. Older-version diagnostics remain readable.
Full suite: 267 passed; lint and whitespace checks pass.

## R4 Transmission Coverage Correction

The transmission gate now accepts a sufficient observed breadth or credit-pressure component
without requiring the other component. A weak partial reading remains unknown; two resolved
weak components fail. Fixed within-component means are unchanged, so partial core credit is
not silently replaced with HYG/TLT alone. The default TV model without a transmission gate is
unchanged.

TVX continuous stress still requires exact component coverage. A lower bound can establish a
positive transmission predicate, but cannot stand in for exact stress, its peak, or its release.
Regression tests cover either missing alternative, threshold equality, both missing, partial
credit, and missing/restored TVX coverage without manufactured release. Core A/B differences
therefore include arithmetic coverage; the complete reduced profile isolates score geometry.

Reran all ten variants in both profiles over 2016-01-04 through 2026-06-01. Only core R2-B's
comparison record changed: 10 washout entries instead of 3, +508.69% net instead of +499.92%.
R2-C remains at 11 washout entries; all reduced-profile records and combined-model results are
unchanged. Updated the results table and interpretation without changing any thresholds or
rewriting canonical snapshots/workbooks.

Final verification: 278 tests pass, lint passes, and the staged whitespace check passes with
standard CSV CRLF line endings recognized. The 5,386 preserved v1.0 snapshot files retain the
SHA256 recorded above. No source fetch, canonical backfill, or parameter retuning was needed.
