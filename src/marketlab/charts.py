"""Reproducible HTML/SVG research charts."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta
from html import escape
from pathlib import Path

from loguru import logger

from marketlab.market_signals import (
    DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT,
    MarketSignal,
    MarketSignalError,
    load_market_signal_snapshot,
)
from marketlab.prices import (
    DEFAULT_PRICE_OBSERVATIONS_ROOT,
    DailyPriceObservation,
    PriceDataError,
    dedupe_symbols,
    load_price_history,
)
from marketlab.regime import (
    DEFAULT_REGIME_SNAPSHOT_ROOT,
    RegimeError,
    RegimeSnapshot,
    load_regime_snapshot,
)

DEFAULT_CHART_REPORT_ROOT = Path("reports")
REGIME_CHART_VERSION = "regime_chart_v0"


class ChartError(ValueError):
    """Raised when a chart cannot be rendered."""


@dataclass(frozen=True, slots=True)
class RegimeChartResult:
    """Result of rendering one regime chart."""

    start_date: date
    end_date: date
    output_path: Path
    price_symbols: tuple[str, ...]
    price_point_count: int
    regime_snapshot_count: int
    market_signal_count: int
    chart_version: str = REGIME_CHART_VERSION


def render_regime_chart(
    *,
    start_date: date,
    end_date: date,
    symbol: str = "SPY",
    comparison_symbol: str | None = "QQQ",
    price_root: Path = DEFAULT_PRICE_OBSERVATIONS_ROOT,
    regime_snapshot_root: Path = DEFAULT_REGIME_SNAPSHOT_ROOT,
    market_signal_snapshot_root: Path = DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT,
    output_path: Path | None = None,
) -> RegimeChartResult:
    """Render a regime chart from saved point-in-time snapshots."""

    if end_date < start_date:
        raise ChartError("Chart end date must be on or after start date")

    requested_symbols = tuple(value for value in (symbol, comparison_symbol) if value)
    price_symbols = dedupe_symbols(requested_symbols)
    price_histories = {
        symbol: _price_rows_in_range(
            symbol=symbol,
            price_root=price_root,
            start_date=start_date,
            end_date=end_date,
        )
        for symbol in price_symbols
    }
    primary_history = price_histories[price_symbols[0]]
    if not primary_history:
        raise ChartError(
            f"No {price_symbols[0]} price observations found from {start_date} to {end_date}"
        )

    snapshots = _load_regime_snapshots_in_range(
        start_date=start_date,
        end_date=end_date,
        snapshot_root=regime_snapshot_root,
    )
    if not snapshots:
        raise ChartError(f"No regime snapshots found from {start_date} to {end_date}")

    signals_by_date = _load_market_signals_in_range(
        start_date=start_date,
        end_date=end_date,
        snapshot_root=market_signal_snapshot_root,
    )
    signals = tuple(signal for rows in signals_by_date.values() for signal in rows)
    resolved_output_path = output_path or _default_regime_chart_path(
        start_date=start_date,
        end_date=end_date,
    )
    html = _render_regime_chart_html(
        start_date=start_date,
        end_date=end_date,
        price_histories=price_histories,
        snapshots=snapshots,
        signals_by_date=signals_by_date,
        price_root=price_root,
        regime_snapshot_root=regime_snapshot_root,
        market_signal_snapshot_root=market_signal_snapshot_root,
    )
    resolved_output_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_output_path.write_text(html, encoding="utf-8")

    result = RegimeChartResult(
        start_date=start_date,
        end_date=end_date,
        output_path=resolved_output_path,
        price_symbols=price_symbols,
        price_point_count=sum(len(rows) for rows in price_histories.values()),
        regime_snapshot_count=len(snapshots),
        market_signal_count=len(signals),
    )
    logger.bind(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        output_path=str(resolved_output_path),
        price_symbols=price_symbols,
        price_point_count=result.price_point_count,
        regime_snapshot_count=result.regime_snapshot_count,
        market_signal_count=result.market_signal_count,
    ).success("Rendered regime chart")
    return result


def _render_regime_chart_html(
    *,
    start_date: date,
    end_date: date,
    price_histories: dict[str, tuple[DailyPriceObservation, ...]],
    snapshots: tuple[RegimeSnapshot, ...],
    signals_by_date: dict[date, tuple[MarketSignal, ...]],
    price_root: Path,
    regime_snapshot_root: Path,
    market_signal_snapshot_root: Path,
) -> str:
    chart_svg = _render_regime_chart_svg(
        start_date=start_date,
        end_date=end_date,
        price_histories=price_histories,
        snapshots=snapshots,
        signals_by_date=signals_by_date,
    )
    latest_snapshot = snapshots[-1]
    latest_signals = signals_by_date.get(latest_snapshot.source_date, ())
    signal_rows = _latest_signal_rows(latest_signals)
    escaped_start = escape(start_date.isoformat())
    escaped_end = escape(end_date.isoformat())
    escaped_price_root = escape(str(price_root))
    escaped_regime_root = escape(str(regime_snapshot_root))
    escaped_signal_root = escape(str(market_signal_snapshot_root))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MarketLab Regime Chart {escaped_start} to {escaped_end}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #172026;
      --muted: #5f6c72;
      --grid: #d8dee2;
      --panel: #f7f9fa;
      --line-spy: #1b6ca8;
      --line-qqq: #7a4cc2;
      --stretch: #c25a17;
      --washout: #087f8c;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      background: #ffffff;
      font-family:
        ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont,
        "Segoe UI", sans-serif;
    }}
    main {{
      max-width: 1240px;
      margin: 0 auto;
      padding: 24px;
    }}
    h1 {{
      margin: 0 0 4px;
      font-size: 24px;
      font-weight: 700;
      letter-spacing: 0;
    }}
    .meta {{
      margin: 0 0 18px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.5;
    }}
    .chart-shell {{
      border: 1px solid #d6dde1;
      border-radius: 6px;
      overflow-x: auto;
      background: #ffffff;
    }}
    svg {{
      display: block;
      width: 100%;
      min-width: 980px;
      height: auto;
    }}
    table {{
      width: 100%;
      margin-top: 18px;
      border-collapse: collapse;
      font-size: 13px;
    }}
    th, td {{
      padding: 8px 10px;
      border-bottom: 1px solid #e3e7ea;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      font-size: 12px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0;
      background: #f5f7f8;
    }}
    .empty {{
      margin-top: 18px;
      color: var(--muted);
      font-size: 13px;
    }}
  </style>
</head>
<body>
<main>
  <h1>MarketLab Regime Chart</h1>
  <p class="meta">
    Date range: {escaped_start} to {escaped_end}.
    Chart version: {REGIME_CHART_VERSION}.
    Sources: prices={escaped_price_root}, regimes={escaped_regime_root},
    signals={escaped_signal_root}.
  </p>
  <div class="chart-shell">
    {chart_svg}
  </div>
  <h2>Latest Market Signals</h2>
  {signal_rows}
</main>
</body>
</html>
"""


