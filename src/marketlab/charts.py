"""Reproducible HTML/SVG research charts."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from html import escape
from pathlib import Path
from typing import Any

from loguru import logger

from marketlab.bulltard.ingest import DEFAULT_OBSERVATIONS_ROOT
from marketlab.bulltard.validation import (
    BENCHMARK_SYMBOLS,
    DEFAULT_CANDIDATE_SNAPSHOT_ROOT,
    CandidateValidationError,
    CandidateValidationSnapshot,
    load_candidate_validation_snapshots,
)
from marketlab.market_signals import (
    DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT,
    MARKET_SIGNAL_SNAPSHOT_FILENAME,
    MarketSignal,
    MarketSignalError,
    load_market_signal_snapshot,
)
from marketlab.policy import (
    DEFAULT_POLICY_SNAPSHOT_ROOT,
    POLICY_SNAPSHOT_FILENAME,
    PortfolioPolicyError,
    PortfolioPolicySnapshot,
    load_portfolio_policy_snapshot,
)
from marketlab.prices import (
    DEFAULT_PRICE_OBSERVATIONS_ROOT,
    DailyPriceObservation,
    PriceDataError,
    dedupe_symbols,
    load_price_history,
    normalize_symbol,
)
from marketlab.regime import (
    DEFAULT_REGIME_SNAPSHOT_ROOT,
    REGIME_SNAPSHOT_FILENAME,
    RegimeError,
    RegimeSnapshot,
    load_regime_snapshot,
)
from marketlab.snapshots.models import (
    SignalTime,
    default_snapshot_version,
    signal_time_value,
    snapshot_source_dates,
)
from marketlab.versions import BULLTARD_VERSION, REGIME_VERSION, versioned_label

DEFAULT_CHART_REPORT_ROOT = Path("reports")
REGIME_CHART_VERSION = versioned_label("regime_chart", REGIME_VERSION)
OPPORTUNITY_CHART_VERSION = versioned_label("opportunity_chart", BULLTARD_VERSION)
DEFAULT_OPPORTUNITY_LOOKBACK_DAYS = 120
DEFAULT_OPPORTUNITY_FORWARD_DAYS = 65
OPPORTUNITY_OUTCOME_HORIZONS = (1, 5, 20, 40, 65, 126)


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
    policy_snapshot_count: int = 0
    chart_version: str = REGIME_CHART_VERSION


@dataclass(frozen=True, slots=True)
class OpportunityChartResult:
    """Result of rendering one single-name opportunity chart."""

    source_date: date
    symbol: str
    output_path: Path
    chart_start_date: date
    chart_end_date: date
    price_symbols: tuple[str, ...]
    price_point_count: int
    flow_event_count: int
    available_forward_outcome_count: int
    validation_status: str
    chart_version: str = OPPORTUNITY_CHART_VERSION


@dataclass(frozen=True, slots=True)
class _TickerFlowEvent:
    source_date: date
    symbol: str
    traded_at: datetime
    order_type: str
    side: str | None
    contract: str
    contract_type: str | None
    expiry: date
    contracts: int
    premium: float | None
    is_older: bool


@dataclass(frozen=True, slots=True)
class _DailyFlowPremium:
    traded_date: date
    bullish_premium: float
    bearish_premium: float
    neutral_premium: float
    event_count: int


@dataclass(frozen=True, slots=True)
class _OpportunityForwardOutcome:
    horizon_days: int
    return_value: float | None
    relative_strength_spy: float | None
    max_drawdown: float | None


def render_regime_chart(
    *,
    start_date: date,
    end_date: date,
    symbol: str = "SPY",
    comparison_symbol: str | None = "QQQ",
    price_root: Path = DEFAULT_PRICE_OBSERVATIONS_ROOT,
    regime_snapshot_root: Path = DEFAULT_REGIME_SNAPSHOT_ROOT,
    market_signal_snapshot_root: Path = DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT,
    policy_snapshot_root: Path = DEFAULT_POLICY_SNAPSHOT_ROOT,
    signal_time: SignalTime | str = SignalTime.EOD,
    snapshot_version: str | None = None,
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
        signal_time=signal_time,
        snapshot_version=snapshot_version,
    )
    if not snapshots:
        raise ChartError(f"No regime snapshots found from {start_date} to {end_date}")

    signals_by_date = _load_market_signals_in_range(
        start_date=start_date,
        end_date=end_date,
        snapshot_root=market_signal_snapshot_root,
        signal_time=signal_time,
        snapshot_version=snapshot_version,
    )
    signals = tuple(signal for rows in signals_by_date.values() for signal in rows)
    policies = _load_policy_snapshots_in_range(
        start_date=start_date,
        end_date=end_date,
        snapshot_root=policy_snapshot_root,
        signal_time=signal_time,
        snapshot_version=snapshot_version,
    )
    resolved_output_path = output_path or _default_regime_chart_path(
        start_date=start_date,
        end_date=end_date,
        signal_time=signal_time,
        snapshot_version=snapshot_version,
    )
    html = _render_regime_chart_html(
        start_date=start_date,
        end_date=end_date,
        price_histories=price_histories,
        snapshots=snapshots,
        signals_by_date=signals_by_date,
        policies=policies,
        price_root=price_root,
        regime_snapshot_root=regime_snapshot_root,
        market_signal_snapshot_root=market_signal_snapshot_root,
        policy_snapshot_root=policy_snapshot_root,
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
        policy_snapshot_count=len(policies),
    )
    logger.bind(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        output_path=str(resolved_output_path),
        price_symbols=price_symbols,
        price_point_count=result.price_point_count,
        regime_snapshot_count=result.regime_snapshot_count,
        market_signal_count=result.market_signal_count,
        policy_snapshot_count=result.policy_snapshot_count,
    ).success("Rendered regime chart")
    return result


def render_opportunity_chart(
    *,
    source_date: date,
    symbol: str,
    lookback_days: int = DEFAULT_OPPORTUNITY_LOOKBACK_DAYS,
    forward_days: int = DEFAULT_OPPORTUNITY_FORWARD_DAYS,
    price_root: Path = DEFAULT_PRICE_OBSERVATIONS_ROOT,
    candidate_snapshot_root: Path = DEFAULT_CANDIDATE_SNAPSHOT_ROOT,
    observations_root: Path = DEFAULT_OBSERVATIONS_ROOT,
    signal_time: SignalTime | str = SignalTime.EOD,
    snapshot_version: str | None = None,
    output_path: Path | None = None,
) -> OpportunityChartResult:
    """Render a single-name opportunity chart from saved research snapshots."""

    if lookback_days < 0:
        raise ChartError("Opportunity chart lookback days must be non-negative")
    if forward_days < 0:
        raise ChartError("Opportunity chart forward days must be non-negative")
    try:
        normalized_symbol = normalize_symbol(symbol)
    except PriceDataError as exc:
        raise ChartError(str(exc)) from exc

    snapshot = _load_candidate_snapshot(
        source_date=source_date,
        symbol=normalized_symbol,
        snapshot_root=candidate_snapshot_root,
        signal_time=signal_time,
        snapshot_version=snapshot_version,
    )
    chart_start_date = source_date - timedelta(days=lookback_days)
    chart_end_date = source_date + timedelta(days=forward_days)
    price_symbols = dedupe_symbols((normalized_symbol, *BENCHMARK_SYMBOLS))
    price_histories = {
        price_symbol: _price_rows_in_range(
            symbol=price_symbol,
            price_root=price_root,
            start_date=chart_start_date,
            end_date=chart_end_date,
        )
        for price_symbol in price_symbols
    }
    if not price_histories[normalized_symbol]:
        raise ChartError(
            f"No {normalized_symbol} price observations found from "
            f"{chart_start_date} to {chart_end_date}"
        )

    flow_events = _load_ticker_flow_events(
        source_date=source_date,
        symbol=normalized_symbol,
        observations_root=observations_root,
    )
    interest_note = _load_trade_interest_note(
        source_date=source_date,
        symbol=normalized_symbol,
        observations_root=observations_root,
    )
    full_symbol_history = _full_price_history(symbol=normalized_symbol, price_root=price_root)
    full_spy_history = _full_price_history(symbol="SPY", price_root=price_root)
    forward_outcomes = _opportunity_forward_outcomes(
        snapshot=snapshot,
        price_history=full_symbol_history,
        spy_history=full_spy_history,
        horizons=OPPORTUNITY_OUTCOME_HORIZONS,
    )
    resolved_output_path = output_path or _default_opportunity_chart_path(
        source_date=source_date,
        symbol=normalized_symbol,
        signal_time=signal_time,
        snapshot_version=snapshot_version,
    )
    html = _render_opportunity_chart_html(
        source_date=source_date,
        symbol=normalized_symbol,
        chart_start_date=chart_start_date,
        chart_end_date=chart_end_date,
        price_histories=price_histories,
        snapshot=snapshot,
        flow_events=flow_events,
        interest_note=interest_note,
        forward_outcomes=forward_outcomes,
        price_root=price_root,
        candidate_snapshot_root=candidate_snapshot_root,
        observations_root=observations_root,
    )
    resolved_output_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_output_path.write_text(html, encoding="utf-8")

    result = OpportunityChartResult(
        source_date=source_date,
        symbol=normalized_symbol,
        output_path=resolved_output_path,
        chart_start_date=chart_start_date,
        chart_end_date=chart_end_date,
        price_symbols=price_symbols,
        price_point_count=sum(len(rows) for rows in price_histories.values()),
        flow_event_count=len(flow_events),
        available_forward_outcome_count=sum(
            1 for outcome in forward_outcomes if outcome.return_value is not None
        ),
        validation_status=snapshot.validation_status,
    )
    logger.bind(
        source_date=source_date.isoformat(),
        symbol=normalized_symbol,
        output_path=str(resolved_output_path),
        chart_start_date=chart_start_date.isoformat(),
        chart_end_date=chart_end_date.isoformat(),
        price_symbols=price_symbols,
        price_point_count=result.price_point_count,
        flow_event_count=result.flow_event_count,
        available_forward_outcome_count=result.available_forward_outcome_count,
        validation_status=result.validation_status,
    ).success("Rendered opportunity chart")
    return result


def _render_regime_chart_html(
    *,
    start_date: date,
    end_date: date,
    price_histories: dict[str, tuple[DailyPriceObservation, ...]],
    snapshots: tuple[RegimeSnapshot, ...],
    signals_by_date: dict[date, tuple[MarketSignal, ...]],
    policies: tuple[PortfolioPolicySnapshot, ...],
    price_root: Path,
    regime_snapshot_root: Path,
    market_signal_snapshot_root: Path,
    policy_snapshot_root: Path,
) -> str:
    chart_svg = _render_regime_chart_svg(
        start_date=start_date,
        end_date=end_date,
        price_histories=price_histories,
        snapshots=snapshots,
        signals_by_date=signals_by_date,
        policies=policies,
    )
    latest_snapshot = snapshots[-1]
    latest_signals = signals_by_date.get(latest_snapshot.source_date, ())
    signal_rows = _latest_signal_rows(latest_signals)
    escaped_start = escape(start_date.isoformat())
    escaped_end = escape(end_date.isoformat())
    escaped_price_root = escape(str(price_root))
    escaped_regime_root = escape(str(regime_snapshot_root))
    escaped_signal_root = escape(str(market_signal_snapshot_root))
    escaped_policy_root = escape(str(policy_snapshot_root))
    escaped_version_summary = escape(_regime_chart_version_summary(snapshots, policies))
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
    signals={escaped_signal_root}, policies={escaped_policy_root}.
    Versions: {escaped_version_summary}.
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


def _render_opportunity_chart_html(
    *,
    source_date: date,
    symbol: str,
    chart_start_date: date,
    chart_end_date: date,
    price_histories: dict[str, tuple[DailyPriceObservation, ...]],
    snapshot: CandidateValidationSnapshot,
    flow_events: tuple[_TickerFlowEvent, ...],
    interest_note: str | None,
    forward_outcomes: tuple[_OpportunityForwardOutcome, ...],
    price_root: Path,
    candidate_snapshot_root: Path,
    observations_root: Path,
) -> str:
    chart_svg = _render_opportunity_chart_svg(
        source_date=source_date,
        symbol=symbol,
        chart_start_date=chart_start_date,
        chart_end_date=chart_end_date,
        price_histories=price_histories,
        snapshot=snapshot,
        flow_events=flow_events,
    )
    escaped_symbol = escape(symbol)
    escaped_source_date = escape(source_date.isoformat())
    escaped_start = escape(chart_start_date.isoformat())
    escaped_end = escape(chart_end_date.isoformat())
    escaped_price_root = escape(str(price_root))
    escaped_candidate_root = escape(str(candidate_snapshot_root))
    escaped_observation_root = escape(str(observations_root))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MarketLab Opportunity Chart {escaped_symbol} {escaped_source_date}</title>
  <style>
    :root {{
      color-scheme: light;
      --ink: #172026;
      --muted: #5f6c72;
      --grid: #d8dee2;
      --panel: #f7f9fa;
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
    h2 {{
      margin: 24px 0 8px;
      font-size: 16px;
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
      margin-top: 10px;
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
    td:first-child {{
      width: 210px;
      color: var(--muted);
    }}
    .empty {{
      margin-top: 10px;
      color: var(--muted);
      font-size: 13px;
    }}
  </style>
</head>
<body>
<main>
  <h1>{escaped_symbol} Opportunity Chart</h1>
  <p class="meta">
    Bulltard date: {escaped_source_date}. Window: {escaped_start} to {escaped_end}.
    Chart version: {OPPORTUNITY_CHART_VERSION}.
    Sources: prices={escaped_price_root}, candidates={escaped_candidate_root},
    observations={escaped_observation_root}.
  </p>
  <div class="chart-shell">
    {chart_svg}
  </div>
  <h2>Point-In-Time Candidate Snapshot</h2>
  {_candidate_snapshot_table(snapshot=snapshot, interest_note=interest_note)}
  <h2>Bulltard Flow Events</h2>
  {_flow_event_table(flow_events)}
  <h2>Forward Outcomes</h2>
  {_forward_outcome_table(forward_outcomes)}
</main>
</body>
</html>
"""


