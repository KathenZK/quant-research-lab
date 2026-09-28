"""Mechanical rankings and complete repository coverage; no performance inference for missing rows."""
from pathlib import Path
from collections import Counter
import hashlib, html, json, re, math

ROOT=Path(__file__).resolve().parents[4]
FAMILY=Path(__file__).resolve().parents[1]
OUT=FAMILY/'artifacts/repository_ranking_20260911'
LABELS={'RANKED':'已完成后续回放','NO_CURRENT_FINAL_RULE':'未选出最终规则','NOT_REPLAYED':'尚未补跑','NO_AFTER_FREEZE_DATA':'现有行情早于定稿','NO_ACCEPTED_FORWARD_INPUT':'尚缺合格后续输入','NOT_COMPLETE_ACCOUNT_STRATEGY':'不是完整账户策略','REPRODUCTION_OR_SELECTION_DEFECT':'原实现或选样有问题','ARCHIVED_MODEL_NOT_REPLAYABLE':'模型已归档且不再回放','LOW_TIMEFRAME_INPUT_MISSING':'缺少1分钟或5分钟输入','DIRECTORY_EXCLUDED':'目录容器或基础设施','MISSING_FROZEN_ARTIFACT':'缺少原模型或配置','MISSING_AUXILIARY_DATA':'缺少必要辅助数据','INPUT_CHECK_FAILED':'后续全市场输入检查未通过'}

def clean(x):
    if isinstance(x,dict):return {k:clean(v) for k,v in x.items()}
    if isinstance(x,list):return [clean(v) for v in x]
    if isinstance(x,float) and not math.isfinite(x):return None
    return x
