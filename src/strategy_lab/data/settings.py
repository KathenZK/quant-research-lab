from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


def _project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"0", "false", "no", "off"}
    return bool(value)


def _looks_like_profile_storage(value: object) -> bool:
    if value is None:
        return False
    path = Path(value)
    if path.is_absolute():
        return False
    return len(path.parts) >= 2 and path.parts[0] == "data"


def _uses_shared_storage(storage: dict[str, Any]) -> bool:
    explicit = storage.get("shared", storage.get("shared_storage"))
    if explicit is not None:
        return _coerce_bool(explicit, default=True)
    return any(
        _looks_like_profile_storage(storage.get(key))
        for key in ("root_dir", "raw_dir", "normalized_dir", "features_dir", "cache_dir", "registry_db_path")
    )


def _resolve_storage_path(value: object, *, default: Path, project_root: Path) -> Path:
    path = Path(value) if value is not None else default
    if path.is_absolute():
        return path
    return project_root / path


@dataclass(slots=True)
class StorageConfig:
    root_dir: Path
    raw_dir: Path
    normalized_dir: Path
    features_dir: Path
    cache_dir: Path
    registry_db_path: Path


@dataclass(slots=True)
class ExchangeConfig:
    name: str
    enabled: bool = True
    market_types: list[str] = field(default_factory=lambda: ["spot", "perp"])
    quote_assets: list[str] = field(default_factory=lambda: ["USDT"])


@dataclass(slots=True)
class ResearchConfig:
    bar_frequencies: list[str] = field(default_factory=lambda: ["1h", "4h", "1d"])
    benchmark_symbols: list[str] = field(default_factory=lambda: ["BTC/USDT", "ETH/USDT"])
    universe_filters: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AppSettings:
    name: str
    timezone: str
    storage: StorageConfig
    exchanges: list[ExchangeConfig]
    research: ResearchConfig


def default_settings(project_root: Path | None = None) -> AppSettings:
    root = project_root or _project_root()
    return AppSettings(
        name="quant-research-lab",
        timezone="UTC",
        storage=StorageConfig(
            root_dir=root / "data",
            raw_dir=root / "data" / "raw",
            normalized_dir=root / "data" / "normalized",
            features_dir=root / "data" / "features",
            cache_dir=root / "data" / "cache",
            registry_db_path=root / "data" / "cache" / "_registry" / "runs.sqlite",
        ),
        exchanges=[
            ExchangeConfig(name="binance", quote_assets=["USDT", "USDC"]),
            ExchangeConfig(name="okx", quote_assets=["USDT", "USDC"]),
        ],
        research=ResearchConfig(
            universe_filters={
                "min_avg_dollar_volume": 1_000_000,
                "exclude_stablecoins": True,
            }
        ),
    )


def load_settings(path: str | Path | None = None) -> AppSettings:
    defaults = default_settings()
    project_root = _project_root()
    if path is None:
        return defaults

    settings_path = Path(path)
    if not settings_path.exists():
        raise FileNotFoundError(f"settings file not found: {settings_path}")

    with settings_path.open("r", encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}

    project = payload.get("project", {})
    storage = payload.get("storage", {})
    exchanges = payload.get("exchanges", [])
    research = payload.get("research", {})
    if _uses_shared_storage(storage):
        root_dir = defaults.storage.root_dir
        raw_dir = defaults.storage.raw_dir
        normalized_dir = defaults.storage.normalized_dir
        features_dir = defaults.storage.features_dir
        cache_dir = defaults.storage.cache_dir
        registry_db_path = defaults.storage.registry_db_path
    else:
        root_dir = _resolve_storage_path(storage.get("root_dir"), default=defaults.storage.root_dir, project_root=project_root)
        raw_dir = _resolve_storage_path(storage.get("raw_dir"), default=defaults.storage.raw_dir, project_root=project_root)
        normalized_dir = _resolve_storage_path(
            storage.get("normalized_dir"),
            default=defaults.storage.normalized_dir,
            project_root=project_root,
        )
        features_dir = _resolve_storage_path(storage.get("features_dir"), default=defaults.storage.features_dir, project_root=project_root)
        cache_dir = _resolve_storage_path(storage.get("cache_dir"), default=defaults.storage.cache_dir, project_root=project_root)
        registry_db_default = cache_dir / "_registry" / "runs.sqlite"
        registry_db_path = _resolve_storage_path(
            storage.get("registry_db_path"),
            default=registry_db_default,
            project_root=project_root,
        )

    return AppSettings(
        name=project.get("name", defaults.name),
        timezone=project.get("timezone", defaults.timezone),
        storage=StorageConfig(
            root_dir=root_dir,
            raw_dir=raw_dir,
            normalized_dir=normalized_dir,
            features_dir=features_dir,
            cache_dir=cache_dir,
            registry_db_path=registry_db_path,
        ),
        exchanges=[
            ExchangeConfig(
                name=item["name"],
                enabled=item.get("enabled", True),
                market_types=item.get("market_types", ["spot", "perp"]),
                quote_assets=item.get("quote_assets", ["USDT"]),
            )
            for item in (exchanges or [{"name": exchange.name} for exchange in defaults.exchanges])
        ],
        research=ResearchConfig(
            bar_frequencies=research.get("bar_frequencies", defaults.research.bar_frequencies),
            benchmark_symbols=research.get("benchmark_symbols", defaults.research.benchmark_symbols),
            universe_filters=research.get("universe_filters", defaults.research.universe_filters),
        ),
    )
