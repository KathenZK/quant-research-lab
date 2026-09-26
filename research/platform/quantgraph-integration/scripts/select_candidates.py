"""Read a running QuantGraph API using its SDK; publish only aggregate counts."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT / 'src'))


def main():
    from strategy_lab.knowledge.candidates import collect_candidates, select_candidates, public_summary
    from quantgraph.client import QuantGraphClient
    p = argparse.ArgumentParser()
    p.add_argument('--url', required=True)
    p.add_argument('--private-output', type=Path)
    p.add_argument('--summary-output', type=Path, required=True)
    args = p.parse_args()
    report = select_candidates(collect_candidates(QuantGraphClient(args.url)))
    if args.private_output:
        args.private_output.parent.mkdir(parents=True, exist_ok=True)
        args.private_output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    summary = public_summary(report)
    args.summary_output.write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
