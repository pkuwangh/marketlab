"""Portfolio policy snapshots derived from market regime and candidate evidence."""

from __future__ import annotations

import json
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path
from typing import Any

from loguru import logger

from marketlab.bulltard.validation import (
    DEFAULT_CANDIDATE_SNAPSHOT_ROOT,
    CandidateValidationError,
    CandidateValidationSnapshot,
    load_candidate_validation_snapshots,
)
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
    load_price_history,
)
from marketlab.regime import (
    DEFAULT_REGIME_OUTCOME_HORIZONS,
    DEFAULT_REGIME_SNAPSHOT_ROOT,
    REGIME_SNAPSHOT_FILENAME,
    RegimeError,
    RegimeSnapshot,
    derive_regime_action_state,
    load_regime_snapshot,
)
from marketlab.snapshots.models import (
    SignalTime,
    current_code_revision,
    default_snapshot_version,
    resolve_snapshot_path,
    signal_time_value,
    snapshot_source_dates,
    utc_timestamp,
    versioned_snapshot_path,
    write_immutable_payload,
)

DEFAULT_POLICY_SNAPSHOT_ROOT = Path("data/snapshots/portfolio/policy")
PORTFOLIO_POLICY_VERSION = "portfolio_policy_v0"
POLICY_SNAPSHOT_FILENAME = "portfolio-policy.json"
PORTFOLIO_POLICY_STATES = ("maintain", "protect", "redeploy")
POLICY_BENCHMARK_PROXY = "50/50 SPY/QQQ beta-scaled proxy; option overlays excluded"


class PortfolioPolicyError(ValueError):
    """Raised when portfolio policy cannot be computed or loaded."""


@dataclass(frozen=True, slots=True)
class PolicyCandidate:
    """One candidate shown in the portfolio policy context."""

    source_date: date
    symbol: str
    validation_status: str
    bulltard_source: str
    interest_rank: int | None
    detail_rows: int
    close: float | None
    return_20d: float | None
    relative_strength_20d_spy: float | None
    posture: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_date": self.source_date.isoformat(),
            "symbol": self.symbol,
            "validation_status": self.validation_status,
            "bulltard_source": self.bulltard_source,
            "interest_rank": self.interest_rank,
            "detail_rows": self.detail_rows,
            "close": self.close,
            "return_20d": self.return_20d,
            "relative_strength_20d_spy": self.relative_strength_20d_spy,
            "posture": self.posture,
            "reason": self.reason,
        }


@dataclass(frozen=True, slots=True)
class PortfolioPolicySnapshot:
    """Daily policy posture for the marginal tactical portfolio sleeve."""

    source_date: date
    policy_version: str
    regime: str
    regime_score: int
    regime_confidence: str
    regime_price_date: date | None
    regime_action_state: str
    regime_action_confidence: str
    regime_action_reason: str
    stretch_score: int
    washout_score: int
    stretch_pressure_score: float | None
    washout_pressure_score: float | None
    pressure_confidence: str
    policy_state: str
    policy_confidence: str
    marginal_beta_target: float
    marginal_beta_range: str
    cash_posture: str
    long_delta_stance: str
    overlay_stance: str
    put_underwriting_stance: str
    single_name_risk_budget: str
    candidate_count: int
    confirm_candidate_count: int
    watch_candidate_count: int
    avoid_candidate_count: int
    candidate_highlights: tuple[PolicyCandidate, ...]
    rationale: tuple[str, ...]
    benchmark_proxy: str = POLICY_BENCHMARK_PROXY
    signal_time: str = SignalTime.EOD.value
    snapshot_version: str | None = None
    regime_snapshot_version: str | None = None
    market_signal_snapshot_version: str | None = None
    candidate_snapshot_version: str | None = None
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
            "snapshot_type": "portfolio-policy",
            "source_date": self.source_date.isoformat(),
            "signal_date": self.source_date.isoformat(),
            "signal_time": self.signal_time,
            "snapshot_version": self.snapshot_version,
            "policy_version": self.policy_version,
            "regime_snapshot_version": self.regime_snapshot_version,
            "market_signal_snapshot_version": self.market_signal_snapshot_version,
            "candidate_snapshot_version": self.candidate_snapshot_version,
            "regime": self.regime,
            "regime_score": self.regime_score,
            "regime_confidence": self.regime_confidence,
            "regime_price_date": self.regime_price_date.isoformat()
            if self.regime_price_date
            else None,
            "regime_action_state": self.regime_action_state,
            "regime_action_confidence": self.regime_action_confidence,
            "regime_action_reason": self.regime_action_reason,
            "stretch_score": self.stretch_score,
            "washout_score": self.washout_score,
            "stretch_pressure_score": self.stretch_pressure_score,
            "washout_pressure_score": self.washout_pressure_score,
            "pressure_confidence": self.pressure_confidence,
            "policy_state": self.policy_state,
            "policy_confidence": self.policy_confidence,
            "marginal_beta_target": self.marginal_beta_target,
            "marginal_beta_range": self.marginal_beta_range,
            "cash_posture": self.cash_posture,
            "long_delta_stance": self.long_delta_stance,
            "overlay_stance": self.overlay_stance,
            "put_underwriting_stance": self.put_underwriting_stance,
            "single_name_risk_budget": self.single_name_risk_budget,
            "candidate_count": self.candidate_count,
            "confirm_candidate_count": self.confirm_candidate_count,
            "watch_candidate_count": self.watch_candidate_count,
            "avoid_candidate_count": self.avoid_candidate_count,
            "candidate_highlights": [
                candidate.to_dict() for candidate in self.candidate_highlights
            ],
            "rationale": list(self.rationale),
            "benchmark_proxy": self.benchmark_proxy,
            "created_at": self.created_at,
            "code_revision": self.code_revision,
        }


@dataclass(frozen=True, slots=True)
class PortfolioPolicySnapshotResult:
    """Result of one portfolio policy snapshot."""

    source_date: date
    snapshot: PortfolioPolicySnapshot
    snapshot_path: Path | None
    candidate_snapshots: tuple[CandidateValidationSnapshot, ...]
    table: str


