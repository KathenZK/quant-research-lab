"""研究文档一致性检查。

把 research/ 的索引更新义务、家族目录骨架和状态词约定变成可执行检查，
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
from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "research"
GOVERNANCE_DOCS = ROOT / "docs" / "research-governance"

# 资产/主题目录：其下一级子目录被视为策略家族目录。
ASSET_DIRS = ["hype", "btc", "eth", "sol", "trx", "bnb", "asset-portfolios"]

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

  同时校验反引号路径和 Markdown 链接（clickable-file-references.mdc 要求
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

    规则来源：.cursor/rules/external-reproduction-spec.mdc。同事只会拿到这一个
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


# 状态词校验：白名单从 glossary 解析，测试内不维护第二份词表。
GLOSSARY_PATH = GOVERNANCE_DOCS / "strategy-status-glossary.md"
_VERSION_TOKEN_RE = re.compile(
  r"^V\d+(?:\.\d+)*[A-Za-z]?(?:[-–]V?\d+(?:\.\d+)*[A-Za-z]?)?$"
)
_FAMILY_NAME_TOKEN_RE = re.compile(
  r"^[A-Z]{2,}(?:-[A-Z0-9]+){1,}$|^[A-Za-z][A-Za-z0-9]*-v\d+$"
)
_GLOSSARY_HEADINGS = {
  "main_status": "主状态定义",
  "modifiers": "修饰词（不是主状态）",
  "overlays": "Overlay 标签（不是主状态）",
  "result_labels": "结果标签（result labels）",
  "index_forward": "索引转发",
  "forbidden": "禁止的状态词",
}


def _glossary_section(text: str, heading: str) -> str:
  marker = f"## {heading}"
  start = text.find(marker)
  assert start >= 0, f"glossary 缺少章节 {heading!r}"
  rest = text[start + len(marker):]
  nxt = re.search(r"\n## ", rest)
  return rest if nxt is None else rest[: nxt.start()]


def _first_column_backticks(section: str) -> tuple[str, ...]:
  tokens: list[str] = []
  for line in section.splitlines():
    stripped = line.strip()
    if not stripped.startswith("|") or set(stripped) <= {"|", "-", " ", ":"}:
      continue
    cell = stripped.strip("|").split("|", 1)[0].strip()
    found = re.findall(r"`([^`]+)`", cell)
    if len(found) == 1:
      tokens.append(found[0])
  return tuple(dict.fromkeys(tokens))


def _forbidden_from_section(section: str) -> tuple[tuple[str, ...], tuple[str, ...]]:
  tokens: list[str] = []
  phrases: list[str] = []
  for line in section.splitlines():
    stripped = line.strip()
    if not stripped.startswith("- "):
      continue
    found = re.findall(r"`([^`]+)`", stripped)
    for item in found:
      if " " in item or "/" in item:
        phrases.append(item)
      else:
        tokens.append(item)
  return tuple(dict.fromkeys(tokens)), tuple(dict.fromkeys(phrases))


def load_glossary_token_sets() -> dict[str, frozenset[str]]:
  text = GLOSSARY_PATH.read_text(encoding="utf-8")
  main_status = _first_column_backticks(
    _glossary_section(text, _GLOSSARY_HEADINGS["main_status"])
  )
  modifiers = _first_column_backticks(
    _glossary_section(text, _GLOSSARY_HEADINGS["modifiers"])
  )
  overlays = _first_column_backticks(
    _glossary_section(text, _GLOSSARY_HEADINGS["overlays"])
  )
  result_labels = _first_column_backticks(
    _glossary_section(text, _GLOSSARY_HEADINGS["result_labels"])
  )
  index_forward = _first_column_backticks(
    _glossary_section(text, _GLOSSARY_HEADINGS["index_forward"])
  )
  forbidden_tokens, forbidden_phrases = _forbidden_from_section(
    _glossary_section(text, _GLOSSARY_HEADINGS["forbidden"])
  )
  assert main_status, "未能从 glossary 解析主状态"
  assert modifiers, "未能从 glossary 解析修饰词"
  assert result_labels, "未能从 glossary 解析结果标签"
  return {
    "main_status": frozenset(main_status),
    "modifiers": frozenset(modifiers),
    "overlays": frozenset(overlays),
    "result_labels": frozenset(result_labels),
    "index_forward": frozenset(index_forward),
    "forbidden_tokens": frozenset(forbidden_tokens),
    "forbidden_phrases": frozenset(forbidden_phrases),
    "allowed": frozenset(main_status)
    | frozenset(modifiers)
    | frozenset(overlays)
    | frozenset(result_labels)
    | frozenset(index_forward),
  }


def _is_identity_token(token: str) -> bool:
  return bool(_VERSION_TOKEN_RE.fullmatch(token) or _FAMILY_NAME_TOKEN_RE.fullmatch(token))


def tokenize_status_cell(cell: str, allowed: frozenset[str]) -> list[str]:
  """最长匹配 glossary 短语，其余按分隔符切开后校验。"""
  text = cell.replace("`", "")
  phrases = sorted(allowed, key=len, reverse=True)
  tokens: list[str] = []
  i = 0
  n = len(text)
  separators = set(" /|;；,，、()（）[]【】:：")
  while i < n:
    while i < n and (text[i] in separators or text[i].isspace()):
      i += 1
    if i >= n:
      break
    matched = None
    for phrase in phrases:
      if text.startswith(phrase, i):
        end = i + len(phrase)
        nxt = text[end] if end < n else ""
        prev = text[i - 1] if i else ""
        boundary_after = end == n or nxt in separators or nxt.isspace()
        boundary_before = i == 0 or prev in separators or prev.isspace()
        if boundary_after and boundary_before:
          matched = phrase
          break
    if matched:
      tokens.append(matched)
      i += len(matched)
      continue
    j = i
    while j < n and text[j] not in separators and not text[j].isspace():
      j += 1
    tokens.append(text[i:j])
    i = j
  return tokens


def _iter_status_cells(md: Path, *, skip_headings: frozenset[str] | None = None):
  """遍历 Markdown 表格中"状态"列的单元格，返回 (行号, 内容)。"""
  for lineno, cells, status_col, _dir_col in _iter_status_rows(md, skip_headings=skip_headings):
    yield lineno, cells[status_col]


PLATFORM_STATUS_HEADINGS = frozenset({"研究平台"})


def _iter_status_rows(md: Path, *, skip_headings: frozenset[str] | None = None):
  """遍历带状态列的表格行，返回 (行号, cells, status_col, dir_col)。"""
  skipped = PLATFORM_STATUS_HEADINGS if skip_headings is None else skip_headings
  status_col = None
  dir_col = None
  heading = ""
  for lineno, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
    if line.startswith("## "):
      heading = line[3:].strip()
    stripped = line.strip()
    if not stripped.startswith("|"):
      status_col = None
      dir_col = None
      continue
    cells = [c.strip() for c in stripped.strip("|").split("|")]
    if "状态" in cells:
      status_col = cells.index("状态")
      dir_col = next(
        (
          i
          for i, col in enumerate(cells)
          if col in {"Directory", "目录"} or "Directory" in col or "目录" in col
        ),
        None,
      )
      continue
    if status_col is None or set(stripped) <= {"|", "-", " ", ":"}:
      continue
    if heading in skipped:
      continue
    if len(cells) > status_col:
      yield lineno, cells, status_col, dir_col


def _href_from_cell(cell: str) -> str | None:
  match = re.search(r"\]\(([^)]+)\)", cell)
  if not match:
    return None
  return match.group(1).split()[0]


def _family_key_from_href(href: str, *, asset: str | None) -> tuple[str, str] | None:
  cleaned = href.split("#", 1)[0]
  if cleaned.startswith(("http://", "https://", "/")):
    return None
  parts = list(Path(cleaned).parts)
  if parts and parts[-1].lower() == "readme.md":
    parts = parts[:-1]
  if not parts:
    return None
  if asset is None:
    if len(parts) >= 2:
      return parts[0], parts[1]
    return None
  name = parts[-1]
  if name in {".", ".."}:
    return None
  return asset, name


def _asset_index_paths() -> list[Path]:
  paths = [RESEARCH / "README.md"]
  for child in sorted(RESEARCH.iterdir()):
    if not child.is_dir() or child.name.startswith((".", "_")):
      continue
    if child.name == "_shared-kernels":
      continue
    readme = child / "README.md"
    if readme.is_file():
      paths.append(readme)
  return paths


def test_routing_table_status_labels_use_glossary_vocabulary() -> None:
  """索引状态列 tokenize 后每个 token 必须属于 glossary 词表或版本号/家族名。"""
  token_sets = load_glossary_token_sets()
  allowed = token_sets["allowed"]
  problems = []
  for md in _asset_index_paths():
    for lineno, cell in _iter_status_cells(md):
      rel = md.relative_to(ROOT)
      lowered = cell.lower()
      hit_forbidden = [
        t for t in token_sets["forbidden_tokens"] if t in lowered
      ]
      if hit_forbidden:
        problems.append(f"{rel}:L{lineno}: 状态含已废弃词 {hit_forbidden}: {cell}")
      hit_phrases = [
        p for p in token_sets["forbidden_phrases"] if p in lowered
      ]
      if hit_phrases:
        problems.append(f"{rel}:L{lineno}: 已废弃状态短语 {hit_phrases}: {cell}")
      tokens = tokenize_status_cell(cell, allowed)
      if cell.strip() and not tokens:
        problems.append(f"{rel}:L{lineno}: 状态列无法分词: {cell}")
        continue
      unknown = [
        tok for tok in tokens if tok not in allowed and not _is_identity_token(tok)
      ]
      if unknown:
        problems.append(
          f"{rel}:L{lineno}: 非法状态 token {unknown}: {cell}"
        )
      if "见顶层" not in tokens and not (token_sets["main_status"] & set(tokens)):
        problems.append(
          f"{rel}:L{lineno}: 状态未包含任何 glossary 主状态词: {cell}"
        )
  assert not problems, "路由表状态词校验失败:\n" + "\n".join(problems)


def test_platform_routing_table_is_not_scored_as_strategy_status() -> None:
  """研究平台表使用治理状态，不得被当成策略 glossary 主状态，也不得用已废弃策略词。"""
  md = RESEARCH / "README.md"
  strategy_lines = {lineno for lineno, _ in _iter_status_cells(md)}
  platform_cells = [
    cell
    for lineno, cell in _iter_status_cells(md, skip_headings=frozenset())
    if lineno not in strategy_lines
  ]
  assert platform_cells, "research/README.md 应有「研究平台」状态列且不按策略 glossary 计分"
  token_sets = load_glossary_token_sets()
  problems = []
  for cell in platform_cells:
    lowered = cell.lower()
    hit_forbidden = [t for t in token_sets["forbidden_tokens"] if t in lowered]
    if hit_forbidden:
      problems.append(f"平台状态含已废弃策略词 {hit_forbidden}: {cell}")
    hit_phrases = [p for p in token_sets["forbidden_phrases"] if p in lowered]
    if hit_phrases:
      problems.append(f"平台状态含已废弃策略短语 {hit_phrases}: {cell}")
  assert not problems, "平台路由表不得借用已废弃策略状态词:\n" + "\n".join(problems)
  assert list(_iter_status_cells(md)), "策略家族路由表状态列必须仍接受 glossary 校验"


def test_asset_index_status_matches_top_level_or_defers() -> None:
  """顶层 research/README.md 家族状态串必须与资产 README 相同，或资产写「见顶层」。"""
  top = RESEARCH / "README.md"
  top_status: dict[tuple[str, str], str] = {}
  for lineno, cells, status_col, dir_col in _iter_status_rows(top):
    href = _href_from_cell(cells[dir_col]) if dir_col is not None else None
    if not href:
      continue
    key = _family_key_from_href(href, asset=None)
    if key is None:
      continue
    top_status[key] = cells[status_col]
  problems = []
  for (asset, family), expected in sorted(top_status.items()):
    asset_readme = RESEARCH / asset / "README.md"
    if not asset_readme.is_file():
      problems.append(f"{asset}/{family}: 缺少资产 README")
      continue
    found = None
    for _, cells, status_col, dir_col in _iter_status_rows(asset_readme):
      href = _href_from_cell(cells[dir_col]) if dir_col is not None else None
      if not href:
        continue
      key = _family_key_from_href(href, asset=asset)
      if key == (asset, family):
        found = cells[status_col]
        break
    if found is None:
      problems.append(f"{asset}/{family}: 资产 README 状态列缺少对应行")
    elif found not in {expected, "见顶层"}:
      problems.append(
        f"{asset}/{family}: 顶层状态 {expected!r} 与资产 README {found!r} 不一致"
      )
  assert not problems, "顶层/资产状态列不一致:\n" + "\n".join(problems)


_FAMILY_README_SKIP_ASSETS = {"_shared-kernels"}
_FAMILY_README_SKIP_CHILDREN = {
  "scripts",
  "artifacts",
  "notes",
  "diagnostics",
  "ablations",
  "specs",
  "live-specs",
  "runner-tracking",
  "legacy-canvas",
}
# shrink-only：只允许压缩，不允许新增超长家族 README。
FAMILY_README_SHRINK_ONLY_ALLOWLIST = {
  "research/asset-portfolios/15m-asset-specific-six-strategy-selector/README.md",
  "research/hype/1d-ma7-machine-learning-trend/README.md",
  "research/us-indexes/1d-nasdaq100-ma7-regime-continuation/README.md",
  "research/asset-portfolios/1d-ma7-cross-trend-probability/README.md",
  "research/bnb/15m-adaptive-regime/README.md",
  "research/sol/1h-adaptive-regime/README.md",
}


def _iter_family_readmes() -> list[Path]:
  found: list[Path] = []
  for readme in sorted(RESEARCH.glob("*/*/README.md")):
    asset = readme.parts[-3]
    child = readme.parts[-2]
    if asset in _FAMILY_README_SKIP_ASSETS or child in _FAMILY_README_SKIP_CHILDREN:
      continue
    found.append(readme)
  return found


def test_family_readmes_respect_length_budget() -> None:
  """家族 README 作为路由页应 ≤30 行；超长文件只能留在 shrink-only allowlist。"""
  problems = []
  seen_allowlist: set[str] = set()
  for readme in _iter_family_readmes():
    rel = str(readme.relative_to(ROOT))
    line_count = len(readme.read_text(encoding="utf-8").splitlines())
    if rel in FAMILY_README_SHRINK_ONLY_ALLOWLIST:
      seen_allowlist.add(rel)
      if line_count <= 30:
        problems.append(f"{rel}: 已压回 {line_count} 行，请从 shrink-only allowlist 移除")
      continue
    if line_count > 30:
      problems.append(f"{rel}: {line_count} 行，超过家族 README 30 行阈值")
  missing = FAMILY_README_SHRINK_ONLY_ALLOWLIST - seen_allowlist
  if missing:
    problems.append(f"allowlist 指向不存在的家族 README: {sorted(missing)}")
  assert not problems, "家族 README 长度检查失败:\n" + "\n".join(problems)


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
      for engine in sorted(version_dir.glob("*.py")):
        digest = hashlib.sha256(engine.read_bytes()).hexdigest()
        if digest not in text:
          problems.append(
            f"{kernel_dir.name}/{version_dir.name}/{engine.name}: "
            f"实际 SHA256 {digest} 未在 kernel README 登记（冻结版本被改动或未登记）"
          )
  assert not problems, "共享内核冻结检查失败:\n" + "\n".join(problems)


def test_core_ledgers_respect_length_budget() -> None:
  problems = []
  for ledger in sorted(RESEARCH.rglob("*core-ledger*.md")):
    rel = str(ledger.relative_to(RESEARCH))
    line_count = len(ledger.read_text(encoding="utf-8").splitlines())
    if line_count > 150:
      problems.append(f"{rel}: {line_count} 行，超过新主账 150 行阈值")
  assert not problems, "core ledger 长度检查失败:\n" + "\n".join(problems)


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


def test_status_combinations_are_not_self_contradictory() -> None:
  problems = []
  status_docs = [RESEARCH / "README.md"]
  status_docs.extend(RESEARCH / asset / "README.md" for asset in ASSET_DIRS)
  status_docs.extend(family_dir / "README.md" for _, family_dir in iter_family_dirs())
  status_docs.extend(RESEARCH.rglob("*core-ledger*.md"))
  for md in dict.fromkeys(status_docs):
    status_lines = {
      lineno: cell for lineno, cell in _iter_status_cells(md)
    }
    for lineno, line in enumerate(md.read_text(encoding="utf-8").splitlines(), 1):
      is_current_status = bool(
        re.match(
          r"^\s*(?:[-*>]\s*)*(?:\*{0,2})?(?:current status|当前状态|status)\s*[:：]",
          line,
          re.IGNORECASE,
        )
      )
      if lineno not in status_lines and not is_current_status:
        continue
      status_text = status_lines.get(lineno, line)
      code_spans = re.findall(r"`([^`]+)`", status_text)
      for fragment in code_spans or [status_text]:
        lowered = fragment.lower()
        if "dry-run" in lowered and "not promoted" in lowered:
          problems.append(f"{md.relative_to(ROOT)}:L{lineno}: dry-run 与 not promoted 并存")
        if "dry-run" in lowered and "no-go" in lowered:
          problems.append(f"{md.relative_to(ROOT)}:L{lineno}: dry-run 与 NO-GO 并存")
        if "no-go" in lowered and "not promoted" in lowered:
          problems.append(f"{md.relative_to(ROOT)}:L{lineno}: NO-GO 与 not promoted 并存")
        if "no-go" in lowered and "not live-ready" in lowered:
          problems.append(f"{md.relative_to(ROOT)}:L{lineno}: NO-GO 与 not live-ready 并存")
        if "archived" in lowered and "not promoted" in lowered:
          problems.append(f"{md.relative_to(ROOT)}:L{lineno}: archived 与 not promoted 并存")
        if "archived" in lowered and "not live-ready" in lowered:
          problems.append(f"{md.relative_to(ROOT)}:L{lineno}: archived 与 not live-ready 并存")
  assert not problems, "发现非法状态组合:\n" + "\n".join(problems)


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
  for script in sorted(RESEARCH.rglob("*.py")):
    if "_shared-kernels" in script.parts:
      continue
    digest = hashlib.sha256(script.read_bytes()).hexdigest()
    if digest in kernel_hashes:
      problems.append(
        f"{script.relative_to(ROOT)}: 复制了共享内核 "
        f"{kernel_hashes[digest].relative_to(ROOT)}，应 SHA pin 引用"
      )
  assert not problems, "共享内核索引/复制边界失败:\n" + "\n".join(problems)
