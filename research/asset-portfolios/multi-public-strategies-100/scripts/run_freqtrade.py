"""Run pinned source strategies using the native offline backtester, no live APIs."""
from pathlib import Path
import subprocess,json,hashlib,datetime
ROOT=Path(__file__).resolve().parents[4];F=Path(__file__).resolve().parents[1]
def main():
    C=json.loads((F/'specs/run-contract-v1.json').read_text());OUT=F/'artifacts/freqtrade';OUT.mkdir(exist_ok=True)
    USER=ROOT/'data/cache/public100/freqtrade-user';USER.mkdir(parents=True,exist_ok=True)
    BIN='/tmp/public100-freqtrade-env/bin/freqtrade'
    subprocess.run(['/Users/ZK/.local/bin/uv','pip','freeze','--python','/tmp/public100-freqtrade-env/bin/python'],stdout=(F/'specs/freqtrade-requirements.lock.txt').open('w'),check=True)
    results=[]
    for sid,strategy in zip(['D7','D8','D9','D10'],C['crypto_source_strategies']):
     for fee in C['crypto_execution_cost_sensitivity']:
      key=f'{sid}-{fee}';dest=OUT/key;dest.mkdir(exist_ok=True)
      cmd=[BIN,'backtesting','--userdir',str(USER),'-c',str(F/'specs/freqtrade-backtest-config.json'),'-d',str(ROOT/'data/cache/public100/freqtrade'),'--strategy-path',str(F/'artifacts/sources/surendrad24__ZwaAP-FreqTrade-Strategies/strategies'),'-s',strategy,'--timerange','20240701-20260901','--fee',str(fee),'--cache','none','--export','trades','--backtest-directory',str(dest),'--breakdown','year']
      if sid!='D8':cmd+=['--timeframe-detail','15m']
      t=datetime.datetime.now(datetime.timezone.utc).isoformat()
      with (dest/'run.log').open('w') as log:p=subprocess.run(cmd,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT)
      rec={'id':sid,'strategy':strategy,'fee':fee,'returncode':p.returncode,'command':cmd,'started_at':t,'files':[str(x.relative_to(F)) for x in dest.glob('*.zip')]};results.append(rec)
      (OUT/'run-manifest.json').write_text(json.dumps({'status':'EXPLORE_UNTRUSTED','runs':results},indent=2))
      print(key,p.returncode,flush=True)
      if p.returncode:print((dest/'run.log').read_text()[-3000:],flush=True);raise SystemExit(p.returncode)

if __name__ == "__main__":
    main()
