"""Compare frozen and natural-readiness accounts; retain interactive stop paths."""
import argparse
import html
import json
import re
from pathlib import Path
import numpy as np
import pandas as pd
from v3_no_extra_warmup_20260913 import R,OLD,ROOT,BASE,ARMS,catalog,load_new,old_directory,verify_frozen
from common import sha,write_json
from v3_opportunity_inputs_20260913 import table
from build_ma30_report_20260911 import STYLE,COMMON_JS,COIN_JS
from build_v3_opportunity_html_20260913 import LABELS
from revise_v3_stoplines_20260913 import CSS,CHART_BODY,DETAIL_COLUMNS

ARM_NAMES={'V3':'V3','E_STATE':'候选按价格状态失效','TP_PROTECT':'空单止盈改跟踪保护'}
NAMES={**{a:label+' · 取消额外预热' for a,label in ARM_NAMES.items()},
       **{'OLD_'+a:label+' · 旧28天等待' for a,label in ARM_NAMES.items()}}
NOTICE='每边手续费0.1%、不利滑点0.04%。取消额外固定28天等待；只保留指标自然就绪与行情有效要求。保持原穿越和退出规则，次日开盘执行，关闭反手。各连续段独立账户，不跨缺口拼接。未核实资金费未计入。'

def packed(d,cols):
    return json.loads(d.reindex(columns=cols).to_json(orient='values',date_format='epoch',date_unit='ms',double_precision=15))
def records(d):return json.loads(d.to_json(orient='records',date_format='iso',double_precision=15))
def decode(p):return json.JSONDecoder().raw_decode(p.read_text().split('const DATA=',1)[1])[0]
def page(title,body,data,script):
    payload=json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('</','<\\/')
    return '<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+STYLE+CSS+'</style><main><h1>'+html.escape(title)+'</h1><p class="note">'+NOTICE+'</p>'+body+'</main><script>const DATA='+payload+';\n'+COMMON_JS+script+'</script></html>'

def tables():
    verify_frozen();assert json.loads((R/'results/completion.json').read_text())['complete']
    out=R/'analysis';out.mkdir(exist_ok=True)
    old=pd.read_csv(OLD/'analysis/period_accounts.csv');new=pd.read_csv(R/'results/periods.csv')
    cols=['run_key','case_id','block','status','actual_start','actual_end','return_pct','max_drawdown_pct','closed_trades','win_rate_pct','unit_payoff_ratio']
    rhs=old[cols].rename(columns={c:'old_'+c for c in cols if c not in ['run_key','case_id','block']})
    joined=new.merge(rhs,on=['run_key','case_id','block'],how='left',validate='one_to_one')
    joined['return_change_pp']=joined.return_pct-joined.old_return_pct
    joined['drawdown_reduction_pp']=joined.old_max_drawdown_pct.abs()-joined.max_drawdown_pct.abs()
    summaries=[]
    for (block,arm),g in joined[joined.status.eq('COMPLETE')&joined.old_status.eq('COMPLETE')].groupby(['block','case_id']):
        assert not g.slug.duplicated().any()
        summaries.append({'block':block,'case_id':arm,'paired_coins':len(g),
            'old_profitable':int(g.old_return_pct.gt(1e-10).sum()),'new_profitable':int(g.return_pct.gt(1e-10).sum()),
            'old_median_return_pct':g.old_return_pct.median(),'new_median_return_pct':g.return_pct.median(),
            'old_median_drawdown_pct':g.old_max_drawdown_pct.abs().median(),'new_median_drawdown_pct':g.max_drawdown_pct.abs().median(),
            'improved':int(g.return_change_pp.gt(1e-8).sum()),'worsened':int(g.return_change_pp.lt(-1e-8).sum()),
            'unchanged':int(g.return_change_pp.abs().le(1e-8).sum())})
    # Exact old start boundary, retaining the new account's inherited position and equity.
    common=[]
    for row in joined[joined.block.eq('full_segment')&joined.legacy].itertuples():
        p=ROOT/row.result_path;eq=pd.read_parquet(p/'equity.parquet');eq.timestamp=pd.to_datetime(eq.timestamp,utc=True)
        a=pd.Timestamp(row.old_actual_start);end=pd.Timestamp(row.actual_end)
        stamps=eq.timestamp.astype('int64').to_numpy();ia=np.searchsorted(stamps,a.value,side='left')
        assert eq.timestamp.iloc[ia]==a
        v=eq.equity.to_numpy()[ia:];base=v[0]
        common.append({'run_key':row.run_key,'case_id':row.case_id,'slug':row.slug,'start':str(a),'end':str(end),
            'old_return_pct':row.old_return_pct,'new_return_pct':float((v[-1]/base-1)*100) if base>0 else None,
            'old_drawdown_pct':abs(row.old_max_drawdown_pct),'new_drawdown_pct':float(-(v/np.maximum.accumulate(v)-1).min()*100) if base>0 else None,
            'new_start_equity':base,'position_and_equity_inherited':True})
    joined.to_csv(out/'comparison.csv',index=False);pd.DataFrame(summaries).to_csv(out/'paired_period_summary.csv',index=False)
    pd.DataFrame(common).to_csv(out/'same_old_start.csv',index=False)
    write_json(out/'completion.json',{'complete':True,'comparison_rows':len(joined),'common_start_accounts':len(common),'fixed_period_paired_summaries':len(summaries),'old_accounts_not_replayed':True})
    print('Comparison complete',len(joined),'rows',flush=True)

