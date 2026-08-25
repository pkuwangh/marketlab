"""Parse Bulltard HTML views into structured observations."""

from __future__ import annotations

from datetime import date
from html.parser import HTMLParser

from marketlab.bulltard.models import (
    BulltardView,
    RankedOptionTradeObservation,
    RankedTradeSide,
)


class ParserError(ValueError):
    """Raised when a Bulltard view cannot be parsed into expected observations."""


def parse_ranked_option_trades(
    html: str,
    *,
    source_date: date,
) -> tuple[RankedOptionTradeObservation, ...]:
    """Parse ranked ticker rows from the Bulltard ranked option trades page."""

    parser = _RankedOptionTradesParser(source_date=source_date)
    parser.feed(html)
    rows = tuple(parser.rows)
    if not rows:
        raise ParserError("No ranked option trade rows found")
    return rows


class _RankedOptionTradesParser(HTMLParser):
    def __init__(self, *, source_date: date) -> None:
        super().__init__(convert_charrefs=True)
        self.source_date = source_date
        self.rows: list[RankedOptionTradeObservation] = []
        self._current_side: RankedTradeSide | None = None
        self._panel_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {key.lower(): value for key, value in attrs if value is not None}
        if self._panel_depth:
            self._panel_depth += 1

        if tag.lower() == "div" and _has_class(attr.get("class", ""), "rankings-panel"):
            self._current_side = _parse_side(attr.get("data-panel-key"))
            self._panel_depth = 1
            return

        if tag.lower() != "tr" or self._current_side is None:
            return

        symbol = attr.get("data-symbol")
        if not symbol:
            return

        self.rows.append(
            RankedOptionTradeObservation(
                source_date=self.source_date,
                view=BulltardView.RANKED_OPTION_TRADES,
                side=self._current_side,
                symbol=symbol,
                trade_count=_parse_int(attr, "data-trades"),
                last_trade_date=_parse_date(attr, "data-last-trade"),
                avg_dte=_parse_optional_float(attr, "data-avg-dte"),
                score=_parse_float(attr, "data-score"),
                premium=_parse_float(attr, "data-premium"),
            )
        )

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, _tag: str) -> None:
        if not self._panel_depth:
            return
        self._panel_depth -= 1
        if not self._panel_depth:
            self._current_side = None


def _has_class(class_value: str, expected: str) -> bool:
    return expected in class_value.split()


def _parse_side(value: str | None) -> RankedTradeSide:
    try:
        return RankedTradeSide(value or "")
    except ValueError as exc:
        raise ParserError(f"Unsupported ranked option trade side: {value}") from exc


def _parse_int(attrs: dict[str, str], key: str) -> int:
    value = attrs.get(key)
    if value is None:
        raise ParserError(f"Missing required row attribute: {key}")
    try:
        return int(value)
    except ValueError as exc:
        raise ParserError(f"Invalid integer for {key}: {value}") from exc


def _parse_float(attrs: dict[str, str], key: str) -> float:
    value = attrs.get(key)
    if value is None:
        raise ParserError(f"Missing required row attribute: {key}")
    try:
        return float(value)
    except ValueError as exc:
        raise ParserError(f"Invalid number for {key}: {value}") from exc


def _parse_optional_float(attrs: dict[str, str], key: str) -> float | None:
    value = attrs.get(key)
    if value in (None, ""):
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise ParserError(f"Invalid number for {key}: {value}") from exc


def _parse_date(attrs: dict[str, str], key: str) -> date:
    value = attrs.get(key)
    if value is None:
        raise ParserError(f"Missing required row attribute: {key}")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ParserError(f"Invalid date for {key}: {value}") from exc
