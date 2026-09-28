"""Local, self-contained HTML for every retained V3 coin and crossing."""
import html
import json
import subprocess
from pathlib import Path
import pandas as pd
from v3_opportunity_study_20260913 import *
from v3_opportunity_inputs_20260913 import load_sources,table
from build_ma30_report_20260911 import STYLE,COMMON_JS,COIN_JS,packed
from build_v3_opportunity_report_20260913 import records,EVENTS

LABELS={'phase_2025_2026':'2025—2026年9月4日','phase_2023_2024':'2023—2024完整两年','cycle_2020_2024':'2020—2024完整周期',
        'calendar_2021_2023':'2021—2023','calendar_2023_2025':'2023—2025',
        **{f'year_{y}':str(y)+'年'+('至9月4日' if y==2026 else '') for y in range(2019,2027)},
        'full_segment':'原始各连续段（起止不同，不合算盈利率）'}
NOTICE='正式V3不变。每边手续费0.1%、不利滑点0.04%；约1倍仓位。未计未核实的资金费。680个加密代码中676个有可用历史、975个独立连续段；股票已排除。数据至UTC 2026-09-04，缺口前后不拼账户。'

def page(title,body,data,script):
    payload=json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('</','<\\/')
    return '<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+STYLE+'</style><main><h1>'+html.escape(title)+'</h1><p class="note">'+NOTICE+'</p>'+body+'</main><script>const DATA='+payload+';\n'+COMMON_JS+script+'</script></html>'

MAIN_JS='''
function refreshAccounts(){let p=$('period').value,a=$('arm').value,status=p==='full_segment'?'ORIGINAL_SEGMENT':$('coverage').value;let rows=DATA.accounts.filter(r=>r.block===p&&r.case_id===a&&r.status===status&&r.slug.toLowerCase().includes($('search').value.toLowerCase()));rows.sort((x,y)=>$('sort').value==='dd'?Math.abs(x.max_drawdown_pct)-Math.abs(y.max_drawdown_pct):$('sort').value==='delta'?y.return_change_pp-x.return_change_pp:y.return_pct-x.return_pct);$('count').textContent=rows.length+' 个连续段；'+(p==='full_segment'?'起止日不同，只逐段查看。':'完整区间与部分历史分开。');let sums=DATA.sums.filter(r=>r.block===p&&r.status==='COMPLETE');$('overview').innerHTML=sums.length?table(['方案','完整币数','盈利币','收益中位','回撤中位','盈亏比中位','较V3改善/恶化'],sums.map(r=>[esc(DATA.names[r.case_id]),r.coins,r.profitable,sign(r.median_return_pct),pct(r.median_drawdown_pct),num(r.median_unit_payoff),r.improved+' / '+r.worsened])):'<p>该范围没有可合并的完整账户；原始分段不合算为全市场盈利率。</p>';$('accounts').innerHTML=table(['币 / 连续段','起止日 UTC','收益','回撤','交易数','胜率','盈亏比','较原V3'],rows.map(r=>[`<a href="coins/${encodeURIComponent(r.slug)}.html">${esc(r.slug)}</a> / ${esc(r.run_key.split('__').pop())}`,esc(r.actual_start.slice(0,10)+'—'+new Date(new Date(r.actual_end)-86400000).toISOString().slice(0,10)),sign(r.return_pct),pct(Math.abs(r.max_drawdown_pct)),r.closed_trades,pct(r.win_rate_pct),num(r.unit_payoff_ratio),num(r.return_change_pp)+' pp']));}
function featureOptions(){let g=DATA.groups.filter(r=>r.event_set===$('event').value&&r.phase===$('phase').value&&r.side===Number($('side').value)&&r.days===Number($('days').value));let f=[...new Set(g.map(r=>r.feature))];$('feature').innerHTML=options(Object.fromEntries(f.map(x=>[x,DATA.featureNames[x]||x])));$('feature').value=$('event').value==='crosses'?'entry_disposition':'all';refreshGroups();}
function refreshGroups(){let g=DATA.groups.filter(r=>r.event_set===$('event').value&&r.phase===$('phase').value&&r.side===Number($('side').value)&&r.days===Number($('days').value)&&r.feature===$('feature').value);$('groups').innerHTML=table(['当时状态','事件/币','完整/不足窗口','固定持有均值','每币等权均值','顺向幅度中位ATR','逆向幅度中位ATR','先顺2ATR/先逆2ATR/顺序不明','再创新高低','恢复中位日'],g.map(r=>[esc(DATA.values[r.value]||r.value),r.events+' / '+r.coins,r.complete+' / '+r.censored,sign(r.mean_fixed_hold_pct),sign(r.equal_coin_mean_fixed_hold_pct),num(r.median_mfe_atr),num(r.median_mae_atr),r.first2_favorable+' / '+r.first2_adverse+' / '+r.first2_ambiguous,r.recovered==null?'—':r.recovered,num(r.median_recovery_day)]));}
$('period').innerHTML=options(DATA.labels);$('arm').innerHTML=options(DATA.names);$('period').value='phase_2025_2026';$('arm').value='V3';for(let id of ['period','arm','coverage','search','sort'])$(id).oninput=refreshAccounts;
$('event').innerHTML=options(DATA.events);$('phase').innerHTML=options({all:'全部历史（非独立盲测）',before_2023:'2023年以前', '2023_2024':'2023—2024', '2025_plus':'2025年以来'});$('phase').value='2025_plus';for(let id of ['event','phase','side','days'])$(id).oninput=featureOptions;$('feature').oninput=refreshGroups;refreshAccounts();featureOptions();
$('pairs').innerHTML=table(['原入场队列','案例','原均值','保护后均值','改善/恶化','赢家转亏','原赢家有符号利润保留'],DATA.pairs.filter(r=>r.cohort==='original_short_tp').map(r=>[esc(r.period),r.trades,sign(r.baseline_mean_return_pct),sign(r.new_mean_return_pct),r.improved_trades+' / '+r.worsened_trades,r.winners_turned_loss,pct(r.original_winner_signed_net_retention_pct)]));
$('allCodes').innerHTML=DATA.scope.map(s=>`<a style="display:inline-block;margin:5px 9px" href="coins/${encodeURIComponent(s.slug)}.html">${esc(s.slug)}${s.segments_with_trading_window?'':'（无交易窗口）'}</a>`).join('');
'''