def _render_regime_chart_svg(
    *,
    start_date: date,
    end_date: date,
    price_histories: dict[str, tuple[DailyPriceObservation, ...]],
    snapshots: tuple[RegimeSnapshot, ...],
    signals_by_date: dict[date, tuple[MarketSignal, ...]],
) -> str:
    width = 1180
    left = 82
    right = 30
    top = 44
    gap = 36
    price_panel = _Panel(top=top, height=230, title="Indexed close")
    pressure_panel = _Panel(
        top=price_panel.bottom + gap,
        height=150,
        title="Stretch / washout pressure",
    )
    component_panel = _Panel(
        top=pressure_panel.bottom + gap,
        height=160,
        title="Regime component scores",
    )
    signal_panel = _Panel(
        top=component_panel.bottom + gap,
        height=160,
        title="Market signal family scores",
    )
    height = signal_panel.bottom + 62
    plot_width = width - left - right

    x_min, x_max = _date_domain(
        start_date=start_date,
        end_date=end_date,
        price_histories=price_histories,
        snapshots=snapshots,
    )
    x_scale = _x_scale(x_min=x_min, x_max=x_max, left=left, plot_width=plot_width)
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="MarketLab regime chart">',
        _svg_defs(),
        _text(left, 24, f"{start_date.isoformat()} to {end_date.isoformat()}", css_class="title"),
    ]
    for panel in (price_panel, pressure_panel, component_panel, signal_panel):
        parts.append(_panel_background(left=left, width=plot_width, panel=panel))
        parts.append(_panel_title(left=left, panel=panel))
        parts.extend(_x_axis_labels(x_min=x_min, x_max=x_max, x_scale=x_scale, panel=panel))

    parts.extend(
        _action_backgrounds(
            snapshots=snapshots,
            x_scale=x_scale,
            x_min=x_min,
            x_max=x_max,
            y=price_panel.top,
            height=signal_panel.bottom - price_panel.top,
        )
    )
    parts.extend(
        _draw_price_panel(
            price_histories=price_histories,
            x_scale=x_scale,
            panel=price_panel,
            left=left,
            plot_width=plot_width,
        )
    )
    parts.extend(
        _draw_pressure_panel(
            snapshots=snapshots,
            x_scale=x_scale,
            panel=pressure_panel,
            left=left,
            plot_width=plot_width,
        )
    )
    parts.extend(
        _draw_component_panel(
            snapshots=snapshots,
            x_scale=x_scale,
            panel=component_panel,
            left=left,
            plot_width=plot_width,
        )
    )
    parts.extend(
        _draw_signal_panel(
            snapshots=snapshots,
            signals_by_date=signals_by_date,
            x_scale=x_scale,
            panel=signal_panel,
            left=left,
            plot_width=plot_width,
        )
    )
    parts.append(_legend(width=width, y=height - 28))
    parts.append(_svg_style())
    parts.append("</svg>")
    return "\n".join(parts)


