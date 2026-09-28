from __future__ import annotations

import importlib.util
import json
import sys
from datetime import date
from pathlib import Path
from types import ModuleType


GOVERNANCE_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts" / "governance"
GOVERNANCE_DOCS = Path(__file__).resolve().parents[1] / "docs" / "research-governance"
sys.path.insert(0, str(GOVERNANCE_SCRIPTS))


def _load_script_module(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        name, GOVERNANCE_SCRIPTS / f"{name}.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


schema_utils = _load_script_module("schema_utils")
validate_live_specs = _load_script_module("validate_live_specs")
check_promotion_surface = _load_script_module("check_promotion_surface")
check_parity_report = _load_script_module("check_parity_report")


HANDOFF_FM = """\
---
schema_version: "1.0"
spec_role: lab_handoff
family_id: DEMO
main_status: registered
spec_status: draft
strategy_id: DEMO-V1
runner_kind: demo
peer_spec: crates/quant-runner/src/runner/strategies/demo/DEMO-V1-SPEC.md
approval_level_max: none
---

# Demo
"""

PROMOTED_FM = """\
---
schema_version: "1.0"
spec_role: lab_handoff
family_id: DEMO
main_status: dry-run
spec_status: active
strategy_id: DEMO-V1
runner_kind: demo
peer_spec: crates/quant-runner/src/runner/strategies/demo/DEMO-V1-SPEC.md
approval_level_max: dry_run
---

# Demo dry-run
"""


def _write_spec(root: Path, name: str, text: str) -> Path:
    path = root / "research" / "demo" / "fam" / "live-specs" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_missing_front_matter_is_error(tmp_path: Path) -> None:
    _write_spec(tmp_path, "no-fm.md", "# No front matter\n")
    errors = validate_live_specs.validate(
        research_root=tmp_path / "research",
        skip_cross_repo=True,
    )
    assert any("missing YAML front matter" in error for error in errors)


def test_readme_without_front_matter_is_ignored(tmp_path: Path) -> None:
    _write_spec(tmp_path, "ok.md", HANDOFF_FM)
    readme = tmp_path / "research" / "demo" / "fam" / "live-specs" / "README.md"
    readme.write_text("# index\n", encoding="utf-8")
    errors = validate_live_specs.validate(
        research_root=tmp_path / "research",
        skip_cross_repo=True,
    )
    assert errors == []


def test_unknown_spec_role_is_error(tmp_path: Path) -> None:
    _write_spec(
        tmp_path,
        "bad-role.md",
        "---\nspec_role: not_a_role\n---\n\n# Bad\n",
    )
    errors = validate_live_specs.validate(
        research_root=tmp_path / "research",
        skip_cross_repo=True,
    )
    assert any("spec_role 'not_a_role'" in error for error in errors)


def test_supporting_schemas_accept_minimal_front_matter() -> None:
    ensemble = {
        "schema_version": "1.0",
        "spec_role": "ensemble_component",
        "family_id": "HYPE-5M-PBTR",
        "component_id": "HYPE-5M-ENS-S01",
        "spec_status": "draft",
    }
    feasibility = {
        "schema_version": "1.0",
        "spec_role": "live_feasibility",
        "family_id": "TRX-1H-AR",
        "strategy_id": "TRX-1H-AR-LIVE-FEASIBILITY-2026-07-03",
        "spec_status": "active",
    }
    reproduction = {
        "schema_version": "1.0",
        "spec_role": "external_reproduction",
        "family_id": "HYPE-1D-MA7-ABT",
        "strategy_id": "HYPE-1D-MA7-ABT-V7.1",
        "spec_status": "active",
        "document_type": "external_reproduction_spec",
    }
    schema_dir = GOVERNANCE_DOCS / "schemas"
    assert not schema_utils.schema_errors(
        ensemble, schema_dir / "live-spec-ensemble-component-frontmatter.schema.json"
    )
    assert not schema_utils.schema_errors(
        feasibility, schema_dir / "live-spec-live-feasibility-frontmatter.schema.json"
    )
    assert not schema_utils.schema_errors(
        reproduction,
        schema_dir / "live-spec-external-reproduction-frontmatter.schema.json",
    )


def test_cross_repo_peer_spec_must_point_back(tmp_path: Path) -> None:
    spec = _write_spec(
        tmp_path,
        "demo-live.md",
        PROMOTED_FM,
    )
    runner = tmp_path / "quant-runner"
    peer = (
        runner
        / "crates/quant-runner/src/runner/strategies/demo/DEMO-V1-SPEC.md"
    )
    peer.parent.mkdir(parents=True)
    peer.write_text(
        "---\npeer_spec: research/demo/fam/live-specs/demo-live.md\n---\n\n# peer\n",
        encoding="utf-8",
    )
    errors, skips = validate_live_specs.validate_detailed(
        research_root=tmp_path / "research",
        runner_root=runner,
    )
    assert skips == []
    assert errors == []
    peer.write_text(
        "---\npeer_spec: research/wrong.md\n---\n\n# peer\n",
        encoding="utf-8",
    )
    errors, _skips = validate_live_specs.validate_detailed(
        research_root=tmp_path / "research",
        runner_root=runner,
    )
    assert any("未反向指向本文件" in error for error in errors)
    assert spec.exists()


def test_cross_repo_skipped_when_runner_missing(tmp_path: Path) -> None:
    _write_spec(tmp_path, "ok.md", HANDOFF_FM)
    _errors, skips = validate_live_specs.validate_detailed(
        research_root=tmp_path / "research",
        runner_root=tmp_path / "missing-runner",
    )
    assert any("跨仓校验未执行" in note for note in skips)


def test_promotion_surface_requires_tracking_and_parity(tmp_path: Path) -> None:
    _write_spec(tmp_path, "demo-live.md", PROMOTED_FM)
    family = tmp_path / "research" / "demo" / "fam"
    errors, warnings = check_promotion_surface.check_promotion_surface(
        research_root=tmp_path / "research",
        today=date(2026, 9, 3),
    )
    assert any("runner-tracking" in error for error in errors)
    assert any("parity-report.schema.json" in error for error in errors)

    tracking = family / "runner-tracking"
    tracking.mkdir()
    (tracking / "demo-runner-2026-07-10.md").write_text("# old\n", encoding="utf-8")
    artifacts = family / "artifacts"
    artifacts.mkdir()
    (artifacts / "demo_parity.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "strategy_id": "DEMO-V1",
                "runner_kind": "demo",
                "runner_commit": "abc",
                "lab_commit": "def",
                "snapshot_id": "snap",
                "gate_level": "parity",
                "command": "not run",
                "window": {"start": "a", "end": "b", "bars": 0},
                "trade_path": {
                    "reference_trades": 1,
                    "runtime_trades": 0,
                    "path_mismatches": 1,
                    "fields_compared": [],
                },
                "conclusion": "FAIL",
                "blockers": ["pending"],
            }
        ),
        encoding="utf-8",
    )
    errors, warnings = check_promotion_surface.check_promotion_surface(
        research_root=tmp_path / "research",
        today=date(2026, 9, 3),
    )
    assert errors == []
    assert any("2026-07-10" in warning for warning in warnings)


def test_parity_zero_reports_fail_only_when_promoted() -> None:
    assert check_parity_report.promoted_requires_parity_reports(0, True)
    assert check_parity_report.promoted_requires_parity_reports(0, False) == []
    assert check_parity_report.promoted_requires_parity_reports(2, True) == []
