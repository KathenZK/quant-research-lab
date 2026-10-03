# SPDX-License-Identifier: GPL-3.0-or-later
"""Fixed-consumer pin verification. No source discovery or network fallback."""

from pathlib import Path
import hashlib
import json
import importlib.metadata as metadata


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def verify(idroot):
    idroot = Path(idroot)
    spec_path = idroot / "specs/protocol.json"
    spec = json.loads(spec_path.read_text())
    for rel, digest in spec["code_hashes"].items():
        assert sha(idroot / rel) == digest, rel
    kernel = Path(__file__).parent
    for name, digest in spec["kernel"]["files"].items():
        assert sha(kernel / name) == digest, name
    for rel, digest in spec["supporting_hashes"].items():
        assert sha(idroot / rel) == digest, rel
    for name, version in spec["dependencies"]["packages"].items():
        assert metadata.version(name) == version, name
    assert (
        spec["fidelity_class"] == "ADAPTED"
        and spec["execution_class"] == "ADAPTED_EXECUTION_PROXY"
    )
    return spec
