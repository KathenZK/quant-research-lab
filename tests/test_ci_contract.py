"""Regression checks for public CI versus explicit private-data acceptance."""

import ast
import hashlib
import json
from pathlib import Path
import tomllib

import pytest

from strategy_lab.governance_scope import research_sources

pytest_plugins = ["pytester"]
ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("arguments", "outcomes"),
    [([], {"failed": 1, "skipped": 1}),
     (["--run-local-data"], {"failed": 2}),
     (["-m", "not local_data"], {"failed": 1, "deselected": 1})],
)
def test_missing_files_never_become_success(pytester, arguments, outcomes):
    pytester.makeconftest((ROOT / "tests/conftest.py").read_text())
    (pytester.path / "local_data_cases.json").write_text(
        json.dumps({"test_inputs.py::test_private_input": {"input": "data/private"}})
    )
    pytester.makeini("[pytest]\nmarkers = local_data: private research inputs")
    pytester.makepyfile(test_inputs='''
        from pathlib import Path
        def test_missing_source():
            Path("missing-source.py").read_text()
        def test_private_input():
            Path("data/private").read_text()
    ''')
    result = pytester.runpytest_subprocess("-q", *arguments)
    result.assert_outcomes(**outcomes)
    assert result.ret == pytest.ExitCode.TESTS_FAILED


def test_private_registry_has_exact_existing_functions_and_documented_inputs():
    registry = json.loads((ROOT / "tests/local_data_cases.json").read_text())
    for nodeid, item in registry.items():
        filename, function = nodeid.split("::")
        tree = ast.parse((ROOT / filename).read_text())
        assert function in {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}, nodeid
        assert item["reason"] and item["input"]
        assert item["input"].startswith("data/") or "/artifacts/" in item["input"], nodeid


def test_frozen_lint_exceptions_cannot_cover_modified_or_new_code():
    registry = json.loads((ROOT / "tests/frozen_test_lint.json").read_text())
    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    ignores = config["tool"]["ruff"]["lint"]["per-file-ignores"]
    assert ignores == {name: row["rules"] for name, row in registry.items()}
    for name, row in registry.items():
        assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == row["sha256"], name


def test_source_scope_excludes_only_research_artifacts(tmp_path):
    active = tmp_path / "research/family/scripts/nested/reader.py"
    artifact = tmp_path / "research/family/artifacts/snapshot/scripts/reader.py"
    for path in (active, artifact):
        path.parent.mkdir(parents=True)
        path.write_text("read_parquet('data/untrusted.parquet')")
    assert list(research_sources(tmp_path)) == [active]
