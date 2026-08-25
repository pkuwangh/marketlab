# MarketLab Implementation Status

`DESIGN.md` is the architecture source of truth. This file tracks the current implementation state
and the next small slices.

## Recent Commits

- `53c94e2` - Initialize marketlab baseline.
- `f846da9` - Add Bulltard recap inspection.
- `0e82e6e` - Track implementation status.
- `9d360ef` - Add local Bulltard archiving.
- `11030cb` - Refocus Bulltard ingest on useful observations.

## Course Correction

`archive-local` was implemented too early and does not solve the real problem. The Bulltard app is
an interface to a subscription database, not something MarketLab should try to mirror. The
archive-first CLI path has been removed from the working tree and replaced with targeted ingest
support for one useful view.

## Implemented

- Python package skeleton with `uv` lockfile.
- Typer CLI exposed as `marketlab`.
- Repo-local `bin/marketlab` symlink.
- Loguru CLI logging via `--log-level`.
- Snapshot identity model.
- Bulltard recap URL extraction from local text/HTML artifacts.
- Gmail `https://www.google.com/url?q=...` unwrap for copied/saved email links.
- Selection of the likely database link when a Gmail export contains many Substack redirects.
- Bulltard ingest planning for `ranked-option-trades`, including view route and intended
  observation output path.
- One-view HTTP retrieval via `httpx.Client(follow_redirects=True)`.
- Temporary debug HTML output under `data/debug/bulltard/...` for parser bring-up.

## Current Useful Commands

```bash
./bin/marketlab --help
./bin/marketlab bulltard
./bin/marketlab bulltard inspect-recap path/to/recap.html
./bin/marketlab bulltard ingest --date 2026-08-24 --view ranked-option-trades path/to/recap.html
```

## Decisions

- Build the shortest end-to-end research loop before adding support infrastructure.
- Use Typer for the CLI and let Typer handle argument parsing directly.
- Use Loguru for operational logs.
- Preserve full temporary URLs in local bring-up logs by default; keep them out of Git and public
  reports.
- Treat Gmail full-page exports as noisy but usable when the database link can be identified by
  nearby context.
- Do not build broad Bulltard crawlers, archive manifests, or storage layers until one targeted
  ingest path produces useful candidate rows.

## Next Slice

Turn the ingest plan into one real Bulltard ingest path:

- Parse structured candidate rows.
- Write local observations under `data/observations/bulltard/...`.
- Report row count and visible failures.
- Keep Playwright out of v0 unless plain HTTP demonstrably fails for that required view.

## Later

- Add another Bulltard view only after the first view proves useful.
- Persist candidate lifecycle records and replay historical candidates.
