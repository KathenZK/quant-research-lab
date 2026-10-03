"""Reuse M0216's pinned official-archive recipe into a new private directory."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import urllib.request

FAMILY = Path(__file__).resolve().parents[1]
REPO = FAMILY.parents[2]
INPUT_SHA = "48e4e785ee3366a459cf09f64617c89e04fb19b91da6c6125e86835506f6b9f5"
SOURCE_SHA = "cce61e4af8ed3cb8e78a5d9713aba7891ec08d1bdb1da9911c3f550424db795d"
SOURCE_URL = ("https://raw.githubusercontent.com/freqtrade/freqtrade-strategies/"
              "f3340ce11f5bdf62f598522e64d1f5638eaa13f5/"
              "user_data/strategies/PatternRecognition.py")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(REPO / "src"))
    recipe = FAMILY.parent / "M0216/scripts/fetch_inputs.py"
    manifest = json.loads((FAMILY / "specs/rebuild-dependencies.json").read_text())
    if hashlib.sha256(recipe.read_bytes()).hexdigest() != manifest["m0216_fetch_inputs_sha256"]:
        raise ValueError("Pinned M0216 recipe changed")
    module_spec = importlib.util.spec_from_file_location("m0216_official_recipe", recipe)
    module = importlib.util.module_from_spec(module_spec)
    module_spec.loader.exec_module(module)
    module.RAW, module.OUT = args.out / "raw", args.out / "staging"
    module.fetch()
    actual = hashlib.sha256((module.OUT / "input.csv").read_bytes()).hexdigest()
    if actual != INPUT_SHA:
        raise ValueError("Official historical input revised; reject exact replay")
    with urllib.request.urlopen(SOURCE_URL, timeout=30) as response:
        source = response.read()
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA:
        raise ValueError("Original strategy source differs")
    (args.out / "PatternRecognition.py").write_bytes(source)
    (args.out / "verified-rebuild.json").write_text(json.dumps({
        "input_sha256": actual, "source_sha256": SOURCE_SHA,
        "input_bytes": (module.OUT / "input.csv").stat().st_size,
        "official_months_checked": len(json.loads((module.OUT / "input-manifest.json").read_text())["sources"]),
        "trusted_for_strategy_claims": False, "quality": "DIAGNOSTIC_ONLY",
    }, indent=2) + "\n")


if __name__ == "__main__":
    main()
