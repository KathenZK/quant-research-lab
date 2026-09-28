"""Fixed MA30 evidence tables and offline interactive daily trade paths."""
import json,html,subprocess,time
from pathlib import Path
import numpy as np
import pandas as pd
from ma30_study_20260911 import *
import build_adaptation_report_20260911 as prior

PERIODS=['phase_2025_2026','year_2023','year_2024','year_2025','year_2026','phase_2023_2024','calendar_2023_2025']
LABELS={'phase_2025_2026':'2025—2026年9月4日','year_2023':'2023全年','year_2024':'2024全年',
        'year_2025':'2025全年','year_2026':'2026年初至9月4日','phase_2023_2024':'2023—2024','calendar_2023_2025':'2023—2025'}

class MixedSource:
    def __init__(self,new,old):self.new,self.old=new,old
    def csv(self,rel,**kw):
        d=(self.old if '/U_READY/' in rel else self.new).csv(rel,**kw)
        if rel.endswith('entry_events.csv') and len(d):
            d=d.copy();d['admission_rule_id']=d.admission_rule_id.replace({'history90_or_ma30_unavailable':'INSUFFICIENT_HISTORY90'})
        return d

def fixed_tables(cases):
    cases=cases.copy();cases['phase']=np.where(cases.entry_time<pd.Timestamp('2025-01-01',tz='UTC'),'phase_2023_2024','phase_2025_2026')
    underlying=['U_READY','C_DEFENSE','C_EXTENSION','M_DEFEND','M_EXTEND','M_MANAGE']
    cases['terminal_any']=cases[['terminal_'+a for a in underlying]].any(axis=1)
    cases['u_v3']=cases.u_U_READY
    cases['entry_state']=np.select([(cases.q<=-.05)&(cases.x<=0),(cases.q<=-.05)&(cases.x>0),(cases.q>=.05)&(cases.x>0),(cases.q>=.05)&(cases.x<=0)],
        ['逆MA30且价格未收回','逆MA30但价格已收回','MA30同向且价格同侧','MA30同向但价格异侧'],default='MA30过渡')
    rows=[];detail=[];frames=[]
    for arm in NAMES:
        g=cases.copy();g['arm']=arm;g['selected_u']=g['u_'+arm]
        g['allow']=g['allow_'+arm] if 'allow_'+arm in g else True;g['delta_u']=g.selected_u-g.u_v3
        for phase,x in g.groupby('phase'):rows.append({'phase':phase,'arm':arm,**prior.natural_case_metrics(x)})
        for (phase,side,state),x in g.groupby(['phase','side','entry_state']):detail.append({'phase':phase,'side':side,'entry_state':state,'arm':arm,**prior.natural_case_metrics(x)})
        frames.append(g)
    return pd.DataFrame(rows),pd.DataFrame(detail),pd.concat(frames,ignore_index=True)

