"""Frozen definitions shared by this MA30 experiment's runner and presentation."""
import importlib.util
import json
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from common import ROOT,BASE,sha,write_json

R=BASE/'artifacts/ma30_states_20260911'
OLD=BASE/'artifacts/adaptation_20260911'
PIN=BASE/'specs/ma30-states-engine-pin-20260911.json'
ARMS={
 'C_DEFENSE':('统一旧防守','none','defense','none'),
 'C_EXTENSION':('统一旧延伸','none','extension','none'),
 'M_SKIP':('MA30只过滤','none','v3','conflict'),
 'M_DEFEND':('MA30只防守','defense','v3','none'),
 'M_EXTEND':('MA30只延伸','extend','v3','none'),
 'M_MANAGE':('MA30防守与延伸','both','v3','none'),
 'M_FULL':('MA30过滤加管理','both','v3','conflict'),
 'M_REPAIR':('允许早期修复','both','v3','repair'),
 'M_BTC':('另加BTC背景','both','v3','btc'),
}
NAMES={'U_READY':'原V3同观察期',**{k:v[0] for k,v in ARMS.items()}}
CORE=['timestamp','open','high','low','close','ma','ma30','prev_ma30','atr','rsi','slope',
      'cross','ready','accel1','accel2','ready90','long_btc_return60','short_btc_return60']

def engine():
    pin=json.loads(PIN.read_text());path=ROOT/pin['engine_path'];assert sha(path)==pin['engine_sha256']
    name='ma7_ma30_frozen_v5'
    if name not in sys.modules:
        spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec)
        sys.modules[name]=m;spec.loader.exec_module(m)
    return sys.modules[name]

def config(arm):
    return engine().Config(reverse=False,progress_days=4,fee=.001,slip=.0004,
                           admission_routing=True,ma30_mode=ARMS[arm][1])

def schedule(d,arm):
    d=d[CORE].copy();d['timestamp']=pd.to_datetime(d.timestamp,utc=True).dt.as_unit('ns')
    _,mode,route,gate=ARMS[arm];q=(d.ma30-d.prev_ma30)/d.atr
    for side,label in [(1,'long'),(-1,'short')]:
        sq=side*q;x=side*(d.close-d.ma30)/d.atr
        conflict=sq<=-.05;repair=conflict&(sq>sq.shift())&(x>0)
        accept=pd.Series(True,index=d.index)
        if gate in {'conflict','btc'}:accept=~conflict
        elif gate=='repair':accept=~conflict|repair
        if gate=='btc':accept&=d[label+'_btc_return60'].ge(0)&d[label+'_btc_return60'].notna()
        ready=d.ready90 & sq.notna() & x.notna()
        d['admit_'+label]=(ready&accept).astype(bool)
        d['route_'+label]=route
        d['rule_id_'+label]=np.where(~ready,'history90_or_ma30_unavailable',np.where(accept,arm+'_allow',arm+'_reject'))
        d[label+'_q']=sq;d[label+'_x']=x;d[label+'_repair']=repair
    return d

def read_trades(path):
    try:d=pd.read_csv(path)
    except pd.errors.EmptyDataError:return pd.DataFrame()
    for col in ['entry_time','exit_time','exit_interval_end','signal_day','cross_day','tp_signal_day']:
        if col in d:d[col]=pd.to_datetime(d[col],utc=True,format='mixed').dt.as_unit('ns')
    return d

def verify_manifest(path):
    for rel,digest in json.loads(path.read_text()).items():assert sha(path.parent/rel)==digest,rel