def dump(path,value):path.write_text(json.dumps(clean(value),ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def family_for_old(i,r):
    if i in range(5,10):return 'research/'+r['name'].split('-')[0].lower()+'/1h-adaptive-regime'
    special={35:'asset-portfolios/1h-adaptive-regime-multi-asset-ensemble',36:'btc/15m-ema-trend-breakout',37:'btc/15m-keltner-trend-breakout',38:'sol/1h-pullback-bracket',39:'sol/1h-volatility-compression-breakout',40:'sol/4h-rs4-regime-switch',41:'btc/30m-trend-continuation',42:'btc/15m-trend-continuation',43:'asset-portfolios/15m-asset-specific-six-strategy-selector',44:'asset-portfolios/15m-asset-specific-six-strategy-selector'}
    return 'research/'+special[i] if i in special else 'research/hype/'+r['family']

SHORT={0:'HYPE 15分钟 EMA-TB V41',1:'HYPE 15分钟 EMA-X V18',2:'HYPE 15分钟 MII V1.4A',3:'HYPE 15分钟 TB+MII V2',4:'HYPE 15分钟 10根8根反转 V35',5:'BTC 1小时 AR V4',6:'ETH 1小时 AR V4',7:'SOL 1小时 AR V3',8:'BNB 1小时 AR V3',9:'TRX 1小时 AR V3',10:'HYPE 1小时 AR V4',11:'HYPE 15分钟 BKSB基线',12:'HYPE 1小时 BKSB基线',13:'HYPE 15分钟 Keltner压缩扩张',14:'HYPE 15分钟 Keltner外轨突破',15:'HYPE 15分钟 Keltner中线回踩',16:'HYPE 30分钟 Keltner V3',17:'HYPE 15分钟 MA7/MA30加仓·跌破MA7退出',18:'HYPE 15分钟 MA7/MA30加仓·反向交叉退出',19:'HYPE 15分钟 MDTP V1',20:'HYPE 1小时 MHEF·缓冲0.00',21:'HYPE 1小时 MHEF·缓冲0.10',22:'HYPE 15分钟 MMTF V3',23:'HYPE 1小时 MMTF V3',24:'HYPE 15分钟 MTPP多头·风险10%',25:'HYPE 15分钟 MTPP多头·风险1%',26:'HYPE 15分钟 MTPP多头·风险3%',27:'HYPE 15分钟 MTPP空头·风险10%',28:'HYPE 15分钟 MTPP空头·风险1%',29:'HYPE 15分钟 MTPP空头·风险3%',30:'HYPE 15分钟 PBTR固定止盈止损观察',31:'HYPE 1小时 PKTSC多头',32:'HYPE 1小时 PKTSC空头',33:'HYPE 15分钟 SDS·KCS固定失败对照',34:'HYPE 15分钟 SMA斜率固定失败对照',35:'六币 1小时 AR-MAE V1',36:'BTC 15分钟 EMA-TB V40迁移观察',37:'BTC 15分钟 Keltner观察',38:'SOL 1小时 回踩R01145',39:'SOL 1小时 波动压缩R002346',40:'SOL 4小时 RS4 R0343',41:'BTC 30分钟 续涨08816b',42:'BTC 15分钟 续涨913f4f',43:'六币 15分钟 AS6S V6·不抢仓',44:'六币 15分钟 AS6S V6·强突破抢仓'}

def results():
    original=FAMILY/'artifacts/all_results.json';old=json.loads(original.read_text());rows=[]
    for i,r in enumerate(old):
        row=dict(id=f'legacy_{i:02}',name=SHORT[i],original_name=r['name'],family_path=family_for_old(i,r),
                 registered=r['registered'],status='已登记版本' if r['registered'] else '固定观察方案',
                 start=r['start'],end='2026-09-05T12:00:00Z' if i==40 else '2026-09-05T15:00:00Z',
                 return_value=r['return'],drawdown=abs(r['drawdown']),trades=r['trades'],count_unit='笔交易',
                 cost=r['cost'],limitation=r['limitation'],source=r['source'],equity_path=r['equity_path'],original_result_index=i,
                 baseline_artifact=str(original.relative_to(ROOT)),baseline_sha256=sha(original))
        if i in [20,21]:row['count_unit']='次方向入场（非完整交易）'
        if i in range(24,30):row['count_unit']='段交易（含加仓）'
        if i==4:row['limitation']='原回放存在退出顺序/next-open歧义，不能等同于后来统一1倍重算的V35。'+row['limitation']
        if i==22:
            p=FAMILY/'artifacts/iteration_comparison_20260911/ar_mmtf/legacy_rvol_correction/correct_spec_rvol96/summary.json';x=json.loads(p.read_text())
            row.update(return_value=x['metrics']['total_return'],drawdown=x['metrics']['max_drawdown'],source=str(p.relative_to(ROOT)),equity_path=str(p.with_name('native_equity.csv').relative_to(ROOT)),correction='RVOL48误写更正为规格RVOL96；收益及原引擎盘中保守回撤同时替换。')
            row['limitation']=row['correction']+' '+row['limitation']
        rows.append(row)
    for p in sorted((OUT/'replays').glob('*/summary.json')):
        row=json.loads(p.read_text());row.update(id=p.parent.name,status='已登记版本' if row['registered'] else '固定观察方案',count_unit=row['source_metrics'].get('count_unit','笔交易'))
        rows.append(row)
    for r in rows:
        if r['id'].startswith('turtle_'):
            labels=['固定1倍','波动目标20%','单笔风险1%','单笔风险2%','固定1倍并回撤降仓','风险1%并回撤降仓']
            r['name']=r['name'].split('·')[0]+'·'+labels[int(r['id'].split('_')[-1])]+'（同收盘成交诊断）'
            r['status']='原模型诊断：同收盘成交'
        r['return_drawdown_ratio']=r['return_value']/r['drawdown'] if r['drawdown']>0 else None
        r['low_count']=r['trades']<=3;r['source_sha256']=sha(ROOT/r['source'])
        assert (ROOT/r['family_path']).is_dir()
    assert len({r['id'] for r in rows})==len(rows)
    return clean(rows)

def rankings(rows):
    positive=[r for r in rows if r['return_value']>0]
    return {'高收益':sorted(rows,key=lambda r:(-r['return_value'],r['drawdown'],r['id'])),
            '盈利且低回撤':sorted(positive,key=lambda r:(r['drawdown'],-r['return_value'],r['id'])),
            '收益回撤比':sorted([r for r in positive if r['return_drawdown_ratio'] is not None],key=lambda r:(-r['return_drawdown_ratio'],-r['return_value'],r['id']))}

def coverage(rows):
    discovery=json.loads((OUT/'scope_discovery.json').read_text());seen={r['family_path'] for r in rows}
    exclude={61:'本次跨家族诊断主题，不是被测试策略',62:'公开100条的容器；下方按100个原始ID展开',124:'行业机会研究，不是交易策略',127:'旧产物容器，归入MU家族',128:'旧文档容器，归入MU家族',129:'旧脚本容器，归入MU家族',130:'平台研究基础设施',131:'数据湖治理',132:'研究项目复盘',133:'运行授权管理'}
    status={}
    def group(ids,code,reason):
        for i in ids:status[i]=(code,reason)
    group([12,21,22,24,25,37,38,39,43,44,56,100],'NO_AFTER_FREEZE_DATA','本地保存的是2026年9月研究时重跑的历史行情；本轮可用行情截至9月5日，不能把这类定稿前历史成绩当作定稿后的收益。')
    group([13,17,42,76,78,126,138,139,141,142],'NO_ACCEPTED_FORWARD_INPUT','保留的外部市场/指数/代理历史没有可直接采用的定稿后完整账户结果；需补后续行情及其质量/交易模型检查，不能用旧历史收益顶替。')
    group([111,120,121,122,59],'LOW_TIMEFRAME_INPUT_MISSING','需要1分钟或5分钟后续行情；当前登记数据目录13个输入没有1分钟/5分钟版本，本轮已有合格价格最小为15分钟。不能用15分钟插成5分钟；尚缺可核验的后续回放输入。')
    group([1,2,16,19,23,30,34,41,49,51,53,55,57,63,64,65,71,104,112,113],'NO_CURRENT_FINAL_RULE','主账没有可按当前正式版本登记表直接选取的最终可运行策略。搜索/模型/失败候选的历史成绩不自动等于最终版定稿后收益；本次没有替它另选搜索赢家。')
    group([14,26,27,28,29,33,50,58,91,101,103,110],'NOT_COMPLETE_ACCOUNT_STRATEGY','主账当前对象是数据、信号/事件、预测或机制研究；未确认一份当前最终交易规则及对应的定稿后完整账户结果。事件收益和预测分数不能作为账户收益入榜。')
    group([15,32,36,48,93,119,60],'REPRODUCTION_OR_SELECTION_DEFECT','主账记有实现、样本选择或复现未对齐问题；尚无排除该问题后的定稿后完整账户结果。具体问题见主账摘录，不能继续引用漂亮的旧成绩代替。')
    group([52],'ARCHIVED_MODEL_NOT_REPLAYABLE','V1 freeze R4已归档，主账明确放弃prospective OOS；本次不打开盲态结果，不用历史OOF收益排名，未重建被清理模型。')
    group([83,86],'MISSING_FROZEN_ARTIFACT','原41家族核查已确认冻结模型/候选JSON缺失：factor-ML缺最终模型和manifest；15m MHEF缺V2完整候选JSON。不能拿默认参数顶替。')
    group([5,7,8,9,10,11,47],'NO_CURRENT_FINAL_RULE','原主账明确没有登记版本，开发搜索未选出可继续验证的唯一候选，研究线关闭；不替它在历史前沿中另挑一个赢家。')
    group([6],'NO_CURRENT_FINAL_RULE','仅冻结了P0研究计划，原研究尚未运行，也没有选定最终配置；不是已有最终策略的后续回放。')
    group([72],'MISSING_AUXILIARY_DATA','原规格必需的20日持仓量高位过滤缺少历史数据；不删掉过滤器后冒称复现。')
    group([40],'INPUT_CHECK_FAILED','后续全市场输入已尝试检查：874代码请求在1000BTTC无有效窗口时失败，尚未完成可核验的整池重建，未补出账户回放。这个技术缺口不是策略亏损；不能只删掉失败代码就声称完整复现。详见 input_probes/ls3.json。')
    checked=[]
    for i,r in enumerate(discovery):
        r=dict(r);r['discovery_index']=i
        docs=[Path(p) for p in r['root_documents']];r['evidence_sha256']={str(p):sha(p) for p in docs}
        text='\n'.join(p.read_text() for p in docs)
        sections=re.split(r'\n## ',text);r['current_state_excerpt']=next((s[:2400] for s in sections[1:] if any(k in s.splitlines()[0] for k in ['Current State','当前状态','身份与状态'])),text[:1500])
        r['spec_files']=[str(p) for p in (ROOT/r['family_path']/'specs').glob('*') if p.is_file()]
        if i in exclude:r.update(coverage_status='DIRECTORY_EXCLUDED',reason=exclude[i])
        elif r['family_path'] in seen:r.update(coverage_status='RANKED',reason='已有定稿后回放；名次只针对已完成方案，详细限制随结果保留。',result_ids=[v['id'] for v in rows if v['family_path']==r['family_path']])
        else:
            code,reason=status.get(i,('NOT_REPLAYED','已有历史研究，但本轮尚未完成这个家族的定稿后回放。未入榜不是亏损，也不表示策略无法运行。'))
            r.update(coverage_status=code,reason=reason)
        r['status_label']=LABELS.get(r['coverage_status'],r['coverage_status'])
        checked.append(r)
    p=ROOT/'research/asset-portfolios/multi-public-strategies-100/specs/inventory.json'
    public=json.loads(p.read_text());assert len(public)==100 and len({r['id'] for r in public})==100
    public_rows=[dict(id=r['id'],name=r['name'],market=r['market'],coverage_status='NO_AFTER_FREEZE_DATA',reason='本仓登记/复核于2026-09-08及09-09，所用数据截止2026-09-01；无本仓定稿后账户结果。原公开发表后历史表现属于另一问题。',source=str(p.relative_to(ROOT)),source_sha256=sha(p)) for r in public]
    return checked,public_rows

def table(rows):
    lines=['| 排名 | 策略 | 身份 | 收益 | 最大回撤 | 收益/回撤 | 数量 | 测试时间（UTC） |','|---:|---|---|---:|---:|---:|---|---|']
    for i,r in enumerate(rows,1):
        ratio='—' if r['return_drawdown_ratio'] is None else f"{r['return_drawdown_ratio']:.3f}"
        count=f"{r['trades']} {r['count_unit']}"+('；仅少量样本' if r['low_count'] else '')
        lines.append(f"|{i}|{r['name']}|{r['status']}|{r['return_value']:+.2%}|{r['drawdown']:.2%}|{ratio}|{count}|{r['start'][:10]} → {r['end'][:10]}|")
    return '\n'.join(lines)

def build():
    rows=results();allr=rankings(rows);registered=rankings([r for r in rows if r['registered']]);cat,pub=coverage(rows)
    counts=Counter(r['coverage_status'] for r in cat);active=[r for r in cat if r['coverage_status']!='DIRECTORY_EXCLUDED']
    summary={'directories':len(cat),'excluded_directories':counts['DIRECTORY_EXCLUDED'],'family_or_topic_count':len(active),'public_original_items':len(pub),'ranked_families':len({r['family_path'] for r in rows}),'scenarios':len(rows),'new_scenarios':sum(not r['id'].startswith('legacy_') for r in rows),'registered_scenarios':sum(r['registered'] for r in rows),'registered_families':len({r['family_path'] for r in rows if r['registered']}),'profitable_scenarios':sum(r['return_value']>0 for r in rows),'losing_scenarios':sum(r['return_value']<0 for r in rows),'zero_scenarios':sum(r['return_value']==0 for r in rows),'coverage_counts':dict(counts),'full_repository_backtesting_complete':False,'coverage_review_complete':True}
    dump(OUT/'results.json',rows);dump(OUT/'rankings.json',{k:[r['id'] for r in v] for k,v in allr.items()});dump(OUT/'registered_rankings.json',{k:[r['id'] for r in v] for k,v in registered.items()});dump(OUT/'coverage.json',cat);dump(OUT/'public100_coverage.json',pub);dump(OUT/'summary.json',summary)
    report=[ '# 全仓定稿后收益与回撤排序（2026-09-11）','',f"全仓清点：{len(cat)}个目录，去掉{counts['DIRECTORY_EXCLUDED']}个基础设施/容器后是{len(active)}个策略家族或研究主题；公开策略另按100个原始条目展开。已有{summary['ranked_families']}家族、{len(rows)}个方案的定稿后回放，其中本次新增{summary['new_scenarios']}方案。**全仓清点已完成，但不是每个目录都补出了回测。月度多空LS3的整池输入检查未通过，尚无后续账户结果；其他未入榜项分别列明缺少资料、没有最终交易规则或没有定稿后行情等原因。**",'',
              '“早期版收益”是早期规则在共同后续行情中的收益，不是策略定稿时公布的历史回测收益。本报告三榜只使用定稿后回放。', '',
              '按所有已完成固定方案及原模型诊断排序，最高收益为ETH日线MA7/MA30加仓直迁观察；它当时没有登记版本，原模型有较高杠杆。海龟模型的同收盘信号/成交假设及未计资金费也单独标注，其漂亮数字不等于可执行。只看已登记版本，HYPE 30分钟 Keltner V3仍为收益第一。两类均保留，可以分别查看，不能把观察方案叫作正式最终版。', '',
              '测试从各自定稿日后的起点到2026-09-05；15分钟/1小时通常截止15:00，4小时/6小时12:00，日线00:00；周线截至8月31日。保留原仓位、原手续费和滑点；大部分为每次手续费0.1%+不利滑点0.04%，EMA、CC、RS4等例外在明细列出。资金费率或者沿用原模型不计入，或者只估算已取得事件，完整覆盖未证明。不同运行天数、仓位和成本下的排名只是本段表现，不是统一风险下的优劣比较。', '',
              '低回撤榜：先筛收益>0，再按回撤升序。收益回撤比榜：先筛收益>0，再按累计收益/最大回撤降序；它不是年化Calmar，也不保证绝对回撤适中。1–3笔样本照列并提示，不据此认定稳定。回撤估值频率沿用各家族，部分为盘中保守估计，部分为收盘/开盘净值，详见明细。', '',
              f"{summary['profitable_scenarios']}个方案盈利，{summary['losing_scenarios']}个亏损，{summary['zero_scenarios']}个为零。方案数包括同一家族预先声明的仓位/退出变体，不能作为独立策略数量。",'',
              '[交互排序与全仓清单](../artifacts/repository_ranking_20260911/index.html) · [计算约定](../specs/repository-post-freeze-ranking-20260911.md) · [全仓清单](repository-coverage-20260911.md) · [机器结果](../artifacts/repository_ranking_20260911/results.json)','']
    for k,v in allr.items():report+=['## 全部固定方案及原模型诊断：'+k,'',table(v),'']
    for k,v in registered.items():report+=['## 仅已登记版本：'+k,'',table(v),'']
    report+=['## 每个方案的来源与成本','']
    for r in rows:
        link='../../../../'+r['source'];report += [f"### {r['name']}",f"- [{r['id']} 原始证据]({link})；家族：`{r['family_path']}`。",f"- 成本：{r['cost']}。",f"- 已知限制：{r['limitation']}",'']
    report+=['## 与线上观察分开','', 'HYPE日线MA7 V7.1另有8月13日启动、9月7日归档的dry-run首笔闭合记录，按毛利减估计手续费约+2.12%，净利字段缺失、账户最大回撤未完整记录，并有一小时缺K延迟。它不是本榜截至9月5日的研究回放，未拿它替换本榜约+0.81%的结果。HYPE5分钟PBTR的live事故记录也没有完整回报/回撤，未伪造为0收益。', '', '本报告不恢复先前已撤回的主观优先级，不据此认定迭代过拟合，也不构成上线或加仓结论。']
    (FAMILY/'diagnostics/repository-ranking-20260911.md').write_text('\n'.join(report)+'\n')
    cover=['# 全仓覆盖与未入榜原因','',f"{len(active)}个策略家族/主题，另100个公开策略原始条目；未入榜不等于亏损。主账摘录及文件指纹保存在机器清单。",'', '| 状态 | 数量 |','|---|---:|',*[f'|{LABELS.get(k,k)}|{v}|' for k,v in sorted(counts.items())],'','## 全部家族与主题','', '| 家族或主题 | 本轮状态 | 说明 | 主账/入口 |','|---|---|---|---|']
    for r in active:
        p=r['root_documents'][0];cover.append(f"|{r['family_path'].removeprefix('research/')}|{r['status_label']}|{r['reason']}|[入口](../../../../{p})|")
    cover+=['','## 公开100条','', '| ID | 名称 | 状态 |','|---|---|---|',*[f"|{r['id']}|{r['name']}|9月8/9日落档，数据截止9月1日，无本仓定稿后回放|" for r in pub]]
    (FAMILY/'diagnostics/repository-coverage-20260911.md').write_text('\n'.join(cover)+'\n')
    payload=json.dumps({'rows':rows,'coverage':active,'public':pub,'summary':summary},ensure_ascii=False).replace('</','<\\/')
    template='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>定稿后策略排序</title><style>body{font:15px/1.55 system-ui,sans-serif;max-width:1500px;margin:30px auto;padding:0 24px;color:#222;background:#faf9f6}h1{font-size:28px}p{max-width:1050px}button,select,input{font:inherit;padding:8px 12px;margin:5px 8px 10px 0}table{border-collapse:collapse;width:100%;background:white}td,th{padding:10px;border-bottom:1px solid #ddd;text-align:left;vertical-align:top}th{position:sticky;top:0;background:#eee}td small{display:block;color:#666;max-width:360px}.positive{color:#08633c}.negative{color:#a12f31}.note{color:#8c5015}details{max-width:520px}summary{cursor:pointer}.scroll{overflow:auto}#count{margin:10px 0}</style><h1>策略定稿以后，实际回放表现怎样？</h1><p id="scope"></p><p>收益从各自定稿后的起点算起，结束于2026年9月5日。各策略原仓位和成本不同；资金费率为已取得事件的估算，部分原模型完全不计资金费率。默认展示已登记最终版，可切换未登记观察与原模型诊断。<strong>尚未补跑的主题没有排名；缺结果不等于亏损。</strong></p><p>“早期版收益”指把早期规则拿到后续行情重跑的收益，并非当时定稿公布的历史回测成绩。</p><button onclick="mode='results';render()">查看三榜</button><button onclick="mode='coverage';render()">全仓覆盖</button><button onclick="mode='public';render()">公开100条</button><div><select id="metric" onchange="render()"><option value="return">高收益：累计收益降序</option><option value="drawdown">盈利且低回撤：回撤升序</option><option value="ratio">收益回撤比：累计收益÷回撤降序</option></select><select id="status" onchange="render()"><option value="registered">仅已登记最终版</option><option value="all">全部：含未登记观察和原模型诊断</option><option value="observation">仅固定观察方案</option></select><input id="search" placeholder="搜索币种、名称、家族或状态" oninput="render()"></div><p class="note">1–3笔样本特别标出，靠前不代表稳定。收益回撤比高不保证绝对回撤适中；回撤估值方法及交易计数单位可能不同，展开每行可看限制。</p><div id="count"></div><div class="scroll" id="table"></div><script>const D=PAYLOAD;let mode='results';const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const pct=x=>(x*100).toFixed(2)+'%';function render(){const q=document.getElementById('search').value.toLowerCase(),kind=document.getElementById('metric').value,status=document.getElementById('status').value;let r=[];let heads=[],body='';if(mode==='results'){r=D.rows.filter(x=>(status==='all'||(status==='registered'?x.registered:!x.registered))&&(kind==='return'||x.return_value>0));r.sort((a,b)=>kind==='return'?b.return_value-a.return_value||a.drawdown-b.drawdown:kind==='drawdown'?a.drawdown-b.drawdown||b.return_value-a.return_value:b.return_drawdown_ratio-a.return_drawdown_ratio||b.return_value-a.return_value);r=r.map((x,i)=>({...x,rank:i+1})).filter(x=>(x.name+' '+x.family_path).toLowerCase().includes(q));heads=['名次','策略与身份','累计收益','最大回撤','收益/回撤','交易数量','测试时间 UTC','成本与限制'];body=r.map(x=>`<tr><td>${x.rank}</td><td>${esc(x.name)}<small>${x.status}</small></td><td class="${x.return_value>0?'positive':'negative'}">${x.return_value>0?'+':''}${pct(x.return_value)}</td><td>${pct(x.drawdown)}</td><td>${x.return_drawdown_ratio==null?'—':x.return_drawdown_ratio.toFixed(3)}</td><td>${x.trades}<small>${esc(x.count_unit)}</small>${x.low_count?'<small class="note">样本很少</small>':''}</td><td>${esc(x.start.slice(0,10))}<br>至 ${esc(x.end.slice(0,16))}</td><td><details><summary>展开</summary><p>${esc(x.cost)}</p><p>${esc(x.limitation)}</p><a href="../../../../../${encodeURI(x.source)}">原始证据</a></details></td></tr>`).join('')}else if(mode==='coverage'){r=D.coverage.filter(x=>(x.family_path+x.status_label+x.reason).toLowerCase().includes(q));heads=['家族或主题','状态','说明'];body=r.map(x=>`<tr><td>${esc(x.family_path.replace('research/',''))}</td><td>${esc(x.status_label)}</td><td>${esc(x.reason)}</td></tr>`).join('')}else{r=D.public.filter(x=>(x.id+x.name+x.market).toLowerCase().includes(q));heads=['ID','公开策略','市场','未入榜原因'];body=r.map(x=>`<tr><td>${x.id}</td><td>${esc(x.name)}</td><td>${esc(x.market)}</td><td>${esc(x.reason)}</td></tr>`).join('')}document.getElementById('count').textContent='当前显示 '+r.length+' 条';document.getElementById('table').innerHTML='<table><thead><tr>'+heads.map(h=>'<th>'+h+'</th>').join('')+'</tr></thead><tbody>'+body+'</tbody></table>'}document.getElementById('scope').textContent=`清点 ${D.summary.family_or_topic_count} 个策略家族/研究主题，另 ${D.summary.public_original_items} 条公开策略；已有 ${D.summary.ranked_families} 家族、${D.summary.scenarios} 方案后续回放，本次新增 ${D.summary.new_scenarios} 方案。`;render();</script></html>'''
    (OUT/'index.html').write_text(template.replace('PAYLOAD',payload))
    print(json.dumps(summary,ensure_ascii=False,indent=2))
    for title,rank in allr.items():print(title,[(r['name'],round(r['return_value']*100,3),round(r['drawdown']*100,3)) for r in rank[:5]])

if __name__=='__main__':build()