STYLE='''body{margin:0;background:#f5f5f1;color:#24302b;font:14px system-ui}main{max-width:1380px;margin:auto;padding:28px}h1{font-size:27px}h2{font-size:20px;margin-top:30px}a{color:#315e4c}p{line-height:1.65}.note{color:#626b64}.filters{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0}select,input,button{font:inherit;padding:8px;border:1px solid #bbb;background:white;border-radius:4px}.scroll{overflow:auto;max-height:580px;background:white}table{border-collapse:collapse;width:100%;white-space:nowrap}th,td{text-align:right;border-bottom:1px solid #e5e6df;padding:9px}th:first-child,td:first-child{text-align:left}th{position:sticky;top:0;background:#e9ece6}canvas{display:block;background:white;width:100%;height:460px;touch-action:none}.green{color:#177748}.red{color:#aa423a}.stats{border-left:3px solid #527965;padding-left:16px}details{margin:14px 0;background:white;padding:12px}#hint{min-height:23px}button{cursor:pointer}@media(max-width:650px){main{padding:14px}h1{font-size:23px}}'''
COMMON_JS='''const $=id=>document.getElementById(id);const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const num=(x,n=2)=>x==null?'—':Number(x).toFixed(n);const pct=x=>num(x)+'%';const sign=x=>`<span class="${x>0?'green':x<0?'red':''}">${pct(x)}</span>`;const table=(heads,rows)=>'<table><thead><tr>'+heads.map(x=>'<th>'+esc(x)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map(x=>'<td>'+x+'</td>').join('')+'</tr>').join('')+'</tbody></table>';const options=(obj)=>Object.entries(obj).map(([v,t])=>`<option value="${esc(v)}">${esc(t)}</option>`).join('');'''
MAIN_JS='''
function selectRows(period,arm,status,search){return DATA.rows.filter(r=>r[3]===period&&r[2]===arm&&r[4]===status&&r[0].toLowerCase().includes(search.toLowerCase()));}
function refresh(){const period=$('period').value,arm=$('arm').value,status=$('coverage').value;let rows=selectRows(period,arm,status,$('search').value);const sort=$('sort').value;rows.sort((a,b)=>sort==='dd'?a[8]-b[8]:sort==='delta'?b[13]-a[13]:b[7]-a[7]);$('count').textContent=rows.length+' 个独立段；部分历史不混算盈利率，零交易不算盈利';const sums=DATA.sums.filter(x=>x.block===period&&x.status==='COMPLETE');$('overview').innerHTML=table(['方案','完整币数','盈利币','收益中位','回撤中位','盈亏比中位','同币改善中位'],sums.map(x=>[esc(DATA.names[x.case_id]),x.coins,x.profitable_segments,sign(x.median_return_pct),pct(x.median_drawdown_pct),num(x.median_closed_trade_payoff),num(x.median_return_change_pp)+' pp']));$('coins').innerHTML=table(['币 / 独立段','时间','收益','最大回撤','本期整笔交易','胜率','盈亏比','利润因子','较原V3','条件拒绝','观察期拒绝'],rows.map(r=>[`<a href="coins/${encodeURIComponent(r[0])}.html">${esc(r[0])}</a> / ${esc(r[1].split('__').pop())}`,esc(r[5]+'—'+r[6]),sign(r[7]),pct(r[8]),r[9],pct(r[10]),num(r[11]),num(r[12]),num(r[13])+' pp',r[14],r[15]]));const phase=period==='year_2023'||period==='year_2024'||period==='phase_2023_2024'?'phase_2023_2024':'phase_2025_2026';$('pairlabel').textContent='同入场队列：'+DATA.labels[phase]+'，并非所选年度账户收益';$('pairs').innerHTML=table(['方案','自然结束案例','原亏单改善','赢家转亏','赢家被拒绝','每币平均改善','原赢家正盈利保留','前5赢家保留'],DATA.pairs.filter(x=>x.phase===phase).map(x=>[esc(DATA.names[x.arm]),x.natural_ready_cases,x.losers_improved,x.winners_turned_loss,x.winners_rejected,num(x.equal_coin_mean_improvement_pp)+' pp',pct(x.positive_winner_retention*100),pct(x.top5_positive_profit_retention*100)]));}
$('period').innerHTML=options(DATA.labels);$('period').value='phase_2025_2026';$('arm').innerHTML=options(DATA.names);$('arm').value='M_MANAGE';for(const id of ['period','arm','coverage','search','sort'])$(id).oninput=refresh;refresh();
'''
COIN_JS='''
let bars=[],trades=[],stops=[],lo=0,hi=1,chosen=null;const cv=$('chart'),ctx=cv.getContext('2d');
function loadSegment(){const seg=DATA.segments[$('segment').value];bars=seg?.bars||[];const a=$('arm').value;trades=seg?.trades[a]||[];stops=seg?.stops[a]||[];$('trade').innerHTML='<option value="">全部交易</option>'+trades.map(t=>`<option value="${t[0]}">#${t[0]} ${t[3]===1?'多':'空'} ${new Date(t[1]).toISOString().slice(0,10)} ${num(t[7]*100)}%</option>`).join('');chosen=null;lo=0;hi=bars.length;$('tradeRows').innerHTML=table(['交易','方向','入场','退出','单笔收益','退出原因'],trades.map(t=>[t[0],t[3]===1?'多':'空',new Date(t[1]).toISOString().slice(0,10),new Date(t[2]).toISOString().slice(0,10),sign(t[7]*100),esc(t[8])]));draw();}
function currentTrade(){return trades.find(t=>String(t[0])===$('trade').value)||null;}
function focusTrade(){chosen=currentTrade();if(chosen){lo=Math.max(0,bars.findIndex(b=>b[0]>=chosen[1])-20);let end=bars.findIndex(b=>b[0]>=chosen[2]);hi=Math.min(bars.length,(end<0?bars.length:end)+12);}else{lo=0;hi=bars.length;}draw();}
function draw(){const w=Math.max(600,cv.clientWidth||1000),height=460;cv.width=w;cv.height=height;ctx.clearRect(0,0,w,height);if(!bars.length){$('hint').textContent='没有本轮可用价格段';return;}lo=Math.max(0,Math.min(lo,bars.length-2));hi=Math.max(lo+2,Math.min(hi,bars.length));let visible=bars.slice(lo,hi);if(!visible.length)return;const lines=chosen?stops.filter(s=>s[0]===chosen[0]):[];let min=Math.min(...visible.map(b=>Math.min(b[3],b[5]??b[3],b[6]??b[3]))),max=Math.max(...visible.map(b=>Math.max(b[2],b[5]??b[2],b[6]??b[2])));for(const s of lines){if(s[1]>=visible[0][0]&&s[1]<=visible.at(-1)[0]){min=Math.min(min,s[2]);max=Math.max(max,s[2]);}}const pad=(max-min)*.08||1;min-=pad;max+=pad;const left=65,right=w-18,top=22,bottom=420;const start=visible[0][0],finish=visible.at(-1)[0]+86400000;const X=t=>left+(t-start)/(finish-start)*(right-left),Y=p=>bottom-(p-min)/(max-min)*(bottom-top);ctx.font='11px system-ui';ctx.fillStyle='#657067';for(let i=0;i<=4;i++){let p=min+(max-min)*i/4,y=Y(p);ctx.strokeStyle='#edf0eb';ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(right,y);ctx.stroke();ctx.fillText(num(p,p<1?5:2),3,y+4);}let bw=Math.max(1,(right-left)/visible.length*.65);for(const b of visible){const x=X(b[0])+bw/2;ctx.strokeStyle=b[4]>=b[1]?'#3c8c6b':'#bc6056';ctx.fillStyle=ctx.strokeStyle;ctx.beginPath();ctx.moveTo(x,Y(b[2]));ctx.lineTo(x,Y(b[3]));ctx.stroke();ctx.fillRect(x-bw/2,Math.min(Y(b[1]),Y(b[4])),bw,Math.max(1,Math.abs(Y(b[1])-Y(b[4]))));}for(const [col,color]of[[5,'#c78d33'],[6,'#586da8']]){ctx.strokeStyle=color;ctx.lineWidth=1.5;ctx.beginPath();let begun=false;for(const b of visible){if(b[col]==null)continue;let x=X(b[0])+bw/2,y=Y(b[col]);if(begun)ctx.lineTo(x,y);else{ctx.moveTo(x,y);begun=true;}}ctx.stroke();}ctx.strokeStyle='#b84271';ctx.lineWidth=2;for(let i=0;i<lines.length;i++){const s=lines[i],end=i+1<lines.length?lines[i+1][1]:chosen[2];if(end<start||s[1]>finish)continue;ctx.beginPath();ctx.moveTo(X(Math.max(start,s[1])),Y(s[2]));ctx.lineTo(X(Math.min(finish,end)),Y(s[2]));ctx.stroke();}ctx.lineWidth=1;for(const t of(chosen?[chosen]:trades)){for(const [tm,price,label,color]of[[t[1],t[4],'入','#177748'],[t[2],t[5],'出','#aa423a']]){if(tm<start||tm>finish)continue;ctx.fillStyle=color;ctx.beginPath();ctx.arc(X(tm),Y(price),4,0,Math.PI*2);ctx.fill();ctx.fillText(label+'#'+t[0],X(tm)+5,Y(price)-6);}}ctx.fillStyle='#657067';ctx.fillText(new Date(start).toISOString().slice(0,10),left,446);ctx.fillText(new Date(finish-86400000).toISOString().slice(0,10),right-75,446);cv._range={start,finish,left,right};}
cv.onwheel=e=>{e.preventDefault();const span=hi-lo,change=Math.max(2,Math.round(span*.15)),center=(lo+hi)/2;const next=Math.max(10,Math.min(bars.length,span+(e.deltaY>0?change:-change)));lo=Math.max(0,Math.round(center-next/2));hi=Math.min(bars.length,lo+next);draw();};let drag=null;cv.onpointerdown=e=>{drag={x:e.clientX,lo,hi};cv.setPointerCapture(e.pointerId)};cv.onpointerup=()=>{drag=null};cv.onpointermove=e=>{if(drag){let n=Math.round((drag.x-e.clientX)/(cv.clientWidth||1000)*(drag.hi-drag.lo));lo=Math.max(0,Math.min(bars.length-(drag.hi-drag.lo),drag.lo+n));hi=lo+drag.hi-drag.lo;draw();return;}if(!cv._range||!bars.length)return;let r=cv.getBoundingClientRect(),g=cv._range,tm=g.start+(e.clientX-r.left-g.left)/(g.right-g.left)*(g.finish-g.start);let b=bars.reduce((a,z)=>Math.abs(z[0]-tm)<Math.abs(a[0]-tm)?z:a,bars[0]);let line=chosen?stops.filter(s=>s[0]===chosen[0]&&s[1]<=b[0]).at(-1):null;$('hint').textContent=new Date(b[0]).toISOString().slice(0,10)+' 开 '+num(b[1],4)+' 高 '+num(b[2],4)+' 低 '+num(b[3],4)+' 收 '+num(b[4],4)+' MA7 '+num(b[5],4)+' MA30 '+num(b[6],4)+(line?' 止损 '+num(line[2],4)+' 状态 '+line[3]:'');};cv.ondblclick=()=>{lo=0;hi=bars.length;draw()};$('segment').innerHTML=options(Object.fromEntries(Object.entries(DATA.segments).map(([k,s])=>[k,k+' '+s.from+'—'+s.to])));$('arm').innerHTML=options(DATA.names);$('arm').value='M_MANAGE';$('segment').oninput=loadSegment;$('arm').oninput=loadSegment;$('trade').oninput=focusTrade;loadSegment();
'''