def _render_opportunity_chart_svg(
    *,
    source_date: date,
    symbol: str,
    chart_start_date: date,
    chart_end_date: date,
    price_histories: dict[str, tuple[DailyPriceObservation, ...]],
    snapshot: CandidateValidationSnapshot,
    flow_events: tuple[_TickerFlowEvent, ...],
) -> str:
    width = 1180
    left = 82
    right = 30
    top = 44
    gap = 36
    price_panel = _Panel(top=top, height=250, title=f"{symbol} indexed close")
    flow_panel = _Panel(
        top=price_panel.bottom + gap,
        height=150,
        title="Bulltard flow premium by trade date",
    )
    relative_panel = _Panel(
        top=flow_panel.bottom + gap,
        height=170,
        title="20d relative strength",
    )
    height = relative_panel.bottom + 62
    plot_width = width - left - right
    plotted_flow_events = tuple(
        event
        for event in flow_events
        if chart_start_date <= event.traded_at.date() <= chart_end_date
    )
    x_min, x_max = _opportunity_date_domain(
        chart_start_date=chart_start_date,
        chart_end_date=chart_end_date,
        source_date=source_date,
        price_histories=price_histories,
        flow_events=plotted_flow_events,
    )
    x_scale = _x_scale(x_min=x_min, x_max=x_max, left=left, plot_width=plot_width)
    anchor_date = snapshot.price_date or source_date
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{escape(symbol)} opportunity chart">',
        _svg_defs(),
        _text(left, 24, f"{symbol} {source_date.isoformat()}", css_class="title"),
    ]
    for panel in (price_panel, flow_panel, relative_panel):
        parts.append(_panel_background(left=left, width=plot_width, panel=panel))
        parts.append(_panel_title(left=left, panel=panel))
        parts.extend(_x_axis_labels(x_min=x_min, x_max=x_max, x_scale=x_scale, panel=panel))

    parts.extend(
        _vertical_event_marker(
            marker_date=source_date,
            x_scale=x_scale,
            top=price_panel.top,
            bottom=relative_panel.bottom,
            color="#172026",
            label="Bulltard date",
        )
    )
    parts.extend(
        _draw_opportunity_price_panel(
            price_histories=price_histories,
            symbol=symbol,
            anchor_date=anchor_date,
            x_scale=x_scale,
            panel=price_panel,
            left=left,
            plot_width=plot_width,
        )
    )
    parts.extend(
        _draw_flow_premium_panel(
            flow_events=plotted_flow_events,
            x_min=x_min,
            x_max=x_max,
            x_scale=x_scale,
            panel=flow_panel,
            left=left,
            plot_width=plot_width,
        )
    )
    parts.extend(
        _draw_relative_strength_panel(
            price_histories=price_histories,
            symbol=symbol,
            x_scale=x_scale,
            panel=relative_panel,
            left=left,
            plot_width=plot_width,
        )
    )
    parts.append(_opportunity_legend(symbol=symbol, y=height - 28))
    parts.append(_svg_style())
    parts.append("</svg>")
    return "\n".join(parts)


