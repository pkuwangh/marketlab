"""Market regime snapshots from daily price proxies."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, replace
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
REGIME_ACTION_VERSION = "regime_action_v0"
REGIME_ACTION_STATES = ("no_change", "scale_down_protect", "scale_up_redeploy")
REGIME_PRESSURE_VERSION = "regime_pressure_v0"
PRESSURE_LOOKBACK_SAMPLES = 252
MIN_PRESSURE_FEATURE_SAMPLES = 20
MIN_PRESSURE_BUCKET_SAMPLES = 20


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
class RegimePressureFeature:
    """One normalized point-in-time feature used by stretch/washout pressure."""

    source_date: date
    pressure_version: str
    family: str
    name: str
    raw_value: float | None
    percentile: float | None
    normalized_score: float | None
    stretch_score: float | None
    washout_score: float | None
    sample_count: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_date": self.source_date.isoformat(),
            "pressure_version": self.pressure_version,
            "family": self.family,
            "name": self.name,
            "raw_value": self.raw_value,
            "percentile": self.percentile,
            "normalized_score": self.normalized_score,
            "stretch_score": self.stretch_score,
            "washout_score": self.washout_score,
            "sample_count": self.sample_count,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class RegimePressureSnapshot:
    """Normalized stretch/washout pressure for one regime date."""

    source_date: date
    pressure_version: str
    stretch_pressure_score: float
    washout_pressure_score: float
    confidence: str
    features: tuple[RegimePressureFeature, ...]


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
    action_version: str = REGIME_ACTION_VERSION
    action_state: str = "no_change"
    stretch_score: int = 0
    washout_score: int = 0
    action_confidence: str = "low"
    action_reason: str = "Action state not computed"
    pressure_version: str = REGIME_PRESSURE_VERSION
    stretch_pressure_score: float | None = None
    washout_pressure_score: float | None = None
    pressure_confidence: str = "low"
    pressure_features: tuple[RegimePressureFeature, ...] = ()

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
            "action_version": self.action_version,
            "action_state": self.action_state,
            "stretch_score": self.stretch_score,
            "washout_score": self.washout_score,
            "action_confidence": self.action_confidence,
            "action_reason": self.action_reason,
            "pressure_version": self.pressure_version,
            "stretch_pressure_score": self.stretch_pressure_score,
            "washout_pressure_score": self.washout_pressure_score,
            "pressure_confidence": self.pressure_confidence,
            "pressure_features": [feature.to_dict() for feature in self.pressure_features],
        }


@dataclass(frozen=True, slots=True)
class RegimeActionState:
    """Rare-action portfolio posture derived from one regime snapshot."""

    source_date: date
    action_version: str
    state: str
    stretch_score: int
    washout_score: int
    confidence: str
    reason: str
    evidence: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_date": self.source_date.isoformat(),
            "action_version": self.action_version,
            "state": self.state,
            "stretch_score": self.stretch_score,
            "washout_score": self.washout_score,
            "confidence": self.confidence,
            "reason": self.reason,
            "evidence": list(self.evidence),
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
    action: RegimeActionState | None = None
    pressure: RegimePressureSnapshot | None = None
    pressure_table: str = ""


@dataclass(frozen=True, slots=True)
class RegimeBackfillResult:
    """Result of computing market regime snapshots over a date range."""

    start_date: date
    end_date: date
    source_dates: tuple[date, ...]
    snapshot_paths: tuple[Path, ...]
    signal_snapshot_paths: tuple[Path, ...]


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
class RegimeActionForwardOutcome:
    """One forward market outcome from one rare-action state."""

    source_date: date
    price_date: date | None
    action_state: str
    stretch_score: int
    washout_score: int
    action_confidence: str
    horizon_days: int
    spy_return: float | None
    qqq_return: float | None
    spy_max_drawdown: float | None
    qqq_max_drawdown: float | None


@dataclass(frozen=True, slots=True)
class RegimeActionOutcomeSummaryRow:
    """Aggregate forward market outcome row for one rare-action bucket."""

    bucket: str
    horizon_days: int
    action_count: int
    available_count: int
    avg_spy_return: float | None
    avg_qqq_return: float | None
    avg_spy_max_drawdown: float | None
    avg_qqq_max_drawdown: float | None


@dataclass(frozen=True, slots=True)
class RegimeActionFrequencyRow:
    """Frequency count for one rare-action state."""

    action_state: str
    action_count: int
    share: float


@dataclass(frozen=True, slots=True)
class RegimeActionOutcomeResult:
    """Result of replaying rare-action states against forward outcomes."""

    start_date: date
    end_date: date
    actions: tuple[RegimeActionState, ...]
    outcomes: tuple[RegimeActionForwardOutcome, ...]
    frequency_rows: tuple[RegimeActionFrequencyRow, ...]
    summary_rows: tuple[RegimeActionOutcomeSummaryRow, ...]
    frequency_table: str
    table: str


@dataclass(frozen=True, slots=True)
class RegimePressureForwardOutcome:
    """One forward market outcome from one normalized pressure snapshot."""

    source_date: date
    price_date: date | None
    stretch_pressure_score: float
    washout_pressure_score: float
    stretch_pressure_percentile: float | None
    washout_pressure_percentile: float | None
    pressure_sample_count: int
    horizon_days: int
    spy_return: float | None
    qqq_return: float | None
    spy_max_drawdown: float | None
    qqq_max_drawdown: float | None


@dataclass(frozen=True, slots=True)
class RegimePressureOutcomeSummaryRow:
    """Aggregate forward outcome row for one pressure bucket."""

    bucket: str
    horizon_days: int
    pressure_count: int
    available_count: int
    avg_stretch_pressure: float | None
    avg_washout_pressure: float | None
    avg_spy_return: float | None
    avg_qqq_return: float | None
    avg_spy_max_drawdown: float | None
    avg_qqq_max_drawdown: float | None


@dataclass(frozen=True, slots=True)
class RegimePressureOutcomeResult:
    """Result of replaying normalized pressure buckets against forward outcomes."""

    start_date: date
    end_date: date
    pressures: tuple[RegimePressureSnapshot, ...]
    outcomes: tuple[RegimePressureForwardOutcome, ...]
    summary_rows: tuple[RegimePressureOutcomeSummaryRow, ...]
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


@dataclass(frozen=True, slots=True)
class _PressureFeatureSpec:
    family: str
    name: str
    mode: str
    reason: str


@dataclass(frozen=True, slots=True)
class _PressureFeatureSample:
    asof_date: date
    value: float


PRESSURE_FEATURE_SPECS = (
    _PressureFeatureSpec(
        family="trend",
        name="spy_return_20d",
        mode="high_stretch_low_washout",
        reason="SPY short-term momentum relative to its own history",
    ),
    _PressureFeatureSpec(
        family="trend",
        name="spy_return_60d",
        mode="high_stretch_low_washout",
        reason="SPY medium-term momentum relative to its own history",
    ),
    _PressureFeatureSpec(
        family="trend",
        name="qqq_return_20d",
        mode="high_stretch_low_washout",
        reason="QQQ short-term momentum relative to its own history",
    ),
    _PressureFeatureSpec(
        family="trend",
        name="spy_ma50_distance",
        mode="high_stretch_low_washout",
        reason="SPY extension versus 50d trend relative to its own history",
    ),
    _PressureFeatureSpec(
        family="trend",
        name="qqq_ma50_distance",
        mode="high_stretch_low_washout",
        reason="QQQ extension versus 50d trend relative to its own history",
    ),
    _PressureFeatureSpec(
        family="volatility",
        name="spy_realized_vol_20d",
        mode="low_stretch_high_washout",
        reason="SPY realized volatility normalized as complacency versus panic",
    ),
    _PressureFeatureSpec(
        family="volatility",
        name="vix_close",
        mode="low_stretch_high_washout",
        reason="VIX normalized as complacency versus panic",
    ),
    _PressureFeatureSpec(
        family="volatility",
        name="vvix_close",
        mode="low_stretch_high_washout",
        reason="VVIX normalized as complacency versus panic",
    ),
    _PressureFeatureSpec(
        family="breadth",
        name="rsp_spy_relative_20d",
        mode="low_weakness_pressure",
        reason="Equal-weight participation weakness relative to its own history",
    ),
    _PressureFeatureSpec(
        family="breadth",
        name="iwm_spy_relative_20d",
        mode="low_weakness_pressure",
        reason="Small-cap participation weakness relative to its own history",
    ),
    _PressureFeatureSpec(
        family="credit",
        name="hyg_tlt_relative_20d",
        mode="low_weakness_pressure",
        reason="High-yield risk appetite relative to Treasury duration",
    ),
    _PressureFeatureSpec(
        family="credit",
        name="credit_spread",
        mode="low_stretch_high_washout",
        reason="High-yield credit spreads normalized as complacency versus stress",
    ),
    _PressureFeatureSpec(
        family="liquidity",
        name="financial_conditions",
        mode="low_stretch_high_washout",
        reason="Financial conditions normalized as loose versus tight",
    ),
    _PressureFeatureSpec(
        family="rates",
        name="yield_curve",
        mode="low_stretch_only",
        reason="10y-2y curve inversion contributes de-risk pressure",
    ),
)


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
    return _compute_regime_snapshot_from_histories(
        source_date=source_date,
        histories=histories,
        market_series_histories=market_series_histories,
        snapshot_root=snapshot_root,
        signal_snapshot_root=signal_snapshot_root,
        write_snapshot=write_snapshot,
    )


def compute_regime_backfill(
    *,
    start_date: date,
    end_date: date,
    price_root: Path = DEFAULT_PRICE_OBSERVATIONS_ROOT,
    market_series_root: Path = DEFAULT_MARKET_SERIES_OBSERVATIONS_ROOT,
    snapshot_root: Path = DEFAULT_REGIME_SNAPSHOT_ROOT,
    signal_snapshot_root: Path = DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT,
    write_snapshot: bool = True,
) -> RegimeBackfillResult:
    """Compute market regime snapshots for each SPY observation date in a range."""

    if end_date < start_date:
        raise RegimeError("Backfill end date must be on or after start date")

    histories = _load_histories(symbols=DEFAULT_REGIME_PRICE_SYMBOLS, price_root=price_root)
    source_dates = _regime_backfill_source_dates(
        start_date=start_date,
        end_date=end_date,
        histories=histories,
    )
    if not source_dates:
        raise RegimeError(f"No SPY price observations found from {start_date} to {end_date}")

    market_series_histories = _load_market_series_histories(
        series_ids=DEFAULT_FRED_MARKET_SERIES_IDS,
        observations_root=market_series_root,
    )
    feature_history = _pressure_feature_history_from_observations(
        source_date=end_date,
        histories=histories,
        market_series_histories=market_series_histories,
    )
    logger.bind(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        source_date_count=len(source_dates),
        write_snapshot=write_snapshot,
    ).info("Starting market regime backfill")

    snapshot_paths: list[Path] = []
    signal_snapshot_paths: list[Path] = []
    for source_date in source_dates:
        result = _compute_regime_snapshot_from_histories(
            source_date=source_date,
            histories=histories,
            market_series_histories=market_series_histories,
            snapshot_root=snapshot_root,
            signal_snapshot_root=signal_snapshot_root,
            write_snapshot=write_snapshot,
            pressure_feature_history=feature_history,
        )
        if result.snapshot_path is not None:
            snapshot_paths.append(result.snapshot_path)
        if result.signal_snapshot_path is not None:
            signal_snapshot_paths.append(result.signal_snapshot_path)
    logger.bind(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        source_date_count=len(source_dates),
        snapshot_count=len(snapshot_paths),
        signal_snapshot_count=len(signal_snapshot_paths),
    ).success("Completed market regime backfill")
    return RegimeBackfillResult(
        start_date=start_date,
        end_date=end_date,
        source_dates=source_dates,
        snapshot_paths=tuple(snapshot_paths),
        signal_snapshot_paths=tuple(signal_snapshot_paths),
    )


def _compute_regime_snapshot_from_histories(
    *,
    source_date: date,
    histories: dict[str, tuple[DailyPriceObservation, ...]],
    market_series_histories: dict[str, tuple[MarketSeriesObservation, ...]],
    snapshot_root: Path,
    signal_snapshot_root: Path,
    write_snapshot: bool,
    pressure_feature_history: dict[str, tuple[_PressureFeatureSample, ...]] | None = None,
) -> RegimeSnapshotResult:
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
    signals = _market_signals_from_snapshot(
        snapshot,
        features=features,
        market_series=market_series,
    )
    pressure = derive_regime_pressure_snapshot(
        source_date=source_date,
        feature_history=pressure_feature_history
        or _pressure_feature_history_from_observations(
            source_date=source_date,
            histories=histories,
            market_series_histories=market_series_histories,
        ),
    )
    snapshot = _snapshot_with_pressure(snapshot=snapshot, pressure=pressure)
    action = derive_regime_action_state(snapshot=snapshot, signals=signals)
    snapshot = _snapshot_with_action(snapshot=snapshot, action=action)
    snapshot_path = (
        write_regime_snapshot(snapshot, snapshot_root=snapshot_root) if write_snapshot else None
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
        action_state=action.state,
        stretch_score=action.stretch_score,
        washout_score=action.washout_score,
        action_confidence=action.confidence,
        stretch_pressure_score=pressure.stretch_pressure_score,
        washout_pressure_score=pressure.washout_pressure_score,
        pressure_confidence=pressure.confidence,
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
        action=action,
        pressure=pressure,
        pressure_table=format_regime_pressure_features(pressure.features),
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


def derive_regime_action_state(
    *,
    snapshot: RegimeSnapshot,
    signals: tuple[MarketSignal, ...] = (),
) -> RegimeActionState:
    """Derive the rare-action state from one point-in-time regime snapshot."""

    stretch_evidence = _stretch_evidence(snapshot=snapshot, signals=signals)
    washout_evidence = _washout_evidence(snapshot=snapshot, signals=signals)
    stretch_score = len(stretch_evidence)
    washout_score = len(washout_evidence)
    severe_funding_stress = _severe_funding_stress(signals)

    if stretch_score >= 3 and washout_score >= 3:
        state = "no_change"
        evidence = stretch_evidence + washout_evidence
        reason = "Conflicting stretch and washout evidence; maintain current posture"
    elif washout_score >= 3 and not severe_funding_stress:
        state = "scale_up_redeploy"
        evidence = washout_evidence
        reason = "Washout/re-risk threshold crossed"
    elif stretch_score >= 3:
        state = "scale_down_protect"
        evidence = stretch_evidence
        reason = "Stretched/de-risk threshold crossed"
    else:
        state = "no_change"
        evidence = stretch_evidence + washout_evidence
        reason = "No rare-action threshold crossed; maintain current posture"

    if severe_funding_stress and washout_score >= 3:
        state = "no_change"
        evidence = washout_evidence
        reason = "Washout present, but credit and liquidity stress block aggressive re-risk"

    return RegimeActionState(
        source_date=snapshot.source_date,
        action_version=REGIME_ACTION_VERSION,
        state=state,
        stretch_score=stretch_score,
        washout_score=washout_score,
        confidence=_action_confidence(
            state=state,
            stretch_score=stretch_score,
            washout_score=washout_score,
            signals=signals,
        ),
        reason=_action_reason(reason=reason, evidence=evidence),
        evidence=evidence,
    )


def _snapshot_with_action(
    *,
    snapshot: RegimeSnapshot,
    action: RegimeActionState,
) -> RegimeSnapshot:
    return replace(
        snapshot,
        action_version=action.action_version,
        action_state=action.state,
        stretch_score=action.stretch_score,
        washout_score=action.washout_score,
        action_confidence=action.confidence,
        action_reason=action.reason,
    )


def _stretch_evidence(
    *,
    snapshot: RegimeSnapshot,
    signals: tuple[MarketSignal, ...],
) -> tuple[str, ...]:
    evidence: list[str] = []
    if _ge(snapshot.spy_return_20d, 0.05) and _ge(snapshot.spy_return_60d, 0.08):
        evidence.append("strong SPY rally")
    if _ge(snapshot.qqq_return_20d, 0.07) and _ge(snapshot.qqq_ma50_distance, 0.05):
        evidence.append("QQQ momentum is extended")
    if _ge(snapshot.spy_ma50_distance, 0.05) or _ge(snapshot.qqq_ma50_distance, 0.07):
        evidence.append("index is extended above 50d trend")
    if _is_complacent_volatility(snapshot=snapshot, signals=signals):
        evidence.append("volatility pricing is complacent")
    if snapshot.regime == "risk_on" and _component_status(snapshot, "breadth") in {
        "mixed",
        "narrow",
    }:
        evidence.append("risk-on tape has weak participation")
    if snapshot.regime == "risk_on" and _has_negative_credit_or_liquidity(signals):
        evidence.append("risk-on tape has credit/liquidity deterioration")
    return tuple(evidence)


def _washout_evidence(
    *,
    snapshot: RegimeSnapshot,
    signals: tuple[MarketSignal, ...],
) -> tuple[str, ...]:
    evidence: list[str] = []
    if (
        _lt(snapshot.spy_return_20d, -0.08)
        or _lt(snapshot.qqq_return_20d, -0.10)
        or _lt(snapshot.spy_return_60d, -0.12)
    ):
        evidence.append("major index selloff")
    if _lt(snapshot.spy_ma50_distance, -0.05) or _lt(snapshot.qqq_ma50_distance, -0.08):
        evidence.append("index is below intermediate trend")
    if _is_panic_volatility(snapshot=snapshot, signals=signals):
        evidence.append("volatility stress is elevated")
    if _component_status(snapshot, "trend") == "weak":
        evidence.append("trend damage is already visible")
    if _component_status(snapshot, "breadth") == "narrow":
        evidence.append("participation washout is broad")
    if evidence and _funding_backdrop_not_broken(signals):
        evidence.append("credit/liquidity backdrop is not broken")
    return tuple(evidence)


def _is_complacent_volatility(
    *,
    snapshot: RegimeSnapshot,
    signals: tuple[MarketSignal, ...],
) -> bool:
    vvix = _signal_value(signals, family="volatility", name="vol_of_vol")
    return (
        snapshot.vix_close is not None
        and snapshot.vix_close <= 14.0
        and (vvix is None or vvix <= 90.0)
    )


def _is_panic_volatility(
    *,
    snapshot: RegimeSnapshot,
    signals: tuple[MarketSignal, ...],
) -> bool:
    vvix = _signal_value(signals, family="volatility", name="vol_of_vol")
    return (snapshot.vix_close is not None and snapshot.vix_close >= 25.0) or (
        vvix is not None and vvix >= 120.0
    )


def _has_negative_credit_or_liquidity(signals: tuple[MarketSignal, ...]) -> bool:
    return any(
        signal.score < 0
        for signal in signals
        if signal.family in {"credit", "liquidity"} and signal.status != "missing"
    )


def _severe_funding_stress(signals: tuple[MarketSignal, ...]) -> bool:
    return _has_signal_status(
        signals,
        family="credit",
        name="credit_spread",
        status="stressed",
    ) and _has_signal_status(
        signals,
        family="liquidity",
        name="financial_conditions",
        status="tight",
    )


def _funding_backdrop_not_broken(signals: tuple[MarketSignal, ...]) -> bool:
    credit_status = _signal_status(signals, family="credit", name="credit_spread")
    liquidity_status = _signal_status(signals, family="liquidity", name="financial_conditions")
    return credit_status in {"supportive", "mixed"} and liquidity_status in {"loose", "neutral"}


def _action_confidence(
    *,
    state: str,
    stretch_score: int,
    washout_score: int,
    signals: tuple[MarketSignal, ...],
) -> str:
    if state == "no_change":
        confidence = "high" if max(stretch_score, washout_score) <= 1 else "medium"
    else:
        confidence = "high" if max(stretch_score, washout_score) >= 4 else "medium"

    if not signals:
        return _downgrade_confidence(confidence, steps=1)
    if any(signal.status == "missing" for signal in signals):
        return _downgrade_confidence(confidence, steps=1)
    return confidence


def _action_reason(*, reason: str, evidence: tuple[str, ...]) -> str:
    if not evidence:
        return reason
    return f"{reason}: {', '.join(evidence)}"


def _component_status(snapshot: RegimeSnapshot, component_name: str) -> str | None:
    for component in snapshot.components:
        if component.name == component_name:
            return component.status
    return None


def _signal_status(
    signals: tuple[MarketSignal, ...],
    *,
    family: str,
    name: str,
) -> str | None:
    signal = _signal_by_name(signals, family=family, name=name)
    return signal.status if signal is not None else None


def _has_signal_status(
    signals: tuple[MarketSignal, ...],
    *,
    family: str,
    name: str,
    status: str,
) -> bool:
    return _signal_status(signals, family=family, name=name) == status


def _signal_value(
    signals: tuple[MarketSignal, ...],
    *,
    family: str,
    name: str,
) -> float | None:
    signal = _signal_by_name(signals, family=family, name=name)
    if (
        signal is None
        or isinstance(signal.value, bool)
        or not isinstance(signal.value, int | float)
    ):
        return None
    return float(signal.value)


def _signal_by_name(
    signals: tuple[MarketSignal, ...],
    *,
    family: str,
    name: str,
) -> MarketSignal | None:
    for signal in signals:
        if signal.family == family and signal.name == name:
            return signal
    return None


def derive_regime_pressure_snapshot(
    *,
    source_date: date,
    feature_history: dict[str, tuple[_PressureFeatureSample, ...]],
) -> RegimePressureSnapshot:
    """Normalize regime features into stretch and washout pressure scores."""

    features = tuple(
        _pressure_feature(
            source_date=source_date,
            spec=spec,
            samples=feature_history.get(spec.name, ()),
        )
        for spec in PRESSURE_FEATURE_SPECS
    )
    return RegimePressureSnapshot(
        source_date=source_date,
        pressure_version=REGIME_PRESSURE_VERSION,
        stretch_pressure_score=_aggregate_pressure_score(features, field_name="stretch_score"),
        washout_pressure_score=_aggregate_pressure_score(features, field_name="washout_score"),
        confidence=_pressure_confidence(features),
        features=features,
    )


def format_regime_pressure_features(features: tuple[RegimePressureFeature, ...]) -> str:
    """Format normalized pressure features as a compact table."""

    if not features:
        return "No regime pressure features found."

    rows = [
        [
            "family",
            "feature",
            "raw",
            "pctile",
            "stretch",
            "washout",
            "samples",
            "basis",
        ]
    ]
    for feature in features:
        rows.append(
            [
                feature.family,
                feature.name,
                _format_pressure_raw(feature),
                _format_percentile(feature.percentile),
                _format_pressure_score(feature.stretch_score),
                _format_pressure_score(feature.washout_score),
                str(feature.sample_count),
                feature.reason,
            ]
        )
    return _format_table(rows)


def _snapshot_with_pressure(
    *,
    snapshot: RegimeSnapshot,
    pressure: RegimePressureSnapshot,
) -> RegimeSnapshot:
    return replace(
        snapshot,
        pressure_version=pressure.pressure_version,
        stretch_pressure_score=pressure.stretch_pressure_score,
        washout_pressure_score=pressure.washout_pressure_score,
        pressure_confidence=pressure.confidence,
        pressure_features=pressure.features,
    )


def _pressure_feature(
    *,
    source_date: date,
    spec: _PressureFeatureSpec,
    samples: tuple[_PressureFeatureSample, ...],
) -> RegimePressureFeature:
    clean_samples = tuple(
        sample
        for sample in sorted(samples, key=lambda row: row.asof_date)
        if sample.asof_date <= source_date and math.isfinite(sample.value)
    )
    if not clean_samples:
        return RegimePressureFeature(
            source_date=source_date,
            pressure_version=REGIME_PRESSURE_VERSION,
            family=spec.family,
            name=spec.name,
            raw_value=None,
            percentile=None,
            normalized_score=None,
            stretch_score=None,
            washout_score=None,
            sample_count=0,
            reason="No point-in-time value available",
        )

    lookback_samples = clean_samples[-PRESSURE_LOOKBACK_SAMPLES:]
    raw_value = lookback_samples[-1].value
    sample_count = len(lookback_samples)
    if sample_count < MIN_PRESSURE_FEATURE_SAMPLES:
        return RegimePressureFeature(
            source_date=source_date,
            pressure_version=REGIME_PRESSURE_VERSION,
            family=spec.family,
            name=spec.name,
            raw_value=raw_value,
            percentile=None,
            normalized_score=None,
            stretch_score=None,
            washout_score=None,
            sample_count=sample_count,
            reason=f"Insufficient history: {sample_count}/{MIN_PRESSURE_FEATURE_SAMPLES}",
        )

    percentile = _percentile_rank(raw_value, tuple(sample.value for sample in lookback_samples))
    normalized_score = _clamp(percentile * 2.0 - 1.0, -1.0, 1.0)
    stretch_score, washout_score = _pressure_scores_from_normalized_score(
        normalized_score=normalized_score,
        mode=spec.mode,
    )
    return RegimePressureFeature(
        source_date=source_date,
        pressure_version=REGIME_PRESSURE_VERSION,
        family=spec.family,
        name=spec.name,
        raw_value=raw_value,
        percentile=percentile,
        normalized_score=normalized_score,
        stretch_score=stretch_score,
        washout_score=washout_score,
        sample_count=sample_count,
        reason=spec.reason,
    )


def _pressure_scores_from_normalized_score(
    *,
    normalized_score: float,
    mode: str,
) -> tuple[float, float]:
    if mode == "high_stretch_low_washout":
        return max(normalized_score, 0.0), max(-normalized_score, 0.0)
    if mode == "low_stretch_high_washout":
        return max(-normalized_score, 0.0), max(normalized_score, 0.0)
    if mode == "low_weakness_pressure":
        weakness_score = max(-normalized_score, 0.0)
        return weakness_score, weakness_score
    if mode == "low_stretch_only":
        return max(-normalized_score, 0.0), 0.0
    raise RegimeError(f"Unknown pressure feature mode: {mode}")


def _aggregate_pressure_score(
    features: tuple[RegimePressureFeature, ...],
    *,
    field_name: str,
) -> float:
    family_scores: dict[str, list[float]] = {}
    for feature in features:
        score = getattr(feature, field_name)
        if score is not None:
            family_scores.setdefault(feature.family, []).append(score)
    family_averages = [sum(scores) / len(scores) for scores in family_scores.values() if scores]
    if not family_averages:
        return 0.0
    return sum(family_averages) / len(family_averages)


def _pressure_confidence(features: tuple[RegimePressureFeature, ...]) -> str:
    usable_features = tuple(feature for feature in features if feature.normalized_score is not None)
    if not usable_features:
        return "low"

    family_count = len({feature.family for feature in usable_features})
    min_sample_count = min(feature.sample_count for feature in usable_features)
    if len(usable_features) >= 8 and family_count >= 5 and min_sample_count >= 126:
        return "high"
    if len(usable_features) >= 5 and family_count >= 3 and min_sample_count >= 60:
        return "medium"
    return "low"


def _pressure_feature_history_from_observations(
    *,
    source_date: date,
    histories: dict[str, tuple[DailyPriceObservation, ...]],
    market_series_histories: dict[str, tuple[MarketSeriesObservation, ...]],
) -> dict[str, tuple[_PressureFeatureSample, ...]]:
    feature_samples: dict[str, list[_PressureFeatureSample]] = {
        spec.name: [] for spec in PRESSURE_FEATURE_SPECS
    }
    sample_dates = _pressure_sample_dates(source_date=source_date, histories=histories)
    for sample_date in sample_dates:
        features = {
            symbol: _symbol_features(
                symbol=symbol,
                source_date=sample_date,
                history=history,
            )
            for symbol, history in histories.items()
        }
        market_series = {
            series_id: _market_series_asof(history, sample_date)
            for series_id, history in market_series_histories.items()
        }
        values = _pressure_feature_values_from_observations(
            features=features,
            market_series=market_series,
        )
        _append_pressure_feature_samples(
            feature_samples=feature_samples,
            sample_date=sample_date,
            values=values,
        )
    return {name: tuple(samples) for name, samples in feature_samples.items()}


def _pressure_feature_history_from_snapshots(
    *,
    snapshots: tuple[RegimeSnapshot, ...],
    signals_by_date: dict[date, tuple[MarketSignal, ...]],
) -> dict[str, tuple[_PressureFeatureSample, ...]]:
    feature_samples: dict[str, list[_PressureFeatureSample]] = {
        spec.name: [] for spec in PRESSURE_FEATURE_SPECS
    }
    for snapshot in sorted(snapshots, key=lambda row: row.source_date):
        values = _pressure_feature_values_from_snapshot(
            snapshot=snapshot,
            signals=signals_by_date.get(snapshot.source_date, ()),
        )
        _append_pressure_feature_samples(
            feature_samples=feature_samples,
            sample_date=snapshot.source_date,
            values=values,
        )
    return {name: tuple(samples) for name, samples in feature_samples.items()}


def _append_pressure_feature_samples(
    *,
    feature_samples: dict[str, list[_PressureFeatureSample]],
    sample_date: date,
    values: dict[str, float | None],
) -> None:
    for spec in PRESSURE_FEATURE_SPECS:
        value = values.get(spec.name)
        if value is not None and math.isfinite(value):
            feature_samples[spec.name].append(
                _PressureFeatureSample(asof_date=sample_date, value=value)
            )


def _pressure_sample_dates(
    *,
    source_date: date,
    histories: dict[str, tuple[DailyPriceObservation, ...]],
) -> tuple[date, ...]:
    spy_dates = tuple(
        row.observed_date for row in histories.get("SPY", ()) if row.observed_date <= source_date
    )
    if spy_dates:
        return spy_dates
    return tuple(
        sorted(
            {
                row.observed_date
                for history in histories.values()
                for row in history
                if row.observed_date <= source_date
            }
        )
    )


def _regime_backfill_source_dates(
    *,
    start_date: date,
    end_date: date,
    histories: dict[str, tuple[DailyPriceObservation, ...]],
) -> tuple[date, ...]:
    return tuple(
        row.observed_date
        for row in histories.get("SPY", ())
        if start_date <= row.observed_date <= end_date
    )


def _pressure_feature_values_from_observations(
    *,
    features: dict[str, _SymbolFeatures],
    market_series: dict[str, MarketSeriesObservation | None],
) -> dict[str, float | None]:
    spy = features.get("SPY", _empty_symbol_features("SPY"))
    qqq = features.get("QQQ", _empty_symbol_features("QQQ"))
    rsp = features.get("RSP", _empty_symbol_features("RSP"))
    iwm = features.get("IWM", _empty_symbol_features("IWM"))
    hyg = features.get("HYG", _empty_symbol_features("HYG"))
    tlt = features.get("TLT", _empty_symbol_features("TLT"))
    vix = features.get("^VIX", _empty_symbol_features("^VIX"))
    vvix = features.get("^VVIX", _empty_symbol_features("^VVIX"))
    ten_year = market_series.get("DGS10")
    two_year = market_series.get("DGS2")
    return {
        "spy_return_20d": spy.return_20d,
        "spy_return_60d": spy.return_60d,
        "qqq_return_20d": qqq.return_20d,
        "spy_ma50_distance": spy.ma50_distance,
        "qqq_ma50_distance": qqq.ma50_distance,
        "spy_realized_vol_20d": spy.realized_vol_20d,
        "vix_close": vix.close,
        "vvix_close": vvix.close,
        "rsp_spy_relative_20d": _relative_return(rsp, spy),
        "iwm_spy_relative_20d": _relative_return(iwm, spy),
        "hyg_tlt_relative_20d": _relative_return(hyg, tlt),
        "credit_spread": _market_series_value(market_series.get("BAMLH0A0HYM2")),
        "financial_conditions": _market_series_value(market_series.get("NFCI")),
        "yield_curve": (
            ten_year.value - two_year.value
            if ten_year is not None and two_year is not None
            else None
        ),
    }


def _pressure_feature_values_from_snapshot(
    *,
    snapshot: RegimeSnapshot,
    signals: tuple[MarketSignal, ...],
) -> dict[str, float | None]:
    return {
        "spy_return_20d": snapshot.spy_return_20d,
        "spy_return_60d": snapshot.spy_return_60d,
        "qqq_return_20d": snapshot.qqq_return_20d,
        "spy_ma50_distance": snapshot.spy_ma50_distance,
        "qqq_ma50_distance": snapshot.qqq_ma50_distance,
        "spy_realized_vol_20d": snapshot.spy_realized_vol_20d,
        "vix_close": snapshot.vix_close,
        "vvix_close": snapshot.vvix_close,
        "rsp_spy_relative_20d": snapshot.rsp_spy_relative_20d,
        "iwm_spy_relative_20d": snapshot.iwm_spy_relative_20d,
        "hyg_tlt_relative_20d": snapshot.hyg_tlt_relative_20d,
        "credit_spread": _signal_value(signals, family="credit", name="credit_spread"),
        "financial_conditions": _signal_value(
            signals,
            family="liquidity",
            name="financial_conditions",
        ),
        "yield_curve": _signal_value(signals, family="rates", name="yield_curve"),
    }


def _market_series_value(row: MarketSeriesObservation | None) -> float | None:
    return row.value if row is not None else None


def _percentile_rank(value: float, values: tuple[float, ...]) -> float:
    if not values:
        return 0.5
    less_count = sum(1 for sample in values if sample < value)
    equal_count = sum(1 for sample in values if sample == value)
    return (less_count + 0.5 * equal_count) / len(values)


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))


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


def compute_regime_action_outcomes(
    *,
    start_date: date,
    end_date: date,
    snapshot_root: Path = DEFAULT_REGIME_SNAPSHOT_ROOT,
    signal_snapshot_root: Path = DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT,
    price_root: Path = DEFAULT_PRICE_OBSERVATIONS_ROOT,
    horizons: tuple[int, ...] = DEFAULT_REGIME_OUTCOME_HORIZONS,
) -> RegimeActionOutcomeResult:
    """Replay rare-action states against forward SPY/QQQ outcomes."""

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
    snapshot_actions = tuple(
        (
            snapshot,
            derive_regime_action_state(
                snapshot=snapshot,
                signals=_load_action_signals(
                    source_date=snapshot.source_date,
                    signal_snapshot_root=signal_snapshot_root,
                ),
            ),
        )
        for snapshot in snapshots
    )
    actions = tuple(action for _snapshot, action in snapshot_actions)
    outcomes = tuple(
        outcome
        for snapshot, action in snapshot_actions
        for outcome in _regime_action_outcomes(
            snapshot=snapshot,
            action=action,
            histories=histories,
            horizons=horizons,
        )
    )
    frequency_rows = summarize_regime_action_frequency(actions)
    summary_rows = summarize_regime_action_outcomes(outcomes)
    frequency_table = format_regime_action_frequency(frequency_rows)
    table = format_regime_action_outcome_summary(summary_rows)
    logger.bind(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        action_count=len(actions),
        outcome_count=len(outcomes),
    ).success("Computed market regime action outcomes")
    return RegimeActionOutcomeResult(
        start_date=start_date,
        end_date=end_date,
        actions=actions,
        outcomes=outcomes,
        frequency_rows=frequency_rows,
        summary_rows=summary_rows,
        frequency_table=frequency_table,
        table=table,
    )


def compute_regime_pressure_outcomes(
    *,
    start_date: date,
    end_date: date,
    snapshot_root: Path = DEFAULT_REGIME_SNAPSHOT_ROOT,
    signal_snapshot_root: Path = DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT,
    price_root: Path = DEFAULT_PRICE_OBSERVATIONS_ROOT,
    horizons: tuple[int, ...] = DEFAULT_REGIME_OUTCOME_HORIZONS,
) -> RegimePressureOutcomeResult:
    """Replay normalized pressure buckets against forward SPY/QQQ outcomes."""

    if end_date < start_date:
        raise RegimeError("End date must be on or after start date")

    snapshots = _load_regime_snapshots_through(
        end_date=end_date,
        snapshot_root=snapshot_root,
    )
    target_snapshots = tuple(
        snapshot for snapshot in snapshots if start_date <= snapshot.source_date <= end_date
    )
    if not target_snapshots:
        raise RegimeError(f"No market regime snapshots found from {start_date} to {end_date}")

    signals_by_date = _load_market_signals_by_source_date_through(
        end_date=end_date,
        signal_snapshot_root=signal_snapshot_root,
    )
    feature_history = _pressure_feature_history_from_snapshots(
        snapshots=snapshots,
        signals_by_date=signals_by_date,
    )
    pressure_pairs = tuple(
        (
            snapshot,
            derive_regime_pressure_snapshot(
                source_date=snapshot.source_date,
                feature_history=feature_history,
            ),
        )
        for snapshot in snapshots
    )
    pressures_by_date = {pressure.source_date: pressure for _snapshot, pressure in pressure_pairs}
    pressure_percentiles = _pressure_percentiles_by_date(
        tuple(pressure for _snapshot, pressure in pressure_pairs)
    )
    histories = _load_histories(symbols=("SPY", "QQQ"), price_root=price_root)
    outcomes = tuple(
        outcome
        for snapshot in target_snapshots
        for outcome in _regime_pressure_outcomes(
            snapshot=snapshot,
            pressure=pressures_by_date[snapshot.source_date],
            pressure_percentile=pressure_percentiles[snapshot.source_date],
            histories=histories,
            horizons=horizons,
        )
    )
    target_pressures = tuple(
        pressures_by_date[snapshot.source_date] for snapshot in target_snapshots
    )
    summary_rows = summarize_regime_pressure_outcomes(outcomes)
    table = format_regime_pressure_outcome_summary(summary_rows)
    logger.bind(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        pressure_count=len(target_pressures),
        outcome_count=len(outcomes),
    ).success("Computed market regime pressure outcomes")
    return RegimePressureOutcomeResult(
        start_date=start_date,
        end_date=end_date,
        pressures=target_pressures,
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


def summarize_regime_action_frequency(
    actions: tuple[RegimeActionState, ...],
) -> tuple[RegimeActionFrequencyRow, ...]:
    """Summarize how often each rare-action state occurs."""

    total = len(actions)
    counts = {state: 0 for state in REGIME_ACTION_STATES}
    for action in actions:
        counts[action.state] = counts.get(action.state, 0) + 1
    return tuple(
        RegimeActionFrequencyRow(
            action_state=state,
            action_count=counts[state],
            share=counts[state] / total if total else 0.0,
        )
        for state in REGIME_ACTION_STATES
    )


def summarize_regime_action_outcomes(
    outcomes: tuple[RegimeActionForwardOutcome, ...],
) -> tuple[RegimeActionOutcomeSummaryRow, ...]:
    """Summarize forward market outcomes by rare-action state."""

    buckets: dict[str, list[RegimeActionForwardOutcome]] = {"all": list(outcomes)}
    for outcome in outcomes:
        buckets.setdefault(f"action:{outcome.action_state}", []).append(outcome)

    rows: list[RegimeActionOutcomeSummaryRow] = []
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
                RegimeActionOutcomeSummaryRow(
                    bucket=bucket,
                    horizon_days=horizon,
                    action_count=len(horizon_outcomes),
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


def summarize_regime_pressure_outcomes(
    outcomes: tuple[RegimePressureForwardOutcome, ...],
) -> tuple[RegimePressureOutcomeSummaryRow, ...]:
    """Summarize forward market outcomes by normalized pressure bucket."""

    buckets: dict[str, list[RegimePressureForwardOutcome]] = {"all": list(outcomes)}
    for outcome in outcomes:
        for bucket in _regime_pressure_buckets(outcome):
            buckets.setdefault(bucket, []).append(outcome)

    rows: list[RegimePressureOutcomeSummaryRow] = []
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
                RegimePressureOutcomeSummaryRow(
                    bucket=bucket,
                    horizon_days=horizon,
                    pressure_count=len(horizon_outcomes),
                    available_count=len(available),
                    avg_stretch_pressure=_average(
                        outcome.stretch_pressure_score for outcome in horizon_outcomes
                    ),
                    avg_washout_pressure=_average(
                        outcome.washout_pressure_score for outcome in horizon_outcomes
                    ),
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


def format_regime_action_frequency(rows: tuple[RegimeActionFrequencyRow, ...]) -> str:
    """Format rare-action frequency as a compact table."""

    if not rows:
        return "No regime action rows found."

    table = [["action_state", "count", "share"]]
    for row in rows:
        table.append(
            [
                row.action_state,
                str(row.action_count),
                _format_share(row.share),
            ]
        )
    return _format_table(table)


def format_regime_action_outcome_summary(
    rows: tuple[RegimeActionOutcomeSummaryRow, ...],
) -> str:
    """Format rare-action forward outcome summaries as a compact table."""

    available_rows = tuple(row for row in rows if row.available_count > 0)
    if not available_rows:
        return "No available regime action outcome rows found."

    table = [
        [
            "bucket",
            "horizon",
            "actions",
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
                str(row.action_count),
                str(row.available_count),
                _format_percent(row.avg_spy_return),
                _format_percent(row.avg_qqq_return),
                _format_drawdown(row.avg_spy_max_drawdown),
                _format_drawdown(row.avg_qqq_max_drawdown),
            ]
        )
    return _format_table(table)


def format_regime_pressure_outcome_summary(
    rows: tuple[RegimePressureOutcomeSummaryRow, ...],
) -> str:
    """Format normalized pressure forward outcome summaries as a compact table."""

    available_rows = tuple(row for row in rows if row.available_count > 0)
    if not available_rows:
        return "No available regime pressure outcome rows found."

    table = [
        [
            "bucket",
            "horizon",
            "pressures",
            "available",
            "stretch",
            "washout",
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
                str(row.pressure_count),
                str(row.available_count),
                _format_pressure_score(row.avg_stretch_pressure),
                _format_pressure_score(row.avg_washout_pressure),
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


def _load_regime_snapshots_through(
    *,
    end_date: date,
    snapshot_root: Path,
) -> tuple[RegimeSnapshot, ...]:
    snapshots: list[RegimeSnapshot] = []
    for path in sorted(snapshot_root.glob("*.json")):
        try:
            source_date = date.fromisoformat(path.stem)
        except ValueError:
            continue
        if source_date <= end_date:
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


def _load_market_signals_by_source_date_through(
    *,
    end_date: date,
    signal_snapshot_root: Path,
) -> dict[date, tuple[MarketSignal, ...]]:
    signals_by_date: dict[date, tuple[MarketSignal, ...]] = {}
    for path in sorted(signal_snapshot_root.glob("*.jsonl")):
        try:
            source_date = date.fromisoformat(path.stem)
        except ValueError:
            continue
        if source_date <= end_date:
            signals_by_date[source_date] = load_market_signal_snapshot(
                source_date=source_date,
                snapshot_root=signal_snapshot_root,
            )
    return signals_by_date


def _load_action_signals(
    *,
    source_date: date,
    signal_snapshot_root: Path,
) -> tuple[MarketSignal, ...]:
    try:
        return load_market_signal_snapshot(
            source_date=source_date,
            snapshot_root=signal_snapshot_root,
        )
    except MarketSignalError as exc:
        raise RegimeError(str(exc)) from exc


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


def _regime_action_outcomes(
    *,
    snapshot: RegimeSnapshot,
    action: RegimeActionState,
    histories: dict[str, tuple[DailyPriceObservation, ...]],
    horizons: tuple[int, ...],
) -> tuple[RegimeActionForwardOutcome, ...]:
    spy_history = histories.get("SPY", ())
    qqq_history = histories.get("QQQ", ())
    spy_index = _exact_date_index(spy_history, snapshot.price_date)
    qqq_index = _exact_date_index(qqq_history, snapshot.price_date)
    return tuple(
        RegimeActionForwardOutcome(
            source_date=snapshot.source_date,
            price_date=snapshot.price_date,
            action_state=action.state,
            stretch_score=action.stretch_score,
            washout_score=action.washout_score,
            action_confidence=action.confidence,
            horizon_days=horizon,
            spy_return=_forward_return(spy_history, index=spy_index, horizon=horizon),
            qqq_return=_forward_return(qqq_history, index=qqq_index, horizon=horizon),
            spy_max_drawdown=_forward_max_drawdown(spy_history, index=spy_index, horizon=horizon),
            qqq_max_drawdown=_forward_max_drawdown(qqq_history, index=qqq_index, horizon=horizon),
        )
        for horizon in horizons
    )


def _regime_pressure_outcomes(
    *,
    snapshot: RegimeSnapshot,
    pressure: RegimePressureSnapshot,
    pressure_percentile: tuple[float | None, float | None, int],
    histories: dict[str, tuple[DailyPriceObservation, ...]],
    horizons: tuple[int, ...],
) -> tuple[RegimePressureForwardOutcome, ...]:
    spy_history = histories.get("SPY", ())
    qqq_history = histories.get("QQQ", ())
    spy_index = _exact_date_index(spy_history, snapshot.price_date)
    qqq_index = _exact_date_index(qqq_history, snapshot.price_date)
    stretch_percentile, washout_percentile, pressure_sample_count = pressure_percentile
    return tuple(
        RegimePressureForwardOutcome(
            source_date=snapshot.source_date,
            price_date=snapshot.price_date,
            stretch_pressure_score=pressure.stretch_pressure_score,
            washout_pressure_score=pressure.washout_pressure_score,
            stretch_pressure_percentile=stretch_percentile,
            washout_pressure_percentile=washout_percentile,
            pressure_sample_count=pressure_sample_count,
            horizon_days=horizon,
            spy_return=_forward_return(spy_history, index=spy_index, horizon=horizon),
            qqq_return=_forward_return(qqq_history, index=qqq_index, horizon=horizon),
            spy_max_drawdown=_forward_max_drawdown(spy_history, index=spy_index, horizon=horizon),
            qqq_max_drawdown=_forward_max_drawdown(qqq_history, index=qqq_index, horizon=horizon),
        )
        for horizon in horizons
    )


def _pressure_percentiles_by_date(
    pressures: tuple[RegimePressureSnapshot, ...],
) -> dict[date, tuple[float | None, float | None, int]]:
    percentiles: dict[date, tuple[float | None, float | None, int]] = {}
    stretch_values: list[float] = []
    washout_values: list[float] = []
    for pressure in sorted(pressures, key=lambda row: row.source_date):
        stretch_values.append(pressure.stretch_pressure_score)
        washout_values.append(pressure.washout_pressure_score)
        sample_count = min(len(stretch_values), len(washout_values))
        if sample_count < MIN_PRESSURE_BUCKET_SAMPLES:
            percentiles[pressure.source_date] = (None, None, sample_count)
            continue
        percentiles[pressure.source_date] = (
            _percentile_rank(pressure.stretch_pressure_score, tuple(stretch_values)),
            _percentile_rank(pressure.washout_pressure_score, tuple(washout_values)),
            sample_count,
        )
    return percentiles


def _regime_pressure_buckets(outcome: RegimePressureForwardOutcome) -> tuple[str, ...]:
    if outcome.stretch_pressure_percentile is None or outcome.washout_pressure_percentile is None:
        return ("pressure:insufficient_history",)

    buckets: list[str] = []
    if outcome.stretch_pressure_percentile >= 0.95:
        buckets.append("stretch:top_5")
    if outcome.stretch_pressure_percentile >= 0.90:
        buckets.append("stretch:top_10")
    if outcome.washout_pressure_percentile >= 0.95:
        buckets.append("washout:top_5")
    if outcome.washout_pressure_percentile >= 0.90:
        buckets.append("washout:top_10")
    if not buckets:
        buckets.append("pressure:below_top_10")
    return tuple(buckets)


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
        action_version=str(row.get("action_version", REGIME_ACTION_VERSION)),
        action_state=str(row.get("action_state", "no_change")),
        stretch_score=int(row.get("stretch_score", 0)),
        washout_score=int(row.get("washout_score", 0)),
        action_confidence=str(row.get("action_confidence", "low")),
        action_reason=str(row.get("action_reason", "Action state not computed")),
        pressure_version=str(row.get("pressure_version", REGIME_PRESSURE_VERSION)),
        stretch_pressure_score=_optional_float(row.get("stretch_pressure_score")),
        washout_pressure_score=_optional_float(row.get("washout_pressure_score")),
        pressure_confidence=str(row.get("pressure_confidence", "low")),
        pressure_features=tuple(
            _pressure_feature_from_dict(feature) for feature in row.get("pressure_features", ())
        ),
    )


def _component_from_dict(row: dict[str, Any]) -> RegimeComponentScore:
    return RegimeComponentScore(
        name=str(row["name"]),
        score=int(row["score"]),
        status=str(row["status"]),
        reason=str(row["reason"]),
    )


def _pressure_feature_from_dict(row: dict[str, Any]) -> RegimePressureFeature:
    return RegimePressureFeature(
        source_date=date.fromisoformat(str(row["source_date"])),
        pressure_version=str(row.get("pressure_version", REGIME_PRESSURE_VERSION)),
        family=str(row["family"]),
        name=str(row["name"]),
        raw_value=_optional_float(row.get("raw_value")),
        percentile=_optional_float(row.get("percentile")),
        normalized_score=_optional_float(row.get("normalized_score")),
        stretch_score=_optional_float(row.get("stretch_score")),
        washout_score=_optional_float(row.get("washout_score")),
        sample_count=int(row.get("sample_count", 0)),
        reason=str(row.get("reason", "")),
    )


def _optional_float(value: object) -> float | None:
    return float(value) if value is not None else None


def _average(values) -> float | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _format_pressure_raw(feature: RegimePressureFeature) -> str:
    value = feature.raw_value
    if value is None:
        return "-"
    if (
        feature.name.startswith(("spy_return", "qqq_return"))
        or feature.name.endswith("_distance")
        or feature.name.endswith("_relative_20d")
        or feature.name == "spy_realized_vol_20d"
    ):
        return _format_percent(value)
    if feature.name == "credit_spread":
        return f"{value:.2f}%"
    if feature.name == "yield_curve":
        return f"{value:+.2f}pp"
    return _format_index(value)


def _format_percentile(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.1f}%"


def _format_pressure_score(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}"


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


def _format_share(value: float) -> str:
    return f"{value * 100:.1f}%"


def _format_table(rows: list[list[str]]) -> str:
    widths = [max(len(row[index]) for row in rows) for index in range(len(rows[0]))]
    lines = []
    for row_index, row in enumerate(rows):
        lines.append("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))
        if row_index == 0:
            lines.append("  ".join("-" * width for width in widths))
    return "\n".join(lines)
