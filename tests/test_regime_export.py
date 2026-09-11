from datetime import date, datetime, timedelta
from pathlib import Path

from openpyxl import Workbook, load_workbook

from marketlab.prices import DailyPriceObservation, write_price_observations
from marketlab.regime import (
    RegimeActionFeature,
    RegimeActionModule,
    RegimeComponentScore,
    RegimePressureFeature,
    RegimePressureModule,
    RegimeSnapshot,
    write_regime_snapshot,
)
from marketlab.regime_export import export_regime_xlsx


def test_export_regime_xlsx_writes_refreshable_data_sheet(tmp_path: Path) -> None:
    snapshot_root = tmp_path / "snapshots"
    price_root = tmp_path / "prices"
    workbook_path = tmp_path / "regime.xlsx"
    first_date = date(2026, 9, 4)
    second_date = date(2026, 9, 8)
    _write_prices(price_root, symbol="SPY", start=first_date, closes=(100.0, 103.0))
    _write_prices(price_root, symbol="QQQ", start=first_date, closes=(200.0, 202.0))
    write_regime_snapshot(
        _snapshot(source_date=first_date, spy_return_20d=0.01),
        snapshot_root=snapshot_root,
    )
    write_regime_snapshot(
        _snapshot(source_date=second_date, spy_return_20d=0.03),
        snapshot_root=snapshot_root,
    )

    result = export_regime_xlsx(
        start_date=first_date,
        end_date=second_date,
        workbook_path=workbook_path,
        snapshot_root=snapshot_root,
        price_root=price_root,
    )

    assert result.row_count == 2
    assert result.column_count > 40
    workbook = load_workbook(workbook_path)
    worksheet = workbook["regime_data"]
    headers = [cell.value for cell in worksheet[1]]
    first_row = dict(zip(headers, (cell.value for cell in worksheet[2]), strict=True))
    assert _as_date(first_row["date"]) == first_date
    assert first_row["SPY_close"] == 100.0
    assert first_row["SPY_indexed_100"] == 100.0
    assert first_row["pressure__vix_close__pctile"] == 0.20
    assert first_row["pressure_module__vol_complacency__stretch"] == 0.80
    assert first_row["action__vvix_turn__protect"] == 0.70
    assert first_row["action_module__volatility_turn__redeploy"] == 0.10
    last_column = worksheet.cell(row=1, column=len(headers)).column_letter
    assert worksheet.tables["RegimeData"].ref == f"A1:{last_column}3"


def test_export_regime_xlsx_preserves_other_sheets_and_clears_stale_rows(
    tmp_path: Path,
) -> None:
    snapshot_root = tmp_path / "snapshots"
    price_root = tmp_path / "prices"
    workbook_path = tmp_path / "regime.xlsx"
    first_date = date(2026, 9, 4)
    second_date = date(2026, 9, 8)
    _write_prices(price_root, symbol="SPY", start=first_date, closes=(100.0, 103.0))
    _write_prices(price_root, symbol="QQQ", start=first_date, closes=(200.0, 202.0))
    write_regime_snapshot(_snapshot(source_date=first_date), snapshot_root=snapshot_root)
    write_regime_snapshot(_snapshot(source_date=second_date), snapshot_root=snapshot_root)

    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "manual_charts"
    worksheet["A1"] = "keep this sheet"
    workbook.save(workbook_path)
    export_regime_xlsx(
        start_date=first_date,
        end_date=second_date,
        workbook_path=workbook_path,
        snapshot_root=snapshot_root,
        price_root=price_root,
    )
    export_regime_xlsx(
        start_date=first_date,
        end_date=first_date,
        workbook_path=workbook_path,
        snapshot_root=snapshot_root,
        price_root=price_root,
    )

    refreshed = load_workbook(workbook_path)
    assert refreshed["manual_charts"]["A1"].value == "keep this sheet"
    data_sheet = refreshed["regime_data"]
    assert _as_date(data_sheet["A2"].value) == first_date
    assert data_sheet["A3"].value is None
    assert data_sheet.tables["RegimeData"].ref.endswith("2")


def _snapshot(
    *,
    source_date: date,
    spy_return_20d: float = 0.01,
) -> RegimeSnapshot:
    return RegimeSnapshot(
        source_date=source_date,
        feature_version="fixture_features",
        model_version="fixture_model",
        price_date=source_date,
        regime="risk_on",
        score=2,
        confidence="medium",
        components=(
            RegimeComponentScore(
                name="trend",
                score=2,
                status="constructive",
                reason="fixture trend",
            ),
        ),
        missing_symbols=(),
        spy_return_20d=spy_return_20d,
        spy_return_60d=0.08,
        spy_ma50_distance=0.02,
        spy_ma200_distance=0.09,
        spy_realized_vol_20d=0.12,
        qqq_return_20d=0.02,
        qqq_ma50_distance=0.03,
        qqq_ma200_distance=0.10,
        rsp_spy_relative_20d=-0.01,
        iwm_spy_relative_20d=-0.02,
        hyg_tlt_relative_20d=0.01,
        vix_close=15.0,
        vvix_close=84.0,
        vix9d_vix_ratio=0.94,
        vix_vix3m_ratio=0.78,
        sp500_above_50d=65.0,
        sp500_above_200d=70.0,
        action_state="scale_down_protect",
        action_confidence="medium",
        action_reason="fixture action",
        stretch_pressure_score=0.62,
        washout_pressure_score=0.11,
        deterioration_score=0.70,
        stabilization_score=0.10,
        protect_strength=0.70,
        redeploy_strength=0.10,
        action_score=-0.60,
        pressure_features=(
            RegimePressureFeature(
                source_date=source_date,
                pressure_version="fixture_pressure",
                family="volatility",
                name="vix_close",
                raw_value=15.0,
                percentile=0.20,
                normalized_score=0.80,
                stretch_score=0.80,
                washout_score=0.20,
                sample_count=126,
                reason="fixture pressure",
            ),
        ),
        pressure_modules=(
            RegimePressureModule(
                source_date=source_date,
                pressure_version="fixture_pressure",
                family="volatility",
                name="vol_complacency",
                stretch_score=0.80,
                washout_score=0.20,
                feature_count=1,
                feature_names=("vix_close",),
                reason="fixture pressure module",
            ),
        ),
        action_features=(
            RegimeActionFeature(
                family="volatility",
                name="vvix_turn",
                deterioration_score=0.70,
                stabilization_score=0.10,
                reason="fixture action feature",
            ),
        ),
        action_modules=(
            RegimeActionModule(
                family="volatility",
                name="volatility_turn",
                deterioration_score=0.70,
                stabilization_score=0.10,
                feature_count=1,
                feature_names=("vvix_turn",),
                reason="fixture action module",
            ),
        ),
    )


def _write_prices(
    price_root: Path,
    *,
    symbol: str,
    start: date,
    closes: tuple[float, ...],
) -> None:
    rows = tuple(
        DailyPriceObservation(
            source="fixture",
            source_symbol=symbol,
            symbol=symbol,
            observed_date=start + timedelta(days=index * 4),
            open=close,
            high=close,
            low=close,
            close=close,
            adjusted_close=close,
            volume=1_000_000,
        )
        for index, close in enumerate(closes)
    )
    write_price_observations(rows, output_root=price_root)


def _as_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    assert isinstance(value, date)
    return value