@dataclass(frozen=True, slots=True)
class _Panel:
    top: int
    height: int
    title: str

    @property
    def bottom(self) -> int:
        return self.top + self.height


def _draw_price_panel(
    *,
    price_histories: dict[str, tuple[DailyPriceObservation, ...]],
    x_scale: Callable[[date], float],
    panel: _Panel,
    left: int,
    plot_width: int,
) -> list[str]:
    indexed_series = {
        symbol: _indexed_price_series(rows) for symbol, rows in price_histories.items()
    }
    values = [value for series in indexed_series.values() for _date, value in series]
    if not values:
        return []
    lower = min(values)
    upper = max(values)
    if lower == upper:
        lower -= 1.0
        upper += 1.0
    else:
        pad = (upper - lower) * 0.08
        lower -= pad
        upper += pad
    y_scale = _y_scale(lower=lower, upper=upper, panel=panel)
    parts = _y_axis_labels(
        values=_ticks(lower, upper, 5),
        formatter=lambda value: f"{value:.0f}",
        y_scale=y_scale,
        left=left,
        plot_width=plot_width,
        panel=panel,
    )
    colors = ("#1b6ca8", "#7a4cc2", "#2f8f46", "#8a5a00")
    for index, (symbol, series) in enumerate(indexed_series.items()):
        color = colors[index % len(colors)]
        path = _line_path(series, x_scale=x_scale, y_scale=y_scale)
        if path:
            parts.append(
                f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.4">'
                f"<title>{escape(symbol)} indexed close</title></path>"
            )
        parts.extend(
            _point_markers(series, x_scale=x_scale, y_scale=y_scale, color=color, label=symbol)
        )
    return parts