@dataclass(frozen=True, slots=True)
class PortfolioPolicyBackfillResult:
    """Result of writing policy snapshots over saved regime dates."""

    start_date: date
    end_date: date
    source_dates: tuple[date, ...]
    snapshot_paths: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class DailyPolicyReportResult:
    """Human-readable daily policy report."""

    source_date: date
    policy: PortfolioPolicySnapshot
    previous_policy: PortfolioPolicySnapshot | None
    policy_snapshot_path: Path | None
    report: str


@dataclass(frozen=True, slots=True)
class PortfolioPolicyForwardOutcome:
    """One forward outcome from one policy snapshot."""

    source_date: date
    regime_price_date: date | None
    policy_state: str
    marginal_beta_target: float
    horizon_days: int
    spy_return: float | None
    qqq_return: float | None
    benchmark_return: float | None
    policy_proxy_return: float | None
    excess_return: float | None
    benchmark_max_drawdown: float | None
    policy_proxy_max_drawdown: float | None


@dataclass(frozen=True, slots=True)
class PortfolioPolicyFrequencyRow:
    """Frequency count for one policy state."""

    policy_state: str
    policy_count: int
    share: float
    avg_marginal_beta_target: float | None


@dataclass(frozen=True, slots=True)
class PortfolioPolicyOutcomeSummaryRow:
    """Aggregate forward outcome row for one policy bucket and horizon."""

    bucket: str
    horizon_days: int
    policy_count: int
    available_count: int
    avg_marginal_beta_target: float | None
    avg_benchmark_return: float | None
    avg_policy_proxy_return: float | None
    avg_excess_return: float | None
    avg_benchmark_max_drawdown: float | None
    avg_policy_proxy_max_drawdown: float | None


@dataclass(frozen=True, slots=True)
class PortfolioPolicyOutcomeResult:
    """Result of replaying policy snapshots against forward SPY/QQQ outcomes."""

    start_date: date
    end_date: date
    policies: tuple[PortfolioPolicySnapshot, ...]
    outcomes: tuple[PortfolioPolicyForwardOutcome, ...]
    frequency_rows: tuple[PortfolioPolicyFrequencyRow, ...]
    summary_rows: tuple[PortfolioPolicyOutcomeSummaryRow, ...]
    frequency_table: str
    table: str


def compute_portfolio_policy_snapshot(
    *,
    source_date: date,
    regime_snapshot_root: Path = DEFAULT_REGIME_SNAPSHOT_ROOT,
    market_signal_snapshot_root: Path = DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT,
    candidate_snapshot_root: Path = DEFAULT_CANDIDATE_SNAPSHOT_ROOT,
    policy_snapshot_root: Path = DEFAULT_POLICY_SNAPSHOT_ROOT,
    signal_time: SignalTime | str = SignalTime.EOD,
    snapshot_version: str | None = None,
    write_snapshot: bool = True,
) -> PortfolioPolicySnapshotResult:
    """Compute one portfolio policy snapshot from saved regime and candidate snapshots."""

    regime_snapshot = _load_required_regime_snapshot(
        source_date=source_date,
        snapshot_root=regime_snapshot_root,
        signal_time=signal_time,
        snapshot_version=snapshot_version,
    )
    market_signals = _load_market_signals(
        source_date=source_date,
        snapshot_root=market_signal_snapshot_root,
        signal_time=signal_time,
        snapshot_version=snapshot_version,
    )
    if _has_regime_component_boundary(market_signals):
        regime_snapshot = _regime_snapshot_with_market_signal_action(
            regime_snapshot=regime_snapshot,
            signals=market_signals,
        )
    candidate_snapshots = _load_candidate_snapshots(
        source_date=source_date,
        snapshot_root=candidate_snapshot_root,
        signal_time=signal_time,
        snapshot_version=snapshot_version,
    )
    snapshot = derive_portfolio_policy_snapshot(
        regime_snapshot=regime_snapshot,
        candidate_snapshots=candidate_snapshots,
    )
    snapshot_path = (
        write_portfolio_policy_snapshot(snapshot, snapshot_root=policy_snapshot_root)
        if write_snapshot
        else None
    )
    table = format_portfolio_policy_snapshot(snapshot)
    logger.bind(
        source_date=source_date.isoformat(),
        policy_state=snapshot.policy_state,
        marginal_beta_target=snapshot.marginal_beta_target,
        candidate_count=snapshot.candidate_count,
        snapshot_path=str(snapshot_path) if snapshot_path else None,
    ).success("Computed portfolio policy snapshot")
    return PortfolioPolicySnapshotResult(
        source_date=source_date,
        snapshot=snapshot,
        snapshot_path=snapshot_path,
        candidate_snapshots=candidate_snapshots,
        table=table,
    )


def compute_portfolio_policy_backfill(
    *,
    start_date: date,
    end_date: date,
    regime_snapshot_root: Path = DEFAULT_REGIME_SNAPSHOT_ROOT,
    market_signal_snapshot_root: Path = DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT,
    candidate_snapshot_root: Path = DEFAULT_CANDIDATE_SNAPSHOT_ROOT,
    policy_snapshot_root: Path = DEFAULT_POLICY_SNAPSHOT_ROOT,
    signal_time: SignalTime | str = SignalTime.EOD,
    snapshot_version: str | None = None,
    write_snapshot: bool = True,
) -> PortfolioPolicyBackfillResult:
    """Compute policy snapshots for every saved regime snapshot in a date range."""

    if end_date < start_date:
        raise PortfolioPolicyError("Policy backfill end date must be on or after start date")

    source_dates = _snapshot_dates_in_range(
        root=regime_snapshot_root,
        start_date=start_date,
        end_date=end_date,
        suffix=".json",
        filename=REGIME_SNAPSHOT_FILENAME,
    )
    if not source_dates:
        raise PortfolioPolicyError(f"No regime snapshots found from {start_date} to {end_date}")

    snapshot_paths: list[Path] = []
    for source_date in source_dates:
        result = compute_portfolio_policy_snapshot(
            source_date=source_date,
            regime_snapshot_root=regime_snapshot_root,
            market_signal_snapshot_root=market_signal_snapshot_root,
            candidate_snapshot_root=candidate_snapshot_root,
            policy_snapshot_root=policy_snapshot_root,
            signal_time=signal_time,
            snapshot_version=snapshot_version,
            write_snapshot=write_snapshot,
        )
        if result.snapshot_path is not None:
            snapshot_paths.append(result.snapshot_path)

    logger.bind(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        policy_count=len(source_dates),
        snapshot_count=len(snapshot_paths),
    ).success("Completed portfolio policy backfill")
    return PortfolioPolicyBackfillResult(
        start_date=start_date,
        end_date=end_date,
        source_dates=source_dates,
        snapshot_paths=tuple(snapshot_paths),
    )


