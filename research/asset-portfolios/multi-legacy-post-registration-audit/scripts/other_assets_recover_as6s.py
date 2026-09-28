"""Read original Rust frozen config functions, execute only them, export values.

The runner is not built, started or modified. A tiny isolated Rust executable
includes the exact two read-only config files plus their plain data types.
"""
from __future__ import annotations
import hashlib
import json
import re
import subprocess
import tempfile
from pathlib import Path
import other_assets_replay as ar

RUNNER = Path("/Users/ZK/OpenCode/quant-runner")
SOURCE = RUNNER / "crates/quant-runner/src/runner/strategies/asset_specific_six_selector_v6_mark_joint_state"
TYPES = RUNNER / "crates/quant-runner/src/runner/strategies/six_asset_ensemble/config.rs"


def extract_type(text, kind, name):
    pattern = f"pub {kind} {name} {{"
    start = text.index(pattern)
    end = text.index("\n}", start) + 2
    return "#[derive(Debug, Clone, Copy)]\n" + text[start:end] if kind == "enum" else "#[derive(Debug, Clone)]\n" + text[start:end]


class DebugParser:
    def __init__(self, text):
        self.tokens = re.findall(r'"(?:\\.|[^"\\])*"|[A-Za-z_][A-Za-z_0-9]*|[-+]?(?:\d+\.\d*|\d+)(?:[eE][-+]?\d+)?|[{}\[\]():,]', text)
        self.i = 0

    def take(self, expected=None):
        token = self.tokens[self.i]
        self.i += 1
        if expected is not None:
            assert token == expected, (expected, token)
        return token

    def value(self):
        token = self.take()
        if token == "[":
            values = []
            while self.tokens[self.i] != "]":
                values.append(self.value())
                if self.tokens[self.i] == ",":
                    self.take(",")
            self.take("]")
            return values
        if token == "Some":
            self.take("(")
            value = self.value()
            self.take(")")
            return value
        if token == "None":
            return None
        if token in ("true", "false") or token.startswith('"') or token[0] in "-+0123456789":
            return json.loads(token)
        if self.i < len(self.tokens) and self.tokens[self.i] == "{":
            self.take("{")
            value = {"_rust_type": token}
            while self.tokens[self.i] != "}":
                key = self.take()
                self.take(":")
                value[key] = self.value()
                if self.tokens[self.i] == ",":
                    self.take(",")
            self.take("}")
            return value
        return token


def main():
    types = TYPES.read_text()
    structs = [extract_type(types, "enum", name) for name in ("Asset", "SideMode", "ExitKind", "Style")]
    structs += [extract_type(types, "struct", name) for name in ("LegConfig", "SixAssetEnsembleConfig")]
    code = "#![allow(dead_code)]\nmod strategies { pub mod six_asset_ensemble {\n" + "\n".join(structs) + "\n}}\n"
    code += f'#[path = {json.dumps(str(SOURCE / "engine_config.rs"))}] mod engine_config;\n'
    code += f'#[path = {json.dumps(str(SOURCE / "config.rs"))}] mod config;\n'
    code += '''fn main() {
        use config::RouteVariant::*;
        for route in [NonPreemptive, StrongBreakoutPreemptive] {
            println!("{}", route.as_str());
            println!("{:?}", config::frozen_sleeves_for(route));
            println!("{:?}", config::frozen_legacy_config_for(route));
        }
    }'''
    output = ar.OUT
    output.mkdir(parents=True, exist_ok=True)
    (output / "as6s_recovery_wrapper.rs").write_text(code)
    with tempfile.TemporaryDirectory(prefix="as6s-config-export-") as temp:
        binary = Path(temp) / "export"
        subprocess.run(["rustc", "--edition=2021", str(output / "as6s_recovery_wrapper.rs"), "-o", str(binary)], check=True, capture_output=True, text=True)
        result = subprocess.run([str(binary)], check=True, capture_output=True, text=True).stdout
    (output / "as6s_recovery_rust_debug.txt").write_text(result)
    lines = result.splitlines()
    routes = {}
    for i in (0, 3):
        sleeves = DebugParser(lines[i + 1]).value()
        legacy = DebugParser(lines[i + 2]).value()
        assert len(sleeves) == 15 and len(legacy["legs"]) == 6
        assert len(set(s["id"] for s in sleeves)) == 15
        routes[lines[i]] = {"account_scale": .75, "sleeves": sleeves, "legacy": legacy}
    paths = [TYPES, SOURCE / "engine_config.rs", SOURCE / "config.rs", SOURCE / "BIN-15M-AS6S-V6-NP-SPEC.md", SOURCE / "BIN-15M-AS6S-V6-SBP-SPEC.md"]
    payload = {
        "status": "RECOVERED_FROM_ORIGINAL_RUNNER_CONFIG_FUNCTIONS",
        "original_lab_freeze_json_missing": True,
        "recovery_method": "Evaluate frozen_sleeves_for and frozen_legacy_config_for by isolated rustc wrapper using original source files, no strategy runtime",
        "routes": routes,
        "source_pins": {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        "historical_parity_evidence": {
            "source": str(SOURCE / "BIN-15M-AS6S-V6-NP-SPEC.md"),
            "recorded_date": "2026-07-15", "signal_checks": 45, "leg_exit_checks": 15,
            "candidate_checks": 1486, "np_route_matches": "634/634",
            "fixture_sha256": "25fc54595a3e941bc5c95d50601f2fe5284f581f1797b0d78afde6b9ea7f2f22",
            "current_replay_of_historical_parity": False,
        },
        "spec_consistency": "six symbols; fifteen sleeves; account scale .75; 4bps slip; .001 fee; both route variants; BNB threshold_high=60 retained; Clean RSI name/actual parameter difference retained",
        "interpretation": "Recoverable runner copy with contemporaneous recorded parity evidence. Missing original Lab JSON hash cannot be rechecked from this output alone.",
    }
    ar.write_json(output / "as6s_recovery.json", payload)
    print(json.dumps({"path": str(output / "as6s_recovery.json"), "routes": {k: len(v["sleeves"]) for k,v in routes.items()}}))


if __name__ == "__main__":
    main()
