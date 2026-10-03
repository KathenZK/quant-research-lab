#!/usr/bin/env python3
"""Static source/dependency audit. No market data, indicators or returns executed.
SPDX-License-Identifier: GPL-3.0-or-later
"""
import argparse, ast, hashlib, importlib.metadata, inspect, json
from datetime import datetime,timezone
from pathlib import Path
import ta.trend, ta.utils

def h(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def loc(fn):
    lines,n=inspect.getsourcelines(fn)
    return {'module':Path(inspect.getsourcefile(fn)).name,'module_sha256':h(inspect.getsourcefile(fn)),'first_line':n,'last_line':n+len(lines)-1}
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--out',required=True);a=p.parse_args()
 assert h(a.source)=='48e405f6d073944da9b993dfbce03aa980d0eea8a5da3c4a6b60f2f1b7264b86'
 src=Path(a.source).read_text();tree=ast.parse(src);cls=next(n for n in tree.body if isinstance(n,ast.ClassDef))
 functions={n.name:{'first_line':n.lineno,'last_line':n.end_lineno} for n in cls.body if isinstance(n,ast.FunctionDef)}
 kst=inspect.getsource(ta.trend.KSTIndicator._run)
 assert 'fill_value=self._close.mean()' in kst
 assert 'fillna=True' in src and 'np.isclose(DFIND, REAL)' in src
 try:
  from numpy.lib import math
  numpy_math='AVAILABLE'
 except ImportError:numpy_math='IMPORT_ERROR'
 result={'schema':'godstra-source-static-audit/v1','id':'M0274','at_utc':datetime.now(timezone.utc).isoformat(),'source_sha256':h(a.source),'script_sha256':h(__file__),'source_method_locations':functions,'library_version':importlib.metadata.version('ta'),'findings':[{'code':'GLOBAL_MEAN_KST_INITIALIZATION','severity':'ORIGINAL_PIPELINE_CAUSALITY_BLOCKER','used_feature':'trend_kst_diff','location':loc(ta.trend.KSTIndicator._run),'mechanism':'Each initial shifted close is filled using mean of the entire supplied close vector. The historical KST and KST signal can therefore depend on values later than the row. This is not repaired.','evaluation_impact':'Not inferred from static inspection; distinguish warmup from evaluation in numerical prefix tests.'},{'code':'VISUAL_ICHIMOKU_GLOBAL_MEAN_INITIALIZATION','severity':'ORIGINAL_FULL_PIPELINE_CAUSALITY_BLOCKER','location':loc(ta.trend.IchimokuIndicator.ichimoku_a),'mechanism':'visual=True features are included by add_all_ta_features; shifted prefix uses span mean of full supplied vector. Entry itself selects the nonvisual base line.'},{'code':'DROPNA_INPUT_SHAPE','severity':'REPRODUCTION_CONSTRAINT','location':loc(ta.utils.dropna),'mechanism':'Native archive ignore field is zero. Passing all native columns would remove every row. Strategy input must be Freqtrade OHLCV shape. No zero native volume rows may silently disappear.'},{'code':'AGEFILTER30_UNPROVEN','severity':'STRICT_REPRODUCTION_BLOCKER','mechanism':'Source comment requests AgeFilter min_days_listed=30. Fixed BTCUSDT and 62 warmup bars do not reproduce dynamic daily candle counting; original configuration/pairlist history not supplied.'},{'code':'ENVIRONMENT_VERSION_UNPINNED','severity':'STRICT_REPRODUCTION_BLOCKER','mechanism':'Author did not pin ta/numpy/pandas/Freqtrade versions. This audit pins installed ta0.11.0 numpy2.3.5 pandas2.2.3. numpy.lib.math compatibility is probed independently below; no import-failure claim is inferred from a version number. Freqtrade is not installed, so no original engine run is claimed.','numpy_lib_math_probe':numpy_math}], 'performance_engine_executed':False,'decision':'BLOCK_ORIGINAL_IMPLEMENTATION_NO_RETURNS','strict_reproductions':0,'source_thresholds_modified':False}
 with Path(a.out).open('x') as f:json.dump(result,f,indent=2,sort_keys=True);f.write('\n')
 print(json.dumps({'decision':result['decision'],'numpy_lib_math_probe':numpy_math,'source_sha256':result['source_sha256']}))
