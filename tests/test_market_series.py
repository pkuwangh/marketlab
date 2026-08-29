from datetime import date
from pathlib import Path

import httpx
import pytest

from marketlab.market_series import (
    MarketSeriesError,
    MarketSeriesObservation,
    fetch_and_write_fred_series,
    load_market_series_history,
    parse_fred_graph_csv,
    write_market_series_observations,
)


def test_parse_fred_graph_csv_skips_missing_values_and_sets_availability() -> None:
    rows = parse_fred_graph_csv(
        "observation_date,BAMLH0A0HYM2\n2026-08-24,2.69\n2026-08-25,.\n2026-08-26,2.67\n",
        series_id="bamlh0a0hym2",
        start_date=date(2026, 8, 24),
        end_date=date(2026, 8, 26),
    )

    assert [row.value for row in rows] == [2.69, 2.67]
    assert rows[0].series_id == "BAMLH0A0HYM2"
    assert rows[0].unit == "percent_level"
    assert rows[0].availability_date == date(2026, 8, 25)


def test_parse_fred_graph_csv_supports_date_header() -> None:
    rows = parse_fred_graph_csv(
        "DATE,NFCI\n2026-08-21,-0.566\n",
        series_id="NFCI",
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
    )

    assert rows[0].observed_date == date(2026, 8, 21)
    assert rows[0].availability_date == date(2026, 8, 26)
    assert rows[0].unit == "index"


def test_parse_fred_graph_csv_rejects_missing_date_column() -> None:
    with pytest.raises(MarketSeriesError, match="observation_date"):
        parse_fred_graph_csv(
            "timestamp,DGS10\n2026-08-27,4.67\n",
            series_id="DGS10",
            start_date=date(2026, 8, 1),
            end_date=date(2026, 8, 31),
        )


def test_fetch_and_write_fred_series_merges_deduped_series(tmp_path: Path) -> None:
    requested_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        series_id = request.url.params["id"]
        return httpx.Response(
            200,
            text=(f"observation_date,{series_id}\n2026-08-26,2.67\n2026-08-27,2.63\n"),
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    output_root = tmp_path / "series"

    results = fetch_and_write_fred_series(
        series_ids=("bamlh0a0hym2", "BAMLH0A0HYM2", "DGS10"),
        start_date=date(2026, 8, 26),
        end_date=date(2026, 8, 27),
        output_root=output_root,
        client=client,
    )

    assert [result.series_id for result in results] == ["BAMLH0A0HYM2", "DGS10"]
    assert len(requested_urls) == 2
    assert "id=BAMLH0A0HYM2" in requested_urls[0]
    assert (output_root / "BAMLH0A0HYM2.jsonl").is_file()
    assert (output_root / "DGS10.jsonl").is_file()
    rows = load_market_series_history(series_id="BAMLH0A0HYM2", observations_root=output_root)
    assert [row.value for row in rows] == [2.67, 2.63]


def test_write_market_series_observations_merges_by_observed_date(tmp_path: Path) -> None:
    output_root = tmp_path / "series"
    first = MarketSeriesObservation(
        source="fixture",
        source_series_id="NFCI",
        series_id="NFCI",
        observed_date=date(2026, 8, 14),
        availability_date=date(2026, 8, 19),
        value=-0.561,
        unit="index",
    )
    second = MarketSeriesObservation(
        source="fixture",
        source_series_id="NFCI",
        series_id="NFCI",
        observed_date=date(2026, 8, 21),
        availability_date=date(2026, 8, 26),
        value=-0.566,
        unit="index",
    )

    write_market_series_observations((first,), output_root=output_root)
    write_market_series_observations((first, second), output_root=output_root)

    rows = load_market_series_history(series_id="NFCI", observations_root=output_root)
    assert [row.observed_date for row in rows] == [date(2026, 8, 14), date(2026, 8, 21)]
    assert [row.value for row in rows] == [-0.561, -0.566]
