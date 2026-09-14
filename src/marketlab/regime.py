"""Market regime snapshots from daily price proxies."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
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
    MARKET_SIGNAL_SNAPSHOT_FILENAME,
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
    fetch_and_write_cboe_index_daily_prices,
    fetch_and_write_eoddata_index_daily_prices,
    fetch_and_write_yahoo_daily_prices,
    is_cboe_index_symbol,
    load_price_history,
)
from marketlab.snapshots.models import (
    SignalTime,
    current_code_revision,
    default_snapshot_version,
    require_eod_signal_time,
    resolve_snapshot_path,
    signal_time_value,
    snapshot_source_dates,
    utc_timestamp,
    versioned_snapshot_path,
    write_snapshot_payload,
)
from marketlab.versions import REGIME_SNAPSHOT_VERSION, REGIME_VERSION, versioned_label

DEFAULT_REGIME_SNAPSHOT_ROOT = Path("data/snapshots/regime/market")
DEFAULT_REGIME_YAHOO_PRICE_SYMBOLS = (
    "SPY",
    "QQQ",
    "IWM",
    "RSP",
    "HYG",
    "TLT",
)
DEFAULT_REGIME_CBOE_PRICE_SYMBOLS = (
    "^VIX",
    "^VIX9D",
    "^VIX3M",
    "^VVIX",
)
DEFAULT_REGIME_BREADTH_SYMBOLS = ("$S5FI", "$S5TH")
DEFAULT_REGIME_PRICE_SYMBOLS = (
    DEFAULT_REGIME_YAHOO_PRICE_SYMBOLS
    + DEFAULT_REGIME_CBOE_PRICE_SYMBOLS
    + DEFAULT_REGIME_BREADTH_SYMBOLS
)
DEFAULT_REGIME_OUTCOME_HORIZONS = (1, 5, 20, 40, 65, 126)
DEFAULT_CORRECTION_EPISODE_LOOKBACK_DAYS = 20
CORRECTION_EPISODE_FIRST_DAMAGE_DRAWDOWN = 0.03
CORRECTION_EPISODE_MIN_DRAWDOWN = 0.05
CORRECTION_EPISODE_SEVERE_DRAWDOWN = 0.08
EXTENSION_ARMED_SETUP_THRESHOLD = 0.60
ACTION_EXTENSION_ARMED_MAX_AGE_DAYS = 40
REGIME_FEATURE_VERSION = versioned_label("market_regime_features", REGIME_VERSION)
REGIME_MODEL_VERSION = versioned_label("market_regime_score", REGIME_VERSION)
REGIME_ACTION_VERSION = versioned_label("regime_action", REGIME_VERSION)
REGIME_ACTION_STATES = ("no_change", "scale_down_protect", "scale_up_redeploy")
REGIME_PRESSURE_VERSION = versioned_label("regime_pressure", REGIME_VERSION)
REGIME_SNAPSHOT_FILENAME = "regime.json"
REGIME_KEY_SIGNALS_CAPTION = "headline regime, setup/evidence, and final action"
REGIME_MARKET_SIGNALS_CAPTION = (
    "score cells marked (regime) feed the headline regime score; "
    "other rows are supporting evidence"
)
PRESSURE_LOOKBACK_SAMPLES = 252
MIN_PRESSURE_FEATURE_SAMPLES = 20
MIN_PRESSURE_BUCKET_SAMPLES = 20
ACTION_STRENGTH_THRESHOLD = 0.55
ACTION_STRENGTH_MARGIN = 0.15
ACTION_EXTENSION_SETUP_THRESHOLD = 0.60
ACTION_REGIME_BREAK_CONTEXT_THRESHOLD = 0.70
ACTION_CONFIRMATION_THRESHOLD = 0.35
ACTION_EXTENSION_CONFIRMATION_MIN_FAMILIES = 2
ACTION_REGIME_BREAK_NON_VOL_MIN_FAMILIES = 2
PROTECTED_POSTURE_MAX_AGE_DAYS = 65
REDEPLOY_POSTURE_MAX_AGE_DAYS = 20
POSTURE_CLEAR_THRESHOLD = 0.35


class RegimeError(ValueError):
    """Raised when a market regime workflow cannot run."""


def _require_eod_signal_time(
    signal_time: SignalTime | str,
    *,
    workflow: str,
) -> str:
    try:
        return require_eod_signal_time(signal_time, workflow=workflow)
    except ValueError as exc:
        raise RegimeError(str(exc)) from exc


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
class RegimePressureModule:
    """One modular pressure read composed from normalized pressure features."""

    source_date: date
    pressure_version: str
    family: str
    name: str
    stretch_score: float | None
    washout_score: float | None
    feature_count: int
    feature_names: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_date": self.source_date.isoformat(),
            "pressure_version": self.pressure_version,
            "family": self.family,
            "name": self.name,
            "stretch_score": self.stretch_score,
            "washout_score": self.washout_score,
            "feature_count": self.feature_count,
            "feature_names": list(self.feature_names),
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
    modules: tuple[RegimePressureModule, ...] = ()
    extension_setup_score: float = 0.0
    fragility_context_score: float = 0.0
    washout_setup_score: float = 0.0


@dataclass(frozen=True, slots=True)
class RegimeActionFeature:
    """One modular turn feature used to gate protect/redeploy action."""

    family: str
    name: str
    deterioration_score: float
    stabilization_score: float
    reason: str
    evidence_kind: str = "turn"

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "name": self.name,
            "deterioration_score": self.deterioration_score,
            "stabilization_score": self.stabilization_score,
            "reason": self.reason,
            "evidence_kind": self.evidence_kind,
        }


@dataclass(frozen=True, slots=True)
class RegimeActionModule:
    """One bounded action-evidence contribution composed from leaf features."""

    family: str
    name: str
    deterioration_score: float
    stabilization_score: float
    feature_count: int
    feature_names: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "family": self.family,
            "name": self.name,
            "deterioration_score": self.deterioration_score,
            "stabilization_score": self.stabilization_score,
            "feature_count": self.feature_count,
            "feature_names": list(self.feature_names),
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
    vix9d_vix_ratio: float | None = None
    vix_vix3m_ratio: float | None = None
    sp500_above_50d: float | None = None
    sp500_above_200d: float | None = None
    action_version: str = REGIME_ACTION_VERSION
    action_state: str = "no_change"
    stretch_score: int = 0
    washout_score: int = 0
    deterioration_score: float = 0.0
    stabilization_score: float = 0.0
    protect_strength: float = 0.0
    redeploy_strength: float = 0.0
    action_score: float = 0.0
    action_confidence: str = "low"
    action_reason: str = "Action state not computed"
    action_path: str | None = None
    event_volatility_context: str = "none"
    action_features: tuple[RegimeActionFeature, ...] = ()
    action_modules: tuple[RegimeActionModule, ...] = ()
    pressure_version: str = REGIME_PRESSURE_VERSION
    stretch_pressure_score: float | None = None
    washout_pressure_score: float | None = None
    extension_setup_score: float | None = None
    fragility_context_score: float | None = None
    washout_setup_score: float | None = None
    extension_memory_status: str = "not_computed"
    extension_armed: bool = False
    extension_armed_since: date | None = None
    extension_armed_age: int | None = None
    extension_armed_decay: float | None = None
    extension_armed_source_strength: float | None = None
    extension_memory_score: float = 0.0
    extension_memory_snapshot_count: int = 0
    pressure_confidence: str = "low"
    pressure_features: tuple[RegimePressureFeature, ...] = ()
    pressure_modules: tuple[RegimePressureModule, ...] = ()
    signal_time: str = SignalTime.EOD.value
    snapshot_version: str | None = None
    market_signal_snapshot_version: str | None = None
    created_at: str | None = field(default=None, compare=False)
    code_revision: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        signal_time = signal_time_value(self.signal_time)
        object.__setattr__(self, "signal_time", signal_time)
        if not self.snapshot_version:
            object.__setattr__(
                self,
                "snapshot_version",
                default_snapshot_version(
                    self.source_date,
                    signal_time=signal_time,
                    default_version=REGIME_SNAPSHOT_VERSION,
                ),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": "marketlab",
            "snapshot_type": "market-regime",
            "source_date": self.source_date.isoformat(),
            "signal_date": self.source_date.isoformat(),
            "signal_time": self.signal_time,
            "snapshot_version": self.snapshot_version,
            "market_signal_snapshot_version": self.market_signal_snapshot_version,
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
            "vix9d_vix_ratio": self.vix9d_vix_ratio,
            "vix_vix3m_ratio": self.vix_vix3m_ratio,
            "sp500_above_50d": self.sp500_above_50d,
            "sp500_above_200d": self.sp500_above_200d,
            "action_version": self.action_version,
            "action_state": self.action_state,
            "stretch_score": self.stretch_score,
            "washout_score": self.washout_score,
            "deterioration_score": self.deterioration_score,
            "stabilization_score": self.stabilization_score,
            "protect_strength": self.protect_strength,
            "redeploy_strength": self.redeploy_strength,
            "action_score": self.action_score,
            "action_confidence": self.action_confidence,
            "action_reason": self.action_reason,
            "action_path": self.action_path,
            "event_volatility_context": self.event_volatility_context,
            "action_features": [feature.to_dict() for feature in self.action_features],
            "action_modules": [module.to_dict() for module in self.action_modules],
            "pressure_version": self.pressure_version,
            "stretch_pressure_score": self.stretch_pressure_score,
            "washout_pressure_score": self.washout_pressure_score,
            "extension_setup_score": self.extension_setup_score,
            "fragility_context_score": self.fragility_context_score,
            "washout_setup_score": self.washout_setup_score,
            "extension_memory_status": self.extension_memory_status,
            "extension_armed": self.extension_armed,
            "extension_armed_since": (
                self.extension_armed_since.isoformat()
                if self.extension_armed_since
                else None
            ),
            "extension_armed_age": self.extension_armed_age,
            "extension_armed_decay": self.extension_armed_decay,
            "extension_armed_source_strength": self.extension_armed_source_strength,
            "extension_memory_score": self.extension_memory_score,
            "extension_memory_snapshot_count": self.extension_memory_snapshot_count,
            "pressure_confidence": self.pressure_confidence,
            "pressure_features": [feature.to_dict() for feature in self.pressure_features],
            "pressure_modules": [module.to_dict() for module in self.pressure_modules],
            "created_at": self.created_at,
            "code_revision": self.code_revision,
        }


@dataclass(frozen=True, slots=True)
class RegimeExtensionMemory:
    """Saved-snapshot memory for extension-unwind protect setups."""

    source_date: date
    status: str
    armed: bool
    armed_since: date | None
    armed_age: int | None
    armed_decay: float | None
    armed_source_strength: float | None
    effective_score: float
    snapshot_count: int


@dataclass(frozen=True, slots=True)
class RegimeActionState:
    """Rare-action portfolio posture derived from setup and turn evidence."""

    source_date: date
    action_version: str
    state: str
    stretch_score: int
    washout_score: int
    confidence: str
    reason: str
    evidence: tuple[str, ...]
    deterioration_score: float = 0.0
    stabilization_score: float = 0.0
    protect_strength: float = 0.0
    redeploy_strength: float = 0.0
    action_score: float = 0.0
    action_path: str | None = None
    event_volatility_context: str = "none"
    extension_memory_status: str = "not_computed"
    extension_armed: bool = False
    extension_armed_since: date | None = None
    extension_armed_age: int | None = None
    extension_armed_decay: float | None = None
    extension_armed_source_strength: float | None = None
    extension_memory_score: float = 0.0
    extension_memory_snapshot_count: int = 0
    action_features: tuple[RegimeActionFeature, ...] = ()
    action_modules: tuple[RegimeActionModule, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_date": self.source_date.isoformat(),
            "action_version": self.action_version,
            "state": self.state,
            "stretch_score": self.stretch_score,
            "washout_score": self.washout_score,
            "deterioration_score": self.deterioration_score,
            "stabilization_score": self.stabilization_score,
            "protect_strength": self.protect_strength,
            "redeploy_strength": self.redeploy_strength,
            "action_score": self.action_score,
            "action_path": self.action_path,
            "event_volatility_context": self.event_volatility_context,
            "extension_memory_status": self.extension_memory_status,
            "extension_armed": self.extension_armed,
            "extension_armed_since": (
                self.extension_armed_since.isoformat()
                if self.extension_armed_since
                else None
            ),
            "extension_armed_age": self.extension_armed_age,
            "extension_armed_decay": self.extension_armed_decay,
            "extension_armed_source_strength": self.extension_armed_source_strength,
            "extension_memory_score": self.extension_memory_score,
            "extension_memory_snapshot_count": self.extension_memory_snapshot_count,
            "confidence": self.confidence,
            "reason": self.reason,
            "evidence": list(self.evidence),
            "action_features": [feature.to_dict() for feature in self.action_features],
            "action_modules": [module.to_dict() for module in self.action_modules],
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
    action_table: str = ""


@dataclass(frozen=True, slots=True)
class RegimeRecentReportResult:
    """Recent saved market-regime snapshots formatted for transition review."""

    source_date: date
    lookback_days: int
    snapshots: tuple[RegimeSnapshot, ...]
    report: str


@dataclass(frozen=True, slots=True)
class RegimeBackfillResult:
    """Result of computing market regime snapshots over a date range."""

    start_date: date
    end_date: date
    source_dates: tuple[date, ...]
    snapshot_paths: tuple[Path, ...]
    signal_snapshot_paths: tuple[Path, ...]
    skipped_snapshot_paths: tuple[Path, ...] = ()


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
class RegimePostureState:
    """Derived held posture reconstructed from regime action events."""

    source_date: date
    price_date: date | None
    posture_state: str
    protected_since: date | None
    protect_reason: str | None
    protect_path: str | None
    redeploy_since: date | None
    posture_age: int | None
    max_drawdown_since_posture: float | None
    reset_reason: str | None


@dataclass(frozen=True, slots=True)
class RegimePostureForwardOutcome:
    """One forward market outcome from one derived posture state."""

    source_date: date
    price_date: date | None
    posture_state: str
    protect_path: str | None
    posture_age: int | None
    max_drawdown_since_posture: float | None
    horizon_days: int
    spy_return: float | None
    qqq_return: float | None
    spy_max_drawdown: float | None
    qqq_max_drawdown: float | None


@dataclass(frozen=True, slots=True)
class RegimePostureOutcomeSummaryRow:
    """Aggregate forward outcome row for one derived posture bucket."""

    bucket: str
    horizon_days: int
    posture_count: int
    available_count: int
    avg_posture_age: float | None
    avg_posture_drawdown: float | None
    avg_spy_return: float | None
    avg_qqq_return: float | None
    avg_spy_max_drawdown: float | None
    avg_qqq_max_drawdown: float | None


@dataclass(frozen=True, slots=True)
class RegimePostureFrequencyRow:
    """Frequency count for one derived posture state."""

    posture_state: str
    posture_count: int
    share: float


@dataclass(frozen=True, slots=True)
class RegimePostureOutcomeResult:
    """Result of replaying derived held posture against forward outcomes."""

    start_date: date
    end_date: date
    postures: tuple[RegimePostureState, ...]
    outcomes: tuple[RegimePostureForwardOutcome, ...]
    frequency_rows: tuple[RegimePostureFrequencyRow, ...]
    summary_rows: tuple[RegimePostureOutcomeSummaryRow, ...]
    frequency_table: str
    table: str


@dataclass(frozen=True, slots=True)
class RegimeRedeployForwardOutcome:
    """One forward market outcome from one redeploy setup/confirmation bucket."""

    source_date: date
    price_date: date | None
    bucket: str
    action_state: str
    washout_setup_score: float | None
    stabilization_score: float
    redeploy_strength: float
    horizon_days: int
    spy_return: float | None
    qqq_return: float | None
    spy_max_drawdown: float | None
    qqq_max_drawdown: float | None


@dataclass(frozen=True, slots=True)
class RegimeRedeployOutcomeSummaryRow:
    """Aggregate forward outcome row for one redeploy validation bucket."""

    bucket: str
    horizon_days: int
    redeploy_count: int
    available_count: int
    avg_washout_setup: float | None
    avg_stabilization: float | None
    avg_redeploy_strength: float | None
    avg_spy_return: float | None
    avg_qqq_return: float | None
    avg_spy_max_drawdown: float | None
    avg_qqq_max_drawdown: float | None


@dataclass(frozen=True, slots=True)
class RegimeRedeployOutcomeResult:
    """Result of validating redeploy setup and stabilization buckets."""

    start_date: date
    end_date: date
    outcomes: tuple[RegimeRedeployForwardOutcome, ...]
    summary_rows: tuple[RegimeRedeployOutcomeSummaryRow, ...]
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
class RegimeCorrectionEpisode:
    """One SPY correction episode and whether current protect logic warned in time."""

    peak_date: date
    first_3pct_date: date | None
    first_5pct_date: date
    first_8pct_date: date | None
    trough_date: date
    recovery_date: date | None
    max_drawdown: float
    first_armed_date: date | None
    armed_before_peak: bool
    first_protect_date: date | None
    protect_lead_days: int | None
    protect_timing: str
    first_redeploy_date: date | None
    redeploy_timing: str
    event_context: str


@dataclass(frozen=True, slots=True)
class RegimeCorrectionEpisodeResult:
    """Result of replaying protect/redeploy timing against SPY correction episodes."""

    start_date: date
    end_date: date
    episodes: tuple[RegimeCorrectionEpisode, ...]
    table: str


@dataclass(frozen=True, slots=True)
class RegimeProtectClusterOutcome:
    """One protect-action cluster replayed against forward market outcomes."""

    cluster_start_date: date
    cluster_end_date: date
    first_price_date: date | None
    protect_path: str | None
    action_count: int
    confirming_families: tuple[str, ...]
    volatility_only: bool
    late_signal: bool
    drawdown_from_peak: float | None
    horizon_days: int
    spy_return: float | None
    qqq_return: float | None
    spy_max_drawdown: float | None
    qqq_max_drawdown: float | None
    had_5pct_drawdown: bool | None


@dataclass(frozen=True, slots=True)
class RegimeProtectClusterResult:
    """Result of replaying protect clusters for false-alert diagnostics."""

    start_date: date
    end_date: date
    outcomes: tuple[RegimeProtectClusterOutcome, ...]
    table: str


@dataclass(frozen=True, slots=True)
class _SymbolFeatures:
    symbol: str
    price_date: date | None
    close: float | None
    return_5d: float | None
    return_20d: float | None
    return_60d: float | None
    change_5d: float | None
    change_20d: float | None
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


@dataclass(frozen=True, slots=True)
class _CorrectionEpisodeWindow:
    peak_index: int
    first_3pct_index: int | None
    first_5pct_index: int
    first_8pct_index: int | None
    trough_index: int
    recovery_index: int | None


@dataclass(frozen=True, slots=True)
class _ProtectGateResult:
    path: str | None
    extension_strength: float
    regime_break_strength: float
    confirming_families: tuple[str, ...]
    non_vol_confirming_families: tuple[str, ...]
    warning_only: bool
    reason: str


@dataclass(frozen=True, slots=True)
class _PressureModuleSpec:
    family: str
    name: str
    feature_names: tuple[str, ...]
    reason: str


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
        family="volatility",
        name="vix9d_vix_ratio",
        mode="low_stretch_high_washout",
        reason="VIX9D/VIX term ratio normalized as contango versus near-term stress",
    ),
    _PressureFeatureSpec(
        family="volatility",
        name="vix_vix3m_ratio",
        mode="low_stretch_high_washout",
        reason="VIX/VIX3M term ratio normalized as contango versus backwardation",
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
        family="breadth",
        name="sp500_above_50d",
        mode="low_weakness_pressure",
        reason="S&P 500 50d breadth participation versus its own history",
    ),
    _PressureFeatureSpec(
        family="breadth",
        name="sp500_above_200d",
        mode="low_weakness_pressure",
        reason="S&P 500 200d breadth participation versus its own history",
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

PRESSURE_MODULE_SPECS = (
    _PressureModuleSpec(
        family="trend",
        name="trend_extension",
        feature_names=(
            "spy_return_20d",
            "spy_return_60d",
            "qqq_return_20d",
            "spy_ma50_distance",
            "qqq_ma50_distance",
        ),
        reason="Index momentum and extension pressure",
    ),
    _PressureModuleSpec(
        family="volatility",
        name="vol_complacency",
        feature_names=(
            "spy_realized_vol_20d",
            "vix_close",
            "vvix_close",
            "vix9d_vix_ratio",
            "vix_vix3m_ratio",
        ),
        reason="Volatility complacency and panic pressure",
    ),
    _PressureModuleSpec(
        family="breadth",
        name="breadth_fragility",
        feature_names=(
            "rsp_spy_relative_20d",
            "iwm_spy_relative_20d",
            "sp500_above_50d",
            "sp500_above_200d",
        ),
        reason="Participation weakness pressure",
    ),
    _PressureModuleSpec(
        family="credit",
        name="credit_risk_appetite",
        feature_names=("hyg_tlt_relative_20d", "credit_spread"),
        reason="Credit and risk-appetite pressure",
    ),
    _PressureModuleSpec(
        family="liquidity",
        name="liquidity_conditions",
        feature_names=("financial_conditions",),
        reason="Liquidity and financial-condition pressure",
    ),
    _PressureModuleSpec(
        family="rates",
        name="yield_curve_pressure",
        feature_names=("yield_curve",),
        reason="Treasury curve pressure",
    ),
)


def refresh_regime_prices(
    *,
    start_date: date,
    end_date: date,
    price_root: Path = DEFAULT_PRICE_OBSERVATIONS_ROOT,
    symbols: tuple[str, ...] = DEFAULT_REGIME_PRICE_SYMBOLS,
    downloader=None,
    cboe_client=None,
    eoddata_client=None,
) -> RegimePriceRefreshResult:
    """Refresh price observations for market regime proxies."""

    if end_date < start_date:
        raise RegimeError("Price refresh end date must be on or after start date")

    requested_symbols = dedupe_symbols(symbols)
    breadth_symbols = tuple(
        symbol for symbol in requested_symbols if symbol in DEFAULT_REGIME_BREADTH_SYMBOLS
    )
    yahoo_symbols = tuple(
        symbol
        for symbol in requested_symbols
        if symbol not in DEFAULT_REGIME_BREADTH_SYMBOLS and not is_cboe_index_symbol(symbol)
    )
    cboe_symbols = tuple(
        symbol for symbol in requested_symbols if is_cboe_index_symbol(symbol)
    )
    price_results: list[PriceFetchResult] = []
    price_failures: list[RegimePriceRefreshFailure] = []
    for symbol in yahoo_symbols:
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
    for symbol in cboe_symbols:
        try:
            price_results.extend(
                fetch_and_write_cboe_index_daily_prices(
                    symbols=(symbol,),
                    start_date=start_date,
                    end_date=end_date,
                    output_root=price_root,
                    client=cboe_client,
                )
            )
        except PriceDataError as exc:
            price_failures.append(RegimePriceRefreshFailure(symbol=symbol, error=str(exc)))
            logger.bind(
                symbol=symbol,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                error=str(exc),
            ).error("Failed market regime CBOE index refresh")
    for symbol in breadth_symbols:
        try:
            price_results.extend(
                fetch_and_write_eoddata_index_daily_prices(
                    symbols=(symbol,),
                    start_date=start_date,
                    end_date=end_date,
                    output_root=price_root,
                    client=eoddata_client,
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
    signal_time: SignalTime | str = SignalTime.EOD,
    snapshot_version: str | None = None,
    write_snapshot: bool = True,
    overwrite_snapshot: bool = True,
    require_action_history: bool = False,
) -> RegimeSnapshotResult:
    """Compute and optionally persist one market regime snapshot."""

    _require_current_regime_compute_snapshot_version(
        snapshot_version,
        workflow="Market regime snapshot",
    )
    signal_time = _require_eod_signal_time(signal_time, workflow="Market regime snapshot")
    prior_snapshots = _load_recent_regime_snapshots_before(
        source_date=source_date,
        lookback_days=ACTION_EXTENSION_ARMED_MAX_AGE_DAYS,
        snapshot_root=snapshot_root,
        signal_time=signal_time,
        snapshot_version=snapshot_version,
    )
    if require_action_history and not prior_snapshots:
        raise RegimeError(
            _missing_extension_memory_history_message(
                source_date=source_date,
                snapshot_version=snapshot_version
                or default_snapshot_version(
                    source_date,
                    signal_time=signal_time,
                    default_version=REGIME_SNAPSHOT_VERSION,
                ),
            )
        )
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
        signal_time=signal_time,
        snapshot_version=snapshot_version,
        write_snapshot=write_snapshot,
        overwrite_snapshot=overwrite_snapshot,
        prior_snapshots=prior_snapshots,
        require_action_history=require_action_history,
    )


def compute_regime_backfill(
    *,
    start_date: date,
    end_date: date,
    price_root: Path = DEFAULT_PRICE_OBSERVATIONS_ROOT,
    market_series_root: Path = DEFAULT_MARKET_SERIES_OBSERVATIONS_ROOT,
    snapshot_root: Path = DEFAULT_REGIME_SNAPSHOT_ROOT,
    signal_snapshot_root: Path = DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT,
    signal_time: SignalTime | str = SignalTime.EOD,
    snapshot_version: str | None = None,
    write_snapshot: bool = True,
    skip_existing: bool = True,
    overwrite_snapshot: bool = True,
) -> RegimeBackfillResult:
    """Compute market regime snapshots for each SPY observation date in a range."""

    _require_current_regime_compute_snapshot_version(
        snapshot_version,
        workflow="Market regime backfill",
    )
    signal_time = _require_eod_signal_time(signal_time, workflow="Market regime backfill")
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
    pressure_feature_history = _pressure_feature_history_from_observations(
        source_date=end_date,
        histories=histories,
        market_series_histories=market_series_histories,
    )
    logger.bind(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        source_date_count=len(source_dates),
        write_snapshot=write_snapshot,
        skip_existing=skip_existing,
        overwrite_snapshot=overwrite_snapshot,
    ).info("Starting market regime backfill")

    snapshot_paths: list[Path] = []
    signal_snapshot_paths: list[Path] = []
    skipped_snapshot_paths: list[Path] = []
    action_history_snapshots = list(
        _load_recent_regime_snapshots_before(
            source_date=start_date,
            lookback_days=ACTION_EXTENSION_ARMED_MAX_AGE_DAYS,
            snapshot_root=snapshot_root,
            signal_time=signal_time,
            snapshot_version=snapshot_version,
        )
    )
    for source_date in source_dates:
        if write_snapshot and skip_existing:
            existing_snapshot_path = _existing_regime_snapshot_path(
                source_date=source_date,
                snapshot_root=snapshot_root,
                signal_time=signal_time,
                snapshot_version=snapshot_version,
            )
            if existing_snapshot_path is not None:
                snapshot_paths.append(existing_snapshot_path)
                skipped_snapshot_paths.append(existing_snapshot_path)
                existing_signal_path = _existing_market_signal_snapshot_path(
                    source_date=source_date,
                    signal_snapshot_root=signal_snapshot_root,
                    signal_time=signal_time,
                    snapshot_version=snapshot_version,
                )
                if existing_signal_path is not None:
                    signal_snapshot_paths.append(existing_signal_path)
                existing_snapshot = load_regime_snapshot(
                    source_date=source_date,
                    snapshot_root=snapshot_root,
                    signal_time=signal_time,
                    snapshot_version=snapshot_version,
                )
                if existing_snapshot is not None:
                    action_history_snapshots.append(existing_snapshot)
                logger.bind(
                    source_date=source_date.isoformat(),
                    snapshot_path=str(existing_snapshot_path),
                ).info("Skipping existing market regime snapshot during backfill")
                continue
        result = _compute_regime_snapshot_from_histories(
            source_date=source_date,
            histories=histories,
            market_series_histories=market_series_histories,
            snapshot_root=snapshot_root,
            signal_snapshot_root=signal_snapshot_root,
            signal_time=signal_time,
            snapshot_version=snapshot_version,
            write_snapshot=write_snapshot,
            overwrite_snapshot=overwrite_snapshot,
            pressure_feature_history=pressure_feature_history,
            prior_snapshots=tuple(action_history_snapshots),
            require_action_history=False,
        )
        action_history_snapshots.append(result.snapshot)
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
        skipped_snapshot_count=len(skipped_snapshot_paths),
        overwrite_snapshot=overwrite_snapshot,
    ).success("Completed market regime backfill")
    return RegimeBackfillResult(
        start_date=start_date,
        end_date=end_date,
        source_dates=source_dates,
        snapshot_paths=tuple(snapshot_paths),
        signal_snapshot_paths=tuple(signal_snapshot_paths),
        skipped_snapshot_paths=tuple(skipped_snapshot_paths),
    )


def _compute_regime_snapshot_from_histories(
    *,
    source_date: date,
    histories: dict[str, tuple[DailyPriceObservation, ...]],
    market_series_histories: dict[str, tuple[MarketSeriesObservation, ...]],
    snapshot_root: Path,
    signal_snapshot_root: Path,
    signal_time: SignalTime | str,
    snapshot_version: str | None,
    write_snapshot: bool,
    overwrite_snapshot: bool,
    pressure_feature_history: dict[str, tuple[_PressureFeatureSample, ...]] | None = None,
    prior_snapshots: tuple[RegimeSnapshot, ...] = (),
    require_action_history: bool = False,
) -> RegimeSnapshotResult:
    _require_current_regime_compute_snapshot_version(
        snapshot_version,
        workflow="Market regime snapshot",
    )
    signal_time_text = _require_eod_signal_time(signal_time, workflow="Market regime snapshot")
    snapshot_version_text = snapshot_version or default_snapshot_version(
        source_date,
        signal_time=signal_time_text,
        default_version=REGIME_SNAPSHOT_VERSION,
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
    signals = _market_signals_from_snapshot(
        _regime_snapshot_from_observation_features(
            source_date=source_date,
            features=features,
            market_series=market_series,
            signal_time=signal_time_text,
            snapshot_version=snapshot_version_text,
        ),
        features=features,
        market_series=market_series,
        market_series_histories=market_series_histories,
    )
    signal_snapshot_path = None

    snapshot = _regime_snapshot_from_market_signals(
        source_date=source_date,
        signals=signals,
        signal_time=signal_time_text,
        snapshot_version=snapshot_version_text,
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
    extension_memory = _extension_memory_from_snapshot_chain(
        snapshot=snapshot,
        prior_snapshots=prior_snapshots,
        require_prior_history=require_action_history,
    )
    action = derive_regime_action_state(
        snapshot=snapshot,
        signals=signals,
        extension_memory=extension_memory,
    )
    snapshot = _snapshot_with_action(snapshot=snapshot, action=action)
    snapshot_path = (
        write_regime_snapshot(
            snapshot,
            snapshot_root=snapshot_root,
            overwrite=overwrite_snapshot,
        )
        if write_snapshot
        else None
    )
    if write_snapshot:
        try:
            signal_snapshot_path = write_market_signal_snapshot(
                signals,
                snapshot_root=signal_snapshot_root,
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
        protect_strength=action.protect_strength,
        redeploy_strength=action.redeploy_strength,
        action_score=action.action_score,
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
        action_table=format_regime_action_modules(
            action.action_modules,
            action_features=action.action_features,
        ),
    )


def _require_current_regime_compute_snapshot_version(
    snapshot_version: str | None,
    *,
    workflow: str,
) -> None:
    if snapshot_version is None or snapshot_version == REGIME_SNAPSHOT_VERSION:
        return
    raise RegimeError(
        f"{workflow} can only compute current regime snapshot version "
        f"{REGIME_SNAPSHOT_VERSION}; got {snapshot_version}. "
        "Use --snapshot-version only with read/replay workflows for older saved snapshots."
    )


def compute_regime_recent_report(
    *,
    source_date: date,
    lookback_days: int = 10,
    snapshot_root: Path = DEFAULT_REGIME_SNAPSHOT_ROOT,
    signal_time: SignalTime | str = SignalTime.EOD,
    snapshot_version: str | None = None,
) -> RegimeRecentReportResult:
    """Format recent saved regime snapshots for transition review."""

    if lookback_days < 1:
        raise RegimeError("Report lookback days must be at least 1")

    snapshots = _load_recent_regime_snapshots_through(
        source_date=source_date,
        lookback_days=lookback_days,
        snapshot_root=snapshot_root,
        signal_time=signal_time,
        snapshot_version=snapshot_version,
    )
    if not snapshots:
        raise RegimeError(f"No market regime snapshots found through {source_date}")

    report = format_regime_recent_report(
        source_date=source_date,
        lookback_days=lookback_days,
        snapshots=snapshots,
    )
    logger.bind(
        source_date=source_date.isoformat(),
        lookback_days=lookback_days,
        snapshot_count=len(snapshots),
    ).success("Computed recent market regime report")
    return RegimeRecentReportResult(
        source_date=source_date,
        lookback_days=lookback_days,
        snapshots=snapshots,
        report=report,
    )


def write_regime_snapshot(
    snapshot: RegimeSnapshot,
    *,
    snapshot_root: Path = DEFAULT_REGIME_SNAPSHOT_ROOT,
    overwrite: bool = True,
) -> Path:
    """Write one market regime snapshot."""

    try:
        path = versioned_snapshot_path(
            snapshot_root=snapshot_root,
            source_date=snapshot.source_date,
            signal_time=snapshot.signal_time,
            snapshot_version=snapshot.snapshot_version,
            filename=REGIME_SNAPSHOT_FILENAME,
        )
    except ValueError as exc:
        raise RegimeError(str(exc)) from exc
    payload = (
        json.dumps(
            _with_write_provenance(
                snapshot.to_dict(),
                created_at=utc_timestamp(),
                code_revision=current_code_revision(),
            ),
            sort_keys=True,
        )
        + "\n"
    )
    wrote = write_snapshot_payload(
        path=path,
        payload=payload,
        error_cls=RegimeError,
        overwrite=overwrite,
    )
    logger.bind(
        source_date=snapshot.source_date.isoformat(),
        snapshot_path=str(path),
        wrote=wrote,
    ).success("Wrote market regime snapshot")
    return path


def load_regime_snapshot(
    *,
    source_date: date,
    snapshot_root: Path = DEFAULT_REGIME_SNAPSHOT_ROOT,
    signal_time: SignalTime | str = SignalTime.EOD,
    snapshot_version: str | None = None,
    model_version: str | None = None,
) -> RegimeSnapshot | None:
    """Load one market regime snapshot if present."""

    try:
        path = resolve_snapshot_path(
            snapshot_root=snapshot_root,
            source_date=source_date,
            signal_time=signal_time,
            snapshot_version=snapshot_version,
            filename=REGIME_SNAPSHOT_FILENAME,
            legacy_suffix=".json",
            default_version=REGIME_SNAPSHOT_VERSION,
        )
    except ValueError as exc:
        raise RegimeError(str(exc)) from exc
    if path is None:
        return None
    try:
        snapshot = _snapshot_from_dict(json.loads(path.read_text(encoding="utf-8")))
        if model_version is not None and snapshot.model_version != model_version:
            return None
        return snapshot
    except OSError as exc:
        raise RegimeError(f"Failed to read market regime snapshot: {path}") from exc
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise RegimeError(f"Invalid market regime snapshot file: {path}") from exc


def _regime_snapshot_from_observation_features(
    *,
    source_date: date,
    features: dict[str, _SymbolFeatures],
    market_series: dict[str, MarketSeriesObservation | None],
    signal_time: str,
    snapshot_version: str,
) -> RegimeSnapshot:
    components = _score_components(features)
    score = sum(component.score for component in components)
    missing_market_signal_count = _missing_market_signal_count(
        features=features,
        market_series=market_series,
    )
    missing_symbols = tuple(
        symbol for symbol, symbol_features in features.items() if symbol_features.price_date is None
    )
    return RegimeSnapshot(
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
        vix9d_vix_ratio=_aligned_ratio(features["^VIX9D"], features["^VIX"]),
        vix_vix3m_ratio=_aligned_ratio(features["^VIX"], features["^VIX3M"]),
        sp500_above_50d=features["$S5FI"].close,
        sp500_above_200d=features["$S5TH"].close,
        signal_time=signal_time,
        snapshot_version=snapshot_version,
        market_signal_snapshot_version=snapshot_version,
    )


def _regime_snapshot_from_market_signals(
    *,
    source_date: date,
    signals: tuple[MarketSignal, ...],
    signal_time: str,
    snapshot_version: str,
) -> RegimeSnapshot:
    if not signals:
        raise RegimeError(f"No market signal snapshot found for {source_date}")
    _validate_market_signal_boundary(
        source_date=source_date,
        signals=signals,
        signal_time=signal_time,
        snapshot_version=snapshot_version,
    )
    component_signals = {
        family: _signal_by_name(signals, family=family, name="price_proxy")
        for family in ("trend", "volatility", "breadth", "credit")
    }
    components = tuple(
        _component_from_signal(family=family, signal=component_signals[family])
        for family in ("trend", "volatility", "breadth", "credit")
    )
    score = sum(component.score for component in components)
    trend = component_signals["trend"]
    volatility = component_signals["volatility"]
    breadth = component_signals["breadth"]
    credit = component_signals["credit"]
    vvix_signal = _signal_by_name(signals, family="volatility", name="vol_of_vol")
    vvix_close = _signal_value(signals, family="volatility", name="vol_of_vol")
    if vvix_close is None:
        vvix_close = _signal_detail_float(vvix_signal, "vvix_close")
    term_structure_signal = _signal_by_name(
        signals,
        family="volatility",
        name="term_structure",
    )
    participation_signal = _signal_by_name(
        signals,
        family="breadth",
        name="participation",
    )
    price_date = _signal_detail_date(trend, "price_date") or (
        trend.observed_date if trend else None
    )
    return RegimeSnapshot(
        source_date=source_date,
        feature_version=REGIME_FEATURE_VERSION,
        model_version=REGIME_MODEL_VERSION,
        price_date=price_date,
        regime=_regime_label(score),
        score=score,
        confidence=_confidence(
            score=score,
            components=components,
            missing_market_signal_count=_missing_independent_market_signal_count(signals),
        ),
        components=components,
        missing_symbols=_missing_symbols_from_signals(signals),
        spy_return_20d=_signal_detail_float(trend, "spy_return_20d"),
        spy_return_60d=_signal_detail_float(trend, "spy_return_60d"),
        spy_ma50_distance=_signal_detail_float(trend, "spy_ma50_distance"),
        spy_ma200_distance=_signal_detail_float(trend, "spy_ma200_distance"),
        spy_realized_vol_20d=_signal_detail_float(volatility, "spy_realized_vol_20d"),
        qqq_return_20d=_signal_detail_float(trend, "qqq_return_20d"),
        qqq_ma50_distance=_signal_detail_float(trend, "qqq_ma50_distance"),
        qqq_ma200_distance=_signal_detail_float(trend, "qqq_ma200_distance"),
        rsp_spy_relative_20d=_signal_detail_float(breadth, "rsp_spy_relative_20d"),
        iwm_spy_relative_20d=_signal_detail_float(breadth, "iwm_spy_relative_20d"),
        hyg_tlt_relative_20d=_signal_detail_float(credit, "hyg_tlt_relative_20d"),
        vix_close=_signal_detail_float(volatility, "vix_close"),
        vvix_close=vvix_close,
        vix9d_vix_ratio=_signal_detail_float(term_structure_signal, "vix9d_vix_ratio"),
        vix_vix3m_ratio=_signal_detail_float(term_structure_signal, "vix_vix3m_ratio"),
        sp500_above_50d=_signal_detail_float(participation_signal, "sp500_above_50d"),
        sp500_above_200d=_signal_detail_float(participation_signal, "sp500_above_200d"),
        signal_time=signal_time,
        snapshot_version=snapshot_version,
        market_signal_snapshot_version=_shared_market_signal_snapshot_version(signals),
    )


def _validate_market_signal_boundary(
    *,
    source_date: date,
    signals: tuple[MarketSignal, ...],
    signal_time: str,
    snapshot_version: str,
) -> None:
    invalid_dates = sorted(
        {signal.source_date for signal in signals if signal.source_date != source_date}
    )
    if invalid_dates:
        raise RegimeError(
            "Market signal boundary contains unexpected source dates: "
            + ",".join(value.isoformat() for value in invalid_dates)
        )
    invalid_times = sorted(
        {signal.signal_time for signal in signals if signal.signal_time != signal_time}
    )
    if invalid_times:
        raise RegimeError(
            "Market signal boundary contains unexpected signal times: " + ",".join(invalid_times)
        )
    invalid_versions = sorted(
        {
            signal.snapshot_version
            for signal in signals
            if signal.snapshot_version and signal.snapshot_version != snapshot_version
        }
    )
    if invalid_versions:
        raise RegimeError(
            "Market signal boundary contains unexpected snapshot versions: "
            + ",".join(invalid_versions)
        )


def _component_from_signal(
    *,
    family: str,
    signal: MarketSignal | None,
) -> RegimeComponentScore:
    if signal is None:
        return RegimeComponentScore(
            name=family,
            score=0,
            status="missing",
            reason=f"Missing {family} price-proxy market signal",
        )
    return RegimeComponentScore(
        name=family,
        score=signal.score,
        status=signal.status,
        reason=signal.reason,
    )


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


def format_regime_key_signals(result: RegimeSnapshotResult) -> str:
    """Format the final market regime read as a compact summary table."""

    snapshot = result.snapshot
    missing_inputs = _missing_market_input_labels(
        snapshot=snapshot,
        signals=result.signals,
    )
    rows = [
        ["signal", "value", "read"],
        [
            "regime",
            f"{snapshot.regime} ({_format_score(snapshot.score)})",
            _regime_read(snapshot, missing_inputs=missing_inputs),
        ],
    ]
    pressure = result.pressure
    stretch_pressure_score = (
        pressure.stretch_pressure_score
        if pressure is not None
        else snapshot.stretch_pressure_score
    )
    washout_pressure_score = (
        pressure.washout_pressure_score
        if pressure is not None
        else snapshot.washout_pressure_score
    )
    pressure_confidence = (
        pressure.confidence if pressure is not None else snapshot.pressure_confidence
    )
    rows.append(
        [
            "pressure",
            (
                f"stretch {_format_pressure_score(stretch_pressure_score)} / "
                f"washout {_format_pressure_score(washout_pressure_score)}"
            ),
            (
                f"{_pressure_level(stretch_pressure_score)} stretch / "
                f"{_pressure_level(washout_pressure_score)} washout; "
                f"{pressure_confidence} confidence"
            ),
        ]
    )
    if snapshot.extension_setup_score is not None:
        rows.append(
            [
                "extension_setup",
                _gate_value(
                    score=snapshot.extension_setup_score,
                    threshold=ACTION_EXTENSION_SETUP_THRESHOLD,
                ),
                _extension_setup_read(snapshot.extension_setup_score),
            ]
        )
    action = result.action or _action_state_from_snapshot(snapshot)
    rows.append(
        [
            "extension_armed",
            _extension_armed_value(action),
            _extension_armed_read(action),
        ]
    )
    if snapshot.fragility_context_score is not None:
        rows.append(
            [
                "fragility",
                _gate_value(
                    score=snapshot.fragility_context_score,
                    threshold=ACTION_REGIME_BREAK_CONTEXT_THRESHOLD,
                ),
                _fragility_context_read(snapshot.fragility_context_score),
            ]
        )
    rows.append(
        [
            "deterioration",
            _format_pressure_score(action.deterioration_score),
            _action_confirmation_read(
                label="protect",
                score=action.deterioration_score,
                families=_confirming_families(
                    modules=action.action_modules,
                    field_name="deterioration_score",
                ),
            ),
        ]
    )
    rows.append(
        [
            "event_vol",
            _event_volatility_context_value(action.event_volatility_context),
            _event_volatility_context_read(action.event_volatility_context),
        ]
    )
    if snapshot.washout_setup_score is not None:
        rows.append(
            [
                "redeploy_setup",
                _format_pressure_score(snapshot.washout_setup_score),
                _redeploy_setup_read(snapshot.washout_setup_score),
            ]
        )
    rows.append(
        [
            "stabilization",
            _format_pressure_score(action.stabilization_score),
            _action_confirmation_read(
                label="redeploy",
                score=action.stabilization_score,
                families=_confirming_families(
                    modules=action.action_modules,
                    field_name="stabilization_score",
                ),
            ),
        ]
    )
    rows.append(
        [
            "strength",
            (
                f"protect {_format_pressure_score(action.protect_strength)} / "
                f"redeploy {_format_pressure_score(action.redeploy_strength)}; "
                f"net {action.action_score:+.2f}"
            ),
            _action_strength_read(action),
        ]
    )
    rows.append(
        [
            "input_gaps",
            ",".join(missing_inputs) if missing_inputs else "none",
            "missing point-in-time observations",
        ]
    )
    rows.append(
        [
            "action",
            f"{_action_state_label(action.state)}; {action.confidence} confidence",
            _action_decision_read(action),
        ]
    )
    return _format_table(rows)


def format_regime_recent_report(
    *,
    source_date: date,
    lookback_days: int,
    snapshots: tuple[RegimeSnapshot, ...],
) -> str:
    """Format recent market-regime snapshots as trend tables."""

    if not snapshots:
        return "No market regime snapshots found."

    lines = [
        f"MarketLab recent regime report - through {source_date.isoformat()}",
        f"saved_trading_day_count={len(snapshots)} requested_days={lookback_days}",
        "",
        "regime_trend: headline, setup pressure, and action strength",
        _format_recent_regime_trend(snapshots),
        "",
        "signal_percentiles: key pressure-feature percentiles in trailing context",
        _format_recent_signal_percentiles(snapshots),
    ]
    return "\n".join(lines)


def _format_recent_regime_trend(snapshots: tuple[RegimeSnapshot, ...]) -> str:
    rows = [
        [
            "date",
            "regime",
            "score",
            "stretch",
            "washout",
            "protect",
            "redeploy",
            "net",
            "action",
        ]
    ]
    for snapshot in snapshots:
        rows.append(
            [
                snapshot.source_date.isoformat(),
                snapshot.regime,
                _format_score(snapshot.score),
                _format_pressure_score(snapshot.stretch_pressure_score),
                _format_pressure_score(snapshot.washout_pressure_score),
                _format_pressure_score(snapshot.protect_strength),
                _format_pressure_score(snapshot.redeploy_strength),
                _format_signed_decimal(snapshot.action_score),
                _action_state_label(snapshot.action_state),
            ]
        )
    return _format_table(rows)


_RECENT_SIGNAL_PERCENTILE_FEATURES = (
    ("SPY20", "spy_return_20d"),
    ("VIX", "vix_close"),
    ("VVIX", "vvix_close"),
    ("RSP/SPY", "rsp_spy_relative_20d"),
    ("IWM/SPY", "iwm_spy_relative_20d"),
    ("HYG/TLT", "hyg_tlt_relative_20d"),
    ("HY OAS", "credit_spread"),
    ("NFCI", "financial_conditions"),
)


def _format_recent_signal_percentiles(snapshots: tuple[RegimeSnapshot, ...]) -> str:
    rows = [["date", *(label for label, _name in _RECENT_SIGNAL_PERCENTILE_FEATURES)]]
    for snapshot in snapshots:
        features = {feature.name: feature for feature in snapshot.pressure_features}
        rows.append(
            [
                snapshot.source_date.isoformat(),
                *(
                    _format_percentile(features[name].percentile)
                    if name in features
                    else "-"
                    for _label, name in _RECENT_SIGNAL_PERCENTILE_FEATURES
                ),
            ]
        )
    return _format_table(rows)


def _regime_read(snapshot: RegimeSnapshot, *, missing_inputs: tuple[str, ...]) -> str:
    return "; ".join(
        (
            _regime_strength_read(snapshot),
            _data_quality_read(missing_inputs),
            f"{snapshot.confidence} confidence",
        )
    )


def _regime_strength_read(snapshot: RegimeSnapshot) -> str:
    if snapshot.regime == "neutral":
        return "mixed backdrop"
    magnitude = abs(snapshot.score)
    if magnitude <= 2:
        return f"marginal {snapshot.regime}"
    if magnitude == 3:
        return f"moderate {snapshot.regime}"
    return f"strong {snapshot.regime}"


def _pressure_level(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= 0.85:
        return "extreme"
    if score >= 0.70:
        return "high"
    if score >= 0.55:
        return "elevated"
    if score >= 0.30:
        return "noticeable"
    return "low"


def _action_strength_read(action: RegimeActionState) -> str:
    if action.state == "scale_down_protect":
        return "protect signal active"
    if action.state == "scale_up_redeploy":
        return "redeploy signal active"
    if action.protect_strength > action.redeploy_strength:
        return _inactive_action_strength_read("protect", action.protect_strength)
    if action.redeploy_strength > action.protect_strength:
        return _inactive_action_strength_read("redeploy", action.redeploy_strength)
    return "balanced below action threshold"


def _inactive_action_strength_read(label: str, strength: float) -> str:
    if strength >= ACTION_STRENGTH_THRESHOLD - 0.10:
        return f"{label} lean near {ACTION_STRENGTH_THRESHOLD:.2f} action threshold"
    return f"{label} lean below action threshold"


def _action_decision_read(action: RegimeActionState) -> str:
    reason = _nonredundant_action_reason(action)
    if reason:
        return reason
    if action.state == "no_change":
        return "no action trigger"
    return "action threshold crossed"


def _action_confirmation_read(
    *,
    label: str,
    score: float,
    families: tuple[str, ...],
) -> str:
    level = _pressure_level(score)
    if families:
        return f"{level} {label} confirmation; families {_family_list_read(families)}"
    return f"{level} {label} confirmation; families none"


def _gate_value(*, score: float, threshold: float) -> str:
    operator = ">=" if score >= threshold else "<"
    return f"{_format_pressure_score(score)} {operator} {threshold:.2f}"


def _extension_setup_read(score: float) -> str:
    if score >= ACTION_EXTENSION_SETUP_THRESHOLD:
        return "today's extension setup can arm protect"
    if score >= ACTION_EXTENSION_SETUP_THRESHOLD - 0.10:
        return "near extension-unwind setup gate"
    if score >= 0.30:
        return "partial extension; not armed"
    return "low extension; extension-unwind setup not armed"


def _extension_armed_value(action: RegimeActionState) -> str:
    if action.extension_armed_since is None:
        return f"no; score {_format_pressure_score(action.extension_memory_score)}"
    age = "-" if action.extension_armed_age is None else str(action.extension_armed_age)
    decay = (
        "-"
        if action.extension_armed_decay is None
        else _format_pressure_score(action.extension_armed_decay)
    )
    return (
        f"{'yes' if action.extension_armed else 'expired'}; "
        f"since {action.extension_armed_since.isoformat()}; "
        f"age {age}; decay {decay}; "
        f"score {_format_pressure_score(action.extension_memory_score)}"
    )


def _extension_armed_read(action: RegimeActionState) -> str:
    if action.extension_memory_status == "initializing":
        return "no prior snapshot chain; run backfill before relying on single-date action"
    if action.extension_armed:
        return "prior extension setup can support extension-unwind protect"
    if action.extension_armed_since is not None:
        return "prior extension setup expired"
    return "no recent extension setup armed"


def _fragility_context_read(score: float) -> str:
    if score >= ACTION_REGIME_BREAK_CONTEXT_THRESHOLD:
        return "regime-break context active"
    if score >= ACTION_REGIME_BREAK_CONTEXT_THRESHOLD - 0.10:
        return "near regime-break context gate"
    if score >= 0.30:
        return "some fragility; not enough for regime-break"
    return "low fragility context"


def _redeploy_setup_read(score: float) -> str:
    if score >= ACTION_STRENGTH_THRESHOLD:
        return "washout setup visible for redeploy"
    if score >= ACTION_STRENGTH_THRESHOLD - 0.10:
        return "near redeploy setup level"
    if score >= 0.30:
        return "partial washout; redeploy setup not armed"
    return "low washout; redeploy setup not armed"


def _action_state_label(state: str) -> str:
    if state == "no_change":
        return "maintain"
    if state == "scale_down_protect":
        return "protect"
    if state == "scale_up_redeploy":
        return "redeploy"
    return state


def _data_quality_read(missing_inputs: tuple[str, ...]) -> str:
    if missing_inputs:
        return "data gaps: " + ",".join(missing_inputs)
    return "data complete"


def _nonredundant_action_reason(action: RegimeActionState) -> str | None:
    default_reason = "No actionable setup; maintain current posture"
    if action.state == "no_change" and action.reason.startswith(default_reason):
        suffix = action.reason[len(default_reason) :].lstrip(": ")
        return suffix or None
    return action.reason


def _event_volatility_context_value(context: str) -> str:
    if context == "near_term_event_premium":
        return "near-term premium"
    if context == "near_term_event_premium_with_confirmation":
        return "near-term premium + confirmation"
    if context == "volatility_only_warning":
        return "vol-only warning"
    return "none"


def _event_volatility_context_read(context: str) -> str:
    if context == "near_term_event_premium":
        return "event-vol premium is visible; needs non-vol confirmation"
    if context == "near_term_event_premium_with_confirmation":
        return "event-vol premium is visible with breadth/credit confirmation"
    if context == "volatility_only_warning":
        return "volatility deterioration lacks non-vol confirmation"
    return "no near-term event-vol premium detected"


def format_regime_action_modules(
    modules: tuple[RegimeActionModule, ...],
    *,
    action_features: tuple[RegimeActionFeature, ...] = (),
) -> str:
    """Format bounded action-evidence modules as a compact table."""

    if not modules:
        return "No regime action evidence modules found."

    if action_features:
        rows = [["family", "signal", "protect", "redeploy", "read"]]
        for feature in _action_features_for_display(action_features):
            rows.append(
                [
                    feature.family,
                    _action_feature_display_name(feature.name),
                    _format_pressure_score(feature.deterioration_score),
                    _format_pressure_score(feature.stabilization_score),
                    feature.reason,
                ]
            )
        return _format_table(rows)

    rows = [["family", "module", "protect", "redeploy", "read"]]
    for module in modules:
        rows.append(
            [
                module.family,
                module.name,
                _format_pressure_score(module.deterioration_score),
                _format_pressure_score(module.stabilization_score),
                module.reason,
            ]
        )
    return _format_table(rows)


def _action_features_for_display(
    features: tuple[RegimeActionFeature, ...],
) -> tuple[RegimeActionFeature, ...]:
    family_order = {
        family: index for index, (family, _module_name) in enumerate(_ACTION_MODULE_SPECS)
    }
    return tuple(
        feature
        for _index, feature in sorted(
            enumerate(features),
            key=lambda item: (
                family_order.get(item[1].family, len(family_order)),
                item[0],
            ),
        )
    )


def _action_feature_display_name(name: str) -> str:
    labels = {
        "vvix_vs_vix": "vvix_vs_vix",
        "volatility_normalization_confirmation": "vol_normalization",
        "price_breadth_divergence": "price_vs_breadth",
        "equity_credit_divergence": "equity_vs_credit",
        "breadth_credit_confirmation": "breadth_vs_credit",
        "rebound_not_confirmed_by_credit": "rebound_vs_credit",
    }
    return labels.get(name, name)


def _missing_market_input_labels(
    *,
    snapshot: RegimeSnapshot,
    signals: tuple[MarketSignal, ...],
) -> tuple[str, ...]:
    missing = list(snapshot.missing_symbols)
    missing.extend(
        f"{signal.family}/{signal.name}"
        for signal in signals
        if signal.status == "missing"
    )
    return tuple(dict.fromkeys(missing))


def _market_signals_from_snapshot(
    snapshot: RegimeSnapshot,
    *,
    features: dict[str, _SymbolFeatures],
    market_series: dict[str, MarketSeriesObservation | None],
    market_series_histories: dict[str, tuple[MarketSeriesObservation, ...]],
) -> tuple[MarketSignal, ...]:
    signals = [
        MarketSignal(
            source_date=snapshot.source_date,
            feature_version=MARKET_SIGNAL_FEATURE_VERSION,
            family=component.name,
            name="price_proxy",
            status=component.status,
            score=component.score,
            value=_component_value(
                snapshot,
                component.name,
                features=features,
            ),
            unit="text",
            source=_component_signal_source(component.name),
            observed_date=snapshot.price_date,
            availability_date=snapshot.price_date,
            reason=component.reason,
            details=_component_signal_details(
                snapshot=snapshot,
                component_name=component.name,
                features=features,
            ),
        )
        for component in snapshot.components
    ]
    signals.append(_vvix_signal(snapshot=snapshot, features=features["^VVIX"]))
    signals.append(_vix_term_structure_signal(snapshot=snapshot, features=features))
    signals.append(_breadth_participation_signal(snapshot=snapshot, features=features))
    signals.extend(
        _fred_market_signals(
            source_date=snapshot.source_date,
            series=market_series,
            histories=market_series_histories,
        )
    )
    return tuple(
        replace(
            signal,
            signal_time=snapshot.signal_time,
            snapshot_version=snapshot.snapshot_version,
        )
        for signal in signals
    )


def _component_signal_details(
    *,
    snapshot: RegimeSnapshot,
    component_name: str,
    features: dict[str, _SymbolFeatures],
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "price_date": snapshot.price_date.isoformat() if snapshot.price_date else None,
        "missing_symbols": list(snapshot.missing_symbols),
    }
    if component_name == "trend":
        details.update(
            {
                "spy_return_20d": snapshot.spy_return_20d,
                "spy_return_60d": snapshot.spy_return_60d,
                "spy_ma50_distance": snapshot.spy_ma50_distance,
                "spy_ma200_distance": snapshot.spy_ma200_distance,
                "qqq_return_20d": snapshot.qqq_return_20d,
                "qqq_return_60d": features["QQQ"].return_60d,
                "qqq_ma50_distance": snapshot.qqq_ma50_distance,
                "qqq_ma200_distance": snapshot.qqq_ma200_distance,
            }
        )
    elif component_name == "volatility":
        vix = features["^VIX"]
        details.update(
            {
                "spy_realized_vol_20d": snapshot.spy_realized_vol_20d,
                "vix_close": snapshot.vix_close,
                "vix_return_5d": vix.return_5d,
                "vix_return_20d": vix.return_20d,
                "vix_change_5d": vix.change_5d,
                "vix_change_20d": vix.change_20d,
            }
        )
    elif component_name == "breadth":
        rsp = features["RSP"]
        iwm = features["IWM"]
        spy = features["SPY"]
        details.update(
            {
                "rsp_spy_relative_5d": _relative_return_for_lookback(
                    rsp,
                    spy,
                    field_name="return_5d",
                ),
                "rsp_spy_relative_20d": snapshot.rsp_spy_relative_20d,
                "iwm_spy_relative_5d": _relative_return_for_lookback(
                    iwm,
                    spy,
                    field_name="return_5d",
                ),
                "iwm_spy_relative_20d": snapshot.iwm_spy_relative_20d,
            }
        )
    elif component_name == "credit":
        hyg = features["HYG"]
        tlt = features["TLT"]
        details.update(
            {
                "hyg_tlt_relative_5d": _relative_return_for_lookback(
                    hyg,
                    tlt,
                    field_name="return_5d",
                ),
                "hyg_tlt_relative_20d": snapshot.hyg_tlt_relative_20d,
            }
        )
    return details


def _component_signal_source(component_name: str) -> str:
    if component_name == "volatility":
        return "yahoo_cboe_price_proxy"
    return "yahoo_price_proxy"


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
            source="cboe_vvix",
            observed_date=None,
            availability_date=None,
            reason="VVIX is unavailable",
            details={
                "vvix_close": None,
                "vvix_return_5d": None,
                "vvix_return_20d": None,
                "vvix_change_5d": None,
                "vvix_change_20d": None,
                "missing_symbols": ["^VVIX"],
            },
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
        source="cboe_vvix",
        observed_date=features.price_date,
        availability_date=features.price_date,
        reason=reason,
        details={
            "vvix_close": features.close,
            "vvix_return_5d": features.return_5d,
            "vvix_return_20d": features.return_20d,
            "vvix_change_5d": features.change_5d,
            "vvix_change_20d": features.change_20d,
            "missing_symbols": [],
        },
    )


def _vix_term_structure_signal(
    *,
    snapshot: RegimeSnapshot,
    features: dict[str, _SymbolFeatures],
) -> MarketSignal:
    vix9d = features["^VIX9D"]
    vix = features["^VIX"]
    vix3m = features["^VIX3M"]
    vix9d_vix_ratio = _aligned_ratio(vix9d, vix)
    vix_vix3m_ratio = _aligned_ratio(vix, vix3m)
    missing_symbols = tuple(
        symbol
        for symbol, feature in (("^VIX9D", vix9d), ("^VIX", vix), ("^VIX3M", vix3m))
        if feature.close is None
    )
    stale_pairs = _vix_term_structure_stale_pairs(vix9d=vix9d, vix=vix, vix3m=vix3m)
    details = {
        "vix9d_close": vix9d.close,
        "vix_close": vix.close,
        "vix3m_close": vix3m.close,
        "vix9d_observed_date": vix9d.price_date.isoformat() if vix9d.price_date else None,
        "vix_observed_date": vix.price_date.isoformat() if vix.price_date else None,
        "vix3m_observed_date": vix3m.price_date.isoformat() if vix3m.price_date else None,
        "vix9d_vix_ratio": vix9d_vix_ratio,
        "vix_vix3m_ratio": vix_vix3m_ratio,
        "vix9d_vix_ratio_change_5d": _aligned_ratio_change(
            vix9d,
            vix,
            field_name="return_5d",
        ),
        "vix9d_vix_ratio_change_20d": _aligned_ratio_change(
            vix9d,
            vix,
            field_name="return_20d",
        ),
        "vix_vix3m_ratio_change_5d": _aligned_ratio_change(
            vix,
            vix3m,
            field_name="return_5d",
        ),
        "vix_vix3m_ratio_change_20d": _aligned_ratio_change(
            vix,
            vix3m,
            field_name="return_20d",
        ),
        "missing_symbols": list(missing_symbols),
        "stale_pairs": list(stale_pairs),
    }
    if missing_symbols or (vix9d_vix_ratio is None and vix_vix3m_ratio is None):
        return MarketSignal(
            source_date=snapshot.source_date,
            feature_version=MARKET_SIGNAL_FEATURE_VERSION,
            family="volatility",
            name="term_structure",
            status="missing",
            score=0,
            value=None,
            unit="ratio",
            source="cboe_vix_term_structure",
            observed_date=None,
            availability_date=None,
            reason="VIX9D/VIX/VIX3M term structure is unavailable on aligned dates",
            details=details,
        )

    if _ge(vix_vix3m_ratio, 1.0) or _ge(vix9d_vix_ratio, 1.10):
        status = "inverted"
        score = -1
        reason = "VIX term structure shows near-term stress"
    elif _lt(vix_vix3m_ratio, 0.90) and _lt(vix9d_vix_ratio, 0.95):
        status = "contango"
        score = 1
        reason = "VIX term structure is upward sloping"
    else:
        status = "mixed"
        score = 0
        reason = "VIX term structure is mixed"
    observed_dates = _vix_term_structure_observed_dates(vix9d=vix9d, vix=vix, vix3m=vix3m)
    observed_date = max(observed_dates) if observed_dates else None
    return MarketSignal(
        source_date=snapshot.source_date,
        feature_version=MARKET_SIGNAL_FEATURE_VERSION,
        family="volatility",
        name="term_structure",
        status=status,
        score=score,
        value=vix_vix3m_ratio,
        unit="ratio",
        source="cboe_vix_term_structure",
        observed_date=observed_date,
        availability_date=observed_date,
        reason=reason,
        details=details,
    )


def _breadth_participation_signal(
    *,
    snapshot: RegimeSnapshot,
    features: dict[str, _SymbolFeatures],
) -> MarketSignal:
    sp500_above_50d = features["$S5FI"]
    sp500_above_200d = features["$S5TH"]
    missing_symbols = tuple(
        symbol
        for symbol, feature in (("$S5FI", sp500_above_50d), ("$S5TH", sp500_above_200d))
        if feature.close is None
    )
    details = {
        "sp500_above_50d": sp500_above_50d.close,
        "sp500_above_200d": sp500_above_200d.close,
        "sp500_above_50d_change_5d": sp500_above_50d.change_5d,
        "sp500_above_50d_change_20d": sp500_above_50d.change_20d,
        "sp500_above_200d_change_5d": sp500_above_200d.change_5d,
        "sp500_above_200d_change_20d": sp500_above_200d.change_20d,
        "missing_symbols": list(missing_symbols),
    }
    if missing_symbols:
        return MarketSignal(
            source_date=snapshot.source_date,
            feature_version=MARKET_SIGNAL_FEATURE_VERSION,
            family="breadth",
            name="participation",
            status="missing",
            score=0,
            value=None,
            unit="percent_level",
            source="eoddata:S5FI/S5TH",
            observed_date=None,
            availability_date=None,
            reason="S&P 500 breadth internals are unavailable",
            details=details,
        )

    above_50d = sp500_above_50d.close
    above_200d = sp500_above_200d.close
    if _le(above_50d, 40.0) or _le(above_200d, 40.0):
        status = "weak"
        score = -1
        reason = "S&P 500 breadth internals show weak participation"
    elif _ge(above_50d, 60.0) and _ge(above_200d, 55.0):
        status = "broad"
        score = 1
        reason = "S&P 500 breadth internals show broad participation"
    else:
        status = "mixed"
        score = 0
        reason = "S&P 500 breadth internals are mixed"
    observed_dates = tuple(
        feature.price_date
        for feature in (sp500_above_50d, sp500_above_200d)
        if feature.price_date is not None
    )
    observed_date = max(observed_dates) if observed_dates else None
    return MarketSignal(
        source_date=snapshot.source_date,
        feature_version=MARKET_SIGNAL_FEATURE_VERSION,
        family="breadth",
        name="participation",
        status=status,
        score=score,
        value=above_50d,
        unit="percent_level",
        source="eoddata:S5FI/S5TH",
        observed_date=observed_date,
        availability_date=observed_date,
        reason=reason,
        details=details,
    )


def _fred_market_signals(
    *,
    source_date: date,
    series: dict[str, MarketSeriesObservation | None],
    histories: dict[str, tuple[MarketSeriesObservation, ...]],
) -> tuple[MarketSignal, ...]:
    return (
        _high_yield_oas_signal(
            source_date=source_date,
            row=series["BAMLH0A0HYM2"],
            history=histories.get("BAMLH0A0HYM2", ()),
        ),
        _nfci_signal(
            source_date=source_date,
            row=series["NFCI"],
            history=histories.get("NFCI", ()),
        ),
        _yield_curve_signal(
            source_date=source_date,
            ten_year=series["DGS10"],
            two_year=series["DGS2"],
            ten_year_history=histories.get("DGS10", ()),
            two_year_history=histories.get("DGS2", ()),
        ),
    )


def _high_yield_oas_signal(
    *,
    source_date: date,
    row: MarketSeriesObservation | None,
    history: tuple[MarketSeriesObservation, ...],
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
        details=_market_series_change_details(
            source_date=source_date,
            row=row,
            history=history,
            key_prefix="credit_spread",
            lookbacks=(("5d", 5), ("20d", 20)),
        ),
    )


def _nfci_signal(
    *,
    source_date: date,
    row: MarketSeriesObservation | None,
    history: tuple[MarketSeriesObservation, ...],
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
        details=_market_series_change_details(
            source_date=source_date,
            row=row,
            history=history,
            key_prefix="financial_conditions",
            lookbacks=(("4w", 4), ("13w", 13)),
        ),
    )


def _yield_curve_signal(
    *,
    source_date: date,
    ten_year: MarketSeriesObservation | None,
    two_year: MarketSeriesObservation | None,
    ten_year_history: tuple[MarketSeriesObservation, ...],
    two_year_history: tuple[MarketSeriesObservation, ...],
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
        details={
            "yield_curve": value,
            **_yield_curve_change_details(
                source_date=source_date,
                ten_year=ten_year,
                two_year=two_year,
                ten_year_history=ten_year_history,
                two_year_history=two_year_history,
            ),
        },
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
    details: dict[str, Any] | None = None,
) -> MarketSignal:
    signal_details = {
        name: row.value,
        "vintage_mode": row.vintage_mode,
    }
    if details is not None:
        signal_details.update(details)
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
        details=signal_details,
    )


def _market_series_change_details(
    *,
    source_date: date,
    row: MarketSeriesObservation,
    history: tuple[MarketSeriesObservation, ...],
    key_prefix: str,
    lookbacks: tuple[tuple[str, int], ...],
) -> dict[str, float | None]:
    return {
        f"{key_prefix}_change_{label}": _market_series_observation_change(
            source_date=source_date,
            row=row,
            history=history,
            lookback_observations=lookback_observations,
        )
        for label, lookback_observations in lookbacks
    }


def _market_series_observation_change(
    *,
    source_date: date,
    row: MarketSeriesObservation,
    history: tuple[MarketSeriesObservation, ...],
    lookback_observations: int,
) -> float | None:
    previous = _market_series_lookback_row(
        source_date=source_date,
        row=row,
        history=history,
        lookback_observations=lookback_observations,
    )
    if previous is None:
        return None
    return row.value - previous.value


def _yield_curve_change_details(
    *,
    source_date: date,
    ten_year: MarketSeriesObservation,
    two_year: MarketSeriesObservation,
    ten_year_history: tuple[MarketSeriesObservation, ...],
    two_year_history: tuple[MarketSeriesObservation, ...],
) -> dict[str, float | None]:
    return {
        f"yield_curve_change_{label}": _yield_curve_observation_change(
            source_date=source_date,
            ten_year=ten_year,
            two_year=two_year,
            ten_year_history=ten_year_history,
            two_year_history=two_year_history,
            lookback_observations=lookback_observations,
        )
        for label, lookback_observations in (("5d", 5), ("20d", 20))
    }


def _yield_curve_observation_change(
    *,
    source_date: date,
    ten_year: MarketSeriesObservation,
    two_year: MarketSeriesObservation,
    ten_year_history: tuple[MarketSeriesObservation, ...],
    two_year_history: tuple[MarketSeriesObservation, ...],
    lookback_observations: int,
) -> float | None:
    previous_ten_year = _market_series_lookback_row(
        source_date=source_date,
        row=ten_year,
        history=ten_year_history,
        lookback_observations=lookback_observations,
    )
    previous_two_year = _market_series_lookback_row(
        source_date=source_date,
        row=two_year,
        history=two_year_history,
        lookback_observations=lookback_observations,
    )
    if previous_ten_year is None or previous_two_year is None:
        return None
    current_curve = ten_year.value - two_year.value
    previous_curve = previous_ten_year.value - previous_two_year.value
    return current_curve - previous_curve


def _market_series_lookback_row(
    *,
    source_date: date,
    row: MarketSeriesObservation,
    history: tuple[MarketSeriesObservation, ...],
    lookback_observations: int,
) -> MarketSeriesObservation | None:
    asof_history = tuple(
        candidate
        for candidate in history
        if candidate.availability_date <= source_date
        and candidate.observed_date <= row.observed_date
    )
    current_index = next(
        (
            index
            for index in range(len(asof_history) - 1, -1, -1)
            if asof_history[index].observed_date == row.observed_date
        ),
        None,
    )
    if current_index is None or current_index < lookback_observations:
        return None
    return asof_history[current_index - lookback_observations]


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
        details={name: None},
    )


def _missing_market_signal_count(
    *,
    features: dict[str, _SymbolFeatures],
    market_series: dict[str, MarketSeriesObservation | None],
) -> int:
    missing_count = 0
    if features["^VVIX"].price_date is None:
        missing_count += 1
    if (
        features["^VIX9D"].price_date is None
        or features["^VIX3M"].price_date is None
        or (
            _aligned_ratio(features["^VIX9D"], features["^VIX"]) is None
            and _aligned_ratio(features["^VIX"], features["^VIX3M"]) is None
        )
    ):
        missing_count += 1
    if features["$S5FI"].price_date is None or features["$S5TH"].price_date is None:
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


def _component_value(
    snapshot: RegimeSnapshot,
    component_name: str,
    *,
    features: dict[str, _SymbolFeatures],
) -> str:
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
    extension_memory: RegimeExtensionMemory | None = None,
) -> RegimeActionState:
    """Derive rare-action state from setup pressure and turn evidence."""

    stretch_evidence = _stretch_evidence(snapshot=snapshot, signals=signals)
    washout_evidence = _washout_evidence(snapshot=snapshot, signals=signals)
    action_features = _action_features(snapshot=snapshot, signals=signals)
    action_modules = _action_modules(action_features)
    deterioration_score = _action_module_average(
        action_modules,
        field_name="deterioration_score",
    )
    stabilization_score = _action_module_average(
        action_modules,
        field_name="stabilization_score",
    )
    stretch_setup_score = _action_setup_score(
        snapshot.stretch_pressure_score,
        fallback_evidence_count=len(stretch_evidence),
    )
    extension_setup_score = (
        _action_setup_score(
            snapshot.extension_setup_score,
            fallback_evidence_count=len(stretch_evidence),
        )
        if snapshot.extension_setup_score is not None
        else stretch_setup_score
    )
    fragility_context_score = (
        _action_setup_score(
            snapshot.fragility_context_score,
            fallback_evidence_count=0,
        )
        if snapshot.fragility_context_score is not None
        else 0.0
    )
    washout_setup_score = (
        _action_setup_score(
            snapshot.washout_setup_score,
            fallback_evidence_count=len(washout_evidence),
        )
        if snapshot.washout_setup_score is not None
        else _action_setup_score(
            snapshot.washout_pressure_score,
            fallback_evidence_count=len(washout_evidence),
        )
    )
    stretch_score = _action_setup_bucket(stretch_setup_score)
    washout_score = _action_setup_bucket(washout_setup_score)
    extension_memory = extension_memory or _current_only_extension_memory(
        snapshot=snapshot,
        extension_setup_score=extension_setup_score,
    )
    protect_gate = _protect_gate_result(
        extension_setup_score=extension_setup_score,
        extension_memory=extension_memory,
        fragility_context_score=fragility_context_score,
        deterioration_score=deterioration_score,
        action_modules=action_modules,
    )
    protect_strength = max(
        protect_gate.extension_strength,
        protect_gate.regime_break_strength,
    )
    redeploy_strength = math.sqrt(washout_setup_score * stabilization_score)
    action_score = redeploy_strength - protect_strength
    severe_funding_stress = _severe_funding_stress(signals)

    if (
        redeploy_strength >= ACTION_STRENGTH_THRESHOLD
        and redeploy_strength - protect_strength >= ACTION_STRENGTH_MARGIN
        and severe_funding_stress
    ):
        state = "no_change"
        action_path = None
        evidence = _action_feature_evidence(
            action_features,
            field_name="stabilization_score",
        )
        reason = "Redeploy setup present, but credit and liquidity stress block aggressive re-risk"
    elif (
        redeploy_strength >= ACTION_STRENGTH_THRESHOLD
        and redeploy_strength - protect_strength >= ACTION_STRENGTH_MARGIN
    ):
        state = "scale_up_redeploy"
        action_path = "redeploy"
        evidence = _action_feature_evidence(
            action_features,
            field_name="stabilization_score",
        )
        reason = "Washout setup plus stabilization evidence supports staged redeploy"
    elif (
        protect_gate.path is not None
        and protect_strength - redeploy_strength >= ACTION_STRENGTH_MARGIN
    ):
        state = "scale_down_protect"
        action_path = protect_gate.path
        evidence = _action_feature_evidence(
            action_features,
            field_name="deterioration_score",
        ) + _protect_gate_evidence(protect_gate)
        reason = f"{protect_gate.path} protect: {protect_gate.reason}"
    elif protect_gate.warning_only and protect_strength >= ACTION_STRENGTH_THRESHOLD:
        state = "no_change"
        action_path = "volatility_only_warning"
        evidence = _action_feature_evidence(
            action_features,
            field_name="deterioration_score",
        ) + _protect_gate_evidence(protect_gate)
        reason = protect_gate.reason
    elif max(stretch_setup_score, washout_setup_score) >= 0.65:
        state = "no_change"
        action_path = None
        evidence = stretch_evidence + washout_evidence
        reason = "Setup pressure present, but broad confirmation is not strong enough"
    else:
        state = "no_change"
        action_path = None
        evidence = stretch_evidence + washout_evidence
        reason = "No actionable setup; maintain current posture"
    event_volatility_context = _event_volatility_context(
        signals=signals,
        protect_gate=protect_gate,
    )

    return RegimeActionState(
        source_date=snapshot.source_date,
        action_version=REGIME_ACTION_VERSION,
        state=state,
        stretch_score=stretch_score,
        washout_score=washout_score,
        confidence=_action_confidence(
            state=state,
            protect_strength=protect_strength,
            redeploy_strength=redeploy_strength,
            signals=signals,
            action_features=action_features,
        ),
        reason=_action_reason(reason=reason, evidence=evidence),
        evidence=evidence,
        deterioration_score=deterioration_score,
        stabilization_score=stabilization_score,
        protect_strength=protect_strength,
        redeploy_strength=redeploy_strength,
        action_score=action_score,
        action_path=action_path,
        event_volatility_context=event_volatility_context,
        extension_memory_status=extension_memory.status,
        extension_armed=extension_memory.armed,
        extension_armed_since=extension_memory.armed_since,
        extension_armed_age=extension_memory.armed_age,
        extension_armed_decay=extension_memory.armed_decay,
        extension_armed_source_strength=extension_memory.armed_source_strength,
        extension_memory_score=extension_memory.effective_score,
        extension_memory_snapshot_count=extension_memory.snapshot_count,
        action_features=action_features,
        action_modules=action_modules,
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
        deterioration_score=action.deterioration_score,
        stabilization_score=action.stabilization_score,
        protect_strength=action.protect_strength,
        redeploy_strength=action.redeploy_strength,
        action_score=action.action_score,
        action_confidence=action.confidence,
        action_reason=action.reason,
        action_path=action.action_path,
        event_volatility_context=action.event_volatility_context,
        extension_memory_status=action.extension_memory_status,
        extension_armed=action.extension_armed,
        extension_armed_since=action.extension_armed_since,
        extension_armed_age=action.extension_armed_age,
        extension_armed_decay=action.extension_armed_decay,
        extension_armed_source_strength=action.extension_armed_source_strength,
        extension_memory_score=action.extension_memory_score,
        extension_memory_snapshot_count=action.extension_memory_snapshot_count,
        action_features=action.action_features,
        action_modules=action.action_modules,
    )


def _action_setup_score(
    pressure_score: float | None,
    *,
    fallback_evidence_count: int,
) -> float:
    if pressure_score is not None:
        return _clamp(pressure_score, 0.0, 1.0)
    return _clamp(fallback_evidence_count / 5.0, 0.0, 1.0)


def _action_setup_bucket(score: float) -> int:
    return int(round(_clamp(score, 0.0, 1.0) * 5))


def _action_module_average(
    modules: tuple[RegimeActionModule, ...],
    *,
    field_name: str,
) -> float:
    scores = tuple(
        score
        for score in sorted((getattr(module, field_name) for module in modules), reverse=True)
        if score > 0.0
    )
    if not scores:
        return 0.0
    top_scores = scores[:3]
    return sum(top_scores) / len(top_scores)


def _action_feature_evidence(
    features: tuple[RegimeActionFeature, ...],
    *,
    field_name: str,
) -> tuple[str, ...]:
    return tuple(
        feature.reason
        for feature in sorted(features, key=lambda item: getattr(item, field_name), reverse=True)
        if getattr(feature, field_name) >= 0.25
    )


def _current_only_extension_memory(
    *,
    snapshot: RegimeSnapshot,
    extension_setup_score: float,
) -> RegimeExtensionMemory:
    armed = extension_setup_score >= ACTION_EXTENSION_SETUP_THRESHOLD
    return RegimeExtensionMemory(
        source_date=snapshot.source_date,
        status="current_only",
        armed=armed,
        armed_since=snapshot.source_date if armed else None,
        armed_age=0 if armed else None,
        armed_decay=1.0 if armed else None,
        armed_source_strength=extension_setup_score if armed else None,
        effective_score=extension_setup_score,
        snapshot_count=1,
    )


def extension_memory_rows_from_snapshots(
    snapshots: tuple[RegimeSnapshot, ...],
) -> dict[date, RegimeExtensionMemory]:
    """Return extension-unwind setup memory for an ordered snapshot chain."""

    currently_elevated = False
    armed_since: date | None = None
    armed_index: int | None = None
    source_strength: float | None = None
    rows: dict[date, RegimeExtensionMemory] = {}
    for index, snapshot in enumerate(sorted(snapshots, key=lambda item: item.source_date)):
        setup_score = _optional_clamped_score(snapshot.extension_setup_score)
        if _armed_extension_setup_active(setup_score):
            if not currently_elevated:
                armed_since = snapshot.source_date
                armed_index = index
                source_strength = setup_score
            currently_elevated = True
        else:
            currently_elevated = False
            if (
                armed_index is not None
                and index - armed_index > ACTION_EXTENSION_ARMED_MAX_AGE_DAYS
            ):
                armed_since = None
                armed_index = None
                source_strength = None

        age = index - armed_index if armed_index is not None else None
        is_armed = age is not None and age <= ACTION_EXTENSION_ARMED_MAX_AGE_DAYS
        decay = (
            max(0.0, 1.0 - age / ACTION_EXTENSION_ARMED_MAX_AGE_DAYS)
            if is_armed and age is not None
            else None
        )
        rows[snapshot.source_date] = RegimeExtensionMemory(
            source_date=snapshot.source_date,
            status="armed" if is_armed else "unarmed",
            armed=is_armed,
            armed_since=armed_since,
            armed_age=age,
            armed_decay=decay,
            armed_source_strength=source_strength,
            effective_score=_extension_memory_effective_score(
                current_setup_score=setup_score,
                armed=is_armed,
                armed_source_strength=source_strength,
                armed_decay=decay,
            ),
            snapshot_count=index + 1,
        )
    return rows


def _extension_memory_from_snapshot_chain(
    *,
    snapshot: RegimeSnapshot,
    prior_snapshots: tuple[RegimeSnapshot, ...],
    require_prior_history: bool,
) -> RegimeExtensionMemory:
    prior_chain = tuple(
        item
        for item in sorted(prior_snapshots, key=lambda prior: prior.source_date)
        if item.source_date < snapshot.source_date
        and item.signal_time == snapshot.signal_time
        and item.snapshot_version == snapshot.snapshot_version
    )
    if require_prior_history and not prior_chain:
        raise RegimeError(
            _missing_extension_memory_history_message(
                source_date=snapshot.source_date,
                snapshot_version=snapshot.snapshot_version,
            )
        )
    chain = (*prior_chain[-ACTION_EXTENSION_ARMED_MAX_AGE_DAYS:], snapshot)
    rows = extension_memory_rows_from_snapshots(chain)
    memory = rows[snapshot.source_date]
    if not prior_chain and not memory.armed:
        return RegimeExtensionMemory(
            source_date=memory.source_date,
            status="initializing",
            armed=memory.armed,
            armed_since=memory.armed_since,
            armed_age=memory.armed_age,
            armed_decay=memory.armed_decay,
            armed_source_strength=memory.armed_source_strength,
            effective_score=memory.effective_score,
            snapshot_count=memory.snapshot_count,
        )
    return memory


def _optional_clamped_score(score: float | None) -> float | None:
    if score is None:
        return None
    return _clamp(score, 0.0, 1.0)


def _extension_memory_effective_score(
    *,
    current_setup_score: float | None,
    armed: bool,
    armed_source_strength: float | None,
    armed_decay: float | None,
) -> float:
    current_score = _optional_clamped_score(current_setup_score) or 0.0
    if not armed or armed_source_strength is None or armed_decay is None:
        return current_score
    return max(current_score, _clamp(armed_source_strength * armed_decay, 0.0, 1.0))


def _armed_extension_setup_active(setup_score: float | None) -> bool:
    return setup_score is not None and setup_score >= EXTENSION_ARMED_SETUP_THRESHOLD


def _missing_extension_memory_history_message(
    *,
    source_date: date,
    snapshot_version: str | None,
) -> str:
    suggested_start = source_date - timedelta(days=90)
    version_read = snapshot_version or REGIME_SNAPSHOT_VERSION
    return (
        "Missing prior same-version regime snapshots for extension action memory: "
        f"date={source_date.isoformat()} snapshot_version={version_read}. "
        "Run a regime backfill first, for example "
        f"`./bin/marketlab regime backfill --start {suggested_start.isoformat()} "
        f"--end {source_date.isoformat()}`. "
        "Backfill creates the saved snapshot chain used by single-date daily snapshots."
    )


def _extension_memory_reason(memory: RegimeExtensionMemory) -> str:
    if memory.armed_since is None:
        return "extension setup is armed"
    if memory.armed_age is None:
        return f"extension setup was armed on {memory.armed_since.isoformat()}"
    return (
        f"extension setup was armed on {memory.armed_since.isoformat()} "
        f"({memory.armed_age} trading snapshots ago)"
    )


def _protect_gate_result(
    *,
    extension_setup_score: float,
    extension_memory: RegimeExtensionMemory,
    fragility_context_score: float,
    deterioration_score: float,
    action_modules: tuple[RegimeActionModule, ...],
) -> _ProtectGateResult:
    confirming_families = _confirming_families(
        modules=action_modules,
        field_name="deterioration_score",
    )
    non_vol_confirming_families = tuple(
        family for family in confirming_families if family != "volatility"
    )
    extension_strength = math.sqrt(extension_memory.effective_score * deterioration_score)
    regime_break_strength = math.sqrt(fragility_context_score * deterioration_score)
    broad_confirmation = (
        len(confirming_families) >= ACTION_EXTENSION_CONFIRMATION_MIN_FAMILIES
        and bool(non_vol_confirming_families)
    )
    extension_ready = (
        extension_memory.armed
        and extension_strength >= ACTION_STRENGTH_THRESHOLD
        and broad_confirmation
    )
    regime_break_ready = (
        fragility_context_score >= ACTION_REGIME_BREAK_CONTEXT_THRESHOLD
        and regime_break_strength >= ACTION_STRENGTH_THRESHOLD
        and len(non_vol_confirming_families) >= ACTION_REGIME_BREAK_NON_VOL_MIN_FAMILIES
    )
    families_read = _family_list_read(confirming_families)
    non_vol_read = _family_list_read(non_vol_confirming_families)
    if extension_ready:
        return _ProtectGateResult(
            path="extension_unwind",
            extension_strength=extension_strength,
            regime_break_strength=regime_break_strength,
            confirming_families=confirming_families,
            non_vol_confirming_families=non_vol_confirming_families,
            warning_only=False,
            reason=(
                f"{_extension_memory_reason(extension_memory)} and broad deterioration confirms it "
                f"(families {families_read})"
            ),
        )
    if regime_break_ready:
        return _ProtectGateResult(
            path="regime_break",
            extension_strength=extension_strength,
            regime_break_strength=regime_break_strength,
            confirming_families=confirming_families,
            non_vol_confirming_families=non_vol_confirming_families,
            warning_only=False,
            reason=(
                "fragility context plus broad non-vol deterioration bypasses extension setup "
                f"(non-vol families {non_vol_read})"
            ),
        )

    volatility_only = confirming_families == ("volatility",)
    warning_only = volatility_only and (
        extension_strength >= ACTION_STRENGTH_THRESHOLD
        or regime_break_strength >= ACTION_STRENGTH_THRESHOLD
    )
    if warning_only:
        reason = (
            "volatility_only_warning: volatility deterioration is visible, "
            "but normal protect requires non-vol confirmation"
        )
    elif (
        extension_memory.armed
        or max(extension_setup_score, fragility_context_score) >= ACTION_EXTENSION_SETUP_THRESHOLD
    ):
        reason = (
            "protect setup present, but confirmation is not broad enough "
            f"(families {families_read})"
        )
    else:
        reason = "no protect gate passed"
    return _ProtectGateResult(
        path=None,
        extension_strength=extension_strength,
        regime_break_strength=regime_break_strength,
        confirming_families=confirming_families,
        non_vol_confirming_families=non_vol_confirming_families,
        warning_only=warning_only,
        reason=reason,
    )


def _confirming_families(
    *,
    modules: tuple[RegimeActionModule, ...],
    field_name: str,
) -> tuple[str, ...]:
    return tuple(
        module.family
        for module in modules
        if getattr(module, field_name) >= ACTION_CONFIRMATION_THRESHOLD
    )


def _protect_gate_evidence(gate: _ProtectGateResult) -> tuple[str, ...]:
    if not gate.confirming_families:
        return ()
    evidence = (f"confirming families {_family_list_read(gate.confirming_families)}",)
    if gate.non_vol_confirming_families:
        evidence += (
            "non-vol families "
            f"{_family_list_read(gate.non_vol_confirming_families)}",
        )
    return evidence


def _event_volatility_context(
    *,
    signals: tuple[MarketSignal, ...],
    protect_gate: _ProtectGateResult,
) -> str:
    term_signal = _signal_by_name(signals, family="volatility", name="term_structure")
    vix9d_vix_ratio = _signal_detail_float(term_signal, "vix9d_vix_ratio")
    vix_vix3m_ratio = _signal_detail_float(term_signal, "vix_vix3m_ratio")
    vix9d_vix_change_5d = _signal_detail_float(term_signal, "vix9d_vix_ratio_change_5d")
    near_term_premium = (
        (_ge(vix9d_vix_ratio, 1.00) or _ge(vix9d_vix_change_5d, 0.05))
        and not _ge(vix_vix3m_ratio, 1.00)
    )
    if near_term_premium and protect_gate.non_vol_confirming_families:
        return "near_term_event_premium_with_confirmation"
    if near_term_premium:
        return "near_term_event_premium"
    if protect_gate.warning_only:
        return "volatility_only_warning"
    return "none"


def _family_list_read(families: tuple[str, ...]) -> str:
    if not families:
        return "none"
    return ",".join(families)


_ACTION_MODULE_SPECS = (
    ("trend", "trend_turn"),
    ("volatility", "volatility_turn"),
    ("breadth", "breadth_turn"),
    ("credit", "credit_turn"),
    ("liquidity", "liquidity_turn"),
)


def _action_modules(features: tuple[RegimeActionFeature, ...]) -> tuple[RegimeActionModule, ...]:
    return tuple(
        module
        for family, name in _ACTION_MODULE_SPECS
        if (
            module := _action_module(
                family=family,
                name=name,
                features=tuple(feature for feature in features if feature.family == family),
            )
        )
        is not None
    )


def _action_module(
    *,
    family: str,
    name: str,
    features: tuple[RegimeActionFeature, ...],
) -> RegimeActionModule | None:
    if not features:
        return None

    active_features = tuple(
        feature
        for feature in features
        if feature.deterioration_score > 0.0 or feature.stabilization_score > 0.0
    )
    feature_names = tuple(feature.name for feature in active_features)
    reason = (
        ", ".join(
            f"{feature.evidence_kind}:{feature.name}" for feature in active_features
        )
        if active_features
        else "No active action evidence"
    )
    return RegimeActionModule(
        family=family,
        name=name,
        deterioration_score=_action_feature_score(features, field_name="deterioration_score"),
        stabilization_score=_action_feature_score(features, field_name="stabilization_score"),
        feature_count=len(active_features),
        feature_names=feature_names,
        reason=reason,
    )


def _action_feature_score(
    features: tuple[RegimeActionFeature, ...],
    *,
    field_name: str,
) -> float:
    scores = tuple(
        score
        for score in sorted((getattr(feature, field_name) for feature in features), reverse=True)
        if score > 0.0
    )
    if not scores:
        return 0.0
    top_scores = scores[:3]
    return sum(top_scores) / len(top_scores)


def _action_features(
    *,
    snapshot: RegimeSnapshot,
    signals: tuple[MarketSignal, ...],
) -> tuple[RegimeActionFeature, ...]:
    features = [
        _trend_turn_feature(snapshot=snapshot),
        _vix_turn_feature(signals=signals),
        _vvix_turn_feature(snapshot=snapshot, signals=signals),
        _vix_term_structure_turn_feature(signals=signals),
        _breadth_turn_feature(signals=signals),
        _hyg_tlt_turn_feature(signals=signals),
        _credit_spread_turn_feature(signals=signals),
        _financial_conditions_turn_feature(signals=signals),
        *_paired_turn_features(snapshot=snapshot, signals=signals),
    ]
    return tuple(feature for feature in features if feature is not None)


def _trend_turn_feature(*, snapshot: RegimeSnapshot) -> RegimeActionFeature | None:
    deterioration = _average_scores(
        (
            _negative_change_score(snapshot.spy_return_20d, full_at=0.08),
            _negative_change_score(snapshot.qqq_return_20d, full_at=0.10),
        )
    )
    stabilization = _average_scores(
        (
            _positive_change_score(snapshot.spy_return_20d, full_at=0.08),
            _positive_change_score(snapshot.qqq_return_20d, full_at=0.10),
        )
    )
    if deterioration is None and stabilization is None:
        return None
    return RegimeActionFeature(
        family="trend",
        name="short_momentum",
        deterioration_score=deterioration or 0.0,
        stabilization_score=stabilization or 0.0,
        reason=(
            "SPY/QQQ 20d momentum "
            f"{_format_percent(snapshot.spy_return_20d)}/{_format_percent(snapshot.qqq_return_20d)}"
        ),
    )


def _vix_turn_feature(*, signals: tuple[MarketSignal, ...]) -> RegimeActionFeature | None:
    signal = _signal_by_name(signals, family="volatility", name="price_proxy")
    vix_return_5d = _signal_detail_float(signal, "vix_return_5d")
    if vix_return_5d is None:
        return None
    vix_change_5d = _signal_detail_float(signal, "vix_change_5d")
    return RegimeActionFeature(
        family="volatility",
        name="vix_turn",
        deterioration_score=_positive_change_score(vix_return_5d, full_at=0.15),
        stabilization_score=_negative_change_score(vix_return_5d, full_at=0.15),
        reason=f"VIX 5d chg {_format_change_with_percent(vix_change_5d, vix_return_5d)}",
    )


def _vvix_turn_feature(
    *,
    snapshot: RegimeSnapshot,
    signals: tuple[MarketSignal, ...],
) -> RegimeActionFeature | None:
    signal = _signal_by_name(signals, family="volatility", name="vol_of_vol")
    vvix_return_5d = _signal_detail_float(signal, "vvix_return_5d")
    if vvix_return_5d is None:
        return None
    vvix_change_5d = _signal_detail_float(signal, "vvix_change_5d")
    quiet_market_boost = (
        1.2 if snapshot.vix_close is not None and snapshot.vix_close <= 16.0 else 1.0
    )
    raw_deterioration = _positive_change_score(vvix_return_5d, full_at=0.12) or 0.0
    deterioration = _clamp(
        raw_deterioration * quiet_market_boost,
        0.0,
        1.0,
    )
    return RegimeActionFeature(
        family="volatility",
        name="vvix_turn",
        deterioration_score=deterioration,
        stabilization_score=_negative_change_score(vvix_return_5d, full_at=0.12),
        reason=f"VVIX 5d chg {_format_change_with_percent(vvix_change_5d, vvix_return_5d)}",
    )


def _vix_term_structure_turn_feature(
    *,
    signals: tuple[MarketSignal, ...],
) -> RegimeActionFeature | None:
    signal = _signal_by_name(signals, family="volatility", name="term_structure")
    vix9d_vix_change_5d = _signal_detail_float(signal, "vix9d_vix_ratio_change_5d")
    vix_vix3m_change_5d = _signal_detail_float(signal, "vix_vix3m_ratio_change_5d")
    deterioration = _average_scores(
        (
            _positive_change_score(vix9d_vix_change_5d, full_at=0.10),
            _positive_change_score(vix_vix3m_change_5d, full_at=0.08),
        )
    )
    stabilization = _average_scores(
        (
            _negative_change_score(vix9d_vix_change_5d, full_at=0.10),
            _negative_change_score(vix_vix3m_change_5d, full_at=0.08),
        )
    )
    if deterioration is None and stabilization is None:
        return None
    return RegimeActionFeature(
        family="volatility",
        name="term_structure_turn",
        deterioration_score=deterioration or 0.0,
        stabilization_score=stabilization or 0.0,
        reason=(
            "VIX term-ratio 5d chg "
            f"{_format_signed_decimal(vix9d_vix_change_5d)}/"
            f"{_format_signed_decimal(vix_vix3m_change_5d)}"
        ),
    )


def _breadth_turn_feature(*, signals: tuple[MarketSignal, ...]) -> RegimeActionFeature | None:
    proxy_signal = _signal_by_name(signals, family="breadth", name="price_proxy")
    participation_signal = _signal_by_name(signals, family="breadth", name="participation")
    rsp_relative_5d = _signal_detail_float(proxy_signal, "rsp_spy_relative_5d")
    iwm_relative_5d = _signal_detail_float(proxy_signal, "iwm_spy_relative_5d")
    above_50d_change_5d = _signal_detail_float(
        participation_signal,
        "sp500_above_50d_change_5d",
    )
    above_200d_change_5d = _signal_detail_float(
        participation_signal,
        "sp500_above_200d_change_5d",
    )
    deterioration = _average_scores(
        (
            _negative_change_score(rsp_relative_5d, full_at=0.025),
            _negative_change_score(iwm_relative_5d, full_at=0.035),
            _negative_change_score(above_50d_change_5d, full_at=8.0),
            _negative_change_score(above_200d_change_5d, full_at=5.0),
        )
    )
    stabilization = _average_scores(
        (
            _positive_change_score(rsp_relative_5d, full_at=0.025),
            _positive_change_score(iwm_relative_5d, full_at=0.035),
            _positive_change_score(above_50d_change_5d, full_at=8.0),
            _positive_change_score(above_200d_change_5d, full_at=5.0),
        )
    )
    if deterioration is None and stabilization is None:
        return None
    return RegimeActionFeature(
        family="breadth",
        name="participation_turn",
        deterioration_score=deterioration or 0.0,
        stabilization_score=stabilization or 0.0,
        reason=(
            "Breadth 5d turns "
            f"RSP/SPY {_format_percent(rsp_relative_5d)}, "
            f"IWM/SPY {_format_percent(iwm_relative_5d)}, "
            f"SPX >50d {_format_points(above_50d_change_5d)}, "
            f"SPX >200d {_format_points(above_200d_change_5d)}"
        ),
    )


def _hyg_tlt_turn_feature(*, signals: tuple[MarketSignal, ...]) -> RegimeActionFeature | None:
    signal = _signal_by_name(signals, family="credit", name="price_proxy")
    relative_5d = _signal_detail_float(signal, "hyg_tlt_relative_5d")
    if relative_5d is None:
        return None
    return RegimeActionFeature(
        family="credit",
        name="hyg_tlt_turn",
        deterioration_score=_negative_change_score(relative_5d, full_at=0.03),
        stabilization_score=_positive_change_score(relative_5d, full_at=0.03),
        reason=f"HYG/TLT 5d relative move {_format_percent(relative_5d)}",
    )


def _credit_spread_turn_feature(*, signals: tuple[MarketSignal, ...]) -> RegimeActionFeature | None:
    signal = _signal_by_name(signals, family="credit", name="credit_spread")
    change_5d = _signal_detail_float(signal, "credit_spread_change_5d")
    if change_5d is None:
        return None
    return RegimeActionFeature(
        family="credit",
        name="credit_spread_turn",
        deterioration_score=_positive_change_score(change_5d, full_at=0.30),
        stabilization_score=_negative_change_score(change_5d, full_at=0.30),
        reason=f"HY OAS 5d change {change_5d:+.2f}pp",
    )


def _financial_conditions_turn_feature(
    *,
    signals: tuple[MarketSignal, ...],
) -> RegimeActionFeature | None:
    signal = _signal_by_name(signals, family="liquidity", name="financial_conditions")
    change_4w = _signal_detail_float(signal, "financial_conditions_change_4w")
    if change_4w is None:
        return None
    return RegimeActionFeature(
        family="liquidity",
        name="financial_conditions_turn",
        deterioration_score=_positive_change_score(change_4w, full_at=0.15),
        stabilization_score=_negative_change_score(change_4w, full_at=0.15),
        reason=f"NFCI 4w change {change_4w:+.2f}",
    )


def _paired_turn_features(
    *,
    snapshot: RegimeSnapshot,
    signals: tuple[MarketSignal, ...],
) -> tuple[RegimeActionFeature, ...]:
    features = (
        _vvix_vs_vix_feature(snapshot=snapshot, signals=signals),
        _volatility_normalization_confirmation_feature(signals=signals),
        _price_breadth_divergence_feature(snapshot=snapshot, signals=signals),
        _equity_credit_divergence_feature(snapshot=snapshot, signals=signals),
        _breadth_credit_confirmation_feature(signals=signals),
        _rebound_not_confirmed_by_credit_feature(snapshot=snapshot, signals=signals),
    )
    return tuple(feature for feature in features if feature is not None)


def _vvix_vs_vix_feature(
    *,
    snapshot: RegimeSnapshot,
    signals: tuple[MarketSignal, ...],
) -> RegimeActionFeature | None:
    vix_signal = _signal_by_name(signals, family="volatility", name="price_proxy")
    vvix_signal = _signal_by_name(signals, family="volatility", name="vol_of_vol")
    vix_return_5d = _signal_detail_float(vix_signal, "vix_return_5d")
    vvix_return_5d = _signal_detail_float(vvix_signal, "vvix_return_5d")
    if vvix_return_5d is None:
        return None

    low_vix_score = (
        _positive_change_score(vvix_return_5d, full_at=0.12)
        if _le(snapshot.vix_close, 16.0)
        else None
    )
    relative_score = None
    relative_change = None
    if vix_return_5d is not None:
        relative_change = vvix_return_5d - vix_return_5d
        relative_score = _positive_change_score(relative_change, full_at=0.12)
    deterioration = _max_scores((low_vix_score, relative_score)) or 0.0
    high_vix_score = _high_vix_context_score(snapshot.vix_close)
    vvix_cooling_score = _negative_change_score(vvix_return_5d, full_at=0.12)
    stabilization = _gated_score(high_vix_score, vvix_cooling_score)
    return RegimeActionFeature(
        family="volatility",
        name="vvix_vs_vix",
        deterioration_score=deterioration,
        stabilization_score=stabilization,
        evidence_kind="divergence",
        reason=(
            "VVIX vs VIX 5d "
            f"{_format_percent(vvix_return_5d)}/{_format_percent(vix_return_5d)}; "
            f"lead {_format_percent(relative_change)}; VIX {_format_index(snapshot.vix_close)}; "
            f"high-VIX gate {_format_pressure_score(high_vix_score)}"
        ),
    )


def _volatility_normalization_confirmation_feature(
    *,
    signals: tuple[MarketSignal, ...],
) -> RegimeActionFeature | None:
    vvix_signal = _signal_by_name(signals, family="volatility", name="vol_of_vol")
    term_signal = _signal_by_name(signals, family="volatility", name="term_structure")
    vvix_return_5d = _signal_detail_float(vvix_signal, "vvix_return_5d")
    vix9d_vix_change_5d = _signal_detail_float(term_signal, "vix9d_vix_ratio_change_5d")
    vix_vix3m_change_5d = _signal_detail_float(term_signal, "vix_vix3m_ratio_change_5d")
    term_score = _average_scores(
        (
            _negative_change_score(vix9d_vix_change_5d, full_at=0.10),
            _negative_change_score(vix_vix3m_change_5d, full_at=0.08),
        )
    )
    if vvix_return_5d is None and term_score is None:
        return None
    vvix_gate = _vvix_not_rising_gate(vvix_return_5d)
    stabilization = _gated_score(vvix_gate, term_score)
    return RegimeActionFeature(
        family="volatility",
        name="volatility_normalization_confirmation",
        deterioration_score=0.0,
        stabilization_score=stabilization,
        evidence_kind="confirmation",
        reason=(
            "VIX term-ratio 5d chg "
            f"{_format_signed_decimal(vix9d_vix_change_5d)}/"
            f"{_format_signed_decimal(vix_vix3m_change_5d)}; "
            f"VVIX gate {_format_pressure_score(vvix_gate)} "
            f"({_format_percent(vvix_return_5d)})"
        ),
    )


def _price_breadth_divergence_feature(
    *,
    snapshot: RegimeSnapshot,
    signals: tuple[MarketSignal, ...],
) -> RegimeActionFeature | None:
    price_score = _price_stable_or_rising_score(snapshot)
    breadth_damage = _breadth_deterioration_score(signals)
    if price_score is None and breadth_damage is None:
        return None
    deterioration = _gated_score(price_score, breadth_damage)
    return RegimeActionFeature(
        family="breadth",
        name="price_breadth_divergence",
        deterioration_score=deterioration,
        stabilization_score=0.0,
        evidence_kind="divergence",
        reason=(
            "SPY/QQQ stable while breadth weakens: "
            f"price gate {_format_pressure_score(price_score)}, "
            f"breadth damage {_format_pressure_score(breadth_damage)}"
        ),
    )


def _equity_credit_divergence_feature(
    *,
    snapshot: RegimeSnapshot,
    signals: tuple[MarketSignal, ...],
) -> RegimeActionFeature | None:
    price_score = _price_stable_or_rising_score(snapshot)
    credit_damage = _credit_liquidity_deterioration_score(signals)
    if price_score is None and credit_damage is None:
        return None
    deterioration = _gated_score(price_score, credit_damage)
    return RegimeActionFeature(
        family="credit",
        name="equity_credit_divergence",
        deterioration_score=deterioration,
        stabilization_score=0.0,
        evidence_kind="divergence",
        reason=(
            "SPY/QQQ stable while credit/liquidity weakens: "
            f"price gate {_format_pressure_score(price_score)}, "
            f"funding damage {_format_pressure_score(credit_damage)}"
        ),
    )


def _breadth_credit_confirmation_feature(
    *,
    signals: tuple[MarketSignal, ...],
) -> RegimeActionFeature | None:
    breadth_recovery = _breadth_recovery_score(signals)
    funding_recovery = _credit_liquidity_stabilization_score(signals)
    if breadth_recovery is None and funding_recovery is None:
        return None
    stabilization = _gated_score(breadth_recovery, funding_recovery)
    return RegimeActionFeature(
        family="credit",
        name="breadth_credit_confirmation",
        deterioration_score=0.0,
        stabilization_score=stabilization,
        evidence_kind="confirmation",
        reason=(
            "Breadth and credit/liquidity recovery: "
            f"breadth {_format_pressure_score(breadth_recovery)}, "
            f"funding {_format_pressure_score(funding_recovery)}"
        ),
    )


def _rebound_not_confirmed_by_credit_feature(
    *,
    snapshot: RegimeSnapshot,
    signals: tuple[MarketSignal, ...],
) -> RegimeActionFeature | None:
    price_rebound = _price_stable_or_rising_score(snapshot)
    breadth_recovery = _breadth_recovery_score(signals)
    rebound_score = _max_scores((price_rebound, breadth_recovery))
    credit_damage = _credit_liquidity_deterioration_score(signals)
    if rebound_score is None and credit_damage is None:
        return None
    contradiction = _gated_score(rebound_score, credit_damage) * 0.5
    return RegimeActionFeature(
        family="credit",
        name="rebound_not_confirmed_by_credit",
        deterioration_score=contradiction,
        stabilization_score=0.0,
        evidence_kind="contradiction",
        reason=(
            "Rebound lacks credit/liquidity confirmation: "
            f"rebound {_format_pressure_score(rebound_score)}, "
            f"funding damage {_format_pressure_score(credit_damage)}"
        ),
    )


def _price_stable_or_rising_score(snapshot: RegimeSnapshot) -> float | None:
    price_return = _average((snapshot.spy_return_20d, snapshot.qqq_return_20d))
    if price_return is None:
        return None
    return 1.0 if price_return >= 0.0 else 0.0


def _high_vix_context_score(vix_close: float | None) -> float | None:
    if vix_close is None:
        return None
    if vix_close <= 20.0:
        return 0.0
    return _clamp((vix_close - 20.0) / 10.0, 0.0, 1.0)


def _vvix_not_rising_gate(vvix_return_5d: float | None) -> float | None:
    if vvix_return_5d is None:
        return None
    return 1.0 if vvix_return_5d <= 0.0 else 0.0


def _breadth_deterioration_score(signals: tuple[MarketSignal, ...]) -> float | None:
    proxy_signal = _signal_by_name(signals, family="breadth", name="price_proxy")
    participation_signal = _signal_by_name(signals, family="breadth", name="participation")
    return _average_scores(
        (
            _negative_change_score(
                _signal_detail_float(proxy_signal, "rsp_spy_relative_5d"),
                full_at=0.025,
            ),
            _negative_change_score(
                _signal_detail_float(proxy_signal, "iwm_spy_relative_5d"),
                full_at=0.035,
            ),
            _negative_change_score(
                _signal_detail_float(participation_signal, "sp500_above_50d_change_5d"),
                full_at=8.0,
            ),
            _negative_change_score(
                _signal_detail_float(participation_signal, "sp500_above_200d_change_5d"),
                full_at=5.0,
            ),
        )
    )


def _breadth_recovery_score(signals: tuple[MarketSignal, ...]) -> float | None:
    proxy_signal = _signal_by_name(signals, family="breadth", name="price_proxy")
    participation_signal = _signal_by_name(signals, family="breadth", name="participation")
    return _average_scores(
        (
            _positive_change_score(
                _signal_detail_float(proxy_signal, "rsp_spy_relative_5d"),
                full_at=0.025,
            ),
            _positive_change_score(
                _signal_detail_float(proxy_signal, "iwm_spy_relative_5d"),
                full_at=0.035,
            ),
            _positive_change_score(
                _signal_detail_float(participation_signal, "sp500_above_50d_change_5d"),
                full_at=8.0,
            ),
            _positive_change_score(
                _signal_detail_float(participation_signal, "sp500_above_200d_change_5d"),
                full_at=5.0,
            ),
        )
    )


def _credit_liquidity_deterioration_score(signals: tuple[MarketSignal, ...]) -> float | None:
    credit_proxy = _signal_by_name(signals, family="credit", name="price_proxy")
    credit_spread = _signal_by_name(signals, family="credit", name="credit_spread")
    liquidity = _signal_by_name(signals, family="liquidity", name="financial_conditions")
    return _average_scores(
        (
            _negative_change_score(
                _signal_detail_float(credit_proxy, "hyg_tlt_relative_5d"),
                full_at=0.03,
            ),
            _positive_change_score(
                _signal_detail_float(credit_spread, "credit_spread_change_5d"),
                full_at=0.30,
            ),
            _positive_change_score(
                _signal_detail_float(liquidity, "financial_conditions_change_4w"),
                full_at=0.15,
            ),
        )
    )


def _credit_liquidity_stabilization_score(signals: tuple[MarketSignal, ...]) -> float | None:
    credit_proxy = _signal_by_name(signals, family="credit", name="price_proxy")
    credit_spread = _signal_by_name(signals, family="credit", name="credit_spread")
    liquidity = _signal_by_name(signals, family="liquidity", name="financial_conditions")
    return _average_scores(
        (
            _positive_change_score(
                _signal_detail_float(credit_proxy, "hyg_tlt_relative_5d"),
                full_at=0.03,
            ),
            _negative_change_score(
                _signal_detail_float(credit_spread, "credit_spread_change_5d"),
                full_at=0.30,
            ),
            _negative_change_score(
                _signal_detail_float(liquidity, "financial_conditions_change_4w"),
                full_at=0.15,
            ),
        )
    )


def _gated_score(first: float | None, second: float | None) -> float:
    if first is None or second is None or first <= 0.0 or second <= 0.0:
        return 0.0
    return math.sqrt(first * second)


def _max_scores(scores: tuple[float | None, ...]) -> float | None:
    clean_scores = tuple(score for score in scores if score is not None)
    if not clean_scores:
        return None
    return max(clean_scores)


def _positive_change_score(value: float | None, *, full_at: float) -> float | None:
    if value is None:
        return None
    if value <= 0.0:
        return 0.0
    return _clamp(value / full_at, 0.0, 1.0)


def _negative_change_score(value: float | None, *, full_at: float) -> float | None:
    if value is None:
        return None
    if value >= 0.0:
        return 0.0
    return _clamp(abs(value) / full_at, 0.0, 1.0)


def _average_scores(scores: tuple[float | None, ...]) -> float | None:
    usable_scores = tuple(score for score in scores if score is not None)
    if not usable_scores:
        return None
    return sum(usable_scores) / len(usable_scores)


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
    protect_strength: float,
    redeploy_strength: float,
    signals: tuple[MarketSignal, ...],
    action_features: tuple[RegimeActionFeature, ...] = (),
) -> str:
    strongest = max(protect_strength, redeploy_strength)
    if state == "no_change":
        confidence = "high" if strongest < 0.35 else "medium"
    else:
        confidence = "high" if strongest >= 0.70 else "medium"

    if not signals:
        return _downgrade_confidence(confidence, steps=1)
    if any(signal.status == "missing" for signal in signals):
        return _downgrade_confidence(confidence, steps=1)
    if state == "scale_up_redeploy" and any(
        feature.evidence_kind == "contradiction" and feature.deterioration_score >= 0.25
        for feature in action_features
    ):
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


def _signal_detail_float(signal: MarketSignal | None, key: str) -> float | None:
    if signal is None:
        return None
    value = signal.details.get(key)
    if value is None or isinstance(value, bool):
        return None
    if not isinstance(value, int | float):
        return None
    return float(value)


def _signal_detail_date(signal: MarketSignal | None, key: str) -> date | None:
    if signal is None:
        return None
    value = signal.details.get(key)
    if value is None or value == "":
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        return None


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


def _missing_symbols_from_signals(signals: tuple[MarketSignal, ...]) -> tuple[str, ...]:
    symbols = {
        str(symbol) for signal in signals for symbol in signal.details.get("missing_symbols", ())
    }
    ordered_symbols = [symbol for symbol in DEFAULT_REGIME_PRICE_SYMBOLS if symbol in symbols]
    ordered_symbols.extend(sorted(symbol for symbol in symbols if symbol not in ordered_symbols))
    return tuple(ordered_symbols)


def _missing_independent_market_signal_count(signals: tuple[MarketSignal, ...]) -> int:
    independent_signals = (
        ("volatility", "vol_of_vol"),
        ("volatility", "term_structure"),
        ("breadth", "participation"),
        ("credit", "credit_spread"),
        ("liquidity", "financial_conditions"),
        ("rates", "yield_curve"),
    )
    return sum(
        1
        for family, name in independent_signals
        if _signal_status(signals, family=family, name=name) == "missing"
    )


def _shared_market_signal_snapshot_version(signals: tuple[MarketSignal, ...]) -> str | None:
    versions = {signal.snapshot_version for signal in signals if signal.snapshot_version}
    if len(versions) == 1:
        return versions.pop()
    if len(versions) > 1:
        return "mixed"
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
    modules = _pressure_modules(source_date=source_date, features=features)
    extension_setup_score = _pressure_score_for_modules(
        modules,
        module_names=("trend_extension", "vol_complacency"),
        field_name="stretch_score",
    )
    fragility_context_score = _pressure_score_for_modules(
        modules,
        module_names=(
            "breadth_fragility",
            "credit_risk_appetite",
            "liquidity_conditions",
            "yield_curve_pressure",
        ),
        field_name="stretch_score",
    )
    washout_setup_score = _aggregate_pressure_score(modules, field_name="washout_score")
    return RegimePressureSnapshot(
        source_date=source_date,
        pressure_version=REGIME_PRESSURE_VERSION,
        stretch_pressure_score=_aggregate_pressure_score(modules, field_name="stretch_score"),
        washout_pressure_score=washout_setup_score,
        extension_setup_score=extension_setup_score,
        fragility_context_score=fragility_context_score,
        washout_setup_score=washout_setup_score,
        confidence=_pressure_confidence(features),
        features=features,
        modules=modules,
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
        extension_setup_score=pressure.extension_setup_score,
        fragility_context_score=pressure.fragility_context_score,
        washout_setup_score=pressure.washout_setup_score,
        pressure_confidence=pressure.confidence,
        pressure_features=pressure.features,
        pressure_modules=pressure.modules,
    )


def _pressure_modules(
    *,
    source_date: date,
    features: tuple[RegimePressureFeature, ...],
) -> tuple[RegimePressureModule, ...]:
    feature_by_name = {feature.name: feature for feature in features}
    return tuple(
        _pressure_module(
            source_date=source_date,
            spec=spec,
            features=tuple(
                feature_by_name[name] for name in spec.feature_names if name in feature_by_name
            ),
        )
        for spec in PRESSURE_MODULE_SPECS
    )


def _pressure_module(
    *,
    source_date: date,
    spec: _PressureModuleSpec,
    features: tuple[RegimePressureFeature, ...],
) -> RegimePressureModule:
    stretch_scores = tuple(
        feature.stretch_score for feature in features if feature.stretch_score is not None
    )
    washout_scores = tuple(
        feature.washout_score for feature in features if feature.washout_score is not None
    )
    usable_names = tuple(
        feature.name
        for feature in features
        if feature.stretch_score is not None or feature.washout_score is not None
    )
    return RegimePressureModule(
        source_date=source_date,
        pressure_version=REGIME_PRESSURE_VERSION,
        family=spec.family,
        name=spec.name,
        stretch_score=_average(stretch_scores),
        washout_score=_average(washout_scores),
        feature_count=len(usable_names),
        feature_names=usable_names,
        reason=spec.reason if usable_names else "No usable module features",
    )


def _pressure_score_for_modules(
    modules: tuple[RegimePressureModule, ...],
    *,
    module_names: tuple[str, ...],
    field_name: str,
) -> float:
    allowed_names = set(module_names)
    return _aggregate_pressure_score(
        tuple(module for module in modules if module.name in allowed_names),
        field_name=field_name,
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

    current_sample = next(
        (sample for sample in reversed(clean_samples) if sample.asof_date == source_date),
        None,
    )
    if current_sample is None:
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
            sample_count=len(clean_samples[-PRESSURE_LOOKBACK_SAMPLES:]),
            reason="No point-in-time value available",
        )

    lookback_samples = clean_samples[-PRESSURE_LOOKBACK_SAMPLES:]
    raw_value = current_sample.value
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
    pressure_rows: tuple[RegimePressureModule, ...],
    *,
    field_name: str,
) -> float:
    family_scores: dict[str, list[float]] = {}
    for row in pressure_rows:
        score = getattr(row, field_name)
        if score is not None:
            family_scores.setdefault(row.family, []).append(score)
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


def _pressure_feature_history_from_signal_rows(
    *,
    signals_by_date: dict[date, tuple[MarketSignal, ...]],
) -> dict[str, tuple[_PressureFeatureSample, ...]]:
    feature_samples: dict[str, list[_PressureFeatureSample]] = {
        spec.name: [] for spec in PRESSURE_FEATURE_SPECS
    }
    for sample_date, signals in sorted(signals_by_date.items()):
        values = _pressure_feature_values_from_signals(signals=signals)
        _append_pressure_feature_samples(
            feature_samples=feature_samples,
            sample_date=sample_date,
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
    vix9d = features.get("^VIX9D", _empty_symbol_features("^VIX9D"))
    vix3m = features.get("^VIX3M", _empty_symbol_features("^VIX3M"))
    vvix = features.get("^VVIX", _empty_symbol_features("^VVIX"))
    sp500_above_50d = features.get("$S5FI", _empty_symbol_features("$S5FI"))
    sp500_above_200d = features.get("$S5TH", _empty_symbol_features("$S5TH"))
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
        "vix9d_vix_ratio": _aligned_ratio(vix9d, vix),
        "vix_vix3m_ratio": _aligned_ratio(vix, vix3m),
        "rsp_spy_relative_20d": _relative_return(rsp, spy),
        "iwm_spy_relative_20d": _relative_return(iwm, spy),
        "sp500_above_50d": sp500_above_50d.close,
        "sp500_above_200d": sp500_above_200d.close,
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
        "vix9d_vix_ratio": snapshot.vix9d_vix_ratio,
        "vix_vix3m_ratio": snapshot.vix_vix3m_ratio,
        "rsp_spy_relative_20d": snapshot.rsp_spy_relative_20d,
        "iwm_spy_relative_20d": snapshot.iwm_spy_relative_20d,
        "sp500_above_50d": snapshot.sp500_above_50d,
        "sp500_above_200d": snapshot.sp500_above_200d,
        "hyg_tlt_relative_20d": snapshot.hyg_tlt_relative_20d,
        "credit_spread": _signal_value(signals, family="credit", name="credit_spread"),
        "financial_conditions": _signal_value(
            signals,
            family="liquidity",
            name="financial_conditions",
        ),
        "yield_curve": _signal_value(signals, family="rates", name="yield_curve"),
    }


def _pressure_feature_values_from_signals(
    *,
    signals: tuple[MarketSignal, ...],
) -> dict[str, float | None]:
    trend = _signal_by_name(signals, family="trend", name="price_proxy")
    volatility = _signal_by_name(signals, family="volatility", name="price_proxy")
    term_structure = _signal_by_name(signals, family="volatility", name="term_structure")
    breadth = _signal_by_name(signals, family="breadth", name="price_proxy")
    participation = _signal_by_name(signals, family="breadth", name="participation")
    credit = _signal_by_name(signals, family="credit", name="price_proxy")
    return {
        "spy_return_20d": _signal_detail_float(trend, "spy_return_20d"),
        "spy_return_60d": _signal_detail_float(trend, "spy_return_60d"),
        "qqq_return_20d": _signal_detail_float(trend, "qqq_return_20d"),
        "spy_ma50_distance": _signal_detail_float(trend, "spy_ma50_distance"),
        "qqq_ma50_distance": _signal_detail_float(trend, "qqq_ma50_distance"),
        "spy_realized_vol_20d": _signal_detail_float(volatility, "spy_realized_vol_20d"),
        "vix_close": _signal_detail_float(volatility, "vix_close"),
        "vvix_close": _signal_value(signals, family="volatility", name="vol_of_vol"),
        "vix9d_vix_ratio": _signal_detail_float(term_structure, "vix9d_vix_ratio"),
        "vix_vix3m_ratio": _signal_detail_float(term_structure, "vix_vix3m_ratio"),
        "rsp_spy_relative_20d": _signal_detail_float(breadth, "rsp_spy_relative_20d"),
        "iwm_spy_relative_20d": _signal_detail_float(breadth, "iwm_spy_relative_20d"),
        "sp500_above_50d": _signal_detail_float(participation, "sp500_above_50d"),
        "sp500_above_200d": _signal_detail_float(participation, "sp500_above_200d"),
        "hyg_tlt_relative_20d": _signal_detail_float(credit, "hyg_tlt_relative_20d"),
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


def derive_regime_postures(
    *,
    snapshots: tuple[RegimeSnapshot, ...],
    spy_history: tuple[DailyPriceObservation, ...] = (),
) -> tuple[RegimePostureState, ...]:
    """Reconstruct held posture from point-in-time regime action events."""

    ordered_snapshots = tuple(sorted(snapshots, key=lambda snapshot: snapshot.source_date))
    posture_state = "neutral"
    posture_start_date: date | None = None
    posture_start_index: int | None = None
    protected_since: date | None = None
    protect_reason: str | None = None
    protect_path: str | None = None
    redeploy_since: date | None = None
    rows: list[RegimePostureState] = []

    for index, snapshot in enumerate(ordered_snapshots):
        reset_reason: str | None = None
        if snapshot.action_state == "scale_down_protect":
            posture_state = "protected"
            posture_start_date = snapshot.source_date
            posture_start_index = index
            protected_since = snapshot.source_date
            protect_reason = snapshot.action_reason
            protect_path = snapshot.action_path or _protect_path_from_reason(
                snapshot.action_reason
            )
            redeploy_since = None
        elif snapshot.action_state == "scale_up_redeploy":
            reset_reason = "redeploy_event" if posture_state == "protected" else None
            posture_state = "redeploying"
            posture_start_date = snapshot.source_date
            posture_start_index = index
            redeploy_since = snapshot.source_date
            protected_since = None
            protect_reason = None
            protect_path = None
        else:
            reset_reason = _posture_reset_reason(
                snapshot=snapshot,
                posture_state=posture_state,
                posture_start_index=posture_start_index,
                snapshot_index=index,
            )
            if reset_reason is not None:
                posture_state = "neutral"
                posture_start_date = None
                posture_start_index = None
                protected_since = None
                protect_reason = None
                protect_path = None
                redeploy_since = None

        posture_age = index - posture_start_index if posture_start_index is not None else None
        rows.append(
            RegimePostureState(
                source_date=snapshot.source_date,
                price_date=snapshot.price_date,
                posture_state=posture_state,
                protected_since=protected_since,
                protect_reason=protect_reason,
                protect_path=protect_path,
                redeploy_since=redeploy_since,
                posture_age=posture_age,
                max_drawdown_since_posture=_posture_max_drawdown(
                    history=spy_history,
                    start_date=posture_start_date,
                    end_date=snapshot.price_date,
                ),
                reset_reason=reset_reason,
            )
        )
    return tuple(rows)


def _protect_path_from_reason(reason: str) -> str | None:
    for path in ("extension_unwind", "regime_break"):
        if reason.startswith(f"{path} protect"):
            return path
    if "volatility_only_warning" in reason:
        return "volatility_only_warning"
    return None


def _posture_reset_reason(
    *,
    snapshot: RegimeSnapshot,
    posture_state: str,
    posture_start_index: int | None,
    snapshot_index: int,
) -> str | None:
    if posture_start_index is None:
        return None
    age = snapshot_index - posture_start_index
    if posture_state == "protected":
        if age >= PROTECTED_POSTURE_MAX_AGE_DAYS:
            return "max_protected_age"
        if _protect_pressure_cleared(snapshot):
            return "protect_pressure_cleared"
    if posture_state == "redeploying":
        if age >= REDEPLOY_POSTURE_MAX_AGE_DAYS:
            return "max_redeploy_age"
        if _redeploy_pressure_cleared(snapshot):
            return "redeploy_pressure_cleared"
    return None


def _protect_pressure_cleared(snapshot: RegimeSnapshot) -> bool:
    return (
        snapshot.protect_strength < POSTURE_CLEAR_THRESHOLD
        and (snapshot.extension_setup_score or 0.0) < ACTION_EXTENSION_SETUP_THRESHOLD
        and (snapshot.fragility_context_score or 0.0) < POSTURE_CLEAR_THRESHOLD
    )


def _redeploy_pressure_cleared(snapshot: RegimeSnapshot) -> bool:
    return (
        snapshot.redeploy_strength < POSTURE_CLEAR_THRESHOLD
        and (snapshot.washout_setup_score or 0.0) < POSTURE_CLEAR_THRESHOLD
    )


def _posture_max_drawdown(
    *,
    history: tuple[DailyPriceObservation, ...],
    start_date: date | None,
    end_date: date | None,
) -> float | None:
    if start_date is None or end_date is None:
        return None
    start_index = _exact_date_index(history, start_date)
    end_index = _exact_date_index(history, end_date)
    if start_index is None or end_index is None or end_index < start_index:
        return None
    start_close = history[start_index].return_close
    if start_close == 0:
        return None
    lows = [row.return_close for row in history[start_index : end_index + 1]]
    if not lows:
        return None
    return min(0.0, min(lows) / start_close - 1.0)


def compute_regime_outcomes(
    *,
    start_date: date,
    end_date: date,
    snapshot_root: Path = DEFAULT_REGIME_SNAPSHOT_ROOT,
    price_root: Path = DEFAULT_PRICE_OBSERVATIONS_ROOT,
    horizons: tuple[int, ...] = DEFAULT_REGIME_OUTCOME_HORIZONS,
    snapshot_version: str | None = None,
) -> RegimeOutcomeResult:
    """Replay forward SPY/QQQ outcomes for saved market regime snapshots."""

    if end_date < start_date:
        raise RegimeError("End date must be on or after start date")

    snapshots = _load_regime_snapshots_in_range(
        start_date=start_date,
        end_date=end_date,
        snapshot_root=snapshot_root,
        snapshot_version=snapshot_version,
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
    snapshot_version: str | None = None,
) -> MarketSignalOutcomeResult:
    """Replay forward SPY/QQQ outcomes for saved market signal rows."""

    if end_date < start_date:
        raise RegimeError("End date must be on or after start date")

    signals = _load_market_signals_in_range(
        start_date=start_date,
        end_date=end_date,
        signal_snapshot_root=signal_snapshot_root,
        snapshot_version=snapshot_version,
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
    snapshot_version: str | None = None,
) -> RegimeActionOutcomeResult:
    """Replay rare-action states against forward SPY/QQQ outcomes."""

    if end_date < start_date:
        raise RegimeError("End date must be on or after start date")

    snapshots = _load_regime_snapshots_in_range(
        start_date=start_date,
        end_date=end_date,
        snapshot_root=snapshot_root,
        snapshot_version=snapshot_version,
    )
    if not snapshots:
        raise RegimeError(f"No market regime snapshots found from {start_date} to {end_date}")

    histories = _load_histories(symbols=("SPY", "QQQ"), price_root=price_root)
    snapshot_actions = tuple(
        (snapshot, _action_state_from_snapshot(snapshot))
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


def _action_state_from_snapshot(snapshot: RegimeSnapshot) -> RegimeActionState:
    return RegimeActionState(
        source_date=snapshot.source_date,
        action_version=snapshot.action_version,
        state=snapshot.action_state,
        stretch_score=snapshot.stretch_score,
        washout_score=snapshot.washout_score,
        confidence=snapshot.action_confidence,
        reason=snapshot.action_reason,
        evidence=(),
        deterioration_score=snapshot.deterioration_score,
        stabilization_score=snapshot.stabilization_score,
        protect_strength=snapshot.protect_strength,
        redeploy_strength=snapshot.redeploy_strength,
        action_score=snapshot.action_score,
        action_path=snapshot.action_path,
        event_volatility_context=snapshot.event_volatility_context,
        extension_memory_status=snapshot.extension_memory_status,
        extension_armed=snapshot.extension_armed,
        extension_armed_since=snapshot.extension_armed_since,
        extension_armed_age=snapshot.extension_armed_age,
        extension_armed_decay=snapshot.extension_armed_decay,
        extension_armed_source_strength=snapshot.extension_armed_source_strength,
        extension_memory_score=snapshot.extension_memory_score,
        extension_memory_snapshot_count=snapshot.extension_memory_snapshot_count,
        action_features=snapshot.action_features,
        action_modules=snapshot.action_modules,
    )


def compute_regime_posture_outcomes(
    *,
    start_date: date,
    end_date: date,
    snapshot_root: Path = DEFAULT_REGIME_SNAPSHOT_ROOT,
    price_root: Path = DEFAULT_PRICE_OBSERVATIONS_ROOT,
    horizons: tuple[int, ...] = DEFAULT_REGIME_OUTCOME_HORIZONS,
    snapshot_version: str | None = None,
) -> RegimePostureOutcomeResult:
    """Replay derived held posture states against forward SPY/QQQ outcomes."""

    if end_date < start_date:
        raise RegimeError("End date must be on or after start date")

    snapshots = _load_regime_snapshots_through(
        end_date=end_date,
        snapshot_root=snapshot_root,
        snapshot_version=snapshot_version,
    )
    target_snapshots = tuple(
        snapshot for snapshot in snapshots if start_date <= snapshot.source_date <= end_date
    )
    if not target_snapshots:
        raise RegimeError(f"No market regime snapshots found from {start_date} to {end_date}")

    histories = _load_histories(symbols=("SPY", "QQQ"), price_root=price_root)
    postures_by_date = {
        posture.source_date: posture
        for posture in derive_regime_postures(
            snapshots=snapshots,
            spy_history=histories.get("SPY", ()),
        )
    }
    target_postures = tuple(
        postures_by_date[snapshot.source_date] for snapshot in target_snapshots
    )
    outcomes = tuple(
        outcome
        for snapshot in target_snapshots
        for outcome in _regime_posture_outcomes(
            snapshot=snapshot,
            posture=postures_by_date[snapshot.source_date],
            histories=histories,
            horizons=horizons,
        )
    )
    frequency_rows = summarize_regime_posture_frequency(target_postures)
    summary_rows = summarize_regime_posture_outcomes(outcomes)
    frequency_table = format_regime_posture_frequency(frequency_rows)
    table = format_regime_posture_outcome_summary(summary_rows)
    logger.bind(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        posture_count=len(target_postures),
        outcome_count=len(outcomes),
    ).success("Computed market regime posture outcomes")
    return RegimePostureOutcomeResult(
        start_date=start_date,
        end_date=end_date,
        postures=target_postures,
        outcomes=outcomes,
        frequency_rows=frequency_rows,
        summary_rows=summary_rows,
        frequency_table=frequency_table,
        table=table,
    )


def compute_regime_redeploy_outcomes(
    *,
    start_date: date,
    end_date: date,
    snapshot_root: Path = DEFAULT_REGIME_SNAPSHOT_ROOT,
    price_root: Path = DEFAULT_PRICE_OBSERVATIONS_ROOT,
    horizons: tuple[int, ...] = DEFAULT_REGIME_OUTCOME_HORIZONS,
    snapshot_version: str | None = None,
) -> RegimeRedeployOutcomeResult:
    """Replay redeploy setup/stabilization buckets against forward outcomes."""

    if end_date < start_date:
        raise RegimeError("End date must be on or after start date")

    snapshots = _load_regime_snapshots_in_range(
        start_date=start_date,
        end_date=end_date,
        snapshot_root=snapshot_root,
        snapshot_version=snapshot_version,
    )
    if not snapshots:
        raise RegimeError(f"No market regime snapshots found from {start_date} to {end_date}")

    histories = _load_histories(symbols=("SPY", "QQQ"), price_root=price_root)
    outcomes = tuple(
        outcome
        for snapshot in snapshots
        for outcome in _regime_redeploy_outcomes(
            snapshot=snapshot,
            histories=histories,
            horizons=horizons,
        )
    )
    summary_rows = summarize_regime_redeploy_outcomes(outcomes)
    table = format_regime_redeploy_outcome_summary(summary_rows)
    logger.bind(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        snapshot_count=len(snapshots),
        outcome_count=len(outcomes),
    ).success("Computed market regime redeploy outcomes")
    return RegimeRedeployOutcomeResult(
        start_date=start_date,
        end_date=end_date,
        outcomes=outcomes,
        summary_rows=summary_rows,
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
    snapshot_version: str | None = None,
) -> RegimePressureOutcomeResult:
    """Replay normalized pressure buckets against forward SPY/QQQ outcomes."""

    if end_date < start_date:
        raise RegimeError("End date must be on or after start date")

    snapshots = _load_regime_snapshots_through(
        end_date=end_date,
        snapshot_root=snapshot_root,
        snapshot_version=snapshot_version,
    )
    target_snapshots = tuple(
        snapshot for snapshot in snapshots if start_date <= snapshot.source_date <= end_date
    )
    if not target_snapshots:
        raise RegimeError(f"No market regime snapshots found from {start_date} to {end_date}")

    signals_by_date = _load_market_signals_by_source_date_through(
        end_date=end_date,
        signal_snapshot_root=signal_snapshot_root,
        snapshot_version=snapshot_version,
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


def compute_regime_correction_episodes(
    *,
    start_date: date,
    end_date: date,
    snapshot_root: Path = DEFAULT_REGIME_SNAPSHOT_ROOT,
    price_root: Path = DEFAULT_PRICE_OBSERVATIONS_ROOT,
    snapshot_version: str | None = None,
    warning_lookback_days: int = DEFAULT_CORRECTION_EPISODE_LOOKBACK_DAYS,
) -> RegimeCorrectionEpisodeResult:
    """Replay current protect/redeploy timing against SPY correction episodes."""

    if end_date < start_date:
        raise RegimeError("End date must be on or after start date")
    if warning_lookback_days < 0:
        raise RegimeError("Warning lookback days must be non-negative")

    histories = _load_histories(symbols=("SPY",), price_root=price_root)
    spy_history = tuple(
        row for row in histories.get("SPY", ()) if row.observed_date <= end_date
    )
    if not spy_history:
        raise RegimeError(f"No SPY price history found through {end_date}")

    windows = _spy_correction_episode_windows(
        history=spy_history,
        start_date=start_date,
        end_date=end_date,
        min_drawdown=CORRECTION_EPISODE_MIN_DRAWDOWN,
        severe_drawdown=CORRECTION_EPISODE_SEVERE_DRAWDOWN,
    )
    snapshots = _load_regime_snapshots_through(
        end_date=end_date,
        snapshot_root=snapshot_root,
        snapshot_version=snapshot_version,
    )
    episodes = tuple(
        _correction_episode_from_window(
            window=window,
            history=spy_history,
            snapshots=snapshots,
            warning_lookback_days=warning_lookback_days,
        )
        for window in windows
    )
    table = format_regime_correction_episodes(episodes)
    logger.bind(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        episode_count=len(episodes),
    ).success("Computed SPY correction episode diagnostics")
    return RegimeCorrectionEpisodeResult(
        start_date=start_date,
        end_date=end_date,
        episodes=episodes,
        table=table,
    )


def compute_regime_protect_clusters(
    *,
    start_date: date,
    end_date: date,
    snapshot_root: Path = DEFAULT_REGIME_SNAPSHOT_ROOT,
    price_root: Path = DEFAULT_PRICE_OBSERVATIONS_ROOT,
    horizons: tuple[int, ...] = DEFAULT_REGIME_OUTCOME_HORIZONS,
    snapshot_version: str | None = None,
) -> RegimeProtectClusterResult:
    """Replay protect-action clusters for false-alert diagnostics."""

    if end_date < start_date:
        raise RegimeError("End date must be on or after start date")

    snapshots = _load_regime_snapshots_in_range(
        start_date=start_date,
        end_date=end_date,
        snapshot_root=snapshot_root,
        snapshot_version=snapshot_version,
    )
    if not snapshots:
        raise RegimeError(f"No market regime snapshots found from {start_date} to {end_date}")

    histories = _load_histories(symbols=("SPY", "QQQ"), price_root=price_root)
    clusters = _protect_clusters_from_snapshots(snapshots)
    outcomes = tuple(
        outcome
        for cluster in clusters
        for outcome in _protect_cluster_outcomes(
            cluster=cluster,
            histories=histories,
            horizons=horizons,
        )
    )
    table = format_regime_protect_cluster_outcomes(outcomes)
    logger.bind(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        cluster_count=len(clusters),
        outcome_count=len(outcomes),
    ).success("Computed market regime protect cluster outcomes")
    return RegimeProtectClusterResult(
        start_date=start_date,
        end_date=end_date,
        outcomes=outcomes,
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


def summarize_regime_posture_frequency(
    postures: tuple[RegimePostureState, ...],
) -> tuple[RegimePostureFrequencyRow, ...]:
    """Summarize derived posture-state frequencies."""

    states = ("neutral", "protected", "redeploying")
    counts = {state: 0 for state in states}
    for posture in postures:
        counts.setdefault(posture.posture_state, 0)
        counts[posture.posture_state] += 1
    total_count = len(postures)
    return tuple(
        RegimePostureFrequencyRow(
            posture_state=state,
            posture_count=counts[state],
            share=counts[state] / total_count if total_count else 0.0,
        )
        for state in counts
    )


def summarize_regime_posture_outcomes(
    outcomes: tuple[RegimePostureForwardOutcome, ...],
) -> tuple[RegimePostureOutcomeSummaryRow, ...]:
    """Summarize forward market outcomes by derived posture bucket."""

    buckets: dict[str, list[RegimePostureForwardOutcome]] = {"all": list(outcomes)}
    for outcome in outcomes:
        buckets.setdefault(f"posture:{outcome.posture_state}", []).append(outcome)
        if outcome.protect_path:
            buckets.setdefault(f"protect_path:{outcome.protect_path}", []).append(outcome)

    rows: list[RegimePostureOutcomeSummaryRow] = []
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
                RegimePostureOutcomeSummaryRow(
                    bucket=bucket,
                    horizon_days=horizon,
                    posture_count=len(horizon_outcomes),
                    available_count=len(available),
                    avg_posture_age=_average(
                        outcome.posture_age for outcome in horizon_outcomes
                    ),
                    avg_posture_drawdown=_average(
                        outcome.max_drawdown_since_posture for outcome in horizon_outcomes
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


def summarize_regime_redeploy_outcomes(
    outcomes: tuple[RegimeRedeployForwardOutcome, ...],
) -> tuple[RegimeRedeployOutcomeSummaryRow, ...]:
    """Summarize forward market outcomes by redeploy validation bucket."""

    buckets: dict[str, list[RegimeRedeployForwardOutcome]] = {"all": list(outcomes)}
    for outcome in outcomes:
        buckets.setdefault(outcome.bucket, []).append(outcome)

    rows: list[RegimeRedeployOutcomeSummaryRow] = []
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
                RegimeRedeployOutcomeSummaryRow(
                    bucket=bucket,
                    horizon_days=horizon,
                    redeploy_count=len(horizon_outcomes),
                    available_count=len(available),
                    avg_washout_setup=_average(
                        outcome.washout_setup_score for outcome in horizon_outcomes
                    ),
                    avg_stabilization=_average(
                        outcome.stabilization_score for outcome in horizon_outcomes
                    ),
                    avg_redeploy_strength=_average(
                        outcome.redeploy_strength for outcome in horizon_outcomes
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
    return _format_grouped_table(table, group_column=0)


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
    return _format_grouped_table(table, group_column=0)


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
    return _format_grouped_table(table, group_column=0)


def format_regime_posture_frequency(rows: tuple[RegimePostureFrequencyRow, ...]) -> str:
    """Format derived posture frequency as a compact table."""

    if not rows:
        return "No regime posture rows found."

    table = [["posture_state", "count", "share"]]
    for row in rows:
        table.append(
            [
                row.posture_state,
                str(row.posture_count),
                _format_share(row.share),
            ]
        )
    return _format_table(table)


def format_regime_posture_outcome_summary(
    rows: tuple[RegimePostureOutcomeSummaryRow, ...],
) -> str:
    """Format derived posture forward outcome summaries as a compact table."""

    available_rows = tuple(row for row in rows if row.available_count > 0)
    if not available_rows:
        return "No available regime posture outcome rows found."

    table = [
        [
            "bucket",
            "horizon",
            "postures",
            "available",
            "age",
            "posture_dd",
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
                str(row.posture_count),
                str(row.available_count),
                _format_decimal(row.avg_posture_age),
                _format_drawdown(row.avg_posture_drawdown),
                _format_percent(row.avg_spy_return),
                _format_percent(row.avg_qqq_return),
                _format_drawdown(row.avg_spy_max_drawdown),
                _format_drawdown(row.avg_qqq_max_drawdown),
            ]
        )
    return _format_grouped_table(table, group_column=0)


def format_regime_redeploy_outcome_summary(
    rows: tuple[RegimeRedeployOutcomeSummaryRow, ...],
) -> str:
    """Format redeploy validation outcome summaries as a compact table."""

    available_rows = tuple(row for row in rows if row.available_count > 0)
    if not available_rows:
        return "No available regime redeploy outcome rows found."

    table = [
        [
            "bucket",
            "horizon",
            "signals",
            "available",
            "washout",
            "stabilize",
            "strength",
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
                str(row.redeploy_count),
                str(row.available_count),
                _format_pressure_score(row.avg_washout_setup),
                _format_pressure_score(row.avg_stabilization),
                _format_pressure_score(row.avg_redeploy_strength),
                _format_percent(row.avg_spy_return),
                _format_percent(row.avg_qqq_return),
                _format_drawdown(row.avg_spy_max_drawdown),
                _format_drawdown(row.avg_qqq_max_drawdown),
            ]
        )
    return _format_grouped_table(table, group_column=0)


def format_regime_pressure_outcome_summary(
    rows: tuple[RegimePressureOutcomeSummaryRow, ...],
) -> str:
    """Format normalized pressure forward outcome summaries as a compact table."""

    available_rows = tuple(row for row in rows if row.available_count > 0)
    if not available_rows:
        return "No available regime pressure outcome rows found."

    header = [
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
    table = [header]
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
    return _format_grouped_table(table, group_column=0)


def format_regime_correction_episodes(
    episodes: tuple[RegimeCorrectionEpisode, ...],
) -> str:
    """Format SPY correction episode diagnostics as a compact table."""

    if not episodes:
        return "No SPY correction episodes found."

    table = [
        [
            "peak",
            "first_3",
            "first_5",
            "first_8",
            "trough",
            "max_dd",
            "recovery",
            "armed",
            "protect",
            "lead",
            "timing",
            "redeploy",
            "redeploy_timing",
            "context",
        ]
    ]
    for episode in episodes:
        table.append(
            [
                episode.peak_date.isoformat(),
                _format_optional_date(episode.first_3pct_date),
                episode.first_5pct_date.isoformat(),
                _format_optional_date(episode.first_8pct_date),
                episode.trough_date.isoformat(),
                _format_drawdown(episode.max_drawdown),
                _format_optional_date(episode.recovery_date),
                _format_optional_date(episode.first_armed_date)
                if episode.armed_before_peak
                else "-",
                _format_optional_date(episode.first_protect_date),
                _format_day_lead(episode.protect_lead_days),
                episode.protect_timing,
                _format_optional_date(episode.first_redeploy_date),
                episode.redeploy_timing,
                episode.event_context,
            ]
        )
    return _format_table(table)


def format_regime_protect_cluster_outcomes(
    outcomes: tuple[RegimeProtectClusterOutcome, ...],
) -> str:
    """Format protect-cluster false-alert diagnostics as a compact table."""

    if not outcomes:
        return "No protect clusters found."

    table = [
        [
            "cluster_start",
            "cluster_end",
            "path",
            "days",
            "horizon",
            "late",
            "vol_only",
            "pre_dd",
            "spy_ret",
            "spy_dd",
            "5pct_dd",
            "families",
        ]
    ]
    for outcome in outcomes:
        table.append(
            [
                outcome.cluster_start_date.isoformat(),
                outcome.cluster_end_date.isoformat(),
                outcome.protect_path or "-",
                str(outcome.action_count),
                f"{outcome.horizon_days}d",
                "yes" if outcome.late_signal else "no",
                _format_bool(outcome.volatility_only),
                _format_drawdown(outcome.drawdown_from_peak),
                _format_percent(outcome.spy_return),
                _format_drawdown(outcome.spy_max_drawdown),
                _format_bool(outcome.had_5pct_drawdown),
                _family_list_read(outcome.confirming_families),
            ]
        )
    return _format_grouped_table(table, group_column=0)


def _format_grouped_table(rows: list[list[str]], *, group_column: int) -> str:
    if not rows:
        return ""
    widths = [max(len(row[index]) for row in rows) for index in range(len(rows[0]))]
    header_separator = "  ".join("=" * width for width in widths)
    group_separator = "  ".join("-" * width for width in widths)
    lines = [
        "  ".join(value.ljust(widths[index]) for index, value in enumerate(rows[0])),
        header_separator,
    ]
    previous_group: str | None = None
    for row in rows[1:]:
        current_group = row[group_column]
        if previous_group is not None and current_group != previous_group:
            lines.append(group_separator)
        lines.append(
            "  ".join(value.ljust(widths[index]) for index, value in enumerate(row))
        )
        previous_group = current_group
    return "\n".join(lines)


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
    snapshot_version: str | None = None,
) -> tuple[RegimeSnapshot, ...]:
    snapshots: list[RegimeSnapshot] = []
    for source_date in snapshot_source_dates(
        snapshot_root=snapshot_root,
        legacy_suffix=".json",
        filename=REGIME_SNAPSHOT_FILENAME,
    ):
        if start_date <= source_date <= end_date:
            snapshot = load_regime_snapshot(
                source_date=source_date,
                snapshot_root=snapshot_root,
                snapshot_version=snapshot_version,
            )
            if snapshot is not None:
                snapshots.append(snapshot)
    return tuple(snapshots)


def _load_recent_regime_snapshots_through(
    *,
    source_date: date,
    lookback_days: int,
    snapshot_root: Path,
    signal_time: SignalTime | str,
    snapshot_version: str | None,
) -> tuple[RegimeSnapshot, ...]:
    snapshots: list[RegimeSnapshot] = []
    for snapshot_source_date in snapshot_source_dates(
        snapshot_root=snapshot_root,
        legacy_suffix=".json",
        filename=REGIME_SNAPSHOT_FILENAME,
    ):
        if snapshot_source_date <= source_date:
            snapshot = load_regime_snapshot(
                source_date=snapshot_source_date,
                snapshot_root=snapshot_root,
                signal_time=signal_time,
                snapshot_version=snapshot_version,
            )
            if snapshot is not None and snapshot.price_date == snapshot.source_date:
                snapshots.append(snapshot)
    return tuple(snapshots[-lookback_days:])


def _load_recent_regime_snapshots_before(
    *,
    source_date: date,
    lookback_days: int,
    snapshot_root: Path,
    signal_time: SignalTime | str,
    snapshot_version: str | None,
) -> tuple[RegimeSnapshot, ...]:
    snapshots: list[RegimeSnapshot] = []
    for snapshot_source_date in snapshot_source_dates(
        snapshot_root=snapshot_root,
        legacy_suffix=".json",
        filename=REGIME_SNAPSHOT_FILENAME,
    ):
        if snapshot_source_date < source_date:
            snapshot = load_regime_snapshot(
                source_date=snapshot_source_date,
                snapshot_root=snapshot_root,
                signal_time=signal_time,
                snapshot_version=snapshot_version,
            )
            if snapshot is not None and snapshot.price_date == snapshot.source_date:
                snapshots.append(snapshot)
    return tuple(snapshots[-lookback_days:])


def _load_regime_snapshots_through(
    *,
    end_date: date,
    snapshot_root: Path,
    snapshot_version: str | None = None,
) -> tuple[RegimeSnapshot, ...]:
    snapshots: list[RegimeSnapshot] = []
    for source_date in snapshot_source_dates(
        snapshot_root=snapshot_root,
        legacy_suffix=".json",
        filename=REGIME_SNAPSHOT_FILENAME,
    ):
        if source_date <= end_date:
            snapshot = load_regime_snapshot(
                source_date=source_date,
                snapshot_root=snapshot_root,
                snapshot_version=snapshot_version,
            )
            if snapshot is not None:
                snapshots.append(snapshot)
    return tuple(snapshots)


def _load_market_signals_in_range(
    *,
    start_date: date,
    end_date: date,
    signal_snapshot_root: Path,
    snapshot_version: str | None = None,
) -> tuple[MarketSignal, ...]:
    signals: list[MarketSignal] = []
    for source_date in snapshot_source_dates(
        snapshot_root=signal_snapshot_root,
        legacy_suffix=".jsonl",
        filename=MARKET_SIGNAL_SNAPSHOT_FILENAME,
    ):
        if start_date <= source_date <= end_date:
            signals.extend(
                load_market_signal_snapshot(
                    source_date=source_date,
                    snapshot_root=signal_snapshot_root,
                    snapshot_version=snapshot_version,
                )
            )
    return tuple(signals)


def _load_market_signals_by_source_date_through(
    *,
    end_date: date,
    signal_snapshot_root: Path,
    signal_time: SignalTime | str = SignalTime.EOD,
    snapshot_version: str | None = None,
) -> dict[date, tuple[MarketSignal, ...]]:
    signals_by_date: dict[date, tuple[MarketSignal, ...]] = {}
    for source_date in snapshot_source_dates(
        snapshot_root=signal_snapshot_root,
        legacy_suffix=".jsonl",
        filename=MARKET_SIGNAL_SNAPSHOT_FILENAME,
    ):
        if source_date <= end_date:
            signals_by_date[source_date] = load_market_signal_snapshot(
                source_date=source_date,
                snapshot_root=signal_snapshot_root,
                signal_time=signal_time,
                snapshot_version=snapshot_version,
            )
    return signals_by_date


def _spy_correction_episode_windows(
    *,
    history: tuple[DailyPriceObservation, ...],
    start_date: date,
    end_date: date,
    min_drawdown: float,
    severe_drawdown: float,
) -> tuple[_CorrectionEpisodeWindow, ...]:
    if not history:
        return ()

    peak_index = 0
    first_3pct_index: int | None = None
    first_5pct_index: int | None = None
    first_8pct_index: int | None = None
    trough_index: int | None = None
    windows: list[_CorrectionEpisodeWindow] = []

    for index, row in enumerate(history):
        if row.observed_date > end_date:
            break

        peak_close = history[peak_index].return_close
        if peak_close == 0:
            peak_index = index
            first_3pct_index = None
            first_5pct_index = None
            first_8pct_index = None
            trough_index = None
            continue

        close = row.return_close
        if first_5pct_index is None:
            if close >= peak_close:
                peak_index = index
                first_3pct_index = None
                continue

            drawdown = close / peak_close - 1.0
            if (
                first_3pct_index is None
                and drawdown <= -CORRECTION_EPISODE_FIRST_DAMAGE_DRAWDOWN
            ):
                first_3pct_index = index
            if drawdown <= -min_drawdown:
                first_5pct_index = index
                first_8pct_index = index if drawdown <= -severe_drawdown else None
                trough_index = index
            continue

        drawdown = close / peak_close - 1.0
        if first_8pct_index is None and drawdown <= -severe_drawdown:
            first_8pct_index = index
        if trough_index is None or close < history[trough_index].return_close:
            trough_index = index
        if close >= peak_close:
            if start_date <= history[first_5pct_index].observed_date <= end_date:
                windows.append(
                    _CorrectionEpisodeWindow(
                        peak_index=peak_index,
                        first_3pct_index=first_3pct_index,
                        first_5pct_index=first_5pct_index,
                        first_8pct_index=first_8pct_index,
                        trough_index=trough_index,
                        recovery_index=index,
                    )
                )
            peak_index = index
            first_3pct_index = None
            first_5pct_index = None
            first_8pct_index = None
            trough_index = None

    if first_5pct_index is not None and trough_index is not None:
        if start_date <= history[first_5pct_index].observed_date <= end_date:
            windows.append(
                _CorrectionEpisodeWindow(
                    peak_index=peak_index,
                    first_3pct_index=first_3pct_index,
                    first_5pct_index=first_5pct_index,
                    first_8pct_index=first_8pct_index,
                    trough_index=trough_index,
                    recovery_index=None,
                )
            )

    return tuple(windows)


def _correction_episode_from_window(
    *,
    window: _CorrectionEpisodeWindow,
    history: tuple[DailyPriceObservation, ...],
    snapshots: tuple[RegimeSnapshot, ...],
    warning_lookback_days: int,
) -> RegimeCorrectionEpisode:
    peak = history[window.peak_index]
    first_3pct = (
        history[window.first_3pct_index] if window.first_3pct_index is not None else None
    )
    first_5pct = history[window.first_5pct_index]
    first_8pct = (
        history[window.first_8pct_index] if window.first_8pct_index is not None else None
    )
    trough = history[window.trough_index]
    recovery = (
        history[window.recovery_index] if window.recovery_index is not None else None
    )
    signal_start_date = history[
        max(0, window.peak_index - warning_lookback_days)
    ].observed_date
    signal_end_date = recovery.observed_date if recovery is not None else history[-1].observed_date
    signal_snapshots = tuple(
        snapshot
        for snapshot in snapshots
        if signal_start_date <= snapshot.source_date <= signal_end_date
    )
    first_armed_date = _first_armed_setup_date(
        snapshots=signal_snapshots,
        through_date=peak.observed_date,
    )
    first_protect_date = _first_action_date(
        snapshots=signal_snapshots,
        action_state="scale_down_protect",
    )
    first_redeploy_date = _first_action_date(
        snapshots=tuple(
            snapshot
            for snapshot in signal_snapshots
            if snapshot.source_date >= first_5pct.observed_date
        ),
        action_state="scale_up_redeploy",
    )

    return RegimeCorrectionEpisode(
        peak_date=peak.observed_date,
        first_3pct_date=first_3pct.observed_date if first_3pct is not None else None,
        first_5pct_date=first_5pct.observed_date,
        first_8pct_date=first_8pct.observed_date if first_8pct is not None else None,
        trough_date=trough.observed_date,
        recovery_date=recovery.observed_date if recovery is not None else None,
        max_drawdown=trough.return_close / peak.return_close - 1.0,
        first_armed_date=first_armed_date,
        armed_before_peak=first_armed_date is not None,
        first_protect_date=first_protect_date,
        protect_lead_days=_trading_day_distance(
            history=history,
            start_date=first_protect_date,
            end_date=first_5pct.observed_date,
        ),
        protect_timing=_protect_timing(
            protect_date=first_protect_date,
            first_3pct_date=first_3pct.observed_date if first_3pct is not None else None,
            first_5pct_date=first_5pct.observed_date,
        ),
        first_redeploy_date=first_redeploy_date,
        redeploy_timing=_redeploy_timing(
            redeploy_date=first_redeploy_date,
            trough_date=trough.observed_date,
            recovery_date=recovery.observed_date if recovery is not None else None,
        ),
        event_context=_correction_episode_event_context(
            window=window,
            history=history,
            snapshots=signal_snapshots,
        ),
    )


def _correction_episode_event_context(
    *,
    window: _CorrectionEpisodeWindow,
    history: tuple[DailyPriceObservation, ...],
    snapshots: tuple[RegimeSnapshot, ...],
) -> str:
    peak = history[window.peak_index]
    first_5pct = history[window.first_5pct_index]
    trough = history[window.trough_index]
    max_drawdown = trough.return_close / peak.return_close - 1.0
    days_to_trough = window.trough_index - window.peak_index
    if max_drawdown <= -0.15 and days_to_trough <= 30:
        return "shock"
    if any(
        snapshot.event_volatility_context.startswith("near_term_event_premium")
        for snapshot in snapshots
        if peak.observed_date <= snapshot.source_date <= first_5pct.observed_date
    ):
        return "scheduled_event_proxy"
    return "ordinary"


def _first_armed_setup_date(
    *,
    snapshots: tuple[RegimeSnapshot, ...],
    through_date: date,
) -> date | None:
    for snapshot in snapshots:
        if snapshot.source_date > through_date:
            break
        if (snapshot.extension_setup_score or 0.0) >= EXTENSION_ARMED_SETUP_THRESHOLD:
            return snapshot.source_date
    return None


def _first_action_date(
    *,
    snapshots: tuple[RegimeSnapshot, ...],
    action_state: str,
) -> date | None:
    for snapshot in snapshots:
        if snapshot.action_state == action_state:
            return snapshot.source_date
    return None


def _protect_timing(
    *,
    protect_date: date | None,
    first_3pct_date: date | None,
    first_5pct_date: date,
) -> str:
    if protect_date is None:
        return "none"
    if first_3pct_date is not None and protect_date <= first_3pct_date:
        return "before_3pct"
    if protect_date <= first_5pct_date:
        return "before_5pct"
    return "after_5pct"


def _redeploy_timing(
    *,
    redeploy_date: date | None,
    trough_date: date,
    recovery_date: date | None,
) -> str:
    if redeploy_date is None:
        return "none"
    if redeploy_date <= trough_date:
        return "before_trough"
    if recovery_date is None:
        return "after_trough_open"
    if redeploy_date <= recovery_date:
        return "before_recovery"
    return "after_recovery"


def _trading_day_distance(
    *,
    history: tuple[DailyPriceObservation, ...],
    start_date: date | None,
    end_date: date,
) -> int | None:
    if start_date is None:
        return None
    start_index = _asof_index(history, start_date)
    end_index = _exact_date_index(history, end_date)
    if start_index is None or end_index is None:
        return None
    return end_index - start_index


def _existing_regime_snapshot_path(
    *,
    source_date: date,
    snapshot_root: Path,
    signal_time: SignalTime | str,
    snapshot_version: str | None,
) -> Path | None:
    try:
        path = versioned_snapshot_path(
            snapshot_root=snapshot_root,
            source_date=source_date,
            signal_time=signal_time,
            snapshot_version=snapshot_version,
            filename=REGIME_SNAPSHOT_FILENAME,
            default_version=REGIME_SNAPSHOT_VERSION,
        )
    except ValueError as exc:
        raise RegimeError(str(exc)) from exc
    return path if path.is_file() else None


def _existing_market_signal_snapshot_path(
    *,
    source_date: date,
    signal_snapshot_root: Path,
    signal_time: SignalTime | str,
    snapshot_version: str | None,
) -> Path | None:
    try:
        path = versioned_snapshot_path(
            snapshot_root=signal_snapshot_root,
            source_date=source_date,
            signal_time=signal_time,
            snapshot_version=snapshot_version,
            filename=MARKET_SIGNAL_SNAPSHOT_FILENAME,
            default_version=REGIME_SNAPSHOT_VERSION,
        )
    except ValueError as exc:
        raise RegimeError(str(exc)) from exc
    return path if path.is_file() else None


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


def _regime_posture_outcomes(
    *,
    snapshot: RegimeSnapshot,
    posture: RegimePostureState,
    histories: dict[str, tuple[DailyPriceObservation, ...]],
    horizons: tuple[int, ...],
) -> tuple[RegimePostureForwardOutcome, ...]:
    spy_history = histories.get("SPY", ())
    qqq_history = histories.get("QQQ", ())
    spy_index = _exact_date_index(spy_history, snapshot.price_date)
    qqq_index = _exact_date_index(qqq_history, snapshot.price_date)
    return tuple(
        RegimePostureForwardOutcome(
            source_date=snapshot.source_date,
            price_date=snapshot.price_date,
            posture_state=posture.posture_state,
            protect_path=posture.protect_path,
            posture_age=posture.posture_age,
            max_drawdown_since_posture=posture.max_drawdown_since_posture,
            horizon_days=horizon,
            spy_return=_forward_return(spy_history, index=spy_index, horizon=horizon),
            qqq_return=_forward_return(qqq_history, index=qqq_index, horizon=horizon),
            spy_max_drawdown=_forward_max_drawdown(spy_history, index=spy_index, horizon=horizon),
            qqq_max_drawdown=_forward_max_drawdown(qqq_history, index=qqq_index, horizon=horizon),
        )
        for horizon in horizons
    )


def _regime_redeploy_outcomes(
    *,
    snapshot: RegimeSnapshot,
    histories: dict[str, tuple[DailyPriceObservation, ...]],
    horizons: tuple[int, ...],
) -> tuple[RegimeRedeployForwardOutcome, ...]:
    spy_history = histories.get("SPY", ())
    qqq_history = histories.get("QQQ", ())
    spy_index = _exact_date_index(spy_history, snapshot.price_date)
    qqq_index = _exact_date_index(qqq_history, snapshot.price_date)
    bucket = _redeploy_validation_bucket(snapshot)
    return tuple(
        RegimeRedeployForwardOutcome(
            source_date=snapshot.source_date,
            price_date=snapshot.price_date,
            bucket=bucket,
            action_state=snapshot.action_state,
            washout_setup_score=snapshot.washout_setup_score,
            stabilization_score=snapshot.stabilization_score,
            redeploy_strength=snapshot.redeploy_strength,
            horizon_days=horizon,
            spy_return=_forward_return(spy_history, index=spy_index, horizon=horizon),
            qqq_return=_forward_return(qqq_history, index=qqq_index, horizon=horizon),
            spy_max_drawdown=_forward_max_drawdown(spy_history, index=spy_index, horizon=horizon),
            qqq_max_drawdown=_forward_max_drawdown(qqq_history, index=qqq_index, horizon=horizon),
        )
        for horizon in horizons
    )


def _redeploy_validation_bucket(snapshot: RegimeSnapshot) -> str:
    washout_setup = snapshot.washout_setup_score or 0.0
    stabilization = snapshot.stabilization_score
    if snapshot.action_state == "scale_up_redeploy":
        return "redeploy:action"
    if snapshot.action_reason.startswith("Redeploy setup present, but"):
        return "redeploy:funding_blocked"
    has_setup = washout_setup >= ACTION_STRENGTH_THRESHOLD
    has_stabilization = stabilization >= ACTION_STRENGTH_THRESHOLD
    if has_setup and has_stabilization:
        return "redeploy:confirmed_no_action"
    if has_setup:
        return "redeploy:setup_only"
    if has_stabilization:
        return "redeploy:stabilization_only"
    return "redeploy:no_setup"


def _protect_clusters_from_snapshots(
    snapshots: tuple[RegimeSnapshot, ...],
) -> tuple[tuple[RegimeSnapshot, ...], ...]:
    clusters: list[tuple[RegimeSnapshot, ...]] = []
    current: list[RegimeSnapshot] = []
    for snapshot in sorted(snapshots, key=lambda row: row.source_date):
        if snapshot.action_state == "scale_down_protect":
            current.append(snapshot)
            continue
        if current:
            clusters.append(tuple(current))
            current = []
    if current:
        clusters.append(tuple(current))
    return tuple(clusters)


def _protect_cluster_outcomes(
    *,
    cluster: tuple[RegimeSnapshot, ...],
    histories: dict[str, tuple[DailyPriceObservation, ...]],
    horizons: tuple[int, ...],
) -> tuple[RegimeProtectClusterOutcome, ...]:
    first_snapshot = cluster[0]
    last_snapshot = cluster[-1]
    spy_history = histories.get("SPY", ())
    qqq_history = histories.get("QQQ", ())
    spy_index = _exact_date_index(spy_history, first_snapshot.price_date)
    qqq_index = _exact_date_index(qqq_history, first_snapshot.price_date)
    drawdown_from_peak = _trailing_drawdown_from_peak(
        spy_history,
        index=spy_index,
        lookback=252,
    )
    confirming_families = _confirming_families(
        modules=first_snapshot.action_modules,
        field_name="deterioration_score",
    )
    late_signal = (
        drawdown_from_peak is not None
        and drawdown_from_peak <= -CORRECTION_EPISODE_MIN_DRAWDOWN
    )
    outcomes: list[RegimeProtectClusterOutcome] = []
    for horizon in horizons:
        spy_drawdown = _forward_max_drawdown(
            spy_history,
            index=spy_index,
            horizon=horizon,
        )
        outcomes.append(
            RegimeProtectClusterOutcome(
                cluster_start_date=first_snapshot.source_date,
                cluster_end_date=last_snapshot.source_date,
                first_price_date=first_snapshot.price_date,
                protect_path=first_snapshot.action_path,
                action_count=len(cluster),
                confirming_families=confirming_families,
                volatility_only=confirming_families == ("volatility",),
                late_signal=late_signal,
                drawdown_from_peak=drawdown_from_peak,
                horizon_days=horizon,
                spy_return=_forward_return(spy_history, index=spy_index, horizon=horizon),
                qqq_return=_forward_return(qqq_history, index=qqq_index, horizon=horizon),
                spy_max_drawdown=spy_drawdown,
                qqq_max_drawdown=_forward_max_drawdown(
                    qqq_history,
                    index=qqq_index,
                    horizon=horizon,
                ),
                had_5pct_drawdown=(
                    spy_drawdown <= -CORRECTION_EPISODE_MIN_DRAWDOWN
                    if spy_drawdown is not None
                    else None
                ),
            )
        )
    return tuple(outcomes)


def _trailing_drawdown_from_peak(
    history: tuple[DailyPriceObservation, ...],
    *,
    index: int | None,
    lookback: int,
) -> float | None:
    if index is None:
        return None
    start_index = max(0, index - lookback)
    peak = max(row.return_close for row in history[start_index : index + 1])
    if peak == 0:
        return None
    return min(0.0, history[index].return_close / peak - 1.0)


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
        buckets.append("stretch:p95")
    if outcome.stretch_pressure_percentile >= 0.90:
        buckets.append("stretch:p90")
    if outcome.washout_pressure_percentile >= 0.95:
        buckets.append("washout:p95")
    if outcome.washout_pressure_percentile >= 0.90:
        buckets.append("washout:p90")
    if not buckets:
        buckets.append("pressure:below_p90")
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
        return_5d=_lookback_return(history, index=index, lookback=5),
        return_20d=_lookback_return(history, index=index, lookback=20),
        return_60d=_lookback_return(history, index=index, lookback=60),
        change_5d=_lookback_change(history, index=index, lookback=5),
        change_20d=_lookback_change(history, index=index, lookback=20),
        ma50_distance=_moving_average_distance(history, index=index, window=50),
        ma200_distance=_moving_average_distance(history, index=index, window=200),
        realized_vol_20d=_realized_volatility(history, index=index, lookback=20),
    )


def _empty_symbol_features(symbol: str) -> _SymbolFeatures:
    return _SymbolFeatures(
        symbol=symbol,
        price_date=None,
        close=None,
        return_5d=None,
        return_20d=None,
        return_60d=None,
        change_5d=None,
        change_20d=None,
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
    return _relative_return_for_lookback(left, right, field_name="return_20d")


def _relative_return_for_lookback(
    left: _SymbolFeatures,
    right: _SymbolFeatures,
    *,
    field_name: str,
) -> float | None:
    left_return = getattr(left, field_name)
    right_return = getattr(right, field_name)
    if left_return is None or right_return is None:
        return None
    return left_return - right_return


def _ratio(numerator: float | None, denominator: float | None) -> float | None:
    if numerator is None or denominator is None or denominator <= 0:
        return None
    return numerator / denominator


def _aligned_ratio(numerator: _SymbolFeatures, denominator: _SymbolFeatures) -> float | None:
    if (
        numerator.price_date is None
        or denominator.price_date is None
        or numerator.price_date != denominator.price_date
    ):
        return None
    return _ratio(numerator.close, denominator.close)


def _ratio_change_for_lookback(
    numerator: _SymbolFeatures,
    denominator: _SymbolFeatures,
    *,
    field_name: str,
) -> float | None:
    current_ratio = _ratio(numerator.close, denominator.close)
    numerator_return = getattr(numerator, field_name)
    denominator_return = getattr(denominator, field_name)
    if current_ratio is None or numerator_return is None or denominator_return is None:
        return None
    numerator_factor = 1.0 + numerator_return
    denominator_factor = 1.0 + denominator_return
    if numerator_factor <= 0.0 or denominator_factor <= 0.0:
        return None
    past_ratio = current_ratio * denominator_factor / numerator_factor
    return current_ratio - past_ratio


def _aligned_ratio_change(
    numerator: _SymbolFeatures,
    denominator: _SymbolFeatures,
    *,
    field_name: str,
) -> float | None:
    if (
        numerator.price_date is None
        or denominator.price_date is None
        or numerator.price_date != denominator.price_date
    ):
        return None
    return _ratio_change_for_lookback(numerator, denominator, field_name=field_name)


def _vix_term_structure_stale_pairs(
    *,
    vix9d: _SymbolFeatures,
    vix: _SymbolFeatures,
    vix3m: _SymbolFeatures,
) -> tuple[str, ...]:
    stale_pairs: list[str] = []
    if _has_mismatched_price_dates(vix9d, vix):
        stale_pairs.append("VIX9D/VIX")
    if _has_mismatched_price_dates(vix, vix3m):
        stale_pairs.append("VIX/VIX3M")
    return tuple(stale_pairs)


def _vix_term_structure_observed_dates(
    *,
    vix9d: _SymbolFeatures,
    vix: _SymbolFeatures,
    vix3m: _SymbolFeatures,
) -> tuple[date, ...]:
    observed_dates = []
    if _aligned_ratio(vix9d, vix) is not None and vix.price_date is not None:
        observed_dates.append(vix.price_date)
    if _aligned_ratio(vix, vix3m) is not None and vix.price_date is not None:
        observed_dates.append(vix.price_date)
    return tuple(observed_dates)


def _has_mismatched_price_dates(left: _SymbolFeatures, right: _SymbolFeatures) -> bool:
    return (
        left.price_date is not None
        and right.price_date is not None
        and left.price_date != right.price_date
    )


def _asof_index(history: tuple[DailyPriceObservation, ...], source_date: date) -> int | None:
    for index in range(len(history) - 1, -1, -1):
        if history[index].availability_date and history[index].availability_date <= source_date:
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


def _lookback_change(
    history: tuple[DailyPriceObservation, ...],
    *,
    index: int,
    lookback: int,
) -> float | None:
    past_index = index - lookback
    if past_index < 0:
        return None
    return history[index].return_close - history[past_index].return_close


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


def _le(value: float | None, threshold: float) -> bool:
    return value is not None and value <= threshold


def _snapshot_from_dict(row: dict[str, Any]) -> RegimeSnapshot:
    source_date = date.fromisoformat(str(row["source_date"]))
    signal_time = str(row.get("signal_time", SignalTime.EOD.value))
    pressure_features = tuple(
        _pressure_feature_from_dict(feature) for feature in row.get("pressure_features", ())
    )
    pressure_modules = (
        tuple(_pressure_module_from_dict(module) for module in row.get("pressure_modules", ()))
        if "pressure_modules" in row
        else _pressure_modules(source_date=source_date, features=pressure_features)
    )
    action_features = tuple(
        _action_feature_from_dict(feature) for feature in row.get("action_features", ())
    )
    action_modules = (
        tuple(_action_module_from_dict(module) for module in row.get("action_modules", ()))
        if "action_modules" in row
        else _action_modules(action_features)
    )
    return RegimeSnapshot(
        source_date=source_date,
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
        vix9d_vix_ratio=_optional_float(row.get("vix9d_vix_ratio")),
        vix_vix3m_ratio=_optional_float(row.get("vix_vix3m_ratio")),
        sp500_above_50d=_optional_float(row.get("sp500_above_50d")),
        sp500_above_200d=_optional_float(row.get("sp500_above_200d")),
        action_version=str(row.get("action_version", REGIME_ACTION_VERSION)),
        action_state=str(row.get("action_state", "no_change")),
        stretch_score=int(row.get("stretch_score", 0)),
        washout_score=int(row.get("washout_score", 0)),
        deterioration_score=_optional_float(row.get("deterioration_score")) or 0.0,
        stabilization_score=_optional_float(row.get("stabilization_score")) or 0.0,
        protect_strength=_optional_float(row.get("protect_strength")) or 0.0,
        redeploy_strength=_optional_float(row.get("redeploy_strength")) or 0.0,
        action_score=_optional_float(row.get("action_score")) or 0.0,
        action_confidence=str(row.get("action_confidence", "low")),
        action_reason=str(row.get("action_reason", "Action state not computed")),
        action_path=_optional_str(row.get("action_path")),
        event_volatility_context=str(row.get("event_volatility_context", "none")),
        action_features=action_features,
        action_modules=action_modules,
        pressure_version=str(row.get("pressure_version", REGIME_PRESSURE_VERSION)),
        stretch_pressure_score=_optional_float(row.get("stretch_pressure_score")),
        washout_pressure_score=_optional_float(row.get("washout_pressure_score")),
        extension_setup_score=_optional_float(row.get("extension_setup_score")),
        fragility_context_score=_optional_float(row.get("fragility_context_score")),
        washout_setup_score=_optional_float(row.get("washout_setup_score")),
        extension_memory_status=str(row.get("extension_memory_status", "not_computed")),
        extension_armed=bool(row.get("extension_armed", False)),
        extension_armed_since=(
            date.fromisoformat(str(row["extension_armed_since"]))
            if row.get("extension_armed_since")
            else None
        ),
        extension_armed_age=(
            int(row["extension_armed_age"])
            if row.get("extension_armed_age") is not None
            else None
        ),
        extension_armed_decay=_optional_float(row.get("extension_armed_decay")),
        extension_armed_source_strength=_optional_float(
            row.get("extension_armed_source_strength")
        ),
        extension_memory_score=_optional_float(row.get("extension_memory_score")) or 0.0,
        extension_memory_snapshot_count=int(row.get("extension_memory_snapshot_count", 0)),
        pressure_confidence=str(row.get("pressure_confidence", "low")),
        pressure_features=pressure_features,
        pressure_modules=pressure_modules,
        signal_time=signal_time,
        snapshot_version=_optional_str(row.get("snapshot_version"))
        or default_snapshot_version(
            source_date,
            signal_time=signal_time,
            default_version=REGIME_SNAPSHOT_VERSION,
        ),
        market_signal_snapshot_version=_optional_str(row.get("market_signal_snapshot_version")),
        created_at=_optional_str(row.get("created_at")),
        code_revision=_optional_str(row.get("code_revision")),
    )


def _action_feature_from_dict(row: dict[str, Any]) -> RegimeActionFeature:
    return RegimeActionFeature(
        family=str(row["family"]),
        name=str(row["name"]),
        deterioration_score=float(row["deterioration_score"]),
        stabilization_score=float(row["stabilization_score"]),
        reason=str(row["reason"]),
        evidence_kind=str(row.get("evidence_kind", "turn")),
    )


def _action_module_from_dict(row: dict[str, Any]) -> RegimeActionModule:
    return RegimeActionModule(
        family=str(row["family"]),
        name=str(row["name"]),
        deterioration_score=float(row["deterioration_score"]),
        stabilization_score=float(row["stabilization_score"]),
        feature_count=int(row["feature_count"]),
        feature_names=tuple(str(name) for name in row["feature_names"]),
        reason=str(row["reason"]),
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


def _pressure_module_from_dict(row: dict[str, Any]) -> RegimePressureModule:
    return RegimePressureModule(
        source_date=date.fromisoformat(str(row["source_date"])),
        pressure_version=str(row.get("pressure_version", REGIME_PRESSURE_VERSION)),
        family=str(row["family"]),
        name=str(row["name"]),
        stretch_score=_optional_float(row.get("stretch_score")),
        washout_score=_optional_float(row.get("washout_score")),
        feature_count=int(row.get("feature_count", 0)),
        feature_names=tuple(str(name) for name in row.get("feature_names", ())),
        reason=str(row.get("reason", "")),
    )


def _optional_float(value: object) -> float | None:
    return float(value) if value is not None else None


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _with_write_provenance(
    row: dict[str, Any],
    *,
    created_at: str,
    code_revision: str | None,
) -> dict[str, Any]:
    enriched = dict(row)
    if enriched.get("created_at") is None:
        enriched["created_at"] = created_at
    if enriched.get("code_revision") is None:
        enriched["code_revision"] = code_revision
    return enriched


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
    if feature.name in {"sp500_above_50d", "sp500_above_200d"}:
        return f"{value:.1f}%"
    if feature.name == "credit_spread":
        return f"{value:.2f}%"
    if feature.name == "yield_curve":
        return f"{value:+.2f}pp"
    if feature.name.endswith("_ratio"):
        return f"{value:.2f}"
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


def _format_signed_decimal(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:+.2f}"


def _format_decimal(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.1f}"


def _format_change_with_percent(change: float | None, percent_change: float | None) -> str:
    if change is None:
        return _format_percent(percent_change)
    if percent_change is None:
        return _format_signed_decimal(change)
    return f"{_format_signed_decimal(change)} ({_format_percent(percent_change)})"


def _format_index(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}"


def _format_points(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:+.1f}pp"


def _format_drawdown(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{min(0.0, value) * 100:.1f}%"


def _format_optional_date(value: date | None) -> str:
    if value is None:
        return "-"
    return value.isoformat()


def _format_day_lead(value: int | None) -> str:
    if value is None:
        return "-"
    if value > 0:
        return f"+{value}d"
    if value < 0:
        return f"{value}d"
    return "0d"


def _format_bool(value: bool | None) -> str:
    if value is None:
        return "-"
    return "yes" if value else "no"


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
