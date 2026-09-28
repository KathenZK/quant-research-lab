"""Offline raw reconstruction and independent trust assessment."""

import argparse
from strategy_lab.knowledge.market_core import materialize

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--contract", required=True)
    p.add_argument("--capture", required=True)
    p.add_argument("--output", required=True)
    a = p.parse_args()
    print(materialize(a.contract, a.capture, a.output))
