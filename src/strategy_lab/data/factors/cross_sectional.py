from __future__ import annotations

import pandas as pd

from strategy_lab.data.factors.base import FactorMetadata, PandasFactor, register_factor_provider


class RelativeStrengthFactor(PandasFactor):
    def __init__(
        self,
        periods: int = 24,
        price_column: str = "close",
        benchmark_column: str = "benchmark_close",
    ) -> None:
        self.periods = periods
        self.price_column = price_column
        self.benchmark_column = benchmark_column
        self.metadata = FactorMetadata(
            name=f"relative_strength_{periods}",
            category="cross_sectional",
            frequency="bar",
            lookback=periods + 1,
            inputs=(price_column, benchmark_column),
            market_types=("spot", "perp"),
            description="Asset trailing return minus benchmark trailing return.",
            cross_sectional=True,
            formula=f"({price_column}[t]/{price_column}[t-{periods}]-1) - "
                    f"({benchmark_column}[t]/{benchmark_column}[t-{periods}]-1)",
            direction="higher_is_stronger",
        )

    def compute(self, frame: pd.DataFrame) -> pd.Series:
        """Trailing excess return is a time-series transform before any ranking.

        A multi-asset panel must never connect two instruments or two known
        discontinuous research segments. Preserve the caller's row/index order.
        Without an explicit time column, rows are assumed already ordered.
        """
        if isinstance(self.periods, bool) or not isinstance(self.periods, int) or self.periods < 1:
            raise ValueError("periods must be a positive integer")
        working = frame.copy().reset_index(drop=True)
        keys = [k for k in ("exchange", "symbol", "market_type", "timeframe", "research_segment_id")
                if k in working.columns]
        if keys and working[keys].isna().any().any():
            raise ValueError("missing instrument/segment identity")
        if "ts" in working.columns:
            ts = pd.to_datetime(working.ts, errors="raise", utc=True)
            if ts.isna().any() or working.assign(ts=ts).duplicated([*keys, "ts"]).any():
                raise ValueError("missing or duplicate factor timestamp")
            working["ts"] = ts
        groups = working.groupby(keys, sort=False, dropna=False) if keys else [(None, working)]
        result = pd.Series(float("nan"), index=working.index, dtype=float)
        for _, group in groups:
            if "ts" in group.columns and not group.ts.is_monotonic_increasing:
                raise ValueError("factor rows must be chronological within each instrument/segment")
            asset_return = group[self.price_column].pct_change(self.periods, fill_method=None)
            benchmark_return = group[self.benchmark_column].pct_change(self.periods, fill_method=None)
            result.loc[group.index] = asset_return - benchmark_return
        result.index = frame.index
        return result


@register_factor_provider()
def builtin_cross_sectional_factors() -> list[PandasFactor]:
    return [
        RelativeStrengthFactor(periods=24),
    ]
