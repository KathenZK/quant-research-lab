from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
FAMILY_DIR = ROOT / "research/btc/30m-trend-continuation"
SOURCE_PATH = (
    ROOT
    / "research/btc/15m-ema-trend-breakout/scripts"
    / "refresh_and_audit_btc_15m_data.py"
)
SOURCE_SHA256 = "507ec927d1cd947ebf30efd0c200cea92ceb1b00b035449a29c47d644190e3eb"
START = pd.Timestamp("2020-01-01T00:00:00Z")
INTERVAL = pd.Timedelta(minutes=30)
TIMEFRAME = "30m"
REPORT_PATH = FAMILY_DIR / "artifacts/btc_binance_30m_long_data_quality_latest.json"


def load_source() -> object:
    actual = hashlib.sha256(SOURCE_PATH.read_bytes()).hexdigest()
    if actual != SOURCE_SHA256:
        raise RuntimeError(
            "BTC data refresh source SHA mismatch: "
            f"expected {SOURCE_SHA256}, got {actual}"
        )
    module_name = "btc_30m_long_data_refresh_source"
    spec = importlib.util.spec_from_file_location(module_name, SOURCE_PATH)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load refresh source: {SOURCE_PATH}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def configure(source: object) -> None:
    source.START = START
    source.INTERVAL = INTERVAL
    source.INTERVAL_MS = int(INTERVAL.total_seconds() * 1000)
    source.TIMEFRAME = TIMEFRAME
    source.FAMILY_DIR = FAMILY_DIR
    source.ARTIFACT_DIR = FAMILY_DIR / "artifacts"
    source.REPORT_PATH = REPORT_PATH
    source.USER_AGENT = "quant-research-lab-btc-30m-trend-continuation-data/0.1"
    source.RAW_OHLCV_ROOT = (
        ROOT
        / "data/raw/ohlcv/exchange=binance/market_type=perp/timeframe=30m"
    )
    source.NORMALIZED_OHLCV_ROOT = (
        ROOT
        / "data/normalized/ohlcv/exchange=binance/market_type=perp/timeframe=30m"
    )


def main() -> None:
    source = load_source()
    configure(source)
    args = source.parse_args()
    report = source.report_base(args=args)
    try:
        server_time = source.binance_server_time(args.timeout)
        cutoff = server_time.floor(INTERVAL)
        if cutoff <= START:
            raise RuntimeError("Binance closed-bar cutoff is not after research start")
        report["binance_server_time"] = server_time.isoformat()
        report["closed_bar_cutoff_exclusive"] = cutoff.isoformat()

        raw_ohlcv = source.fetch_klines(
            start=START,
            end=cutoff,
            timeout=args.timeout,
        )
        normalized_ohlcv = source.normalize_klines(raw_ohlcv)
        funding_source, funding_metadata = source.build_funding(
            start=START,
            end=cutoff,
            timeout=args.timeout,
            no_write=args.no_write,
        )
        raw_funding, normalized_funding = source.enrich_funding(funding_source)
        ohlcv_quality = source.audit_ohlcv(
            raw_ohlcv,
            normalized_ohlcv,
            start=START,
            end=cutoff,
        )
        funding_quality = source.audit_funding(
            funding_source,
            raw_funding,
            normalized_funding,
            start=START,
            end=cutoff,
        )
        total_blockers = int(
            ohlcv_quality["blocker_count"] + funding_quality["blocker_count"]
        )
        report["funding_retrieval"] = funding_metadata
        report["ohlcv_quality"] = ohlcv_quality
        report["funding_quality"] = funding_quality
        report["total_blocker_count"] = total_blockers

        if args.no_write:
            report["writes"] = {"performed": False, "reason": "--no-write"}
        elif total_blockers:
            report["writes"] = {
                "performed": False,
                "reason": "data-quality blockers prevent standard data-lake refresh",
            }
        else:
            report["writes"] = {
                "performed": True,
                "reason": "all data-quality gates passed",
                **source.write_data_lake(
                    raw_ohlcv,
                    normalized_ohlcv,
                    raw_funding,
                    normalized_funding,
                ),
            }
    except Exception as exc:
        report["fatal_errors"].append(
            {"type": type(exc).__name__, "message": str(exc)}
        )
        report["total_blocker_count"] = max(
            1,
            int(report.get("total_blocker_count", 0)),
        )
        report["writes"] = {
            "performed": False,
            "reason": "fatal refresh or audit error",
        }

    source.persist_or_print_report(report, no_write=args.no_write)
    if report["total_blocker_count"]:
        raise RuntimeError(
            f"BTCUSDT 30m data-quality blockers remain: "
            f"{report['total_blocker_count']}"
        )


if __name__ == "__main__":
    main()
