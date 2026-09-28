from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from strategy_lab.data.settings import AppSettings
from strategy_lab.data.models import DatasetKind, MarketType


@dataclass(slots=True)
class DataLakeLayout:
    root_dir: Path
    raw_dir: Path
    normalized_dir: Path
    features_dir: Path
    cache_dir: Path
    registry_db_path: Path | None = None
    derived_dir: Path | None = None

    def __post_init__(self) -> None:
        if self.derived_dir is None:
            self.derived_dir = self.root_dir / "derived"

    @classmethod
    def from_settings(cls, settings: AppSettings) -> "DataLakeLayout":
        return cls(
            root_dir=settings.storage.root_dir,
            raw_dir=settings.storage.raw_dir,
            normalized_dir=settings.storage.normalized_dir,
            features_dir=settings.storage.features_dir,
            cache_dir=settings.storage.cache_dir,
            registry_db_path=settings.storage.registry_db_path,
            derived_dir=settings.storage.derived_dir,
        )

    def ensure_directories(self) -> None:
        for path in (
            self.root_dir,
            self.raw_dir,
            self.normalized_dir,
            self.features_dir,
            self.cache_dir,
            self.resolved_derived_dir,
            self.derived_datasets_dir,
            self.derived_staging_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)

    @property
    def resolved_derived_dir(self) -> Path:
        return self.derived_dir if self.derived_dir is not None else self.root_dir / "derived"

    @property
    def derived_datasets_dir(self) -> Path:
        return self.resolved_derived_dir / "datasets"

    @property
    def derived_staging_dir(self) -> Path:
        return self.resolved_derived_dir / "_staging"

    def dataset_root(self, layer: str, kind: DatasetKind) -> Path:
        if layer == "raw":
            return self.raw_dir / kind.value
        if layer == "normalized":
            return self.normalized_dir / kind.value
        if layer == "features":
            return self.features_dir / kind.value
        if layer == "derived":
            raise ValueError(
                "derived OHLCV is addressed by dataset_id, not by globbing "
                "layout.dataset_root('derived', kind); use strategy_lab.data.catalog"
            )
        raise ValueError(f"unsupported layer: {layer}")

    def dataset_path(
        self,
        *,
        layer: str,
        kind: DatasetKind,
        exchange: str | None = None,
        market_type: MarketType | None = None,
        symbol: str | None = None,
        timeframe: str | None = None,
        source: str | None = None,
        partition_date: date | None = None,
        file_stem: str | None = None,
    ) -> Path:
        path = self.dataset_root(layer, kind)
        if exchange:
            path = path / f"exchange={exchange.lower()}"
        if market_type:
            path = path / f"market_type={market_type.value}"
        if timeframe:
            path = path / f"timeframe={timeframe.lower()}"
        if source:
            path = path / f"source={source.lower()}"
        if partition_date:
            path = path / f"date={partition_date.isoformat()}"
        if file_stem is None:
            file_stem = "part-0000"
            if symbol:
                normalized_symbol = symbol.replace("/", "_").replace(":", "_").lower()
                file_stem = f"symbol={normalized_symbol}"
        return path / f"{file_stem}.parquet"

    def summary(self) -> dict[str, str]:
        return {
            "root_dir": str(self.root_dir),
            "raw_dir": str(self.raw_dir),
            "normalized_dir": str(self.normalized_dir),
            "features_dir": str(self.features_dir),
            "cache_dir": str(self.cache_dir),
            "derived_dir": str(self.resolved_derived_dir),
            "registry_db_path": str(self.run_registry_db_path),
        }

    @property
    def run_registry_db_path(self) -> Path:
        return self.registry_db_path or (self.cache_dir / "_registry" / "runs.sqlite")
