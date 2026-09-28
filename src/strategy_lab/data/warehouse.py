from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from strategy_lab.data.authenticity import (
    DEFAULT_BLOCKED_SOURCE_PATTERNS,
    DEFAULT_REAL_SOURCE_ALLOWLIST,
    unverified_source_mask,
)
from strategy_lab.data.lake import DataLakeLayout
from strategy_lab.data.liquidations import (
    aggregate_liquidation_events,
    enrich_liquidation_features,
)
from strategy_lab.data.models import DatasetKind, MarketType
from strategy_lab.data.quality import (
    DuplicatePolicy,
    DuplicateStats,
    audit_ohlcv_frame,
    resolve_duplicates,
)
from strategy_lab.data.sessions import OHLCVSessionPolicy


def _symbol_file_stem(symbol: str) -> str:
    return f"symbol={symbol.replace('/', '_').replace(':', '_').lower()}.parquet"


@dataclass(slots=True)
class DuckDBWarehouse:
    layout: DataLakeLayout
    database_path: Path | None = None

    def __post_init__(self) -> None:
        if self.database_path is None:
            self.database_path = self.layout.root_dir / "strategy_lab.duckdb"

    def connect(self) -> duckdb.DuckDBPyConnection:
        self.layout.ensure_directories()
        return duckdb.connect(str(self.database_path))

    def dataset_files(self, *, layer: str, kind: DatasetKind) -> list[str]:
        root = self.layout.dataset_root(layer, kind)
        return [str(path) for path in sorted(root.glob("**/*.parquet"))]

    def _filtered_dataset_files(
        self,
        *,
        layer: str,
        kind: DatasetKind,
        exchange: str | None = None,
        market_type: MarketType | None = None,
        symbol: str | None = None,
        timeframe: str | None = None,
        source: str | None = None,
    ) -> list[str]:
        if layer == "derived":
            raise ValueError(
                "derived OHLCV must be loaded by dataset_id via "
                "strategy_lab.data.catalog.load_trusted_dataset"
            )
        root = self.layout.dataset_root(layer, kind)
        path = root
        if exchange:
            path = path / f"exchange={exchange.lower()}"
        if market_type:
            path = path / f"market_type={market_type.value}"
        if timeframe:
            path = path / f"timeframe={timeframe.lower()}"
        if source:
            path = path / f"source={source.lower()}"
        if symbol and any((exchange, market_type, timeframe, source)):
            files = sorted(path.glob(f"**/{_symbol_file_stem(symbol)}"))
        else:
            files = sorted(path.glob("**/*.parquet"))
        return [str(file_path) for file_path in files]

    def load_dataset(
        self,
        *,
        layer: str,
        kind: DatasetKind,
        exchange: str | None = None,
        market_type: MarketType | None = None,
        symbol: str | None = None,
        timeframe: str | None = None,
        source: str | None = None,
        columns: list[str] | None = None,
        duplicate_policy: DuplicatePolicy = DuplicatePolicy.ERROR,
        return_duplicate_stats: bool = False,
    ) -> pd.DataFrame | tuple[pd.DataFrame, DuplicateStats]:
        files = self._filtered_dataset_files(
            layer=layer,
            kind=kind,
            exchange=exchange,
            market_type=market_type,
            symbol=symbol,
            timeframe=timeframe,
            source=source,
        )
        if not files and any((exchange, market_type, symbol, timeframe, source)):
            # Fall back to scanning the dataset root so pre-canonical legacy files remain readable.
            files = self.dataset_files(layer=layer, kind=kind)
        if not files:
            empty = pd.DataFrame(columns=columns or [])
            stats = DuplicateStats(duplicate_policy, (), 0, 0, 0)
            return (empty, stats) if return_duplicate_stats else empty

        return_columns = list(columns) if columns else None
        projection = "*"
        filters: list[str] = []
        params: list[Any] = [files]
        if exchange:
            filters.append("exchange = ?")
            params.append(exchange.lower())
        if market_type:
            filters.append("market_type = ?")
            params.append(market_type.value)
        if symbol:
            filters.append("replace(upper(symbol), '_', '/') = ?")
            params.append(symbol.upper())
        if source:
            filters.append("source = ?")
            params.append(source.lower())

        where_clause = f"WHERE {' AND '.join(filters)}" if filters else ""
        order_columns = (
            ["ts", "symbol"] if kind != DatasetKind.ASSET_METADATA else ["symbol"]
        )
        sql = (
            f"SELECT {projection}, filename AS __source_file "
            "FROM read_parquet(?, hive_partitioning = false, union_by_name = true, filename = true) "
            f"{where_clause} ORDER BY {', '.join(order_columns)}"
        )
        with self.connect() as connection:
            frame = connection.execute(sql, params).fetch_df()

        if timeframe and "timeframe" in frame.columns:
            normalized_timeframe = timeframe.lower()
            exact = frame[
                frame["timeframe"].astype("string").str.lower() == normalized_timeframe
            ].reset_index(drop=True)
            if not exact.empty:
                frame = exact
            else:
                # Legacy parquet files may not have a timeframe column. Keep them readable
                # until data has been refreshed into timeframe-partitioned paths.
                frame = frame[frame["timeframe"].isna()].reset_index(drop=True)
        frame, duplicate_stats = resolve_duplicates(
            kind,
            frame,
            policy=duplicate_policy,
            order_columns=("__source_file",),
        )
        frame = frame.drop(columns=["filename", "__source_file"], errors="ignore")
        if "ts" in frame.columns:
            frame["ts"] = pd.to_datetime(frame["ts"], utc=True, errors="raise")
        if return_columns is not None:
            frame = frame[
                [column for column in return_columns if column in frame.columns]
            ]
        frame.attrs["duplicate_stats"] = duplicate_stats.to_dict()
        return (frame, duplicate_stats) if return_duplicate_stats else frame

    def load_trusted_ohlcv(
        self,
        *,
        exchange: str,
        market_type: MarketType,
        symbol: str,
        timeframe: str,
        source: str | None = None,
        layer: str = "normalized",
        start: pd.Timestamp | None = None,
        end: pd.Timestamp | None = None,
        require_contiguous: bool = True,
        require_closed: bool = True,
        session_policy: OHLCVSessionPolicy | str | None = None,
        closure_as_of: pd.Timestamp | str | None = None,
        allowed_sources: tuple[str, ...] = DEFAULT_REAL_SOURCE_ALLOWLIST,
        blocked_source_patterns: tuple[str, ...] = DEFAULT_BLOCKED_SOURCE_PATTERNS,
    ) -> pd.DataFrame:
        """Compatibility loader for existing research scripts.

        New research must not call this method. Use
        ``catalog.load_trusted_research_dataset`` then
        ``catalog.require_passing_trusted`` instead.
        """
        if session_policy is None:
            if market_type == MarketType.EQUITY:
                raise ValueError(
                    "equity trusted OHLCV loads require an explicit session_policy"
                )
            resolved_session_policy = OHLCVSessionPolicy.CONTINUOUS_24_7
        else:
            resolved_session_policy = OHLCVSessionPolicy(session_policy)
        if (
            resolved_session_policy == OHLCVSessionPolicy.XNAS_REGULAR
            and market_type != MarketType.EQUITY
        ):
            raise ValueError("xnas_regular session policy is only valid for equity data")

        frame = self.load_dataset(
            layer=layer,
            kind=DatasetKind.OHLCV,
            exchange=exchange,
            market_type=market_type,
            symbol=symbol,
            timeframe=timeframe,
            source=source,
        )
        if start is not None and "ts" in frame.columns:
            start_ts = pd.Timestamp(start)
            start_ts = (
                start_ts.tz_localize("UTC")
                if start_ts.tzinfo is None
                else start_ts.tz_convert("UTC")
            )
            frame = frame.loc[frame["ts"].ge(start_ts)].reset_index(drop=True)
        if end is not None and "ts" in frame.columns:
            end_ts = pd.Timestamp(end)
            end_ts = (
                end_ts.tz_localize("UTC")
                if end_ts.tzinfo is None
                else end_ts.tz_convert("UTC")
            )
            frame = frame.loc[frame["ts"].lt(end_ts)].reset_index(drop=True)
        report = audit_ohlcv_frame(
            frame,
            expected_timeframe=timeframe,
            require_closed=require_closed,
            session_policy=resolved_session_policy,
            closure_as_of=closure_as_of,
        )
        blockers: dict[str, object] = {
            "duplicate_rows": report.duplicate_rows,
            "unexpected_intervals": report.unexpected_intervals,
            "open_rows": report.open_rows,
            "timeframe_mismatches": report.timeframe_mismatches,
            "out_of_session_rows": report.out_of_session_rows,
            "closure_mismatches": report.closure_mismatches,
            "schema_errors": list(report.schema_errors),
        }
        if require_contiguous:
            blockers["missing_bars"] = report.missing_bars
        source_mask = unverified_source_mask(
            frame,
            allowed_sources=allowed_sources,
            blocked_patterns=blocked_source_patterns,
        )
        blockers["unverified_source_rows"] = int(source_mask.sum())
        if any(bool(value) for value in blockers.values()):
            raise ValueError(f"OHLCV dataset is not trusted: {blockers}")
        trusted = frame.copy()
        trusted.attrs["ohlcv_audit"] = report.to_dict()
        trusted.attrs["source_counts"] = {
            str(source): int(count)
            for source, count in frame["source"].value_counts(dropna=False).items()
        }
        return trusted

    def query(self, sql: str, parameters: list[Any] | None = None) -> pd.DataFrame:
        with self.connect() as connection:
            return connection.execute(sql, parameters or []).fetch_df()

    def merged_market_frame(
        self,
        *,
        exchange: str,
        symbol: str,
        market_type: MarketType,
        timeframe: str | None = None,
        layer: str = "normalized",
    ) -> pd.DataFrame:
        ohlcv = self.load_dataset(
            layer=layer,
            kind=DatasetKind.OHLCV,
            exchange=exchange,
            market_type=market_type,
            symbol=symbol,
            timeframe=timeframe,
        )
        if ohlcv.empty:
            return ohlcv

        merged = ohlcv.copy()
        if market_type == MarketType.PERP:
            for kind, suffix, core_columns in (
                (
                    DatasetKind.FUNDING_RATES,
                    "funding",
                    {"funding_rate", "next_funding_ts"},
                ),
                (
                    DatasetKind.OPEN_INTEREST,
                    "oi",
                    {"open_interest", "open_interest_value"},
                ),
                (
                    DatasetKind.BASIS,
                    "basis",
                    {
                        "basis",
                        "basis_rate",
                        "annualized_basis",
                        "futures_price",
                        "index_price",
                        "mark_price",
                        "premium_index",
                    },
                ),
            ):
                data = self.load_dataset(
                    layer=layer,
                    kind=kind,
                    exchange=exchange,
                    market_type=market_type,
                    symbol=symbol,
                    timeframe=timeframe,
                )
                if data.empty:
                    continue
                extra_columns = [
                    column
                    for column in data.columns
                    if column
                    not in {
                        "exchange",
                        "symbol",
                        "market_type",
                        "timeframe",
                        "base_asset",
                        "quote_asset",
                        "source",
                        "date",
                    }
                ]
                rename_map = {
                    column: f"{column}_{suffix}"
                    for column in extra_columns
                    if column not in {"ts", *core_columns}
                }
                prepared = data.rename(columns=rename_map)
                merged = merged.merge(
                    prepared,
                    on=[
                        "ts",
                        "exchange",
                        "symbol",
                        "market_type",
                        "base_asset",
                        "quote_asset",
                    ],
                    how="left",
                    suffixes=("", f"_{suffix}"),
                )
        return merged.sort_values("ts").reset_index(drop=True)

    def load_liquidation_features(
        self,
        *,
        exchange: str,
        symbol: str,
        market_type: MarketType,
        timeframe: str | None = None,
        frequency: str | None = None,
        spike_window: int = 24,
        cooldown_bars: int = 3,
        spike_threshold: float = 2.5,
        notional_ratio_threshold: float = 0.03,
        layer: str = "normalized",
    ) -> pd.DataFrame:
        ohlcv = self.load_dataset(
            layer=layer,
            kind=DatasetKind.OHLCV,
            exchange=exchange,
            market_type=market_type,
            symbol=symbol,
            timeframe=timeframe,
        )
        if ohlcv.empty:
            return pd.DataFrame()

        # 未显式指定时，从 ohlcv ts 间隔自动推断频率，保证聚合后与主表可 merge。
        if frequency is None:
            inferred_freq = "1h"
            ts_series = (
                pd.to_datetime(ohlcv["ts"], utc=True)
                .sort_values()
                .reset_index(drop=True)
            )
            if len(ts_series) >= 2:
                diffs = ts_series.diff().dropna()
                if not diffs.empty:
                    median_delta = diffs.median()
                    total_seconds = median_delta.total_seconds()
                    if total_seconds >= 86400 * 0.9:
                        inferred_freq = "1D"
                    elif total_seconds >= 14400 * 0.9:
                        inferred_freq = "4h"
                    elif total_seconds >= 3600 * 0.9:
                        inferred_freq = "1h"
                    else:
                        inferred_freq = f"{int(total_seconds)}s"
            frequency = inferred_freq

        base = ohlcv[
            [
                "ts",
                "exchange",
                "symbol",
                "market_type",
                "base_asset",
                "quote_asset",
                "close",
                "volume",
            ]
        ].copy()

        raw_events = self.load_dataset(
            layer=layer,
            kind=DatasetKind.LIQUIDATIONS,
            exchange=exchange,
            market_type=market_type,
            symbol=symbol,
        )
        if raw_events.empty:
            empty = base.copy()
            empty["liquidation_long_notional"] = 0.0
            empty["liquidation_short_notional"] = 0.0
            empty["liquidation_total_notional"] = 0.0
            empty["liquidation_count"] = 0
            empty["liquidation_imbalance"] = 0.0
            empty["liq_spike_zscore"] = 0.0
            empty["liq_notional_vs_dollar_volume"] = 0.0
            empty["post_liq_oi_drop"] = 0.0
            empty["event_cooldown_flag"] = 0
            return empty.drop(columns=["close", "volume"])

        aggregated = aggregate_liquidation_events(raw_events, frequency=frequency)
        oi = self.load_dataset(
            layer=layer,
            kind=DatasetKind.OPEN_INTEREST,
            exchange=exchange,
            market_type=market_type,
            symbol=symbol,
            timeframe=timeframe,
            columns=["ts", "open_interest"],
        )
        dollar_volume_series = pd.Series(
            (base["close"] * base["volume"]).to_numpy(),
            index=pd.to_datetime(base["ts"], utc=True),
        )
        open_interest_series = None
        if not oi.empty:
            open_interest_series = pd.Series(
                oi["open_interest"].to_numpy(),
                index=pd.to_datetime(oi["ts"], utc=True),
            )

        features = enrich_liquidation_features(
            aggregated,
            dollar_volume=dollar_volume_series,
            open_interest=open_interest_series,
            spike_window=spike_window,
            cooldown_bars=cooldown_bars,
            spike_threshold=spike_threshold,
            notional_ratio_threshold=notional_ratio_threshold,
        )

        merged = base.merge(
            features,
            on=["ts", "exchange", "symbol", "market_type", "base_asset", "quote_asset"],
            how="left",
        )
        fill_columns = [
            "liquidation_long_notional",
            "liquidation_short_notional",
            "liquidation_total_notional",
            "liquidation_count",
            "liquidation_imbalance",
            "liq_spike_zscore",
            "liq_notional_vs_dollar_volume",
            "post_liq_oi_drop",
            "event_cooldown_flag",
        ]
        for column in fill_columns:
            merged[column] = merged[column].fillna(0.0)
        merged["event_cooldown_flag"] = merged["event_cooldown_flag"].astype(int)
        return merged.drop(columns=["close", "volume"])