def compute_daily_policy_report(
    *,
    source_date: date,
    regime_snapshot_root: Path = DEFAULT_REGIME_SNAPSHOT_ROOT,
    market_signal_snapshot_root: Path = DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT,
    candidate_snapshot_root: Path = DEFAULT_CANDIDATE_SNAPSHOT_ROOT,
    policy_snapshot_root: Path = DEFAULT_POLICY_SNAPSHOT_ROOT,
    signal_time: SignalTime | str = SignalTime.EOD,
    snapshot_version: str | None = None,
    write_snapshot: bool = True,
) -> DailyPolicyReportResult:
    """Build a concise daily report from saved regime, signal, and candidate snapshots."""

    policy_result = compute_portfolio_policy_snapshot(
        source_date=source_date,
        regime_snapshot_root=regime_snapshot_root,
        market_signal_snapshot_root=market_signal_snapshot_root,
        candidate_snapshot_root=candidate_snapshot_root,
        policy_snapshot_root=policy_snapshot_root,
        signal_time=signal_time,
        snapshot_version=snapshot_version,
        write_snapshot=write_snapshot,
    )
    previous_policy = _latest_policy_snapshot_before(
        source_date=source_date,
        snapshot_root=policy_snapshot_root,
        signal_time=signal_time,
    )
    signals = _load_market_signals(
        source_date=source_date,
        snapshot_root=market_signal_snapshot_root,
        signal_time=signal_time,
        snapshot_version=snapshot_version,
    )
    report = format_daily_policy_report(
        policy=policy_result.snapshot,
        previous_policy=previous_policy,
        signals=signals,
    )
    return DailyPolicyReportResult(
        source_date=source_date,
        policy=policy_result.snapshot,
        previous_policy=previous_policy,
        policy_snapshot_path=policy_result.snapshot_path,
        report=report,
    )


def derive_portfolio_policy_snapshot(
    *,
    regime_snapshot: RegimeSnapshot,
    candidate_snapshots: tuple[CandidateValidationSnapshot, ...] = (),
) -> PortfolioPolicySnapshot:
    """Map regime action evidence into a bounded marginal portfolio policy."""

    policy_state = _policy_state_from_action(regime_snapshot.action_state)
    settings = _policy_settings(policy_state)
    confirm_count = sum(
        1 for candidate in candidate_snapshots if candidate.validation_status == "confirm"
    )
    watch_count = sum(
        1 for candidate in candidate_snapshots if candidate.validation_status == "watch"
    )
    avoid_count = sum(
        1 for candidate in candidate_snapshots if candidate.validation_status == "avoid"
    )
    highlights = _policy_candidate_highlights(
        policy_state=policy_state,
        candidates=candidate_snapshots,
    )
    rationale = _policy_rationale(
        policy_state=policy_state,
        regime_snapshot=regime_snapshot,
        candidate_count=len(candidate_snapshots),
        confirm_count=confirm_count,
    )
    return PortfolioPolicySnapshot(
        source_date=regime_snapshot.source_date,
        policy_version=PORTFOLIO_POLICY_VERSION,
        signal_time=regime_snapshot.signal_time,
        snapshot_version=regime_snapshot.snapshot_version,
        regime_snapshot_version=regime_snapshot.snapshot_version,
        market_signal_snapshot_version=regime_snapshot.market_signal_snapshot_version,
        candidate_snapshot_version=_shared_candidate_snapshot_version(candidate_snapshots),
        regime=regime_snapshot.regime,
        regime_score=regime_snapshot.score,
        regime_confidence=regime_snapshot.confidence,
        regime_price_date=regime_snapshot.price_date,
        regime_action_state=regime_snapshot.action_state,
        regime_action_confidence=regime_snapshot.action_confidence,
        regime_action_reason=regime_snapshot.action_reason,
        stretch_score=regime_snapshot.stretch_score,
        washout_score=regime_snapshot.washout_score,
        stretch_pressure_score=regime_snapshot.stretch_pressure_score,
        washout_pressure_score=regime_snapshot.washout_pressure_score,
        pressure_confidence=regime_snapshot.pressure_confidence,
        policy_state=policy_state,
        policy_confidence=_policy_confidence(
            regime_confidence=regime_snapshot.confidence,
            action_confidence=regime_snapshot.action_confidence,
            pressure_confidence=regime_snapshot.pressure_confidence,
        ),
        marginal_beta_target=settings["marginal_beta_target"],
        marginal_beta_range=settings["marginal_beta_range"],
        cash_posture=settings["cash_posture"],
        long_delta_stance=settings["long_delta_stance"],
        overlay_stance=settings["overlay_stance"],
        put_underwriting_stance=settings["put_underwriting_stance"],
        single_name_risk_budget=_single_name_risk_budget(
            policy_state=policy_state,
            confirm_count=confirm_count,
        ),
        candidate_count=len(candidate_snapshots),
        confirm_candidate_count=confirm_count,
        watch_candidate_count=watch_count,
        avoid_candidate_count=avoid_count,
        candidate_highlights=highlights,
        rationale=rationale,
    )


