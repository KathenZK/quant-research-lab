"""Aggregate predeclared version pairs; never rank or choose parameter variants."""
from pathlib import Path
import json
import pandas as pd

ROOT=Path(__file__).resolve().parents[4]
FAMILY=Path(__file__).resolve().parents[1]
A=FAMILY/'artifacts/iteration_comparison_20260911'
SCENARIOS={'unit':'equal_1x_base','fixed1x':'equal_1x_base','fixed_1x':'equal_1x_base',
 'original_sizing':'original_size_base','original_size':'original_size_base',
 'unit_slip8bps':'equal_1x_stress','fixed1x_slip8bps':'equal_1x_stress','fixed_1x_slippage_8bps':'equal_1x_stress',
 'long_fixed1x':'equal_1x_base'}
NAMES={'EMA-X':'HYPE 15m EMA-X','EMA-TB':'HYPE 15m EMA-TB','MII':'HYPE 15m MII','ENS':'HYPE 15m TB+MII组合',
 'HYPE-CC':'HYPE 15m 10/8反转','HYPE_15m_MMTF':'HYPE 15m MMTF','HYPE_1h_MMTF':'HYPE 1h MMTF',
 'HYPE_30m_Keltner':'HYPE 30m Keltner',**{f'{a}_1h_AR':f'{a} 1h AR' for a in ['BTC','ETH','SOL','BNB','TRX','HYPE']}}

def read(p):return json.loads(p.read_text())
def save(p,obj):p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=str)+'\n')
def pct(x):return f'{100*x:+.2f}%'
def dd(x):return f'{100*abs(x):.2f}%'
def resolve(s):
 p=Path(s)
 return p if p.is_absolute() else ROOT/p

def normal_rows():
 out=[]
 for group in ('ema','ar_mmtf','cc'):
  raw=read(A/group/'results.json')
  if isinstance(raw,dict):raw=raw.get('rows',raw.get('results'))
  assert isinstance(raw,list),group
  for r in raw:
   if group=='cc' and r['funding_mode']!='observed_funding_estimate':continue
   if group=='cc':
    sibling=next(x for x in raw if x['case_id']==r['case_id'] and x['funding_mode']=='funding_excluded')
    ret=r['return_pct']/100;price=sibling['return_pct']/100
   elif 'return_pct' in r:
    ret=r['return_pct']/100;price=r['return_excluding_funding_pct']/100
   else:ret=r['return_estimated_funding'];price=r['return_ex_funding']
   draw=-abs(r['max_drawdown_pct']/100) if 'max_drawdown_pct' in r else -abs(r['max_drawdown'])
   ep=r.get('equity_path',r.get('equity_file'))
   tp=r.get('trades_path',r.get('trades_file'))
   assert ep and tp,(group,r)
   row={'group':group,'family':r['family'],'name':NAMES.get(r['family'],r['family']),
    'version':r['version'],'role':'final' if r['role']=='latest' else r['role'],'scenario':SCENARIOS[r['scenario']],
    'window':r.get('window','common'),'start':r['start'],'end':r.get('end',r.get('end_exclusive')),
    'return':ret,'return_ex_funding':price,'drawdown':draw,'trades':r['trades'],
    'terminal_closes':r.get('terminal_closes',r.get('terminal_trades',0)),
    'equity_path':str(resolve(ep)),'trades_path':str(resolve(tp)),
    'monthly_path':str(resolve(r['monthly_path'])) if r.get('monthly_path') else None,
    'source':str((A/group/'results.json').relative_to(ROOT)),
    'funding_limitation':r.get('funding_status',r.get('funding_event_order_limitation','observed settlement estimate; incomplete history'))}
   assert resolve(ep).exists() and resolve(tp).exists(), row
   out.append(row)
 return out

