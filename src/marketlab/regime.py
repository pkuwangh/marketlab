"""Market regime snapshots from daily price proxies."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from loguru import logger

from marketlab.market_series import (
    DEFAULT_FRED_MARKET_SERIES_IDS,
    DEFAULT_MARKET_SERIES_OBSERVATIONS_ROOT,
    MarketSeriesError,
    MarketSeriesObservation,
    load_market_series_history,
)
from marketlab.market_signals import (
    DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT,
    MARKET_SIGNAL_FEATURE_VERSION,
    MarketSignal,
    MarketSignalError,
    format_market_signals,
    load_market_signal_snapshot,
    write_market_signal_snapshot,
)
from marketlab.prices import (
    DEFAULT_PRICE_OBSERVATIONS_ROOT,
    DailyPriceObservation,
    PriceDataError,
    PriceFetchResult,
    dedupe_symbols,
    fetch_and_write_yahoo_daily_prices,
    load_price_history,
)

DEFAULT_REGIME_SNAPSHOT_ROOT = Path("data/snapshots/regime/market")
DEFAULT_REGIME_PRICE_SYMBOLS = ("SPY", "QQQ", "IWM", "RSP", "HYG", "TLT", "^VIX", "^VVIX")
DEFAULT_REGIME_OUTCOME_HORIZONS = (1, 5, 20, 40, 65, 126)
REGIME_FEATURE_VERSION = "market_regime_features_v0"
REGIME_MODEL_VERSION = "market_regime_score_v0"


class RegimeError(ValueError):
    """Raised when a market regime workflow cannot run."""


@dataclass(frozen=True, slots=True)
class RegimePriceRefreshFailure:
    """One failed regime price refresh."""

    symbol: str
    error: str


@dataclass(frozen=True, slots=True)
class RegimePriceRefreshResult:
    """Result of refreshing market regime price proxies."""

    start_date: date
    end_date: date
    requested_symbols: tuple[str, ...]
    price_results: tuple[PriceFetchResult, ...]
    price_failures: tuple[RegimePriceRefreshFailure, ...]


@dataclass(frozen=True, slots=True)
class RegimeComponentScore:
    """One interpretable component of the market regime score."""

    name: str
    score: int
    status: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "score": self.score,
            "status": self.status,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class RegimeSnapshot:
    """Point-in-time market regime snapshot."""

    source_date: date
    feature_version: str
    model_version: str
    price_date: date | None
    regime: str
    score: int
    confidence: str
    components: tuple[RegimeComponentScore, ...]
    missing_symbols: tuple[str, ...]
    spy_return_20d: float | None
    spy_return_60d: float | None
    spy_ma50_distance: float | None
    spy_ma200_distance: float | None
    spy_realized_vol_20d: float | None
    qqq_return_20d: float | None
    qqq_ma50_distance: float | None
    qqq_ma200_distance: float | None
    rsp_spy_relative_20d: float | None
    iwm_spy_relative_20d: float | None
    hyg_tlt_relative_20d: float | None
    vix_close: float | None
    vvix_close: float | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": "marketlab",
            "snapshot_type": "market-regime",
            "source_date": self.source_date.isoformat(),
            "feature_version": self.feature_version,
            "model_version": self.model_version,
            "price_date": self.price_date.isoformat() if self.price_date else None,
            "regime": self.regime,
            "score": self.score,
            "confidence": self.confidence,
            "components": [component.to_dict() for component in self.components],
            "missing_symbols": list(self.missing_symbols),
            "spy_return_20d": self.spy_return_20d,
            "spy_return_60d": self.spy_return_60d,
            "spy_ma50_distance": self.spy_ma50_distance,
            "spy_ma200_distance": self.spy_ma200_distance,
            "spy_realized_vol_20d": self.spy_realized_vol_20d,
            "qqq_return_20d": self.qqq_return_20d,
            "qqq_ma50_distance": self.qqq_ma50_distance,
            "qqq_ma200_distance": self.qqq_ma200_distance,
            "rsp_spy_relative_20d": self.rsp_spy_relative_20d,
            "iwm_spy_relative_20d": self.iwm_spy_relative_20d,
            "hyg_tlt_relative_20d": self.hyg_tlt_relative_20d,
            "vix_close": self.vix_close,
            "vvix_close": self.vvix_close,
        }


@dataclass(frozen=True, slots=True)
class RegimeSnapshotResult:
    """Result of one market regime snapshot run."""

    source_date: date
    snapshot: RegimeSnapshot
    snapshot_path: Path | None
    table: str
    signals: tuple[MarketSignal, ...] = ()
    signal_snapshot_path: Path | None = None
    signal_table: str = ""
    contradictions: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class RegimeForwardOutcome:
    """One forward market outcome from one regime snapshot."""

    source_date: date
    price_date: date | None
    regime: str
    score: int
    confidence: str
    horizon_days: int
    spy_return: float | None
    qqq_return: float | None
    spy_max_drawdown: float | None
    qqq_max_drawdown: float | None


@dataclass(frozen=True, slots=True)
class RegimeOutcomeSummaryRow:
    """Aggregate forward market outcome row for one regime bucket and horizon."""

    bucket: str
    horizon_days: int
    snapshot_count: int
    available_count: int
    avg_spy_return: float | None
    avg_qqq_return: float | None
    avg_spy_max_drawdown: float | None
    avg_qqq_max_drawdown: float | None


@dataclass(frozen=True, slots=True)
class RegimeOutcomeResult:
    """Result of one market regime outcome replay."""

    start_date: date
    end_date: date
    outcomes: tuple[RegimeForwardOutcome, ...]
    summary_rows: tuple[RegimeOutcomeSummaryRow, ...]
    table: str


@dataclass(frozen=True, slots=True)
class MarketSignalForwardOutcome:
    """One forward market outcome from one market signal row."""

    source_date: date
    family: str
    name: str
    status: str
    score: int
    horizon_days: int
    spy_return: float | None
    qqq_return: float | None
    spy_max_drawdown: float | None
    qqq_max_drawdown: float | None


@dataclass(frozen=True, slots=True)
class MarketSignalOutcomeSummaryRow:
    """Aggregate forward market outcome row for one market signal bucket."""

    bucket: str
    horizon_days: int
    signal_count: int
    available_count: int
    avg_spy_return: float | None
    avg_qqq_return: float | None
    avg_spy_max_drawdown: float | None
    avg_qqq_max_drawdown: float | None


@dataclass(frozen=True, slots=True)
class MarketSignalOutcomeResult:
    """Result of one market signal outcome replay."""

    start_date: date
    end_date: date
    outcomes: tuple[MarketSignalForwardOutcome, ...]
    summary_rows: tuple[MarketSignalOutcomeSummaryRow, ...]
    table: str


@dataclass(frozen=True, slots=True)
class _SymbolFeatures:
    symbol: str
    price_date: date | None
    close: float | None
    return_20d: float | None
    return_60d: float | None
    ma50_distance: float | None
    ma200_distance: float | None
    realized_vol_20d: float | None


def refresh_regime_prices(
    *,
    start_date: date,
    end_date: date,
    price_root: Path = DEFAULT_PRICE_OBSERVATIONS_ROOT,
    symbols: tuple[str, ...] = DEFAULT_REGIME_PRICE_SYMBOLS,
    downloader=None,
) -> RegimePriceRefreshResult:
    """Refresh Yahoo price observations for market regime proxies."""

    if end_date < start_date:
        raise RegimeError("Price refresh end date must be on or after start date")

    requested_symbols = dedupe_symbols(symbols)
    price_results: list[PriceFetchResult] = []
    price_failures: list[RegimePriceRefreshFailure] = []
    for symbol in requested_symbols:
        try:
            price_results.extend(
                fetch_and_write_yahoo_daily_prices(
                    symbols=(symbol,),
                    start_date=start_date,
                    end_date=end_date,
                    output_root=price_root,
                    downloader=downloader,
                )
            )
        except PriceDataError as exc:
            price_failures.append(RegimePriceRefreshFailure(symbol=symbol, error=str(exc)))
            logger.bind(
                symbol=symbol,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                error=str(exc),
            ).error("Failed market regime price refresh")

    result = RegimePriceRefreshResult(
        start_date=start_date,
        end_date=end_date,
        requested_symbols=requested_symbols,
        price_results=tuple(price_results),
        price_failures=tuple(price_failures),
    )
    logger.bind(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        requested_symbols=len(requested_symbols),
        price_successes=len(price_results),
        price_failures=len(price_failures),
        price_root=str(price_root),
    ).success("Refreshed market regime prices")
    return result


def compute_regime_snapshot(
    *,
    source_date: date,
    price_root: Path = DEFAULT_PRICE_OBSERVATIONS_ROOT,
    market_series_root: Path = DEFAULT_MARKET_SERIES_OBSERVATIONS_ROOT,
    snapshot_root: Path = DEFAULT_REGIME_SNAPSHOT_ROOT,
    signal_snapshot_root: Path = DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT,
    write_snapshot: bool = True,
) -> RegimeSnapshotResult:
    """Compute and optionally persist one market regime snapshot."""

    histories = _load_histories(symbols=DEFAULT_REGIME_PRICE_SYMBOLS, price_root=price_root)
    market_series_histories = _load_market_series_histories(
        series_ids=DEFAULT_FRED_MARKET_SERIES_IDS,
        observations_root=market_series_root,
    )
    market_series = {
        series_id: _market_series_asof(history, source_date)
        for series_id, history in market_series_histories.items()
    }
    features = {
        symbol: _symbol_features(
            symbol=symbol,
            source_date=source_date,
            history=histories[symbol],
        )
        for symbol in DEFAULT_REGIME_PRICE_SYMBOLS
    }
    components = _score_components(features)
    score = sum(component.score for component in components)
    missing_market_signal_count = _missing_market_signal_count(
        features=features,
        market_series=market_series,
    )
    missing_symbols = tuple(
        symbol for symbol, symbol_features in features.items() if symbol_features.price_date is None
    )
    snapshot = RegimeSnapshot(
        source_date=source_date,
        feature_version=REGIME_FEATURE_VERSION,
        model_version=REGIME_MODEL_VERSION,
        price_date=features["SPY"].price_date,
        regime=_regime_label(score),
        score=score,
        confidence=_confidence(
            score=score,
            components=components,
            missing_market_signal_count=missing_market_signal_count,
        ),
        components=components,
        missing_symbols=missing_symbols,
        spy_return_20d=features["SPY"].return_20d,
        spy_return_60d=features["SPY"].return_60d,
        spy_ma50_distance=features["SPY"].ma50_distance,
        spy_ma200_distance=features["SPY"].ma200_distance,
        spy_realized_vol_20d=features["SPY"].realized_vol_20d,
        qqq_return_20d=features["QQQ"].return_20d,
        qqq_ma50_distance=features["QQQ"].ma50_distance,
        qqq_ma200_distance=features["QQQ"].ma200_distance,
        rsp_spy_relative_20d=_relative_return(features["RSP"], features["SPY"]),
        iwm_spy_relative_20d=_relative_return(features["IWM"], features["SPY"]),
        hyg_tlt_relative_20d=_relative_return(features["HYG"], features["TLT"]),
        vix_close=features["^VIX"].close,
        vvix_close=features["^VVIX"].close,
    )
    snapshot_path = (
        write_regime_snapshot(snapshot, snapshot_root=snapshot_root) if write_snapshot else None
    )
    signals = _market_signals_from_snapshot(
        snapshot,
        features=features,
        market_series=market_series,
    )
    try:
        signal_snapshot_path = (
            write_market_signal_snapshot(signals, snapshot_root=signal_snapshot_root)
            if write_snapshot
            else None
        )
    except MarketSignalError as exc:
        raise RegimeError(str(exc)) from exc
    contradictions = _market_signal_contradictions(signals)
    table = format_regime_snapshot(snapshot)
    signal_table = format_market_signals(signals)
    logger.bind(
        source_date=source_date.isoformat(),
        price_date=snapshot.price_date.isoformat() if snapshot.price_date else None,
        regime=snapshot.regime,
        score=snapshot.score,
        confidence=snapshot.confidence,
        snapshot_path=str(snapshot_path) if snapshot_path else None,
        market_signal_count=len(signals),
        market_signal_contradiction_count=len(contradictions),
        market_signal_snapshot_path=str(signal_snapshot_path) if signal_snapshot_path else None,
    ).success("Computed market regime snapshot")
    return RegimeSnapshotResult(
        source_date=source_date,
        snapshot=snapshot,
        snapshot_path=snapshot_path,
        table=table,
        signals=signals,
        signal_snapshot_path=signal_snapshot_path,
        signal_table=signal_table,
        contradictions=contradictions,
    )


def write_regime_snapshot(
    snapshot: RegimeSnapshot,
    *,
    snapshot_root: Path = DEFAULT_REGIME_SNAPSHOT_ROOT,
) -> Path:
    """Write one market regime snapshot."""

    path = snapshot_root / f"{snapshot.source_date.isoformat()}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot.to_dict(), sort_keys=True) + "\n", encoding="utf-8")
    logger.bind(
        source_date=snapshot.source_date.isoformat(),
        snapshot_path=str(path),
    ).success("Wrote market regime snapshot")
    return path


def load_regime_snapshot(
    *,
    source_date: date,
    snapshot_root: Path = DEFAULT_REGIME_SNAPSHOT_ROOT,
) -> RegimeSnapshot | None:
    """Load one market regime snapshot if present."""

    path = snapshot_root / f"{source_date.isoformat()}.json"
    if not path.is_file():
        return None
    try:
        return _snapshot_from_dict(json.loads(path.read_text(encoding="utf-8")))
    except OSError as exc:
        raise RegimeError(f"Failed to read market regime snapshot: {path}") from exc
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise RegimeError(f"Invalid market regime snapshot file: {path}") from exc


def format_regime_snapshot(snapshot: RegimeSnapshot) -> str:
    """Format a market regime snapshot as a compact component table."""

    rows = [["component", "score", "status", "reason"]]
    for component in snapshot.components:
        rows.append(
            [
                component.name,
                _format_score(component.score),
                component.status,
                component.reason,
            ]
        )
    return _format_table(rows)


def _market_signals_from_snapshot(
    snapshot: RegimeSnapshot,
    *,
    features: dict[str, _SymbolFeatures],
    market_series: dict[str, MarketSeriesObservation | None],
) -> tuple[MarketSignal, ...]:
    signals = [
        MarketSignal(
            source_date=snapshot.source_date,
            feature_version=MARKET_SIGNAL_FEATURE_VERSION,
            family=component.name,
            name="price_proxy",
            status=component.status,
            score=component.score,
            value=_component_value(snapshot, component.name),
            unit="text",
            source="yahoo_price_proxy",
            observed_date=snapshot.price_date,
            availability_date=snapshot.price_date,
            reason=component.reason,
        )
        for component in snapshot.components
    ]
    signals.append(_vvix_signal(snapshot=snapshot, features=features["^VVIX"]))
    signals.extend(_fred_market_signals(source_date=snapshot.source_date, series=market_series))
    return tuple(signals)


def _vvix_signal(*, snapshot: RegimeSnapshot, features: _SymbolFeatures) -> MarketSignal:
    if features.close is None:
        return MarketSignal(
            source_date=snapshot.source_date,
            feature_version=MARKET_SIGNAL_FEATURE_VERSION,
            family="volatility",
            name="vol_of_vol",
            status="missing",
            score=0,
            value=None,
            unit="index",
            source="yahoo_vvix",
            observed_date=None,
            availability_date=None,
            reason="VVIX is unavailable",
        )
    if features.close >= 120.0:
        status = "stressed"
        score = -1
        reason = "VVIX shows elevated volatility-of-volatility"
    elif features.close <= 90.0:
        status = "calm"
        score = 1
        reason = "VVIX shows contained volatility-of-volatility"
    else:
        status = "mixed"
        score = 0
        reason = "VVIX is neither calm nor stressed"
    return MarketSignal(
        source_date=snapshot.source_date,
        feature_version=MARKET_SIGNAL_FEATURE_VERSION,
        family="volatility",
        name="vol_of_vol",
        status=status,
        score=score,
        value=features.close,
        unit="index",
        source="yahoo_vvix",
        observed_date=features.price_date,
        availability_date=features.price_date,
        reason=reason,
    )


def _fred_market_signals(
    *,
    source_date: date,
    series: dict[str, MarketSeriesObservation | None],
) -> tuple[MarketSignal, ...]:
    return (
        _high_yield_oas_signal(source_date=source_date, row=series["BAMLH0A0HYM2"]),
        _nfci_signal(source_date=source_date, row=series["NFCI"]),
        _yield_curve_signal(
            source_date=source_date,
            ten_year=series["DGS10"],
            two_year=series["DGS2"],
        ),
    )


def _high_yield_oas_signal(
    *,
    source_date: date,
    row: MarketSeriesObservation | None,
) -> MarketSignal:
    if row is None:
        return _missing_fred_signal(
            source_date=source_date,
            family="credit",
            name="credit_spread",
            unit="percent_level",
            source="fred:BAMLH0A0HYM2",
            reason="FRED high-yield OAS is unavailable as of source date",
        )
    if row.value >= 5.0:
        status = "stressed"
        score = -1
        reason = "High-yield credit spreads are elevated"
    elif row.value <= 3.5:
        status = "supportive"
        score = 1
        reason = "High-yield credit spreads are contained"
    else:
        status = "mixed"
        score = 0
        reason = "High-yield credit spreads are neither tight nor stressed"
    return _fred_signal(
        source_date=source_date,
        family="credit",
        name="credit_spread",
        status=status,
        score=score,
        row=row,
        source="fred:BAMLH0A0HYM2",
        reason=reason,
    )


def _nfci_signal(
    *,
    source_date: date,
    row: MarketSeriesObservation | None,
) -> MarketSignal:
    if row is None:
        return _missing_fred_signal(
            source_date=source_date,
            family="liquidity",
            name="financial_conditions",
            unit="index",
            source="fred:NFCI",
            reason="FRED NFCI is unavailable as of source date",
        )
    if row.value > 0.25:
        status = "tight"
        score = -1
        reason = "NFCI financial conditions are tighter than average"
    elif row.value < -0.25:
        status = "loose"
        score = 1
        reason = "NFCI financial conditions are looser than average"
    else:
        status = "neutral"
        score = 0
        reason = "NFCI financial conditions are near average"
    return _fred_signal(
        source_date=source_date,
        family="liquidity",
        name="financial_conditions",
        status=status,
        score=score,
        row=row,
        source="fred:NFCI",
        reason=reason,
    )


def _yield_curve_signal(
    *,
    source_date: date,
    ten_year: MarketSeriesObservation | None,
    two_year: MarketSeriesObservation | None,
) -> MarketSignal:
    if ten_year is None or two_year is None:
        return _missing_fred_signal(
            source_date=source_date,
            family="rates",
            name="yield_curve",
            unit="percentage_points",
            source="fred:DGS10-DGS2",
            reason="FRED 10y or 2y Treasury yield is unavailable as of source date",
        )

    value = ten_year.value - two_year.value
    if value <= -0.25:
        status = "inverted"
        score = -1
        reason = "10y-2y Treasury curve is meaningfully inverted"
    elif value >= 0.50:
        status = "normal"
        score = 1
        reason = "10y-2y Treasury curve has a positive slope"
    else:
        status = "flat"
        score = 0
        reason = "10y-2y Treasury curve is flat"
    return MarketSignal(
        source_date=source_date,
        feature_version=MARKET_SIGNAL_FEATURE_VERSION,
        family="rates",
        name="yield_curve",
        status=status,
        score=score,
        value=value,
        unit="percentage_points",
        source="fred:DGS10-DGS2",
        observed_date=max(ten_year.observed_date, two_year.observed_date),
        availability_date=max(ten_year.availability_date, two_year.availability_date),
        reason=reason,
    )


def _fred_signal(
    *,
    source_date: date,
    family: str,
    name: str,
    status: str,
    score: int,
    row: MarketSeriesObservation,
    source: str,
    reason: str,
) -> MarketSignal:
    return MarketSignal(
        source_date=source_date,
        feature_version=MARKET_SIGNAL_FEATURE_VERSION,
        family=family,
        name=name,
        status=status,
        score=score,
        value=row.value,
        unit=row.unit,
        source=source,
        observed_date=row.observed_date,
        availability_date=row.availability_date,
        reason=reason,
    )


def _missing_fred_signal(
    *,
    source_date: date,
    family: str,
    name: str,
    unit: str,
    source: str,
    reason: str,
) -> MarketSignal:
    return MarketSignal(
        source_date=source_date,
        feature_version=MARKET_SIGNAL_FEATURE_VERSION,
        family=family,
        name=name,
        status="missing",
        score=0,
        value=None,
        unit=unit,
        source=source,
        observed_date=None,
        availability_date=None,
        reason=reason,
    )


def _missing_market_signal_count(
    *,
    features: dict[str, _SymbolFeatures],
    market_series: dict[str, MarketSeriesObservation | None],
) -> int:
    missing_count = 0
    if features["^VVIX"].price_date is None:
        missing_count += 1
    if market_series["BAMLH0A0HYM2"] is None:
        missing_count += 1
    if market_series["NFCI"] is None:
        missing_count += 1
    if market_series["DGS10"] is None or market_series["DGS2"] is None:
        missing_count += 1
    return missing_count


def _market_signal_contradictions(signals: tuple[MarketSignal, ...]) -> tuple[str, ...]:
    positive = tuple(_signal_label(signal) for signal in signals if signal.score > 0)
    negative = tuple(_signal_label(signal) for signal in signals if signal.score < 0)
    if not positive or not negative:
        return ()
    return (f"positive={','.join(positive)} negative={','.join(negative)}",)


def _signal_label(signal: MarketSignal) -> str:
    return f"{signal.family}/{signal.name}:{signal.status}"


def _component_value(snapshot: RegimeSnapshot, component_name: str) -> str:
    if component_name == "trend":
        return (
            f"SPY 20d {_format_percent(snapshot.spy_return_20d)}, "
            f"SPY 60d {_format_percent(snapshot.spy_return_60d)}, "
            f"QQQ 20d {_format_percent(snapshot.qqq_return_20d)}"
        )
    if component_name == "volatility":
        return (
            f"VIX {_format_index(snapshot.vix_close)}, "
            f"SPY rv20 {_format_percent(snapshot.spy_realized_vol_20d)}"
        )
    if component_name == "breadth":
        return (
            f"RSP/SPY 20d {_format_percent(snapshot.rsp_spy_relative_20d)}, "
            f"IWM/SPY 20d {_format_percent(snapshot.iwm_spy_relative_20d)}"
        )
    if component_name == "credit":
        return f"HYG/TLT 20d {_format_percent(snapshot.hyg_tlt_relative_20d)}"
    return "-"


def compute_regime_outcomes(
    *,
    start_date: date,
    end_date: date,
    snapshot_root: Path = DEFAULT_REGIME_SNAPSHOT_ROOT,
    price_root: Path = DEFAULT_PRICE_OBSERVATIONS_ROOT,
    horizons: tuple[int, ...] = DEFAULT_REGIME_OUTCOME_HORIZONS,
) -> RegimeOutcomeResult:
    """Replay forward SPY/QQQ outcomes for saved market regime snapshots."""

    if end_date < start_date:
        raise RegimeError("End date must be on or after start date")

    snapshots = _load_regime_snapshots_in_range(
        start_date=start_date,
        end_date=end_date,
        snapshot_root=snapshot_root,
    )
    if not snapshots:
        raise RegimeError(f"No market regime snapshots found from {start_date} to {end_date}")

    histories = _load_histories(symbols=("SPY", "QQQ"), price_root=price_root)
    outcomes = tuple(
        outcome
        for snapshot in snapshots
        for outcome in _regime_snapshot_outcomes(
            snapshot=snapshot,
            histories=histories,
            horizons=horizons,
        )
    )
    summary_rows = summarize_regime_outcomes(outcomes)
    table = format_regime_outcome_summary(summary_rows)
    logger.bind(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        snapshot_count=len(snapshots),
        outcome_count=len(outcomes),
    ).success("Computed market regime outcomes")
    return RegimeOutcomeResult(
        start_date=start_date,
        end_date=end_date,
        outcomes=outcomes,
        summary_rows=summary_rows,
        table=table,
    )


def compute_market_signal_outcomes(
    *,
    start_date: date,
    end_date: date,
    signal_snapshot_root: Path = DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT,
    price_root: Path = DEFAULT_PRICE_OBSERVATIONS_ROOT,
    horizons: tuple[int, ...] = DEFAULT_REGIME_OUTCOME_HORIZONS,
) -> MarketSignalOutcomeResult:
    """Replay forward SPY/QQQ outcomes for saved market signal rows."""

    if end_date < start_date:
        raise RegimeError("End date must be on or after start date")

    signals = _load_market_signals_in_range(
        start_date=start_date,
        end_date=end_date,
        signal_snapshot_root=signal_snapshot_root,
    )
    if not signals:
        raise RegimeError(f"No market signal snapshots found from {start_date} to {end_date}")

    histories = _load_histories(symbols=("SPY", "QQQ"), price_root=price_root)
    outcomes = tuple(
        outcome
        for signal in signals
        for outcome in _market_signal_outcomes(
            signal=signal,
            histories=histories,
            horizons=horizons,
        )
    )
    summary_rows = summarize_market_signal_outcomes(outcomes)
    table = format_market_signal_outcome_summary(summary_rows)
    logger.bind(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        signal_count=len(signals),
        outcome_count=len(outcomes),
    ).success("Computed market signal outcomes")
    return MarketSignalOutcomeResult(
        start_date=start_date,
        end_date=end_date,
        outcomes=outcomes,
        summary_rows=summary_rows,
        table=table,
    )


def summarize_regime_outcomes(
    outcomes: tuple[RegimeForwardOutcome, ...],
) -> tuple[RegimeOutcomeSummaryRow, ...]:
    """Summarize forward market outcomes by regime bucket."""

    buckets: dict[str, list[RegimeForwardOutcome]] = {"all": list(outcomes)}
    for outcome in outcomes:
        buckets.setdefault(f"regime:{outcome.regime}", []).append(outcome)

    rows: list[RegimeOutcomeSummaryRow] = []
    for bucket in sorted(buckets):
        bucket_outcomes = tuple(buckets[bucket])
        for horizon in sorted({outcome.horizon_days for outcome in bucket_outcomes}):
            horizon_outcomes = tuple(
                outcome for outcome in bucket_outcomes if outcome.horizon_days == horizon
            )
            available = tuple(
                outcome
                for outcome in horizon_outcomes
                if outcome.spy_return is not None and outcome.qqq_return is not None
            )
            rows.append(
                RegimeOutcomeSummaryRow(
                    bucket=bucket,
                    horizon_days=horizon,
                    snapshot_count=len(horizon_outcomes),
                    available_count=len(available),
                    avg_spy_return=_average(outcome.spy_return for outcome in available),
                    avg_qqq_return=_average(outcome.qqq_return for outcome in available),
                    avg_spy_max_drawdown=_average(
                        outcome.spy_max_drawdown for outcome in available
                    ),
                    avg_qqq_max_drawdown=_average(
                        outcome.qqq_max_drawdown for outcome in available
                    ),
                )
            )
    return tuple(rows)


def summarize_market_signal_outcomes(
    outcomes: tuple[MarketSignalForwardOutcome, ...],
) -> tuple[MarketSignalOutcomeSummaryRow, ...]:
    """Summarize forward market outcomes by market signal bucket."""

    buckets: dict[str, list[MarketSignalForwardOutcome]] = {"all": list(outcomes)}
    for outcome in outcomes:
        buckets.setdefault(f"family:{outcome.family}", []).append(outcome)
        buckets.setdefault(
            f"signal:{outcome.family}/{outcome.name}/{outcome.status}",
            [],
        ).append(outcome)

    rows: list[MarketSignalOutcomeSummaryRow] = []
    for bucket in sorted(buckets):
        bucket_outcomes = tuple(buckets[bucket])
        for horizon in sorted({outcome.horizon_days for outcome in bucket_outcomes}):
            horizon_outcomes = tuple(
                outcome for outcome in bucket_outcomes if outcome.horizon_days == horizon
            )
            available = tuple(
                outcome
                for outcome in horizon_outcomes
                if outcome.spy_return is not None and outcome.qqq_return is not None
            )
            rows.append(
                MarketSignalOutcomeSummaryRow(
                    bucket=bucket,
                    horizon_days=horizon,
                    signal_count=len(horizon_outcomes),
                    available_count=len(available),
                    avg_spy_return=_average(outcome.spy_return for outcome in available),
                    avg_qqq_return=_average(outcome.qqq_return for outcome in available),
                    avg_spy_max_drawdown=_average(
                        outcome.spy_max_drawdown for outcome in available
                    ),
                    avg_qqq_max_drawdown=_average(
                        outcome.qqq_max_drawdown for outcome in available
                    ),
                )
            )
    return tuple(rows)


def format_regime_outcome_summary(rows: tuple[RegimeOutcomeSummaryRow, ...]) -> str:
    """Format market regime outcome summaries as a compact table."""

    available_rows = tuple(row for row in rows if row.available_count > 0)
    if not available_rows:
        return "No available regime outcome rows found."

    table = [
        [
            "bucket",
            "horizon",
            "snapshots",
            "available",
            "avg_spy",
            "avg_qqq",
            "spy_dd",
            "qqq_dd",
        ]
    ]
    for row in available_rows:
        table.append(
            [
                row.bucket,
                f"{row.horizon_days}d",
                str(row.snapshot_count),
                str(row.available_count),
                _format_percent(row.avg_spy_return),
                _format_percent(row.avg_qqq_return),
                _format_drawdown(row.avg_spy_max_drawdown),
                _format_drawdown(row.avg_qqq_max_drawdown),
            ]
        )
    return _format_table(table)


def format_market_signal_outcome_summary(
    rows: tuple[MarketSignalOutcomeSummaryRow, ...],
) -> str:
    """Format market signal outcome summaries as a compact table."""

    available_rows = tuple(row for row in rows if row.available_count > 0)
    if not available_rows:
        return "No available market signal outcome rows found."

    table = [
        [
            "bucket",
            "horizon",
            "signals",
            "available",
            "avg_spy",
            "avg_qqq",
            "spy_dd",
            "qqq_dd",
        ]
    ]
    for row in available_rows:
        table.append(
            [
                row.bucket,
                f"{row.horizon_days}d",
                str(row.signal_count),
                str(row.available_count),
                _format_percent(row.avg_spy_return),
                _format_percent(row.avg_qqq_return),
                _format_drawdown(row.avg_spy_max_drawdown),
                _format_drawdown(row.avg_qqq_max_drawdown),
            ]
        )
    return _format_table(table)


def _load_histories(
    *,
    symbols: tuple[str, ...],
    price_root: Path,
) -> dict[str, tuple[DailyPriceObservation, ...]]:
    histories: dict[str, tuple[DailyPriceObservation, ...]] = {}
    for symbol in symbols:
        try:
            histories[symbol] = load_price_history(symbol=symbol, price_root=price_root)
        except PriceDataError as exc:
            raise RegimeError(str(exc)) from exc
    return histories


def _load_market_series_histories(
    *,
    series_ids: tuple[str, ...],
    observations_root: Path,
) -> dict[str, tuple[MarketSeriesObservation, ...]]:
    histories: dict[str, tuple[MarketSeriesObservation, ...]] = {}
    for series_id in series_ids:
        try:
            histories[series_id] = load_market_series_history(
                series_id=series_id,
                observations_root=observations_root,
            )
        except MarketSeriesError as exc:
            raise RegimeError(str(exc)) from exc
    return histories


def _market_series_asof(
    history: tuple[MarketSeriesObservation, ...],
    source_date: date,
) -> MarketSeriesObservation | None:
    for row in reversed(history):
        if row.availability_date <= source_date:
            return row
    return None


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
        if start_date <= source_date <= end_date:
            snapshot = load_regime_snapshot(source_date=source_date, snapshot_root=snapshot_root)
            if snapshot is not None:
                snapshots.append(snapshot)
    return tuple(snapshots)


def _load_market_signals_in_range(
    *,
    start_date: date,
    end_date: date,
    signal_snapshot_root: Path,
) -> tuple[MarketSignal, ...]:
    signals: list[MarketSignal] = []
    for path in sorted(signal_snapshot_root.glob("*.jsonl")):
        try:
            source_date = date.fromisoformat(path.stem)
        except ValueError:
            continue
        if start_date <= source_date <= end_date:
            signals.extend(
                load_market_signal_snapshot(
                    source_date=source_date,
                    snapshot_root=signal_snapshot_root,
                )
            )
    return tuple(signals)


def _regime_snapshot_outcomes(
    *,
    snapshot: RegimeSnapshot,
    histories: dict[str, tuple[DailyPriceObservation, ...]],
    horizons: tuple[int, ...],
) -> tuple[RegimeForwardOutcome, ...]:
    spy_history = histories.get("SPY", ())
    qqq_history = histories.get("QQQ", ())
    spy_index = _exact_date_index(spy_history, snapshot.price_date)
    qqq_index = _exact_date_index(qqq_history, snapshot.price_date)
    return tuple(
        RegimeForwardOutcome(
            source_date=snapshot.source_date,
            price_date=snapshot.price_date,
            regime=snapshot.regime,
            score=snapshot.score,
            confidence=snapshot.confidence,
            horizon_days=horizon,
            spy_return=_forward_return(spy_history, index=spy_index, horizon=horizon),
            qqq_return=_forward_return(qqq_history, index=qqq_index, horizon=horizon),
            spy_max_drawdown=_forward_max_drawdown(spy_history, index=spy_index, horizon=horizon),
            qqq_max_drawdown=_forward_max_drawdown(qqq_history, index=qqq_index, horizon=horizon),
        )
        for horizon in horizons
    )


def _market_signal_outcomes(
    *,
    signal: MarketSignal,
    histories: dict[str, tuple[DailyPriceObservation, ...]],
    horizons: tuple[int, ...],
) -> tuple[MarketSignalForwardOutcome, ...]:
    spy_history = histories.get("SPY", ())
    qqq_history = histories.get("QQQ", ())
    spy_index = _asof_index(spy_history, signal.source_date)
    qqq_index = _asof_index(qqq_history, signal.source_date)
    return tuple(
        MarketSignalForwardOutcome(
            source_date=signal.source_date,
            family=signal.family,
            name=signal.name,
            status=signal.status,
            score=signal.score,
            horizon_days=horizon,
            spy_return=_forward_return(spy_history, index=spy_index, horizon=horizon),
            qqq_return=_forward_return(qqq_history, index=qqq_index, horizon=horizon),
            spy_max_drawdown=_forward_max_drawdown(spy_history, index=spy_index, horizon=horizon),
            qqq_max_drawdown=_forward_max_drawdown(qqq_history, index=qqq_index, horizon=horizon),
        )
        for horizon in horizons
    )


def _symbol_features(
    *,
    symbol: str,
    source_date: date,
    history: tuple[DailyPriceObservation, ...],
) -> _SymbolFeatures:
    index = _asof_index(history, source_date)
    if index is None:
        return _empty_symbol_features(symbol)
    return _SymbolFeatures(
        symbol=symbol,
        price_date=history[index].observed_date,
        close=history[index].return_close,
        return_20d=_lookback_return(history, index=index, lookback=20),
        return_60d=_lookback_return(history, index=index, lookback=60),
        ma50_distance=_moving_average_distance(history, index=index, window=50),
        ma200_distance=_moving_average_distance(history, index=index, window=200),
        realized_vol_20d=_realized_volatility(history, index=index, lookback=20),
    )


def _empty_symbol_features(symbol: str) -> _SymbolFeatures:
    return _SymbolFeatures(
        symbol=symbol,
        price_date=None,
        close=None,
        return_20d=None,
        return_60d=None,
        ma50_distance=None,
        ma200_distance=None,
        realized_vol_20d=None,
    )


def _score_components(
    features: dict[str, _SymbolFeatures],
) -> tuple[RegimeComponentScore, ...]:
    return (
        _score_trend(features),
        _score_volatility(features),
        _score_breadth(features),
        _score_credit(features),
    )


def _score_trend(features: dict[str, _SymbolFeatures]) -> RegimeComponentScore:
    spy = features["SPY"]
    qqq = features["QQQ"]
    required = (
        spy.return_20d,
        spy.return_60d,
        spy.ma50_distance,
        spy.ma200_distance,
        qqq.return_20d,
        qqq.ma50_distance,
        qqq.ma200_distance,
    )
    if any(value is None for value in required):
        return RegimeComponentScore(
            name="trend",
            score=0,
            status="missing",
            reason="SPY/QQQ trend history is incomplete",
        )

    assert spy.return_20d is not None
    assert spy.return_60d is not None
    assert spy.ma50_distance is not None
    assert spy.ma200_distance is not None
    assert qqq.return_20d is not None
    assert qqq.ma50_distance is not None
    assert qqq.ma200_distance is not None
    if (
        spy.return_20d > 0
        and spy.return_60d > 0
        and spy.ma50_distance > 0
        and spy.ma200_distance > 0
        and qqq.return_20d > 0
        and qqq.ma50_distance > 0
        and qqq.ma200_distance > 0
    ):
        return RegimeComponentScore(
            name="trend",
            score=2,
            status="constructive",
            reason="SPY and QQQ are rising and above 50/200d averages",
        )
    if (
        spy.return_20d < 0
        and spy.ma50_distance < 0
        and qqq.return_20d < 0
        and qqq.ma50_distance < 0
    ) or (spy.ma200_distance < 0 and qqq.ma200_distance < 0):
        return RegimeComponentScore(
            name="trend",
            score=-2,
            status="weak",
            reason="SPY and QQQ trend is below key averages",
        )
    return RegimeComponentScore(
        name="trend",
        score=0,
        status="mixed",
        reason="SPY/QQQ trend is not aligned",
    )


def _score_volatility(features: dict[str, _SymbolFeatures]) -> RegimeComponentScore:
    spy_vol = features["SPY"].realized_vol_20d
    vix_close = features["^VIX"].close
    if spy_vol is None and vix_close is None:
        return RegimeComponentScore(
            name="volatility",
            score=0,
            status="missing",
            reason="SPY realized volatility and VIX are unavailable",
        )
    if (vix_close is not None and vix_close >= 25.0) or (spy_vol is not None and spy_vol >= 0.30):
        return RegimeComponentScore(
            name="volatility",
            score=-1,
            status="elevated",
            reason="VIX or SPY realized volatility is elevated",
        )
    if vix_close is not None and vix_close <= 18.0 and (spy_vol is None or spy_vol <= 0.20):
        return RegimeComponentScore(
            name="volatility",
            score=1,
            status="calm",
            reason="VIX is calm and SPY realized volatility is contained",
        )
    return RegimeComponentScore(
        name="volatility",
        score=0,
        status="mixed",
        reason="Volatility is neither clearly calm nor stressed",
    )


def _score_breadth(features: dict[str, _SymbolFeatures]) -> RegimeComponentScore:
    rsp_spy = _relative_return(features["RSP"], features["SPY"])
    iwm_spy = _relative_return(features["IWM"], features["SPY"])
    if rsp_spy is None and iwm_spy is None:
        return RegimeComponentScore(
            name="breadth",
            score=0,
            status="missing",
            reason="RSP/SPY and IWM/SPY relative returns are unavailable",
        )
    if _ge(rsp_spy, -0.01) and _ge(iwm_spy, -0.02):
        return RegimeComponentScore(
            name="breadth",
            score=1,
            status="broad",
            reason="Equal-weight and small-cap proxies are participating",
        )
    if _lt(rsp_spy, -0.03) and _lt(iwm_spy, -0.03):
        return RegimeComponentScore(
            name="breadth",
            score=-1,
            status="narrow",
            reason="Equal-weight and small-cap proxies lag SPY",
        )
    return RegimeComponentScore(
        name="breadth",
        score=0,
        status="mixed",
        reason="Participation proxies are mixed",
    )


def _score_credit(features: dict[str, _SymbolFeatures]) -> RegimeComponentScore:
    hyg_tlt = _relative_return(features["HYG"], features["TLT"])
    if hyg_tlt is None:
        return RegimeComponentScore(
            name="credit",
            score=0,
            status="missing",
            reason="HYG/TLT relative return is unavailable",
        )
    if hyg_tlt > 0.01:
        return RegimeComponentScore(
            name="credit",
            score=1,
            status="risk_appetite",
            reason="High yield is outperforming Treasuries",
        )
    if hyg_tlt < -0.02:
        return RegimeComponentScore(
            name="credit",
            score=-1,
            status="defensive",
            reason="High yield is lagging Treasuries",
        )
    return RegimeComponentScore(
        name="credit",
        score=0,
        status="mixed",
        reason="Credit/rates proxy is neutral",
    )


def _regime_label(score: int) -> str:
    if score >= 2:
        return "risk_on"
    if score <= -2:
        return "risk_off"
    return "neutral"


def _confidence(
    *,
    score: int,
    components: tuple[RegimeComponentScore, ...],
    missing_market_signal_count: int = 0,
) -> str:
    available_components = sum(1 for component in components if component.status != "missing")
    if available_components < 3:
        return "low"
    if abs(score) >= 4:
        confidence = "high"
    elif abs(score) >= 2:
        confidence = "medium"
    else:
        confidence = "low"
    if missing_market_signal_count >= 3:
        return _downgrade_confidence(confidence, steps=2)
    if missing_market_signal_count > 0:
        return _downgrade_confidence(confidence, steps=1)
    return confidence


def _downgrade_confidence(confidence: str, *, steps: int) -> str:
    levels = ("low", "medium", "high")
    index = levels.index(confidence)
    return levels[max(0, index - steps)]


def _relative_return(
    left: _SymbolFeatures,
    right: _SymbolFeatures,
) -> float | None:
    if left.return_20d is None or right.return_20d is None:
        return None
    return left.return_20d - right.return_20d


def _asof_index(history: tuple[DailyPriceObservation, ...], source_date: date) -> int | None:
    for index in range(len(history) - 1, -1, -1):
        if history[index].observed_date <= source_date:
            return index
    return None


def _exact_date_index(
    history: tuple[DailyPriceObservation, ...],
    observed_date: date | None,
) -> int | None:
    if observed_date is None:
        return None
    for index, row in enumerate(history):
        if row.observed_date == observed_date:
            return index
    return None


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


def _lookback_return(
    history: tuple[DailyPriceObservation, ...],
    *,
    index: int,
    lookback: int,
) -> float | None:
    past_index = index - lookback
    if past_index < 0:
        return None
    past_close = history[past_index].return_close
    if past_close == 0:
        return None
    return history[index].return_close / past_close - 1.0


def _moving_average_distance(
    history: tuple[DailyPriceObservation, ...],
    *,
    index: int,
    window: int,
) -> float | None:
    start = index - window + 1
    if start < 0:
        return None
    closes = [row.return_close for row in history[start : index + 1]]
    average = sum(closes) / len(closes)
    if average == 0:
        return None
    return history[index].return_close / average - 1.0


def _realized_volatility(
    history: tuple[DailyPriceObservation, ...],
    *,
    index: int,
    lookback: int,
) -> float | None:
    start = index - lookback
    if start < 0:
        return None
    returns = []
    for previous, current in zip(history[start:index], history[start + 1 : index + 1]):
        previous_close = previous.return_close
        current_close = current.return_close
        if previous_close <= 0 or current_close <= 0:
            return None
        returns.append(math.log(current_close / previous_close))
    if len(returns) < 2:
        return None
    average = sum(returns) / len(returns)
    variance = sum((value - average) ** 2 for value in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(252)


def _ge(value: float | None, threshold: float) -> bool:
    return value is not None and value >= threshold


def _lt(value: float | None, threshold: float) -> bool:
    return value is not None and value < threshold


def _snapshot_from_dict(row: dict[str, Any]) -> RegimeSnapshot:
    return RegimeSnapshot(
        source_date=date.fromisoformat(str(row["source_date"])),
        feature_version=str(row["feature_version"]),
        model_version=str(row["model_version"]),
        price_date=date.fromisoformat(str(row["price_date"])) if row["price_date"] else None,
        regime=str(row["regime"]),
        score=int(row["score"]),
        confidence=str(row["confidence"]),
        components=tuple(_component_from_dict(component) for component in row["components"]),
        missing_symbols=tuple(str(symbol) for symbol in row["missing_symbols"]),
        spy_return_20d=_optional_float(row["spy_return_20d"]),
        spy_return_60d=_optional_float(row["spy_return_60d"]),
        spy_ma50_distance=_optional_float(row["spy_ma50_distance"]),
        spy_ma200_distance=_optional_float(row["spy_ma200_distance"]),
        spy_realized_vol_20d=_optional_float(row["spy_realized_vol_20d"]),
        qqq_return_20d=_optional_float(row["qqq_return_20d"]),
        qqq_ma50_distance=_optional_float(row["qqq_ma50_distance"]),
        qqq_ma200_distance=_optional_float(row["qqq_ma200_distance"]),
        rsp_spy_relative_20d=_optional_float(row["rsp_spy_relative_20d"]),
        iwm_spy_relative_20d=_optional_float(row["iwm_spy_relative_20d"]),
        hyg_tlt_relative_20d=_optional_float(row["hyg_tlt_relative_20d"]),
        vix_close=_optional_float(row["vix_close"]),
        vvix_close=_optional_float(row.get("vvix_close")),
    )


def _component_from_dict(row: dict[str, Any]) -> RegimeComponentScore:
    return RegimeComponentScore(
        name=str(row["name"]),
        score=int(row["score"]),
        status=str(row["status"]),
        reason=str(row["reason"]),
    )


def _optional_float(value: object) -> float | None:
    return float(value) if value is not None else None


def _average(values) -> float | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _format_score(value: int) -> str:
    return f"{value:+d}"


def _format_percent(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:+.1f}%"


def _format_index(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}"


def _format_drawdown(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{min(0.0, value) * 100:.1f}%"


def _format_table(rows: list[list[str]]) -> str:
    widths = [max(len(row[index]) for row in rows) for index in range(len(rows[0]))]
    lines = []
    for row_index, row in enumerate(rows):
        lines.append("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))
        if row_index == 0:
            lines.append("  ".join("-" * width for width in widths))
    return "\n".join(lines)
