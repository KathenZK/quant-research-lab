"""研究文档一致性检查。

把 research/ 的索引登记、家族目录骨架和证据契约变成可执行检查，
防止路由表与目录结构漂移（历史上 6h-rs4-regime-switch 曾建目录但未登记索引）。
规则来源：.cursor/rules/research-report-storage.mdc 与 docs/research-governance/strategy-status-glossary.md。
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import yaml
import pytest
from jsonschema import Draft202012Validator, FormatChecker

from strategy_lab.governance_scope import research_sources
ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "research"
GOVERNANCE_DOCS = ROOT / "docs" / "research-governance"

# 资产/主题目录：其下一级子目录被视为策略家族目录。
ASSET_DIRS = ["hype", "btc", "eth", "sol", "trx", "bnb", "asset-portfolios", "public-strategies"]

# 扁平结构的 grandfathered 目录，不按 <asset>/<timeframe>-<family> 检查。
FLAT_GRANDFATHERED = {"mu"}

# 非家族的基础设施目录。
NON_FAMILY_DIRS = {"_shared-kernels"}


def _frontmatter(md: Path) -> dict:
  lines = md.read_text(encoding="utf-8").splitlines()
  if not lines or lines[0].strip() != "---":
    return {}
  try:
    end = lines.index("---", 1)
  except ValueError:
    return {}
  parsed = yaml.safe_load("\n".join(lines[1:end]))
  return parsed if isinstance(parsed, dict) else {}


def _schema_problems(instance: object, schema_path: Path) -> list[str]:
  schema = json.loads(schema_path.read_text(encoding="utf-8"))
  validator = Draft202012Validator(schema, format_checker=FormatChecker())
  return [
    f"{'.'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
    for error in sorted(validator.iter_errors(instance), key=lambda item: list(item.path))
  ]

_ALLOWED_RESEARCH_CLASSIFICATIONS = {"strategy_family", "diagnostic_topic"}


def iter_family_dirs() -> list[tuple[str, Path]]:
  families: list[tuple[str, Path]] = []
  for asset in ASSET_DIRS:
    asset_dir = RESEARCH / asset
    assert asset_dir.is_dir(), f"缺少资产目录 research/{asset}/"
    for child in sorted(asset_dir.iterdir()):
      if not child.is_dir() or child.name.startswith(("__", ".")):
        continue
      families.append((f"{asset}/{child.name}", child))
  return families


def test_asset_dirs_have_readme() -> None:
  missing = [
    asset
    for asset in ASSET_DIRS + sorted(FLAT_GRANDFATHERED)
    if not (RESEARCH / asset / "README.md").is_file()
  ]
  assert not missing, f"资产目录缺少 README.md: {missing}"


def test_family_dirs_have_readme_and_decision_log() -> None:
  problems = []
  for key, family_dir in iter_family_dirs():
    if not (family_dir / "README.md").is_file():
      problems.append(f"{key}: 缺少 README.md")
    if not (family_dir / "decision-log.md").is_file():
      problems.append(f"{key}: 缺少 decision-log.md")
  assert not problems, "家族目录骨架不完整:\n" + "\n".join(problems)


def test_strategy_families_have_core_ledger_and_topics_are_explicit() -> None:
  problems = []
  for key, family_dir in iter_family_dirs():
    readme = family_dir / "README.md"
    classification = _frontmatter(readme).get(
      "research_classification", "strategy_family"
    )
    if classification not in _ALLOWED_RESEARCH_CLASSIFICATIONS:
      problems.append(
        f"{key}: research_classification={classification!r} 非法，"
        f"只允许 {sorted(_ALLOWED_RESEARCH_CLASSIFICATIONS)}"
      )
      continue
    has_ledger = any(family_dir.glob("*core-ledger*.md"))
    if classification == "diagnostic_topic" and has_ledger:
      problems.append(f"{key}: diagnostic_topic 不得伪造策略 core ledger")
    if classification == "strategy_family" and not has_ledger:
      problems.append(
        f"{key}: strategy_family 缺少 <family-id>-core-ledger.md；"
        "若确属非策略诊断主题，请在 README front matter 显式声明 "
        "research_classification: diagnostic_topic"
      )
  assert not problems, "core-ledger 覆盖检查失败:\n" + "\n".join(problems)


def test_core_ledger_template_defines_required_sections() -> None:
  template = GOVERNANCE_DOCS / "core-ledger-template.md"
  assert template.is_file(), "缺少 docs/research-governance/core-ledger-template.md"
  text = template.read_text(encoding="utf-8")
  required_headings = [
    "## Family Identity",
    "## Current State",
    "## Version Rules",
    "## Version Table",
    "## Shared Assumptions",
    "## Evidence Map",
    "## What Not To Put Here",
  ]
  missing = [heading for heading in required_headings if heading not in text]
  assert not missing, "core-ledger-template.md 缺少标准章节:\n" + "\n".join(missing)


def test_families_registered_in_top_level_index() -> None:
  """索引更新义务：每个家族目录必须出现在 research/README.md 路由表中。"""
  index_text = (RESEARCH / "README.md").read_text(encoding="utf-8")
  missing = [
    key for key, _ in iter_family_dirs() if f"{key}/" not in index_text
  ]
  assert not missing, (
    "以下家族目录未登记进 research/README.md 路由表:\n" + "\n".join(missing)
  )


def test_families_registered_in_asset_index() -> None:
  problems = []
  for key, family_dir in iter_family_dirs():
    asset = key.split("/", 1)[0]
    asset_readme = (RESEARCH / asset / "README.md").read_text(encoding="utf-8")
    if family_dir.name not in asset_readme:
      problems.append(f"{key}: 未出现在 research/{asset}/README.md")
  assert not problems, "资产索引缺项:\n" + "\n".join(problems)


def test_top_level_index_links_resolve() -> None:
  """research/README.md 与 hype/README.md 中引用的仓库相对路径必须存在。

  同时校验反引号路径和 Markdown 链接（research-report-storage.mdc 要求
  路由表使用可点击链接，链接失效同样属于索引漂移）。
  """
  problems = []
  index_files = [(RESEARCH / "README.md", RESEARCH)]
  for asset in ASSET_DIRS + sorted(FLAT_GRANDFATHERED):
    index_files.append((RESEARCH / asset / "README.md", RESEARCH / asset))
  for md, base in index_files:
    text = md.read_text(encoding="utf-8")
    refs = [m.group(1) for m in re.finditer(r"`([^`\s]+?\.md)`", text)]
    refs += [m.group(1) for m in re.finditer(r"\]\(([^)\s]+?\.md)\)", text)]
    for rel in refs:
      # 无目录成分的裸反引号文件名（如泛指的 decision-log.md）不视为链接；
      # Markdown 链接则总是校验。
      if rel.startswith(("http", "/")):
        continue
      if "/" not in rel and f"`{rel}`" in text and f"]({rel})" not in text:
        continue
      if not (base / rel).resolve().exists():
        problems.append(f"{md.relative_to(ROOT)}: 引用不存在的文件 {rel}")
  assert not problems, "索引链接失效:\n" + "\n".join(problems)


def test_no_links_to_retired_reports_dir() -> None:
  """顶层 reports/ 已退役；research/ 文档不得再链接它（legacy-canvas 除外）。"""
  pattern = re.compile(r"\]\((?:\.\./)*reports/|\]\(/reports/")
  offenders = []
  for md in RESEARCH.rglob("*.md"):
    if "legacy-canvas" in md.parts:
      continue
    if pattern.search(md.read_text(encoding="utf-8")):
      offenders.append(str(md.relative_to(ROOT)))
  assert not offenders, "以下文档仍链接已退役的 reports/:\n" + "\n".join(offenders)


GRANDFATHERED_REPRO_SPECS: set[str] = set()

# 附录标题必须含此标记，其后的仓库内部引用才被允许。
_REPRO_APPENDIX_MARKER = "非复现依赖"
_REPRO_INTERNAL_REF = re.compile(
    r"(?:research|scripts|artifacts)/[A-Za-z0-9_\-./]+\.(?:py|json|csv|md|html|parquet)"
    r"|/Users/ZK"
    r"|uv run"
)


def test_external_reproduction_specs_are_self_contained() -> None:
    """对外复现规格必须自包含：仓库内部引用只能出现在"非复现依赖"附录之后。

    规则来源：docs/research-governance/external-reproduction-spec.md。同事只会拿到这一个
    Markdown 文件，正文里引用仓库脚本/产物/绝对路径都会让复现在仓库外失败。
    """
    problems = []
    candidates = []
    for md in sorted(RESEARCH.rglob("*.md")):
        frontmatter = _frontmatter(md)
        named = "reproduction-spec" in md.name.lower()
        declared = frontmatter.get("document_type") == "external_reproduction_spec"
        if named or declared:
            candidates.append((md, frontmatter, named, declared))
    for md, frontmatter, named, declared in candidates:
        rel = str(md.relative_to(RESEARCH))
        lines = md.read_text(encoding="utf-8").splitlines()
        metadata_violations = []
        if not declared:
            metadata_violations.append(
                "缺少 front matter: document_type: external_reproduction_spec"
            )
        if not isinstance(frontmatter.get("intended_audience"), str) or not frontmatter.get(
            "intended_audience", ""
        ).strip():
            metadata_violations.append("缺少非空 intended_audience")
        if declared and not named:
            metadata_violations.append("用途已声明但文件名缺少 reproduction-spec")
        appendix_start = next(
            (
                i
                for i, line in enumerate(lines)
                if line.startswith("#") and _REPRO_APPENDIX_MARKER in line
            ),
            len(lines),
        )
        violations = [
            f"  L{i + 1}: {line.strip()[:100]}"
            for i, line in enumerate(lines[:appendix_start])
            if _REPRO_INTERNAL_REF.search(line)
        ]
        all_violations = metadata_violations + violations
        if all_violations and rel not in GRANDFATHERED_REPRO_SPECS:
            problems.append(
                f"{rel}: 外部复现规格声明/自包含不合规:\n"
                + "\n".join(all_violations[:8])
            )
        if not all_violations and rel in GRANDFATHERED_REPRO_SPECS:
            problems.append(f"{rel}: 已整改，请从 GRANDFATHERED_REPRO_SPECS 移除")
    assert not problems, "对外复现规格自包含检查失败:\n" + "\n".join(problems)


def test_glossary_main_statuses_match_live_spec_schema() -> None:
  """机器主状态与文档定义一致；研究叙述和结果说明不受词表限制。"""
  glossary = (GOVERNANCE_DOCS / "strategy-status-glossary.md").read_text(
    encoding="utf-8"
  )
  heading = "## 主状态定义"
  assert heading in glossary, "glossary 缺少主状态定义"
  section = glossary.split(heading, 1)[1].split("\n## ", 1)[0]
  documented = set(re.findall(r"^\|\s*`([^`]+)`\s*\|", section, re.MULTILINE))
  schema = json.loads(
    (GOVERNANCE_DOCS / "schemas" / "lab-live-spec-frontmatter.schema.json").read_text(
      encoding="utf-8"
    )
  )
  machine_statuses = set(schema["properties"]["main_status"]["enum"])
  assert documented, "glossary 主状态表为空或无法解析"
  assert documented == machine_statuses, (
    f"glossary 与 main_status schema 不一致: "
    f"仅文档有 {sorted(documented - machine_statuses)}; "
    f"仅 schema 有 {sorted(machine_statuses - documented)}"
  )


def test_shared_kernel_versions_are_frozen() -> None:
  """_shared-kernels 冻结版本目录的 SHA256 必须与 kernel README 登记值一致。"""
  import hashlib

  kernels_dir = RESEARCH / "_shared-kernels"
  assert (kernels_dir / "README.md").is_file()
  problems = []
  for kernel_dir in sorted(kernels_dir.iterdir()):
    if not kernel_dir.is_dir():
      continue
    readme = kernel_dir / "README.md"
    if not readme.is_file():
      problems.append(f"{kernel_dir.name}: 缺少 README.md")
      continue
    text = readme.read_text(encoding="utf-8")
    for version_dir in sorted(kernel_dir.glob("v*")):
      if not version_dir.is_dir():
        continue
      manifest_pins = {}
      manifest = version_dir / "manifest.json"
      if manifest.is_file() and hashlib.sha256(manifest.read_bytes()).hexdigest() in text:
        manifest_pins = json.loads(manifest.read_text()).get("files", {})
        for relative, expected in manifest_pins.items():
          frozen_file = version_dir / relative
          if not frozen_file.is_file() or hashlib.sha256(frozen_file.read_bytes()).hexdigest() != expected:
            problems.append(f"{kernel_dir.name}/{version_dir.name}/{relative}: 冻结 manifest 不匹配")
      for engine in sorted(version_dir.glob("*.py")):
        digest = hashlib.sha256(engine.read_bytes()).hexdigest()
        if digest not in text and manifest_pins.get(engine.name) != digest:
          problems.append(
            f"{kernel_dir.name}/{version_dir.name}/{engine.name}: "
            f"实际 SHA256 {digest} 未在 kernel README 登记（冻结版本被改动或未登记）"
          )
  assert not problems, "共享内核冻结检查失败:\n" + "\n".join(problems)


def test_kernel_manifest_chain_rejects_tampered_sources_and_manifests(tmp_path, monkeypatch):
  monkeypatch.setattr(sys.modules[__name__], "RESEARCH", tmp_path)
  kernels = tmp_path / "_shared-kernels"
  version = kernels / "example/v1"
  version.mkdir(parents=True)
  (kernels / "README.md").write_text("example")
  engine = version / "engine.py"
  engine.write_text("VALUE = 1\n")
  manifest = version / "manifest.json"
  manifest.write_text(json.dumps({"files": {"engine.py": hashlib.sha256(engine.read_bytes()).hexdigest()}}))
  (version.parent / "README.md").write_text("v1 " + hashlib.sha256(manifest.read_bytes()).hexdigest())
  test_shared_kernel_versions_are_frozen()
  engine.write_text("VALUE = 2\n")
  with pytest.raises(AssertionError, match="manifest"):
    test_shared_kernel_versions_are_frozen()
  manifest.write_text(json.dumps({"files": {"engine.py": hashlib.sha256(engine.read_bytes()).hexdigest()}}))
  with pytest.raises(AssertionError, match="SHA256"):
    test_shared_kernel_versions_are_frozen()


def test_live_specs_directories_are_not_empty() -> None:
  problems = []
  for live_specs in sorted(path for path in RESEARCH.rglob("live-specs") if path.is_dir()):
    specs = [
      md
      for md in live_specs.rglob("*.md")
      if md.name.lower() != "readme.md"
    ]
    if not specs:
      problems.append(str(live_specs.relative_to(ROOT)))
  assert not problems, "以下 live-specs/ 只有 README 或为空:\n" + "\n".join(problems)


def test_lab_does_not_define_runtime_authority() -> None:
  forbidden = [
    GOVERNANCE_DOCS / "machine" / "active-strategy-manifest.json",
    GOVERNANCE_DOCS / "schemas" / "active-strategy-manifest.schema.json",
    GOVERNANCE_DOCS / "machine" / "external-runner-grandfathers.json",
    GOVERNANCE_DOCS / "schemas" / "external-runner-grandfathers.schema.json",
    ROOT / "scripts" / "governance" / "validate_manifest.py",
  ]
  existing = [path.relative_to(ROOT) for path in forbidden if path.exists()]
  assert not existing, (
    "运行与授权真源只允许存在于 quant-runner，Lab 不得恢复 active manifest: "
    f"{existing}"
  )


def test_governance_schemas_accept_canonical_contracts(tmp_path: Path) -> None:
  live_spec_schema = (
    GOVERNANCE_DOCS / "schemas" / "lab-live-spec-frontmatter.schema.json"
  )
  joint_frontmatter = {
    "schema_version": "1.0",
    "spec_role": "lab_handoff",
    "family_id": "EXAMPLE",
    "main_status": "dry-run",
    "spec_status": "active",
    "approval_level_max": "dry_run",
    "overlays": ["handoff"],
    "implementations": [
      {
        "strategy_id": "EXAMPLE-V1-A",
        "runner_kind": "example_a",
        "peer_spec": "crates/quant-runner/src/runner/strategies/example_a/A-SPEC.md",
      },
      {
        "strategy_id": "EXAMPLE-V1-B",
        "runner_kind": "example_b",
        "peer_spec": "crates/quant-runner/src/runner/strategies/example_b/B-SPEC.md",
      },
    ],
  }
  assert not _schema_problems(joint_frontmatter, live_spec_schema)
  joint_frontmatter["strategy_id"] = "AMBIGUOUS"
  assert _schema_problems(joint_frontmatter, live_spec_schema)

  scalar_frontmatter = {
    "schema_version": "1.0",
    "spec_role": "lab_handoff",
    "family_id": "EXAMPLE",
    "main_status": "registered",
    "spec_status": "draft",
    "approval_level_max": "none",
    "strategy_id": "EXAMPLE-V1",
    "runner_kind": "example",
    "peer_spec": "crates/quant-runner/src/runner/strategies/example/EXAMPLE-V1-SPEC.md",
  }
  assert not _schema_problems(scalar_frontmatter, live_spec_schema)
  scalar_frontmatter["peer_spec"] = (
    "quant-runner/crates/quant-runner/src/runner/strategies/example/EXAMPLE-V1-SPEC.md"
  )
  assert any("peer_spec" in problem for problem in _schema_problems(scalar_frontmatter, live_spec_schema))
  scalar_frontmatter["peer_spec"] = "/crates/quant-runner/src/runner/strategies/example/EXAMPLE-V1-SPEC.md"
  assert any("peer_spec" in problem for problem in _schema_problems(scalar_frontmatter, live_spec_schema))

  sys.path.insert(0, str(ROOT))
  try:
    from scripts.governance.check_parity_report import _validate_report
    from scripts.governance.validate_live_specs import validate as validate_live_specs
  finally:
    sys.path.pop(0)

  sentinel_schema = tmp_path / "sentinel.schema.json"
  sentinel_schema.write_text(
    json.dumps({"type": "object", "required": ["schema_was_loaded"]}),
    encoding="utf-8",
  )
  assert any(
    "schema_was_loaded" in error
    for error in validate_live_specs(sentinel_schema)
  )
  parity_artifact = tmp_path / "parity.json"
  parity_artifact.write_text("{}", encoding="utf-8")
  assert any(
    "schema_was_loaded" in error
    for error in _validate_report(parity_artifact, sentinel_schema, [])
  )


def test_shared_kernel_index_and_copy_boundaries() -> None:
  kernels_dir = RESEARCH / "_shared-kernels"
  shared_index = (kernels_dir / "README.md").read_text(encoding="utf-8")
  top_index = (RESEARCH / "README.md").read_text(encoding="utf-8")
  problems = []
  kernel_hashes: dict[str, Path] = {}
  for kernel_dir in sorted(path for path in kernels_dir.iterdir() if path.is_dir()):
    if kernel_dir.name not in shared_index:
      problems.append(f"{kernel_dir.name}: 未登记在 _shared-kernels/README.md")
    if kernel_dir.name not in top_index:
      problems.append(f"{kernel_dir.name}: 未登记在 research/README.md")
    readme = kernel_dir / "README.md"
    if not readme.is_file():
      continue
    text = readme.read_text(encoding="utf-8")
    for version_dir in sorted(kernel_dir.glob("v*")):
      if version_dir.is_dir() and version_dir.name not in text:
        problems.append(f"{kernel_dir.name}/{version_dir.name}: 未登记在 kernel README")
      for engine in version_dir.glob("*.py"):
        kernel_hashes[hashlib.sha256(engine.read_bytes()).hexdigest()] = engine
  # This original predates extraction into TSPR v1; its manifest explicitly records
  # capture_source as MTCS scripts/capture.py. Keep the original frozen bytes.
  original_source = "research/asset-portfolios/1d-medium-term-continuation-state/scripts/capture.py"
  original_digest = "42585a7289aacdb8b6a3727fcc575ec8b97294bcd70912fbf713799ef91dc351"
  assert hashlib.sha256((ROOT / original_source).read_bytes()).hexdigest() == original_digest
  for script in sorted(research_sources(ROOT)):
    if "_shared-kernels" in script.parts:
      continue
    digest = hashlib.sha256(script.read_bytes()).hexdigest()
    if script.relative_to(ROOT).as_posix() == original_source and digest == original_digest:
      continue
    if digest in kernel_hashes:
      problems.append(
        f"{script.relative_to(ROOT)}: 复制了共享内核 "
        f"{kernel_hashes[digest].relative_to(ROOT)}，应 SHA pin 引用"
      )
  assert not problems, "共享内核索引/复制边界失败:\n" + "\n".join(problems)
