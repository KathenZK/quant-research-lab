"""Render the retained Lab replay as a self-contained interactive HTML."""
from pathlib import Path
import datetime as dt,json,hashlib,math
ROOT=Path(__file__).resolve().parents[1];S=ROOT/'scripts';O=ROOT/'artifacts/20260907'
datasets=json.loads((O/'chart-data.json').read_text());checks=[]
for coin,windows in datasets.items():
 for window,d in windows.items():
  bars=d['bars'];d['bh']=[b['close']/bars[0]['close'] for b in bars]
  for b in bars:b['date']=dt.datetime.fromtimestamp(b['ts']/1000,dt.timezone.utc).strftime('%Y-%m-%d')
  for mode,r in d['runs'].items():
   stops=[None]*len(bars);ids=set()
   assert len(r['trades'])==r['metrics']['n_trades']
   for j,t in enumerate(r['trades']):
    uid=f'{coin}/{window}/{mode}/{j+1}';assert uid not in ids;ids.add(uid);t['id']=uid
    assert bars[t['entry_idx']]['ts']<=bars[t['exit_idx']]['ts']
    t['path_endpoints']=[[t['entry_date'],t['entry_price']],[t['exit_date'],t['exit_price']]]
    assert all(bars[i]['date']==day for i,day in [(t['entry_idx'],t['entry_date']),(t['exit_idx'],t['exit_date'])])
    initial=next(e['stop'] for e in r['events'] if e['action']=='entry' and e['i']==t['entry_idx']);stop=initial
    for i in range(t['entry_idx'],t['exit_idx']+1):
     if i>t['entry_idx']:
      k=i if mode=='literal' else i-1
      stop=max(stop,d['ma'][k]-1.5*d['atr'][k])
     stops[i]=stop
    if t['reason']!='end_of_test':
     assert abs(stop-t['stop_after'])<1e-10
     raw=bars[t['exit_idx']]['open'] if t['reason']=='gap_stop' else stop
     expected=raw*(1-r['metrics']['slippage_bps_per_fill']/10000)
     assert math.isclose(expected,t['exit_price'],abs_tol=1e-10)
    prices=[t['entry_price']]+[b['close'] for b in bars[t['entry_idx']:t['exit_idx']]]
    if t['reason']=='end_of_test':prices.append(t['exit_price'])
    t['max_close_return_pct']=(max(prices)/t['entry_price']-1)*100
    t['giveback_from_peak_pct']=(1-t['exit_price']/max(*prices,t['exit_price']))*100
    t['initial_stop']=initial;t['final_stop']=stop
   r['display_stops']=stops
   checks.append({'coin':coin,'window':window,'mode':mode,'trade_count':len(ids),'endpoints_checked':2*len(ids),'status':'PASS'})
html=(S/'trade-path-template.html').read_text().replace('/*__ECHARTS__*/',(S/'echarts.min.js').read_text().replace('</script','<\\/script')).replace('/*__DATA__*/',json.dumps(datasets,ensure_ascii=False,separators=(',',':'),allow_nan=False)).replace('/*__APP__*/',(S/'trade-path-app.js').read_text())
assert '/*__' not in html
out=O/'七币交易路径.html';out.write_text(html)
(O/'visual-validation.json').write_text(json.dumps({'status':'PASS','checks':checks,'html_sha256':hashlib.sha256(out.read_bytes()).hexdigest()},ensure_ascii=False,indent=2)+'\n')
print(out, len(html.encode()),'bytes;',len(checks),'views checked')
