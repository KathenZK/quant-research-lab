"""Paired descriptive analysis; no strategy selection and no new backtests."""
from pathlib import Path
import sys,json,os,html
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parent))
import validate_fixed_atr_20260924_r3 as v
from report_v3_parameters_20260924 import records,mdtable,fmt
from build_ma30_report_20260911 import STYLE,COMMON_JS,COIN_JS
from revise_v3_stoplines_20260913 import CSS,CHART_BODY,DETAIL_COLUMNS
from report_v3_no_extra_warmup_20260913 import SETUP_JS,ENDING_JS,packed,crosses
R,X,P,ROOT,BASE,MARKET=v.R,v.X,v.P,v.ROOT,v.BASE,v.MARKET

def summary(d,label):
 n=len(d);good=d.dropna(subset=['D_return_pct','F_return_pct'])
 return {'sample':label,'count':n,'valid_pairs':len(good),'undefined_pairs':n-len(good),
  'improved':int(good.delta_return_pp.gt(1e-8).sum()),'worsened':int(good.delta_return_pp.lt(-1e-8).sum()),'unchanged':int(good.delta_return_pp.abs().le(1e-8).sum()),
  'improved_pct':100*good.delta_return_pp.gt(1e-8).sum()/n,
  **{f'{a}_profitable':int(good[f'{a}_return_pct'].gt(0).sum()) for a in ['D','F']},
  **{f'{a}_median_return_pct':float(good[f'{a}_return_pct'].median()) for a in ['D','F']},
  **{f'{a}_median_drawdown_pct':float(good[f'{a}_max_drawdown_pct'].abs().median()) for a in ['D','F']},
  'median_delta_return_pp':float(good.delta_return_pp.median()),'median_delta_drawdown_pp':float(good.delta_drawdown_pp.median())}

