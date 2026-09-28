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


def test_nested_active_readers_remain_gated_and_artifact_copies_do_not(tmp_path):
    for relative in ("scripts/nested/reader.py", "artifacts/snapshot/scripts/reader.py"):
        path = tmp_path / "research/example" / relative
        path.parent.mkdir(parents=True)
        path.write_text("import pandas as pd\npd.read_parquet('data/unregistered.parquet')\n")
    errors = check_trusted_consumers.discover_unfrozen_direct_lake_scripts(tmp_path)
    assert len(errors) == 1 and "scripts/nested/reader.py" in errors[0]


def test_only_archived_private_source_can_be_absent(tmp_path, monkeypatch):
    classify = check_trusted_consumers.AuxiliaryClassification
    entries = (
        classify("research/f/artifacts/sources/old.py", "main", "archived-third-party-source", "private source snapshot"),
        classify("research/f/scripts/active.py", "main", "archived-third-party-source", "active path must exist"),
        classify("research/f/artifacts/required.py", "main", "frozen-artifact-consumer", "explicitly required evidence"),
    )
    monkeypatch.setattr(check_trusted_consumers, "AUXILIARY_CLASSIFICATIONS", entries)
    errors = check_trusted_consumers.validate_auxiliary_classifications(tmp_path)
    assert len(errors) == 2
    assert all("sources/old.py" not in error for error in errors)


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


def test_unregistered_direct_parquet_script_is_denied(tmp_path: Path) -> None:
    scripts = tmp_path / "research" / "hype" / "1h-adaptive-regime" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "probe_untrusted_reader.py").write_text(
        'frame = read_parquet("data/normalized/ohlcv/exchange=binance/demo.parquet")\n',
        encoding="utf-8",
    )
    errors = check_trusted_consumers.discover_unfrozen_direct_lake_scripts(tmp_path)
    assert any("probe_untrusted_reader.py" in error for error in errors)


FROZEN_RESEARCH_SCRIPTS_MAX_LINES = 259


def test_frozen_research_scripts_can_only_shrink() -> None:
    path = GOVERNANCE_SCRIPTS / "frozen_research_scripts.txt"
    raw = path.read_bytes()
    line_count = raw.count(b"\n")
    if raw and not raw.endswith(b"\n"):
        line_count += 1
    assert line_count <= FROZEN_RESEARCH_SCRIPTS_MAX_LINES
    assert line_count > 0


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


def test_new_bundle_startup_consumer_still_requires_registration(tmp_path: Path) -> None:
    scripts = tmp_path / "research" / "btc" / "1h-new-family" / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "load_bundle.py").write_text(
        "from strategy_lab.data.research_bundle import require_research_startup\n",
        encoding="utf-8",
    )
    errors = check_trusted_consumers.discover_unregistered_binance_ohlcv_scripts(tmp_path)
    assert any("load_bundle.py" in error and "not registered" in error for error in errors)


def test_explicit_module_entrypoint_requires_a_module_call(tmp_path: Path) -> None:
    path = tmp_path / "consumer.py"
    spec = check_trusted_consumers.ConsumerSpec(
        "consumer.py", ("<module>",), ("require_research_startup",),
        "binance-bundle-startup-consumer",
    )
    path.write_text("inputs = require_research_startup(request, project_root=root)\n")
    assert check_trusted_consumers.scan_consumer(tmp_path, spec) == []

    # Imports, a bare reference and an uncalled helper must not satisfy the
    # new explicit module route. This leaves existing function scans unchanged.
    for source in (
        "from reader import require_research_startup\n",
        "loader = require_research_startup\n",
        "def unused():\n    return require_research_startup(request)\n",
    ):
        path.write_text(source)
        errors = check_trusted_consumers.scan_consumer(tmp_path, spec)
        assert any("do not call require_research_startup()" in error for error in errors)


def test_tpsa_account_consumers_are_classified_without_frozen_exceptions() -> None:
    prefix = "research/asset-portfolios/1d-tpsa-long-account/scripts/"
    specs = [
        spec for spec in (
            *check_trusted_consumers.ACTIVE_TRUSTED_CONSUMERS,
            *check_trusted_consumers.BINANCE_CATALOG_CONSUMERS,
        ) if spec.path.startswith(prefix)
    ]
    assert {Path(spec.path).name for spec in specs} == {"load_prices.py", "account_acceptance.py"}
    for spec in specs:
        assert spec.required_calls
        assert check_trusted_consumers.scan_consumer(REPOSITORY_ROOT, spec) == []
    errors = (
        check_trusted_consumers.validate_auxiliary_classifications(REPOSITORY_ROOT)
        + check_trusted_consumers.discover_unregistered_binance_ohlcv_scripts(REPOSITORY_ROOT)
        + check_trusted_consumers.discover_unfrozen_direct_lake_scripts(REPOSITORY_ROOT)
    )
    assert not [error for error in errors if prefix in error]
    assert not any(path.startswith(prefix) for path in check_trusted_consumers.FROZEN_LEGACY_OHLCV_GLOBS)
    assert not any(path.startswith(prefix) for path in check_trusted_consumers.load_frozen_research_scripts(REPOSITORY_ROOT))