NOTICE='每边手续费0.1%、滑点0.04%；约1倍仓位，未计未核实资金费。只含加密标的，股票已排除。完整周期来源冲突仍未解决，正式V1/V2/V3不变。'
RULES='''<details open><summary>三层规则怎样结合</summary><p>Q＝方向×MA30每日变化÷ATR14；X＝方向×(收盘−MA30)÷ATR14。多单方向为+1，空单为−1。Q≤−0.05为明显冲突；Q≥0.05且X&gt;0为中期同向，其余为过渡。</p><p><b>暂时不做：</b>冲突时拒绝本次MA7候选；修复对照允许Q改善且价格回到MA30正确一侧。<b>提前防守：</b>MA30冲突且MA7失守、回撤≥0.75ATR或低效率亏损时，止损候选逼近到收盘外侧0.5ATR。<b>盈利延伸：</b>MA30同向、扣成本后盈利、近3日效率≥0.6且推进≥0.5ATR、回撤≤0.75ATR时暂停机械收紧；加速后按降速与回撤保护。已有止损不放宽。</p><p>原MA7穿越及斜率条件不变，日收盘判断、次日执行。完整公式见<a href="../../../specs/contract-ma30-states-20260911.md">计算前规则</a>。BTC对照额外要求BTC近60日变化顺着开仓方向，核心MA30方案不读取BTC。</p></details>'''

