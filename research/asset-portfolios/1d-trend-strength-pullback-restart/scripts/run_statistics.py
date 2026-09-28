"""新家族固定统计入口；先核验完整身份，禁止传入替代统计参数。"""
from __future__ import annotations

import datetime as dt
import importlib.util
import sys
import time

from family_common import FAMILY, KERNEL, load_panel, save_json, sha, verify_lock


def main():
    identity = verify_lock()
    panel, panel_identity = load_panel()
    started_path = FAMILY / 'artifacts/p1-statistics-wrapper-started.json'
    if not started_path.exists():
        save_json(started_path, {'utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                                 **identity, **panel_identity})
    else:
        import json
        prior = json.loads(started_path.read_text())
        for key, value in {**identity, **panel_identity}.items():
            if prior[key] != value:
                raise ValueError('Restart wrapper identity differs')
    spec = importlib.util.spec_from_file_location('tspr_frozen_statistics_v1', KERNEL / 'statistics.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    started = time.time()
    out = FAMILY / 'artifacts/p1-statistics'
    report = module.run(panel, out)
    verify_lock()
    receipt = FAMILY / 'artifacts/p1-statistics-wrapper-completed.json'
    if not receipt.exists():
        save_json(receipt, {'utc': dt.datetime.now(dt.timezone.utc).isoformat(),
                           'seconds_this_invocation': time.time() - started,
                           'report_sha256': sha(out / 'report.json'),
                           'script_sha256': sha(__file__), **identity, **panel_identity,
                           'status': report.get('status', 'REPORT_WRITTEN')})
    print(report, flush=True)


if __name__ == '__main__':
    main()