def pairs(rows):
 out=[]
 families=list(dict.fromkeys(r['family'] for r in rows if r['window']=='common'))
 for fam in families:
  rr=[r for r in rows if r['family']==fam and r['window']=='common' and r['scenario']=='equal_1x_base']
  final=[r for r in rr if r['role']=='final']
  if fam=='EMA-TB':early=[r for r in rr if r['version']=='V35']
  else:early=[r for r in rr if r['role'].startswith('early')]
  assert len(final)==len(early)==1,(fam,[(r['version'],r['role']) for r in rr])
  e,f=early[0],final[0]
  out.append({'family':fam,'name':e['name'],'early_version':e['version'],'final_version':f['version'],
   'early_return':e['return'],'final_return':f['return'],'increment':f['return']-e['return'],
   'early_return_ex_funding':e['return_ex_funding'],'final_return_ex_funding':f['return_ex_funding'],
   'increment_ex_funding':f['return_ex_funding']-e['return_ex_funding'],
   'early_drawdown':e['drawdown'],'final_drawdown':f['drawdown'],
   'early_trades':e['trades'],'final_trades':f['trades'],
   'primary_is_earliest_simple_rule':fam not in ('EMA-X','EMA-TB','ENS','HYPE-CC')})
 return out

def main():
 rows=normal_rows();ps=pairs(rows)
 assert len(ps)==14,len(ps)
 save(A/'all_results.json',rows);pd.DataFrame(rows).to_csv(A/'all_results.csv',index=False)
 save(A/'paired_results.json',ps);pd.DataFrame(ps).to_csv(A/'paired_results.csv',index=False)
 higher=sum(p['increment']>1e-9 for p in ps);lower=sum(p['increment']<-1e-9 for p in ps)
 equal=len(ps)-higher-lower;profitable=sum(p['final_return']>0 for p in ps)
 oldpositive=sum(p['early_return']>0 for p in ps)
 family_renames={'HYPE-EMA-X':'EMA-X','HYPE-EMA-TB':'EMA-TB','HYPE-15M-MII':'MII','HYPE-15M-TB-MII-ENS':'ENS',
  **{f'{a}-1H-AR':f'{a}_1h_AR' for a in ['BTC','ETH','SOL','BNB','TRX','HYPE']},
  'HYPE-15M-MMTF':'HYPE_15m_MMTF','HYPE-1H-MMTF':'HYPE_1h_MMTF','HYPE-30M-Keltner':'HYPE_30m_Keltner'}
 scope=read(A/'scope.json')
 for r in scope['rows']:
  if r['status']=='PLANNED_VERSION_COMPARISON':
   fid=family_renames.get(r['family'],r['family'])
   matched=[p for p in ps if p['family']==fid]
   assert len(matched)==1,(r,fid)
   r['status']='REPLAYED_VERSION_COMPARISON';r['pair']=matched[0]
 save(A/'coverage_final.json',scope)
 lines=['# 早期版本与最终版本：同一段后续行情的比较（2026-09-11）','',
  f'实际完成14个家族的版本对照，含预先并列里程碑和仓位/成本情景共{len(rows)}条结果。统一1倍仓位后，最终版收益高于早期对照的有{higher}个，低于早期的有{lower}个，相同的有{equal}个；最终版盈利{profitable}个，早期对照盈利{oldpositive}个。收益提高也可能只是少亏，不能与盈利混为一谈。',
  '', '这次结果回答哪些修改在后续行情有帮助，不能直接推出“版本越多越差”，也没有估计过拟合概率。各家族共享行情，不能当作14次独立统计实验。',
  '', '**共同窗口：2026-07-23 00:00 UTC至2026-09-05 15:00 UTC，共44天15小时。** 初始现金空仓，每次开仓实际成交名义为当时权益的1倍，持仓数量固定。手续费每次0.1%，基础滑点每次0.04%；压力滑点每次0.08%。原规则明确的额外入场等待保留。表中收益加入已有资金费事件的估算，未含资金费结果也全部保存；结算日历、部分标记价格及盘中退出时刻不完整。',
  '', '## 14个家族的主对照','',
  '| 家族 | 早期→最终 | 早期收益 | 最终收益 | 收益差 | 早期回撤 | 最终回撤 | 交易数早→晚 |',
  '|---|---|---:|---:|---:|---:|---:|---:|']
 for p in ps:
  lines.append(f"|{p['name']}|{p['early_version']}→{p['final_version']}|{pct(p['early_return'])}|{pct(p['final_return'])}|{100*p['increment']:+.2f}个百分点|{dd(p['early_drawdown'])}|{dd(p['final_drawdown'])}|{p['early_trades']}→{p['final_trades']}|")
 lines+=['','早期对照不都等于未经调参的原始规则：EMA-X V1是按早期代码恢复的裸交叉基线，完整独立V1规格缺失，不能证明当年唯一选定的退出规则；EMA-TB主比较从可执行代码完整的V35开始，最早V2P另列恢复诊断；TB+MII早期组合是明确冻结的诊断方案，没有伪造登记V1；CC最早完整规格为V10。MMTF V2只是V1清理等价版，不重复计作新策略。1倍名义仓位也不等于各版单笔止损风险相同。',
  '', '回撤按各根K收盘账户权益计算；例如BTC最终版仅1笔交易，表中0.00%不表示盘中没有浮亏。各组资金费估算也并非完全相同：AR/MMTF用固定入场名义并排除盘中退出所在K的事件，EMA用结算K开盘价，CC优先使用保留的结算标记价格。本报告比较每个家族内的前后版本，不按估计收益给跨家族优劣排名；完全排除资金费后，14组收益变化方向均不改变。',
  '', '## 保留原仓位后的区别','',
  '| 家族 | 早期原仓位收益 | 最终原仓位收益 | 最终统一1倍收益 |',
  '|---|---:|---:|---:|']
 for p in ps:
  e=next(r for r in rows if r['family']==p['family'] and r['version']==p['early_version'] and r['scenario']=='original_size_base' and r['window']=='common')
  f=next(r for r in rows if r['family']==p['family'] and r['version']==p['final_version'] and r['scenario']=='original_size_base' and r['window']=='common')
  lines.append(f"|{p['name']}|{pct(e['return'])}|{pct(f['return'])}|{pct(p['final_return'])}|")
 lines+=['','这里保留原版入场仓位公式，但同样使用固定实际数量和统一成本；不是沿用旧引擎逐根隐含加杠杆再平衡的复利数字。改变持仓数量和改变交易规则的影响分开看。',
  '', '## 重点：15分钟10根中至少8根同色反转','',
  '这就是HYPE-CC。最近10根已收盘K中至少8根阳线做空，至少8根阴线做多；不要求8根连续，十字星不计。只在信号刚出现时考虑入场，已有仓位不加仓或反手。早期版已有趋势禁入、冷却、ATR止盈止损等规则，并非裸10/8信号。',
  '', '| 版本 | 主窗口1倍收益 | 主窗口回撤 | 交易数 | 滑点加倍后 | 6月8日起较长窗口1倍收益 |',
  '|---|---:|---:|---:|---:|---:|']
 for v in ['V10','V13','V18','V21','V35']:
  c=next(r for r in rows if r['family']=='HYPE-CC' and r['version']==v and r['window']=='common' and r['scenario']=='equal_1x_base')
  s=next(r for r in rows if r['family']=='HYPE-CC' and r['version']==v and r['window']=='common' and r['scenario']=='equal_1x_stress')
  l=next(r for r in rows if r['family']=='HYPE-CC' and r['version']==v and r['window']=='long')
  lines.append(f"|{v}|{pct(c['return'])}|{dd(c['drawdown'])}|{c['trades']}|{pct(s['return'])}|{pct(l['return'])}|")
 lines+=['','较长窗口从2026-06-08 03:45 UTC开始，也是回放前指定。五版在该较长窗口均亏损：这不能由挑回某个早期版本解决。主窗口中V18/V21比V10/V13更好，但V35没有超过V21；不能把所有迭代一概说成无效，也不能从这里重新挑一个历史赢家就宣称已经验证。',
  '', '滑点测试中，CC和AR/MMTF按改变后的成交价格重新判断保护单和后续交易，EMA在固定参考交易路径上重新计价。因此各组的压力测试实现不同。CC V10提高滑点后反而少亏，是触发和后续入场路径改变，不能解释为交易成本越高越有利；组内早晚版本使用相同方法。',
  '', 'V21增加开仓K之后前3根全部反向时提前退出，V35又增加前12根中至少9根同向/反向提前退出，并改变止盈和原仓位。这次严格排除实际成交K、按下一可执行open退出；原文和旧代码在这些时点有冲突，因此不把本次CC结果写成上一轮旧适配器逐笔复现。详细参数、费用、资金费、方向与原仓位结果见[CC专题](../artifacts/iteration_comparison_20260911/cc/report.md)。',
  '', '## 需要更正的旧结果与本轮限制','',
  '- 上一轮HYPE15m MMTF的RVOL错误用了48根，原规格和引擎要求96根。本次原窗口、原3倍仓位、原模型单独重算，原报告−14.22%更正为−14.15%，仍为10笔；差约0.066个百分点，不改变亏损结论。本轮统一仓位主表采用正确96根和共同账户模型。详见[前后复现记录](../artifacts/iteration_comparison_20260911/ar_mmtf/legacy_rvol_correction/comparison.json)。',
  '- 本轮旧版本使用共同可执行账户修正：AR被占仓丢弃信号不产生虚拟冷却，EMA-X退出损益放到实际下一open时点；EMA-TB V2P文档含当前K定义盘中保护线问题，修正后只能作为恢复诊断。实现修复不能归因给版本参数。',
  '- Keltner原规格从完整1分钟数据聚合，本轮从完整15分钟数据聚合30分钟和1小时。前后版使用相同输入，适合本次版本对照；未证明与原冻结1分钟聚合数据逐值相同。',
  '- MDTP V1和六币1h组合V1没有更早登记版本可比；AS6S V1的五条15m腿完整配置已随冻结JSON删除，Git中没有该文件历史。V6虽已恢复，不能把V6参数塞回V1。三者不记成零收益或迭代失败。',
  '- 昨日已查看过本次后段行情。本轮没有新搜索，但这是已知历史上的对照，不是新的盲测。少量交易和一个多月的样本仍不能证明未来稳定盈利。',
  '', '## 对过拟合问题的判断',
  '', '本次发现部分后期改动没有经受住这段后续行情：EMA-X的增强版落后于恢复的裸交叉基线，SOL最终版过滤到完全不交易，CC V35明显落后于中期V21。但MII、HYPE 1h MMTF和CC较早的几次迭代有改善，不能将所有失败都归结为版本多。EMA-X最终版只有3笔、SOL早版只有4笔，差异很容易受少数行情影响。',
  '', 'CC尤其值得继续检查V21到V35增加的提前退出和止盈改动。不过较长窗口所有版本都亏，说明最近一个多月的盈利没有覆盖整个落档后期间。规则是否追着旧行情调整、是否有特定行情失效、成本是否吞掉优势，需要分别判断；本次没有逐项拆除改动，不能给某条规则单独定罪。当前结果支持“有些增强没有带来稳定好处”，尚不足以证明过拟合是唯一或主要原因。',
  '', '若继续验证，先固定EMA-X简单基线、MII最终版及CC V21/V35这几条对照，记录之后真正没看过的数据；不要根据这次排名再换参数。它们是进一步核对的对象，本轮没有任何一条被证明能稳定盈利。',
  '', '## 图表与复核材料',
  '', '![14组前后版本收益](../artifacts/iteration_comparison_20260911/paired_returns.png)',
  '', '![CC两个固定窗口](../artifacts/iteration_comparison_20260911/cc_versions_windows.png)',
  '', '[全部情景数据](../artifacts/iteration_comparison_20260911/all_results.csv) · [14个固定版本对照](../artifacts/iteration_comparison_20260911/paired_results.csv) · [输入验证](../artifacts/iteration_comparison_20260911/inputs/manifest.json) · [预定比较规则](../specs/iteration-comparison-20260911.md) · [覆盖与缺件](../artifacts/iteration_comparison_20260911/coverage_final.json)',
  '', '[EMA独立复核](../artifacts/iteration_comparison_20260911/acceptance_ema_independent.json) · [AR/MMTF独立复核](../artifacts/iteration_comparison_20260911/acceptance_ar_mmtf_independent.json) · [CC独立复核](../artifacts/iteration_comparison_20260911/acceptance_cc_independent.json) · [汇总复核](../artifacts/iteration_comparison_20260911/acceptance_aggregate.json)']
 (FAMILY/'diagnostics/iteration-comparison-20260911.md').write_text('\n'.join(lines)+'\n')
 save(A/'aggregate_counts.json',{'families':len(ps),'result_rows':len(rows),'final_higher':higher,'final_lower':lower,'equal':equal,'final_positive':profitable,'early_positive':oldpositive,
  'funding_changes_increment_sign':[p['family'] for p in ps if (p['increment']>0)!=(p['increment_ex_funding']>0)]})
 print(json.dumps(read(A/'aggregate_counts.json'),ensure_ascii=False))

if __name__=='__main__':main()
