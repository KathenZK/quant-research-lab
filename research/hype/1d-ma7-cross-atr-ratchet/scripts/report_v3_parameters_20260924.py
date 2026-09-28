"""Report every frozen case, not just winners; offline interactive HTML."""
from pathlib import Path
import sys,json,html
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[4]
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts'))
from build_ma30_report_20260911 import STYLE,COMMON_JS
from common import write_json
R=BASE/'artifacts/v3_parameter_stability_20260924'

def records(frame):return json.loads(frame.to_json(orient='records',date_format='iso',double_precision=15))
def mdtable(headers,rows):return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |',*['| '+' | '.join(map(str,row))+' |' for row in rows]])
def fmt(x):return '—' if x is None or pd.isna(x) else f'{x:.2f}'

def main():
 frozen=json.loads((R/'started.json').read_text());audit=json.loads((R/'audit.json').read_text());assert audit['complete']
 c=pd.read_csv(R/'comparison.csv');m=pd.read_csv(R/'memberships.csv');b=c.set_index('case_id').loc['B'];joined=m.merge(c,on='case_id',suffixes=('_membership',''))
 cfgs={x['case_id']:x['config'] for x in frozen['cases']};basecfg=cfgs['B'];look=c.set_index('case_id')
 stats=[];path_data={};pairs=[];periods=[]
 bt=pd.read_csv(R/'accounts/B/trades.csv');old={(t.entry_time,int(t.side)):t for t in bt.itertuples()}
 economic_cols=['entry_time','exit_time','side','entry_price','exit_price','return_on_entry_equity']
 economic={}
 for case in frozen['cases']:
  cid=case['case_id'];p=R/'accounts'/cid;t=pd.read_csv(p/'trades.csv');eq=pd.read_parquet(p/'equity.parquet');economic[cid]=t[economic_cols]
  day=eq.assign(day=eq.timestamp.dt.floor('D')).groupby('day',sort=False).tail(1)
  trcols=['trade_id','entry_time','exit_time','side','entry_price','exit_price','return_on_entry_equity','exit_reason','tightening_days','stop_mult']
  path_data[cid]={'trades':records(t[trcols]),'curve':records(day[['timestamp','equity']])}
  new={(z.entry_time,int(z.side)):z for z in t.itertuples()}
  for k in sorted(old.keys()|new.keys()):
   x,y=old.get(k),new.get(k)
   pairs.append({'case_id':cid,'entry_time':k[0],'side':k[1],'relationship':'same' if x and y else 'missed' if x else 'new',
      'baseline_return_pct':x.return_on_entry_equity*100 if x else None,'new_return_pct':y.return_on_entry_equity*100 if y else None,
      'baseline_exit':x.exit_time if x else None,'new_exit':y.exit_time if y else None,
      'baseline_terminal':bool(x and x.exit_reason=='sample_end'),'new_terminal':bool(y and y.exit_reason=='sample_end')})
  boundary=pd.Timestamp('2026-01-01',tz='UTC');at=float(eq.loc[(eq.timestamp==boundary)&eq.kind.eq('hour_close'),'equity'].iloc[0])
  for label,lo,hi,start_equity in [('2025剩余时段',pd.Timestamp(b.start),boundary,10000.),('2026至截止',boundary,pd.Timestamp(b.end_exclusive),at)]:
   z=eq.loc[(eq.timestamp>=lo)&(eq.timestamp<=hi),'equity'].to_numpy()
   final=at if label=='2025剩余时段' else float(eq.equity.iloc[-1]);z=np.r_[start_equity,z,final]
   periods.append({'case_id':cid,'period':label,'start':str(lo),'end':str(hi),'return_pct':100*(final/start_equity-1),'max_drawdown_pct':100*float(np.min(z/np.maximum.accumulate(z)-1))})
 for key,(label,values) in frozen['grid'].items():
  group=joined[(joined.group=='neighbor')&(joined.parameter==key)].sort_values('value');off=group[group.value.ne(basecfg[key])].copy()
  good=((100+off.return_pct)>=(100+b.return_pct)*.75)&(off.max_drawdown_pct.abs()<=abs(b.max_drawdown_pct)+5)
  near=off[off.value.isin([values[1],values[3]])];ng=((100+near.return_pct)>=(100+b.return_pct)*.75)&(near.max_drawdown_pct.abs()<=abs(b.max_drawdown_pct)+5)
  same=sum(economic[row.case_id].equals(economic['B']) for row in off.itertuples())
  stats.append({'parameter':key,'label':label,'baseline':basecfg[key],'values':values,'returns':group.return_pct.tolist(),
    'drawdowns':group.max_drawdown_pct.abs().tolist(),'all_profitable':bool(off.return_pct.gt(0).all()),'passing_neighbors':int(good.sum()),'passing_nearest':int(ng.sum()),
    'same_economic_paths':same,'label_stability':'本样本路径未变' if same==4 else '五点较稳' if good.all() else '最近邻较稳，外侧敏感' if ng.all() else '敏感',
    'minimum_return_pct':float(off.return_pct.min()),'maximum_return_pct':float(off.return_pct.max()),
    'median_return_pct':float(off.return_pct.median()),'maximum_drawdown_pct':float(off.max_drawdown_pct.abs().max())})
 pd.DataFrame(stats).to_csv(R/'parameter_stability.csv',index=False);pd.DataFrame(pairs).to_csv(R/'trade_pairs.csv',index=False);pd.DataFrame(periods).to_csv(R/'calendar_periods.csv',index=False)
 joint=joined[joined.group.eq('joint')];joint_summary={'n':len(joint),'profitable':int(joint.return_pct.gt(0).sum()),'return_min':float(joint.return_pct.min()),'return_median':float(joint.return_pct.median()),'return_max':float(joint.return_pct.max()),'drawdown_median':float(joint.max_drawdown_pct.abs().median()),'drawdown_max':float(joint.max_drawdown_pct.abs().max()),'wealth_75pct_count':int(((100+joint.return_pct)>=(100+b.return_pct)*.75).sum())}
 write_json(R/'analysis.json',{'parameters':stats,'joint':joint_summary,'all_off_center_neighbors':44,'off_center_profitable':int(joined[(joined.group=='neighbor')&joined.case_id.ne('B')].return_pct.gt(0).sum()),'path_equal_ablations':[cid for cid in economic if cid.startswith('A_') and economic[cid].equals(economic['B'])]})
 out=R/'html';out.mkdir(exist_ok=True)
 body='''<p class="note">仅HYPE，统一空仓起点2025-06-19，结束于2026-09-05 00:00 UTC。每边手续费0.1%、滑点0.04%；约1倍复利，未核实资金费未计入。121组不同配置，所有结果都展示。没有自动替换V3。</p>
<div class="stats"><b>结论：收紧参数较平缓，MA7的高收益明显突出。</b><br>44个单参数邻点全部盈利；11参数同时小幅偏移的32组也都盈利，但收益只有23.51%—90.46%。不能把“仍然盈利”理解成“高收益稳定”。</div>
<p>原6月15日起点的V3为+544.76%／回撤27.26%／18笔。本页所有实验统一起点的V3为<b>+463.60%／回撤27.26%／17笔</b>。起点改变了早期持仓占用，不能只减去第一笔收益。</p>
<p><a href="#neighbors">11参数邻域</a> · <a href="#interactions">联合检查</a> · <a href="#all">全部实验</a> · <a href="../../../diagnostics/v3-parameter-stability-results-20260924.md">完整中文报告</a> · <a href="../comparison.csv">完整结果表</a></p>
<h2 id="neighbors">每次只动一个参数</h2><label>参数 <select id="parameter"></select></label><p id="localSummary"></p><div id="localTable" class="scroll"></div><div id="localCharts"></div>
<p class="note">标签提前固定：四个非基线邻点都保留至少75%的期末资产，且回撤不比基线高5个百分点以上，称本样本五点较稳。并非统计显著性或未来保证。点击任一结果查看该配置的完整交易。</p>
<h2 id="interactions">两个相关参数同时改变</h2><select id="pair"></select><div id="heatmap" class="scroll"></div><p class="note">每格显示收益／回撤；点击查看明细。六组3×3全部保留。多个分组重复引用同一配置，去重后仍为121个账户。</p>
<h2>11参数同时扰动：32组平衡检查</h2><div id="jointSummary"></div>
<h2 id="all">全部规则消融与参数实验</h2><div class="filters"><label>组别 <select id="group"><option value="ablation">规则消融／替换</option><option value="neighbor">单参数邻域</option><option value="pair">两参数联合</option><option value="joint">11参数同时扰动</option><option value="all">全部121配置</option></select></label><label>排序 <select id="sort"><option value="declared">声明顺序</option><option value="return">收益从高到低</option><option value="drawdown">回撤从小到大</option></select></label><label>筛选 <input id="search" placeholder="参数名或方案名称"></label></div><p id="count"></p><div id="resultTable" class="scroll"></div>
<h2 id="detail">完整账户与交易明细</h2><select id="case"></select><p id="caseSummary"></p><div id="config" class="scroll"></div><div id="equityChart"></div><div id="periods" class="scroll"></div><p>净值图按日显示，表中最大回撤按完整小时节点计算。样本末结算单尚未自然退出。</p><div id="trades" class="scroll"></div><h3>与基线相同入场的盈亏变化，以及新增／错失</h3><div id="tradePairs" class="scroll"></div><p id="links"></p>
<p class="note">同入场配对不能替代账户结果：错失基线赢家按0计入保留率，新增交易另列。多参数改变了入场、退出和资金占用，不能将收益差全部归因于单一退出点。本轮是已见HYPE样本内诊断，不是全市场或未见样本验证。</p>'''
 data={'rows':records(c),'members':records(m),'grid':frozen['grid'],'baseConfig':basecfg,'configs':cfgs,'stability':stats,'joint':joint_summary,'paths':path_data,'pairs':pairs,'periods':periods}
 payload=json.dumps(data,ensure_ascii=False,allow_nan=False,separators=(',',':')).replace('</','<\\/')
 page='<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>HYPE V3 · 参数稳定性</title><style>'+STYLE+'svg{max-width:100%;height:auto} select{max-width:100%}.twocol{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:16px} .baseline{background:#eef5f0}button{cursor:pointer}td{white-space:nowrap}</style><main><h1>HYPE V3 · 全参数消融与邻域检查</h1>'+body+'</main><script>const DATA='+payload+';\n'+COMMON_JS+JS+'</script></html>'
 (out/'index.html').write_text(page)
 report=build_report(c,joined,stats,joint_summary,audit,periods)
 (BASE/'diagnostics/v3-parameter-stability-results-20260924.md').write_text(report)
 write_json(R/'report_complete.json',{'complete':True,'unique_cases':len(c),'html':'html/index.html','browser_layout_verified':False,'no_new_backtests_during_report':True})
 print('Report and HTML complete',flush=True)