def _draw_pressure_panel(
    *,
    snapshots: tuple[RegimeSnapshot, ...],
    x_scale: Callable[[date], float],
    panel: _Panel,
    left: int,
    plot_width: int,
) -> list[str]:
    y_scale = _y_scale(lower=0.0, upper=1.0, panel=panel)
    parts = _y_axis_labels(
        values=(0.0, 0.5, 1.0),
        formatter=lambda value: f"{value:.1f}",
        y_scale=y_scale,
        left=left,
        plot_width=plot_width,
        panel=panel,
    )
    stretch = tuple(
        (snapshot.source_date, snapshot.stretch_pressure_score)
        for snapshot in snapshots
        if snapshot.stretch_pressure_score is not None
    )
    washout = tuple(
        (snapshot.source_date, snapshot.washout_pressure_score)
        for snapshot in snapshots
        if snapshot.washout_pressure_score is not None
    )
    for series, color, label in (
        (stretch, "#c25a17", "stretch pressure"),
        (washout, "#087f8c", "washout pressure"),
    ):
        path = _line_path(series, x_scale=x_scale, y_scale=y_scale)
        if path:
            parts.append(
                f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.2">'
                f"<title>{escape(label)}</title></path>"
            )
        parts.extend(
            _point_markers(series, x_scale=x_scale, y_scale=y_scale, color=color, label=label)
        )
    return parts


def _draw_component_panel(
    *,
    snapshots: tuple[RegimeSnapshot, ...],
    x_scale: Callable[[date], float],
    panel: _Panel,
    left: int,
    plot_width: int,
) -> list[str]:
    y_scale = _y_scale(lower=-2.0, upper=2.0, panel=panel)
    parts = _y_axis_labels(
        values=(-2.0, -1.0, 0.0, 1.0, 2.0),
        formatter=lambda value: f"{value:+.0f}",
        y_scale=y_scale,
        left=left,
        plot_width=plot_width,
        panel=panel,
    )
    colors = {
        "trend": "#1b6ca8",
        "volatility": "#c25a17",
        "breadth": "#2f8f46",
        "credit": "#7a4cc2",
    }
    for component in ("trend", "volatility", "breadth", "credit"):
        series = tuple(
            (snapshot.source_date, float(component_scores[component]))
            for snapshot in snapshots
            if (component_scores := _component_scores(snapshot)) and component in component_scores
        )
        color = colors[component]
        path = _line_path(series, x_scale=x_scale, y_scale=y_scale)
        if path:
            parts.append(
                f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2">'
                f"<title>{escape(component)} component score</title></path>"
            )
        parts.extend(
            _point_markers(series, x_scale=x_scale, y_scale=y_scale, color=color, label=component)
        )
    return parts


def _draw_signal_panel(
    *,
    snapshots: tuple[RegimeSnapshot, ...],
    signals_by_date: dict[date, tuple[MarketSignal, ...]],
    x_scale: Callable[[date], float],
    panel: _Panel,
    left: int,
    plot_width: int,
) -> list[str]:
    y_scale = _y_scale(lower=-1.0, upper=1.0, panel=panel)
    parts = _y_axis_labels(
        values=(-1.0, 0.0, 1.0),
        formatter=lambda value: f"{value:+.0f}",
        y_scale=y_scale,
        left=left,
        plot_width=plot_width,
        panel=panel,
    )
    families = ("trend", "volatility", "breadth", "credit", "liquidity", "rates")
    colors = {
        "trend": "#1b6ca8",
        "volatility": "#c25a17",
        "breadth": "#2f8f46",
        "credit": "#7a4cc2",
        "liquidity": "#59656f",
        "rates": "#8a5a00",
    }
    snapshot_dates = tuple(snapshot.source_date for snapshot in snapshots)
    for family in families:
        series = tuple(
            (source_date, value)
            for source_date in snapshot_dates
            if (value := _family_average_score(signals_by_date.get(source_date, ()), family=family))
            is not None
        )
        if not series:
            continue
        color = colors[family]
        path = _line_path(series, x_scale=x_scale, y_scale=y_scale)
        if path:
            parts.append(
                f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2">'
                f"<title>{escape(family)} market signal score</title></path>"
            )
        parts.extend(
            _point_markers(series, x_scale=x_scale, y_scale=y_scale, color=color, label=family)
        )
    return parts


def _load_regime_snapshots_in_range(
    *,
    start_date: date,
    end_date: date,
    snapshot_root: Path,
) -> tuple[RegimeSnapshot, ...]:
    snapshots: list[RegimeSnapshot] = []
    for path in sorted(snapshot_root.glob("*.json")):
        try:
            source_date = date.fromisoformat(path.stem)
        except ValueError:
            continue
        if not start_date <= source_date <= end_date:
            continue
        try:
            snapshot = load_regime_snapshot(source_date=source_date, snapshot_root=snapshot_root)
        except RegimeError as exc:
            raise ChartError(str(exc)) from exc
        if snapshot is not None:
            snapshots.append(snapshot)
    return tuple(sorted(snapshots, key=lambda row: row.source_date))


