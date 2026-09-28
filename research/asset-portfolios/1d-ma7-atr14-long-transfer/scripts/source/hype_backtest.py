import urllib.request, json, datetime, time

def hl_fetch(start_ms, end_ms, retries=4):
    body=json.dumps({"type":"candleSnapshot","req":{"coin":"HYPE","interval":"1d","startTime":start_ms,"endTime":end_ms}})
    for a in range(retries):
        try:
            req=urllib.request.Request("https://api.hyperliquid.xyz/info",data=body.encode(),headers={'Content-Type':'application/json','User-Agent':'Mozilla/5.0'})
            with urllib.request.urlopen(req,timeout=40) as r: return json.loads(r.read())
        except Exception:
            if a==retries-1: raise
            time.sleep(0.6*(a+1))

start=1732752000000; end=1788739200000; chunk=60*86400000
raw={}; cur=start
while cur<end:
    e=min(cur+chunk-1,end)
    try:
        for c in hl_fetch(cur,e): raw[int(c['t'])]=c
    except Exception: pass
    cur+=chunk; time.sleep(0.12)
ts=sorted(raw.keys())
bars=[{'ts':t,'open':float(raw[t]['o']),'high':float(raw[t]['h']),'low':float(raw[t]['l']),'close':float(raw[t]['c'])} for t in ts]
def dstr(ts): return datetime.datetime.utcfromtimestamp(ts/1000).strftime('%Y-%m-%d')
n=len(bars)
closes=[b['close'] for b in bars]
ma7=[None]*n
for i in range(n):
    if i>=6: ma7[i]=sum(closes[i-6:i+1])/7.0
tr=[None]*n
for i in range(n):
    tr[i]=bars[i]['high']-bars[i]['low'] if i==0 else max(bars[i]['high']-bars[i]['low'],abs(bars[i]['high']-closes[i-1]),abs(bars[i]['low']-closes[i-1]))
atr=[None]*n
if n>14:
    atr[13]=sum(tr[0:14])/14.0
    for i in range(14,n): atr[i]=(atr[i-1]*13+tr[i])/14.0

def backtest(slope_thr=0.0, atr_mult=1.5):
    pos=None; trades=[]; equity=1.0; peak=1.0; max_dd=0.0; nav=[1.0]*n
    for i in range(n):
        # 出场
        if pos is not None and i>pos['entry_i']:
            stop=pos['stop']
            if ma7[i] is not None and atr[i] is not None:
                ns=ma7[i]-atr_mult*atr[i]
                if ns>stop: stop=ns
            exit_p=None
            if bars[i]['low']<=stop: exit_p=stop
            elif bars[i]['close']<=stop: exit_p=bars[i]['close']
            if exit_p is not None:
                equity*=exit_p/pos['entry_price']   # 复利
                trades.append((pos['entry_i'],i,pos['entry_price'],exit_p))
                pos=None
            else:
                pos['stop']=stop
        # 入场
        if pos is None and i>=14 and ma7[i-1] is not None and ma7[i] is not None and atr[i] is not None:
            if closes[i-1]<ma7[i-1] and closes[i]>ma7[i] and (ma7[i]-ma7[i-1])/ma7[i-1]*100>slope_thr:
                pos={'entry_price':bars[i]['close'],'entry_i':i,'stop':ma7[i]-atr_mult*atr[i]}
        # 净值
        cur=equity*(bars[i]['close']/pos['entry_price']) if pos is not None else equity
        nav[i]=cur
        if cur>peak: peak=cur
        dd=(peak-cur)/peak
        if dd>max_dd: max_dd=dd
    if pos is not None:
        equity*=bars[-1]['close']/pos['entry_price']
        trades.append((pos['entry_i'],n-1,pos['entry_price'],bars[-1]['close']))
    nt=len(trades); wins=sum(1 for t in trades if t[3]>t[2]); rets=[t[3]/t[2]-1 for t in trades]
    total_ret=equity-1; buyhold=closes[-1]/closes[0]-1
    days=(bars[-1]['ts']-bars[0]['ts'])/86400000.0
    cagr=equity**(365.0/days)-1 if days>0 else 0
    avg_hold=sum((t[1]-t[0]) for t in trades)/nt if nt else 0
    avg_ret=sum(rets)/nt if nt else 0
    return dict(nt=nt,wins=wins,winrate=wins/nt if nt else 0,total_ret=total_ret,buyhold=buyhold,
                max_dd=max_dd,cagr=cagr,avg_hold=avg_hold,avg_ret=avg_ret,trades=trades,rets=rets,nav=nav)

print(f"数据: {dstr(bars[0]['ts'])} ~ {dstr(bars[-1]['ts'])}  共 {n} 根日K (Hyperliquid官方)")
print(f"首日收盘 {closes[0]:.2f}  末日收盘 {closes[-1]:.2f}\n")
print("="*72)
print("策略：昨日收MA7下方 → 今日向上穿越MA7 且 MA7斜率>阈值 → 买入做多")
print("      移动止损：跌破 MA7 - 1.5*ATR14 离场（只上移不下移）")
print("="*72)
results={}
for thr in [0.0,0.3,0.5,1.0]:
    r=backtest(slope_thr=thr); results[thr]=r
    print(f"\n【MA7斜率阈值 > {thr}%/日】")
    print(f"  交易 {r['nt']} 次 | 胜率 {r['winrate']*100:.1f}% | 平均持仓 {r['avg_hold']:.1f} 天")
    print(f"  策略累计 {r['total_ret']*100:+.1f}% (年化 {r['cagr']*100:+.1f}%) | 买入持有 {r['buyhold']*100:+.1f}%")
    print(f"  最大回撤 {r['max_dd']*100:.1f}% | 单笔平均 {r['avg_ret']*100:+.2f}%")

print("\n"+"="*72); print("逐笔明细（斜率阈值 > 0）"); print("="*72)
r0=results[0.0]
print(f"{'入场日':<12}{'入场价':>9}{'离场日':<12}{'离场价':>9}{'收益%':>9}{'持仓天数':>8}")
for t in r0['trades']:
    print(f"{dstr(bars[t[0]]['ts']):<12}{t[2]:>9.2f}{dstr(bars[t[1]]['ts']):<12}{t[3]:>9.2f}{(t[3]/t[2]-1)*100:>9.1f}{t[1]-t[0]:>8}")

import csv
with open('/Users/ZK/WorkBuddy/2026-09-07-17-51-16/hype_trades.csv','w',newline='') as f:
    w=csv.writer(f); w.writerow(['entry_date','entry_price','exit_date','exit_price','ret_pct','hold_days'])
    for t in r0['trades']:
        w.writerow([dstr(bars[t[0]]['ts']),round(t[2],4),dstr(bars[t[1]]['ts']),round(t[3],4),round((t[3]/t[2]-1)*100,2),t[1]-t[0]])

# 保存净值曲线供画图
import pickle
with open('/Users/ZK/WorkBuddy/2026-09-07-17-51-16/hype_nav.pkl','wb') as f:
    pickle.dump({'dates':[dstr(b['ts']) for b in bars],'close':closes,'ma7':ma7,
                 'nav0':results[0.0]['nav'],'bh':[c/closes[0] for c in closes],
                 'trades':r0['trades']}, f)
print("\n已保存: hype_trades.csv, hype_nav.pkl")