def write_portfolio_policy_snapshot(
    snapshot: PortfolioPolicySnapshot,
    *,
    snapshot_root: Path = DEFAULT_POLICY_SNAPSHOT_ROOT,
    overwrite: bool = False,
) -> Path:
    """Write one portfolio policy snapshot."""

    try:
        path = versioned_snapshot_path(
            snapshot_root=snapshot_root,
            source_date=snapshot.source_date,
            signal_time=snapshot.signal_time,
            snapshot_version=snapshot.snapshot_version,
            artifact_version=snapshot.policy_version,
            filename=POLICY_SNAPSHOT_FILENAME,
        )
    except ValueError as exc:
        raise PortfolioPolicyError(str(exc)) from exc
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
    wrote = write_immutable_payload(
        path=path,
        payload=payload,
        error_cls=PortfolioPolicyError,
        overwrite=overwrite,
    )
    logger.bind(
        source_date=snapshot.source_date.isoformat(),
        policy_state=snapshot.policy_state,
        snapshot_path=str(path),
        wrote=wrote,
    ).success("Wrote portfolio policy snapshot")
    return path


def load_portfolio_policy_snapshot(
    *,
    source_date: date,
    snapshot_root: Path = DEFAULT_POLICY_SNAPSHOT_ROOT,
    signal_time: SignalTime | str = SignalTime.EOD,
    snapshot_version: str | None = None,
    policy_version: str | None = None,
) -> PortfolioPolicySnapshot | None:
    """Load one portfolio policy snapshot if present."""

    try:
        path = resolve_snapshot_path(
            snapshot_root=snapshot_root,
            source_date=source_date,
            signal_time=signal_time,
            snapshot_version=snapshot_version,
            artifact_version=policy_version,
            filename=POLICY_SNAPSHOT_FILENAME,
            legacy_suffix=".json",
        )
    except ValueError as exc:
        raise PortfolioPolicyError(str(exc)) from exc
    if path is None:
        return None
    try:
        return _policy_snapshot_from_dict(json.loads(path.read_text(encoding="utf-8")))
    except OSError as exc:
        raise PortfolioPolicyError(f"Failed to read portfolio policy snapshot: {path}") from exc
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as exc:
        raise PortfolioPolicyError(f"Invalid portfolio policy snapshot file: {path}") from exc


def compute_portfolio_policy_outcomes(
    *,
    start_date: date,
    end_date: date,
    policy_snapshot_root: Path = DEFAULT_POLICY_SNAPSHOT_ROOT,
    price_root: Path = DEFAULT_PRICE_OBSERVATIONS_ROOT,
    horizons: tuple[int, ...] = DEFAULT_REGIME_OUTCOME_HORIZONS,
) -> PortfolioPolicyOutcomeResult:
    """Replay policy snapshots against a fixed 50/50 SPY/QQQ beta-scaled benchmark."""

    if end_date < start_date:
        raise PortfolioPolicyError("Policy outcome end date must be on or after start date")

    policies = _load_policy_snapshots_in_range(
        start_date=start_date,
        end_date=end_date,
        snapshot_root=policy_snapshot_root,
    )
    if not policies:
        raise PortfolioPolicyError(
            f"No portfolio policy snapshots found from {start_date} to {end_date}"
        )

    histories = _load_price_histories(price_root=price_root)
    outcomes = tuple(
        outcome
        for policy in policies
        for outcome in _policy_forward_outcomes(
            policy=policy,
            histories=histories,
            horizons=horizons,
        )
    )
    frequency_rows = summarize_policy_frequency(policies)
    summary_rows = summarize_policy_outcomes(outcomes)
    frequency_table = format_policy_frequency(frequency_rows)
    table = format_policy_outcome_summary(summary_rows)
    logger.bind(
        start_date=start_date.isoformat(),
        end_date=end_date.isoformat(),
        policy_count=len(policies),
        outcome_count=len(outcomes),
    ).success("Computed portfolio policy outcomes")
    return PortfolioPolicyOutcomeResult(
        start_date=start_date,
        end_date=end_date,
        policies=policies,
        outcomes=outcomes,
        frequency_rows=frequency_rows,
        summary_rows=summary_rows,
        frequency_table=frequency_table,
        table=table,
    )


def summarize_policy_frequency(
    policies: tuple[PortfolioPolicySnapshot, ...],
) -> tuple[PortfolioPolicyFrequencyRow, ...]:
    """Summarize policy state frequency."""

    total = len(policies)
    rows: list[PortfolioPolicyFrequencyRow] = []
    for state in PORTFOLIO_POLICY_STATES:
        state_policies = tuple(policy for policy in policies if policy.policy_state == state)
        rows.append(
            PortfolioPolicyFrequencyRow(
                policy_state=state,
                policy_count=len(state_policies),
                share=len(state_policies) / total if total else 0.0,
                avg_marginal_beta_target=_average(
                    policy.marginal_beta_target for policy in state_policies
                ),
            )
        )
    return tuple(rows)


def summarize_policy_outcomes(
    outcomes: tuple[PortfolioPolicyForwardOutcome, ...],
) -> tuple[PortfolioPolicyOutcomeSummaryRow, ...]:
    """Summarize forward outcomes by policy bucket."""

    buckets: dict[str, list[PortfolioPolicyForwardOutcome]] = {"all": list(outcomes)}
    for outcome in outcomes:
        buckets.setdefault(f"policy:{outcome.policy_state}", []).append(outcome)

    rows: list[PortfolioPolicyOutcomeSummaryRow] = []
    for bucket in sorted(buckets):
        bucket_outcomes = tuple(buckets[bucket])
        for horizon in sorted({outcome.horizon_days for outcome in bucket_outcomes}):
            horizon_outcomes = tuple(
                outcome for outcome in bucket_outcomes if outcome.horizon_days == horizon
            )
            available = tuple(
                outcome for outcome in horizon_outcomes if outcome.benchmark_return is not None
            )
            rows.append(
                PortfolioPolicyOutcomeSummaryRow(
                    bucket=bucket,
                    horizon_days=horizon,
                    policy_count=len(horizon_outcomes),
                    available_count=len(available),
                    avg_marginal_beta_target=_average(
                        outcome.marginal_beta_target for outcome in horizon_outcomes
                    ),
                    avg_benchmark_return=_average(
                        outcome.benchmark_return for outcome in available
                    ),
                    avg_policy_proxy_return=_average(
                        outcome.policy_proxy_return for outcome in available
                    ),
                    avg_excess_return=_average(outcome.excess_return for outcome in available),
                    avg_benchmark_max_drawdown=_average(
                        outcome.benchmark_max_drawdown for outcome in available
                    ),
                    avg_policy_proxy_max_drawdown=_average(
                        outcome.policy_proxy_max_drawdown for outcome in available
                    ),
                )
            )
    return tuple(rows)


