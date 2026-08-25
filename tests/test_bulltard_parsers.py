from datetime import date
from pathlib import Path

import pytest

from marketlab.bulltard.models import BulltardView, RankedTradeSide
from marketlab.bulltard.parsers import (
    ParserError,
    parse_ranked_option_trades,
    parse_ticker_flow_history,
)

FIXTURE_DIR = Path(__file__).parent / "fixtures" / "bulltard"


def test_parse_ranked_option_trades_reads_bullish_and_bearish_rows() -> None:
    html = (FIXTURE_DIR / "ranked_option_trades.html").read_text(encoding="utf-8")

    rows = parse_ranked_option_trades(html, source_date=date(2026, 8, 25))

    assert len(rows) == 3
    assert rows[0].to_dict() == {
        "source": "bulltard",
        "source_date": "2026-08-25",
        "view": BulltardView.RANKED_OPTION_TRADES.value,
        "side": RankedTradeSide.BULLISH.value,
        "symbol": "INTC",
        "trade_count": 31,
        "last_trade_date": "2026-08-25",
        "avg_dte": 180.1153846153846,
        "score": 19.0,
        "premium": 74508194.5,
    }
    assert rows[1].symbol == "BYD"
    assert rows[1].avg_dte is None
    assert rows[2].side == RankedTradeSide.BEARISH
    assert rows[2].score == -2.0


def test_parse_ranked_option_trades_fails_when_rows_are_absent() -> None:
    with pytest.raises(ParserError, match="No ranked option trade rows found"):
        parse_ranked_option_trades("<html></html>", source_date=date(2026, 8, 25))


def test_parse_ticker_flow_history_reads_visible_table_rows() -> None:
    html = (FIXTURE_DIR / "ticker_intc.html").read_text(encoding="utf-8")

    rows = parse_ticker_flow_history(html, source_date=date(2026, 8, 25), symbol="intc")

    assert len(rows) == 3
    assert rows[0].to_dict() == {
        "source": "bulltard",
        "source_date": "2026-08-25",
        "view": "ticker-flow-history",
        "symbol": "INTC",
        "traded_at": "2026-08-25T15:46",
        "order_type": "Calls Bought",
        "side": RankedTradeSide.BULLISH.value,
        "contract": "90C",
        "contract_type": "call",
        "expiry": "2026-09-04",
        "contracts": 2500,
        "premium": 808000.0,
        "is_older": False,
    }
    assert rows[1].contract == "85/140P"
    assert rows[1].contract_type == "put"
    assert rows[1].contracts == 4400
    assert rows[1].premium == 6460000.0
    assert rows[1].is_older is True
    assert rows[2].side == RankedTradeSide.BEARISH
    assert rows[2].premium == 1000000.0


def test_parse_ticker_flow_history_fails_when_rows_are_absent() -> None:
    with pytest.raises(ParserError, match="No ticker flow-history rows found"):
        parse_ticker_flow_history("<html></html>", source_date=date(2026, 8, 25), symbol="INTC")
