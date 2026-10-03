"""Freeze source-default M0315 hypothesis before historical performance, exclusive create."""

from datetime import datetime, timezone
import hashlib
import importlib.metadata as metadata
import json
from pathlib import Path
import platform
import talib

ROOT = Path(__file__).resolve().parents[1]


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def write(p, obj):
    with Path(p).open("x") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False)
        f.write("\n")


def freeze():
    now = datetime.now(timezone.utc).isoformat()
    spec = {
        "record_id": "M0315",
        "name": "UniversalMACD literal defaults",
        "family": "PUBLIC-M0315-UNIVERSAL-MACD",
        "run_id": "M0315-20261003-first-replay",
        "variant_id": "M0315-BTCUSDT-5M-DEFAULTS-2024-20261003",
        "frozen_at_utc": now,
        "fidelity_class": "HYPOTHESIS",
        "evidence_class": "historical_replay",
        "status": "explore / not promoted / not live-ready",
    }
    spec["source"] = {
        "repository": "freqtrade/freqtrade-strategies",
        "commit": "f3340ce11f5bdf62f598522e64d1f5638eaa13f5",
        "path": "user_data/strategies/UniversalMACD.py",
        "author": "Masoud Azizi (@mablue)",
        "selection": "BTCUSDT spot researcher instance; original commented multi-coin pool and old hyperopt context not reproduced",
    }
    spec["framework_reference"] = {
        "name": "Freqtrade",
        "version": "2026.9",
        "execution_engine_used": False,
        "purpose": "Unmodified source import and ft_load_hyper_params native DecimalParameter defaults; independent declared OHLC execution port",
    }
    spec["dependencies"] = {
        k: metadata.version(k)
        for k in ["numpy", "pandas", "TA-Lib", "freqtrade", "technical", "ft-pandas-ta"]
    }
    spec["dependencies"].update(
        python=platform.python_version(),
        ta_library=talib.__ta_version__.decode().split()[0],
        talib_compatibility=0,
        ema_unstable_period=0,
    )
    spec["parameters"] = {
        "ema_short": 12,
        "ema_long": 26,
        "buy_umacd_min": -0.01416,
        "buy_umacd_max": -0.01176,
        "sell_umacd_min": -0.00707,
        "sell_umacd_max": -0.02323,
        "decimals": 5,
        "startup_candle_count": 30,
        "external_parameter_file": False,
        "hyperopt": False,
    }
    spec["signals"] = {
        "entry": "EMA(close,12)/EMA(close,26)-1 between[-.01416,-.01176], inclusive both",
        "exit": "literal between[-.00707,-.02323] is empty; always false; do not reorder thresholds",
        "nan": "EMA SMA initialization, 25 initial NaNs; no filling;31day warmup covers startup30",
        "volume_guard": False,
        "availability": "closed native5m bars; no warmup orders; no cross required",
        "warmup_bars": 8928,
        "lookahead_bars": 0,
    }
    spec["risk"] = {
        "minimal_roi": {"0": 0.213, "27": 0.099, "60": 0.03, "164": 0},
        "stoploss": -0.318,
        "trailing": False,
        "inactive_trailing_fields": {
            "positive": None,
            "offset": 0.0,
            "only_offset_is_reached": False,
        },
        "roi_formula": "entry_fill*(1+fee)*(1+roi_age)/(1-fee), then adverse2bps sell slippage",
        "stop_formula": "entry_fill*.682, then sell fee and adverse2bps slippage",
        "minute_transition_approximation": "ROI sampled only at native5m open:27min takes effect30min,60at60,164at165. No intrabar minute interpolation. Not exact full Freqtrade execution.",
    }
    spec["execution"] = {
        "initial_cash": 100000,
        "cash_currency": "USDT",
        "cash_budget_fraction": 0.95,
        "budget_includes_buy_fee": True,
        "slippage_bps": 2,
        "open_execution_overrides": {},
        "intrabar_execution_latest_overrides": {},
        "direction": "long_only",
        "leverage": 1,
        "max_positions": 1,
        "pyramiding": False,
        "cash_interest": 0,
        "funding": "not applicable spot without borrowing",
        "fractional_fills": True,
        "sequence": [
            "scheduled signal exit at open unless entry collision",
            "flat due entry at raw open, never reenter after same-bar exit",
            "opening stop gap, then ROI gap, then intrabar low stop, then intrabar high ROI",
            "mark remaining position at raw close",
        ],
        "ambiguity": "open-between-thresholds and both touched -> stop first; exact intrabar time unavailable, record5m bounds",
        "pending": "only evaluation signals; delay1or2 bars; stale entry while long ignored; no orders after end",
        "terminal": "no forced sale for strategy or buyhold; raw final close mark; unrealized exit costs excluded",
        "limitations": "assumed full fills; no historical orderbook/lot/minnotional/partial fills/PIT tradability; 5mopen proxy",
    }
    spec["input"] = {
        "filename": "BTCUSDT-5m-202312-202412-native12.csv",
        "sha256": "91e5bb0ba80ba2b70c5d6a5924c590459b0ffbe3e5955ba177abc981fb2a0af2",
        "bytes": 31428289,
        "start": "2023-12-01T00:00:00Z",
        "end_exclusive": "2025-01-01T00:00:00Z",
        "expected_rows": 114336,
        "exchange": "binance",
        "market_type": "spot",
        "symbol": "BTCUSDT",
        "timeframe": "5m",
        "source": "official Binance Vision13 native monthly archives",
        "raw_manifest_sha256": "fb84e080d97ed85ec92227bc43b9468de331b3399e6b8254dba4afa7ccc8d058",
        "quality_status": "DIAGNOSTIC_ONLY",
        "trusted": False,
        "strict_core_finality": "NOT_ESTABLISHED",
        "pit_status": "NOT_PROVEN",
        "gap_policy": "reject;114336 exact grids/close times, no discarded rows",
        "new_market_requests": 0,
        "loader_exception": "Explicit user-authorized spot native5m diagnostic; existing canonical perpetual v3 loader is different market/timeframe. Hash/grid/OHLCV and39raw-file CRC/byte-rebuild QA equivalent checks; never label trusted or net_research.",
    }
    spec["evaluation"] = {
        "start": "2024-01-01T00:00:00Z",
        "end_exclusive": "2025-01-01T00:00:00Z",
        "expected_rows": 105408,
        "initial_state": "cash only; first allowed strategy entry at second evaluation open",
    }
    spec["metrics"] = {
        "sharpe": "UTC366 daily returns, initialcash included, ddof1 sqrt365 riskfree0",
        "sharpe_5m": "105408 native bar-close returns sqrt365*288 ddof1",
        "max_drawdown": "all105408 bar-close equity states plus initial cash; not intrabar drawdown",
        "annualized_return": "(final/initial)^(365/366)-1",
        "exposure": "fraction of bar-close states invested",
    }
    spec["cases"] = [
        {"name": n, "fee_bps": fee, "delay_bars": delay}
        for n, fee, delay in [
            ("base", 8, 1),
            ("fee0", 0, 1),
            ("fee20", 20, 1),
            ("delay2", 8, 2),
        ]
    ] + [{"name": "buyhold", "fee_bps": 8, "delay_bars": 1, "buy_hold": True}]
    spec["buyhold"] = (
        "same95%fee-inclusive cash at first evalopen; same fee8/slip2bps; no stop/ROI; same finalmark"
    )
    spec["exposure"] = {
        "window_previously_exposed": True,
        "historical_total_search_count": "UNKNOWN",
        "oos_claim": False,
        "DSR_or_PBO_claim": False,
        "strategy_ids": 1,
        "strategy_configurations": 4,
        "controls": 1,
        "parameter_searches": 0,
        "selection": "Availability-driven2024 window after2023 native5m input rejection, frozen before performance; not OOS nor direct comparison with earlier2023-2024 totals",
        "claim_commit": "42e43ed1145129a7e8590fbec37d9b66073b3837",
        "base_commit": "d5a0c5ee6ac7ddc56159b3d5969c5267ca83bf96",
    }
    spec["source_hashes"] = {
        "UniversalMACD.py": "b3a62e0d8a26024e7ab5f3613d0964e3954373bc3735c1ffd0678d84ce1b1e32"
    }
    spec["code_hashes"] = {
        str(p.relative_to(ROOT)): sha(p)
        for p in sorted((ROOT / "scripts").glob("*.py"))
    }
    spec["supporting_evidence_hashes"] = {
        str(p.relative_to(ROOT)): sha(p)
        for p in sorted((ROOT / "specs").iterdir())
        if p.is_file()
    }
    target = ROOT / "specs/M0315-first-replay.json"
    write(target, spec)
    exposure = {
        "id": "M0315-20261003-first-replay-exposure",
        "kind": "exposure",
        "family": spec["family"],
        "window_start": spec["evaluation"]["start"],
        "window_end": spec["evaluation"]["end_exclusive"],
        "evidence_class": "historical_replay",
        "trial_count": 4,
        "controls": 1,
        "selection_reason": spec["exposure"]["selection"],
        "artifacts": {"specs/M0315-first-replay.json": sha(target)},
        "recorded_at_utc": now,
        "historical_total_search_count": "UNKNOWN",
        "oos_claim": False,
    }
    write(ROOT / "specs/exposure.json", exposure)
    receipt = {
        "id": "M0315",
        "state": "FROZEN_NOT_EXECUTED",
        "frozen_at_utc": now,
        "protocol_sha256": sha(target),
        "input_sha256": spec["input"]["sha256"],
        "strategy_ids": 1,
        "strategy_configurations": 4,
        "controls": 1,
        "strict_replication": False,
        "new_market_requests": 0,
        "remote_backup_verified": False,
    }
    write(ROOT / "artifacts/20261003-first-replay/freeze-receipt.json", receipt)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    freeze()
