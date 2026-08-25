# MarketLab Implementation Status

`DESIGN.md` is the architecture source of truth. This file tracks the current implementation state
and the next small slices.

## Current Commits

- `53c94e2` - Initialize marketlab baseline.
- `f846da9` - Add Bulltard recap inspection.

## Implemented

- Python package skeleton with `uv` lockfile.
- Typer CLI exposed as `marketlab`.
- Repo-local `bin/marketlab` symlink.
- Loguru CLI logging via `--log-level`.
- Snapshot identity model.
- Bulltard capture manifest and raw artifact models.
- Bulltard recap URL extraction from local text/HTML artifacts.
- Gmail `https://www.google.com/url?q=...` unwrap for copied/saved email links.
- Selection of the likely database link when a Gmail export contains many Substack redirects.
- Bulltard app route discovery and classification for the v0 crawl boundary.
- Local Bulltard artifact archiving into `data/raw/bulltard/<date>/`.
- Local capture manifest generation with SHA-256 hashes and byte counts.
- Local archive overwrite protection unless `--force` is passed.

## Current Commands

```bash
./bin/marketlab --help
./bin/marketlab bulltard
./bin/marketlab bulltard inspect-recap path/to/recap.html
./bin/marketlab bulltard archive-local --date 2026-08-24 --artifact recap=path/to/recap.html
```

## Decisions

- Keep early functionality local-only until source artifact semantics are solid.
- Use Typer for the CLI and let Typer handle argument parsing directly.
- Use Loguru for operational logs.
- Preserve full local capture URLs by default; do not build premature redaction into the normal path.
- Treat Gmail full-page exports as noisy but usable when the database link can be identified by
  nearby context.
- Do not add live HTTP capture until local parsing and archive behavior are stable.

## Next Slice

Implement live-but-bounded HTTP capture:

- Read a local recap artifact for the requested date.
- Extract the signed Substack redirect.
- Use one short-lived `httpx.Client(follow_redirects=True)`.
- Fetch the bootstrap page and archive it as `home.html`.
- Discover same-origin research routes from the archived page.
- Keep failures visible in `capture_manifest.json`.
- Keep Playwright out of v0 unless plain HTTP demonstrably fails for a required route.

## Later

- Fetch bounded same-origin research pages.
- Parse normalized Bulltard tables/signals from archived pages.
- Persist candidate lifecycle records and replay historical candidates.