def _load_market_signals_in_range(
    *,
    start_date: date,
    end_date: date,
    snapshot_root: Path,
) -> dict[date, tuple[MarketSignal, ...]]:
    signals_by_date: dict[date, tuple[MarketSignal, ...]] = {}
    for path in sorted(snapshot_root.glob("*.jsonl")):
        try:
            source_date = date.fromisoformat(path.stem)
        except ValueError:
            continue
        if not start_date <= source_date <= end_date:
            continue
        try:
            signals_by_date[source_date] = load_market_signal_snapshot(
                source_date=source_date,
                snapshot_root=snapshot_root,
            )
        except MarketSignalError as exc:
            raise ChartError(str(exc)) from exc
    return signals_by_date


def _price_rows_in_range(
    *,
    symbol: str,
    price_root: Path,
    start_date: date,
    end_date: date,
) -> tuple[DailyPriceObservation, ...]:
    try:
        rows = load_price_history(symbol=symbol, price_root=price_root)
    except PriceDataError as exc:
        raise ChartError(str(exc)) from exc
    return tuple(row for row in rows if start_date <= row.observed_date <= end_date)


def _indexed_price_series(
    rows: tuple[DailyPriceObservation, ...],
) -> tuple[tuple[date, float], ...]:
    if not rows:
        return ()
    base = rows[0].return_close
    if base == 0:
        return ()
    return tuple((row.observed_date, row.return_close / base * 100.0) for row in rows)


def _date_domain(
    *,
    start_date: date,
    end_date: date,
    price_histories: dict[str, tuple[DailyPriceObservation, ...]],
    snapshots: tuple[RegimeSnapshot, ...],
) -> tuple[date, date]:
    dates = [
        row.observed_date
        for rows in price_histories.values()
        for row in rows
        if start_date <= row.observed_date <= end_date
    ]
    dates.extend(snapshot.source_date for snapshot in snapshots)
    if not dates:
        return start_date, end_date
    x_min = min(min(dates), start_date)
    x_max = max(max(dates), end_date)
    if x_min == x_max:
        return x_min - timedelta(days=1), x_max + timedelta(days=1)
    return x_min, x_max


def _x_scale(
    *,
    x_min: date,
    x_max: date,
    left: int,
    plot_width: int,
) -> Callable[[date], float]:
    span = max(1, x_max.toordinal() - x_min.toordinal())

    def scale(value: date) -> float:
        return left + (value.toordinal() - x_min.toordinal()) / span * plot_width

    return scale


def _y_scale(*, lower: float, upper: float, panel: _Panel) -> Callable[[float], float]:
    span = upper - lower if upper != lower else 1.0

    def scale(value: float) -> float:
        return panel.bottom - (value - lower) / span * panel.height

    return scale


def _action_backgrounds(
    *,
    snapshots: tuple[RegimeSnapshot, ...],
    x_scale: Callable[[date], float],
    x_min: date,
    x_max: date,
    y: int,
    height: int,
) -> list[str]:
    if not snapshots:
        return []
    parts: list[str] = []
    dates = [snapshot.source_date for snapshot in snapshots]
    min_width = 8.0
    for index, snapshot in enumerate(snapshots):
        if len(snapshots) == 1:
            x1 = x_scale(x_min)
            x2 = x_scale(x_max)
        else:
            previous_date = dates[index - 1] if index > 0 else x_min
            next_date = dates[index + 1] if index + 1 < len(dates) else x_max
            left_date = snapshot.source_date - timedelta(
                days=max(1, (snapshot.source_date - previous_date).days) // 2
            )
            right_date = snapshot.source_date + timedelta(
                days=max(1, (next_date - snapshot.source_date).days) // 2
            )
            x1 = max(x_scale(x_min), x_scale(left_date))
            x2 = min(x_scale(x_max), x_scale(right_date))
        if x2 - x1 < min_width:
            center = x_scale(snapshot.source_date)
            x1 = center - min_width / 2
            x2 = center + min_width / 2
        color = _action_color(snapshot.action_state)
        parts.append(
            f'<rect x="{x1:.1f}" y="{y}" width="{x2 - x1:.1f}" height="{height}" '
            f'fill="{color}" opacity="0.10">'
            f"<title>{escape(snapshot.source_date.isoformat())} "
            f"{escape(snapshot.action_state)} / {escape(snapshot.regime)}</title></rect>"
        )
    return parts