def _render_regime_chart_svg(
    *,
    start_date: date,
    end_date: date,
    price_histories: dict[str, tuple[DailyPriceObservation, ...]],
    snapshots: tuple[RegimeSnapshot, ...],
    signals_by_date: dict[date, tuple[MarketSignal, ...]],
    policies: tuple[PortfolioPolicySnapshot, ...],
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
    policy_panel = _Panel(
        top=signal_panel.bottom + gap,
        height=140,
        title="Portfolio policy state",
    )
    height = policy_panel.bottom + 62
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
    for panel in (price_panel, pressure_panel, component_panel, signal_panel, policy_panel):
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
            height=policy_panel.bottom - price_panel.top,
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
        _draw_policy_panel(
            policies=policies,
            x_scale=x_scale,
            panel=policy_panel,
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


def _draw_policy_panel(
    *,
    policies: tuple[PortfolioPolicySnapshot, ...],
    x_scale: Callable[[date], float],
    panel: _Panel,
    left: int,
    plot_width: int,
) -> list[str]:
    y_scale = _y_scale(lower=-1.0, upper=1.0, panel=panel)
    parts = _y_axis_labels(
        values=(-1.0, 0.0, 1.0),
        formatter=_format_policy_axis,
        y_scale=y_scale,
        left=left,
        plot_width=plot_width,
        panel=panel,
    )
    series = tuple(
        (policy.source_date, float(_policy_state_value(policy.policy_state)))
        for policy in policies
        if _policy_state_value(policy.policy_state) is not None
    )
    path = _line_path(series, x_scale=x_scale, y_scale=y_scale)
    if path:
        parts.append(
            f'<path d="{path}" fill="none" stroke="#172026" stroke-width="2">'
            "<title>portfolio policy state</title></path>"
        )
    if not policies:
        parts.append(
            _text(left + 8, panel.top + panel.height / 2, "No policy snapshots", css_class="axis")
        )
        return parts

    radius = "3.4" if len(series) < 80 else "2.2"
    for policy in policies:
        value = _policy_state_value(policy.policy_state)
        if value is None:
            continue
        x = x_scale(policy.source_date)
        y = y_scale(float(value))
        color = _policy_state_color(policy.policy_state)
        title = (
            f"{policy.source_date.isoformat()} {policy.policy_state}; "
            f"target_beta={policy.marginal_beta_target:g}; "
            f"cash={policy.cash_posture}; overlay={policy.overlay_stance}"
        )
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{color}">'
            f"<title>{escape(title)}</title></circle>"
        )
    return parts


def _draw_opportunity_price_panel(
    *,
    price_histories: dict[str, tuple[DailyPriceObservation, ...]],
    symbol: str,
    anchor_date: date,
    x_scale: Callable[[date], float],
    panel: _Panel,
    left: int,
    plot_width: int,
) -> list[str]:
    indexed_series = {
        price_symbol: _anchored_indexed_price_series(rows, anchor_date=anchor_date)
        for price_symbol, rows in price_histories.items()
    }
    values = [value for series in indexed_series.values() for _date, value in series]
    if not values:
        return []
    lower, upper = _padded_value_domain(values=tuple(values), include_zero=False, pad_ratio=0.08)
    y_scale = _y_scale(lower=lower, upper=upper, panel=panel)
    parts = _y_axis_labels(
        values=_ticks(lower, upper, 5),
        formatter=lambda value: f"{value:.0f}",
        y_scale=y_scale,
        left=left,
        plot_width=plot_width,
        panel=panel,
    )
    colors = _opportunity_price_colors(symbol)
    for price_symbol, series in indexed_series.items():
        if not series:
            continue
        color = colors.get(price_symbol, "#8a5a00")
        path = _line_path(series, x_scale=x_scale, y_scale=y_scale)
        if path:
            parts.append(
                f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.4">'
                f"<title>{escape(price_symbol)} indexed to {anchor_date.isoformat()}</title>"
                "</path>"
            )
        parts.extend(
            _point_markers(
                series,
                x_scale=x_scale,
                y_scale=y_scale,
                color=color,
                label=price_symbol,
            )
        )
    return parts


def _draw_flow_premium_panel(
    *,
    flow_events: tuple[_TickerFlowEvent, ...],
    x_min: date,
    x_max: date,
    x_scale: Callable[[date], float],
    panel: _Panel,
    left: int,
    plot_width: int,
) -> list[str]:
    buckets = _daily_flow_premiums(flow_events)
    max_abs = max(
        (
            abs(value)
            for bucket in buckets
            for value in (
                bucket.bullish_premium,
                bucket.bearish_premium,
                bucket.neutral_premium,
            )
        ),
        default=1.0,
    )
    if max_abs == 0:
        max_abs = 1.0
    y_scale = _y_scale(lower=-max_abs, upper=max_abs, panel=panel)
    parts = _y_axis_labels(
        values=(-max_abs, 0.0, max_abs),
        formatter=_format_money_compact,
        y_scale=y_scale,
        left=left,
        plot_width=plot_width,
        panel=panel,
    )
    zero_y = y_scale(0.0)
    parts.append(
        f'<line x1="{left}" x2="{left + plot_width}" y1="{zero_y:.1f}" '
        f'y2="{zero_y:.1f}" stroke="#88939a" stroke-width="1.2" />'
    )
    if not buckets:
        parts.append(
            _text(
                left + 12,
                panel.top + 24,
                "No ticker-flow detail rows found",
                css_class="axis",
            )
        )
        return parts

    bar_width = _time_bar_width(x_min=x_min, x_max=x_max, plot_width=plot_width)
    for bucket in buckets:
        x = x_scale(bucket.traded_date)
        if bucket.bullish_premium:
            y = y_scale(bucket.bullish_premium)
            parts.append(
                _bar_rect(
                    x=x,
                    y=y,
                    width=bar_width,
                    height=zero_y - y,
                    color="#2f8f46",
                    title=(
                        f"{bucket.traded_date.isoformat()} bullish premium "
                        f"{_format_money_compact(bucket.bullish_premium)}"
                    ),
                )
            )
        if bucket.bearish_premium:
            y = y_scale(-bucket.bearish_premium)
            parts.append(
                _bar_rect(
                    x=x,
                    y=zero_y,
                    width=bar_width,
                    height=y - zero_y,
                    color="#b23b3b",
                    title=(
                        f"{bucket.traded_date.isoformat()} bearish premium "
                        f"{_format_money_compact(bucket.bearish_premium)}"
                    ),
                )
            )
        if bucket.neutral_premium:
            y = y_scale(bucket.neutral_premium)
            parts.append(
                _bar_rect(
                    x=x,
                    y=y,
                    width=bar_width,
                    height=zero_y - y,
                    color="#7d8790",
                    title=(
                        f"{bucket.traded_date.isoformat()} unclassified premium "
                        f"{_format_money_compact(bucket.neutral_premium)}"
                    ),
                )
            )
        if not bucket.bullish_premium and not bucket.bearish_premium:
            parts.append(
                f'<circle cx="{x:.1f}" cy="{zero_y:.1f}" r="3.4" '
                'fill="#7d8790">'
                f"<title>{escape(bucket.traded_date.isoformat())} "
                f"{bucket.event_count} flow events without premium</title></circle>"
            )
    return parts


def _draw_relative_strength_panel(
    *,
    price_histories: dict[str, tuple[DailyPriceObservation, ...]],
    symbol: str,
    x_scale: Callable[[date], float],
    panel: _Panel,
    left: int,
    plot_width: int,
) -> list[str]:
    symbol_history = price_histories.get(symbol, ())
    series_by_benchmark = {
        benchmark: _rolling_relative_strength_series(
            symbol_history=symbol_history,
            benchmark_history=price_histories.get(benchmark, ()),
            lookback=20,
        )
        for benchmark in BENCHMARK_SYMBOLS
        if benchmark != symbol
    }
    values = [value for series in series_by_benchmark.values() for _date, value in series]
    lower, upper = (
        _padded_value_domain(values=tuple(values), include_zero=True, pad_ratio=0.15)
        if values
        else (-0.10, 0.10)
    )
    y_scale = _y_scale(lower=lower, upper=upper, panel=panel)
    parts = _y_axis_labels(
        values=_ticks(lower, upper, 5),
        formatter=lambda value: f"{value * 100:+.0f}%",
        y_scale=y_scale,
        left=left,
        plot_width=plot_width,
        panel=panel,
    )
    colors = {"SPY": "#59656f", "QQQ": "#7a4cc2"}
    for benchmark, series in series_by_benchmark.items():
        if not series:
            continue
        color = colors.get(benchmark, "#8a5a00")
        label = f"{symbol} vs {benchmark}"
        path = _line_path(series, x_scale=x_scale, y_scale=y_scale)
        if path:
            parts.append(
                f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2">'
                f"<title>{escape(label)} 20d relative strength</title></path>"
            )
        parts.extend(
            _point_markers(series, x_scale=x_scale, y_scale=y_scale, color=color, label=label)
        )
    if not values:
        parts.append(
            _text(
                left + 12,
                panel.top + 24,
                "Not enough local price history for 20d relative strength",
                css_class="axis",
            )
        )
    return parts


def _load_regime_snapshots_in_range(
    *,
    start_date: date,
    end_date: date,
    snapshot_root: Path,
    signal_time: SignalTime | str = SignalTime.EOD,
    snapshot_version: str | None = None,
) -> tuple[RegimeSnapshot, ...]:
    snapshots: list[RegimeSnapshot] = []
    for source_date in snapshot_source_dates(
        snapshot_root=snapshot_root,
        legacy_suffix=".json",
        filename=REGIME_SNAPSHOT_FILENAME,
    ):
        if not start_date <= source_date <= end_date:
            continue
        try:
            snapshot = load_regime_snapshot(
                source_date=source_date,
                snapshot_root=snapshot_root,
                signal_time=signal_time,
                snapshot_version=snapshot_version,
            )
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
    signal_time: SignalTime | str = SignalTime.EOD,
    snapshot_version: str | None = None,
) -> dict[date, tuple[MarketSignal, ...]]:
    signals_by_date: dict[date, tuple[MarketSignal, ...]] = {}
    for source_date in snapshot_source_dates(
        snapshot_root=snapshot_root,
        legacy_suffix=".jsonl",
        filename=MARKET_SIGNAL_SNAPSHOT_FILENAME,
    ):
        if not start_date <= source_date <= end_date:
            continue
        try:
            signals_by_date[source_date] = load_market_signal_snapshot(
                source_date=source_date,
                snapshot_root=snapshot_root,
                signal_time=signal_time,
                snapshot_version=snapshot_version,
            )
        except MarketSignalError as exc:
            raise ChartError(str(exc)) from exc
    return signals_by_date


