"""Compare saved pre-fix source and new source, and inventory static call sites."""
from pathlib import Path
import importlib.util
import json
import re
import subprocess
import sys

import pandas as pd

from strategy_lab.data.factors.cross_sectional import RelativeStrengthFactor
from strategy_lab.research.evidence import sha256

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "research/platform/cross-sectional-alpha-pipeline/artifacts/implementation-20260925"


def main():
    path = OUT / "source-before/cross_sectional.py"
    module_spec = importlib.util.spec_from_file_location("relative_strength_before_fix", path)
    old = importlib.util.module_from_spec(module_spec)
    sys.modules[module_spec.name] = old
    # Load the archived class without registering its old provider globally.
    exec(compile(path.read_text().split("@register_factor_provider")[0], str(path), "exec"), old.__dict__)
    frame = pd.DataFrame({"symbol": ["A", "A", "B", "B"], "close": [100., 110., 1000., 1000.],
                          "benchmark_close": [100.] * 4,
                          "ts": pd.to_datetime(["2026-01-01", "2026-01-02"] * 2, utc=True)})
    before, after = old.RelativeStrengthFactor(1), RelativeStrengthFactor(1)
    a, b = before.compute(frame), after.compute(frame)
    assert a.iloc[2] > 8 and pd.isna(b.iloc[2]) and b.iloc[3] == 0
    assert before.version() != after.version()
    names = subprocess.check_output(["rg", "--files", "-g", "*.py", "-g", "!**/artifacts/**",
                                     "-g", "!**/archive/**", "src", "scripts", "research", "tests"], cwd=ROOT, text=True).splitlines()
    direct, indirect = [], []
    for relative in names:
        text = (ROOT / relative).read_text()
        for i, line in enumerate(text.splitlines(), 1):
            record = {"path": relative, "line": i, "source": line.strip()}
            if re.search(r"RelativeStrengthFactor|relative_strength_24", line):
                direct.append(record)
            if re.search(r"compute_factor_bundle|default_registry|FeatureBuilder", line):
                indirect.append(record)
    result = {"old_source_sha256": sha256(path),
              "new_source_sha256": sha256(ROOT / "src/strategy_lab/data/factors/cross_sectional.py"),
              "period1_old_version": before.version(), "period1_new_version": after.version(),
              "period24_old_version": old.RelativeStrengthFactor().version(),
              "period24_new_version": RelativeStrengthFactor().version(),
              "old_B_first_return": float(a.iloc[2]), "new_B_first_return": None,
              "new_B_second_return": float(b.iloc[3]), "direct_static_references": direct,
              "generic_pipeline_static_references": indirect,
              "scope": "current Python sources outside artifacts/archive; dynamic imports and historical runs not proven absent",
              "impact": "reproducible cross-symbol defect in shared implementation; default FeatureBuilder loads one symbol. Static audit does not establish corruption of every past strategy result.",
              "historical_results_rewritten": False, "old_caches_deleted": False,
              "future_cache_identity_changed": True}
    (OUT / "factor-boundary-audit.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({k: v for k, v in result.items() if "references" not in k}, indent=2))


if __name__ == "__main__":
    main()