def analyze():
 assert v.read_result(R/'accounts/original/F')[0]['trades']==18
 for path in [R/'hype_complete.json',R/'audit_r2.json',X/'cross_complete.json',X/'audit_r2.json']:assert json.loads(path.read_text())['complete']
 h=pd.read_csv(R/'comparison.csv');c=pd.read_csv(X/'comparison.csv');p=pd.read_csv(X/'periods.csv');tp=pd.read_csv(X/'trade_pairs.csv')
 longest=c.sort_values(['slug','days','D_start'],ascending=[True,False,True]).drop_duplicates('slug');assert len(longest)==649
 longest.to_csv(X/'longest_per_coin.csv',index=False)
 pp=p[p.arm.eq('D')].merge(p[p.arm.eq('F')],on=['run_key','slug','block'],suffixes=('_D','_F'),validate='one_to_one')
 for arm in ['D','F']:
  for k in ['return_pct','max_drawdown_pct']:pp[f'{arm}_{k}']=pp[f'{k}_{arm}']
 pp['delta_return_pp']=pp.F_return_pct-pp.D_return_pct;pp['delta_drawdown_pp']=pp.F_max_drawdown_pct.abs()-pp.D_max_drawdown_pct.abs()
 pp.to_csv(X/'paired_periods.csv',index=False)
 sums=[summary(longest,'每币最长连续段'),summary(c,'全部连续段')]
 for block,g in pp[pp.status_D.eq('COMPLETE')&pp.status_F.eq('COMPLETE')].groupby('block'):
  assert not g.slug.duplicated().any();sums.append(summary(g,block))
 pd.DataFrame(sums).to_csv(X/'summary.csv',index=False)
 memberships=pd.DataFrame(json.loads((R/'started.json').read_text())['HYPE_neighbor_memberships']);neighbors=memberships.merge(h,on='case_id');neighbors.to_csv(R/'neighborhoods.csv',index=False)
 ns=[]
 grid=json.loads((P/'started.json').read_text())['grid']
 for key,g in neighbors.groupby('parameter',sort=False):
  off=g[g.case_id.ne('B')];ns.append({'parameter':key,'label':grid[key][0],'values':g.sort_values('value').value.tolist(),'D':g.sort_values('value').D_return_pct.tolist(),'F':g.sort_values('value').F_return_pct.tolist(),'improved_neighbors':int(off.delta_return_pp.gt(1e-8).sum()),'worse_neighbors':int(off.delta_return_pp.lt(-1e-8).sum()),'F_min':off.F_return_pct.min(),'F_max_drawdown':off.F_max_drawdown_pct.abs().max()})
 pd.DataFrame(ns).to_csv(R/'neighborhood_summary.csv',index=False)
 loo=[]
 for row in h[h.case_id.isin(['B','original'])].itertuples():
  D=v.table(ROOT/row.D_path/'trades.csv');F=v.table(ROOT/row.F_path/'trades.csv')
  pairs=D.merge(F,on=['entry_time','side'],suffixes=('_D','_F'),validate='one_to_one');assert len(pairs)==len(D)==len(F)
  for i,t in pairs.iterrows():
   other=pairs.drop(index=i);a=((1+other.return_on_entry_equity_D).prod()-1)*100;b=((1+other.return_on_entry_equity_F).prod()-1)*100
   loo.append({'case_id':row.case_id,'removed_entry':str(t.entry_time),'side':t.side,'D_remaining_return_pct':a,'F_remaining_return_pct':b,'delta_pp':b-a})
 pd.DataFrame(loo).to_csv(R/'leave_one_out.csv',index=False)
 # Matched-entry outcomes across actual accounts; no fixed-entry causal interpretation here.
 trade_sums=[]
 for name,keys in [('全部947段',set(c.run_key)),('每币最长649段',set(longest.run_key))]:
  z=tp[tp.run_key.isin(keys)];same=z[z.relationship.eq('same')];win=same[same.D_return_pct>0];loss=same[same.D_return_pct<0]
  trade_sums.append({'sample':name,'original_trades':int(z.relationship.ne('new').sum()),'same_entries':len(same),'missed':int(z.relationship.eq('missed').sum()),'new':int(z.relationship.eq('new').sum()),'same_better':int(same.delta_pp.gt(1e-8).sum()),'same_worse':int(same.delta_pp.lt(-1e-8).sum()),'same_equal':int(same.delta_pp.abs().le(1e-8).sum()),'original_same_winners':len(win),'winners_to_loss':int(win.F_return_pct.lt(0).sum()),'original_same_losers':len(loss),'losers_improved':int(loss.delta_pp.gt(1e-8).sum()),'losers_worsened':int(loss.delta_pp.lt(-1e-8).sum()),'missed_winners':int((z.relationship.eq('missed')&z.D_return_pct.gt(0)).sum()),'censored_pairs':int((z.D_terminal|z.F_terminal).sum()),'top5_retention_equal_coin_median':float(c[c.run_key.isin(keys)].top5_retention_pct.median()),'natural_same_better':int(same[~same.D_terminal&~same.F_terminal].delta_pp.gt(1e-8).sum()),'natural_same_worse':int(same[~same.D_terminal&~same.F_terminal].delta_pp.lt(-1e-8).sum())})
 pd.DataFrame(trade_sums).to_csv(X/'trade_summary.csv',index=False)
 sides=[]
 for side,label in [(1,'多'),(-1,'空')]:
  a=tp[tp.relationship.eq('same')&tp.side.eq(side)];sides.append({'side':label,'same_entries':len(a),'D_sum_unit_return_pct':a.D_return_pct.sum(),'F_sum_unit_return_pct':a.F_return_pct.sum(),'median_delta_pp':a.delta_pp.median(),'improved':int(a.delta_pp.gt(1e-8).sum()),'worsened':int(a.delta_pp.lt(-1e-8).sum())})
 pd.DataFrame(sides).to_csv(X/'matched_sides.csv',index=False)
 gate={'HYPE_majority_45':bool(h[h.window.eq('common')].delta_return_pp.gt(1e-8).sum()>22.5),'HYPE_not_single_trade_dependent':bool(min(x['delta_pp'] for x in loo if x['case_id']=='B')>0),'cross_longest_majority_positive_delta_nonworse_dd':bool(sums[0]['improved_pct']>50 and sums[0]['median_delta_return_pp']>0 and sums[0]['median_delta_drawdown_pp']<=0)}
 recent=next(s for s in sums if s['sample']=='phase_2025_2026');gate['cross_recent_majority_positive_delta_nonworse_dd']=bool(recent['improved_pct']>50 and recent['median_delta_return_pp']>0 and recent['median_delta_drawdown_pp']<=0)
 analysis={'decision':'NOT_SUPPORTED_AS_GENERAL_REPLACEMENT','description':'固定ATR不支持普遍替换原V3；正式V3保持不变','gates':gate,'hype_common_improved':int(h[h.window.eq('common')].delta_return_pp.gt(1e-8).sum()),'hype_common_worse':int(h[h.window.eq('common')].delta_return_pp.lt(-1e-8).sum()),'hype_common_median_delta_pp':h[h.window.eq('common')].delta_return_pp.median(),'hype_neighborhoods':ns,'cross_summaries':sums,'cross_trades':trade_sums,'sides':sides,'insolvent_D':int(c.D_bankrupt.sum()),'insolvent_F':int(c.F_bankrupt.sum()),'all_data_previously_seen':True,'complete_funding':False}
 v.write_json(R/'analysis.json',analysis);v.write_json(X/'analysis.json',analysis)
 return h,c,longest,pp,neighbors,pd.DataFrame(sums),tp,analysis

