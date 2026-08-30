"""Local DuckDB research store built from source snapshots and observations."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from loguru import logger

from marketlab.bulltard.validation import DEFAULT_CANDIDATE_SNAPSHOT_ROOT
from marketlab.market_series import DEFAULT_MARKET_SERIES_OBSERVATIONS_ROOT
from marketlab.market_signals import DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT
from marketlab.prices import DEFAULT_PRICE_OBSERVATIONS_ROOT
from marketlab.regime import DEFAULT_REGIME_SNAPSHOT_ROOT

DEFAULT_RESEARCH_DB_PATH = Path("marketlab.duckdb")
STORE_SCHEMA_VERSION = "research_store_v0"


class ResearchStoreError(ValueError):
    """Raised when the local research store cannot be refreshed or queried."""


@dataclass(frozen=True, slots=True)
class StoreTableRefresh:
    """Refresh result for one DuckDB table."""

    table_name: str
    row_count: int
    parquet_path: Path | None = None


@dataclass(frozen=True, slots=True)
class StoreRefreshResult:
    """Result of rebuilding the local research store."""

    db_path: Path
    schema_version: str
    table_refreshes: tuple[StoreTableRefresh, ...]


@dataclass(frozen=True, slots=True)
class StoreQueryResult:
    """Rows returned by a local store query."""

    columns: tuple[str, ...]
    rows: tuple[tuple[Any, ...], ...]


def refresh_research_store(
    *,
    db_path: Path = DEFAULT_RESEARCH_DB_PATH,
    price_root: Path = DEFAULT_PRICE_OBSERVATIONS_ROOT,
    market_series_root: Path = DEFAULT_MARKET_SERIES_OBSERVATIONS_ROOT,
    regime_snapshot_root: Path = DEFAULT_REGIME_SNAPSHOT_ROOT,
    market_signal_snapshot_root: Path = DEFAULT_MARKET_SIGNAL_SNAPSHOT_ROOT,
    candidate_snapshot_root: Path = DEFAULT_CANDIDATE_SNAPSHOT_ROOT,
    parquet_root: Path | None = None,
) -> StoreRefreshResult:
    """Rebuild queryable DuckDB tables from local snapshot and observation files."""

    duckdb = _duckdb_module()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if parquet_root is not None:
        parquet_root.mkdir(parents=True, exist_ok=True)

    logger.bind(
        db_path=str(db_path),
        price_root=str(price_root),
        market_series_root=str(market_series_root),
        regime_snapshot_root=str(regime_snapshot_root),
        market_signal_snapshot_root=str(market_signal_snapshot_root),
        candidate_snapshot_root=str(candidate_snapshot_root),
        parquet_root=str(parquet_root) if parquet_root else None,
    ).info("Refreshing local research store")

    try:
        connection = duckdb.connect(str(db_path))
    except Exception as exc:
        raise ResearchStoreError(f"Failed to open DuckDB store: {db_path}") from exc

    try:
        refreshes = (
            _refresh_metadata(connection, parquet_root=parquet_root),
            _refresh_daily_prices(connection, root=price_root, parquet_root=parquet_root),
            _refresh_market_series(connection, root=market_series_root, parquet_root=parquet_root),
            _refresh_regime_snapshots(
                connection,
                root=regime_snapshot_root,
                parquet_root=parquet_root,
            ),
            _refresh_regime_components(
                connection,
                root=regime_snapshot_root,
                parquet_root=parquet_root,
            ),
            _refresh_regime_pressure_features(
                connection,
                root=regime_snapshot_root,
                parquet_root=parquet_root,
            ),
            _refresh_market_signals(
                connection,
                root=market_signal_snapshot_root,
                parquet_root=parquet_root,
            ),
            _refresh_candidate_snapshots(
                connection,
                root=candidate_snapshot_root,
                parquet_root=parquet_root,
            ),
        )
    finally:
        connection.close()

    result = StoreRefreshResult(
        db_path=db_path,
        schema_version=STORE_SCHEMA_VERSION,
        table_refreshes=refreshes,
    )
    logger.bind(
        db_path=str(db_path),
        table_count=len(refreshes),
        row_count=sum(refresh.row_count for refresh in refreshes),
    ).success("Refreshed local research store")
    return result


def query_research_store(
    *,
    query: str,
    db_path: Path = DEFAULT_RESEARCH_DB_PATH,
) -> StoreQueryResult:
    """Run a read-only SQL query against the local research store."""

    if not db_path.is_file():
        raise ResearchStoreError(f"Research store does not exist: {db_path}")
    duckdb = _duckdb_module()
    try:
        connection = duckdb.connect(str(db_path), read_only=True)
    except Exception as exc:
        raise ResearchStoreError(f"Failed to open DuckDB store: {db_path}") from exc

    try:
        cursor = connection.execute(query)
        rows = tuple(tuple(row) for row in cursor.fetchall())
        columns = tuple(column[0] for column in cursor.description or ())
    except Exception as exc:
        raise ResearchStoreError(f"Store query failed: {exc}") from exc
    finally:
        connection.close()

    return StoreQueryResult(columns=columns, rows=rows)


def summarize_research_store(*, db_path: Path = DEFAULT_RESEARCH_DB_PATH) -> StoreQueryResult:
    """Return table row counts for the local research store."""

    return query_research_store(
        db_path=db_path,
        query="""
            select table_name, row_count
            from store_metadata
            where table_name is not null
            order by table_name
        """,
    )


def format_store_refresh_result(result: StoreRefreshResult) -> str:
    """Format store refresh row counts."""

    rows = [["table", "rows", "parquet"]]
    for refresh in result.table_refreshes:
        rows.append(
            [
                refresh.table_name,
                str(refresh.row_count),
                str(refresh.parquet_path) if refresh.parquet_path else "-",
            ]
        )
    return _format_table(rows)


def format_query_result(result: StoreQueryResult, *, limit: int = 50) -> str:
    """Format query rows as a compact table."""

    if not result.columns:
        return "No columns returned."
    if not result.rows:
        return "No rows returned."

    rows = [list(result.columns)]
    for row in result.rows[:limit]:
        rows.append([_format_cell(value) for value in row])
    if len(result.rows) > limit:
        rows.append([f"... {len(result.rows) - limit} more rows"] + [""] * (len(rows[0]) - 1))
    return _format_table(rows)


def _duckdb_module():
    try:
        import duckdb
    except ImportError as exc:
        raise ResearchStoreError("duckdb is not installed; run `uv add duckdb`") from exc
    return duckdb


def _refresh_metadata(connection, *, parquet_root: Path | None) -> StoreTableRefresh:
    schema = (
        ("key", "VARCHAR"),
        ("value", "VARCHAR"),
        ("table_name", "VARCHAR"),
        ("row_count", "BIGINT"),
    )
    rows = [(STORE_SCHEMA_VERSION, "active", None, None)]
    return _replace_table(
        connection,
        table_name="store_metadata",
        schema=schema,
        rows=rows,
        parquet_root=parquet_root,
    )


def _refresh_daily_prices(
    connection,
    *,
    root: Path,
    parquet_root: Path | None,
) -> StoreTableRefresh:
    schema = (
        ("source", "VARCHAR"),
        ("source_symbol", "VARCHAR"),
        ("symbol", "VARCHAR"),
        ("observed_date", "DATE"),
        ("open", "DOUBLE"),
        ("high", "DOUBLE"),
        ("low", "DOUBLE"),
        ("close", "DOUBLE"),
        ("volume", "BIGINT"),
        ("adjusted_close", "DOUBLE"),
        ("dollar_volume", "DOUBLE"),
        ("return_close", "DOUBLE"),
    )
    rows = []
    for row in _read_jsonl_files(root):
        close = _optional_float(row.get("close"))
        adjusted_close = _optional_float(row.get("adjusted_close"))
        volume = _optional_int(row.get("volume"))
        rows.append(
            (
                _optional_str(row.get("source")),
                _optional_str(row.get("source_symbol")),
                _optional_str(row.get("symbol")),
                _optional_date(row.get("date")),
                _optional_float(row.get("open")),
                _optional_float(row.get("high")),
                _optional_float(row.get("low")),
                close,
                volume,
                adjusted_close,
                close * volume if close is not None and volume is not None else None,
                adjusted_close if adjusted_close is not None else close,
            )
        )
    return _replace_table(
        connection,
        table_name="daily_prices",
        schema=schema,
        rows=tuple(rows),
        parquet_root=parquet_root,
    )


def _refresh_market_series(
    connection,
    *,
    root: Path,
    parquet_root: Path | None,
) -> StoreTableRefresh:
    schema = (
        ("source", "VARCHAR"),
        ("source_series_id", "VARCHAR"),
        ("series_id", "VARCHAR"),
        ("observed_date", "DATE"),
        ("availability_date", "DATE"),
        ("value", "DOUBLE"),
        ("unit", "VARCHAR"),
    )
    rows = tuple(
        (
            _optional_str(row.get("source")),
            _optional_str(row.get("source_series_id")),
            _optional_str(row.get("series_id")),
            _optional_date(row.get("observed_date")),
            _optional_date(row.get("availability_date")),
            _optional_float(row.get("value")),
            _optional_str(row.get("unit")),
        )
        for row in _read_jsonl_files(root)
    )
    return _replace_table(
        connection,
        table_name="market_series",
        schema=schema,
        rows=rows,
        parquet_root=parquet_root,
    )


def _refresh_regime_snapshots(
    connection,
    *,
    root: Path,
    parquet_root: Path | None,
) -> StoreTableRefresh:
    schema = (
        ("source_date", "DATE"),
        ("price_date", "DATE"),
        ("feature_version", "VARCHAR"),
        ("model_version", "VARCHAR"),
        ("regime", "VARCHAR"),
        ("score", "INTEGER"),
        ("confidence", "VARCHAR"),
        ("action_version", "VARCHAR"),
        ("action_state", "VARCHAR"),
        ("stretch_score", "INTEGER"),
        ("washout_score", "INTEGER"),
        ("action_confidence", "VARCHAR"),
        ("action_reason", "VARCHAR"),
        ("pressure_version", "VARCHAR"),
        ("stretch_pressure_score", "DOUBLE"),
        ("washout_pressure_score", "DOUBLE"),
        ("pressure_confidence", "VARCHAR"),
        ("missing_symbols", "VARCHAR"),
    )
    rows = tuple(
        (
            _optional_date(row.get("source_date")),
            _optional_date(row.get("price_date")),
            _optional_str(row.get("feature_version")),
            _optional_str(row.get("model_version")),
            _optional_str(row.get("regime")),
            _optional_int(row.get("score")),
            _optional_str(row.get("confidence")),
            _optional_str(row.get("action_version")),
            _optional_str(row.get("action_state")),
            _optional_int(row.get("stretch_score")),
            _optional_int(row.get("washout_score")),
            _optional_str(row.get("action_confidence")),
            _optional_str(row.get("action_reason")),
            _optional_str(row.get("pressure_version")),
            _optional_float(row.get("stretch_pressure_score")),
            _optional_float(row.get("washout_pressure_score")),
            _optional_str(row.get("pressure_confidence")),
            ",".join(str(symbol) for symbol in row.get("missing_symbols", ())),
        )
        for row in _read_json_files(root)
    )
    return _replace_table(
        connection,
        table_name="regime_snapshots",
        schema=schema,
        rows=rows,
        parquet_root=parquet_root,
    )


def _refresh_regime_components(
    connection,
    *,
    root: Path,
    parquet_root: Path | None,
) -> StoreTableRefresh:
    schema = (
        ("source_date", "DATE"),
        ("component", "VARCHAR"),
        ("score", "INTEGER"),
        ("status", "VARCHAR"),
        ("reason", "VARCHAR"),
    )
    rows = []
    for row in _read_json_files(root):
        source_date = _optional_date(row.get("source_date"))
        for component in row.get("components", ()):
            rows.append(
                (
                    source_date,
                    _optional_str(component.get("name")),
                    _optional_int(component.get("score")),
                    _optional_str(component.get("status")),
                    _optional_str(component.get("reason")),
                )
            )
    return _replace_table(
        connection,
        table_name="regime_components",
        schema=schema,
        rows=tuple(rows),
        parquet_root=parquet_root,
    )


def _refresh_regime_pressure_features(
    connection,
    *,
    root: Path,
    parquet_root: Path | None,
) -> StoreTableRefresh:
    schema = (
        ("source_date", "DATE"),
        ("pressure_version", "VARCHAR"),
        ("family", "VARCHAR"),
        ("feature", "VARCHAR"),
        ("raw_value", "DOUBLE"),
        ("percentile", "DOUBLE"),
        ("normalized_score", "DOUBLE"),
        ("stretch_score", "DOUBLE"),
        ("washout_score", "DOUBLE"),
        ("sample_count", "INTEGER"),
        ("reason", "VARCHAR"),
    )
    rows = []
    for row in _read_json_files(root):
        for feature in row.get("pressure_features", ()):
            rows.append(
                (
                    _optional_date(feature.get("source_date")),
                    _optional_str(feature.get("pressure_version")),
                    _optional_str(feature.get("family")),
                    _optional_str(feature.get("name")),
                    _optional_float(feature.get("raw_value")),
                    _optional_float(feature.get("percentile")),
                    _optional_float(feature.get("normalized_score")),
                    _optional_float(feature.get("stretch_score")),
                    _optional_float(feature.get("washout_score")),
                    _optional_int(feature.get("sample_count")),
                    _optional_str(feature.get("reason")),
                )
            )
    return _replace_table(
        connection,
        table_name="regime_pressure_features",
        schema=schema,
        rows=tuple(rows),
        parquet_root=parquet_root,
    )


def _refresh_market_signals(
    connection,
    *,
    root: Path,
    parquet_root: Path | None,
) -> StoreTableRefresh:
    schema = (
        ("source_date", "DATE"),
        ("feature_version", "VARCHAR"),
        ("family", "VARCHAR"),
        ("signal", "VARCHAR"),
        ("status", "VARCHAR"),
        ("score", "INTEGER"),
        ("value_number", "DOUBLE"),
        ("value_text", "VARCHAR"),
        ("unit", "VARCHAR"),
        ("data_source", "VARCHAR"),
        ("observed_date", "DATE"),
        ("availability_date", "DATE"),
        ("reason", "VARCHAR"),
    )
    rows = []
    for row in _read_jsonl_files(root):
        value = row.get("value")
        rows.append(
            (
                _optional_date(row.get("source_date")),
                _optional_str(row.get("feature_version")),
                _optional_str(row.get("family")),
                _optional_str(row.get("name")),
                _optional_str(row.get("status")),
                _optional_int(row.get("score")),
                _optional_float(value) if isinstance(value, int | float) else None,
                str(value) if value is not None and not isinstance(value, int | float) else None,
                _optional_str(row.get("unit")),
                _optional_str(row.get("data_source")),
                _optional_date(row.get("observed_date")),
                _optional_date(row.get("availability_date")),
                _optional_str(row.get("reason")),
            )
        )
    return _replace_table(
        connection,
        table_name="market_signals",
        schema=schema,
        rows=tuple(rows),
        parquet_root=parquet_root,
    )


def _refresh_candidate_snapshots(
    connection,
    *,
    root: Path,
    parquet_root: Path | None,
) -> StoreTableRefresh:
    schema = (
        ("source_date", "DATE"),
        ("feature_version", "VARCHAR"),
        ("symbol", "VARCHAR"),
        ("bulltard_source", "VARCHAR"),
        ("ranked_side", "VARCHAR"),
        ("ranked_score", "DOUBLE"),
        ("ranked_trade_count", "INTEGER"),
        ("ranked_premium", "DOUBLE"),
        ("interest_rank", "INTEGER"),
        ("detail_rows", "INTEGER"),
        ("price_date", "DATE"),
        ("close", "DOUBLE"),
        ("dollar_volume", "DOUBLE"),
        ("return_5d", "DOUBLE"),
        ("return_20d", "DOUBLE"),
        ("return_60d", "DOUBLE"),
        ("ma20_distance", "DOUBLE"),
        ("ma50_distance", "DOUBLE"),
        ("ma200_distance", "DOUBLE"),
        ("drawdown_60d", "DOUBLE"),
        ("relative_strength_20d_spy", "DOUBLE"),
        ("relative_strength_20d_qqq", "DOUBLE"),
        ("underlying_liquidity_status", "VARCHAR"),
        ("options_liquidity_status", "VARCHAR"),
        ("validation_status", "VARCHAR"),
        ("validation_reasons", "VARCHAR"),
    )
    rows = tuple(
        (
            _optional_date(row.get("source_date")),
            _optional_str(row.get("feature_version")),
            _optional_str(row.get("symbol")),
            _optional_str(row.get("bulltard_source")),
            _optional_str(row.get("ranked_side")),
            _optional_float(row.get("ranked_score")),
            _optional_int(row.get("ranked_trade_count")),
            _optional_float(row.get("ranked_premium")),
            _optional_int(row.get("interest_rank")),
            _optional_int(row.get("detail_rows")),
            _optional_date(row.get("price_date")),
            _optional_float(row.get("close")),
            _optional_float(row.get("dollar_volume")),
            _optional_float(row.get("return_5d")),
            _optional_float(row.get("return_20d")),
            _optional_float(row.get("return_60d")),
            _optional_float(row.get("ma20_distance")),
            _optional_float(row.get("ma50_distance")),
            _optional_float(row.get("ma200_distance")),
            _optional_float(row.get("drawdown_60d")),
            _optional_float(row.get("relative_strength_20d_spy")),
            _optional_float(row.get("relative_strength_20d_qqq")),
            _optional_str(row.get("underlying_liquidity_status")),
            _optional_str(row.get("options_liquidity_status")),
            _optional_str(row.get("validation_status")),
            ",".join(str(reason) for reason in row.get("validation_reasons", ())),
        )
        for row in _read_jsonl_files(root)
    )
    return _replace_table(
        connection,
        table_name="candidate_snapshots",
        schema=schema,
        rows=rows,
        parquet_root=parquet_root,
    )


def _replace_table(
    connection,
    *,
    table_name: str,
    schema: tuple[tuple[str, str], ...],
    rows: tuple[tuple[Any, ...], ...] | list[tuple[Any, ...]],
    parquet_root: Path | None,
) -> StoreTableRefresh:
    schema_sql = ", ".join(f"{column} {column_type}" for column, column_type in schema)
    placeholders = ", ".join("?" for _column, _column_type in schema)
    connection.execute(f"create or replace table {table_name} ({schema_sql})")
    row_tuple = tuple(rows)
    if row_tuple:
        connection.executemany(f"insert into {table_name} values ({placeholders})", row_tuple)

    parquet_path = _write_parquet(connection, table_name=table_name, parquet_root=parquet_root)
    if table_name != "store_metadata":
        connection.execute(
            "insert into store_metadata values (?, ?, ?, ?)",
            (STORE_SCHEMA_VERSION, "row_count", table_name, len(row_tuple)),
        )
    return StoreTableRefresh(
        table_name=table_name,
        row_count=len(row_tuple),
        parquet_path=parquet_path,
    )


def _write_parquet(connection, *, table_name: str, parquet_root: Path | None) -> Path | None:
    if parquet_root is None:
        return None
    parquet_path = parquet_root / f"{table_name}.parquet"
    sql_path = str(parquet_path).replace("'", "''")
    connection.execute(f"copy {table_name} to '{sql_path}' (format parquet)")
    return parquet_path


def _read_json_files(root: Path) -> tuple[dict[str, Any], ...]:
    if not root.exists():
        return ()
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.json")):
        try:
            rows.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            raise ResearchStoreError(f"Failed to read JSON snapshot: {path}") from exc
    return tuple(rows)


def _read_jsonl_files(root: Path) -> tuple[dict[str, Any], ...]:
    if not root.exists():
        return ()
    rows: list[dict[str, Any]] = []
    for path in sorted(root.glob("*.jsonl")):
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                if line.strip():
                    rows.append(json.loads(line))
        except (OSError, json.JSONDecodeError) as exc:
            raise ResearchStoreError(f"Failed to read JSONL observations: {path}") from exc
    return tuple(rows)


def _optional_str(value: object) -> str | None:
    if value is None:
        return None
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


def _format_cell(value: object) -> str:
    if value is None:
        return "-"
    if isinstance(value, float):
        return f"{value:.6g}"
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _format_table(rows: list[list[str]]) -> str:
    widths = [max(len(row[index]) for row in rows) for index in range(len(rows[0]))]
    lines = []
    for row_index, row in enumerate(rows):
        lines.append("  ".join(value.ljust(widths[index]) for index, value in enumerate(row)))
        if row_index == 0:
            lines.append("  ".join("-" * width for width in widths))
    return "\n".join(lines)