SETUP_JS='''
let crosses=[],events=[],focusCross=null;
const initialLoad=loadSegment;
function updateAdmission(){
 const s=DATA.segments[$('segment').value],a=$('arm').value,at=s?.starts?.[a],r=s?.summaries?.[a];
 $('admission').innerHTML=at?`<b>${esc(DATA.names[a])} · ${utcDay(at)} 00:00 UTC起可交易</b><br>${r?`收益 ${sign(r.return_pct)} · 最大回撤 ${pct(Math.abs(r.max_drawdown_pct))} · ${r.trades}笔交易。`:''} 灰色区域为指标准备期，K线仅供观察，不接受交易信号。`:'<b>这段历史在当前方案下没有可交易窗口。</b>';
 crosses=s?.crossByArm?.[a]||[];focusCross=null;
 $('cross').innerHTML='<option value="">选择一个穿越信号</option>'+crosses.map((x,i)=>`<option value="${i}">${utcDay(x[0]-86400000)} ${x[1]===1?'上穿':'下穿'} · ${esc(DATA.reasons[x[2]]||x[2])}</option>`).join('');
 $('crossRows').innerHTML=table(['信号收盘所属日 UTC','次日处理时间','方向','当前方案处理','顺向斜率ATR','成交编号'],crosses.map((x,i)=>[`<button onclick="document.getElementById('cross').value='${i}';focusSignal()">${utcDay(x[0]-86400000)}</button>`,utcTime(x[0]),x[1]===1?'多':'空',esc(DATA.reasons[x[2]]||x[2]),num(x[3],4),x[4]??'—']));
 const cs=s?.candidates?.[a]||[];$('candidates').innerHTML=cs.length?table(['处理日期','原穿越日','方向','状态','原因','等待天数'],cs.map(x=>[utcDay(x[0]),x[1]==null?'—':utcDay(x[1]),x[2]===1?'多':'空',esc(x[3]),esc(DATA.reasons[x[4]]||x[4]),x[5]??'—'])):'<p>当前方案没有等待候选记录。</p>';
}
loadSegment=function(){initialLoad();updateAdmission();};
function focusSignal(){const i=$('cross').value;focusCross=i===''?null:crosses[Number(i)];if(focusCross){chosen=null;$('trade').value='';let n=bars.findIndex(x=>x[0]>=focusCross[0]);lo=Math.max(0,n-12);hi=Math.min(bars.length,n+20);}draw();}
$('cross').oninput=focusSignal;$('showCrosses').oninput=draw;
'''
ENDING_JS='''
const naturalBaseDraw=draw;
draw=function(){naturalBaseDraw();const g=cv._range,s=activeSegment(),at=s.starts?.[$('arm').value];if(!g)return;const w=Math.max(300,cv.clientWidth||1000),height=w<640?400:490;const bound=at??g.finish;
 if(bound>g.start){ctx.save();ctx.fillStyle='#707b7d15';ctx.fillRect(g.left,g.top,g.X(Math.min(bound,g.finish))-g.left,height-g.top-g.bottom);ctx.fillStyle='#657067';ctx.font='11px system-ui';ctx.fillText('指标准备期',g.left+5,g.top+13);ctx.restore();}
 if(at&&at>=g.start&&at<=g.finish){ctx.save();ctx.strokeStyle='#768688';ctx.setLineDash([2,4]);ctx.beginPath();ctx.moveTo(g.X(at),g.top);ctx.lineTo(g.X(at),height-g.bottom);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle='#657067';ctx.fillText('开始接受交易',Math.min(g.X(at)+5,g.right-90),g.top+13);ctx.restore();}
};
const originalHover=hoverStopChart;
hoverStopChart=function(e,target){originalHover(e,target);const g=target._range;if(!g||!bars.length)return;const box=target.getBoundingClientRect(),at=g.start+(e.clientX-box.left-g.left)/(g.right-g.left)*(g.finish-g.start);const first=activeSegment().starts?.[$('arm').value];if(first==null||at<first){$('hint').textContent+=' · 指标准备期，不接受交易';$('chartTooltip').textContent=$('hint').textContent;}};
draw();updateAdmission();
'''

