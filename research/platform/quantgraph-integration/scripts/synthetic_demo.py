"""Reproduce an explicitly synthetic pipeline diagnostic; no market evidence."""
import hashlib
import importlib.util
import json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[4]
KERNEL = ROOT / 'research/_shared-kernels/quantgraph-diagnostics/v1/metrics.py'
EXPECTED_SHA256 = '32b96a286e5a70a458e7cf2c0194ad802107c37415e4264bc0e46a8c3f2fb593'


def run():
    if hashlib.sha256(KERNEL.read_bytes()).hexdigest() != EXPECTED_SHA256:
        raise ValueError('Frozen diagnostic kernel changed')
    spec = importlib.util.spec_from_file_location('quantgraph_diagnostics_v1', KERNEL)
    metrics = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(metrics)
    returns = np.random.default_rng(20260926).normal(0, .01, (256, 8))
    return {'scope': 'SYNTHETIC_PIPELINE_TEST_NOT_MARKET_EVIDENCE', 'seed': 20260926, 'trial_count': 8,
            'in_sample': metrics.performance(returns[:128, 0]), 'oos': metrics.performance(returns[128:, 0]),
            'walk_forward': [metrics.performance(returns[i:i + 64, 0]) for i in (128, 192)],
            'pbo': metrics.pbo(returns),
            'deflated_sharpe': metrics.deflated_sharpe(returns[:, 0], trial_sharpes=metrics.sharpe(returns), effective_trials=8),
            'parameter_plateau': metrics.plateau(metrics.sharpe(returns).tolist()), 'real_research_runs': 0}


if __name__ == '__main__':
    output = Path(__file__).resolve().parents[1] / 'artifacts/synthetic-diagnostics.json'
    output.write_text(json.dumps(run(), indent=2, allow_nan=False) + '\n')
    print('SYNTHETIC_PIPELINE_TEST_NOT_MARKET_EVIDENCE: reproduced')
