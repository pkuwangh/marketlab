import json
from datetime import date, timedelta
from pathlib import Path

from marketlab.bulltard.validation import (
    load_candidate_validation_snapshots,
    validate_bulltard_candidates,
)
from marketlab.prices import DailyPriceObservation, write_price_observations


def test_validate_bulltard_candidates_writes_price_validation_snapshot(
    tmp_path: Path,
) -> None:
    source_date = date(2026, 3, 2)
    observations_root = tmp_path / "observations" / "bulltard"
    price_root = tmp_path / "prices"
    snapshot_root = tmp_path / "snapshots"
    _write_jsonl(
        observations_root / "ranked_option_trades" / "2026-03-02.jsonl",
        [
            {
                "source_date": "2026-03-02",
                "symbol": "META",
                "side": "bullish",
                "score": 10.0,
                "trade_count": 4,
                "premium": 2_500_000.0,
            },
            {
                "source_date": "2026-03-02",
                "symbol": "WEAK",
                "side": "bullish",
                "score": 8.0,
                "trade_count": 3,
                "premium": 1_500_000.0,
            },
            {
                "source_date": "2026-03-02",
                "symbol": "THIN",
                "side": "bullish",
                "score": 7.0,
                "trade_count": 2,
                "premium": 1_000_000.0,
            },
        ],
    )
    _write_jsonl(
        observations_root / "trades_of_interest" / "2026-03-02.jsonl",
        [
            {
                "source_date": "2026-03-02",
                "rank": 1,
                "symbol": "META",
                "note": "Recap interest note.",
            }
        ],
    )
    _write_price_history(
        price_root,
        symbol="META",
        start=date(2026, 1, 1),
        closes=[100 + index for index in range(61)],
        volume=1_000_000,
    )
    _write_price_history(
        price_root,
        symbol="WEAK",
        start=date(2026, 1, 1),
        closes=[200 - index for index in range(61)],
        volume=1_000_000,
    )
    _write_price_history(
        price_root,
        symbol="THIN",
        start=date(2026, 1, 1),
        closes=[50 + index * 0.1 for index in range(61)],
        volume=100_000,
    )
    _write_price_history(
        price_root,
        symbol="SPY",
        start=date(2026, 1, 1),
        closes=[100 + index * 0.2 for index in range(61)],
        volume=10_000_000,
    )
    _write_price_history(
        price_root,
        symbol="QQQ",
        start=date(2026, 1, 1),
        closes=[100 + index * 0.3 for index in range(61)],
        volume=8_000_000,
    )

    result = validate_bulltard_candidates(
        source_date=source_date,
        observations_root=observations_root,
        price_root=price_root,
        snapshot_root=snapshot_root,
        limit=3,
    )

    assert result.snapshot_path == _candidate_snapshot_path(snapshot_root, source_date)
    assert result.snapshot_path.is_file()
    assert [snapshot.symbol for snapshot in result.snapshots] == ["META", "WEAK", "THIN"]
    assert result.snapshots[0].validation_status == "confirm"
    assert result.snapshots[0].bulltard_source == "ranked+interest#1"
    assert result.snapshots[0].return_20d is not None
    assert result.snapshots[0].relative_strength_20d_spy is not None
    assert result.snapshots[1].validation_status == "avoid"
    assert result.snapshots[1].validation_reasons == (
        "weak_trend",
        "negative_relative_strength",
        "below_ma50",
    )
    assert result.snapshots[2].validation_status == "avoid"
    assert result.snapshots[2].validation_reasons == ("thin_underlying",)
    assert result.summary.candidate_count == 3
    assert result.summary.confirm_count == 1
    assert result.summary.watch_count == 0
    assert result.summary.avoid_count == 2
    assert result.summary.thin_underlying_count == 1
    assert "dollar_vol" in result.table
    assert "opt_liq" not in result.table

    loaded = load_candidate_validation_snapshots(
        source_date=source_date,
        snapshot_root=snapshot_root,
    )
    assert loaded == result.snapshots

    legacy_root = tmp_path / "legacy-snapshots"
    legacy_root.mkdir()
    (legacy_root / "2026-03-02.jsonl").write_text(
        "".join(json.dumps(snapshot.to_dict()) + "\n" for snapshot in result.snapshots),
        encoding="utf-8",
    )
    assert (
        load_candidate_validation_snapshots(
            source_date=source_date,
            snapshot_root=legacy_root,
        )
        == result.snapshots
    )


def _candidate_snapshot_path(snapshot_root: Path, source_date: date) -> Path:
    source_date_value = source_date.isoformat()
    return (
        snapshot_root
        / source_date_value
        / "eod"
        / f"{source_date_value}_eod"
        / "bulltard_candidate_validation_rules_v0+candidate_validation_only_v0"
        / "candidate-validation.jsonl"
    )


def _write_price_history(
    price_root: Path,
    *,
    symbol: str,
    start: date,
    closes: list[float],
    volume: int,
) -> None:
    rows = tuple(
        DailyPriceObservation(
            source="fixture",
            source_symbol=symbol.lower(),
            symbol=symbol,
            observed_date=start + timedelta(days=index),
            open=close - 0.5,
            high=close + 1.0,
            low=close - 1.0,
            close=close,
            volume=volume,
        )
        for index, close in enumerate(closes)
    )
    write_price_observations(rows, output_root=price_root)


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