def crosses(d,t,e,start,end):
    result=[];mapping={(x.entry_time,int(x.side)):x.trade_id for x in t.itertuples()} if len(t) else {}
    for x in d[d.cross.ne(0)].itertuples():
        at=x.timestamp+pd.Timedelta(days=1)
        if at>=end:reason='sample_end';tid=None
        elif start is None or at<start:reason='not_ready';tid=None
        elif (at,int(x.cross)) in mapping:reason='filled';tid=mapping[(at,int(x.cross))]
        else:
            tid=None;hit=e[e.timestamp.eq(at)&e.side.eq(int(x.cross))] if len(e) else e
            if len(hit):reason=str(hit.reason.iloc[-1])
            elif len(t) and ((t.exit_time==at)&t.exit_reason.isin(['stop_gap','accel1_rsi30'])).any():reason='exit_priority_same_hour'
            elif len(t) and ((t.entry_time<at)&(t.exit_time>=at)).any():reason='position_occupied'
            else:raise AssertionError(('unclassified cross',str(at),start))
        result.append([int(at.timestamp()*1000),int(x.cross),reason,float(x.cross*x.slope) if np.isfinite(x.slope) else None,tid])
    return result

INDEX_JS='''
function refresh(){const p=$('period').value,a=$('arm').value,s=$('search').value.toLowerCase();let rows=DATA.rows.filter(r=>r.block===p&&r.case_id===a&&r.slug.toLowerCase().includes(s)&&(p==='full_segment'||r.status===$('coverage').value));rows.sort((x,y)=>$('sort').value==='delta'?(y.return_change_pp??-Infinity)-(x.return_change_pp??-Infinity):$('sort').value==='dd'?Math.abs(x.max_drawdown_pct)-Math.abs(y.max_drawdown_pct):y.return_pct-x.return_pct);
 $('count').textContent=rows.length+'个独立连续段；全段起止日不同，新增短段没有旧账户。';
 $('accounts').innerHTML=table(['币 / 连续段','新交易起点 UTC','旧交易起点 UTC','新收益','旧收益','变化百分点','新回撤','旧回撤','新/旧交易数','新胜率','新盈亏比'],rows.map(r=>[`<a href="coins/${encodeURIComponent(r.slug)}.html">${esc(r.slug)}</a> / ${esc(r.run_key.split('__').pop())}`,r.actual_start.slice(0,10),r.old_actual_start?.slice(0,10)??'无旧账户',sign(r.return_pct),sign(r.old_return_pct),num(r.return_change_pp),pct(Math.abs(r.max_drawdown_pct)),r.old_max_drawdown_pct==null?'—':pct(Math.abs(r.old_max_drawdown_pct)),r.closed_trades+' / '+(r.old_closed_trades??'—'),pct(r.win_rate_pct),num(r.unit_payoff_ratio)]));
 const z=DATA.summaries.filter(r=>r.block===p);$('overview').innerHTML=z.length?table(['相同完整区间配对','币数','新/旧盈利币','新/旧收益中位','新/旧回撤中位','改善/变差/不变'],z.map(r=>[esc(DATA.names[r.case_id]),r.paired_coins,r.new_profitable+' / '+r.old_profitable,num(r.new_median_return_pct)+'% / '+num(r.old_median_return_pct)+'%',num(r.new_median_drawdown_pct)+'% / '+num(r.old_median_drawdown_pct)+'%',r.improved+' / '+r.worsened+' / '+r.unchanged])):'<p>全段起止不同，不汇总成同一市场周期收益。可切换固定自然年区间比较。</p>';
}
$('period').innerHTML=options(DATA.labels);$('period').value='full_segment';$('arm').innerHTML=options(DATA.names);$('arm').value='V3';for(const id of ['period','arm','coverage','search','sort'])$(id).oninput=refresh;refresh();
$('allCodes').innerHTML=DATA.codes.map(x=>`<a style="display:inline-block;margin:5px 9px" href="coins/${encodeURIComponent(x)}.html">${esc(x)}</a>`).join('');
'''