EXTRA_COIN_JS='''
let crosses=[],events=[],focusCross=null;
const originalLoad=loadSegment,originalDraw=draw;
loadSegment=function(){originalLoad();let s=DATA.segments[$('segment').value];crosses=s?.crosses||[];events=s?.events||[];focusCross=null;$('cross').innerHTML='<option value="">选择一笔原始穿越</option>'+crosses.map((r,i)=>`<option value="${i}">${new Date(r[0]).toISOString().slice(0,10)} ${r[1]===1?'上穿':'下穿'} · ${DATA.dispositions[r[2]]||r[2]}</option>`).join('');$('crossRows').innerHTML=table(['观察起点','方向','原V3处理','顺向斜率','20日固定持有','20日顺向/逆向ATR','首触2ATR'],crosses.map((r,i)=>[`<button onclick="document.getElementById('cross').value='${i}';focusSignal()">${new Date(r[0]).toISOString().slice(0,10)}</button>`,r[1]===1?'多':'空',esc(DATA.dispositions[r[2]]||r[2]),num(r[3],3),r[5]?sign(r[6]*100):'窗口不足',r[5]?num(r[7])+' / '+num(r[8]):'—',esc(DATA.touches[r[9]]||r[9]||'—')]));$('eventRows').innerHTML=table(['事件日期','类型','原交易','原单收益','20日同方向变化','顺/逆向ATR','恢复原极值/天'],events.map(r=>[new Date(r[0]).toISOString().slice(0,10),esc(DATA.eventNames[r[1]]||r[1]),r[2],sign(r[3]*100),r[4]?sign(r[5]):'窗口不足',r[4]?num(r[6])+' / '+num(r[7]):'—',r[8]==null?'—':r[8]?'恢复 / '+r[9]:'未恢复']));let a=$('arm').value;let candidates=s?.candidates?.[a]||[];$('candidates').innerHTML=candidates.length?table(['处理时间','原穿越日','方向','状态','原因','等待天数'],candidates.map(r=>[new Date(r[0]).toISOString().slice(0,10),r[1]==null?'—':new Date(r[1]).toISOString().slice(0,10),r[2]===1?'多':'空',esc(r[3]),esc(DATA.candidateReasons[r[4]]||r[4]),r[5]??'—'])):'<p>此方案无等待候选记录。</p>';draw();};
function focusSignal(){let id=$('cross').value;focusCross=id===''?null:crosses[Number(id)];if(focusCross){$('trade').value='';chosen=null;let i=bars.findIndex(b=>b[0]>=focusCross[0]);lo=Math.max(0,i-20);hi=Math.min(bars.length,i+30);}draw();}
draw=function(){originalDraw();let g=cv._range;if(!g)return;ctx.save();ctx.lineWidth=1;for(let t of(chosen?[chosen]:trades)){if(t[2]<g.start||t[1]>g.finish)continue;ctx.strokeStyle=t[7]>=0?'#17774888':'#aa423a88';ctx.setLineDash([4,4]);ctx.beginPath();ctx.moveTo(g.X(t[1]),g.Y(t[4]));ctx.lineTo(g.X(t[2]),g.Y(t[5]));ctx.stroke();}ctx.setLineDash([]);let marked=focusCross?[focusCross]:$('showCrosses').checked?crosses:[];for(let r of marked){if(r[0]<g.start||r[0]>g.finish)continue;let b=bars.find(b=>b[0]===r[0]);if(!b)continue;let x=g.X(r[0]),y=g.Y(b[1]);ctx.strokeStyle=r[2]==='slope_rejected'?'#ba8114':r[2]==='filled'?'#267855':'#87918a';ctx.lineWidth=focusCross?3:1.5;ctx.beginPath();ctx.moveTo(x,y-6);ctx.lineTo(x+6,y);ctx.lineTo(x,y+6);ctx.lineTo(x-6,y);ctx.closePath();ctx.stroke();}ctx.restore();};
$('segment').oninput=loadSegment;$('arm').oninput=loadSegment;$('cross').oninput=focusSignal;$('showCrosses').oninput=draw;loadSegment();
'''