def _load_policy_snapshots_in_range(
    *,
    start_date: date,
    end_date: date,
    snapshot_root: Path,
    signal_time: SignalTime | str = SignalTime.EOD,
    snapshot_version: str | None = None,
) -> tuple[PortfolioPolicySnapshot, ...]:
    policies: list[PortfolioPolicySnapshot] = []
    for source_date in snapshot_source_dates(
        snapshot_root=snapshot_root,
        legacy_suffix=".json",
        filename=POLICY_SNAPSHOT_FILENAME,
    ):
        if not start_date <= source_date <= end_date:
            continue
        try:
            policy = load_portfolio_policy_snapshot(
                source_date=source_date,
                snapshot_root=snapshot_root,
                signal_time=signal_time,
                snapshot_version=snapshot_version,
            )
        except PortfolioPolicyError as exc:
            raise ChartError(str(exc)) from exc
        if policy is not None:
            policies.append(policy)
    return tuple(sorted(policies, key=lambda row: row.source_date))


def _load_candidate_snapshot(
    *,
    source_date: date,
    symbol: str,
    snapshot_root: Path,
    signal_time: SignalTime | str = SignalTime.EOD,
    snapshot_version: str | None = None,
) -> CandidateValidationSnapshot:
    try:
        snapshots = load_candidate_validation_snapshots(
            source_date=source_date,
            snapshot_root=snapshot_root,
            signal_time=signal_time,
            snapshot_version=snapshot_version,
        )
    except CandidateValidationError as exc:
        raise ChartError(str(exc)) from exc
    if not snapshots:
        raise ChartError(f"No Bulltard candidate validation snapshots found for {source_date}")
    for snapshot in snapshots:
        if snapshot.symbol.upper() == symbol:
            return snapshot
    available = ", ".join(sorted({snapshot.symbol for snapshot in snapshots}))
    raise ChartError(
        f"No Bulltard candidate validation snapshot found for {symbol} on "
        f"{source_date}; available symbols: {available}"
    )


