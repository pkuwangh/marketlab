from copy import deepcopy
from dataclasses import replace
from datetime import date, timedelta

import pytest
from test_regime import _snapshot, _write_price_history

from marketlab.regime import (
    _redeploy_path_reading,
    compute_regime_redeploy_outcomes,
    write_regime_snapshot,
)

DAY = date(2026, 1, 2)
PATHS = {"redeploy-washout": "washout", "redeploy-confirm": "pullback"}


def snapshot():
    return replace(
        _snapshot(source_date=DAY, regime="neutral", score=0),
        lifecycle={
            "gates": {
                "redeploy-washout": dict(
                    setup=True,
                    release=True,
                    confirmation=True,
                    opportunity=True,
                    funding_clear=True,
                ),
                "redeploy-confirm": dict(
                    enabled=True,
                    setup=True,
                    price_recovery=True,
                    confirmation=True,
                    opportunity=True,
                    funding_clear=True,
                ),
            },
            "washout": {"id": "washout:prior", "consumed": False, "release": 0.06},
            "pullback": {"id": "pullback:prior", "consumed": False},
            "eligible_candidates": [],
            "supporting": [],
            "conflict": False,
        },
    )


@pytest.mark.parametrize("path", PATHS)
@pytest.mark.parametrize(
    "funding,expected", [(False, "funding_blocked_only"), (None, "funding_unknown_only")]
)
def test_funding_only_requires_every_other_entry_requirement(path, funding, expected):
    snap = snapshot()
    snap.lifecycle["gates"][path]["funding_clear"] = funding
    assert _redeploy_path_reading(snap, path)[0] == expected

    additional = deepcopy(snap)
    additional.lifecycle["gates"][path]["confirmation"] = None
    assert _redeploy_path_reading(additional, path)[0] == "multiple_blockers"

    used = deepcopy(snap)
    used.lifecycle[PATHS[path]]["consumed"] = True
    status, gates, _ = _redeploy_path_reading(used, path)
    assert status == "consumed" and gates["unused_episode"] is False
    assert gates["funding_clear"] is funding  # Not hidden by the primary status.

    inactive = deepcopy(snap)
    inactive.lifecycle["gates"][path]["setup"] = False
    status, _, episode = _redeploy_path_reading(inactive, path)
    assert status == "no_setup" and episode is None

    opposed = deepcopy(snap)
    opposed.lifecycle["eligible_candidates"] = ["protect-break"]
    assert _redeploy_path_reading(opposed, path)[0] == "multiple_blockers"


@pytest.mark.parametrize("path", PATHS)
def test_selected_entry_is_not_misclassified_as_consumed(path):
    snap = replace(snapshot(), action_state=path)
    snap.lifecycle[PATHS[path]]["consumed"] = True
    snap.lifecycle["eligible_candidates"] = [path]
    status, gates, _ = _redeploy_path_reading(snap, path)
    assert status == "action" and all(value is True for value in gates.values())


def test_overlap_priority_support_and_opposing_conflict():
    snap = replace(snapshot(), action_state="redeploy-washout")
    snap.lifecycle["eligible_candidates"] = list(PATHS)
    snap.lifecycle["pullback"]["consumed"] = True
    assert _redeploy_path_reading(snap, "redeploy-confirm")[0] == "overlap"

    unknown = deepcopy(snap)
    unknown.lifecycle["eligible_candidates"] = ["redeploy-washout"]
    unknown.lifecycle["pullback"]["consumed"] = False
    unknown.lifecycle["gates"]["redeploy-confirm"]["funding_clear"] = None
    assert _redeploy_path_reading(unknown, "redeploy-confirm")[0] == "multiple_blockers"

    snap = snapshot()
    snap.lifecycle["supporting"] = ["redeploy-washout"]
    snap.lifecycle["washout"]["consumed"] = True
    assert _redeploy_path_reading(snap, "redeploy-washout")[0] == "already_held"

    snap = snapshot()
    snap.lifecycle["eligible_candidates"] = ["protect-break", "redeploy-washout"]
    snap.lifecycle["conflict"] = True
    assert _redeploy_path_reading(snap, "redeploy-washout")[0] == "conflict"


