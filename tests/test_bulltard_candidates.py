import json
from datetime import date
from pathlib import Path

import pytest

from marketlab.bulltard.candidates import (
    CandidateReviewError,
    format_candidate_reviews,
    load_candidate_reviews,
)


def test_load_candidate_reviews_attaches_available_ticker_flow(tmp_path: Path) -> None:
    observations_root = tmp_path / "observations" / "bulltard"
    ranked_path = observations_root / "ranked_option_trades" / "2026-08-26.jsonl"
    flow_path = observations_root / "ticker_flow" / "INTC" / "2026-08-26.jsonl"
    _write_jsonl(
        ranked_path,
        [
            {
                "source_date": "2026-08-26",
                "symbol": "BYD",
                "side": "bullish",
                "score": 1.0,
                "trade_count": 1,
                "premium": 125100.0,
            },
            {
                "source_date": "2026-08-26",
                "symbol": "INTC",
                "side": "bullish",
                "score": 19.0,
                "trade_count": 31,
                "premium": 74508194.5,
            },
            {
                "source_date": "2026-08-26",
                "symbol": "AKAM",
                "side": "bearish",
                "score": -2.0,
                "trade_count": 2,
                "premium": 2433676.0,
            },
        ],
    )
    _write_jsonl(
        flow_path,
        [
            {
                "symbol": "INTC",
                "traded_at": "2026-08-26T09:45",
                "order_type": "Calls Bought",
                "contract": "90C",
                "expiry": "2026-09-04",
                "premium": 808000.0,
            },
            {
                "symbol": "INTC",
                "traded_at": "2026-08-26T10:15",
                "order_type": "Puts Sold",
                "contract": "100P",
                "expiry": "2027-06-17",
                "premium": 2650000.0,
            },
        ],
    )

    reviews = load_candidate_reviews(
        source_date=date(2026, 8, 26),
        observations_root=observations_root,
        limit=2,
    )

    assert [review.symbol for review in reviews] == ["INTC", "AKAM"]
    assert reviews[0].detail_rows == 2
    assert reviews[0].latest_flow is not None
    assert reviews[0].latest_flow["contract"] == "100P"
    assert reviews[0].top_flow is not None
    assert reviews[0].top_flow["premium"] == 2650000.0
    assert reviews[1].detail_rows == 0
    assert reviews[1].latest_flow is None


def test_format_candidate_reviews_outputs_compact_table(tmp_path: Path) -> None:
    observations_root = tmp_path / "observations" / "bulltard"
    ranked_path = observations_root / "ranked_option_trades" / "2026-08-26.jsonl"
    flow_path = observations_root / "ticker_flow" / "INTC" / "2026-08-26.jsonl"
    _write_jsonl(
        ranked_path,
        [
            {
                "source_date": "2026-08-26",
                "symbol": "INTC",
                "side": "bullish",
                "score": 19.0,
                "trade_count": 31,
                "premium": 74508194.5,
            }
        ],
    )
    _write_jsonl(
        flow_path,
        [
            {
                "symbol": "INTC",
                "traded_at": "2026-08-26T10:15",
                "order_type": "Puts Sold",
                "contract": "100P",
                "expiry": "2027-06-17",
                "premium": 2650000.0,
            }
        ],
    )
    reviews = load_candidate_reviews(
        source_date=date(2026, 8, 26),
        observations_root=observations_root,
        limit=10,
    )

    output = format_candidate_reviews(reviews)

    assert "symbol" in output
    assert "INTC" in output
    assert "$74.5M" in output
    assert "2026-08-26 10:15 Puts Sold 100P 2027-06-17 $2.6M" in output


def test_load_candidate_reviews_fails_when_ranked_file_is_missing(tmp_path: Path) -> None:
    with pytest.raises(CandidateReviewError, match="Ranked observations not found"):
        load_candidate_reviews(
            source_date=date(2026, 8, 26),
            observations_root=tmp_path / "observations" / "bulltard",
            limit=10,
        )


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