def build_html():
    assert json.loads((R/'analysis/completion.json').read_text())['complete']
    out=R/'html';assert not out.exists();(out/'coins').mkdir(parents=True)
    renderer=Path(__file__).with_name('v3_stoplines_chart_20260913.js')
    js=COIN_JS.replace("'M_MANAGE'","'V3'")+SETUP_JS+renderer.read_text()+ENDING_JS
    # SETUP's wrapper runs only after renderer constants have been initialized.
    body=CHART_BODY.split('<details class="optional-evidence">')[0]
    body=body.replace('<div class="stop-charts">','<div id="admission" class="stop-detail"></div><div class="stop-charts">')
    body+='''<details class="optional-evidence"><summary>全部穿越与未开仓原因</summary><div class="filters"><select id="cross"></select><label><input type="checkbox" id="showCrosses">在图中标记穿越</label></div><div id="crossRows" class="scroll"></div><h2>候选处理记录</h2><div id="candidates" class="scroll"></div></details>'''
    reasons={'filled':'实际开仓','not_ready':'指标准备期／旧固定等待','sample_end':'信号后已到样本末','slope_rejected':'斜率未达标','position_occupied':'已有持仓','exit_priority_same_hour':'该小时先退出','nonpositive_equity':'权益不足','created':'建立候选','conditions_pending':'等待确认','confirmed':'首次确认','ma_side_invalid':'价格回到错误侧','fresh_cross_supersedes':'新穿越替换','sample_end_unresolved':'样本末尚未确认'}
    scope=pd.read_csv(R/'inputs/scope.csv');by={}
    for key,info in catalog().items():by.setdefault(info['slug'],[]).append(key)
    old_manifest=json.loads((OLD/'html_stoplines/artifact_checksums.json').read_text());count=0;stopcount=0
    for i,slug in enumerate(scope.slug,1):
        oldfile=OLD/'html_stoplines/coins'/(slug+'.html');assert sha(oldfile)==old_manifest['coins/'+slug+'.html'];original=decode(oldfile)
        segments={}
        for key in by.get(slug,[]):
            d,h,meta=load_new(key);del h;orig=original['segments'].get(key,{})
            seg={'from':str(d.timestamp.iloc[0].date()),'to':str(d.timestamp.iloc[-1].date()),'bars':packed(d,['timestamp','open','high','low','close','ma','ma30']),
                'dayIndicators':packed(d,['timestamp','atr','rsi']),'trades':{},'stops':{},'stopDetails':{},'candidates':{},'starts':{},'summaries':{},'crossByArm':{},'crosses':[],'events':[]}
            if orig:assert seg['bars']==orig['bars'] and seg['dayIndicators']==orig['dayIndicators']
            for arm in NAMES:
                old=arm.startswith('OLD_');base=arm.removeprefix('OLD_');p=old_directory(key,base) if old else R/'accounts'/key/base
                if p is None or not p.exists():
                    for name in ['trades','stops','stopDetails','candidates','crossByArm']:seg[name][arm]=[]
                    seg['starts'][arm]=None;continue
                summary=json.loads((p/'summary.json').read_text());seg['summaries'][arm]={k:summary[k] for k in ['return_pct','max_drawdown_pct','trades']}
                start=pd.Timestamp(summary['start']);seg['starts'][arm]=int(start.timestamp()*1000)
                t=table(p/'trades.csv');s=table(p/'stops.csv');e=table(p/'entry_events.csv')
                seg['trades'][arm]=packed(t,['trade_id','entry_time','exit_time','side','entry_price','exit_price','net_pnl','return_on_entry_equity','exit_reason']) if len(t) else []
                s['display_state']='V3移动止损'
                if 'tp_protect_active' not in s:s['tp_protect_active']=False
                seg['stops'][arm]=packed(s,['trade_id','timestamp','new_stop','display_state']) if len(s) else []
                seg['stopDetails'][arm]=packed(s,DETAIL_COLUMNS) if len(s) else [];stopcount+=len(s)
                cs=e[e.stage.astype(str).str.contains('candidate|wait')] if len(e) and base=='E_STATE' else pd.DataFrame()
                seg['candidates'][arm]=packed(cs,['timestamp','cross_day','side','status','reason','candidate_age_days']) if len(cs) else []
                seg['crossByArm'][arm]=crosses(d,t,e,start,pd.Timestamp(meta['end']))
                if old and orig:
                    assert seg['trades'][arm]==orig['trades'][base]
                    assert seg['stopDetails'][arm]==orig['stopDetails'][base]
            segments[key]=seg
        (out/'coins'/(slug+'.html')).write_text(page(slug+' · V3取消额外预热 · 全部交易与止损',body,{'names':NAMES,'segments':segments,'reasons':reasons},js))
        count+=len(segments)
        if i%100==0:print('HTML',i,680,flush=True)
    indexbody='''<p class="stats"><a href="coins/HYPE.html"><b>打开HYPE全部交易路径</b></a>：默认保留ATR止损阶梯虚线、收紧圆圈与倍数子图；可在新规则和旧等待规则之间切换。</p><p>只取消固定等待，MA7/ATR14/RSI6仍需有效值。新旧全段交易起点不同；切换自然年区间可查看双方完整覆盖的成对比较。提前持仓与资金延续到后续区间，不按年份重新开仓。</p><div class="filters">区间<select id="period"></select>方案<select id="arm"></select>覆盖<select id="coverage"><option value="COMPLETE">完整</option><option value="PARTIAL">部分历史</option></select>币<input id="search">排序<select id="sort"><option value="return">新收益</option><option value="delta">改善幅度</option><option value="dd">新回撤</option></select></div><div id="overview" class="scroll"></div><p id="count"></p><div id="accounts" class="scroll"></div><p><a href="../analysis/comparison.csv">全部逐币新旧结果</a> · <a href="../analysis/same_old_start.csv">固定旧起点的共同区间</a> · <a href="../results/entry_comparison.csv">全部入场得失</a> · <a href="../../../diagnostics/v3-no-extra-warmup-results-20260913.md">中文报告</a></p><details><summary>全部680币入口</summary><div id="allCodes"></div></details>'''
    data={'names':ARM_NAMES,'labels':LABELS,'rows':records(pd.read_csv(R/'analysis/comparison.csv')),'summaries':records(pd.read_csv(R/'analysis/paired_period_summary.csv')),'codes':scope.slug.tolist()}
    (out/'index.html').write_text(page('V3取消额外预热 · 全市场新旧对照',indexbody,data,INDEX_JS))
    write_json(out/'completion.json',{'complete':True,'pages':681,'segments':count,'displayed_stop_details':stopcount,'old_numeric_data_preserved':True,'default_dashed_stops_preserved':True,'browser_render_verified':False,'generator_sha256':sha(Path(__file__)),'renderer_sha256':sha(renderer)})
    write_json(out/'artifact_checksums.json',{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='artifact_checksums.json'})

def main():
    ap=argparse.ArgumentParser();ap.add_argument('stage',choices=['tables','html']);args=ap.parse_args()
    tables() if args.stage=='tables' else build_html()

if __name__=='__main__':main()