def packed(frame,columns):
    return json.loads(frame[columns].to_json(orient='values',date_format='epoch',date_unit='ms',double_precision=15))

def page(title,body,data,script):
    payload=json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('</','<\\/')
    return '<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+STYLE+'</style><main><h1>'+html.escape(title)+'</h1><p class="note">'+NOTICE+'</p>'+body+'</main><script>const DATA='+payload+';\n'+COMMON_JS+script+'</script></html>'

def build_html(out,periods,sums,pairs,scope,chart):
    (out/'coins').mkdir(parents=True)
    p=periods[periods.block.isin(PERIODS)].copy();p['dd']=p.max_drawdown_pct.abs();p['begin']=pd.to_datetime(p.actual_start,utc=True).dt.strftime('%Y-%m-%d');p['finish']=(pd.to_datetime(p.actual_end,utc=True)-pd.Timedelta(days=1)).dt.strftime('%Y-%m-%d')
    cols=['slug','run_key','case_id','block','status','begin','finish','return_pct','dd','closed_trades','closed_trade_win_rate_pct','closed_trade_payoff_ratio','closed_trade_profit_factor','return_change_pp','learning_rejected','history90_rejected']
    data={'names':NAMES,'labels':LABELS,'rows':packed(p,cols),'sums':prior.records(sums),'pairs':prior.records(pairs)}
    body=RULES+'<div class="filters">时期 <select id="period"></select>方案 <select id="arm"></select>覆盖 <select id="coverage"><option value="COMPLETE">完整期间</option><option value="PARTIAL">部分历史单列</option></select>币 <input id="search">排序 <select id="sort"><option value="return">收益高</option><option value="dd">回撤小</option><option value="delta">较原版改善大</option></select></div><h2>同一时期比较</h2><div class="scroll" id="overview"></div><p class="note">回撤显示跌幅。各指标是逐币中位数；同币改善另算。2023—2024完整覆盖仅5币，不代表完整全市场牛熊。</p><h2>逐币结果，点币名查看MA7、MA30和交易路径</h2><p id="count"></p><div class="scroll" id="coins"></div><h2>少亏与保住大赢家</h2><p id="pairlabel"></p><p class="note">相同入场、同数量对照；所有退出都自然结束才比较。拒绝入场记0。不能相加当账户收益。盈亏比、胜率按本期退出的整笔交易统计，可能带入前期持仓。</p><div class="scroll" id="pairs"></div><p><a href="../analysis/period_accounts.csv">全部逐币逐期表</a> · <a href="../analysis/entry_state_summary.csv">MA30状态与成败</a> · <a href="../../../diagnostics/ma30-states-results-20260911.md">研究报告</a></p>'
    (out/'index.html').write_text(page('MA7 × MA30：过滤、防守与盈利延伸',body,data,MAIN_JS))
    for slug in scope.slug:
        data={'names':NAMES,'segments':chart.get(slug,{})}
        body='<p><a href="../index.html">返回全市场</a></p><div class="filters">连续段 <select id="segment"></select>方案 <select id="arm"></select>交易 <select id="trade"></select></div><p class="note">橙线MA7，蓝线MA30，粉线为所选交易的实际止损。滚轮缩放，拖动平移，双击复位；每次只显示一个连续段。</p><canvas id="chart"></canvas><p id="hint"></p><div id="tradeRows" class="scroll"></div>'
        (out/'coins'/(slug+'.html')).write_text(page(slug+' · MA30交易路径',body,data,COIN_JS))
    (out/'main.js').write_text(COMMON_JS+MAIN_JS);(out/'coin.js').write_text(COMMON_JS+COIN_JS)

