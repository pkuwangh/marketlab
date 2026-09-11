# MarketLab

- [MarketLab](#marketlab)
  - [Design Docs](#design-docs)
  - [Current Capabilities](#current-capabilities)
  - [Normal Daily Use](#normal-daily-use)
  - [Market Regime Pillar](#market-regime-pillar)
    - [Market Regime Signals](#market-regime-signals)
    - [Portfolio Policy](#portfolio-policy)
  - [Bulltard Pillar](#bulltard-pillar)
    - [Gmail Recap Fetch](#gmail-recap-fetch)
    - [Bulltard Debug Utilities](#bulltard-debug-utilities)
    - [Candidate Validation](#candidate-validation)
    - [Reset Local Research Data](#reset-local-research-data)
  - [Local Research Store](#local-research-store)

MarketLab is a local research system for market-regime analysis and large-cap opportunity tracking.

Design is split between research logic and implementation mechanics.

## Design Docs

- [DESIGN.md](./DESIGN.md): short index to the design documents.
- [ALGORITHM_DESIGN.md](./ALGORITHM_DESIGN.md): market-regime, portfolio, Bulltard candidate, and outcome-research logic.
- [IMPLEMENTATION_DESIGN.md](./IMPLEMENTATION_DESIGN.md): CLI, storage, source handling, snapshot/version semantics, and local workflow architecture.

## Current Capabilities

MarketLab is organized around two alpha-research pillars.  The primary pillar is market regime:
decide when marginal SPY/QQQ risk should be maintained, protected, or redeployed.  The secondary
pillar is Bulltard-driven single-name research: use subscribed option flow as candidate
generation, then independently validate and measure it.

- Market regime and portfolio posture, primary pillar:
  - Refreshes SPY/QQQ, VIX/VVIX, VIX term-structure, breadth, HYG/TLT, and FRED credit/liquidity/rates observations.
  - Computes daily directional regime, stretch/washout setup pressure, family-bounded deterioration/stabilization action evidence, and rare action states: `no_change`, `scale_down_protect`, or `scale_up_redeploy`.
  - Reports named turn, divergence, confirmation, and contradiction evidence across trend, volatility, breadth, credit, and liquidity modules.
  - Maps regime action states into provisional marginal beta, cash, overlay, and single-name risk posture.
  - Replays regime, market-signal, pressure, and policy states against forward SPY/QQQ returns and drawdowns.
  - Renders the daily policy report and regime chart from saved point-in-time snapshots.

- Bulltard and single-name candidates, secondary pillar:
  - Fetches the daily Bulltard recap from Gmail and uses the original signed link to capture targeted app views.
  - Parses ranked option trades, trades of interest, and ticker-flow detail.
  - Treats Bulltard names as a research funnel, not trade recommendations: `confirm` means independent price/liquidity/relative-strength evidence is aligned, `watch` means evidence is incomplete or mixed, and `avoid` means the name fails basic independent checks.
  - Builds candidate review and validation snapshots with independent price, volume, trend, drawdown, and relative-strength features.
  - Replays candidate outcomes over 1, 5, 20, 40, 65, and 126 trading-day horizons, with cohort views for source, validation status, ranked side, ticker-flow subtype, and market regime when available.
  - Renders a reproducible opportunity chart for one saved candidate.

- Research record for iteration:
  - Preserves point-in-time observations and research snapshots with source-date, signal-time, version, and provenance fields.
  - Keeps calculated snapshots under `data/snapshots/`; same-version `v0` outputs are overwritten during pre-debut iteration.
  - Rebuilds a local DuckDB query store from JSON/JSONL source files for analysis and outcome review.

Current limitations:

- Portfolio policy is a provisional rule layer: it maps regime action states into beta/cash/overlay posture, but the action evidence, thresholds, and position bands still need longer-history calibration and anti-churn rules.
- Bulltard candidate handling currently stops at research triage. Real options-liquidity, fundamental viability, instrument suitability, lifecycle episodes, thesis, and invalidation modeling are still future work before a candidate can become a complete opportunity.
- Market-signal rows still use compact hand-authored feature rules. Keep them interpretable until replay shows which families add value.

## Normal Daily Use

The routine operating path is one command:

```bash
./bin/marketlab daily
```

By default it uses today's local date. The daily run first refreshes market sources
(Yahoo ETF/index proxies, CBOE volatility indexes, EODData breadth indexes, and FRED
market series), writes market-signal and regime snapshots, derives the portfolio policy,
and renders the daily policy report and regime chart. When read-only Gmail credentials exist,
it then fetches the Bulltard recap from Gmail, validates captured candidates, and refreshes
the local DuckDB store for outcome review.
Daily mode recomputes and overwrites same-version market-signal and regime snapshots by default.
Use `--no-bulltard` for a market-regime-only run.

For a specific date:

```bash
./bin/marketlab daily --date 2026-09-04
```

The lower-level `regime` and `bulltard` pillar commands remain available for focused research.
Utility commands live under `data` for raw market-data/store work and `tools` for external
integrations such as Gmail.

## Market Regime Pillar

### Market Regime Signals

Compute the market regime directly:

```bash
./bin/marketlab regime snapshot --date 2026-09-04 --refresh-sources
```

`regime snapshot` is a snapshot command. By default it prints concise metadata plus the
key-signals table: headline regime, pressure, input gaps, and action. Use `regime report`
to inspect the recent multi-day regime trend, or add `--detail` when debugging the heavier
evidence tables from the snapshot command itself.

Regime and market-signal snapshots are replaceable calculated under `data/snapshots/`;
source observations remain under `data/observations/`.

Some specific data concerns include:
- VIX term-structure ratios require same-date observations for both legs.
  Volatility indexes are fetched from CBOE historical CSVs; if a source returns stale
  VIX9D or VIX3M rows while current VIX is available,
  the term-structure signal is shown as an input gap instead of mixing dates.
- FRED market-series backfills use the latest revised history available when you fetch them.
  - In economic-data terminology, a "vintage" is the data as it existed on a specific release date.
  - MarketLab does not fetch true historical vintages yet, so these rows are useful for research
    but are not the original values that were known on each past date.
  - Refreshing these current-history rows can replace prior local values for the same
    observed date when FRED publishes a revision.
  - Replaced rows are recorded in
    `data/observations/market/series/_revisions/<SERIES>.jsonl`, and the refresh logs a warning.

The current regime score uses:

- SPY/QQQ trend and moving-average posture.
- SPY realized volatility, VIX/VVIX, and VIX9D/VIX/VIX3M term structure.
- RSP/SPY and IWM/SPY participation proxies, plus S&P 500 percent above 50d/200d moving averages.
- HYG/TLT risk appetite.
- FRED credit spread, financial conditions, and yield-curve context.

The regime snapshot output is organized as:

- Key signals: the headline regime, pressure, input gaps, and action. This prints by default.
- Action evidence: bounded deterioration/redeployment signals by family, with paired checks folded into the relevant family.
- Market signals: directional family evidence such as trend, volatility, breadth, credit,
  liquidity, and rates. Score cells marked `(regime)` feed the headline `regime_score`;
  other rows are supporting evidence for pressure, action, and later validation.
- Pressure features: normalized stretch/washout setup values and recent point-in-time raw inputs.
  Action evidence, market signals, and pressure features print with `--detail`.

See [KNOWLEDGE.md](./KNOWLEDGE.md) for a row-by-row interpretation guide for these
market-regime tables.

Backfill market-regime and market-signal snapshots over local price dates:

```bash
./bin/marketlab regime backfill --start 2016-01-01 --end 2026-09-04 --refresh-sources
```

### Backtesting

Backfill recomputes and overwrites same-version snapshots by default. Use `--skip-existing` when
you only want to fill missing dates.

Replay saved regime actions against forward SPY/QQQ returns and drawdowns:

```bash
./bin/marketlab regime outcomes --start 2016-01-01 --end 2026-06-01 --horizons 20,40,65
```

Replay headline regime labels, normalized pressure buckets, market-signal rows, or policy states:

```bash
./bin/marketlab regime outcomes --by regime   --start 2016-01-01 --end 2026-06-01 --horizons 20,40,65
./bin/marketlab regime outcomes --by pressure --start 2016-01-01 --end 2026-06-01 --horizons 20,40,65
./bin/marketlab regime outcomes --by signal   --start 2016-01-01 --end 2026-06-01 --horizons 20,40,65
./bin/marketlab regime outcomes --by policy   --start 2016-01-01 --end 2026-06-01 --horizons 20,40,65
```

Render a reproducible market-regime chart:

```bash
./bin/marketlab regime chart --start 2026-08-28 --end 2026-08-28
```

### Portfolio Policy

Create a policy snapshot from a saved regime snapshot and any saved Bulltard candidate validation snapshot:

```bash
./bin/marketlab regime policy --date 2026-09-04
```

`regime policy` is also a snapshot command. By default it prints snapshot metadata only. Use
`regime policy --detail` for the underlying policy posture table.

Render the recent regime trend report. By default this shows the last 10 saved trading-day
snapshots through `--date`, including stretch/washout pressure, protect/redeploy strength, and
key signal percentiles:

```bash
./bin/marketlab regime report --date 2026-09-04
./bin/marketlab regime report --date 2026-09-04 --days 20
```

Backfill and replay policy snapshots:

```bash
./bin/marketlab regime policy-backfill --start 2025-01-02 --end 2026-08-28
./bin/marketlab regime outcomes --by policy --start 2025-01-02 --end 2026-05-22 --horizons 20,40,65
```

The v0 policy keeps the permanent SPY/QQQ core conceptually unchanged. It only maps the marginal tactical sleeve:

- `maintain`: target roughly neutral tactical beta and make no forced change.
- `protect`: reduce marginal beta, preserve or raise cash, and consider covered calls.
- `redeploy`: add exposure in tranches after washout conditions, including possible 60-90 DTE calls/call spreads or bounded put underwriting.


## Bulltard Pillar

### Gmail Recap Fetch

Gmail access is read-only and uses local OAuth credentials. This is a one-time setup.

1. In Google Cloud Console, enable the Gmail API for a project.
2. Create an OAuth Client ID with application type `Desktop app`.
3. Download that JSON file into this repo as `secrets/google-oauth-client.json`.
   This file is not your Gmail password; it only identifies the local MarketLab OAuth app.
4. Authorize MarketLab once:

```bash
./bin/marketlab tools gmail auth --client-secret secrets/google-oauth-client.json
```

By default this opens a browser, asks Google for Gmail read-only access, receives the callback
on `127.0.0.1`, and writes `secrets/gmail-token.json`. That token is what future runs use and
refresh locally. Keep both files under `secrets/`; both `secrets/` and `data/` are gitignored.

If the command runs on a machine without a normal interactive browser, or Google shows a
message like "JavaScript turned off" after the command opens Chrome, use the manual browser
path instead. Pick a fixed callback port and have MarketLab print the `authorization_url`:

```bash
./bin/marketlab tools gmail auth --no-browser --port 8765
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
./bin/marketlab tools gmail bulltard-recap --date 2026-09-01
```

This searches Gmail for the recap, caches it as
`data/inbox/bulltard/recap-YYYY-MM-DD.html`, verifies that it contains a signed Bulltard app
link, and leaves the existing Bulltard parser/ingester to do the rest.

### Bulltard Debug Utilities

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

### Candidate Validation

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
./bin/marketlab data prices fetch-yahoo META,XAR,SRRK,DKS,QXO,SPY,QQQ \
  --start 2025-01-01 \
  --end 2026-08-27
```

This uses the actively maintained `yfinance` package. It stores raw `close` and `adjusted_close`;
MarketLab uses adjusted close for return/outcome calculations when available. Re-fetching an
overlapping date range updates the local price cache; saved snapshots carry the dates, versions,
and provenance used when they were written.

For source-only CBOE volatility-index diagnostics:

```bash
./bin/marketlab data prices fetch-cboe '^VIX9D,^VIX,^VIX3M,^VVIX' \
  --start 2025-01-01 \
  --end 2026-09-08
```

For source-only FRED diagnostics:

```bash
./bin/marketlab data market-series fetch-fred --start 2025-01-01 --end 2026-08-27
```

The older Stooq path remains available as `data prices fetch`, but it may require a Stooq API key:

```bash
./bin/marketlab data prices fetch META,SPY --start 2025-01-01 --end 2026-08-27
```

Or import a local CSV with `Date, Open, High, Low, Close, Volume` columns:

```bash
./bin/marketlab data prices import-csv META ~/Downloads/META.csv --source manual
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

Render a reproducible chart for one saved candidate:

```bash
./bin/marketlab bulltard chart MRVL --date 2026-08-28
```

The opportunity chart shows the candidate versus SPY/QQQ, Bulltard flow-premium event bars,
20d relative strength, the point-in-time validation snapshot, and a separate forward-outcome
table that stays marked `waiting` until enough future local price rows exist.

If you need a manual fallback, pass a local recap file or a small text file containing the
recap's database/app link to the lower-level Bulltard commands. Gmail may wrap the useful Substack
redirect as a `https://www.google.com/url?q=...` link; the tool unwraps that form.

### Reset Local Research Data

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

## Local Research Store

Refresh the local DuckDB store from saved observations and snapshots:

```bash
./bin/marketlab data store refresh
```

Optionally also export each table as Parquet:

```bash
./bin/marketlab data store refresh --parquet-root data/warehouse/parquet
```

Inspect or query the store:

```bash
./bin/marketlab data store tables
./bin/marketlab data store query "select source_date, policy_state, marginal_beta_target from policy_snapshots order by source_date desc limit 10"
```
