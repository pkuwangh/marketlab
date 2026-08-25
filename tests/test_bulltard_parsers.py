from datetime import date
from pathlib import Path

import pytest

from marketlab.bulltard.models import BulltardView, RankedTradeSide
from marketlab.bulltard.parsers import ParserError, parse_ranked_option_trades

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