def main():
    out=R/'html';assert not out.exists();out.mkdir();(out/'coins').mkdir()
    a=R/'analysis';assert json.loads((a/'completion.json').read_text())['complete']
    sources=load_sources();periods=pd.read_csv(a/'period_accounts.csv');sums=pd.read_csv(a/'period_summary.csv');groups=pd.read_csv(a/'opportunity_groups.csv')
    scope=pd.read_csv(R/'inputs/universe_scope.csv');pairs=pd.read_csv(R/'pairs/summary.csv')
    features={'all':'全部','entry_disposition':'原V3执行原因','efficiency20_bin':'过去20日价格效率','cross20_bin':'过去20日穿越次数','wick20_bin':'过去20日影线占比','initial_risk_bin':'信号日初始风险','ma30_bin':'MA30是否顺向'}
    dispositions={'filled':'实际开仓','slope_rejected':'斜率未达标','position_occupied':'已有持仓','exit_priority_same_hour':'该小时先处理退出','nonpositive_equity':'权益不足'}
    for reason,label in dispositions.items():
        for field,name in list(features.items()):
            if field not in ['all','entry_disposition'] and '|' not in field:features[reason+'|'+field]=label+' · '+name
    values={**dispositions,'all':'全部','lt_0.2':'效率<0.2','0.2_to_0.5':'效率0.2—0.5','ge_0.5':'效率≥0.5','le_3':'穿越≤3次','4_to_7':'穿越4—7次','ge_8':'穿越≥8次','lt_0.4':'影线<40%','0.4_to_0.6':'影线40%—60%','ge_0.6':'影线≥60%','lt_10pct':'初始风险<10%','10_to_20pct':'初始风险10%—20%','ge_20pct':'初始风险≥20%','conflict_le_-0.05':'MA30明显逆向','aligned_gt_0.05':'MA30明显顺向','middle':'MA30过渡','missing':'描述不足'}
    body='''<p class="stats"><b>本轮只回答两个局部改动的得失。</b>先查看全部原始穿越与退出后走势，再看真实账户。正式V3没有被替换，两项实验分别运行，没有叠加或筛选最优参数。</p><details><summary>固定规则与读表方式</summary><p>原V3：MA7穿越且顺向斜率&gt;0.05ATR；最高/最低价连续4日停滞后每天收紧0.2ATR，倍数从1.5到最低0.5，实际止损只收窄；保留原空单加速+RSI6超卖止盈，关闭反手。</p><p>候选实验：斜率不足的空仓穿越，候选不按2/3日到期；收盘回到MA7错误侧则失效；首次同时斜率达标、价格仍在正确侧且收盘越过原穿越日收盘，次日开仓。</p><p>空单保护实验：原提前止盈首次触发后，以触发日固定1ATR加在此后最低日K低点上，次日生效；与原V3止损取更紧的一条。已有止损不放宽。</p><p>固定持有观察可相互重叠，不能累加成账户收益；退出后观察从下一根完整小时开始。盈亏比按单笔入场权益收益计算，年度按当年退出的整笔交易统计，可带入前期持仓。原始完整段起止日不同，不混为同一牛熊周期。</p></details>
<h2>两个改动有没有改善完整账户</h2><div class="filters">时期 <select id="period"></select>方案 <select id="arm"></select>覆盖 <select id="coverage"><option value="COMPLETE">完整区间</option><option value="PARTIAL">部分历史单列</option></select>币 <input id="search">排序 <select id="sort"><option value="return">收益高</option><option value="dd">回撤小</option><option value="delta">改善大</option></select></div><div id="overview" class="scroll"></div><p id="count"></p><div id="accounts" class="scroll"></div>
<h2>机会与损耗：全体信号，包含没成交和退出后的走势</h2><p>20日为事先固定的主窗口，5/10日用于核对结论方向。顺向最大幅度只是潜在空间，不能当实际利润。再创新高低与恢复天数仅对停滞事件有意义。</p><div class="filters">事件 <select id="event"></select>时期 <select id="phase"></select>方向 <select id="side"><option value="0">多空分别按方向合计</option><option value="1">多单</option><option value="-1">空单</option></select>窗口 <select id="days"><option value="20">20日</option><option value="10">10日</option><option value="5">5日</option></select>当时状态 <select id="feature"></select></div><div id="groups" class="scroll"></div>
<h2>空单同入场对照：多拿到的跌幅与归还的利润</h2><p>使用每一笔原入场、原仓位。表中是整笔交易收益均值，不是额外账户收益；原赢家后来变亏也按负数计入保留率。原提前止盈交易单列。</p><div id="pairs" class="scroll"></div>
<p><a href="../../../diagnostics/v3-opportunity-results-20260913.md">中文完整结论</a> · <a href="../../../specs/contract-v3-opportunity-20260913.md">计算前规则</a> · <a href="../analysis/period_accounts.csv">全部逐币收益回撤</a> · <a href="../analysis/opportunity_groups.csv">全部状态分组</a></p><details><summary>全部680个代码入口</summary><div id="allCodes"></div></details>'''
    data={'names':NAMES,'labels':LABELS,'accounts':records(periods),'sums':records(sums),'events':EVENTS,'groups':records(groups),'featureNames':features,'values':values,'pairs':records(pairs),'scope':records(scope)}
    (out/'index.html').write_text(page('V3：全市场机会、损耗与两个局部改动',body,data,MAIN_JS))
    dc={name:pd.read_parquet(a/(name+'.parquet')) for name in EVENTS}
    alltrades=pd.read_parquet(a/'all_account_trades.parquet');by={}
    for key,info in sources.items():by.setdefault(info['slug'],[]).append(key)
    chartjs=COIN_JS.replace("'M_MANAGE'","'V3'").replace("cv._range={start,finish,left,right};","cv._range={start,finish,left,right,Y,X};").replace('+12);','+25);')+EXTRA_COIN_JS
    for i,slug in enumerate(scope.slug,1):
        segments={}
        for key in by.get(slug,[]):
            info=sources[key];daily=pd.read_parquet(ROOT/info['daily_source']);daily.timestamp=pd.to_datetime(daily.timestamp,utc=True)
            seg={'from':str(daily.timestamp.iloc[0].date()),'to':str(daily.timestamp.iloc[-1].date()),'bars':packed(daily,['timestamp','open','high','low','close','ma','ma30']),'trades':{},'stops':{},'candidates':{}}
            for arm in NAMES:
                t=alltrades[alltrades.run_key.eq(key)&alltrades.case_id.eq(arm)]
                seg['trades'][arm]=packed(t,['trade_id','entry_time','exit_time','side','entry_price','exit_price','net_pnl','return_on_entry_equity','exit_reason']) if len(t) else []
                path=ROOT/info['baseline_dir'] if arm=='V3' else R/'accounts'/arm/'runs'/key/arm/'full'
                s=table(path/'stops.csv');e=table(path/'entry_events.csv')
                if len(s):
                    s['display_state']='V3原止损'
                    if 'tp_protect_active' in s:s.loc[s.tp_protect_active.fillna(False).astype(bool),'display_state']='空单保护已启动'
                    seg['stops'][arm]=packed(s,['trade_id','timestamp','new_stop','display_state'])
                else:seg['stops'][arm]=[]
                if len(e) and arm=='E_STATE':
                    q=e[e.stage.astype(str).str.contains('candidate|wait',regex=True)].copy()
                    for c in ['candidate_age_days','entry_wait_days_used']:
                        if c in q:break
                    else:c='display_wait';q[c]=None
                    seg['candidates'][arm]=packed(q,['timestamp','cross_day','side','status','reason',c]) if len(q) else []
                else:seg['candidates'][arm]=[]
            q=dc['crosses'][dc['crosses'].run_key.eq(key)]
            seg['crosses']=packed(q,['event_time','side','entry_disposition','slope_direction','actual_trade_id','f20_complete','f20_hypothetical_net_return','f20_mfe_atr','f20_mae_atr','f20_first_2atr'])
            q=pd.concat([d[d.run_key.eq(key)] for n,d in dc.items() if n!='crosses'],ignore_index=True)
            seg['events']=packed(q,['event_time','event_type','actual_trade_id','actual_unit_return','f20_complete','f20_directional_close_pct','f20_mfe_atr','f20_mae_atr','f20_old_extreme_recovered','f20_recovery_first_day']) if len(q) else []
            segments[key]=seg
        body='''<p><a href="../index.html">返回全市场</a></p><div class="filters">连续段 <select id="segment"></select>方案 <select id="arm"></select>交易 <select id="trade"></select></div><p>橙线MA7、蓝线MA30（仅供观察）、粉线为所选交易实际止损。虚线连接实际进出场。滚轮缩放、拖动平移、双击复位；选择交易可查看完整止损路径。</p><canvas id="chart"></canvas><p id="hint"></p><div class="filters">原始穿越 <select id="cross"></select><label><input type="checkbox" id="showCrosses">显示全部原穿越标记</label></div><p>菱形：绿色成交、橙色斜率拒绝、灰色其他原因。原始穿越和退出后诊断以原V3为基准；切换实验方案不会改变这份机会观察账。</p><div id="tradeRows" class="scroll"></div><h2>全部原始穿越：点日期定位K线</h2><div id="crossRows" class="scroll"></div><h2>候选的建立、等待、失效和确认</h2><div id="candidates" class="scroll"></div><h2>原V3退出与停滞之后发生了什么</h2><div id="eventRows" class="scroll"></div>'''
        data={'names':NAMES,'segments':segments,'dispositions':dispositions,'touches':{'favorable_first':'先顺向','adverse_first':'先逆向','same_hour_ambiguous':'同小时顺序未知','neither':'均未触及'},'eventNames':{'natural_exit':'自然退出','first_stagnation4':'四日停滞','first_actual_short_tp':'原空单止盈'},'candidateReasons':{'created':'建立候选','conditions_pending':'等待确认','confirmed':'首次确认','ma_side_invalid':'价格失效','fresh_cross_supersedes':'新穿越取代候选','not_ready':'指标不就绪','sample_end_unresolved':'样本末未决'}}
        (out/'coins'/(slug+'.html')).write_text(page(slug+' · V3交易、被拒穿越与退出后路径',body,data,chartjs))
        if i%200==0:print('HTML',i,680,flush=True)
    (out/'main.js').write_text(COMMON_JS+MAIN_JS);(out/'coin.js').write_text(COMMON_JS+chartjs)
    for p in [out/'main.js',out/'coin.js']:subprocess.run(['node','--check',str(p)],check=True)
    write_json(out/'completion.json',{'complete':True,'pages':681,'utc':str(pd.Timestamp.now(tz='UTC')),'source_sha256':sha(Path(__file__)),'visual_browser_verified':False})
    write_json(out/'artifact_checksums.json',{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='artifact_checksums.json'})
    print('HTML completed',flush=True)

if __name__=='__main__':main()
