"""Local append/verify/query CLI; does not start a collector or trading service."""
import argparse
import json
from pathlib import Path

from strategy_lab.research.exposure import append_record, read_ledger, overlaps, observation_coverage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("operation", choices=["append", "verify", "overlaps", "coverage"])
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--record", type=Path)
    parser.add_argument("--start")
    parser.add_argument("--end")
    parser.add_argument("--family")
    parser.add_argument("--as-of")
    parser.add_argument("--cadence-hours", type=int)
    args = parser.parse_args()
    if args.operation == "append":
        if args.record is None:
            parser.error("append requires --record")
        result = append_record(args.ledger, json.loads(args.record.read_text()))
    else:
        records = read_ledger(args.ledger)
        if args.operation == "coverage":
            if not all([args.start, args.end, args.family, args.as_of, args.cadence_hours]):
                parser.error("coverage requires start/end/family/as-of/cadence-hours from a fixed contract")
            result = observation_coverage(records, family=args.family, start=args.start, end=args.end,
                                          as_of=args.as_of, cadence_hours=args.cadence_hours)
        elif args.operation == "overlaps":
            if not args.start or not args.end:
                parser.error("overlaps requires --start and --end")
            result = overlaps(records, start=args.start, end=args.end)
        else:
            result = {"status": "CHAIN_VALID", "records": len(records),
                      "last_sha256": records[-1]["sha256"] if records else None}
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