def format_portfolio_policy_snapshot(snapshot: PortfolioPolicySnapshot) -> str:
    """Format one policy snapshot."""

    rows = [
        ["field", "value"],
        ["policy_state", snapshot.policy_state],
        ["policy_confidence", snapshot.policy_confidence],
        ["marginal_beta_target", f"{snapshot.marginal_beta_target:.2f}"],
        ["marginal_beta_range", snapshot.marginal_beta_range],
        ["cash_posture", snapshot.cash_posture],
        ["long_delta_stance", snapshot.long_delta_stance],
        ["overlay_stance", snapshot.overlay_stance],
        ["put_underwriting_stance", snapshot.put_underwriting_stance],
        ["single_name_risk_budget", snapshot.single_name_risk_budget],
        ["candidate_count", str(snapshot.candidate_count)],
        ["confirm_candidate_count", str(snapshot.confirm_candidate_count)],
        ["watch_candidate_count", str(snapshot.watch_candidate_count)],
        ["avoid_candidate_count", str(snapshot.avoid_candidate_count)],
    ]
    return _format_table(rows)


def format_daily_policy_report(
    *,
    policy: PortfolioPolicySnapshot,
    previous_policy: PortfolioPolicySnapshot | None,
    signals: tuple[MarketSignal, ...] = (),
) -> str:
    """Format a concise daily policy report."""

    lines = [
        f"MarketLab daily policy report - {policy.source_date.isoformat()}",
        "",
        "Portfolio posture",
        format_portfolio_policy_snapshot(policy),
        "",
        "Regime context",
        _format_table(
            [
                ["field", "value"],
                ["regime", policy.regime],
                ["regime_score", str(policy.regime_score)],
                ["regime_confidence", policy.regime_confidence],
                ["regime_action_state", policy.regime_action_state],
                ["regime_action_confidence", policy.regime_action_confidence],
                ["stretch_pressure", _format_score(policy.stretch_pressure_score)],
                ["washout_pressure", _format_score(policy.washout_pressure_score)],
                ["pressure_confidence", policy.pressure_confidence],
                ["change", _policy_change_text(policy, previous_policy)],
            ]
        ),
    ]
    if signals:
        lines.extend(("", "Market signals", _format_market_signal_summary(signals)))
    if policy.candidate_highlights:
        lines.extend(
            ("", "Candidate sleeve", _format_policy_candidates(policy.candidate_highlights))
        )
    else:
        lines.extend(("", "Candidate sleeve", "No validated Bulltard candidate snapshot found."))
    lines.extend(("", "Rationale", _format_rationale(policy.rationale)))
    return "\n".join(lines)


def format_policy_frequency(rows: tuple[PortfolioPolicyFrequencyRow, ...]) -> str:
    """Format policy state frequency."""

    if not rows:
        return "No portfolio policy rows found."
    table = [["policy_state", "count", "share", "avg_beta"]]
    for row in rows:
        table.append(
            [
                row.policy_state,
                str(row.policy_count),
                _format_share(row.share),
                _format_optional_float(row.avg_marginal_beta_target),
            ]
        )
    return _format_table(table)


def format_policy_outcome_summary(
    rows: tuple[PortfolioPolicyOutcomeSummaryRow, ...],
) -> str:
    """Format policy outcome summary rows."""

    available_rows = tuple(row for row in rows if row.available_count > 0)
    if not available_rows:
        return "No available portfolio policy outcome rows found."

    table = [
        [
            "bucket",
            "horizon",
            "policies",
            "available",
            "avg_beta",
            "benchmark",
            "policy",
            "excess",
            "bench_dd",
            "policy_dd",
        ]
    ]
    for row in available_rows:
        table.append(
            [
                row.bucket,
                f"{row.horizon_days}d",
                str(row.policy_count),
                str(row.available_count),
                _format_optional_float(row.avg_marginal_beta_target),
                _format_percent(row.avg_benchmark_return),
                _format_percent(row.avg_policy_proxy_return),
                _format_percent(row.avg_excess_return),
                _format_drawdown(row.avg_benchmark_max_drawdown),
                _format_drawdown(row.avg_policy_proxy_max_drawdown),
            ]
        )
    return _format_table(table)


def _load_required_regime_snapshot(
    *,
    source_date: date,
    snapshot_root: Path,
    signal_time: SignalTime | str = SignalTime.EOD,
    snapshot_version: str | None = None,
) -> RegimeSnapshot:
    try:
        snapshot = load_regime_snapshot(
            source_date=source_date,
            snapshot_root=snapshot_root,
            signal_time=signal_time,
            snapshot_version=snapshot_version,
        )
    except RegimeError as exc:
        raise PortfolioPolicyError(str(exc)) from exc
    if snapshot is None:
        raise PortfolioPolicyError(f"No regime snapshot found for {source_date}")
    return snapshot


def _load_candidate_snapshots(
    *,
    source_date: date,
    snapshot_root: Path,
    signal_time: SignalTime | str = SignalTime.EOD,
    snapshot_version: str | None = None,
) -> tuple[CandidateValidationSnapshot, ...]:
    try:
        return load_candidate_validation_snapshots(
            source_date=source_date,
            snapshot_root=snapshot_root,
            signal_time=signal_time,
            snapshot_version=snapshot_version,
        )
    except CandidateValidationError as exc:
        raise PortfolioPolicyError(str(exc)) from exc