def _panel_background(*, left: int, width: int, panel: _Panel) -> str:
    return (
        f'<rect x="{left}" y="{panel.top}" width="{width}" height="{panel.height}" '
        'fill="#f7f9fa" stroke="#d8dee2" stroke-width="1" />'
    )


def _panel_title(*, left: int, panel: _Panel) -> str:
    return _text(left, panel.top - 10, panel.title, css_class="panel-title")


def _x_axis_labels(
    *,
    x_min: date,
    x_max: date,
    x_scale: Callable[[date], float],
    panel: _Panel,
) -> list[str]:
    labels = []
    for tick in _date_ticks(x_min, x_max, count=5):
        x = x_scale(tick)
        labels.append(
            f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{panel.top}" y2="{panel.bottom}" class="grid" />'
        )
        labels.append(
            _text(x, panel.bottom + 16, tick.isoformat(), css_class="axis", anchor="middle")
        )
    return labels


def _y_axis_labels(
    *,
    values: tuple[float, ...],
    formatter: Callable[[float], str],
    y_scale: Callable[[float], float],
    left: int,
    plot_width: int,
    panel: _Panel,
) -> list[str]:
    labels = []
    for value in values:
        y = y_scale(value)
        labels.append(
            f'<line x1="{left}" x2="{left + plot_width}" y1="{y:.1f}" y2="{y:.1f}" class="grid" />'
        )
        labels.append(_text(left - 10, y + 4, formatter(value), css_class="axis", anchor="end"))
    labels.append(
        f'<line x1="{left}" x2="{left + plot_width}" y1="{panel.bottom}" '
        f'y2="{panel.bottom}" class="axis-line" />'
    )
    labels.append(
        f'<line x1="{left}" x2="{left}" y1="{panel.top}" y2="{panel.bottom}" class="axis-line" />'
    )
    return labels


def _line_path(
    series: tuple[tuple[date, float], ...],
    *,
    x_scale: Callable[[date], float],
    y_scale: Callable[[float], float],
) -> str:
    if len(series) < 2:
        return ""
    points = tuple((x_scale(row_date), y_scale(value)) for row_date, value in series)
    first_x, first_y = points[0]
    rest = " ".join(f"L {x:.1f},{y:.1f}" for x, y in points[1:])
    return f"M {first_x:.1f},{first_y:.1f} {rest}"


def _point_markers(
    series: tuple[tuple[date, float], ...],
    *,
    x_scale: Callable[[date], float],
    y_scale: Callable[[float], float],
    color: str,
    label: str,
) -> list[str]:
    radius = "2.8" if len(series) < 80 else "1.8"
    return [
        f'<circle cx="{x_scale(row_date):.1f}" cy="{y_scale(value):.1f}" r="{radius}" '
        f'fill="{color}"><title>{escape(label)} {escape(row_date.isoformat())}: '
        f"{value:.2f}</title></circle>"
        for row_date, value in series
    ]


def _component_scores(snapshot: RegimeSnapshot) -> dict[str, int]:
    return {component.name: component.score for component in snapshot.components}


def _family_average_score(signals: tuple[MarketSignal, ...], *, family: str) -> float | None:
    family_signals = tuple(
        signal for signal in signals if signal.family == family and signal.status != "missing"
    )
    if not family_signals:
        return None
    return sum(signal.score for signal in family_signals) / len(family_signals)