def main():
    out=R/'analysis';pages=R/'html';assert not out.exists() and not pages.exists()
    new=prior.Source(R/'results');old=prior.Source(OLD/'results');ps=prior.Source(R/'pairs')
    ns=new.csv('summary.csv');us=old.csv('summary.csv');us=us[us.case_id.eq('U_READY')]
    summary=pd.concat([ns,us],ignore_index=True);blocks=pd.concat([new.csv('blocks.csv'),old.csv('blocks.csv').query('case_id == "U_READY"')],ignore_index=True)
    periods=prior.attach_periods(summary,blocks,MixedSource(new,old));sums=prior.summarize_periods(periods)
    rawcases=ps.parquet('cases.parquet');pairs,detail,decisions=fixed_tables(rawcases)
    scope=pd.read_csv(OLD/'analysis/universe_scope.csv');assert len(scope)==680
    out.mkdir();pages.mkdir();chart={};state_rows=[];side_rows=[]
    source_meta=json.loads((OLD/'cases/sources.json').read_text())
    names={'V3':'原V3','PROTECT':'衰竭保护','DEFENSE':'提前防守','WATCH':'延伸观察','HEALTHY':'健康推进','PROBE':'观察初期','ORDINARY':'正常持有'}
    for key,g in summary.groupby('run_key'):
        info=source_meta[key];slug=info['slug'];daily=pd.read_parquet(OLD/'cases/daily_features'/(key+'.parquet'));daily.timestamp=pd.to_datetime(daily.timestamp,utc=True)
        seg={'from':str(daily.timestamp.iloc[0].date()),'to':str(daily.timestamp.iloc[-1].date()),
             'bars':packed(daily,['timestamp','open','high','low','close','ma','ma30']),'trades':{},'stops':{}}
        for _,account in g.iterrows():
            arm=account.case_id;src=old if arm=='U_READY' else new;stem=f'runs/{key}/{arm}/full/'
            t=src.csv(stem+'trades.csv',allow_empty=True);s=src.csv(stem+'stops.csv',allow_empty=True)
            if len(t):
                for c in ['entry_time','exit_time']:t[c]=pd.to_datetime(t[c],utc=True)
                seg['trades'][arm]=packed(t,['trade_id','entry_time','exit_time','side','entry_price','exit_price','net_pnl','return_on_entry_equity','exit_reason'])
                t['phase']=np.where(t.entry_time<pd.Timestamp('2025-01-01',tz='UTC'),'phase_2023_2024','phase_2025_2026')
                for (phase,side),x in t.groupby(['phase','side']):
                    u=x.return_on_entry_equity;pos=u[u>0];neg=-u[u<0]
                    side_rows.append({'run_key':key,'slug':slug,'arm':arm,'phase':phase,'side':int(side),'trades':len(x),'terminal':int(x.exit_reason.eq('sample_end').sum()),'mean_entry_equity_return_pct':u.mean()*100,'positive_u':pos.sum(),'negative_u':neg.sum(),'win_rate_pct':(u>0).mean()*100})
            else:seg['trades'][arm]=[]
            if len(s):
                s.timestamp=pd.to_datetime(s.timestamp,utc=True);s['state']=s.sm_state.fillna('V3') if 'sm_state' in s else 'V3';s['state']=s.state.map(names)
                seg['stops'][arm]=packed(s,['trade_id','timestamp','new_stop','state'])
                held=s[s.full_holding_day].copy();held['phase']=np.where(held.timestamp<pd.Timestamp('2025-01-01',tz='UTC'),'phase_2023_2024','phase_2025_2026')
                for (phase,side,state),x in held.groupby(['phase','side','state']):state_rows.append({'run_key':key,'slug':slug,'arm':arm,'phase':phase,'side':int(side),'state':state,'days':len(x),'tightened_days':int(x.tightened.sum()),'short_tp_postponed':int(x.m30_short_tp_actually_suppressed.fillna(False).sum()) if 'm30_short_tp_actually_suppressed' in x else 0})
            else:seg['stops'][arm]=[]
        chart.setdefault(slug,{})[key]=seg
    tables={'period_accounts.csv':periods,'period_summary.csv':sums,'fixed_case_summary.csv':pairs,
        'entry_state_summary.csv':detail,'state_coverage.csv':pd.DataFrame(state_rows),'side_trade_results.csv':pd.DataFrame(side_rows),
        'segment_accounts.csv':summary,'universe_scope.csv':scope}
    for name,t in tables.items():t.to_csv(out/name,index=False)
    decisions.to_parquet(out/'fixed_decisions.parquet',index=False)
    priorstats=pd.read_csv(OLD/'analysis/period_summary.csv');priorstats[priorstats.case_id.isin(['A_ASSET','D_JOINT'])].to_csv(out/'prior_learned_comparison.csv',index=False)
    write_json(out/'inputs.json',{'new_results':new.record(),'old_control':old.record(),'pairs':ps.record(),'old_analysis_manifest_sha256':sha(OLD/'analysis/artifact_checksums.json'),'source_script_sha256':sha(Path(__file__))})
    (out/'source_script.py.txt').write_bytes(Path(__file__).read_bytes());build_html(pages,periods,sums,pairs,scope,chart)
    for file in ['main.js','coin.js']:subprocess.run(['node','--check',str(pages/file)],check=True)
    write_json(out/'summary.json',{'new_accounts':len(ns),'reused_baseline_accounts':len(us),'replayed_coins':ns.slug.nunique(),'original_codes':680,'same_entry_cases':len(rawcases),'fixed_natural_cases':int((~rawcases[[c for c in rawcases if c.startswith('terminal_')]].any(axis=1)).sum()),'html_pages':681,'no_stock_inclusion':True,'funding_verified':False,'official_price_conflict_resolved':False})
    for directory in [out,pages]:
        write_json(directory/'completion.json',{'complete':True,'utc':str(pd.Timestamp.now(tz='UTC'))})
        write_json(directory/'artifact_checksums.json',{str(p.relative_to(directory)):sha(p) for p in directory.rglob('*') if p.is_file() and p.name!='artifact_checksums.json'})
    print('Analysis and interactive HTML complete',flush=True)

if __name__=='__main__':main()
