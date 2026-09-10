"""Point-in-time market signal snapshots."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from loguru import logger

from marketlab.snapshots.models import (
    SignalTime,
    current_code_revision,
    default_snapshot_version,
    resolve_snapshot_path,
    signal_time_value,
    utc_timestamp,
    versioned_snapshot_path,
    write_snapshot_payload,
)

DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT = Path("data/snapshots/market/signals")
MARKET_SIGNAL_FEATURE_VERSION = "market_signals_v0"
MARKET_SIGNAL_MODEL_VERSION = "market_signals_model_v0"
MARKET_SIGNAL_SNAPSHOT_FILENAME = "market-signals.jsonl"
MARKET_SIGNAL_FAMILY_ORDER = {
    "trend": 0,
    "volatility": 1,
    "breadth": 2,
    "credit": 3,
    "liquidity": 4,
    "rates": 5,
}
MARKET_SIGNAL_NAME_ORDER = {
    "price_proxy": 0,
    "vol_of_vol": 1,
    "term_structure": 2,
    "participation": 1,
    "credit_spread": 1,
    "financial_conditions": 1,
    "yield_curve": 1,
}


class MarketSignalError(ValueError):
    """Raised when market signal snapshots cannot be read or written."""


@dataclass(frozen=True, slots=True)
class MarketSignal:
    """One point-in-time market signal row."""

    source_date: date
    feature_version: str
    family: str
    name: str
    status: str
    score: int
    value: float | str | None
    unit: str
    source: str
    observed_date: date | None
    availability_date: date | None
    reason: str
    details: dict[str, Any] = field(default_factory=dict)
    signal_time: str = SignalTime.EOD.value
    snapshot_version: str | None = None
    model_version: str = MARKET_SIGNAL_MODEL_VERSION
    created_at: str | None = field(default=None, compare=False)
    code_revision: str | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        signal_time = signal_time_value(self.signal_time)
        object.__setattr__(self, "signal_time", signal_time)
        if not self.snapshot_version:
            object.__setattr__(
                self,
                "snapshot_version",
                default_snapshot_version(self.source_date, signal_time=signal_time),
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": "marketlab",
            "snapshot_type": "market-signal",
            "source_date": self.source_date.isoformat(),
            "signal_date": self.source_date.isoformat(),
            "signal_time": self.signal_time,
            "snapshot_version": self.snapshot_version,
            "feature_version": self.feature_version,
            "model_version": self.model_version,
            "family": self.family,
            "name": self.name,
            "status": self.status,
            "score": self.score,
            "value": self.value,
            "unit": self.unit,
            "data_source": self.source,
            "observed_date": self.observed_date.isoformat() if self.observed_date else None,
            "availability_date": (
                self.availability_date.isoformat() if self.availability_date else None
            ),
            "reason": self.reason,
            "details": self.details,
            "created_at": self.created_at,
            "code_revision": self.code_revision,
        }


def write_market_signal_snapshot(
    signals: tuple[MarketSignal, ...],
    *,
    snapshot_root: Path = DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT,
    overwrite: bool = True,
) -> Path:
    """Write one date's replaceable market signal rows."""

    if not signals:
        raise MarketSignalError("Cannot write an empty market signal snapshot")
    source_date = signals[0].source_date
    if any(signal.source_date != source_date for signal in signals):
        raise MarketSignalError("Market signal snapshot must contain one source date")
    signal_time = signals[0].signal_time
    if any(signal.signal_time != signal_time for signal in signals):
        raise MarketSignalError("Market signal snapshot must contain one signal time")
    snapshot_version = signals[0].snapshot_version
    if any(signal.snapshot_version != snapshot_version for signal in signals):
        raise MarketSignalError("Market signal snapshot must contain one snapshot version")
    model_version = signals[0].model_version
    if any(signal.model_version != model_version for signal in signals):
        raise MarketSignalError("Market signal snapshot must contain one model version")

    try:
        path = versioned_snapshot_path(
            snapshot_root=snapshot_root,
            source_date=source_date,
            signal_time=signal_time,
            snapshot_version=snapshot_version,
            filename=MARKET_SIGNAL_SNAPSHOT_FILENAME,
        )
    except ValueError as exc:
        raise MarketSignalError(str(exc)) from exc
    created_at = utc_timestamp()
    code_revision = current_code_revision()
    payload = "".join(
        json.dumps(
            _with_write_provenance(
                signal.to_dict(),
                created_at=created_at,
                code_revision=code_revision,
            ),
            sort_keys=True,
        )
        + "\n"
        for signal in signals
    )
    wrote = write_snapshot_payload(
        path=path,
        payload=payload,
        error_cls=MarketSignalError,
        overwrite=overwrite,
    )
    logger.bind(
        source_date=source_date.isoformat(),
        row_count=len(signals),
        snapshot_path=str(path),
        wrote=wrote,
    ).success("Wrote market signal snapshot")
    return path