def _latest_signal_rows(signals: tuple[MarketSignal, ...]) -> str:
    if not signals:
        return '<p class="empty">No market signal rows found for the latest regime date.</p>'
    rows = [
        "<table>",
        "<thead><tr><th>Family</th><th>Signal</th><th>Score</th><th>Status</th><th>Value</th><th>Observed</th><th>Reason</th></tr></thead>",
        "<tbody>",
    ]
    for signal in signals:
        rows.append(
            "<tr>"
            f"<td>{escape(signal.family)}</td>"
            f"<td>{escape(signal.name)}</td>"
            f"<td>{signal.score:+d}</td>"
            f"<td>{escape(signal.status)}</td>"
            f"<td>{escape(_format_signal_value(signal))}</td>"
            f"<td>{escape(signal.observed_date.isoformat() if signal.observed_date else '-')}</td>"
            f"<td>{escape(signal.reason)}</td>"
            "</tr>"
        )
    rows.extend(["</tbody>", "</table>"])
    return "\n".join(rows)


def _format_signal_value(signal: MarketSignal) -> str:
    value = signal.value
    if value is None:
        return "-"
    if isinstance(value, float):
        if signal.unit == "percent":
            return f"{value * 100:+.1f}%"
        if signal.unit == "percent_level":
            return f"{value:.2f}%"
        if signal.unit == "percentage_points":
            return f"{value:+.2f}pp"
        if signal.unit in {"index", "ratio"}:
            return f"{value:.2f}"
        return f"{value:.4g}"
    return str(value)


def _date_ticks(x_min: date, x_max: date, *, count: int) -> tuple[date, ...]:
    if count <= 1 or x_min == x_max:
        return (x_min,)
    span = x_max.toordinal() - x_min.toordinal()
    return tuple(
        date.fromordinal(x_min.toordinal() + round(span * index / (count - 1)))
        for index in range(count)
    )


def _ticks(lower: float, upper: float, count: int) -> tuple[float, ...]:
    if count <= 1:
        return (lower,)
    step = (upper - lower) / (count - 1)
    return tuple(lower + index * step for index in range(count))


def _action_color(action_state: str) -> str:
    if action_state == "scale_down_protect":
        return "#c25a17"
    if action_state == "scale_up_redeploy":
        return "#087f8c"
    return "#7d8790"


def _legend(*, width: int, y: int) -> str:
    items = (
        ("#1b6ca8", "SPY / trend"),
        ("#7a4cc2", "QQQ / credit"),
        ("#c25a17", "stretch / volatility"),
        ("#087f8c", "washout / redeploy"),
        ("#7d8790", "no_change shading"),
    )
    x = 82
    parts = []
    for color, label in items:
        parts.append(f'<rect x="{x}" y="{y - 9}" width="14" height="4" fill="{color}" />')
        parts.append(_text(x + 20, y - 5, label, css_class="legend"))
        x += 180
    return "\n".join(parts)


def _svg_defs() -> str:
    return """<defs>
  <clipPath id="plotClip">
    <rect x="82" y="44" width="1068" height="754" />
  </clipPath>
</defs>"""


def _svg_style() -> str:
    return """<style>
  .title { font: 700 18px ui-sans-serif, system-ui, sans-serif; fill: #172026; }
  .panel-title { font: 700 13px ui-sans-serif, system-ui, sans-serif; fill: #172026; }
  .axis { font: 11px ui-sans-serif, system-ui, sans-serif; fill: #5f6c72; }
  .legend { font: 12px ui-sans-serif, system-ui, sans-serif; fill: #364047; }
  .grid { stroke: #d8dee2; stroke-width: 1; }
  .axis-line { stroke: #88939a; stroke-width: 1; }
</style>"""


def _text(
    x: float,
    y: float,
    text: str,
    *,
    css_class: str,
    anchor: str = "start",
) -> str:
    return (
        f'<text x="{x:.1f}" y="{y:.1f}" class="{css_class}" '
        f'text-anchor="{anchor}">{escape(text)}</text>'
    )


def _default_regime_chart_path(*, start_date: date, end_date: date) -> Path:
    return (
        DEFAULT_CHART_REPORT_ROOT / f"regime-{start_date.isoformat()}-{end_date.isoformat()}.html"
    )