def test_report_covers_both_paths_preserves_zero_rows_and_counts_baseline_once(tmp_path):
    root, prices = tmp_path / "snapshots", tmp_path / "prices"
    first = snapshot()
    first.lifecycle["washout"]["consumed"] = True
    first.lifecycle["gates"]["redeploy-washout"]["funding_clear"] = None
    first.lifecycle["gates"]["redeploy-confirm"]["price_recovery"] = False
    second = replace(
        snapshot(),
        source_date=DAY + timedelta(days=1),
        price_date=DAY + timedelta(days=1),
        action_state="redeploy-washout",
    )
    second.lifecycle["washout"]["consumed"] = True
    second.lifecycle["eligible_candidates"] = ["redeploy-washout"]
    second.lifecycle["gates"]["redeploy-confirm"]["price_recovery"] = None
    paths = [write_regime_snapshot(s, snapshot_root=root) for s in (first, second)]
    original = [p.read_bytes() for p in paths]
    for symbol in ("SPY", "QQQ"):
        _write_price_history(prices, symbol=symbol, start=DAY, closes=[100, 102, 104])
    result = compute_regime_redeploy_outcomes(
        start_date=DAY,
        end_date=DAY + timedelta(days=1),
        snapshot_root=root,
        price_root=prices,
        horizons=(1, 20),
    )
    assert len(result.outcomes) == 8  # Two days * two paths * two horizons.
    by_bucket = {(r.bucket, r.horizon_days): r for r in result.summary_rows}
    assert by_bucket["all", 1].redeploy_count == 2
    assert by_bucket["all", 20].available_count == 0
    for path in PATHS:
        assert (
            sum(
                row.redeploy_count
                for row in result.summary_rows
                if row.horizon_days == 1 and row.bucket.startswith(path + ":")
            )
            == 2
        )
    assert by_bucket["redeploy-confirm:action", 1].redeploy_count == 0
    assert by_bucket["redeploy-confirm:waiting:price_recovery", 1].redeploy_count == 1
    # The other path's selected entry also blocks priority on the second day.
    assert by_bucket["redeploy-confirm:multiple_blockers", 1].redeploy_count == 1
    assert by_bucket["redeploy-washout:action", 1].avg_washout_release == 0.06
    assert by_bucket["redeploy-washout:consumed", 1].episode_count == 1
    assert by_bucket["redeploy-washout:funding_unknown_only", 1].redeploy_count == 0
    assert "redeploy-confirm:action" in result.table
    assert "20d" in result.table and "Gate diagnostics:" in result.table
    assert "funding_blocked_or_unknown" not in result.table
    funding_line = next(
        line.split()
        for line in result.table.splitlines()
        if line.startswith("redeploy-washout ") and "funding_clear" in line
    )
    assert funding_line[2:] == ["2", "1", "0", "1", "0", "0"]
    assert all(
        o.washout_setup_score is None for o in result.outcomes if o.path == "redeploy-confirm"
    )
    assert [p.read_bytes() for p in paths] == original
    from marketlab.cli import _regime_redeploy_outcome_report_text

    report = _regime_redeploy_outcome_report_text(result)
    assert "regime_redeploy_day_count=2" in report
    assert "regime_redeploy_path_count=2" in report
    assert "regime_redeploy_outcome_count=8" in report


def test_single_unknown_price_confirmation_is_not_a_known_failure():
    snap = snapshot()
    snap.lifecycle["gates"]["redeploy-confirm"]["price_recovery"] = None
    assert _redeploy_path_reading(snap, "redeploy-confirm")[0] == "unknown:price_recovery"
