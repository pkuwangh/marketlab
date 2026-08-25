"""Parse Bulltard HTML views into structured observations."""

from __future__ import annotations

import re
from datetime import date, datetime
from html.parser import HTMLParser

from marketlab.bulltard.models import (
    BulltardView,
    RankedOptionTradeObservation,
    RankedTradeSide,
    TickerFlowObservation,
)

_MONEY_RE = re.compile(r"^\$?([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*([KMB])?$", re.IGNORECASE)


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


def parse_ticker_flow_history(
    html: str,
    *,
    source_date: date,
    symbol: str,
) -> tuple[TickerFlowObservation, ...]:
    """Parse option-flow rows from a Bulltard ticker detail page."""

    parser = _TickerFlowHistoryParser(source_date=source_date, symbol=symbol.strip().upper())
    parser.feed(html)
    rows = tuple(parser.rows)
    if not rows:
        raise ParserError("No ticker flow-history rows found")
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


class _TickerFlowHistoryParser(HTMLParser):
    def __init__(self, *, source_date: date, symbol: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source_date = source_date
        self.symbol = symbol
        self.rows: list[TickerFlowObservation] = []
        self._table_depth = 0
        self._tbody_depth = 0
        self._row_depth = 0
        self._cell_depth = 0
        self._current_cells: list[str] | None = None
        self._current_cell_text: list[str] | None = None
        self._current_row_is_older = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        attr = {key.lower(): value for key, value in attrs if value is not None}
        self._increment_active_depths()

        if tag == "table" and attr.get("id") == "flow-history-table":
            self._table_depth = 1
            return

        if not self._table_depth:
            return

        if tag == "tbody":
            self._tbody_depth = 1
            return

        if not self._tbody_depth:
            return

        if tag == "tr" and not self._row_depth:
            self._row_depth = 1
            self._current_cells = []
            self._current_row_is_older = _has_class(attr.get("class", ""), "flow-row-older")
            return

        if tag == "td" and self._row_depth and not self._cell_depth:
            self._cell_depth = 1
            self._current_cell_text = []

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self._current_cell_text is not None:
            self._current_cell_text.append(data)

    def handle_endtag(self, _tag: str) -> None:
        if self._cell_depth:
            self._cell_depth -= 1
            if not self._cell_depth:
                if self._current_cells is None or self._current_cell_text is None:
                    raise ParserError("Ticker flow parser reached a cell without row state")
                self._current_cells.append(_normalize_text("".join(self._current_cell_text)))
                self._current_cell_text = None

        if self._row_depth:
            self._row_depth -= 1
            if not self._row_depth:
                self._finish_row()

        if self._tbody_depth:
            self._tbody_depth -= 1

        if self._table_depth:
            self._table_depth -= 1

    def _increment_active_depths(self) -> None:
        if self._table_depth:
            self._table_depth += 1
        if self._tbody_depth:
            self._tbody_depth += 1
        if self._row_depth:
            self._row_depth += 1
        if self._cell_depth:
            self._cell_depth += 1

    def _finish_row(self) -> None:
        cells = self._current_cells or []
        if len(cells) != 6:
            raise ParserError(f"Expected 6 ticker flow columns, found {len(cells)}")
        self.rows.append(
            TickerFlowObservation(
                source_date=self.source_date,
                symbol=self.symbol,
                traded_at=_parse_datetime_text(cells[0], "trade date"),
                order_type=cells[1],
                side=_parse_order_side(cells[1]),
                contract=cells[2],
                contract_type=_parse_contract_type(cells[2]),
                expiry=_parse_date_text(cells[3], "expiry"),
                contracts=_parse_int_text(cells[4], "contracts"),
                premium=_parse_money_text(cells[5], "premium"),
                is_older=self._current_row_is_older,
            )
        )
        self._current_cells = None
        self._current_row_is_older = False


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


def _normalize_text(value: str) -> str:
    return " ".join(value.split())


def _parse_datetime_text(value: str, label: str) -> datetime:
    try:
        return datetime.fromisoformat(value.replace(" ", "T"))
    except ValueError as exc:
        raise ParserError(f"Invalid datetime for {label}: {value}") from exc


def _parse_date_text(value: str, label: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ParserError(f"Invalid date for {label}: {value}") from exc


def _parse_int_text(value: str, label: str) -> int:
    normalized = value.replace(",", "")
    try:
        return int(normalized)
    except ValueError as exc:
        raise ParserError(f"Invalid integer for {label}: {value}") from exc


def _parse_money_text(value: str, label: str) -> float:
    normalized = value.replace(",", "").strip()
    match = _MONEY_RE.fullmatch(normalized)
    if not match:
        raise ParserError(f"Invalid money value for {label}: {value}")
    multiplier = {
        None: 1.0,
        "K": 1_000.0,
        "M": 1_000_000.0,
        "B": 1_000_000_000.0,
    }[match.group(2).upper() if match.group(2) else None]
    return float(match.group(1)) * multiplier


def _parse_order_side(value: str) -> RankedTradeSide | None:
    match value.lower():
        case "calls bought" | "puts sold":
            return RankedTradeSide.BULLISH
        case "puts bought" | "calls sold":
            return RankedTradeSide.BEARISH
        case _:
            return None


def _parse_contract_type(value: str) -> str | None:
    normalized = value.strip().upper()
    if normalized.endswith("C"):
        return "call"
    if normalized.endswith("P"):
        return "put"
    return None
