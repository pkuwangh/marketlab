# MarketLab

- [MarketLab](#marketlab)
  - [Current Capabilities](#current-capabilities)
  - [Normal Daily Use](#normal-daily-use)
  - [Market Regime Pillar](#market-regime-pillar)
    - [Market Regime Signals](#market-regime-signals)
    - [Portfolio Policy](#portfolio-policy)
  - [Gmail Recap Fetch](#gmail-recap-fetch)
  - [Bulltard Debug Utilities](#bulltard-debug-utilities)
  - [Visualization](#visualization)
  - [Local Research Store](#local-research-store)
  - [Candidate Validation](#candidate-validation)
  - [Reset Local Research Data](#reset-local-research-data)

MarketLab is a research system for market-regime analysis and large-cap opportunity tracking.

The implementation follows `DESIGN.md`: point-in-time observations, deterministic calculations, bounded agent outputs, and reproducible reports.

Use this README for current commands and `DESIGN.md` for architecture and research direction.

## Current Capabilities

MarketLab is organized around two alpha-research pillars. The primary pillar is market regime:
decide when marginal SPY/QQQ risk should be maintained, protected, or redeployed. The secondary
pillar is Bulltard-driven single-name research: use subscription flow as candidate generation,
then independently validate and measure it.

- Market regime and portfolio posture, primary pillar:
  - Refreshes SPY/QQQ, VIX/VVIX, RSP/IWM, HYG/TLT, and FRED credit/liquidity/rates observations.
  - Computes daily directional regime, stretch/washout setup pressure, deterioration/stabilization action evidence, and rare action states: `no_change`, `scale_down_protect`, or `scale_up_redeploy`.
  - Maps regime action states into provisional marginal beta, cash, overlay, and single-name risk posture.
  - Replays regime, market-signal, pressure, and policy states against forward SPY/QQQ returns and drawdowns.
  - Renders the daily policy report and regime chart from saved point-in-time snapshots.

- Bulltard and single-name candidates, secondary pillar:
  - Fetches the daily Bulltard recap from Gmail and uses the original signed link to capture targeted app views.
  - Parses ranked option trades, Trades Of Interest, and ticker-flow detail.
  - Treats Bulltard names as a research funnel, not trade recommendations: `confirm` means independent price/liquidity/relative-strength evidence is aligned, `watch` means evidence is incomplete or mixed, and `avoid` means the name fails basic independent checks.
  - Builds candidate review and validation snapshots with independent price, volume, trend, drawdown, and relative-strength features.
  - Replays candidate outcomes over 1, 5, 20, 40, 65, and 126 trading-day horizons, with cohort views for source, validation status, ranked side, ticker-flow subtype, and market regime when available.
  - Renders a reproducible opportunity chart for one saved candidate.

- Research record for iteration:
  - Preserves point-in-time observations and snapshots with source-date, signal-time, version, and provenance fields.
  - Rebuilds a local DuckDB query store from JSON/JSONL source artifacts for analysis and outcome review.

Current limitations:

- Portfolio policy is a provisional rule layer: it maps regime action states into beta/cash/overlay posture, but the action evidence, thresholds, and position bands still need longer-history calibration and anti-churn rules.
- Bulltard candidate handling currently stops at research triage. Real options-liquidity, fundamental viability, instrument suitability, lifecycle episodes, thesis, and invalidation modeling are still future work before a candidate can become a complete opportunity.
- Market-signal production still uses hard-coded v0 feature thresholds; richer calibrated signal families are future work.

## Normal Daily Use

The routine operating path is one command:

```bash
./bin/marketlab daily
```

By default it uses today's local date. The daily run first refreshes market sources, writes
market-signal and regime snapshots, derives the portfolio policy, and renders the daily
policy report and regime chart. When read-only Gmail credentials exist, it then fetches the
Bulltard recap from Gmail, validates captured candidates, and refreshes the local DuckDB
store for outcome review.
Daily mode regenerates replaceable derived market-signal artifacts, but it does not replace
same-version regime snapshots unless you pass `--replace-regime`. Use that only when you
intentionally want a research-date snapshot to reflect changed source data or model code.

For a specific date:

```bash
./bin/marketlab daily --date 2026-09-04
```

The lower-level `regime`, `bulltard`, `policy`, `chart`, and `store` commands remain available
for debugging, backfills, and focused research.

## Market Regime Pillar

### Market Regime Signals

Compute the market regime directly:

```bash
./bin/marketlab regime snapshot --date 2026-09-04 --refresh-sources
```

`--refresh-sources` refreshes the local Yahoo price cache and FRED market series before computing
the regime snapshot. The lower-level `--fetch-prices` and `--fetch-market-series` flags remain
available for partial diagnostics, but routine one-off regime runs should refresh both source
families together. Overlapping Yahoo/Stooq refreshes replace existing rows for the same symbol/date
because vendors can revise adjusted prices; saved regime, policy, and candidate snapshots remain
the frozen research record unless replacement is explicit. Index symbols keep their source symbol
in each row, but use filesystem-safe cache names such as `INDEX_VIX.jsonl` and `INDEX_VVIX.jsonl`.
FRED market-series backfills use the current available local vintage; they are useful for research,
but they are not true historical FRED vintages.
Regime computation always starts from local price/FRED observations. Market-signal rows are
replaceable derived artifacts under `data/derived/market/signals`; they are for inspection and
outcome replay, not immutable snapshots and not an input cache.

The current score uses:

- SPY/QQQ trend and moving-average posture.
- SPY realized volatility and VIX.
- RSP/SPY and IWM/SPY participation.
- HYG/TLT risk appetite.

Backfill market-regime snapshots and derived market-signal artifacts over local price dates:

```bash
./bin/marketlab regime backfill --start 2025-01-02 --end 2026-09-04
```

Backfill skips existing same-version regime snapshots by default, so repeated runs fill missing dates
without rewriting frozen historical records. Market-signal artifacts are replaceable. Use
`--recompute-existing` only when you intentionally want to recompute saved regime dates and surface
any immutable snapshot conflicts.

Replay saved regime snapshots against forward SPY/QQQ returns and drawdowns:

```bash
./bin/marketlab regime outcomes --start 2026-08-01 --end 2026-09-04
```

Replay rare action states or normalized pressure buckets:

```bash
./bin/marketlab regime action-outcomes --start 2025-01-02 --end 2026-05-22 --horizons 20,40,65
./bin/marketlab regime pressure-outcomes --start 2025-01-02 --end 2026-05-22 --horizons 20,40,65
```

### Portfolio Policy

Create a policy snapshot from a saved regime snapshot and any saved Bulltard candidate validation snapshot:

```bash
./bin/marketlab policy snapshot --date 2026-08-28
```

Render the daily human-facing report:

```bash
./bin/marketlab report daily --date 2026-08-28
```

Backfill and replay policy snapshots:

```bash
./bin/marketlab policy backfill --start 2025-01-02 --end 2026-08-28
./bin/marketlab policy outcomes --start 2025-01-02 --end 2026-05-22 --horizons 20,40,65
```

The v0 policy keeps the permanent SPY/QQQ core conceptually unchanged. It only maps the marginal tactical sleeve:

- `maintain`: target roughly neutral tactical beta and make no forced change.
- `protect`: reduce marginal beta, preserve or raise cash, and consider covered calls.
- `redeploy`: add exposure in tranches after washout conditions, including possible 60-90 DTE calls/call spreads or bounded put underwriting.


## Gmail Recap Fetch

Gmail access is read-only and uses local OAuth credentials. This is a one-time setup.

1. In Google Cloud Console, enable the Gmail API for a project.
2. Create an OAuth Client ID with application type `Desktop app`.
3. Download that JSON file into this repo as `secrets/google-oauth-client.json`.
   This file is not your Gmail password; it only identifies the local MarketLab OAuth app.
4. Authorize MarketLab once:

```bash
./bin/marketlab gmail auth --client-secret secrets/google-oauth-client.json
```

By default this opens a browser, asks Google for Gmail read-only access, receives the callback
on `127.0.0.1`, and writes `secrets/gmail-token.json`. That token is what future runs use and
refresh locally. Keep both files under `secrets/`; both `secrets/` and `data/` are gitignored.

If the command runs on a machine without a normal interactive browser, or Google shows a
message like "JavaScript turned off" after the command opens Chrome, use the manual browser
path instead. Pick a fixed callback port and have MarketLab print the `authorization_url`:

```bash
./bin/marketlab gmail auth --no-browser --port 8765
```

Open the printed URL in a normal local browser. If MarketLab is running on a remote machine
over SSH, forward the same port before running the auth command:

```bash
ssh -L 8765:127.0.0.1:8765 YOUR_REMOTE
```

After approval, Google redirects to `127.0.0.1:8765`, the SSH tunnel sends that callback back
to MarketLab, and the command should print `MarketLab Gmail authorization complete.` The default
`--port 0` chooses any free local port and is the easiest option on a normal local desktop. A
fixed `--port` is mainly for SSH forwarding or firewall rules.

If Google says the app is still in testing and only developer-approved testers can access it,
add your Gmail address under the project's OAuth consent screen test users, then rerun the
auth command and open the new URL.

After auth, the daily workflow can fetch the recap and create `data/inbox/bulltard/`
automatically:

```bash
./bin/marketlab daily
```

To test only the email acquisition step:

```bash
./bin/marketlab gmail bulltard-recap --date 2026-09-01
```

This searches Gmail for the recap, caches it as
`data/inbox/bulltard/recap-YYYY-MM-DD.html`, verifies that it contains a signed Bulltard app
link, and leaves the existing Bulltard parser/ingester to do the rest.

## Bulltard Debug Utilities

Routine use should go through `./bin/marketlab daily`. The commands in this section are lower-level
debugging and manual-fallback surfaces for a specific saved recap file.

Inspect a local recap and print the redacted signed source URL:

```bash
./bin/marketlab bulltard inspect-recap tests/fixtures/bulltard/recap.html
```

To reveal the full temporary capability URL for local debugging, pass `--show-secret-url`.

Retrieve and parse the first targeted view:

```bash
./bin/marketlab bulltard ingest \
  --date 2026-08-24 \
  --view ranked-option-trades \
  data/inbox/bulltard/recap-2026-08-24.html
```

The current `ingest` command resolves the recap, signed access link, and view route, retrieves the
view into `data/debug/bulltard/...` for parser troubleshooting, and writes parsed rows to
`data/observations/bulltard/...`.

Retrieve and parse the Bulltard detail page for one ticker from the same signed recap access:

```bash
./bin/marketlab bulltard ticker \
  INTC \
  data/inbox/bulltard/recap-2026-08-24.html \
  --date 2026-08-24
```

Ticker pages are currently saved under `data/debug/bulltard/tickers/<SYMBOL>/`.
Ticker flow observations are written under
`data/observations/bulltard/ticker_flow/<SYMBOL>/`.

Parse the recap's Trades Of Interest section into local observations:

```bash
./bin/marketlab bulltard trades-of-interest \
  --date 2026-08-26 \
  data/inbox/bulltard/recap-2026-08-26.html
```

Review ranked candidates and attach any ticker-flow detail already collected:

```bash
./bin/marketlab bulltard candidates --date 2026-08-26
```

Run the Bulltard-only daily loop against a saved recap file:

```bash
./bin/marketlab bulltard daily \
  --date 2026-08-26 \
  data/inbox/bulltard/recap-2026-08-26.html
```

By default, `daily` ingests the ranked database view, parses Trades Of Interest from the recap,
fetches ticker detail for the Trades Of Interest names, and prints the candidate review table.
Use `--top-ranked N` to also fetch detail for the top N ranked database names, or
`--no-ticker-details` to skip detail fetches.

Run the full Bulltard-only candidate loop:

```bash
./bin/marketlab bulltard daily \
  --date 2026-08-28 \
  data/inbox/bulltard/recap-2026-08-28.html \
  --fetch-prices \
  --validate \
  --outcomes
```

`--fetch-prices` refreshes Yahoo daily prices for the captured candidates plus `SPY` and `QQQ`.
The default price window starts 550 calendar days before `--date` and ends today. `--outcomes`
replays saved validation snapshots from the earliest saved snapshot through `--date` by default.
Use `--outcome-start` and `--outcome-end` to override that replay window.

## Visualization

Generate reproducible charts from saved snapshots and observations:

```bash
./bin/marketlab chart regime --start 2026-08-28 --end 2026-08-28
./bin/marketlab chart opportunity --date 2026-08-28 MRVL
```

By default these write `reports/regime-START-END.html` and
`reports/opportunity-SYMBOL-DATE.html`.

The regime chart shows indexed SPY/QQQ price, regime action-state shading, stretch/washout
pressure, market-signal family scores, and the latest market-signal table.
The opportunity chart shows the candidate versus SPY/QQQ, Bulltard flow-premium event bars,
20d relative strength, the point-in-time validation snapshot, and a separate forward-outcome
table that stays marked `waiting` until enough future local price rows exist.

## Local Research Store

Refresh the local DuckDB store from saved observations and snapshots:

```bash
./bin/marketlab store refresh
```

Optionally also export each table as Parquet:

```bash
./bin/marketlab store refresh --parquet-root data/warehouse/parquet
```

Inspect or query the store:

```bash
./bin/marketlab store tables
./bin/marketlab store query "select source_date, policy_state, marginal_beta_target from policy_snapshots order by source_date desc limit 10"
```

## Candidate Validation

For normal daily use, let `./bin/marketlab daily` refresh prices, acquire the recap, validate
candidates, and replay outcomes. To refresh a captured Bulltard date explicitly:

```bash
./bin/marketlab bulltard refresh-prices \
  --date 2026-08-26 \
  --start 2025-01-01 \
  --end 2026-08-27
```

You can still fetch independent daily OHLCV history for arbitrary tickers:

```bash
./bin/marketlab prices fetch-yahoo META,XAR,SRRK,DKS,QXO,SPY,QQQ \
  --start 2025-01-01 \
  --end 2026-08-27
```

This uses the actively maintained `yfinance` package. It stores raw `close` and `adjusted_close`;
MarketLab uses adjusted close for return/outcome calculations when available. Re-fetching an
overlapping date range updates the local price cache; point-in-time snapshots preserve the exact
derived signal used for research.

The older Stooq path remains available as `prices fetch`, but it may require a Stooq API key:

```bash
./bin/marketlab prices fetch META,SPY --start 2025-01-01 --end 2026-08-27
```

Or import a local CSV with `Date, Open, High, Low, Close, Volume` columns:

```bash
./bin/marketlab prices import-csv META ~/Downloads/META.csv --source manual
```

Validate a captured Bulltard candidate set from local price observations:

```bash
./bin/marketlab bulltard validate --date 2026-08-26
```

Or run capture, price refresh, validation, and saved-snapshot outcome replay together:

```bash
./bin/marketlab bulltard daily \
  --date 2026-08-28 \
  data/inbox/bulltard/recap-2026-08-28.html \
  --fetch-prices \
  --validate \
  --outcomes
```

Validation snapshots are written under `data/snapshots/bulltard/candidates/`.

Replay forward outcomes after enough future price rows exist:

```bash
./bin/marketlab bulltard outcomes --start 2026-08-01 --end 2026-08-26 --horizons 40,65
```

This is the candidate-learning loop. Each saved Bulltard validation row is treated as a
point-in-time candidate episode, then grouped into cohorts such as Trades Of Interest versus
ranked-only, `confirm` versus `watch`, ranked bullish/bearish side, detailed ticker-flow subtype
such as put selling or call buying, and same-day market regime when a regime snapshot exists.
The 40- and 65-trading-day horizons approximate the 60-90 calendar-day window.

If you need a manual fallback, pass a local recap artifact or a small text file containing the
recap's database/app link to the lower-level Bulltard commands. Gmail may wrap the useful Substack
redirect as a `https://www.google.com/url?q=...` link; the tool unwraps that form.

## Reset Local Research Data

To rebuild from scratch while keeping Gmail authorization intact:

```bash
rm -rf data reports marketlab.duckdb marketlab.duckdb.wal marketlab.duckdb.tmp
./bin/marketlab daily
```

Do not delete `secrets/` unless you intentionally want to redo Gmail OAuth.

CLI logging uses Loguru. Set verbosity with:

```bash
./bin/marketlab --log-level DEBUG bulltard inspect-recap tests/fixtures/bulltard/recap.html
```

The live research database, inbox files, generated observations, debug payloads, reports, and credentials are intentionally gitignored.