def report(h,c,longest,pp,neighbors,sums,tp,a):
 tab=lambda heads,rows:mdtable(heads,rows)
 get=lambda key:sums.set_index('sample').loc[key]
 text=['# V3固定入场ATR验证：HYPE、邻域与649币对照',
 '**结论：不支持把固定入场ATR作为V3的普遍升级。HYPE原起点收益略降、回撤增加；较晚起点的明显增益几乎依赖一笔多单；跨币和多数年份没有普遍改善。正式V3保持不变。**',
 '[交互结果：参数、币种与逐笔对照](../artifacts/v3_fixed_atr_validation_20260924/html/index.html) · [HYPE全部K线与止损虚线](../artifacts/v3_fixed_atr_validation_20260924/html/coins/HYPE.html) · [事前冻结契约](../specs/v3-fixed-entry-atr-validation-20260924.md)',
 '## 这次究竟改了什么',
 '原V3（D）用每天新算出的ATR移动止损；固定版（F）在开仓时记下前一根已收盘日K的ATR，整笔持仓一直用这个数。下一笔重新记录。MA7继续移动；4日最高/最低价不刷新后，倍数仍每天减0.2至0.5；实际止损仍只能收窄。开仓斜率和空单加速判断继续用当时ATR，并没有一起冻结。',
 '两方案每边手续费0.1%、不利滑点0.04%，约1倍名义金额复利。信号次日开盘执行、小时线判止损。保留空单加速＋RSI6≤30提前止盈、关闭反手、自然指标就绪。复用行情截至2026-09-05 00:00 UTC（最后完整日为9月4日），不是更新到9月24日。未知资金费未计入，因此是扣手续费与滑点的价格诊断。',
 '## HYPE：必须把两个起点分开看',
 tab(['空仓启动 UTC','原V3收益','固定ATR收益','原/固定回撤','原/固定笔数'],[[r.D_start[:10],fmt(r.D_return_pct)+'%',fmt(r.F_return_pct)+'%',fmt(abs(r.D_max_drawdown_pct))+'% / '+fmt(abs(r.F_max_drawdown_pct))+'%',f'{r.D_trades} / {r.F_trades}'] for r in h[h.case_id.isin(['original','B'])].sort_values('D_start').itertuples()]),
 '原起点2025-06-15是当前V3的完整HYPE账户。6月19日是上一轮为ATR18自然就绪而统一的参数比较起点；它不是新预热要求。较晚起点错过6月18日空单，使6月28日多单能够入场。原起点当时仍持空，所以实际接上的多单在7月3日。不能把两组账户混成同一个V3收益。',
 '原起点18笔全部同入场：固定后5笔改善、6笔变差、7笔不变；没有新增或错失入场，没有原赢家转亏，3笔原亏单改善。固定原入场时间、方向、数量与权益的18组独立退出探针得到同样的逐笔结果。原前5赢家收益保留102.28%，仍不足以抵消其他损失。',
 '较晚起点17笔全部同入场：6笔改善、4笔变差、7笔不变。6月28日多单由+1.06%变成+23.10%；将这笔从两边同时剔除，其余16笔的描述性复利为**原V3+457.66%，固定ATR+456.51%**。因此此前+585.08%的显著优势几乎都来自这一笔。逐一剔除仅用于诊断集中度，不是可执行策略。',
 '## 为什么这笔改善了，而其他交易未必',
 '6月28日多单的入场信号ATR为3.4926。之后波动率下降，原V3的ATR跟着下降，止损更靠近MA7；7月8日止损为37.1164并触发，固定版当日仍更宽，躲过回调直到7月17日退出。这里固定ATR赚得更多，恰恰因为允许更宽的回调，不是总能更快止损。',
 '反过来，若开仓时波动较高，之后行情趋稳，固定版可能长时间容忍本来可以缩小的风险。2025-10-15空单原亏3.06%，固定后亏4.90%；2025-12-06空单原赚17.69%，固定后赚16.24%。也有盈利延伸：2026-05-15多单由50.58%升到53.86%。这些是已发生路径的机制解释，不据此追加择时条件。',
 '两账户最后一笔均为2026-08-09多单，在样本末估值结算，单笔52.71%，不是策略自然平仓。原起点剔除这笔后的描述性复利为322.21% / 317.52%；共同起点为269.06% / 348.62%。末尾持仓收益保留单列，不能当已实现退出能力。',
 '## 45组HYPE邻域：多数改善，但没有可靠的普遍优势',
 f"沿用原11个参数各四个非基线邻点，加基线共45组；仅切换是否固定ATR。{a['hype_common_improved']}组收益上升，{a['hype_common_worse']}组下降，配对收益变化中位{a['hype_common_median_delta_pp']:.2f}个百分点。全部固定版仍盈利。它们共享HYPE历史与相似交易，不是45次独立验证。",
 tab(['参数','取值','原V3收益%','固定ATR收益%','四邻点改善数'],[[s['label'],' / '.join(f'{x:g}' for x in s['values']),' / '.join(fmt(x) for x in s['D']),' / '.join(fmt(x) for x in s['F']),str(s['improved_neighbors'])+'/4'] for s in a['hype_neighborhoods']]),
 '更直接的反证：初始倍数1.1、1.3、1.7、1.9四个邻点中，固定ATR全部弱于动态ATR；MA6与MA8也都略弱。固定ATR没有解决MA7收益明显突出的现象，不能将34/45解释成优势已稳定。',
 '## 非HYPE：649币、947连续段',
 '只用冻结分类COIN，排除HYPE和28个UNKNOWN代码。未使用BTC因子；没有把UNKNOWN悄悄认定为美股或币。649币947个指标已就绪的连续段全部保留；每段独立账户，不跨缺口拼接。原动态ATR账户复用原产物并逐文件验指纹，固定ATR新跑947个账户。每币最长段只按天数、再按最早起点选取，与收益无关。',
 tab(['样本','币/段数','固定版改善/变差/不变','配对收益变化中位','配对回撤变化中位','原/固定盈利数量'],[[s['sample'],s['count'],f"{s['improved']} / {s['worsened']} / {s['unchanged']}",fmt(s['median_delta_return_pp'])+' pp',fmt(s['median_delta_drawdown_pp'])+' pp',f"{s['D_profitable']} / {s['F_profitable']}"] for s in a['cross_summaries'] if s['sample'] in ['每币最长连续段','全部连续段','phase_2025_2026']]),
 '回撤变化为正表示恶化。最长段中仅295/649（45.45%）改善；原/固定收益中位为−35.61% / −33.96%，但同币配对变化中位为−0.87个百分点。两组各自中位数之差不等于配对变化中位数，判断改动用后者。最长段起止不同，不把这些收益当成统一时间的投资组合。',
 '完整覆盖2025-01-01至2026-09-05的255币中，仅111币改善（43.53%）；配对收益变化中位−1.50个百分点，回撤变化中位+0.81个百分点。没有达到事前约定的“过半改善且中位回撤不恶化”。',
 '## 不只看最近一段行情',
 tab(['完整时间窗','完整币数/收益可定义','改善数','收益变化中位','回撤变化中位'],[[s['sample'],f"{s['count']} / {s['valid_pairs']}",s['improved'],fmt(s['median_delta_return_pp'])+' pp',fmt(s['median_delta_drawdown_pp'])+' pp'] for s in a['cross_summaries'] if s['sample'].startswith(('year_','cycle_','calendar_'))]),
 '按连续账户权益在自然年边界切分，跨年持仓继承，不按年重新开仓。至少30币完整覆盖的年份中，2021、2022、2025、2026的收益配对中位为负；2023只有小幅正向。2026截至9月4日，不是完整自然年。2026有467币完整行情覆盖，其中3币在期初已经破产，收益百分比无定义，单列而不按0填补；其失败在全段统计中完整保留。',
 '严格完整覆盖2020—2024五年的只有BTC、ETH两个币，不能证明全市场完整牛熊适配。2024完整年也只有5币：冻结输入的连续性边界导致很多旧段无法穿过该年。这一覆盖不足不能靠拼接缺口或缩短窗口掩盖。',
 '## 少亏与多赚：交易层面的代价',
 tab(['样本','同入场','原亏单改善/恶化','原赢家转亏','原赢家错失','新增/错失入场','前5赢家保留中位'],[[s['sample'],s['same_entries'],f"{s['losers_improved']} / {s['losers_worsened']}",s['winners_to_loss'],s['missed_winners'],f"{s['new']} / {s['missed']}",fmt(s['top5_retention_equal_coin_median'])+'%'] for s in a['cross_trades']]),
 '跨币逐笔以入场时间＋方向配对、比较每笔入场权益收益，不能把不同仓位的现金利润直接相减。前5赢家按原账户挑选，若错失记0；可超过100%。新增与错失说明退出也改变了后续持仓占用，所以跨币账户配对不能冒充固定入场的纯退出因果效果。所有样本末结算、原亏单、错失赢家均可在HTML里查到。',
 tab(['方向（全部947段同入场）','配对数','改善/恶化','单笔变化中位'],[[s['side'],s['same_entries'],f"{s['improved']} / {s['worsened']}",fmt(s['median_delta_pp'])+' pp'] for s in a['sides']]),
 '## 证据边界与核验',
 '两方案均有6个全段账户权益耗尽：ARIA、H、JELLYJELLY、NAORIS、TAC、TRUTH。均未剔除。冻结模型没有强平与保证金执行层，某些极端空单可得到低于−100%的账户收益，这不是可真实执行的永续合约最终净收益。它揭示风险尺度并未解决极端行情风险；这里不借机改变仓位规则。当前身份分类不是历史时点可交易名单，资金费、流动性与强平证据也不完整。',
 'HYPE46个新完整账户与36个固定入场单笔探针、非HYPE947个新账户通过独立成交、止损路径、最早退出、成本和逐时权益复核。非HYPE共21,460笔、235,118条止损、25,706,840个权益节点。7项针对性测试通过。原动态账户沿用旧审计并核验内容指纹，没有重复全市场回测。',
 '本轮复核器修正并留档三类边界：CSV空值表示、滚动均线恰好相等时的浮点算序、亏光账户之后不再开仓；另修正固定入场探针午夜退出时的止损日期校验。原引擎、数据、参数和已保存账户经济结果均未修改；原失败记录及各修订脚本保留。HTML通过离线交互与虚线记录核验；实际浏览器布局验证状态以交付记录为准。',
 '**处理决定：保留原V3，固定ATR归为已验证但不支持普遍替换的结构对照，不登记V4、不按币挑参数。** 这次排除了“高收益数字代表广泛改善”的解释；不需要为了挽救固定ATR继续叠条件。所有历史已被研究过，跨币与邻域是稳健性诊断，不是独立未见数据的样本外证明。',
 '[全部HYPE对照](../artifacts/v3_fixed_atr_validation_20260924/comparison.csv) · [18笔固定入场](../artifacts/v3_fixed_atr_validation_20260924/fixed_entry_pairs.csv) · [逐一剔除诊断](../artifacts/v3_fixed_atr_validation_20260924/leave_one_out.csv) · [跨币汇总](../../../asset-portfolios/1d-ma7-cross-atr-generalization/artifacts/v3_fixed_atr_validation_20260924/summary.csv) · [跨币复核](../../../asset-portfolios/1d-ma7-cross-atr-generalization/artifacts/v3_fixed_atr_validation_20260924/audit_r2.json)']
 (BASE/'diagnostics/v3-fixed-atr-validation-results-20260924.md').write_text('\n\n'.join(text)+'\n')

def page(title,body,data,script):
 payload=json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('</','<\\/')
 return '<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+STYLE+CSS+'</style><main><h1>'+html.escape(title)+'</h1>'+body+'</main><script>const DATA='+payload+';\n'+COMMON_JS+script+'</script></html>'

def main():
 args=analyze();report(*args)
 v.write_json(R/'report_analysis_complete.json',{'complete':True,'no_new_backtests':True})
 print(json.dumps({k:z for k,z in args[-1].items() if k not in ['hype_neighborhoods','cross_summaries']},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
