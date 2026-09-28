"""Render a self-contained full-market research report from pinned replay artifacts."""
from pathlib import Path
import gzip,hashlib,json,math
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/full-market-20260908'

def read_pinned(path,manifest):
 info=manifest['files'][str(path.relative_to(OUT))]
 assert hashlib.sha256(path.read_bytes()).hexdigest()==info['sha256'],str(path)
 return path

def write_json(path,x):path.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def pct(x):return 'NA' if x is None or pd.isna(x) else f'{x:+.2f}%'
def fmt(x):return 'NA' if x is None or pd.isna(x) else f'{x:.2f}'
def mdtable(headers,rows):return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+['| '+' | '.join(str(x) for x in row)+' |' for row in rows])

def build():
 manifest=json.loads((OUT/'run-output-manifest.json').read_text())
 a=json.loads(read_pinned(OUT/'analysis.json',manifest).read_text());m=pd.read_csv(read_pinned(OUT/'main-symbol-results.csv',manifest));t=pd.read_csv(read_pinned(OUT/'full-history-trades.csv.gz',manifest))
 fixed=m[m.asset_class.eq('COIN')&m.cohort.eq('complete_639_days')]
 curves={};main_trades=[];dashboard_rows=[]
 for row in m.to_dict('records'):
  coin=row['coin'];path=read_pinned(OUT/'main-replays'/f'{coin}.json.gz',manifest)
  with gzip.open(path,'rt') as f:payload=json.load(f)
  bars=payload['bars'];row['buyhold_log_growth_pct']=math.log(bars[-1]['close']/bars[0]['close'])*100;dashboard_rows.append(row);r=payload['runs']['causal_binance_cost'];assert len(r['nav'])==row['n_bars'];assert math.isclose((r['nav'][-1]-1)*100,row['cost_return_pct'],abs_tol=1e-8)
  curves[coin]={'start':row['start'],'nav':[round(x,8) for x in r['nav']],'bh':[round(b['close']/bars[0]['close'],8) for b in bars],'trades':[{'entry':x['entry_date'],'exit':x['exit_date'],'return':x['ret_pct'],'reason':x['reason']} for x in r['trades']]}
  for trade in r['trades']:
   entry=next(e for e in r['events'] if e['action']=='entry' and e['i']==trade['entry_idx']);raw=trade['entry_price']/(1+.0004)
   close_prices=[trade['entry_price']]+[b['close'] for b in bars[trade['entry_idx']:trade['exit_idx']]]
   if trade['reason']=='end_of_test':close_prices.append(trade['exit_price'])
   mfe=(max(close_prices)/trade['entry_price']-1)*100
   main_trades.append({'coin':coin,'asset_class':row['asset_class'],'cohort':row['cohort'],'economic_flag':row['economic_flag'],**trade,'initial_stop_distance_pct':(raw-entry['stop'])/raw*100,'close_mfe_pct':mfe})
 mt=pd.DataFrame(main_trades);q=mt[mt.asset_class.eq('COIN')&mt.cohort.eq('complete_639_days')];wins=q[q.ret_pct>0];loss=q[q.ret_pct<0]
 gw=np.log1p(wins.ret_pct/100);gl=np.log1p(loss.ret_pct/100)
 decomposition={'fixed_cohort_trades':len(q),'wins':len(wins),'losses':len(loss),'actual_win_rate_pct':len(wins)/len(q)*100,'mean_win_pct':float(wins.ret_pct.mean()),'mean_loss_pct':float(loss.ret_pct.mean()),'mean_trade_pct':float(q.ret_pct.mean()),'mean_log_trade_pct':float(np.log1p(q.ret_pct/100).mean()*100),'break_even_win_rate_from_mean_log_pct':float(-gl.mean()/(gw.mean()-gl.mean())*100),'median_initial_stop_distance_pct':float(q.initial_stop_distance_pct.median()),'losses_with_prior_positive_close_mfe':int(loss.close_mfe_pct.gt(0).sum()),'losses_with_prior_close_mfe_ge5pct':int(loss.close_mfe_pct.ge(5).sum()),'losses_with_prior_close_mfe_ge10pct':int(loss.close_mfe_pct.ge(10).sum()),'natural_exit_count':int(q.reason.ne('end_of_test').sum()),'terminal_valuations':int(q.reason.eq('end_of_test').sum()),'median_stop_distance_by_reference':{c:float(g.initial_stop_distance_pct.median()) for c,g in mt[mt.coin.isin(['BTC','ETH','SOL','BNB','UNI','ARB','LIT','HYPE'])].groupby('coin')}}
 low=t[t.asset_class.eq('COIN')&t.entry_features_valid&t.natural_exit&t.atr_pct.le(3)&t.entry_date.ge('2020-01-01')]
 decomposition['low_atr_group_symbols']=low.groupby('symbol').ret_pct.agg(['size','mean']).reset_index().rename(columns={'size':'trades','mean':'mean_return_pct'}).to_dict('records')
 decomposition['low_atr_usdc_gold_trades']=int(low.symbol.isin(['USDC/USDT:USDT','PAXG/USDT:USDT','XAUT/USDT:USDT']).sum());decomposition['low_atr_total_trades']=len(low)
 decomposition['reference_compounding']={c:{'mean_arithmetic_trade_pct':float(g.ret_pct.mean()),'mean_log_trade_pct':float(np.log1p(g.ret_pct/100).mean()*100),'compounded_return_pct':float(np.expm1(np.log1p(g.ret_pct/100).sum())*100)} for c,g in mt[mt.coin.isin(['BTC','ETH','SOL','BNB','UNI','ARB','LIT','HYPE'])].groupby('coin')}
 write_json(OUT/'mechanism-decomposition.json',decomposition);mt.to_csv(OUT/'main-window-trades.csv.gz',index=False,compression='gzip')
 coverage=a['coverage'];fstat=next(x for x in a['cohort_statistics'] if x['asset_class']=='COIN' and x['cohort']=='complete_639_days' and not x['exclude_economic_flags'])
 cleanstat=next(x for x in a['cohort_statistics'] if x['asset_class']=='COIN' and x['cohort']=='complete_639_days' and x['exclude_economic_flags'])
 cohorts=[x for x in a['cohort_statistics'] if x['asset_class']=='COIN' and not x['exclude_economic_flags'] and x['cohort']!='ALL_AVAILABLE']
 cn={'complete_639_days':'完整主窗口 639 日','partial_180plus_to_cutoff':'较晚开始，至少 180 日，延续至末端','short_30_179_to_cutoff':'短历史 30–179 日，延续至末端','ended_before_cutoff':'有效历史在末端前已中断'}
 report=f'''# MA7 / ATR14 全市场固定参数迁移：盈亏原因与规律审计

日期：2026-09-08。主题：`MA7-ATR14-Long-Fixed-Parameter-Transfer`。本轮子研究：`MA7-ATR14-Full-Market-Mechanism-Audit-20260908`。结论为 `explore / diagnostic-only / not promoted / not live-ready`。

## 研究结论

**这套参数在全市场不具备普遍盈利能力。** 对时间完全一致的 {len(fixed)} 个 COIN 标的，只有 {fstat['profitable']} 个盈利，盈利占比 {fstat['profitable_share_pct']:.2f}%，收益中位数 {pct(fstat['median_return_pct'])}，最大日收盘回撤的中位数 {fstat['median_drawdown_pct']:.2f}%。

有些币盈利，主要表现为大波段的盈利足够抵消反复止损；亏损币则是赢得少、输得多，固定一倍仓位让高波动币承受更大的实际止损金额。市场阶段、波段收益分布与风险幅度同时影响结果。手续费会削弱收益，但不是主要亏损来源。

**没有发现可直接用于提前选币的稳定规律。** 上一年策略收益与下一年排序的相关性接近零。六个预先固定的入场条件中，趋势、动量、低震荡和高流动性没有给出稳定的跨年优势。低 ATR 仅是有待验证的风险线索，其年度样本都不足，且混有稳定币和黄金代币。

## 全市场范围与数据口径

在本地 `/Users/ZK/OpenCode/quant-strategy-lab` 执行，继续消费已固定的 `binance.v3.research_inputs.v2`，日线数据集为 `binance.perp.ohlcv.1d.from_15m.v2`。历史最大覆盖 2019-09-09 至 2026-09-04（日K标签，UTC）；最后完整日K于 2026-09-05 00:00 UTC 收盘，发布日期不代表行情已更新到 9 月 8 日。

清单 874 个标的中，652 个 COIN 进入主研究；31 个 UNKNOWN 历史代码全部检查、另列敏感性结果；191 个已标为股票、指数、商品或其他非加密类别的合约未混入主样本。COIN 是清单观测分类，包含 USDC、PAXG、XAUT 等代币，不等于所有标的具有相同经济属性。

683 个请求标的全部通过价格输入校验。678 个至少有一段 30 根完整日K可回放；5 个没有足够长的连续段，逐项记录为样本不足。不存在价格读取失败后回退旧数据的情况。

主窗口固定为 **2024-12-05 至 2026-09-04**，与前一轮六币长窗口一致；该窗口有可用段的 629 个标的中，625 个为 COIN，4 个为 UNKNOWN。其余 54 个也检查了全历史，没有偷偷删除：它们可能在主窗口前已结束有效交易，或在该窗口不足 30 根连续日K。

所有历史按有效连续段分开回放；不跨零成交日、数据缺口、已观测的重开边界继承仓位和 ATR。每币主表用其主窗口内最后一个可回放段，**不要求它活到今天**；其他段保留在完整结果中。末日结算只作估值，不证明退市前能按该价格退出。没有完整历史身份/PIT 和资金费率认证，因此不称为全成本净收益或可执行的全市场组合。

## 固定策略

SMA7、Wilder ATR14、1.5 倍 ATR 止损、MA7 斜率大于 0，全部不调参。前一收盘低于 MA7、本日收盘上穿 MA7 才产生信号；至少 15 根连续有效日K。收盘信号后次日开盘入场，使用前一收盘确定的止损；跳空穿越按开盘价退出，入场当天允许止损。只做多，入场名义仓位为本金一倍，不反手、不加仓、不做波动率仓位调整。

每次成交手续费 0.1%，不利滑点 0.04%；另保存零成本与滑点加倍情景。**资金费率未计入。** 每币独立本金一，不把币种平均收益冒充组合收益。回撤按日收盘权益，未估计日内最大回撤。

## 盈利分布：不能把不同历史长度放在一起排名

'''
 report+=mdtable(['样本组','币数','盈利币数','盈利占比','收益中位数','回撤中位数'],[[cn[x['cohort']],x['n'],x['profitable'],f"{x['profitable_share_pct']:.2f}%",pct(x['median_return_pct']),f"{x['median_drawdown_pct']:.2f}%"] for x in cohorts])
 report+=f'''

625 个可用 COIN 主段合计 77 个盈利，占 12.32%，但历史长度不同，这只能描述已观测分布。更可比的完整窗口是 244 个标的、11 个盈利。完整窗口本身仍条件于整个区间连续存在，历史中断的 104 个标的单列，避免将该组误说成无幸存条件的市场总体。

先于收益固定的经济异常提示包括相邻收盘相差超过 4 倍或跌至四分之一以下、日内高低价比超过 10 倍、ATR/价格超过 50%。提示不等于已证明坏数据；原始结果保留，只另做剔除敏感性。完整窗口剔除 3 个提示标的后，剩余 {cleanstat['n']} 个仍只有 {cleanstat['profitable']} 个盈利，中位收益 {pct(cleanstat['median_return_pct'])}。亏损结论没有依赖这三个极端样本。主窗口其他样本的异常提示更多，均在明细中显示；此事后数据筛查不能当作实盘入场过滤器。

## 原因一：弱势市场中，减少跌幅仍不足以赚钱

完整窗口 244 个币中，买入持有的中位收益为 {pct(fstat['median_bh_return_pct'])}。策略有 {fstat['beat_bh_share_pct']:.2f}% 的币跑赢买入持有，但自身中位收益仍为 {pct(fstat['median_return_pct'])}。这说明规避部分下跌与获得绝对盈利是两种不同结果。

其中 229 个币同期买入持有跌幅超过 50%，策略只有 6 个盈利。SMA7 向上穿越会在长期下行中的反弹再次触发，规则又没有更长期弱势禁入或反手模块，因而止损后仍可能继续参与下一次失败反弹。

下表每年都只比较当年完整有效窗口，重新空仓预热。年度样本组成不同，2020 年只有 3 个标的；2026 年为截至 9 月 4 日，不是全年。

'''
 report+=mdtable(['年份','完整窗口币数','策略盈利占比','策略中位收益','买入持有中位收益'],[[str(x['year'])+(' 年内' if x['year']==2026 else ''),x['n'],f"{x['profitable_share_pct']:.2f}%",pct(x['median_return_pct']),pct(x['median_bh_return_pct'])] for x in a['calendar_years'] if not x['exclude_economic_flags']])
 report+='''

2024 年和 2025 年差异很大。但“币价总体上涨”也不是充分条件：2021 年该组买入持有中位数为 +180.66%，策略中位数仍为 -1.84%。还必须在实际开仓区间抓住足够盈利，并承受中间回撤；整体涨幅不能代替交易路径。

## 原因二：一倍仓位固定，单笔风险并不固定

'''
 report+=f'''完整窗口合计 {len(q)} 笔交易，实际胜率 {decomposition['actual_win_rate_pct']:.2f}%，盈利单平均 {pct(decomposition['mean_win_pct'])}，亏损单平均 {pct(decomposition['mean_loss_pct'])}。按这些实际交易的平均盈利/亏损对数收益推算，达到复利盈亏平衡需约 {decomposition['break_even_win_rate_from_mean_log_pct']:.2f}% 胜率，明显高于实际值；这只是盈亏账本恒等式，不是未来胜率预测。

止损初始距离的中位数为本金名义价格的 {decomposition['median_initial_stop_distance_pct']:.2f}%。同样 1.5 倍 ATR，在 BTC 和 ARB 上并不意味着同样的资金风险：实际初始止损距离中位数分别为 {decomposition['median_stop_distance_by_reference']['BTC']:.2f}% 和 {decomposition['median_stop_distance_by_reference']['ARB']:.2f}%。高波动时仓位没有降低，一次亏损更重，之后需要更大上涨才能补回。

下面均为前一轮相同主段，LIT 和 Binance HYPE 的历史更短，不能与六币长窗口直接排名；HYPE 此处是 Binance 结果，不能替换此前 Hyperliquid +469% 的数字。

'''
 refs=m[m.coin.isin(['BTC','ETH','SOL','BNB','UNI','ARB','LIT','HYPE'])].copy();order=['BTC','ETH','SOL','BNB','UNI','ARB','LIT','HYPE'];refs['order']=refs.coin.map({c:i for i,c in enumerate(order)});refs=refs.sort_values('order')
 report+=mdtable(['币','起始日','收益','交易数','胜率','平均盈利单','平均亏损单'],[[x.coin,x.start,pct(x.cost_return_pct),x.n_trades,f'{x.win_rate_pct:.2f}%',pct(x.mean_win_pct),pct(x.mean_loss_pct)] for x in refs.itertuples()])
 report+='''

BTC 的单次亏损较小，少数盈利能覆盖损失；UNI 以较大的盈利单补偿较深亏损。ETH 虽平均盈利单较大，但胜率偏低；SOL 胜率不算最低，亏损幅度却使复利结果转负；ARB 同时面对低胜率和较深亏损。这些是已实现交易的会计分解，不能据此保证币种将来仍保持同样特征。

还存在复利损耗：ETH 这 18 笔交易的算术平均收益约 +0.50%，但实际连续复利为 -10.35%。涨跌幅不能直接相加，较大的亏损需要不对称的涨幅才能补回；用平均盈利单、平均亏损单和胜率作解释时，必须同时核对真实净值乘积。

## 原因三：少数大盈利交易决定结局

'''
 report+=f'''完整窗口的 11 个盈利币，若将各自最好的 3 笔交易收益置为零、其余交易保持原值，**11 个全部转亏**。这三笔占所有正对数收益的比例，中位数为 {fstat['median_winner_top3_share_positive_logs']*100:.2f}%。这是收益集中度的算术敏感性，不是可执行的删交易回测。

止损回吐也确实存在：{len(loss)} 笔亏损交易中，{decomposition['losses_with_prior_positive_close_mfe']} 笔在退出前曾有正的日收盘浮盈，其中 {decomposition['losses_with_prior_close_mfe_ge5pct']} 笔曾达到至少 5% 的日收盘浮盈。该统计不使用止损当天退出后的收盘价，也不把盘中最高价当成可以成交的利润。

手续费不是主要原因：完整窗口仅 1 个币从零成本盈利变成扣成本后亏损。扣成本相对零成本的收益减少量中位数为 {fstat['median_cost_drag_arithmetic_pp']:.2f} 个百分点。即使去掉手续费和滑点，也不能把大面积失败解释掉。

## 能不能提前知道哪个币更适合

### 1. 历史盈利榜缺乏稳定延续

所有相邻年度都检查了。只保留两期完整覆盖的同币样本，前一年排名前四分之一的界限只用前一年数据确定。两期完整覆盖仍有生存条件，不能当作历史可交易选币池。

'''
 report+=mdtable(['前一年 → 后一年','同币样本数','收益排序相关系数','前一年最好 25% 的次年中位收益','其余币次年中位收益'],[[f"{x['previous_year']} → {x['next_year']}",x['pairs'],f"{x['spearman_rho']:.3f}",pct(x['next_median_return_prior_top']),pct(x['next_median_return_others'])] for x in a['coin_persistence'] if not x['exclude_economic_flags']])
 report+='''

2020→2021 只有 3 个配对样本，未进入相关系数解释。其余相关系数约在 -0.02～0.07，并未表现出稳定的赢家排序延续。2025→2026 前一年靠前组的次年中位数好一些，但仍为负，单次差异不能推翻跨期不稳定结论。

### 2. 开仓前六类条件逐年复核

只用信号收盘时已知的数据：MA60 方向、过去 30 日涨跌、30 日路径效率、过去 30 日 MA7 穿越次数、ATR/价格、30 日成交额中位数。每个事件至少有 80 根连续历史。MA60 上行指本日 MA60 高于 20 日前；路径效率为过去 30 日净对数变化绝对值除以逐日对数变化绝对值之和，不区分上涨和下跌；穿越计数使用 `close > MA7` 状态的变化（等于均线归入非上方）。ATR 比例和成交额均截至信号当日完整收盘。参数阈值在统计收益前固定，没有根据效果重新切档。

入场特征分析来自完整历史连续运行产生的交易；年度绩效表则每年重新空仓，二者不是同一套交易分母。主窗口、年度和全历史回放相互重叠，不能将其数量当作独立样本。

主要标签仅用自然退出的实际交易；终点估值作为右删失样本排除，并另报包含它们的敏感性。每个年份的跨年未完成交易也剔除，不能让开发期借用下一年的结局。所有年份都是已揭示历史诊断，不叫盲样本外。

下表为 A 组减 B 组的单笔平均**对数收益百分点**。它是条件交易结果差异，不是给策略加过滤器后的组合回测收益。星号表示至少一组未达到 30 笔、10 个币、5 个入场月份的最低样本要求。

'''
 labels={'trend60':'MA60 上方且上行 / 其他','momentum30':'过去 30 日上涨 / 未上涨','efficiency30':'路径效率 ≥0.25 / <0.10','chop30':'30 日穿越 ≤3 次 / ≥8 次','atr_pct':'ATR/价格 ≤3% / >6%','liquidity30':'日成交额 ≥1000万 / <1000万'}
 contrastrows=[]
 for key,label in labels.items():
  xs=[next(x for x in a['feature_contrasts'] if x['feature']==key and x['period']==period and not x['exclude_economic_flags']) for period in ['audit_2024','audit_2025','audit_2026']]
  contrastrows.append([label]+[f"{x['estimate_log_pp']:+.2f}"+(' *' if not x['adequate_sample'] else '') for x in xs])
 report+=mdtable(['开仓前对照 A / B','2024','2025','2026 年内'],contrastrows)
 report+=f'''

趋势、动量和震荡条件没有给出稳定且可信的正向优势，按入场月份对齐比较后一些关系还会减弱或反向。因此“这个币事后趋势更好”不能直接变成“开仓前用这个条件就能赚钱”。

低 ATR 的全期对照有正向差异，但低组只有 94 笔、14 个币；分年低组分别仅 15、26、29 笔，均未通过预先规定的年度样本门槛。{decomposition['low_atr_usdc_gold_trades']} / {decomposition['low_atr_total_trades']} 笔来自 USDC、PAXG、XAUT：USDC 是美元稳定币，后两者与实物黄金挂钩，经济属性不同。故保留为风险机制线索，不能宣布找到通用盈利过滤器。来源：[Circle USDC](https://www.circle.com/usdc)、[Paxos PAX Gold](https://www.paxos.com/pax-gold)、[Tether Gold](https://gold.tether.to/faq)。

不确定性使用币种与入场月份两维的独立 Poisson 重加权，共 500 次；这样避免把同币、同阶段交易都视为独立样本，但不是精确因果推断，也没有解决所有时间依赖、历史身份与多重比较问题。所有六个对照和失败结果全部披露。方法参考：[Owen 与 Eckles 的多因素 bootstrap](https://arxiv.org/abs/1106.2125)。

## 本轮边界与后续含义

本轮支持的判断是：**没有证明该策略能通用迁移，盈利币不能靠事后榜单稳定挑出。** 少数大波段、下行反弹损耗和跨币风险不等共同解释已观察到的收益差异；这些结果不足以给出可上线的筛选规则。

本轮没有调参数、增加过滤器、模拟做空或优化仓位。若继续改策略，应另立冻结实验，分别验证风险金额控制和弱势期入场机制；目前对 MA60 等条件的结果不能当成已验证的改进。现有资产清单、分段估值、未计资金费率与已揭示历史，仍限制任何晋升或投资结论。

## 验证、复现与证据入口

共 683 个标的的价格输入校验、4002 个连续段×窗口回放，每个同时保存零成本、基础成本、滑点加倍结果；全历史 15633 笔交易。前一轮七币的两个窗口共 14 个锚点，交易及净值逐字一致。每币抽取有效段做原函数对拍、独立因果回放、未来前缀不变性，其余所有回放均检查成本恒等式、净值乘积、有效信号掩码和无跨缺口持仓。另有 4 项针对因果特征、缺口隔离、对称异常提示和两维重抽样的测试；与 20 项研究文档一致性检查一起，24 项通过。旧七币的 202 份冻结文件哈希保持不变。全仓库扫描仍有其他研究脚本的 6 条既有登记问题，本主题没有该类错误，未修改其他研究来制造全仓库通过。

交互面板已检查筛选分母、全部 629 个单币序列、逐币选择、CSV 导出和离线显示；浏览器无脚本错误或外部网络请求。

- [全市场交互研究面板](../artifacts/full-market-20260908/全市场研究面板.html)
- [完整币种主段结果](../artifacts/full-market-20260908/main-symbol-results.csv)
- [全年度、全历史及其他连续段](../artifacts/full-market-20260908/all-window-results.csv)
- [所有标的覆盖与不足原因](../artifacts/full-market-20260908/coverage-ledger.csv)
- [全部统计与对照](../artifacts/full-market-20260908/analysis.json)
- [六项开仓条件及置信区间](../artifacts/full-market-20260908/entry-feature-contrasts.csv)
- [收益来源和止损风险分解](../artifacts/full-market-20260908/mechanism-decomposition.json)
- [主窗口逐笔交易](../artifacts/full-market-20260908/main-window-trades.csv.gz)
- [全历史逐笔与信号特征](../artifacts/full-market-20260908/full-history-trades.csv.gz)
- [截至各段末日的近期切片](../artifacts/full-market-20260908/recent-slices.csv)
- [输入与结果保留指纹](../artifacts/full-market-20260908/run-output-manifest.json)
- [回放验证](../artifacts/full-market-20260908/replay-validation.json)
- [测试、旧结果保护与仓库扫描](../artifacts/full-market-20260908/repository-validation.json)
- [浏览器交互验证](../artifacts/full-market-20260908/dashboard-browser-validation.json)
- [本轮冻结合同](../specs/full-market-contract-20260908.json)

近期切片继承原段内持仓和指标；对提前中断样本，截止点是其自身段末日，不是全局 9 月 4 日。短历史按实际天数标明。入场月份和同币重抽样区间只用于解释不确定性，不构成实盘可执行性认证。
'''
 (ROOT/'diagnostics/full-market-report-20260908.md').write_text(report)
 payload={'rows':pd.DataFrame(dashboard_rows).replace({np.nan:None}).to_dict('records'),'curves':curves,'analysis':a,'decomposition':decomposition}
 with gzip.open(OUT/'dashboard-payload.json.gz','wt',encoding='utf-8') as fp:json.dump(payload,fp,ensure_ascii=False,separators=(',',':'),allow_nan=False)
 html=(ROOT/'scripts/full-market-template.html').read_text().replace('/*__ECHARTS__*/',(ROOT/'scripts/echarts.min.js').read_text().replace('</script','<\\/script')).replace('/*__PAYLOAD__*/',json.dumps(payload,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('<','\\u003c')).replace('/*__APP__*/',(ROOT/'scripts/full-market-app.js').read_text())
 assert '/*__' not in html
 (OUT/'全市场研究面板.html').write_text(html)
 print('Built full-market report and dashboard, HTML MiB',round(len(html.encode())/2**20,2));print(json.dumps(decomposition,ensure_ascii=False))

if __name__=='__main__':build()