def load_market_signal_snapshot(
    *,
    source_date: date,
    snapshot_root: Path = DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT,
    signal_time: SignalTime | str = SignalTime.EOD,
    snapshot_version: str | None = None,
    model_version: str | None = None,
) -> tuple[MarketSignal, ...]:
    """Load one date's market signal rows."""

    try:
        path = resolve_snapshot_path(
            snapshot_root=snapshot_root,
            source_date=source_date,
            signal_time=signal_time,
            snapshot_version=snapshot_version,
            filename=MARKET_SIGNAL_SNAPSHOT_FILENAME,
            legacy_suffix=".jsonl",
        )
    except ValueError as exc:
        raise MarketSignalError(str(exc)) from exc
    if path is None:
        return ()
    if not path.is_file():
        return ()
    try:
        signals = tuple(
            _signal_from_dict(json.loads(line))
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
        if model_version is not None:
            signals = tuple(signal for signal in signals if signal.model_version == model_version)
        return signals
    except OSError as exc:
        raise MarketSignalError(f"Failed to read market signal snapshot: {path}") from exc
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise MarketSignalError(f"Invalid market signal snapshot file: {path}") from exc


def format_market_signals(signals: tuple[MarketSignal, ...]) -> str:
    """Format market signal rows as a compact table."""

    if not signals:
        return "No market signal rows found."

    rows = [
        [
            "family",
            "signal",
            "score",
            "status",
            "value",
            "observed",
            "reason",
        ]
    ]
    for signal in sorted(signals, key=_market_signal_sort_key):
        rows.extend(_format_market_signal_rows(signal))
    return _format_table(rows)


def _format_market_signal_rows(signal: MarketSignal) -> list[list[str]]:
    if signal.family == "trend" and signal.name == "price_proxy":
        return [
            _format_market_signal_row(
                signal,
                signal_name="SPY",
                contributes_to_regime=_contributes_to_regime_score(signal),
                value=_format_trend_symbol_value(signal, symbol="spy")
                or _format_value(signal.value, signal.unit),
            ),
            _format_market_signal_row(
                signal,
                signal_name="QQQ",
                value=_format_trend_symbol_value(signal, symbol="qqq")
                or _format_value(signal.value, signal.unit),
                repeat_signal_metadata=False,
            ),
        ]
    if signal.family == "volatility" and signal.name == "term_structure":
        return [
            _format_market_signal_row(
                signal,
                signal_name="VIX9D/VIX",
                value=_format_term_structure_leg_value(
                    signal,
                    ratio_key="vix9d_vix_ratio",
                    ratio_change_5d_key="vix9d_vix_ratio_change_5d",
                    ratio_change_20d_key="vix9d_vix_ratio_change_20d",
                )
                or _format_value(signal.value, signal.unit),
            ),
            _format_market_signal_row(
                signal,
                signal_name="VIX/VIX3M",
                value=_format_term_structure_leg_value(
                    signal,
                    ratio_key="vix_vix3m_ratio",
                    ratio_change_5d_key="vix_vix3m_ratio_change_5d",
                    ratio_change_20d_key="vix_vix3m_ratio_change_20d",
                )
                or _format_value(signal.value, signal.unit),
                repeat_signal_metadata=False,
            ),
        ]
    if signal.family == "breadth" and signal.name == "price_proxy":
        return [
            _format_market_signal_row(
                signal,
                signal_name="RSP/SPY",
                contributes_to_regime=_contributes_to_regime_score(signal),
                value=_format_breadth_relative_value(
                    signal,
                    relative_5d_key="rsp_spy_relative_5d",
                    relative_20d_key="rsp_spy_relative_20d",
                )
                or _format_value(signal.value, signal.unit),
            ),
            _format_market_signal_row(
                signal,
                signal_name="IWM/SPY",
                value=_format_breadth_relative_value(
                    signal,
                    relative_5d_key="iwm_spy_relative_5d",
                    relative_20d_key="iwm_spy_relative_20d",
                )
                or _format_value(signal.value, signal.unit),
                repeat_signal_metadata=False,
            ),
        ]
    return [
        _format_market_signal_row(
            signal,
            contributes_to_regime=_contributes_to_regime_score(signal),
            value=_format_signal_value(signal),
        )
    ]


def _format_market_signal_row(
    signal: MarketSignal,
    *,
    value: str,
    signal_name: str | None = None,
    contributes_to_regime: bool = False,
    repeat_signal_metadata: bool = True,
) -> list[str]:
    score = (
        _format_market_signal_score(signal.score, contributes_to_regime=contributes_to_regime)
        if repeat_signal_metadata
        else "-"
    )
    status = signal.status if repeat_signal_metadata else "-"
    reason = signal.reason if repeat_signal_metadata else "-"
    return [
        signal.family,
        signal_name or signal.name,
        score,
        status,
        value,
        signal.observed_date.isoformat() if signal.observed_date else "-",
        reason,
    ]


def _format_market_signal_score(score: int, *, contributes_to_regime: bool) -> str:
    value = _format_score(score)
    if contributes_to_regime:
        return f"{value} (regime)"
    return value


def _contributes_to_regime_score(signal: MarketSignal) -> bool:
    return signal.name == "price_proxy" and signal.family in {
        "trend",
        "volatility",
        "breadth",
        "credit",
    }


def _market_signal_sort_key(signal: MarketSignal) -> tuple[int, str, int, str]:
    return (
        MARKET_SIGNAL_FAMILY_ORDER.get(signal.family, 99),
        signal.family,
        MARKET_SIGNAL_NAME_ORDER.get(signal.name, 99),
        signal.name,
    )


def _format_signal_value(signal: MarketSignal) -> str:
    if signal.family == "trend" and signal.name == "price_proxy":
        return _format_trend_pair_value(signal) or _format_value(signal.value, signal.unit)

    if signal.family == "volatility" and signal.name == "price_proxy":
        vix = _format_detail_scalar(signal.details, key="vix_close", unit="index")
        vix_change = _format_signed_decimal_change_pair(
            signal.details,
            left_key="vix_change_5d",
            right_key="vix_change_20d",
        )
        spy_realized_volatility = _format_detail_scalar(
            signal.details,
            key="spy_realized_vol_20d",
            unit="percent",
        )
        value = _format_signal_value_sections(
            (
                ("VIX", vix or "-"),
                ("5,20d chg", vix_change),
                ("SPY rv20", spy_realized_volatility or "-"),
            ),
            label_separator=" ",
        )
        return value or _format_value(signal.value, signal.unit)

    if signal.family == "volatility" and signal.name == "vol_of_vol":
        current_vvix = _format_detail_scalar(signal.details, key="vvix_close", unit="index")
        if current_vvix is None:
            current_vvix = _format_value(signal.value, signal.unit)
        vvix_change = _format_signed_decimal_change_pair(
            signal.details,
            left_key="vvix_change_5d",
            right_key="vvix_change_20d",
        )
        value = _format_signal_value_sections(
            (
                ("VVIX", current_vvix),
                ("5,20d chg", vvix_change),
            ),
            label_separator=" ",
        )
        return value or _format_value(signal.value, signal.unit)

    if signal.family == "volatility" and signal.name == "term_structure":
        value = _format_signal_value_sections(
            (
                (
                    "VIX9D/VIX",
                    _format_term_structure_leg_value(
                        signal,
                        ratio_key="vix9d_vix_ratio",
                        ratio_change_5d_key="vix9d_vix_ratio_change_5d",
                        ratio_change_20d_key="vix9d_vix_ratio_change_20d",
                    ),
                ),
                (
                    "VIX/VIX3M",
                    _format_term_structure_leg_value(
                        signal,
                        ratio_key="vix_vix3m_ratio",
                        ratio_change_5d_key="vix_vix3m_ratio_change_5d",
                        ratio_change_20d_key="vix_vix3m_ratio_change_20d",
                    ),
                ),
            ),
            label_separator=" ",
        )
        return value or _format_value(signal.value, signal.unit)

    if signal.family == "breadth" and signal.name == "price_proxy":
        rsp_spy = _format_detail_pair(
            signal.details,
            left_key="rsp_spy_relative_5d",
            right_key="rsp_spy_relative_20d",
            unit="percent",
            compact_percent=True,
        )
        iwm_spy = _format_detail_pair(
            signal.details,
            left_key="iwm_spy_relative_5d",
            right_key="iwm_spy_relative_20d",
            unit="percent",
            compact_percent=True,
        )
        value = _format_signal_value_sections(
            (
                ("RSP/SPY: 5,20d", rsp_spy),
                ("IWM/SPY: 5d,20d", iwm_spy),
            ),
            label_separator=" ",
        )
        return value or _format_value(signal.value, signal.unit)

    if signal.family == "breadth" and signal.name == "participation":
        current = _format_percent_level_pair(
            signal.details,
            left_key="sp500_above_50d",
            right_key="sp500_above_200d",
        )
        change_5d = _format_percentage_point_change_pair(
            signal.details,
            left_key="sp500_above_50d_change_5d",
            right_key="sp500_above_200d_change_5d",
        )
        change_20d = _format_percentage_point_change_pair(
            signal.details,
            left_key="sp500_above_50d_change_20d",
            right_key="sp500_above_200d_change_20d",
        )
        value = _format_signal_value_sections(
            (
                ("SPX >50/>200", current),
                ("5d chg", change_5d),
                ("20d chg", change_20d),
            ),
            label_separator=" ",
        )
        return value or _format_value(signal.value, signal.unit)

    if signal.family == "credit" and signal.name == "price_proxy":
        high_yield_treasury = _format_signal_value_values(
            (
                _format_detail_scalar(
                    signal.details,
                    key="hyg_tlt_relative_5d",
                    unit="percent",
                ),
                _format_detail_scalar(
                    signal.details,
                    key="hyg_tlt_relative_20d",
                    unit="percent",
                ),
            )
        )
        value = _format_signal_value_sections(
            (("HYG/TLT: 5,20d", high_yield_treasury),),
            label_separator=" ",
        )
        return value or _format_value(signal.value, signal.unit)

    if signal.family == "credit" and signal.name == "credit_spread":
        value = _format_signal_value_sections(
            (
                ("HY OAS", _format_value(signal.value, signal.unit)),
                (
                    "5,20d chg",
                    _format_basis_point_change_pair(
                        signal.details,
                        left_key="credit_spread_change_5d",
                        right_key="credit_spread_change_20d",
                    ),
                ),
            ),
            label_separator=" ",
        )
        return value or _format_prefixed_value("HY OAS", signal.value, signal.unit)

    if signal.family == "liquidity" and signal.name == "financial_conditions":
        value = _format_signal_value_sections(
            (
                ("NFCI", _format_value(signal.value, signal.unit)),
                (
                    "4,13w chg",
                    _format_signed_decimal_change_pair(
                        signal.details,
                        left_key="financial_conditions_change_4w",
                        right_key="financial_conditions_change_13w",
                    ),
                ),
            ),
            label_separator=" ",
        )
        return value or _format_prefixed_value("NFCI", signal.value, signal.unit)

    if signal.family == "rates" and signal.name == "yield_curve":
        value = _format_signal_value_sections(
            (
                ("10y-2y", _format_value(signal.value, signal.unit)),
                (
                    "5,20d chg",
                    _format_basis_point_change_pair(
                        signal.details,
                        left_key="yield_curve_change_5d",
                        right_key="yield_curve_change_20d",
                    ),
                ),
            ),
            label_separator=" ",
        )
        return value or _format_prefixed_value("10y-2y", signal.value, signal.unit)

    return _format_value(signal.value, signal.unit)


def _format_trend_symbol_value(signal: MarketSignal, *, symbol: str) -> str:
    gain = _format_signal_value_values(
        (
            _format_detail_scalar(
                signal.details,
                key=f"{symbol}_return_20d",
                unit="percent",
            ),
            _format_detail_scalar(
                signal.details,
                key=f"{symbol}_return_60d",
                unit="percent",
            ),
        ),
    )
    moving_average_distance = _format_signal_value_values(
        (
            _format_detail_scalar(
                signal.details,
                key=f"{symbol}_ma50_distance",
                unit="percent",
            ),
            _format_detail_scalar(
                signal.details,
                key=f"{symbol}_ma200_distance",
                unit="percent",
            ),
        ),
    )
    value = _format_signal_value_sections(
        (
            ("20,60d", gain),
            ("MA50,200", moving_average_distance),
        ),
        label_separator=" ",
    )
    return value


def _format_trend_pair_value(signal: MarketSignal) -> str:
    gain = _format_signal_value_values(
        (
            _format_detail_pair(
                signal.details,
                left_key="spy_return_20d",
                right_key="qqq_return_20d",
                unit="percent",
                compact_percent=True,
            ),
            _format_detail_pair(
                signal.details,
                left_key="spy_return_60d",
                right_key="qqq_return_60d",
                unit="percent",
                compact_percent=True,
            ),
        ),
    )
    moving_average_distance = _format_signal_value_values(
        (
            _format_detail_pair(
                signal.details,
                left_key="spy_ma50_distance",
                right_key="qqq_ma50_distance",
                unit="percent",
                compact_percent=True,
            ),
            _format_detail_pair(
                signal.details,
                left_key="spy_ma200_distance",
                right_key="qqq_ma200_distance",
                unit="percent",
                compact_percent=True,
            ),
        ),
    )
    return _format_signal_value_sections(
        (
            ("SPY/QQQ: 20,60d", gain),
            ("MA50,200", moving_average_distance),
        ),
        label_separator=" ",
    )


def _format_term_structure_leg_value(
    signal: MarketSignal,
    *,
    ratio_key: str,
    ratio_change_5d_key: str,
    ratio_change_20d_key: str,
) -> str:
    ratio = _format_detail_scalar(signal.details, key=ratio_key, unit="ratio")
    change = _format_signed_decimal_change_pair(
        signal.details,
        left_key=ratio_change_5d_key,
        right_key=ratio_change_20d_key,
    )
    return _format_value_with_change(ratio, change)


def _format_breadth_relative_value(
    signal: MarketSignal,
    *,
    relative_5d_key: str,
    relative_20d_key: str,
) -> str:
    relative = _format_detail_pair(
        signal.details,
        left_key=relative_5d_key,
        right_key=relative_20d_key,
        unit="percent",
        compact_percent=True,
    )
    return _format_signal_value_sections(
        (("5,20d", relative),),
        label_separator=" ",
    )


def _format_signal_value_sections(
    sections: tuple[tuple[str, str], ...],
    *,
    separator: str = "; ",
    label_separator: str = ": ",
) -> str:
    values = tuple(
        f"{label}{label_separator}{value}" for label, value in sections if value != "-"
    )
    return separator.join(values)


def _format_signal_value_values(values: tuple[str | None, ...]) -> str:
    available = tuple(value for value in values if value is not None and value != "-")
    return ", ".join(available) if available else "-"


def _format_value_with_change(value: str | None, change: str) -> str:
    if value is None and change == "-":
        return "-"
    if change == "-":
        return value or "-"
    return f"{value or '-'}; 5,20d chg {change}"


def _format_detail_pair(
    details: dict[str, Any],
    *,
    left_key: str,
    right_key: str,
    unit: str,
    compact_percent: bool = False,
) -> str:
    left = _format_detail_scalar(details, key=left_key, unit=unit)
    right = _format_detail_scalar(details, key=right_key, unit=unit)
    if left is None and right is None:
        return "-"
    if compact_percent and unit == "percent":
        return _format_compact_percent_pair(left=left, right=right)
    return f"{left or '-'}/{right or '-'}"


def _format_compact_percent_pair(*, left: str | None, right: str | None) -> str:
    if left is None:
        return f"-/{right or '-'}"
    if right is None:
        return f"{left}/-"
    return f"{left.removesuffix('%')}/{right}"


def _format_basis_point_change_pair(
    details: dict[str, Any],
    *,
    left_key: str,
    right_key: str,
) -> str:
    left = _format_basis_point_change(_detail_float(details, key=left_key))
    right = _format_basis_point_change(_detail_float(details, key=right_key))
    if left is None and right is None:
        return "-"
    if left is None:
        return f"-/{right or '-'}"
    if right is None:
        return f"{left}/-"
    return f"{left.removesuffix('bp')}/{right}"


def _format_percent_level_pair(
    details: dict[str, Any],
    *,
    left_key: str,
    right_key: str,
) -> str:
    left = _format_percent_level(_detail_float(details, key=left_key))
    right = _format_percent_level(_detail_float(details, key=right_key))
    if left is None and right is None:
        return "-"
    if left is None:
        return f"-/{right or '-'}"
    if right is None:
        return f"{left}/-"
    return f"{left.removesuffix('%')}/{right}"


def _format_percentage_point_change_pair(
    details: dict[str, Any],
    *,
    left_key: str,
    right_key: str,
) -> str:
    left = _format_percentage_point_change(_detail_float(details, key=left_key))
    right = _format_percentage_point_change(_detail_float(details, key=right_key))
    if left is None and right is None:
        return "-"
    if left is None:
        return f"-/{right or '-'}"
    if right is None:
        return f"{left}/-"
    return f"{left.removesuffix('pp')}/{right}"


def _format_percentage_point_change(value: float | None) -> str | None:
    if value is None:
        return None
    return f"{value:+.1f}pp"


def _format_percent_level(value: float | None) -> str | None:
    if value is None:
        return None
    return f"{value:.1f}%"


def _format_basis_point_change(value: float | None) -> str | None:
    if value is None:
        return None
    return f"{value * 100:+.0f}bp"


def _format_signed_decimal_change_pair(
    details: dict[str, Any],
    *,
    left_key: str,
    right_key: str,
) -> str:
    left = _format_signed_decimal_change(_detail_float(details, key=left_key))
    right = _format_signed_decimal_change(_detail_float(details, key=right_key))
    if left is None and right is None:
        return "-"
    return f"{left or '-'}/{right or '-'}"


def _format_signed_decimal_change(value: float | None) -> str | None:
    if value is None:
        return None
    return f"{value:+.2f}"


def _format_detail_scalar(details: dict[str, Any], *, key: str, unit: str) -> str | None:
    value = _detail_float(details, key=key)
    if value is None:
        return None
    return _format_value(value, unit)


def _detail_float(details: dict[str, Any], *, key: str) -> float | None:
    value = details.get(key)
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return float(value)


def _format_prefixed_value(prefix: str, value: float | str | None, unit: str) -> str:
    formatted = _format_value(value, unit)
    if formatted == "-":
        return formatted
    return f"{prefix} {formatted}"


def _format_detail_values(
    details: dict[str, Any],
    specs: tuple[tuple[str, str, str], ...],
) -> str:
    values = tuple(
        formatted
        for label, key, unit in specs
        if (formatted := _format_detail_value(details, label=label, key=key, unit=unit))
    )
    return ", ".join(values) if values else "-"


def _format_detail_value(
    details: dict[str, Any],
    *,
    label: str,
    key: str,
    unit: str,
) -> str | None:
    formatted = _format_detail_scalar(details, key=key, unit=unit)
    if formatted is None:
        return None
    return f"{label} {formatted}"


def _signal_from_dict(row: dict[str, Any]) -> MarketSignal:
    source_date = date.fromisoformat(str(row["source_date"]))
    signal_time = str(row.get("signal_time", SignalTime.EOD.value))
    return MarketSignal(
        source_date=source_date,
        feature_version=str(row["feature_version"]),
        family=str(row["family"]),
        name=str(row["name"]),
        status=str(row["status"]),
        score=int(row["score"]),
        value=row.get("value"),
        unit=str(row["unit"]),
        source=str(row["data_source"]),
        observed_date=_optional_date(row.get("observed_date")),
        availability_date=_optional_date(row.get("availability_date")),
        reason=str(row["reason"]),
        details=_optional_details(row.get("details")),
        signal_time=signal_time,
        snapshot_version=_optional_str(row.get("snapshot_version"))
        or default_snapshot_version(source_date, signal_time=signal_time),
        model_version=_optional_str(row.get("model_version")) or MARKET_SIGNAL_MODEL_VERSION,
        created_at=_optional_str(row.get("created_at")),
        code_revision=_optional_str(row.get("code_revision")),
    )


def _optional_date(value: object) -> date | None:
    if value is None or value == "":
        return None
    return date.fromisoformat(str(value))


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
    return str(value)


def _optional_details(value: object) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise MarketSignalError("Market signal details must be an object")
    return dict(value)


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


def _format_score(value: int) -> str:
    return f"{value:+d}"


def _format_value(value: float | str | None, unit: str) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        if unit == "percent":
            return f"{value * 100:+.1f}%"
        if unit == "percent_level":
            return f"{value:.2f}%"
        if unit == "percentage_points":
            return f"{value:+.2f}pp"
        if unit in {"index", "ratio"}:
            return f"{value:.2f}"
        return f"{value:.4g}"
    return str(value)


def _format_table(rows: list[list[str]]) -> str:
    widths = [max(len(row[index]) for row in rows) for index in range(len(rows[0]))]
    lines = []
    for row_index, row in enumerate(rows):
        lines.append("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))
        if row_index == 0:
            lines.append("  ".join("-" * width for width in widths))
    return "\n".join(lines)
