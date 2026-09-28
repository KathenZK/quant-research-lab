"""Targeted temporal and accounting checks for this replay's native kernels."""
from dataclasses import asdict
import hashlib
import numpy as np
import pandas as pd
import audit_common as common
import other_assets_replay as ar


def main():
    checks = []
    cutoff = pd.Timestamp("2026-08-01T00:00:00Z")
    for asset in ar.REGISTERED:
        engine = ar.load_module(ar.ENGINE_PATH, f"audit_verify_{asset}_engine")
        configs, _, special = ar.frozen_configs(asset, engine)
        raw = common.load_prices(asset, "1h")
        funding = common.load_funding(asset)
        raw = raw[raw.ts >= funding.ts.min().ceil("h")].reset_index(drop=True)
        full = engine.add_features(raw, funding)
        prefix = engine.add_features(raw[raw.ts < cutoff].copy(), funding[funding.ts <= cutoff].copy())
        for i, cfg in enumerate(configs):
            if special is not None and i == 1:
                a = special.armed_vwap_signal(engine, full, cfg, 3, "roc6_macd")[0]
                b = special.armed_vwap_signal(engine, prefix, cfg, 3, "roc6_macd")[0]
            else:
                a, b = engine.build_signal(full, cfg), engine.build_signal(prefix, cfg)
            assert np.array_equal(a[:len(b)], b), (asset, cfg.name)
            checks.append({"asset": asset, "leg": cfg.name, "check": "removing_future_prices_and_funding_does_not_change_past_signals", "cutoff": cutoff, "pass": True})
        artifact = ar.OUT / asset / "base_trades.csv"
        if artifact.stat().st_size > 1:
            trades = pd.read_csv(artifact)
            if not trades.empty:
                assert np.allclose(trades.equity_ret, trades.exposure * trades.net_ret_1x)
                assert (pd.to_datetime(trades.entry_ts) > pd.to_datetime(trades.signal_ts)).all()
                assert (pd.to_datetime(trades.exit_ts) >= pd.to_datetime(trades.entry_ts)).all()
                assert (pd.to_datetime(trades.exit_ts).iloc[:-1].to_numpy() < pd.to_datetime(trades.entry_ts).iloc[1:].to_numpy()).all()
        checks.append({"asset": asset, "check": "account_multiplication_signal_timing_and_nonoverlap", "pass": True})
    ar.write_json(ar.OUT / "verification.json", {"status": "PASS", "checks": checks, "engine_sha256": hashlib.sha256(ar.ENGINE_PATH.read_bytes()).hexdigest()})
    print(f"PASS {len(checks)} focused checks")


if __name__ == "__main__":
    main()