def build_report(c,j,stats,joint,audit,periods):
 b=c.set_index('case_id').loc['B'];ab=j[j.group=='ablation'];sections=[]
 sections.append('''# HYPE V3全参数消融与邻域检查

**结论：V3的部分机制有明确贡献，停滞后的渐进收紧有较宽容的参数区间；但四五倍的高收益没有形成广泛稳定的平台，均线7日明显突出，几个空单止盈阈值还依赖一次关键的持仓切换。** 44个单参数非基线邻点都盈利，因此不是稍微改变参数就亏损；高收益的稳定性明显弱于盈利方向的稳定性。

[打开可筛选HTML：全部参数、联合检查和逐笔交易](../artifacts/v3_parameter_stability_20260924/html/index.html) · [运行前契约](../specs/v3-parameter-stability-registry-correction-20260924.md) · [完整账户表](../artifacts/v3_parameter_stability_20260924/comparison.csv)。

## 固定范围与起点

仅HYPE；原冻结行情至2026-09-04，未更新到研究日期2026-09-24。每边手续费0.1%、不利滑点0.04%、约1倍名义仓位复利，未知资金费未计入。次日开盘执行、小时止损、实际止损只能收窄。

原V3从6月15日起，+544.76%／回撤27.26%／18笔，逐笔复现成功。最长ATR18于6月18日收盘自然就绪，所以本实验全部从**6月19日空仓**开始，结束于2026-09-05 00:00 UTC。共同起点的V3为**+463.60%／回撤27.26%／17笔**。这不是新增任意预热；原起点保留单独对照。原6月18日空单不再参与后，6月28日多仓会占用7月3日原多仓机会，因此不能只从总收益减掉第一笔。

声明20项规则移除/替换、11参数各五点、六组最近邻3×3、32组11参数同时扰动，去重后121配置。这里“全参数”指当前V3所有11个生效数值参数；费用、成交时序与只收窄等执行约束保持固定。已关闭的MA30、延后确认、初始止损封顶等不假装成V3参数。不是穷举所有参数笛卡尔积，没有按结果扩搜索。

## 全部规则消融与结构对照

下表统一与+463.60%／27.26%／17笔比较。只移除一项的结果也包含后续持仓占用变化；这是该改动的账户总效果，不是机械相减的独立利润贡献。''')
 sections.append(mdtable(['移除或替换','收益','回撤','笔数','单笔盈亏比','原赢家转亏','原前5赢家保留'],[[r.label,fmt(r.return_pct)+'%',fmt(abs(r.max_drawdown_pct))+'%',r.trades,fmt(r.unit_payoff),r.winners_to_loss,fmt(r.top5_retention_pct)+'%'] for r in ab.itertuples()]))
 sections.append('''斜率与穿越事件有实质贡献：移除全部斜率后亏损41.28%，移除穿越事件后只剩24.47%。取消停滞收紧仍赚392.25%，说明收紧有增益，但并非所有盈利都由这一个部件产生。取消整个空单提前止盈降至187.85%；取消逐步收紧、直接到0.5降至278.71%，回撤35.26%。

**默认条件下，移除RSI门槛、移除跌幅大于前日条件、移除提前止盈须有净浮盈条件，三者分别都与基线经济路径完全相同。** 只能说这些条件在本样本、其他条件保持不变时没有额外拦截，不能据此认定它们在其他行情无用，也未测试三个同时删除。

冻结入场ATR、改收盘价停滞在该样本中收益更高；其余指标有取舍。它们是结构替换的样本内结果，不选作新版本。原前5赢家保留率允许超过100%，且包含样本末估值；冻结MA锚等长持有会得到高比值，同时回撤很大，不能单看保留率。

## 11项参数的完整五点结果

每行收益顺序与参数取值一一对应。预先固定的“较稳”要求四个非基线邻点都保留至少75%的期末资产，且回撤不超过基线+5个百分点；这是描述标签，不是统计检验。''')
 sections.append(mdtable(['参数','取值顺序','对应收益%','四邻点最大回撤','标签'],[[s['label'],' / '.join(map(str,s['values'])),' / '.join(fmt(v) for v in s['returns']),fmt(s['maximum_drawdown_pct'])+'%',s['label_stability']] for s in stats]))
 sections.append('''- **均线周期最突出：MA6为+64.11%，MA7为+463.60%，MA8为+101.27%。** MA5/9也盈利，但都明显低于7。均线改变同时改变穿越、斜率和止损，不能把差距只归因于止损锚。5个点不足以统计证明过拟合，但不支持“7附近有宽阔的高收益平台”。
- **收紧步长、下限、初始ATR倍数和斜率门槛相对平缓。** 不是恰好0.2或0.5才有效。停滞3/4/5日也较稳，缩到2日才明显下降；这与过早收紧伤害趋势的既有证据一致。
- ATR周期、RSI周期/门槛、加速幅度存在离散变化；其中若干差距主要是同一条后续持仓路径放大的，不能当成多个独立证据。
- “跌幅必须比前日大多少”的0.75–1.25全部同路径，邻域平坦也可能来自条件没有实际起作用，而非强泛化能力。

## 一条关键路径为何制造阈值跳变

2026年7月17日空单，在原V3中于7月28日提前止盈，赚7.36%。7月27日收盘时RSI6=29.4687，单日跌幅3.535，前日ATR14=3.4548；刚好满足RSI≤30且跌幅≥1ATR。

- RSI周期6改7后，RSI变成30.4876，未达到30。
- ATR周期14改16后，前日ATR变成3.5730，高于跌幅3.535。
- RSI上限降为25，或加速门槛升至1.2ATR，也会错过这次提前退出。

这些方案的空单继续占仓至8月12日，收益仍约6.6%，单笔本身没有差很多；**但8月9日多头信号因仍持空单而无法入场**。原V3这笔多仓到样本末估值+52.71%，几个改动方案直到8月30日才再开多，末尾估值+0.95%。因此总收益大降主要包含错过后一笔的影响，不能解读为“RSI7的空头止盈本身差一半”。

同口径基线剔除最后样本末结算单的自然退出交易复利为+269.06%；这仍是强结果，但说明+463.60%中有显著末尾趋势贡献。该剔除统计仅识别依赖，不能当作新的可执行策略，也不是未来验证。

## 六组相关参数联合检查

每格为收益%／最大回撤%。所有九格保留，行列中间为V3默认值。''')
 for key,g in j[j.group=='pair'].groupby('pair',sort=False):
  x,y=key.split('__');xs=sorted(g.x.unique());ys=sorted(g.y.unique());sections.append(f'### {x} × {y}\n\n'+mdtable([x+' \\ '+y,*map(str,ys)],[[vx,*[fmt(g[(g.x==vx)&(g.y==vy)].iloc[0].return_pct)+' / '+fmt(abs(g[(g.x==vx)&(g.y==vy)].iloc[0].max_drawdown_pct)) for vy in ys]] for vx in xs]))
 sections.append(f'''## 11参数同时偏移

32组平衡联合扰动全部盈利，收益范围**+{joint['return_min']:.2f}%至+{joint['return_max']:.2f}%**，中位**+{joint['return_median']:.2f}%**；回撤中位{joint['drawdown_median']:.2f}%，最大{joint['drawdown_max']:.2f}%。**没有一组保留基线75%的期末资产。**

这32组全部参数均取最近邻高或低值，包括MA只取6或8，不含7。因此它们主要说明离开当前组合后高收益不易保留，不能将差距归咎于11个参数都分别脆弱；均线3×3与各参数单独结果提供了区分。这是32/2048个角点的平衡设计，不是全面交互搜索或置信区间。32个参数向量虽然不同，前日跌幅比较倍数在这里仍未改变交易，实际只有16种经济路径；更不能视为32个独立市场样本。

## 时间贡献与结论边界

以下是连续账户在自然年边界的权益变化，跨年持仓照常携带，未重置账户；两个阶段都已被看过，不能称为样本外。''')
 periods=pd.DataFrame(periods);selected=['B','A_no_slope','A_no_short_tp','N_ma_period_6','N_ma_period_8']
 sections.append(mdtable(['方案','2025剩余时段收益','2026至截止收益'],[[cid,*[fmt(periods[(periods.case_id==cid)&(periods.period==p)].iloc[0].return_pct)+'%' for p in ['2025剩余时段','2026至截止']]] for cid in selected]))
 sections.append(f'''完整121配置分段指标见[连续账户时间贡献](../artifacts/v3_parameter_stability_20260924/calendar_periods.csv)。这些只是单币已见样本，不能满足完整牛熊或全市场适配证明。

本轮支持保留V3作为清晰基线；收紧部件有贡献且部分参数存在平台。下一步值得研究的薄弱处是“开仓必须发生在某条均线穿越当天”与“退出时点改变后续持仓占用”的耦合，不能继续按这段HYPE的最高收益挑参数。未把本轮更高收益配置晋升，未改变正式V3。

## 核验与证据

登记表检查发现并修正了重复组合：旧110行实际105种数值配置、联合32行实际16种；旧草稿单独留存并撤回汇总标签。修正只恢复事先声明的32种不同联合向量、合并数值相等配置，没有按收益增删参数。最终以下统计均按121个不同配置。

23项针对性测试通过，覆盖冻结v7默认等价、独立指标计算、11参数未来前缀不变、止损日程与单向约束、联合设计平衡及非法参数拒绝。原起点V3逐笔复现一致。独立核验121账户、{audit['trades']:,}笔交易、{audit['stop_records']:,}条止损及{audit['equity_marks']:,}个权益节点通过；数量、成本、最早止损、空单最早合格止盈、入场机会和账户权益均检查。

[核验结果](../artifacts/v3_parameter_stability_20260924/audit.json) · [测试记录](../artifacts/v3_parameter_stability_20260924/tests.json) · [运行前冻结配置](../artifacts/v3_parameter_stability_20260924/started.json) · [全部配对](../artifacts/v3_parameter_stability_20260924/trade_pairs.csv) · [参数分类](../artifacts/v3_parameter_stability_20260924/parameter_stability.csv)。HTML使用离线脚本核验，真实浏览器视觉布局未验证；交互核验记录与最终散列清单在产物目录。
''')
 return '\n\n'.join(sections)+'\n'