def _load_market_signals(
    *,
    source_date: date,
    snapshot_root: Path,
    signal_time: SignalTime | str = SignalTime.EOD,
    snapshot_version: str | None = None,
) -> tuple[MarketSignal, ...]:
    try:
        return load_market_signal_snapshot(
            source_date=source_date,
            snapshot_root=snapshot_root,
            signal_time=signal_time,
            snapshot_version=snapshot_version,
        )
    except MarketSignalError as exc:
        raise PortfolioPolicyError(str(exc)) from exc


def _policy_state_from_action(action_state: str) -> str:
    if action_state == "scale_down_protect":
        return "protect"
    if action_state == "scale_up_redeploy":
        return "redeploy"
    return "maintain"


def _regime_snapshot_with_market_signal_action(
    *,
    regime_snapshot: RegimeSnapshot,
    signals: tuple[MarketSignal, ...],
) -> RegimeSnapshot:
    action = derive_regime_action_state(snapshot=regime_snapshot, signals=signals)
    return replace(
        regime_snapshot,
        action_version=action.action_version,
        action_state=action.state,
        stretch_score=action.stretch_score,
        washout_score=action.washout_score,
        action_confidence=action.confidence,
        action_reason=action.reason,
        market_signal_snapshot_version=_shared_market_signal_snapshot_version(signals),
    )


def _has_regime_component_boundary(signals: tuple[MarketSignal, ...]) -> bool:
    return all(
        _market_signal_by_name(signals, family=family, name="price_proxy") is not None
        for family in ("trend", "volatility", "breadth", "credit")
    )


def _market_signal_by_name(
    signals: tuple[MarketSignal, ...],
    *,
    family: str,
    name: str,
) -> MarketSignal | None:
    for signal in signals:
        if signal.family == family and signal.name == name:
            return signal
    return None


def _policy_settings(policy_state: str) -> dict[str, Any]:
    if policy_state == "protect":
        return {
            "marginal_beta_target": 0.90,
            "marginal_beta_range": "0.85-0.95 tactical beta",
            "cash_posture": "raise or preserve cash; do not spend dry powder casually",
            "long_delta_stance": "avoid fresh long calls unless setup is exceptional",
            "overlay_stance": "consider covered calls against part of existing exposure",
            "put_underwriting_stance": "tighten put-selling standards and prefer defined risk",
        }
    if policy_state == "redeploy":
        return {
            "marginal_beta_target": 1.15,
            "marginal_beta_range": "1.05-1.20 tactical beta",
            "cash_posture": "deploy dry powder in tranches after washout confirmation",
            "long_delta_stance": "consider 60-90 DTE calls or call spreads",
            "overlay_stance": "avoid capping too much rebound upside",
            "put_underwriting_stance": "consider cash-secured puts or defined-risk put spreads",
        }
    return {
        "marginal_beta_target": 1.00,
        "marginal_beta_range": "0.95-1.05 tactical beta",
        "cash_posture": "maintain current cash reserve",
        "long_delta_stance": "normal selectivity for new long-delta risk",
        "overlay_stance": "selective overlays only",
        "put_underwriting_stance": "normal standards; no forced underwriting",
    }


def _single_name_risk_budget(*, policy_state: str, confirm_count: int) -> str:
    if policy_state == "protect":
        return "reduced; confirmed liquid setups only"
    if policy_state == "redeploy":
        if confirm_count:
            return "expanded for confirmed liquid setups, still tranche entries"
        return "expanded market posture, but no validated single-name setup yet"
    return "normal bounded sleeve"


def _policy_confidence(
    *,
    regime_confidence: str,
    action_confidence: str,
    pressure_confidence: str,
) -> str:
    levels = {"low": 0, "medium": 1, "high": 2}
    score = min(
        levels.get(regime_confidence, 0),
        levels.get(action_confidence, 0),
        levels.get(pressure_confidence, 0),
    )
    return ("low", "medium", "high")[score]


def _policy_rationale(
    *,
    policy_state: str,
    regime_snapshot: RegimeSnapshot,
    candidate_count: int,
    confirm_count: int,
) -> tuple[str, ...]:
    rationale = [
        f"Regime action state is {regime_snapshot.action_state}: {regime_snapshot.action_reason}",
        (
            "Normalized pressure scores: stretch "
            f"{_format_score(regime_snapshot.stretch_pressure_score)}, washout "
            f"{_format_score(regime_snapshot.washout_pressure_score)}"
        ),
    ]
    if policy_state == "protect":
        rationale.append("Policy preserves the core and reduces only marginal tactical risk.")
    elif policy_state == "redeploy":
        rationale.append("Policy adds exposure in tranches; it is not an all-in market call.")
    else:
        rationale.append("No rare-action threshold crossed, so the default is no portfolio move.")

    if candidate_count:
        rationale.append(
            f"Candidate context: {confirm_count} confirmed out of {candidate_count} validated rows."
        )
    else:
        rationale.append("No validated single-name candidate snapshot is available for this date.")
    return tuple(rationale)


def _policy_candidate_highlights(
    *,
    policy_state: str,
    candidates: tuple[CandidateValidationSnapshot, ...],
    limit: int = 8,
) -> tuple[PolicyCandidate, ...]:
    sorted_candidates = sorted(candidates, key=_candidate_sort_key)
    return tuple(
        _policy_candidate(policy_state=policy_state, candidate=candidate)
        for candidate in sorted_candidates[:limit]
    )


def _shared_candidate_snapshot_version(
    candidates: tuple[CandidateValidationSnapshot, ...],
) -> str | None:
    versions = {
        getattr(candidate, "snapshot_version", None)
        for candidate in candidates
        if getattr(candidate, "snapshot_version", None)
    }
    if len(versions) == 1:
        return versions.pop()
    if len(versions) > 1:
        return "mixed"
    return None


def _shared_market_signal_snapshot_version(signals: tuple[MarketSignal, ...]) -> str | None:
    versions = {signal.snapshot_version for signal in signals if signal.snapshot_version}
    if len(versions) == 1:
        return versions.pop()
    if len(versions) > 1:
        return "mixed"
    return None


