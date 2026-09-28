"""Aggregate actual replay outputs without selecting parameters by performance."""
from pathlib import Path
import json
import math
import hashlib
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[4]
FAMILY=Path(__file__).resolve().parents[1]
A=FAMILY/'artifacts'

def read(p):return json.loads(p.read_text())
def pct(x):return f'{100*x:+.2f}%'
def dd(x):return f'{100*abs(x):.2f}%'

def normalized_curve(path,start,semantics=None):
    f=pd.read_csv(path)
    tc='ts' if 'ts' in f else f.columns[0]
    ec=next((c for c in ('equity','net_equity','equity_net') if c in f),None)
    if ec is None:return None
    s=pd.Series(pd.to_numeric(f[ec]).values,index=pd.to_datetime(f[tc],utc=True)).sort_index()
    semantics=semantics or {}
    if semantics.get('label')=='bar_open':
        delta=pd.Timedelta(minutes=semantics['bar_duration_minutes'])
        terminal=pd.Timestamp('2026-09-05T15:00:00Z')
        s.index=pd.DatetimeIndex([min(t+delta,terminal) for t in s.index])
    s=s[~s.index.duplicated(keep='last')]
    return s[s.index>=pd.Timestamp(start)]

def main():
    rows=[]
    legacy=read(A/'hype_legacy/summary.json')
    choices={'HYPE-EMA-TB-V41':'observed_funding','HYPE-EMA-X-V18':'observed_funding_overlay',
        'HYPE-15M-MII-V1.4A':'observed_funding_overlay','HYPE-15M-TB-MII-ENS-V2':'observed_funding_overlay',
        'HYPE-CC-V35':'next_open_spec_cost'}
    for d in legacy:
        if choices.get(d['strategy'])!=d['variant']:continue
        ep=Path(d['equity_file']);ep=ep if ep.is_absolute() else ROOT/ep
        rows.append({'name':d['strategy'],'family':d['family'],'registered':True,'primary':True,
            'start':d['start'],'return':d['return_pct']/100,'drawdown':d['max_drawdown_pct']/100,
            'trades':d['natural_closed_trades']+d.get('terminal_marks',0),'cost':d['cost'],
            'equity_path':str(ep),'equity_timestamp_semantics':{'label':'bar_open','bar_duration_minutes':15},'source':str((A/'hype_legacy/summary.json').relative_to(ROOT)),
            'limitation':d.get('limitation','') or ('spec与旧代码成交时点有歧义，单列敏感性' if d['strategy']=='HYPE-CC-V35' else '')})
    for d in read(A/'other_assets/results.json'):
        if d['scenario']!='base':continue
        rows.append({'name':f"{d['asset']}-1H-AR-{d['version']}",'family':f"{d['asset']}-1h-ar",'registered':True,'primary':True,
            'start':d['start'],'return':d['return'],'drawdown':min(d['close_marked_max_drawdown'],d['legacy_engine_conservative_mae_drawdown']),
            'trades':d['trade_count'],'cost':'手续费10bps/边+滑点4bps/边；原固定杠杆',
            'equity_path':str(A/f"other_assets/{d['asset']}/base_equity.csv"),'source':str((A/'other_assets/results.json').relative_to(ROOT)),
            'limitation':'回撤取收盘盯市与原单笔最不利价格估计较大者；同K内先后次序不完全可知'})
    registered={'ar_v4','keltner_v3','mmtf_1h_v3','mmtf_15m_v3','mdtp_v1'}
    inventory_path=A/'hype_other/inventory.json'
    case_family={case:row['family'] for row in read(inventory_path)['rows'] for case in row.get('cases',[])} if inventory_path.exists() else {}
    family_map={'mhef_1h':'1h-mhef','mtpp_':'15m-mtpp','keltner15_':'15m-keltner','sds_':'15m-sds','ma_pt_':'15m-ma-pt'}
    for p in sorted((A/'hype_other').glob('*/summary.json')):
        case=p.parent.name
        if 'prefix' in case:continue
        d=read(p);m=d.get('metrics',{})
        fid=case_family.get(case,next((v for k,v in family_map.items() if case.startswith(k)),case))
        count=m.get('trades',m.get('campaigns',m.get('directional_entries')))
        if count is None:
            try:count=len(pd.read_csv(p.parent/'trades.csv'))
            except pd.errors.EmptyDataError:count=0
        xdd=d['curve_close_drawdown']
        if case=='ar_v4':xdd=min(xdd,m.get('max_dd',0))
        rows.append({'name':d['version']+' / '+case,'family':fid,'registered':case in registered,'primary':case in registered,
            'start':d['start'],'return':d['curve_return'],'drawdown':xdd,'trades':count,
            'cost':'手续费10bps/边+滑点4bps/边；原仓位规则','equity_path':str(p.parent/'equity.csv'),
            'source':str(p.relative_to(ROOT)),'equity_timestamp_semantics':d.get('equity_timestamp_semantics',{'label':'bar_open','bar_duration_minutes':60 if case=='ar_v4' or case.startswith('mhef_1h') or case=='mmtf_1h_v3' else 30 if case=='keltner_v3' else 15}),'limitation':d.get('limitation','')})
    d=read(A/'ensemble/base/summary.json')
    rows.append({'name':'六币1H-AR-MAE-V1','family':'1h-ar-mae','registered':True,'primary':True,'start':d['start'],
        'return':d['return'],'drawdown':d['max_drawdown'],'trades':d['trades'],
        'cost':'手续费10bps/边+滑点4bps/边；成分原杠杆，最高5倍',
        'equity_path':str(A/'ensemble/base/equity.csv'),'source':str((A/'ensemble/base/summary.json').relative_to(ROOT)),
        'limitation':'原spec先生成各币交易再做账户阻塞；不是联合实时账户；SOL固定V2、ETH固定V3'})
    # Supplementary observations are exported by the other-assets worker.
    supplemental=A/'other_assets/supplemental_results.json'
    if supplemental.exists():
        for d in read(supplemental):
            if d.get('scenario','base')!='base':continue
            d=dict(d)
            names={'lvcb-913f4ff89386':'BTC 15m 续涨 / lvcb-913f4ff89386','lvcb-08816b18771a':'BTC 30m 续涨 / lvcb-08816b18771a','SOL_1H_PB_R01145':'SOL 1h 回踩 / R01145','SOL_1H_VCB_R002346':'SOL 1h 波动压缩突破 / R002346','SOL_4H_RS4_R0343':'SOL 4h RS4 / R0343'}
            d['name']=names.get(d['name'],d['name'])
            rows.append(d)
    as6s=A/'other_assets/AS6S_V6/results.json'
    if as6s.exists():
        for d in read(as6s)['results']:
            if d['scenario']!='base':continue
            route=d['route'];name='不抢仓' if route=='nonpreemptive' else '强突破抢仓'
            rows.append({'name':f'六币15m AS6S V6 / {name}','family':'15m-as6s','registered':True,'primary':False,
                'start':d['start'],'return':d['return'],'drawdown':min(d['close_marked_max_drawdown'],d['legacy_mae_drawdown']),
                'trades':d['trades'],'cost':'手续费10bps/边+滑点4bps/边；原0.75账户分配倍数',
                'equity_path':str(A/f'other_assets/AS6S_V6/{route}_base_equity.csv'),
                'source':str(as6s.relative_to(ROOT)),
                'limitation':'从原移植程序恢复参数并使用官方mark回放；原冻结JSON已删，无法再次核对原JSON哈希；本轮提前部分揭示。'})
    for r in rows:
        path=Path(r.get('equity_path',''))
        if not path.exists():
            # Worker schema may name scenario curves in the other order.
            alternative=path.with_name('equity_base.csv')
            if alternative.exists():path=alternative;r['equity_path']=str(path)
        if path.is_file():
            s=normalized_curve(path,r['start'],r.get('equity_timestamp_semantics'))
            if s is not None and len(s):
                start=pd.Timestamp(r['start']);cut=start+pd.Timedelta(days=30)
                first=s[s.index<=cut]
                r['first30_return']=float(first.iloc[-1]-1) if len(first) else None
                r['after30_return']=float(s.iloc[-1]/first.iloc[-1]-1) if len(first) and s.index[-1]>cut else None
                aug=s[s.index<=pd.Timestamp('2026-09-01T00:00:00Z')]
                july=s[s.index<=pd.Timestamp('2026-08-01T00:00:00Z')]
                r['august_return']=float(aug.iloc[-1]/(july.iloc[-1] if len(july) else 1)-1) if len(aug) else None
    (A/'all_results.json').write_text(json.dumps(rows,indent=2,ensure_ascii=False,default=str)+'\n')
    pd.DataFrame(rows).to_csv(A/'all_results.csv',index=False)
    mainrows=sorted([r for r in rows if r['primary']],key=lambda r:r['return'],reverse=True)
    positive=[r for r in mainrows if r['return']>1e-12];negative=[r for r in mainrows if r['return']<-1e-12];zero=[r for r in mainrows if abs(r['return'])<=1e-12]
    lines=['# 早期日内策略：落档之后还能不能赚钱（2026-09-10）','',
        f'本轮实际回放覆盖 {len(set(r["family"] for r in rows))} 个策略家族，共 {len(rows)} 条主版本、固定观察及并列方案。重点 {len(mainrows)} 组登记版本的复核结果为：{len(positive)} 组期末盈利、{len(negative)} 组亏损、{len(zero)} 组没有交易；其中CC V35存在spec/代码时序歧义，只作为有歧义的复核对照。其余包括未登记但已写清参数的观察，以及从原移植程序恢复的六币15m组合两种模式。全部结果附在后表，没有根据本次收益重新挑参数。',
        '', '主体计算截至 **2026-09-05 15:00 UTC（北京时间23:00）**，并非9月10日；额外的SOL 4h RS4观察只到当天最后完整4h收盘12:00 UTC。每组从其spec/登记之后空仓启动、保留更早指标预热，测试时间不同，所以不是同一时段的选股排名。只有日期时从次日UTC开始。',
        '', '**收益均扣原手续费和滑点；加入现有资金费事件的结果仍是估计值。** 全窗口历史结算日历、部分结算mark价格和历史身份资料未全部核准，不能称为已完整核准的净收益。零交易不是策略赚钱。回撤包括持仓过程，不只看平仓盈亏；表中部分原引擎还采用单笔最不利价格估计。',
        '', '## 已登记版本完整结果清单（不是无争议候选排名）','',
        '| 策略 | 开始日期 UTC | 截止时收益 | 最大回撤 | 交易/期末结算数 | 前30天 | 之后 |',
        '| --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for r in mainrows:
        lines.append(f"| {r['name']} | {str(r['start'])[:10]} | {pct(r['return'])} | {dd(r['drawdown'])} | {int(r['trades'])} | {pct(r['first30_return']) if r.get('first30_return') is not None else '—'} | {pct(r['after30_return']) if r.get('after30_return') is not None else '—'} |")
    lines+=['','## 怎么看这些结果','',
        '- 最值得继续核对的是 HYPE 15m MII V1.4A，以及未登记但规格明确的 HYPE 1h 多速度EMA预测。它们这段有利润且回撤比30m Keltner小，但目前样本时间仍短，不能因此认定长期有效。',
        '- BTC 15m续涨冻结观察也值得继续核对：本次收益约14.56%、回撤约5.64%，前30天及后段都为正；8笔交易仍不足以排除偶然。BTC30m续涨约20.27%，但只有3笔，不能按更高收益直接认定更好。',
        '- HYPE 30m Keltner V3 赚得最多，同时经历超过30%的回撤。若用户承受不了这样的中途亏损，这一段赚钱也不代表适合使用。',
        '- BTC/ETH 1h自适应策略的盈利交易太少，尤其BTC只有一笔；不能把偶然一次赚钱当成已经验证。',
        '- HYPE EMA-X V18、EMA-TB V41、TB+MII V2以及六币1h组合在落档后明显恶化。组合不会自动分散亏损，六币组合原规则允许最高5倍暴露。',
        '- HYPE CC V35 在原成本下接近保本，按后来的Binance更高成本则明显亏损；原spec与代码的入场/退出时点还有歧义，因此不作为清晰复现的候选推荐。',
        '', '## 原成本与关键限制','', '| 策略 | 原成本 / 仓位 | 本次限制 |','| --- | --- | --- |']
    for r in mainrows:lines.append(f"| {r['name']} | {r['cost']} | {r['limitation'] or '资金费与结算价格完整性未全部核准；收益为估计'} |")
    lines+=['','## 其他有明确冻结规则或已恢复的方案','',
        '同一家族的不同机制、仓位档位或缓冲版本全部并列，不能按本次成绩从中选一个再声称它早就被确定。连续仓位策略的方向段数也不能和完整往返交易数直接等同。',
        '', '| 原观察方案 | 起点 UTC | 收益 | 最大回撤 | 交易/方向段 |','| --- | --- | ---: | ---: | ---: |']
    for r in rows:
        if r['primary']:continue
        lines.append(f"| {r['name']} | {str(r['start'])[:10]} | {pct(r['return'])} | {dd(r['drawdown'])} | {r['trades']} |")
    lines+=['','## 复核与交付材料','',
        '- 原始策略参数未改动、没有新搜索；每组原代码/配置和日期证据在各子目录。已有缺失参数通过spec恢复；缺失优先级的五币1h策略检查了两种顺序在本段是否产生相同逐笔交易，未按收益选择顺序。',
        '- 有两个家族需特别区分：HYPE 15m PBTR 最新追踪止损版本有已记录的不可执行问题，附表只回放主账另行列明的固定止损代表方案；HYPE 1h PKTSC 原诊断代码用未来结果是否齐全筛选测试行，本次改为只要求当时已知特征齐全，并保留原来的每日训练与参数，因此属于修正时间错误后的规则回放，不是原代码逐字复现。',
        '- 另有7个家族未得到有效回测：HYPE 15m因子机器学习缺训练模型，15m多速度EMA预测缺完整候选配置；15m及1h价格运动延续研究没有入场、退出和仓位规则；HYPE 30m Keltner突破回踩和BNB 15m自适应研究没有确定唯一策略；HYPE 15m Riptide还存在未解决的原结果复现差异。它们没有被记作亏损，也没有被默认算成零收益。',
        '- 原始闭合15m/1h价格共六币，经本次完整组合检查，无缺口且有效性窗口通过；所有派生输入都有SHA256。资金费事件另存，未伪造完整覆盖。',
        '- HYPE每个主要登记后窗口都有135个资金事件缺少原生结算mark价格，不是在预热期之外就消失；原模型按分配比例乘费率的估计不能代替精确结算金额。',
        '- 针对主要引擎做截断回放、终点结算、逐笔复利与曲线终值核对；具体结果见各组verification材料和统一验收文件。',
        '- 本轮重点是早期15m、30m、1h加密币策略，不宣称已跑完整仓库的1m/5m、4h、日线、全市场机器学习或传统资产。不能恢复的家族与仍缺资料的条目见[覆盖清单](../artifacts/coverage_inventory.json)。',
        '', '[全部结果数据](../artifacts/all_results.csv) · [主版本收益图](../artifacts/registered_returns.png) · [独立验收](../artifacts/acceptance_independent.json) · [本次输入与资金费审计](../artifacts/inputs/manifest.json) · [研究规则](../specs/contract-20260910.md)',
        '', '本报告只回答原规则在落档之后这段历史的表现；这段历史已经查看，今后不能再次称为未知样本。']
    (FAMILY/'diagnostics/report-20260910.md').write_text('\n'.join(lines)+'\n')
    print(json.dumps({'registered':len(mainrows),'positive':len(positive),'negative':len(negative),'zero':len(zero),'all_observation_rows':len(rows)},ensure_ascii=False))

if __name__=='__main__':main()
