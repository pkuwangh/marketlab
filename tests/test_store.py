import json
from datetime import date
from pathlib import Path

from marketlab.bulltard.validation import (
    CandidateValidationSnapshot,
    write_candidate_validation_snapshots,
)
from marketlab.market_series import MarketSeriesObservation, write_market_series_observations
from marketlab.market_signals import MarketSignal, write_market_signal_snapshot
from marketlab.prices import DailyPriceObservation, write_price_observations
from marketlab.regime import (
    RegimeComponentScore,
    RegimePressureFeature,
    RegimePressureModule,
    RegimeSnapshot,
    write_regime_snapshot,
)
from marketlab.store import (
    format_query_result,
    query_research_store,
    refresh_research_store,
    summarize_research_store,
)


def test_refresh_research_store_builds_query_tables(tmp_path: Path) -> None:
    source_date = date(2026, 8, 28)
    price_root = tmp_path / "prices"
    market_series_root = tmp_path / "market-series"
    regime_root = tmp_path / "regime"
    signal_root = tmp_path / "signals"
    candidate_root = tmp_path / "candidates"
    bulltard_root = tmp_path / "observations" / "bulltard"
    db_path = tmp_path / "marketlab.duckdb"
    parquet_root = tmp_path / "parquet"

    write_price_observations(
        (
            DailyPriceObservation(
                source="fixture",
                source_symbol="SPY",
                symbol="SPY",
                observed_date=source_date,
                open=100.0,
                high=101.0,
                low=99.0,
                close=100.5,
                volume=1_000_000,
                adjusted_close=100.5,
            ),
        ),
        output_root=price_root,
    )
    _write_jsonl(
        price_root / "SPY.legacy.jsonl",
        [
            {
                "source": "fixture",
                "source_symbol": "SPY",
                "symbol": "SPY",
                "date": "2026-08-28",
                "availability_date": "2026-08-28",
                "retrieved_at": "2026-08-28T22:00:00Z",
                "open": 100.0,
                "high": 102.0,
                "low": 99.0,
                "close": 101.5,
                "volume": 1_100_000,
                "adjusted_close": 101.5,
            }
        ],
    )
    write_market_series_observations(
        (
            MarketSeriesObservation(
                source="fixture",
                source_series_id="NFCI",
                series_id="NFCI",
                observed_date=source_date,
                availability_date=source_date,
                value=-0.3,
                unit="index",
            ),
        ),
        output_root=market_series_root,
    )
    write_regime_snapshot(
        RegimeSnapshot(
            source_date=source_date,
            feature_version="fixture_features",
            model_version="fixture_model",
            price_date=source_date,
            regime="risk_on",
            score=4,
            confidence="medium",
            components=(
                RegimeComponentScore(
                    name="trend",
                    score=2,
                    status="constructive",
                    reason="fixture",
                ),
            ),
            missing_symbols=(),
            spy_return_20d=0.03,
            spy_return_60d=0.05,
            spy_ma50_distance=0.02,
            spy_ma200_distance=0.08,
            spy_realized_vol_20d=0.12,
            qqq_return_20d=0.04,
            qqq_ma50_distance=0.03,
            qqq_ma200_distance=0.10,
            rsp_spy_relative_20d=0.0,
            iwm_spy_relative_20d=-0.01,
            hyg_tlt_relative_20d=0.0,
            vix_close=14.0,
            vvix_close=88.0,
            action_state="no_change",
            action_confidence="medium",
            action_reason="fixture",
            stretch_pressure_score=0.4,
            washout_pressure_score=0.2,
            pressure_features=(
                RegimePressureFeature(
                    source_date=source_date,
                    pressure_version="fixture_pressure",
                    family="trend",
                    name="spy_return_20d",
                    raw_value=0.03,
                    percentile=0.7,
                    normalized_score=0.4,
                    stretch_score=0.4,
                    washout_score=0.0,
                    sample_count=100,
                    reason="fixture",
                ),
            ),
            pressure_modules=(
                RegimePressureModule(
                    source_date=source_date,
                    pressure_version="fixture_pressure",
                    family="trend",
                    name="trend_extension",
                    stretch_score=0.4,
                    washout_score=0.0,
                    feature_count=1,
                    feature_names=("spy_return_20d",),
                    reason="fixture module",
                ),
            ),
        ),
        snapshot_root=regime_root,
    )
    write_market_signal_snapshot(
        (
            MarketSignal(
                source_date=source_date,
                feature_version="fixture_signal",
                family="volatility",
                name="vol_of_vol",
                status="calm",
                score=1,
                value=88.0,
                unit="index",
                source="fixture",
                observed_date=source_date,
                availability_date=source_date,
                reason="fixture",
            ),
        ),
        snapshot_root=signal_root,
    )
    write_candidate_validation_snapshots(
        (
            CandidateValidationSnapshot(
                source_date=source_date,
                feature_version="fixture_candidate",
                symbol="META",
                bulltard_source="interest#1",
                ranked_side=None,
                ranked_score=None,
                ranked_trade_count=None,
                ranked_premium=None,
                interest_rank=1,
                detail_rows=5,
                price_date=source_date,
                close=700.0,
                dollar_volume=10_000_000_000.0,
                return_5d=0.01,
                return_20d=0.04,
                return_60d=0.09,
                ma20_distance=0.02,
                ma50_distance=0.05,
                ma200_distance=0.20,
                drawdown_60d=-0.03,
                relative_strength_20d_spy=0.02,
                relative_strength_20d_qqq=0.01,
                underlying_liquidity_status="liquid",
                options_liquidity_status="unknown",
                validation_status="confirm",
                validation_reasons=("positive_20d", "rs_spy_positive"),
            ),
        ),
        snapshot_root=candidate_root,
        source_date=source_date,
    )
    _write_jsonl(
        bulltard_root / "ranked_option_trades" / "2026-08-28.jsonl",
        [
            {
                "source": "bulltard",
                "source_date": "2026-08-28",
                "view": "ranked-option-trades",
                "ingest_id": "fixture-ingest",
                "parser_version": "fixture_parser",
                "side": "bullish",
                "symbol": "META",
                "trade_count": 12,
                "last_trade_date": "2026-08-28",
                "avg_dte": 45.0,
                "score": 10.0,
                "premium": 24_000_000.0,
            }
        ],
    )
    _write_jsonl(
        bulltard_root / "trades_of_interest" / "2026-08-28.jsonl",
        [
            {
                "source": "bulltard",
                "source_date": "2026-08-28",
                "view": "trades-of-interest",
                "ingest_id": "fixture-ingest",
                "parser_version": "fixture_parser",
                "rank": 1,
                "symbol": "META",
                "note": "fixture note",
            }
        ],
    )
    _write_jsonl(
        bulltard_root / "ticker_flow" / "META" / "2026-08-28.jsonl",
        [
            {
                "source": "bulltard",
                "source_date": "2026-08-28",
                "view": "ticker-flow-history",
                "ingest_id": "fixture-ingest",
                "parser_version": "fixture_parser",
                "symbol": "META",
                "traded_at": "2026-08-28T10:30",
                "order_type": "Calls Bought",
                "side": "bullish",
                "contract": "META 2026-10-16 800C",
                "contract_type": "call",
                "expiry": "2026-10-16",
                "contracts": 100,
                "premium": 250_000.0,
                "is_older": False,
            }
        ],
    )
    _write_json(
        bulltard_root / "ranked_option_trades" / "2026-08-28.meta.json",
        {
            "source": "bulltard",
            "record_type": "bulltard-ingest-run",
            "schema_version": "bulltard_ingest_v0",
            "ingest_id": "fixture-ingest",
            "source_date": "2026-08-28",
            "retrieved_at": "2026-08-28T22:00:00Z",
            "view": "ranked-option-trades",
            "symbol": None,
            "final_url": "https://app.jamesbulltard.com/ranked_option_trades",
            "status_code": 200,
            "content_type": "text/html",
            "byte_count": 1234,
            "debug_path": "debug.html",
            "recap_path": "recap.html",
            "parser_version": "fixture_parser",
            "row_count": 1,
        },
    )

    result = refresh_research_store(
        db_path=db_path,
        price_root=price_root,
        market_series_root=market_series_root,
        regime_snapshot_root=regime_root,
        market_signal_snapshot_root=signal_root,
        candidate_snapshot_root=candidate_root,
        bulltard_observation_root=bulltard_root,
        parquet_root=parquet_root,
    )

    counts = {refresh.table_name: refresh.row_count for refresh in result.table_refreshes}
    assert counts["daily_prices"] == 1
    assert counts["market_series"] == 1
    assert counts["regime_snapshots"] == 1
    assert counts["regime_components"] == 1
    assert counts["regime_pressure_features"] == 1
    assert counts["regime_pressure_modules"] == 1
    assert counts["market_signals"] == 1
    assert counts["bulltard_ingest_runs"] == 1
    assert counts["bulltard_ranked_option_trades"] == 1
    assert counts["bulltard_trades_of_interest"] == 1
    assert counts["bulltard_ticker_flow"] == 1
    assert counts["candidate_snapshots"] == 1
    assert (parquet_root / "regime_snapshots.parquet").is_file()

    query_result = query_research_store(
        db_path=db_path,
        query=(
            "select source_date, regime, action_state, stretch_pressure_score from regime_snapshots"
        ),
    )
    assert query_result.columns == (
        "source_date",
        "regime",
        "action_state",
        "stretch_pressure_score",
    )
    assert query_result.rows == ((source_date, "risk_on", "no_change", 0.4),)
    assert "risk_on" in format_query_result(query_result)

    price_query = query_research_store(
        db_path=db_path,
        query="select close, adjusted_close, volume from daily_prices where symbol = 'SPY'",
    )
    assert price_query.rows == ((101.5, 101.5, 1_100_000),)

    summary = summarize_research_store(db_path=db_path)
    assert ("regime_snapshots", 1) in summary.rows


def _write_json(path: Path, row: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(row, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)
    path.write_text(payload, encoding="utf-8")