JS=r'''
const byId=Object.fromEntries(DATA.rows.map(r=>[r.case_id,r]));
function choose(id){$('case').value=id;detail();}
function btn(id,label){return `<button onclick="choose('${id}')">${esc(label)}</button>`;}
function chart(points,title,color,percent=true){
 const w=650,h=240,L=65,R=625,T=30,B=200;let ys=points.map(p=>p[1]);let low=Math.min(0,...ys),high=Math.max(...ys);if(high-low<1e-8)high=low+1;
 const Y=v=>B-(v-low)/(high-low)*(B-T),X=i=>L+(R-L)*i/Math.max(1,points.length-1);
 let s=`<svg viewBox="0 0 ${w} ${h}" role="img" aria-label="${esc(title)}"><text x="${L}" y="18" fill="#22382f">${esc(title)}</text>`;
 for(let i=0;i<4;i++){let v=low+(high-low)*i/3,y=Y(v);s+=`<line x1="${L}" x2="${R}" y1="${y}" y2="${y}" stroke="#e4eae6"/><text x="4" y="${y+4}" font-size="11">${num(v,1)}${percent?'%':''}</text>`;}
 s+=`<polyline points="${points.map((p,i)=>X(i)+','+Y(p[1])).join(' ')}" fill="none" stroke="${color}" stroke-width="2"/>`;
 points.forEach((p,i)=>{if(points.length<10){s+=`<circle cx="${X(i)}" cy="${Y(p[1])}" r="4" fill="${color}"><title>${esc(p[0])}: ${num(p[1])}</title></circle><text x="${X(i)}" y="225" text-anchor="middle" font-size="12">${esc(p[0])}</text>`;}});
 if(points.length>=10)s+=`<text x="${L}" y="225" font-size="11">${esc(points[0][0])}</text><text x="${R}" y="225" text-anchor="end" font-size="11">${esc(points.at(-1)[0])}</text>`;
 return s+'</svg>';
}
function rowValues(r,label){return [btn(r.case_id,label||r.label),sign(r.return_pct),pct(Math.abs(r.max_drawdown_pct)),r.trades,pct(r.win_rate_pct),num(r.unit_payoff),sign(r.closed_only_compounded_pct),num(r.top5_retention_pct)+'%'];}
const headers=['方案（点击看交易）','收益','最大回撤','笔数','胜率','盈亏比','剔除末尾估值后','原前5赢家保留'];
function local(){const key=$('parameter').value,s=DATA.stability.find(r=>r.parameter===key);const rs=DATA.members.filter(m=>m.group==='neighbor'&&m.parameter===key).sort((a,b)=>a.value-b.value);
 $('localSummary').textContent=`${s.label_stability} · 最近两点通过 ${s.passing_nearest}/2 · 四邻点通过 ${s.passing_neighbors}/4 · 与基线经济路径相同 ${s.same_economic_paths}/4`;
 $('localTable').innerHTML=table(headers,rs.map(m=>rowValues(byId[m.case_id],String(m.value)+(m.case_id==='B'?' · V3':''))));
 $('localCharts').innerHTML='<div class="twocol">'+chart(rs.map(m=>[m.value,byId[m.case_id].return_pct]),'收益','#207358')+chart(rs.map(m=>[m.value,Math.abs(byId[m.case_id].max_drawdown_pct)]),'最大回撤（越小越好）','#b26734')+'</div>';
}
function pair(){const rs=DATA.members.filter(m=>m.group==='pair'&&m.pair===$('pair').value),xs=[...new Set(rs.map(r=>r.x))].sort((a,b)=>a-b),ys=[...new Set(rs.map(r=>r.y))].sort((a,b)=>a-b);
 $('heatmap').innerHTML=table(['行值 / 列值',...ys],xs.map(x=>[x,...ys.map(y=>{let m=rs.find(z=>z.x===x&&z.y===y),r=byId[m.case_id];return btn(r.case_id,(m.case_id==='B'?'V3 · ':'')+num(r.return_pct)+'% / '+num(Math.abs(r.max_drawdown_pct))+'%');})]));
}
function list(){let group=$('group').value,ids=group==='all'?DATA.rows.map(r=>r.case_id):['B',...DATA.members.filter(m=>m.group===group).map(m=>m.case_id)];let rs=[...new Set(ids)].map(id=>byId[id]);const q=$('search').value.toLowerCase();rs=rs.filter(r=>(r.case_id+' '+r.label).toLowerCase().includes(q));
 if($('sort').value==='return')rs.sort((a,b)=>b.return_pct-a.return_pct);if($('sort').value==='drawdown')rs.sort((a,b)=>Math.abs(a.max_drawdown_pct)-Math.abs(b.max_drawdown_pct));
 $('count').textContent=`当前显示 ${rs.length} 个不同配置；全部共121个。`;$('resultTable').innerHTML=table(headers,rs.map(r=>rowValues(r)));
}
function detail(){const id=$('case').value,r=byId[id],p=DATA.paths[id],cfg=DATA.configs[id];
 $('caseSummary').textContent=`${r.label}：收益 ${num(r.return_pct)}%，回撤 ${num(Math.abs(r.max_drawdown_pct))}%，${r.trades}笔；同入场${r.same_entries}笔，错失基线${r.missed_baseline_entries}笔，新增${r.new_entries}笔。`;
 const keys=Object.keys(DATA.grid);let changed=Object.keys(cfg).filter(k=>cfg[k]!==DATA.baseConfig[k]&&!keys.includes(k));
 $('config').innerHTML=table(['参数','本方案','V3'],[...keys,...changed].map(k=>[esc(DATA.grid[k]?.[0]||k),esc(String(cfg[k])),esc(String(DATA.baseConfig[k]))]));
 $('equityChart').innerHTML=chart(p.curve.map(x=>[x.timestamp.slice(0,10),x.equity]),'账户权益 · 初始10,000','#207358',false);
 $('periods').innerHTML=table(['连续账户区间','区间收益','区间回撤'],DATA.periods.filter(x=>x.case_id===id).map(x=>[x.period,sign(x.return_pct),pct(Math.abs(x.max_drawdown_pct))]));
 $('trades').innerHTML=table(['编号','入场 UTC','方向','退出 UTC','入价','出价','单笔收益','原因','收紧次数','末尾倍数'],p.trades.map(t=>[t.trade_id,t.entry_time.slice(0,16),t.side===1?'多':'空',t.exit_time.slice(0,16),num(t.entry_price,4),num(t.exit_price,4),sign(t.return_on_entry_equity*100),t.exit_reason==='sample_end'?'样本末估值':t.exit_reason.startsWith('stop_')?'移动止损':'空单提前退出',t.tightening_days,num(t.stop_mult)]));
 $('tradePairs').innerHTML=table(['入场 UTC','方向','关系','V3收益','本方案收益','V3退出','本方案退出'],DATA.pairs.filter(x=>x.case_id===id).map(x=>[x.entry_time.slice(0,16),x.side===1?'多':'空',x.relationship==='same'?'同入场':x.relationship==='missed'?'错失基线':'新增',sign(x.baseline_return_pct)+(x.baseline_terminal?'（末估）':''),sign(x.new_return_pct)+(x.new_terminal?'（末估）':''),x.baseline_exit?.slice(0,16)||'—',x.new_exit?.slice(0,16)||'—']));
 $('links').innerHTML=`<a href="../accounts/${id}/trades.csv">本方案逐笔记录</a> · <a href="../accounts/${id}/stops.csv">每日止损明细</a> · <a href="../accounts/${id}/entry_events.csv">入场及过滤记录</a>`;
}
$('parameter').innerHTML=options(Object.fromEntries(Object.entries(DATA.grid).map(([k,v])=>[k,v[0]])));$('parameter').value='ma_period';$('parameter').oninput=local;
$('pair').innerHTML=options(Object.fromEntries([...new Set(DATA.members.filter(x=>x.group==='pair').map(x=>x.pair))].map(k=>[k,k.split('__').map(x=>DATA.grid[x][0]).join(' × ')])));$('pair').oninput=pair;
$('case').innerHTML=options(Object.fromEntries(DATA.rows.map(r=>[r.case_id,r.case_id+' · '+r.label])));$('case').value='B';$('case').oninput=detail;
for(const id of ['group','sort','search'])$(id).oninput=list;
const j=DATA.joint;$('jointSummary').innerHTML=`<p>${j.profitable}/${j.n}盈利；收益 ${sign(j.return_min)} 至 ${sign(j.return_max)}，中位 ${sign(j.return_median)}；回撤中位 ${pct(j.drawdown_median)}、最大 ${pct(j.drawdown_max)}；${j.wealth_75pct_count}/32达到基线75%的期末资产。</p><p>联合组全部同时离开基线，均线只取6或8。这个结果不能归因于每个参数都脆弱，也不是2048个角点的穷举。</p>`;
local();pair();list();detail();
'''

if __name__=='__main__':main()