def _load_ticker_flow_events(
    *,
    source_date: date,
    symbol: str,
    observations_root: Path,
) -> tuple[_TickerFlowEvent, ...]:
    path = observations_root / "ticker_flow" / symbol / f"{source_date.isoformat()}.jsonl"
    if not path.is_file():
        return ()
    try:
        events = tuple(_ticker_flow_event_from_dict(row) for row in _read_jsonl_rows(path))
    except (KeyError, TypeError, ValueError) as exc:
        raise ChartError(f"Invalid Bulltard ticker-flow observations file: {path}") from exc
    return tuple(sorted(events, key=lambda event: event.traded_at))


def _load_trade_interest_note(
    *,
    source_date: date,
    symbol: str,
    observations_root: Path,
) -> str | None:
    path = observations_root / "trades_of_interest" / f"{source_date.isoformat()}.jsonl"
    if not path.is_file():
        return None
    try:
        for row in _read_jsonl_rows(path):
            if str(row["symbol"]).upper() == symbol:
                return str(row["note"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ChartError(f"Invalid Bulltard Trades Of Interest observations file: {path}") from exc
    return None


def _read_jsonl_rows(path: Path) -> tuple[dict[str, Any], ...]:
    try:
        return tuple(
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    except OSError as exc:
        raise ChartError(f"Failed to read observations file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ChartError(f"Invalid JSONL observations file: {path}") from exc


def _ticker_flow_event_from_dict(row: dict[str, Any]) -> _TickerFlowEvent:
    return _TickerFlowEvent(
        source_date=date.fromisoformat(str(row["source_date"])),
        symbol=str(row["symbol"]).upper(),
        traded_at=datetime.fromisoformat(str(row["traded_at"])),
        order_type=str(row["order_type"]),
        side=str(row["side"]) if row["side"] is not None else None,
        contract=str(row["contract"]),
        contract_type=str(row["contract_type"]) if row["contract_type"] is not None else None,
        expiry=date.fromisoformat(str(row["expiry"])),
        contracts=int(row["contracts"]),
        premium=float(row["premium"]) if row["premium"] is not None else None,
        is_older=bool(row["is_older"]),
    )


def _full_price_history(
    *,
    symbol: str,
    price_root: Path,
) -> tuple[DailyPriceObservation, ...]:
    try:
        return load_price_history(symbol=symbol, price_root=price_root)
    except PriceDataError as exc:
        raise ChartError(str(exc)) from exc


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


def _opportunity_forward_outcomes(
    *,
    snapshot: CandidateValidationSnapshot,
    price_history: tuple[DailyPriceObservation, ...],
    spy_history: tuple[DailyPriceObservation, ...],
    horizons: tuple[int, ...],
) -> tuple[_OpportunityForwardOutcome, ...]:
    anchor_date = snapshot.price_date or snapshot.source_date
    price_index = _exact_price_index(price_history, anchor_date)
    spy_index = _exact_price_index(spy_history, anchor_date)
    return tuple(
        _OpportunityForwardOutcome(
            horizon_days=horizon,
            return_value=_forward_return(
                price_history,
                index=price_index,
                horizon=horizon,
            ),
            relative_strength_spy=_forward_relative_strength(
                price_history=price_history,
                price_index=price_index,
                spy_history=spy_history,
                spy_index=spy_index,
                horizon=horizon,
            ),
            max_drawdown=_forward_max_drawdown(
                price_history,
                index=price_index,
                horizon=horizon,
            ),
        )
        for horizon in horizons
    )


def _forward_relative_strength(
    *,
    price_history: tuple[DailyPriceObservation, ...],
    price_index: int | None,
    spy_history: tuple[DailyPriceObservation, ...],
    spy_index: int | None,
    horizon: int,
) -> float | None:
    return_value = _forward_return(price_history, index=price_index, horizon=horizon)
    spy_return = _forward_return(spy_history, index=spy_index, horizon=horizon)
    if return_value is None or spy_return is None:
        return None
    return return_value - spy_return


def _forward_return(
    history: tuple[DailyPriceObservation, ...],
    *,
    index: int | None,
    horizon: int,
) -> float | None:
    if index is None:
        return None
    future_index = index + horizon
    if future_index >= len(history):
        return None
    current_close = history[index].return_close
    if current_close == 0:
        return None
    return history[future_index].return_close / current_close - 1.0


def _forward_max_drawdown(
    history: tuple[DailyPriceObservation, ...],
    *,
    index: int | None,
    horizon: int,
) -> float | None:
    if index is None:
        return None
    future_index = index + horizon
    if future_index >= len(history):
        return None
    current_close = history[index].return_close
    if current_close == 0:
        return None
    lows = [row.return_close for row in history[index + 1 : future_index + 1]]
    if not lows:
        return None
    return min(0.0, min(lows) / current_close - 1.0)


def _exact_price_index(
    history: tuple[DailyPriceObservation, ...],
    observed_date: date,
) -> int | None:
    for index, row in enumerate(history):
        if row.observed_date == observed_date:
            return index
    return None


def _asof_price_index(
    history: tuple[DailyPriceObservation, ...],
    observed_date: date,
) -> int | None:
    for index in range(len(history) - 1, -1, -1):
        if history[index].observed_date <= observed_date:
            return index
    return None


def _indexed_price_series(
    rows: tuple[DailyPriceObservation, ...],
) -> tuple[tuple[date, float], ...]:
    if not rows:
        return ()
    base = rows[0].return_close
    if base == 0:
        return ()
    return tuple((row.observed_date, row.return_close / base * 100.0) for row in rows)


def _anchored_indexed_price_series(
    rows: tuple[DailyPriceObservation, ...],
    *,
    anchor_date: date,
) -> tuple[tuple[date, float], ...]:
    if not rows:
        return ()
    anchor_index = _asof_price_index(rows, anchor_date)
    base_row = rows[anchor_index] if anchor_index is not None else rows[0]
    base = base_row.return_close
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


def _opportunity_date_domain(
    *,
    chart_start_date: date,
    chart_end_date: date,
    source_date: date,
    price_histories: dict[str, tuple[DailyPriceObservation, ...]],
    flow_events: tuple[_TickerFlowEvent, ...],
) -> tuple[date, date]:
    dates = [chart_start_date, chart_end_date, source_date]
    dates.extend(row.observed_date for rows in price_histories.values() for row in rows)
    dates.extend(event.traded_at.date() for event in flow_events)
    x_min = min(dates)
    x_max = max(dates)
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


def _daily_flow_premiums(
    flow_events: tuple[_TickerFlowEvent, ...],
) -> tuple[_DailyFlowPremium, ...]:
    buckets: dict[date, dict[str, float | int]] = {}
    for event in flow_events:
        traded_date = event.traded_at.date()
        bucket = buckets.setdefault(
            traded_date,
            {
                "bullish_premium": 0.0,
                "bearish_premium": 0.0,
                "neutral_premium": 0.0,
                "event_count": 0,
            },
        )
        premium = abs(event.premium or 0.0)
        if event.side == "bullish":
            bucket["bullish_premium"] = float(bucket["bullish_premium"]) + premium
        elif event.side == "bearish":
            bucket["bearish_premium"] = float(bucket["bearish_premium"]) + premium
        else:
            bucket["neutral_premium"] = float(bucket["neutral_premium"]) + premium
        bucket["event_count"] = int(bucket["event_count"]) + 1
    return tuple(
        _DailyFlowPremium(
            traded_date=traded_date,
            bullish_premium=float(bucket["bullish_premium"]),
            bearish_premium=float(bucket["bearish_premium"]),
            neutral_premium=float(bucket["neutral_premium"]),
            event_count=int(bucket["event_count"]),
        )
        for traded_date, bucket in sorted(buckets.items())
    )


def _rolling_relative_strength_series(
    *,
    symbol_history: tuple[DailyPriceObservation, ...],
    benchmark_history: tuple[DailyPriceObservation, ...],
    lookback: int,
) -> tuple[tuple[date, float], ...]:
    series = []
    for index, row in enumerate(symbol_history):
        return_value = _trailing_return(symbol_history, index=index, lookback=lookback)
        benchmark_index = _asof_price_index(benchmark_history, row.observed_date)
        benchmark_return = _trailing_return(
            benchmark_history,
            index=benchmark_index,
            lookback=lookback,
        )
        if return_value is None or benchmark_return is None:
            continue
        series.append((row.observed_date, return_value - benchmark_return))
    return tuple(series)


def _trailing_return(
    history: tuple[DailyPriceObservation, ...],
    *,
    index: int | None,
    lookback: int,
) -> float | None:
    if index is None:
        return None
    past_index = index - lookback
    if past_index < 0:
        return None
    past_close = history[past_index].return_close
    if past_close == 0:
        return None
    return history[index].return_close / past_close - 1.0


def _padded_value_domain(
    *,
    values: tuple[float, ...],
    include_zero: bool,
    pad_ratio: float,
) -> tuple[float, float]:
    clean = [value for value in values if value == value]
    if include_zero:
        clean.append(0.0)
    if not clean:
        return -1.0, 1.0
    lower = min(clean)
    upper = max(clean)
    if lower == upper:
        pad = max(abs(lower) * pad_ratio, 0.01)
    else:
        pad = (upper - lower) * pad_ratio
    return lower - pad, upper + pad


def _time_bar_width(*, x_min: date, x_max: date, plot_width: int) -> float:
    span_days = max(1, x_max.toordinal() - x_min.toordinal())
    return min(16.0, max(4.0, plot_width / max(8, span_days) * 0.70))


def _bar_rect(
    *,
    x: float,
    y: float,
    width: float,
    height: float,
    color: str,
    title: str,
) -> str:
    rect_height = max(1.0, abs(height))
    rect_y = y if height >= 0 else y + height
    return (
        f'<rect x="{x - width / 2:.1f}" y="{rect_y:.1f}" '
        f'width="{width:.1f}" height="{rect_height:.1f}" fill="{color}" '
        f'opacity="0.78"><title>{escape(title)}</title></rect>'
    )


def _vertical_event_marker(
    *,
    marker_date: date,
    x_scale: Callable[[date], float],
    top: int,
    bottom: int,
    color: str,
    label: str,
) -> list[str]:
    x = x_scale(marker_date)
    return [
        f'<line x1="{x:.1f}" x2="{x:.1f}" y1="{top}" y2="{bottom}" '
        f'stroke="{color}" stroke-width="1.6" stroke-dasharray="5 5">'
        f"<title>{escape(label)} {escape(marker_date.isoformat())}</title></line>",
        _text(x + 6, top + 15, label, css_class="event-label"),
    ]


def _opportunity_price_colors(symbol: str) -> dict[str, str]:
    return {
        symbol: "#1b6ca8",
        "SPY": "#59656f",
        "QQQ": "#7a4cc2",
    }


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


def _candidate_snapshot_table(
    *,
    snapshot: CandidateValidationSnapshot,
    interest_note: str | None,
) -> str:
    rows = [
        ("symbol", snapshot.symbol),
        ("source", snapshot.bulltard_source),
        ("ranked side", snapshot.ranked_side or "-"),
        ("ranked score", _format_optional_number(snapshot.ranked_score)),
        ("ranked trades", _format_optional_int(snapshot.ranked_trade_count)),
        ("ranked premium", _format_optional_money(snapshot.ranked_premium)),
        ("interest rank", _format_optional_int(snapshot.interest_rank)),
        ("detail rows", str(snapshot.detail_rows)),
        ("price date", snapshot.price_date.isoformat() if snapshot.price_date else "-"),
        ("close", _format_optional_number(snapshot.close)),
        ("dollar volume", _format_optional_money(snapshot.dollar_volume)),
        ("5d return", _format_percent_value(snapshot.return_5d)),
        ("20d return", _format_percent_value(snapshot.return_20d)),
        ("60d return", _format_percent_value(snapshot.return_60d)),
        ("20d RS vs SPY", _format_percent_value(snapshot.relative_strength_20d_spy)),
        ("20d RS vs QQQ", _format_percent_value(snapshot.relative_strength_20d_qqq)),
        ("MA50 distance", _format_percent_value(snapshot.ma50_distance)),
        ("60d drawdown", _format_percent_value(snapshot.drawdown_60d)),
        ("validation status", snapshot.validation_status),
        ("validation reasons", ", ".join(snapshot.validation_reasons)),
    ]
    if interest_note:
        rows.append(("Trades Of Interest note", interest_note))
    return _key_value_table(rows)


def _flow_event_table(flow_events: tuple[_TickerFlowEvent, ...]) -> str:
    if not flow_events:
        return '<p class="empty">No Bulltard ticker-flow rows found for this candidate date.</p>'
    rows = sorted(
        flow_events,
        key=lambda event: (event.premium or 0.0, event.traded_at),
        reverse=True,
    )[:20]
    parts = [
        "<table>",
        "<thead><tr>"
        "<th>Traded At</th><th>Side</th><th>Order</th><th>Contract</th>"
        "<th>Expiry</th><th>Contracts</th><th>Premium</th><th>Older</th>"
        "</tr></thead>",
        "<tbody>",
    ]
    for event in rows:
        parts.append(
            "<tr>"
            f"<td>{escape(event.traded_at.isoformat(timespec='minutes'))}</td>"
            f"<td>{escape(event.side or '-')}</td>"
            f"<td>{escape(event.order_type)}</td>"
            f"<td>{escape(event.contract)}</td>"
            f"<td>{escape(event.expiry.isoformat())}</td>"
            f"<td>{event.contracts}</td>"
            f"<td>{escape(_format_optional_money(event.premium))}</td>"
            f"<td>{'yes' if event.is_older else 'no'}</td>"
            "</tr>"
        )
    parts.extend(["</tbody>", "</table>"])
    return "\n".join(parts)


def _forward_outcome_table(
    forward_outcomes: tuple[_OpportunityForwardOutcome, ...],
) -> str:
    parts = [
        "<table>",
        "<thead><tr>"
        "<th>Horizon</th><th>Status</th><th>Forward Return</th>"
        "<th>RS vs SPY</th><th>Max Drawdown</th>"
        "</tr></thead>",
        "<tbody>",
    ]
    for outcome in forward_outcomes:
        available = outcome.return_value is not None
        parts.append(
            "<tr>"
            f"<td>{outcome.horizon_days} trading rows</td>"
            f"<td>{'available' if available else 'waiting'}</td>"
            f"<td>{escape(_format_percent_value(outcome.return_value))}</td>"
            f"<td>{escape(_format_percent_value(outcome.relative_strength_spy))}</td>"
            f"<td>{escape(_format_drawdown_value(outcome.max_drawdown))}</td>"
            "</tr>"
        )
    parts.extend(["</tbody>", "</table>"])
    return "\n".join(parts)


def _key_value_table(rows: list[tuple[str, str]]) -> str:
    parts = ["<table>", "<tbody>"]
    for label, value in rows:
        parts.append(f"<tr><td>{escape(label)}</td><td>{escape(value)}</td></tr>")
    parts.extend(["</tbody>", "</table>"])
    return "\n".join(parts)


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


def _format_optional_int(value: int | None) -> str:
    return str(value) if value is not None else "-"


def _format_optional_number(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}"


def _format_percent_value(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:+.1f}%"


def _format_drawdown_value(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{min(0.0, value) * 100:.1f}%"


def _format_optional_money(value: float | None) -> str:
    if value is None:
        return "-"
    return _format_money_compact(value)


def _format_money_compact(value: float) -> str:
    absolute = abs(value)
    for suffix, scale in (("B", 1_000_000_000), ("M", 1_000_000), ("K", 1_000)):
        if absolute >= scale:
            scaled = value / scale
            precision = 0 if abs(scaled) >= 100 else 1
            return f"${scaled:.{precision}f}{suffix}"
    return f"${value:.0f}"


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


def _format_policy_axis(value: float) -> str:
    if value < -0.5:
        return "protect"
    if value > 0.5:
        return "redeploy"
    return "maintain"


def _policy_state_value(policy_state: str) -> int | None:
    if policy_state == "protect":
        return -1
    if policy_state == "redeploy":
        return 1
    if policy_state == "maintain":
        return 0
    return None


def _policy_state_color(policy_state: str) -> str:
    if policy_state == "protect":
        return "#c25a17"
    if policy_state == "redeploy":
        return "#087f8c"
    return "#172026"


def _regime_chart_version_summary(
    snapshots: tuple[RegimeSnapshot, ...],
    policies: tuple[PortfolioPolicySnapshot, ...],
) -> str:
    latest_snapshot = snapshots[-1]
    parts = [
        f"snapshot={latest_snapshot.snapshot_version}",
        f"feature={latest_snapshot.feature_version}",
        f"model={latest_snapshot.model_version}",
        f"action={latest_snapshot.action_version}",
        f"pressure={latest_snapshot.pressure_version}",
    ]
    if policies:
        latest_policy = policies[-1]
        parts.extend(
            (
                f"policy_snapshot={latest_policy.snapshot_version}",
                f"policy={latest_policy.policy_version}",
            )
        )
    return "; ".join(parts)


def _legend(*, width: int, y: int) -> str:
    items = (
        ("#1b6ca8", "SPY / trend"),
        ("#7a4cc2", "QQQ / credit"),
        ("#c25a17", "stretch / volatility"),
        ("#087f8c", "washout / redeploy"),
        ("#7d8790", "no_change shading"),
        ("#172026", "policy state"),
    )
    x = 82
    parts = []
    for color, label in items:
        parts.append(f'<rect x="{x}" y="{y - 9}" width="14" height="4" fill="{color}" />')
        parts.append(_text(x + 20, y - 5, label, css_class="legend"))
        x += 180
    return "\n".join(parts)


def _opportunity_legend(*, symbol: str, y: int) -> str:
    items = (
        ("#1b6ca8", f"{symbol} indexed close"),
        ("#59656f", "SPY benchmark / RS"),
        ("#7a4cc2", "QQQ benchmark / RS"),
        ("#2f8f46", "bullish flow premium"),
        ("#b23b3b", "bearish flow premium"),
        ("#172026", "Bulltard date"),
    )
    x = 82
    parts = []
    for color, label in items:
        parts.append(f'<rect x="{x}" y="{y - 9}" width="14" height="4" fill="{color}" />')
        parts.append(_text(x + 20, y - 5, label, css_class="legend"))
        x += 170
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
  .event-label { font: 700 11px ui-sans-serif, system-ui, sans-serif; fill: #172026; }
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


def _default_regime_chart_path(
    *,
    start_date: date,
    end_date: date,
    signal_time: SignalTime | str,
    snapshot_version: str | None,
) -> Path:
    date_key = (
        start_date.isoformat()
        if start_date == end_date
        else f"{start_date.isoformat()}_to_{end_date.isoformat()}"
    )
    return (
        DEFAULT_CHART_REPORT_ROOT
        / "regime"
        / "market"
        / date_key
        / signal_time_value(signal_time)
        / (snapshot_version or default_snapshot_version(start_date, signal_time=signal_time))
        / "chart.html"
    )


def _default_opportunity_chart_path(
    *,
    source_date: date,
    symbol: str,
    signal_time: SignalTime | str,
    snapshot_version: str | None,
) -> Path:
    return (
        DEFAULT_CHART_REPORT_ROOT
        / "bulltard"
        / "opportunity"
        / symbol
        / source_date.isoformat()
        / signal_time_value(signal_time)
        / (snapshot_version or default_snapshot_version(source_date, signal_time=signal_time))
        / "chart.html"
    )