def _policy_candidate(
    *,
    policy_state: str,
    candidate: CandidateValidationSnapshot,
) -> PolicyCandidate:
    return PolicyCandidate(
        source_date=candidate.source_date,
        symbol=candidate.symbol,
        validation_status=candidate.validation_status,
        bulltard_source=candidate.bulltard_source,
        interest_rank=candidate.interest_rank,
        detail_rows=candidate.detail_rows,
        close=candidate.close,
        return_20d=candidate.return_20d,
        relative_strength_20d_spy=candidate.relative_strength_20d_spy,
        posture=_candidate_posture(policy_state=policy_state, candidate=candidate),
        reason=",".join(candidate.validation_reasons) or "no_validation_reason",
    )


def _candidate_sort_key(candidate: CandidateValidationSnapshot) -> tuple[int, int, int, float]:
    status_order = {"confirm": 0, "watch": 1, "avoid": 2}
    return (
        status_order.get(candidate.validation_status, 3),
        candidate.interest_rank if candidate.interest_rank is not None else 9999,
        -candidate.detail_rows,
        -(candidate.ranked_score or 0.0),
    )


def _candidate_posture(
    *,
    policy_state: str,
    candidate: CandidateValidationSnapshot,
) -> str:
    if candidate.validation_status == "avoid":
        return "reject"
    if policy_state == "protect":
        return "reduced_watch" if candidate.validation_status == "confirm" else "defer"
    if policy_state == "redeploy":
        return "active_research" if candidate.validation_status == "confirm" else "entry_watch"
    return "research" if candidate.validation_status == "confirm" else "watch"


def _load_policy_snapshots_in_range(
    *,
    start_date: date,
    end_date: date,
    snapshot_root: Path,
) -> tuple[PortfolioPolicySnapshot, ...]:
    snapshots: list[PortfolioPolicySnapshot] = []
    for source_date in _snapshot_dates_in_range(
        root=snapshot_root,
        start_date=start_date,
        end_date=end_date,
        suffix=".json",
        filename=POLICY_SNAPSHOT_FILENAME,
    ):
        snapshot = load_portfolio_policy_snapshot(
            source_date=source_date,
            snapshot_root=snapshot_root,
        )
        if snapshot is not None:
            snapshots.append(snapshot)
    return tuple(snapshots)


def _snapshot_dates_in_range(
    *,
    root: Path,
    start_date: date,
    end_date: date,
    suffix: str,
    filename: str,
) -> tuple[date, ...]:
    dates: list[date] = []
    for source_date in snapshot_source_dates(
        snapshot_root=root,
        legacy_suffix=suffix,
        filename=filename,
    ):
        if start_date <= source_date <= end_date:
            dates.append(source_date)
    return tuple(dates)


def _latest_policy_snapshot_before(
    *,
    source_date: date,
    snapshot_root: Path,
    signal_time: SignalTime | str = SignalTime.EOD,
) -> PortfolioPolicySnapshot | None:
    prior_dates = tuple(
        candidate_date
        for candidate_date in _snapshot_dates_in_range(
            root=snapshot_root,
            start_date=date.min,
            end_date=source_date,
            suffix=".json",
            filename=POLICY_SNAPSHOT_FILENAME,
        )
        if candidate_date < source_date
    )
    if not prior_dates:
        return None
    return load_portfolio_policy_snapshot(
        source_date=prior_dates[-1],
        snapshot_root=snapshot_root,
        signal_time=signal_time,
    )


def _load_price_histories(
    *,
    price_root: Path,
) -> dict[str, tuple[DailyPriceObservation, ...]]:
    histories: dict[str, tuple[DailyPriceObservation, ...]] = {}
    for symbol in ("SPY", "QQQ"):
        try:
            histories[symbol] = load_price_history(symbol=symbol, price_root=price_root)
        except PriceDataError as exc:
            raise PortfolioPolicyError(str(exc)) from exc
    return histories


def _policy_forward_outcomes(
    *,
    policy: PortfolioPolicySnapshot,
    histories: dict[str, tuple[DailyPriceObservation, ...]],
    horizons: tuple[int, ...],
) -> tuple[PortfolioPolicyForwardOutcome, ...]:
    spy_history = histories.get("SPY", ())
    qqq_history = histories.get("QQQ", ())
    spy_index = _exact_date_index(spy_history, policy.regime_price_date)
    qqq_index = _exact_date_index(qqq_history, policy.regime_price_date)
    outcomes = []
    for horizon in horizons:
        spy_return = _forward_return(spy_history, index=spy_index, horizon=horizon)
        qqq_return = _forward_return(qqq_history, index=qqq_index, horizon=horizon)
        spy_drawdown = _forward_max_drawdown(spy_history, index=spy_index, horizon=horizon)
        qqq_drawdown = _forward_max_drawdown(qqq_history, index=qqq_index, horizon=horizon)
        benchmark_return = _basket_value(spy_return, qqq_return)
        benchmark_drawdown = _basket_value(spy_drawdown, qqq_drawdown)
        policy_return = (
            benchmark_return * policy.marginal_beta_target if benchmark_return is not None else None
        )
        policy_drawdown = (
            benchmark_drawdown * policy.marginal_beta_target
            if benchmark_drawdown is not None
            else None
        )
        outcomes.append(
            PortfolioPolicyForwardOutcome(
                source_date=policy.source_date,
                regime_price_date=policy.regime_price_date,
                policy_state=policy.policy_state,
                marginal_beta_target=policy.marginal_beta_target,
                horizon_days=horizon,
                spy_return=spy_return,
                qqq_return=qqq_return,
                benchmark_return=benchmark_return,
                policy_proxy_return=policy_return,
                excess_return=(
                    policy_return - benchmark_return
                    if policy_return is not None and benchmark_return is not None
                    else None
                ),
                benchmark_max_drawdown=benchmark_drawdown,
                policy_proxy_max_drawdown=policy_drawdown,
            )
        )
    return tuple(outcomes)


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


def _basket_value(left: float | None, right: float | None) -> float | None:
    if left is None or right is None:
        return None
    return 0.5 * left + 0.5 * right


