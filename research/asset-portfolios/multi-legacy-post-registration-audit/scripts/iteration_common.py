"""Bind existing verified readers to the new startup-returned comparison inputs."""
from pathlib import Path
import audit_common

FAMILY = Path(__file__).resolve().parents[1]
OUT = FAMILY / "artifacts/iteration_comparison_20260911"
INPUTS = OUT / "inputs"
audit_common.INPUTS = INPUTS
load_checked = audit_common.load_checked
load_prices = audit_common.load_prices
load_funding = audit_common.load_funding
END = audit_common.END
