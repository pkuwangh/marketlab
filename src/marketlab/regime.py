"""Market regime snapshots from daily price proxies."""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from loguru import logger

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
DEFAULT_REGIME_PRICE_SYMBOLS = ("SPY", "QQQ", "IWM", "RSP", "HYG", "TLT", "^VIX")
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
        }


@dataclass(frozen=True, slots=True)
class RegimeSnapshotResult:
    """Result of one market regime snapshot run."""

    source_date: date
    snapshot: RegimeSnapshot
    snapshot_path: Path | None
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
    snapshot_root: Path = DEFAULT_REGIME_SNAPSHOT_ROOT,
    write_snapshot: bool = True,
) -> RegimeSnapshotResult:
    """Compute and optionally persist one market regime snapshot."""

    histories = _load_histories(symbols=DEFAULT_REGIME_PRICE_SYMBOLS, price_root=price_root)
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
        confidence=_confidence(score=score, components=components),
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
    )
    snapshot_path = (
        write_regime_snapshot(snapshot, snapshot_root=snapshot_root) if write_snapshot else None
    )
    table = format_regime_snapshot(snapshot)
    logger.bind(
        source_date=source_date.isoformat(),
        price_date=snapshot.price_date.isoformat() if snapshot.price_date else None,
        regime=snapshot.regime,
        score=snapshot.score,
        confidence=snapshot.confidence,
        snapshot_path=str(snapshot_path) if snapshot_path else None,
    ).success("Computed market regime snapshot")
    return RegimeSnapshotResult(
        source_date=source_date,
        snapshot=snapshot,
        snapshot_path=snapshot_path,
        table=table,
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


def _confidence(*, score: int, components: tuple[RegimeComponentScore, ...]) -> str:
    available_components = sum(1 for component in components if component.status != "missing")
    if available_components < 3:
        return "low"
    if abs(score) >= 4:
        return "high"
    if abs(score) >= 2:
        return "medium"
    return "low"


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


def _format_score(value: int) -> str:
    return f"{value:+d}"


def _format_table(rows: list[list[str]]) -> str:
    widths = [max(len(row[index]) for row in rows) for index in range(len(rows[0]))]
    lines = []
    for row_index, row in enumerate(rows):
        lines.append("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))
        if row_index == 0:
            lines.append("  ".join("-" * width for width in widths))
    return "\n".join(lines)
