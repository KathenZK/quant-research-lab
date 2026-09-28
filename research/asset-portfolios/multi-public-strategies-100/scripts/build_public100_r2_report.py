"""Join retained R1 and R2 evidence without rewriting frozen R1 artifacts."""
from pathlib import Path
import json
from collections import Counter
from public100_r2_inputs import F,ART,sha

def read(p):return json.loads((F/p).read_text())
def pct(v):return '不外推' if v is None else f'{v*100:+.2f}%'
def dd(v):return f'{abs(v)*100:.2f}%'
def table(rows,labels):
    text=['| 策略版本 | 累计收益 | 年化收益 | 最大回撤 |','|---|---:|---:|---:|']
    for r in rows:text.append(f'| {labels.get(r["variant"],r["variant"])} | {pct(r["total_return"])} | {pct(r.get("cagr"))} | {dd(r["mdd"])} |')
    return '\n'.join(text)

def main():
    old=read('artifacts/public100-ranking-20260909.json');original=read('artifacts/strategy-review-100.json')['rows'];un=read('artifacts/untested-81-20260909.json')
    b5=read('artifacts/continuation-r2/b5/results.json')['results'];eq=read('artifacts/continuation-r2/equities/results.json')['results'];fund=read('artifacts/continuation-r2/funding/results.json')['results'];boros=read('artifacts/continuation-r2/boros/results.json')['results']
    corr=read('artifacts/continuation-r2/source-corrections/results.json')['results']
    newids={'A2','A55','B5','C10','D1','D2','D5'};oldids={r['id'] for r in old['etf_ranking']+old['crypto_ranking']};assert len(oldids)==19 and oldids.isdisjoint(newids)
    labels={'B5_CODE_COUNTER22':'B5 原代码22日调仓','B5_TEXT_EVERY21':'B5 文字21日调仓','A2_DAY_OPEN':'A2 当天开盘基准','A2_PREVIOUS_CLOSE':'A2 前收盘基准','A55_LAST30_MINUTES':'A55 最后半小时动量','C10_SMA200_50':'C10 SPY＋BTC均线择时','BENCHMARK_C10_HOLD60_30':'同配比60% SPY＋30% BTC一直持有','BENCHMARK_C10_SPY_HOLD':'SPY单独一直持有','D1_CODE_SPARSE':'D1 代码：非极端就空仓','D1_TEXT_HYSTERESIS':'D1 文字：回到均值区再平仓','D2_DEFAULT10_001':'D2 默认10次均值、1%阈值','D2_EXAMPLE20_0015':'D2 示例20次均值、1.5%阈值','D5_BASE90_15_HOLD8':'D5 90次费率反向、持有8小时','BENCHMARK_PERP_BUY_HOLD':'同期各半买入持有永续（含费率）'}
    labels.update({'A36_JAN_FIRST_OPEN':'A36 一月首开盘起算','A36_PREVIOUS_DEC_CLOSE':'A36 上年末收盘起算','C1_GEM_SOURCE_IVV_VEU_BND':'C1 来源ETF版 IVV/VEU/BND'})
    for r in old['etf_ranking']:
        if r['variant']=='C1_GEM':r['label']='C1 旧清单简化版 SPY/EFA/BIL'
        if r['variant']=='A36_JANUARY_BAROMETER':r['label']='A36 旧一月首收盘起算'
    etf=old['etf_ranking']+[dict(r,label=labels[r['variant']]) for r in b5+corr if r['cost_bps']==10]
    etf=sorted([r for r in etf if r['cagr']>0],key=lambda r:r['cagr']/abs(r['mdd']),reverse=True)+sorted([r for r in etf if r['cagr']<=0],key=lambda r:r['total_return'],reverse=True)
    for i,r in enumerate(etf,1):r['rank']=i;r['calmar_comparison']=r['cagr']/abs(r['mdd'])
    explanations={
      'B5':'已找回原论坛嵌入的六个源码文件并补测；22日版年化6.04%、回撤20.76%，21日版3.88%、18.86%。调仓相位是新冻结起点；不是原2008年LEAN精确重放。',
      'A2':'SPY小时数据完整尾段已补测145个交易日；当天开盘版亏16.32%，前收盘版仅赚0.43%、较高成本即亏。原平台开盘Price语义差异不能择优掩盖。',
      'A55':'原三只ETF的33个交易日已补测，亏6.01%；毛价格盈亏仅约+0.39%初始资金，费用约6.40%，交易幅度不够覆盖成本。只有短样本，不能断言长期均无效。',
      'C10':'已补Coinbase美元现货并统一美股开盘交易时钟；2021年起累计148.27%、年化17.44%、回撤28.42%。同配比买入持有年化14.60%、回撤42.29%。值得继续检验。',
      'D1':'湖中BTC/ETH价格与费率经净收益输入检查，补真实markPrice；各半代码版亏8.01%、回撤9.77%，文字版亏9.60%、回撤24.36%。费率收入不足补偿价格损失和成本。',
      'D2':'已运行默认及示例版，BTC/ETH均0笔交易、0收益；样本平均费率最高约0.058%，达不到原1%或1.5%阈值。未改阈值凑交易，不能称其低回撤有效。',
      'D5':'默认无OI、无止损基础版已修正并补测，各半亏24.33%、回撤28.58%。OI原本是可选项，之前把它作为基础版阻塞原因不准确。可选OI版仍欠历史持仓量。',
      'D6':'已取得真实Boros历史买卖价与链上结算，另做三张2025-12-26到期合约的25日币本位费率仓位估算，每张只有2笔。未含抵押物美元风险、gas、入场费、盘口深度、历史参数和FIndex精确结算，不能计完整账户。'}
    corrections={
      'C3':'已核原论坛：止损按周五收盘判断、周一执行，并非还缺周内止损。剩余缺口是原历史股票池、市场范围，以及文字20周/30%与代码10周/10%的版本冲突。',
      'E7':'现在已有SPY/IWM/IYR短期日内行情；仍缺原交易股票池、明确的完整退出规则及原VWAP口径。不能擅自把SPY典型价乘量指标当所有原股票/期权版本。',
      'E11':'现有分钟数据为常规时段；原文要求盘前，且5/12或5/13、多层云确认及止损仍未固定。取得普通分钟数据不能补齐未给出的交易规则。',
      'A44':'本轮重新查询原Dropbox CAPE链接仍返回错误HTML；Barclays链接返回应用外壳，未取得带发布日期的原序列。源码另含加拿大XIC身份/币种及ERUS等历史终止ETF，不能按现存美股池替代。',
      'D3':'源码默认当期Binance.US现货池与做空借贷、随机成本/成交时序尚未补齐；数据湖Binance USDT永续不能自动替代该市场和历史池。',
      'D4':'贝塔分母错误、全样本最大仓位缩放及残差收益不可直接交易的问题仍须修正版；同样缺原Binance.US现货池和做空契约，不能用永续结果冒充原版。'}
    unm={r['id']:r for r in un['rows']};status=[]
    for r in original:
        ident=r['id'];row={'id':ident,'name':r['name'],'source_url':r['source_url'],'original_strategy_formally_verified':False}
        if ident in newids:
            row.update(status='ACCOUNT_DIAGNOSTIC_COMPLETE_NO_TRADES' if ident=='D2' else 'ACCOUNT_DIAGNOSTIC_COMPLETE',detail=explanations[ident],round='R2',account_backtest=True,numeric_partial_only=False,variants=sorted({x['variant'] for x in b5+eq+fund if x['id']==ident}))
        elif ident in oldids:row.update(status='ACCOUNT_DIAGNOSTIC_COMPLETE',detail=r['finding'],round='R1 retained',account_backtest=True,numeric_partial_only=False,variants=r['numeric_variants'])
        elif ident=='D6':row.update(status='PARTIAL_POSITION_DIAGNOSTIC_NOT_ACCOUNT',detail=explanations[ident],round='R2',account_backtest=False,numeric_partial_only=True,variants=['D6_ACTUAL_QUOTES_POSITION_DIAGNOSTIC'])
        else:
            u=unm[ident];row.update(status=r['status'],detail=corrections.get(ident,u['why_not_tested']),next_needed=u['next_step'],round='R1 retained; R2 scope reassessment',account_backtest=False,numeric_partial_only=False,variants=[])
        if ident in ['A36','C1']:
            actual=[x for x in corr if x['id']==ident and x['cost_bps']==10]
            row['variants']=row['variants']+[x['variant'] for x in actual];row['round']='R1 retained; R2 source/time corrections added'
            summary='；'.join(f'{labels[x["variant"]]}年化{pct(x["cagr"])}、回撤{dd(x["mdd"])}' for x in actual)
            row['detail']=summary+('。旧首收盘口径漏掉一月首日走势，不能沿用旧榜首优先级；仍为日线时钟代理。' if ident=='A36' else '。旧SPY/EFA/BIL只是清单简化变体；来源中BIL是门槛，BND才是防守资产。')
        status.append(row)
    assert len(status)==100 and len({r['id'] for r in status})==100
    counts={'total_original_ids':100,'account_backtest_ids':26,'new_account_backtest_ids':7,'account_ids_with_trades':25,'account_ids_without_trades':1,'partial_position_only_ids':1,'no_numeric_ids':73,'not_completed_account_ids':74,'formally_verified_strategy_ids':0}
    assert sum(r['account_backtest'] for r in status)==26
    sources=[{'path':p,'sha256':sha(F/p)} for p in ['artifacts/public100-ranking-20260909.json','artifacts/strategy-review-100.json','artifacts/continuation-r2/b5/results.json','artifacts/continuation-r2/equities/results.json','artifacts/continuation-r2/funding/results.json','artifacts/continuation-r2/boros/results.json','artifacts/continuation-r2/source-corrections/results.json']]
    (ART/'status-100.json').write_text(json.dumps({'counts':counts,'sources':sources,'rows':status},ensure_ascii=False,indent=2)+'\n')
    ranking={'counts':counts,'method':'Same-window ETF positive returns ranked by CAGR/abs(drawdown), negative by least loss; other markets/windows separate; D6 not a complete account and never ranked against USD returns. No best-variant original-ID selection.','sources':sources,'etf_2011_2026':etf,'crypto_spot_2024_2026':old['crypto_ranking'],'stock_btc_2021_2026':[r for r in eq if r['cost_bps']==10 and 'C10' in r['variant']],'intraday_2026':[r for r in eq if r['cost_bps']==10 and r['id'] in ['A2','A55']],'funding_dec2023_jul2024':[r for r in fund if r['cost_bps']==6 and r['symbol']=='HALF_BTC_ETH'],'boros_partial_only':boros}
    (ART/'ranking.json').write_text(json.dumps(ranking,ensure_ascii=False,indent=2)+'\n')
    labelall=labels|{r['variant']:r.get('label',r['variant']) for r in old['etf_ranking']}
    text=['# 100个策略续测：新增7个账户回测，另补1个费率仓位诊断','',
      '**这轮真正新增了A2、A55、B5、C10、D1、D2、D5七个原编号的账户回测。现在共26个有账户模型结果，其中D2没有触发交易。D6另有部分费率仓位估算，不算完整账户；还有73个没有数值，因此仍有74个没完成账户回测。正式验证通过仍是0个。**','',
      '这不是把100个都做完了，也不是宣称剩下的都永远测不了。本轮把能用已固定规则、现有湖中数据或本次补齐数据执行的账户批次跑完。其余每条尚欠材料列在[完整100项状态表](public100-status-100-r2-20260909.md)，不将未完成统一称为“免费数据不存在”。','',
      '**新结果里优先推进C10；旧结果里保留A9文字版，A7作为简单跨资产对照。A36因一月起算时点敏感，下调优先级；C1已补来源ETF版本，旧简化版单列。C4/B5作次一级防御配置比较。A2、A55、D1、D5暂缓；D2需要先核清原作者费率单位，不能因为零回撤就认为有效。**','',
      '## 新增结果','',
      '所有百分比都是相应固定样本和费用假设下的结果。回撤是从账户此前最高值跌到最低值的比例。不同样本长度不能拿累计收益直接排名。','',
      '### B5：2011-01-03至2026-08-31，ETF买卖各0.10%','',table([r for r in b5 if r['cost_bps']==10],labels),'',
      '原论坛页面其实保留了嵌入的源码附件，上轮漏读了。原参数写21，但计数条件实际每22日才触发。两种版本都跑了，未择优删掉较差版本；新启动相位与原2008年回测不同。22日版单边成本升至0.20%后年化4.77%、回撤21.81%，有正收益，但调仓时点敏感，作为较低优先级的防御配置比较。','',
      '### C10：2021-01-04至2026-08-31，SPY买卖各0.10%、BTC各0.20%','',table(ranking['stock_btc_2021_2026'],labels),'',
      '采用美股开盘统一下单的明确版本，SPY用前一交易日收盘、BTC用此前完成的UTC日线。持仓期间不天天重配。2021年前有3次所需共同开盘的BTC报价缺失，因此按数据完整性固定2021年起的窗口，没有填补。原生日线用于50日均线和每日估值；已有十五分钟缺口不被拼成完整分钟路径。','',
      'C10相对同配比一直持有，年化多约2.84个百分点，最大回撤少约13.87个百分点。股票/BTC成本提高到各0.20%/0.40%后，年化仍约15.80%、回撤30.10%。但2022年仍亏25.10%，且对比纯SPY的回撤更大；这不是低风险保本策略，也还没有独立未来检验。','',
      '| 年份 | C10账户收益 |','|---|---:|']
    c=next(r for r in eq if r['variant']=='C10_SMA200_50' and r['cost_bps']==10)
    text.extend(f'| {y}{"（至8月）" if y=="2026" else ""} | {pct(v)} |' for y,v in c['yearly'].items())
    text+=['','### A36与C1：补齐来源差异，旧数字保留','',
      '另一项[独立质地审查](../../../platform/research-program-review/diagnostics/public100-strategy-quality-review-2026-09-09.md)指出了起算时点和来源身份差异。本轮重新读原文与源码，先固定修正规则，再补跑整个2011—2026窗口；这是知道旧结果后的来源核验，不是新样本。以下买卖各0.10%。','',table([r for r in corr if r['cost_bps']==10],labels),'',
      'A36旧版用一月第一个收盘起算，漏掉首日涨跌。现在把首日开盘、上年末收盘两种清晰口径都跑完，整个窗口两版恰好产生相同持仓：年化均9.46%、回撤19.35%。源码是日频订阅加月初定时取价，原LEAN具体缓存与成交语义仍未完整重放，因此三条结果各自保留。旧版年化11.30%的排名不能直接变成最高研究优先级。','',
      'C1的[清单来源](https://indexswingtrader.blogspot.com/2016/10/prospecting-dual-momentum-with-gem.html)先比较美国股票与BIL的12个月收益，再选IVV或VEU，防守时买BND。旧SPY/EFA/BIL是清单简化变体，现已按来源另测IVV/VEU/BND，年化8.85%、回撤33.90%，当前也没有突出优势。新增两只ETF的公开原生日线已按源层规范留湖；不把来源文章的合成指数长历史或零成本业绩拿来拼接。','']
    text+=['','### A2与A55：短样本单列，买卖各0.10%','',table(ranking['intraday_2026'],labels),'',
      'A2只有2026-02-03至08-31的145个完整交易日。按当天开盘计算门槛亏16.32%；前收盘版本仅赚0.43%，单边成本到0.20%转亏3.73%。不能把不同的开盘语义当成参数挑选题。','',
      'A55只有2026-07-16至08-31的33个交易日，原三只ETF不变。扣费前的价格盈亏合计约+0.39%初始本金，买卖费用约6.40%，所以最后亏6.01%，33天只有1天在中档成本后赚钱。即使单边成本降至0.05%，仍亏2.86%。这是日内波幅不够支付频繁交易的例子，但样本不足以宣判长期无效。','',
      '### D1、D2、D5：2023-12-01至2024-07-31 16:00 UTC','',
      '价格直接复用数据湖Binance BTC/ETH永续。先过净收益输入检查，再补每笔结算的真实markPrice；两币各6,568根输入小时K线、821笔输入费率均逐条核对。11月作预热，账户从12月开始。以下为初始资金各半、独立运行、不互相调拨，买卖各0.06%，不加杠杆。','',table(ranking['funding_dec2023_jul2024'],labels),'',
      '| 版本 | BTC收益 / 回撤 | ETH收益 / 回撤 |','|---|---:|---:|']
    for v in ['D1_CODE_SPARSE','D1_TEXT_HYSTERESIS','D5_BASE90_15_HOLD8']:
        x=[next(r for r in fund if r['variant']==v and r['cost_bps']==6 and r['symbol']==s) for s in ['BTC/USDT:USDT','ETH/USDT:USDT']]
        text.append(f'| {labels[v]} | {pct(x[0]["total_return"])} / {dd(x[0]["mdd"])} | {pct(x[1]["total_return"])} / {dd(x[1]["mdd"])} |')
    text+=['','亏损原因可以分清：D1代码版BTC价格损失约1.38%初始本金，收到费率0.82%，成本4.37%；ETH价格损失7.04%，收到0.87%，成本4.93%。D5的BTC价格损失12.28%、收到费率1.87%、成本11.54%；ETH对应为17.53%、2.03%、11.20%。收到资金费率不代表账户赚钱。','',
      'D2不是数据没跑通，而是原10次/20次平均费率的1%/1.5%阈值没有触发，样本里最高平均费率约0.058%。默认与示例均零交易。D5原函数的OI过滤为可选项，所以这轮先完成无OI基础版，OI过滤版本仍欠历史数据。','',
      '## D6：有了真实报价，但只算部分仓位诊断','',
      '已从[Boros官方历史档案](https://historical-data.boros.finance/index.html)保存真实买卖报价和链上结算。只测三张同到期日合约的2025年12月1日至25日，各600小时、2次完整持有7天的交易；规则和成本在计算前固定。','',
      '| 合约 | 币本位费率仓位收益 | 币本位回撤 | 完整往返 |','|---|---:|---:|---:|']
    for r in boros:
        if r['fee_multiple']==1:text.append(f'| {r["coin"]}，2025-12-26到期 | {pct(r["total_return"])} | {dd(r["mdd"])} | {r["round_trips"]} |')
    text+=['','此处只展示费率仓位的币本位盈亏，未计抵押物美元涨跌、gas、一次性入场费和盘口深度；按整小时结算近似，未重建原链上FIndex、成交标签及历史参数。当前参数费用模型同时计入开仓、退出的真实剩余期限和持有期费用，依据[官方费用说明](https://docs.pendle.finance/boros-docs/boros-systems/fees)。因此不能把小回撤当美元账户安全，也不加入26个账户回测或收益排名。原报告“没有Boros历史数据”的说法已更新。','',
      '## 已回测策略的更新排名','',
      '十五年ETF组仍按正收益策略的“年化收益÷最大回撤”排序；亏损策略按亏得少到多排。保留同一编号的全部已测试规则差异，不挑一个最高收益版本给原编号贴金。C10、日内与永续的窗口不同，单列比较。','',table(etf,labelall),'',
      '原现货加密组的顺序保持：D9（+39.00%、回撤28.91%），D8（-52.85%、52.85%），D10（-53.24%、55.12%），D7（-55.39%、55.57%）。窗口为2024-07-01至2026-08-31、单边0.10%。D9的费率升到0.20%就亏33.03%；D7/D8/D10部分时期因原小账户资金不足停止开仓，仍不能拿幸存交易推断长期可用。','',
      '继续研究优先保留C10与A9文字12个月版，分别检查共同交易时钟/市场阶段，以及行业重叠/收益贡献集中；A7作为简单跨资产对照。A36下调为低优先级时点核验，C1来源版先作规则正确的比较基线，C4/B5作次一级防御配置比较。D9只保留成本诊断价值。优先顺序综合规则可靠性和证据，不能仅用上表的收益回撤比自动决定，也不等于可以实盘。','',
      '## 数据和核对','',
      '- Binance行情与已验收费率直接来自湖中固定V3组合，实际消费启动接口返回的帧；没有用缓存绕过检查，也没修改其他家族的数据版本。较长2024–2026原始月档已补齐，但当前固定组合的费率日历没有覆盖整段，因此本轮采用事先固定的独立完整区间。','- 新下载Yahoo、Coinbase、Boros和费率补充资料保留原响应、来源、SHA256、UTC日分区和逐项质量审计。未验收资料保持raw_unaccepted，没有写入trusted normalized。Coinbase缺310根15分钟K线，单日重查仍缺；缺口未被填零或插值。Yahoo的零量/空行有单独重查记录。','- 原始订单、每次结算、净值、调仓权重/记录及各档成本结果分别保留在continuation-r2；原R1报告和回测不覆盖。每个账户做独立资金对账，最大差异在浮点误差量级。','- 针对性测试和全仓消费者检查见[核对日志](../artifacts/continuation-r2/validation.json)。全仓仍有其他家族的未登记读取器问题；本主题不能把自己的检查通过写成整个仓库通过。','',
      '证据：[完整100项机器状态](../artifacts/continuation-r2/status-100.json)、[分组排名与数字](../artifacts/continuation-r2/ranking.json)、[本轮文件清单与哈希](../artifacts/continuation-r2/delivery-manifest.json)。']
    (F/'diagnostics/public100-continuation-results-20260909.md').write_text('\n'.join(text)+'\n')
    lines=['# 100项最新状态：26项账户回测、1项部分仓位诊断、73项无数值','','按原编号计数，不重复计算成本档位、币种和规则变体。26个账户结果中25个实际交易，D2没有交易；没有正式验证通过的策略。旧报告按当时日期保留，以本表为本轮最新状态。','','| 编号 | 策略 | 当前状态 | 结果或尚缺什么 |','|---|---|---|---|']
    for r in status:
        state='已跑账户（未正式验证）' if r['account_backtest'] else ('只有部分仓位估算' if r['numeric_partial_only'] else '尚未数值回测')
        if r['id']=='D2':state='已跑账户，0笔交易'
        lines.append(f'| {r["id"]} | {r["name"]} | {state} | {r["detail"].replace("|","/")} |')
    lines+=['','## 剩余74个账户未完成项','', '其中D6已有部分仓位估算；其余73个仍没有数值。下面按原缺口分组，不能把“尚未补齐”解释成“永远没有免费数据”。','']
    for g in un['groups']:
        ids=[i for i in g['ids'] if i not in newids]
        if ids:lines.append(f'- {g["name"]}：{len(ids)}项——'+ '、'.join(ids)+'。')
    lines+=['','B5、C3、D5、D6、E7等条目的旧原因已按本轮实际证据纠正。完整数字与成本解释见[本轮结果](public100-continuation-results-20260909.md)。']
    (F/'diagnostics/public100-status-100-r2-20260909.md').write_text('\n'.join(lines)+'\n')
    print(counts)

if __name__=='__main__':main()
