from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


GOVERNANCE_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "governance"
REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _load_script_module(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        name, GOVERNANCE_SCRIPTS / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


check_trusted_consumers = _load_script_module("check_trusted_consumers")


def test_repository_governed_consumers_pass() -> None:
    assert check_trusted_consumers.run_checks(REPOSITORY_ROOT) == []


def test_scanner_rejects_direct_parquet_and_cache_calls(
    tmp_path: Path,
) -> None:
    (tmp_path / "consumer.py").write_text(
        """
def load_market(warehouse, path):
    frame = warehouse.load_trusted_ohlcv(timeframe="15m")
    cached = read_parquet(path)
    refresh_cache()
    return frame, cached
""",
        encoding="utf-8",
    )
    spec = check_trusted_consumers.ConsumerSpec(
        "consumer.py", ("load_market",)
    )

    errors = check_trusted_consumers.scan_consumer(tmp_path, spec)

    assert any("read_parquet()" in error for error in errors)
    assert any("cache-like function refresh_cache()" in error for error in errors)


def test_scanner_rejects_generic_ohlcv_loader(tmp_path: Path) -> None:
    (tmp_path / "consumer.py").write_text(
        """
def load_market(warehouse):
    return warehouse.load_dataset(kind=DatasetKind.OHLCV)
""",
        encoding="utf-8",
    )
    spec = check_trusted_consumers.ConsumerSpec(
        "consumer.py", ("load_market",)
    )

    errors = check_trusted_consumers.scan_consumer(tmp_path, spec)

    assert any("do not call load_trusted_ohlcv()" in error for error in errors)
    assert any("uses load_dataset()" in error for error in errors)


def test_producer_and_archive_classifications_are_explicit() -> None:
    assert (
        check_trusted_consumers.classify_path(
            "research/hype/demo/scripts/fetch_demo.py"
        )
        == "producer-excluded"
    )
    assert (
        check_trusted_consumers.classify_path(
            "archive/scripts/research/demo.py"
        )
        == "archived-excluded"
    )
    assert (
        check_trusted_consumers.classify_path(
            "research/asset-portfolios/"
            "15m-asset-specific-six-strategy-selector/scripts/demo.py"
        )
        == "archived-excluded"
    )
    assert (
        check_trusted_consumers.classify_path("research/demo/scripts/demo.py")
        == "unclassified"
    )
    embedded = {
        item.symbol: item.classification
        for item in check_trusted_consumers.AUXILIARY_CLASSIFICATIONS
    }
    assert embedded["fetch_fapi_klines"] == "embedded-legacy-producer-unused"
    assert embedded["fetch_binance_klines"] == "embedded-producer-route"


def test_unregistered_binance_catalog_consumer_is_detected(tmp_path: Path) -> None:
    research = tmp_path / "research" / "asset-portfolios" / "4h-ma7-regime-continuation" / "scripts"
    research.mkdir(parents=True)
    (research / "new_unregistered.py").write_text(
        "from strategy_lab.data.catalog import load_trusted_dataset\n",
        encoding="utf-8",
    )
    errors = check_trusted_consumers.discover_unregistered_binance_ohlcv_scripts(tmp_path)
    assert any("new_unregistered.py" in error for error in errors)


def test_unregistered_catalog_consumer_outside_watch_dir_is_detected(tmp_path: Path) -> None:
    """Catalog API use is in-scope for all of research/, not only the 4h watch dir."""
    scripts = tmp_path / "research" / "btc" / "1h-new-family" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "load_btc.py").write_text(
        "from strategy_lab.data.catalog import load_trusted_research_dataset\n",
        encoding="utf-8",
    )
    errors = check_trusted_consumers.discover_unregistered_binance_ohlcv_scripts(tmp_path)
    assert any("load_btc.py" in error for error in errors)