def _policy_snapshot_from_dict(row: dict[str, Any]) -> PortfolioPolicySnapshot:
    source_date = date.fromisoformat(str(row["source_date"]))
    signal_time = str(row.get("signal_time", SignalTime.EOD.value))
    return PortfolioPolicySnapshot(
        source_date=source_date,
        policy_version=str(row["policy_version"]),
        signal_time=signal_time,
        snapshot_version=_optional_str(row.get("snapshot_version"))
        or default_snapshot_version(source_date, signal_time=signal_time),
        regime_snapshot_version=_optional_str(row.get("regime_snapshot_version")),
        market_signal_snapshot_version=_optional_str(row.get("market_signal_snapshot_version")),
        candidate_snapshot_version=_optional_str(row.get("candidate_snapshot_version")),
        regime=str(row["regime"]),
        regime_score=int(row["regime_score"]),
        regime_confidence=str(row["regime_confidence"]),
        regime_price_date=_optional_date(row.get("regime_price_date")),
        regime_action_state=str(row["regime_action_state"]),
        regime_action_confidence=str(row["regime_action_confidence"]),
        regime_action_reason=str(row["regime_action_reason"]),
        stretch_score=int(row["stretch_score"]),
        washout_score=int(row["washout_score"]),
        stretch_pressure_score=_optional_float(row.get("stretch_pressure_score")),
        washout_pressure_score=_optional_float(row.get("washout_pressure_score")),
        pressure_confidence=str(row["pressure_confidence"]),
        policy_state=str(row["policy_state"]),
        policy_confidence=str(row["policy_confidence"]),
        marginal_beta_target=float(row["marginal_beta_target"]),
        marginal_beta_range=str(row["marginal_beta_range"]),
        cash_posture=str(row["cash_posture"]),
        long_delta_stance=str(row["long_delta_stance"]),
        overlay_stance=str(row["overlay_stance"]),
        put_underwriting_stance=str(row["put_underwriting_stance"]),
        single_name_risk_budget=str(row["single_name_risk_budget"]),
        candidate_count=int(row["candidate_count"]),
        confirm_candidate_count=int(row["confirm_candidate_count"]),
        watch_candidate_count=int(row["watch_candidate_count"]),
        avoid_candidate_count=int(row["avoid_candidate_count"]),
        candidate_highlights=tuple(
            _policy_candidate_from_dict(candidate)
            for candidate in row.get("candidate_highlights", ())
        ),
        rationale=tuple(str(reason) for reason in row.get("rationale", ())),
        benchmark_proxy=str(row.get("benchmark_proxy", POLICY_BENCHMARK_PROXY)),
        created_at=_optional_str(row.get("created_at")),
        code_revision=_optional_str(row.get("code_revision")),
    )


def _policy_candidate_from_dict(row: dict[str, Any]) -> PolicyCandidate:
    return PolicyCandidate(
        source_date=date.fromisoformat(str(row["source_date"])),
        symbol=str(row["symbol"]),
        validation_status=str(row["validation_status"]),
        bulltard_source=str(row["bulltard_source"]),
        interest_rank=_optional_int(row.get("interest_rank")),
        detail_rows=int(row["detail_rows"]),
        close=_optional_float(row.get("close")),
        return_20d=_optional_float(row.get("return_20d")),
        relative_strength_20d_spy=_optional_float(row.get("relative_strength_20d_spy")),
        posture=str(row["posture"]),
        reason=str(row["reason"]),
    )


def _policy_change_text(
    policy: PortfolioPolicySnapshot,
    previous_policy: PortfolioPolicySnapshot | None,
) -> str:
    if previous_policy is None:
        return "no prior policy snapshot"
    if previous_policy.policy_state == policy.policy_state:
        return f"unchanged from {previous_policy.source_date.isoformat()}"
    return (
        f"{previous_policy.policy_state} on {previous_policy.source_date.isoformat()} "
        f"to {policy.policy_state}"
    )


def _format_market_signal_summary(signals: tuple[MarketSignal, ...]) -> str:
    rows = [["family", "signal", "score", "status", "value", "reason"]]
    for signal in signals:
        rows.append(
            [
                signal.family,
                signal.name,
                f"{signal.score:+d}",
                signal.status,
                _format_signal_value(signal.value, signal.unit),
                signal.reason,
            ]
        )
    return _format_table(rows)


def _format_policy_candidates(candidates: tuple[PolicyCandidate, ...]) -> str:
    rows = [["symbol", "status", "posture", "source", "ret20", "rs_spy20", "reason"]]
    for candidate in candidates:
        rows.append(
            [
                candidate.symbol,
                candidate.validation_status,
                candidate.posture,
                candidate.bulltard_source,
                _format_percent(candidate.return_20d),
                _format_percent(candidate.relative_strength_20d_spy),
                candidate.reason,
            ]
        )
    return _format_table(rows)


def _format_rationale(rationale: tuple[str, ...]) -> str:
    return "\n".join(f"- {reason}" for reason in rationale)


def _format_signal_value(value: float | str | None, unit: str) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        if unit == "percent":
            return _format_percent(value)
        if unit == "percent_level":
            return f"{value:.2f}%"
        if unit == "percentage_points":
            return f"{value:+.2f}pp"
        if unit in {"index", "ratio"}:
            return f"{value:.2f}"
        return f"{value:.4g}"
    return str(value)


def _optional_date(value: object) -> date | None:
    if value is None or value == "":
        return None
    return date.fromisoformat(str(value))


def _optional_float(value: object) -> float | None:
    if value is None or value == "":
        return None
    return float(value)


def _optional_int(value: object) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


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


def _format_optional_float(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}"


def _format_percent(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:+.1f}%"


def _format_drawdown(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.1f}%"


def _format_score(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.2f}"


def _format_share(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value * 100:.1f}%"


def _format_table(rows: list[list[str]]) -> str:
    widths = [max(len(row[index]) for row in rows) for index in range(len(rows[0]))]
    lines = []
    for row_index, row in enumerate(rows):
        lines.append("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))
        if row_index == 0:
            lines.append("  ".join("-" * width for width in widths))
    return "\n".join(lines)
