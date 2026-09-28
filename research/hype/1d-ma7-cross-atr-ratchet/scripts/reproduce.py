"""Safe reproduction entrypoint: requires a fresh explicit output directory."""
import argparse
from pathlib import Path

import run_study


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    destination = args.output.expanduser().resolve()
    if destination.exists():
        parser.error("Output already exists; choose a new directory to preserve evidence")
    destination.parent.mkdir(parents=True, exist_ok=True)
    run_study.OUT = destination
    run_study.main()


if __name__ == "__main__":
    main()
