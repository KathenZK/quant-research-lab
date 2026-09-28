"""HYPE-only interactive account and stop-path comparison; no new simulation."""
from pathlib import Path
import sys,json,html,re
import pandas as pd
ROOT=Path(__file__).resolve().parents[4]
BASE=Path(__file__).resolve().parents[1]
MARKET=ROOT/'research/asset-portfolios/1d-ma7-cross-atr-generalization/scripts'
sys.path.insert(0,str(MARKET))
from common import sha,write_json
from v3_no_extra_warmup_20260913 import load_new
from v3_opportunity_inputs_20260913 import table
from build_ma30_report_20260911 import STYLE,COMMON_JS,COIN_JS
from revise_v3_stoplines_20260913 import CSS,CHART_BODY,DETAIL_COLUMNS
from report_v3_no_extra_warmup_20260913 import SETUP_JS,ENDING_JS,packed,crosses

R=BASE/'artifacts/v3_immediate_floor_20260913'
NAMES={'B':'当前V3 · 原逐日收紧','A':'仅反向超0.2ATR一步到0.5','S':'仅四日停滞一步到0.5','AS':'用户方案 · 双触发一步到0.5'}
NOTICE='仅HYPE。取消额外固定预热，UTC 2025-06-15至2026-09-04；每边手续费0.1%、滑点0.04%。保留原开仓、空单加速加RSI6止盈，关闭反手。约1倍名义仓位，未知资金费未计入。'

def page(title,body,data,js):
    payload=json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('</','<\\/')
    return '<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+STYLE+CSS+'</style><main><h1>'+html.escape(title)+'</h1><p class="note">'+NOTICE+'</p>'+body+'</main><script>const DATA='+payload+';\n'+COMMON_JS+js+'</script></html>'

FLOOR_JS='''
const previousFloorDetail=updateTradeDetail;
updateTradeDetail=function(){previousFloorDetail();const all=activeSegment().floorEvents?.[$('arm').value]||[],rs=chosen?all.filter(x=>x[0]===chosen[0]):all;
 $('floorDetails').innerHTML=rs.length?table(['交易','触发日收盘 UTC','新止损生效','一步收紧原因','反向偏离MA7 ATR','未刷新天数','ATR倍数','实际止损'],rs.map(x=>[`<button onclick="selectStopTrade(${x[0]})">#${x[0]}</button>`,utcDay(x[1]),utcTime(x[2]),esc(DATA.floorReasons[x[3]]||x[3]),num(x[4],3),x[5],num(x[6],1)+' → '+num(x[7],1),priceText(x[8])+' → '+priceText(x[9])])):'<p>当前选择没有一步降到0.5的触发。</p>';
};
$('showMA30').oninput=draw;draw();
'''

def main():
    assert json.loads((R/'completion.json').read_text())['complete'];assert json.loads((R/'audit.json').read_text())['complete']
    out=R/'html';assert not out.exists();(out/'coins').mkdir(parents=True)
    d,h,m=load_new('HYPE__seg001');del h
    seg={'from':str(d.timestamp.iloc[0].date()),'to':str(d.timestamp.iloc[-1].date()),'bars':packed(d,['timestamp','open','high','low','close','ma','ma30']),
         'dayIndicators':packed(d,['timestamp','atr','rsi']),'trades':{},'stops':{},'stopDetails':{},'candidates':{},'starts':{},'summaries':{},'crossByArm':{},'floorEvents':{},'crosses':[],'events':[]}
    summaries=[];count=0;stops=0
    for arm in NAMES:
        p=R/'accounts'/arm;s=json.loads((p/'summary.json').read_text());t=table(p/'trades.csv');st=table(p/'stops.csv');ev=table(p/'entry_events.csv')
        seg['starts'][arm]=pd.Timestamp(s['start']).value//10**6
        seg['summaries'][arm]={k:s[k] for k in ['return_pct','max_drawdown_pct','trades']}
        seg['trades'][arm]=packed(t,['trade_id','entry_time','exit_time','side','entry_price','exit_price','net_pnl','return_on_entry_equity','exit_reason'])
        st['display_state']='一步收紧' if arm!='B' else '原V3逐日收紧';st['tp_protect_active']=False
        seg['stops'][arm]=packed(st,['trade_id','timestamp','new_stop','display_state'])
        seg['stopDetails'][arm]=packed(st,DETAIL_COLUMNS);seg['candidates'][arm]=[]
        seg['crossByArm'][arm]=crosses(d,t,ev,pd.Timestamp(s['start']),pd.Timestamp(s['end_exclusive']))
        jumps=st[st.jump_to_floor]
        seg['floorEvents'][arm]=packed(jumps,['trade_id','signal_day','timestamp','tightening_trigger','adverse_ma_distance_atr','no_new_extreme_days','old_mult','new_mult','old_stop','new_stop'])
        summaries.append({'arm':arm,'name':NAMES[arm],**s});count+=len(t);stops+=len(st)
    body=CHART_BODY.split('<details class="optional-evidence">')[0].replace('← 全市场结果','← 本次HYPE对照')
    body=body.replace('<div class="stop-charts">','<div id="admission" class="stop-detail"></div><div class="stop-charts">')
    body=body.replace('<h2>每日止损怎样收紧</h2>','<h2>每日止损怎样收紧</h2>')
    body+='<h2>哪一天、因为什么一步降到0.5</h2><div id="floorDetails" class="scroll"></div>'
    body+='''<details class="optional-evidence"><summary>全部穿越与未开仓原因</summary><div class="filters"><select id="cross"></select><label><input type="checkbox" id="showCrosses">在图中标记穿越</label></div><div id="crossRows" class="scroll"></div><div id="candidates"></div></details>'''
    body='<p><b>双触发规则：</b>多单收盘低于MA7−0.2ATR、空单收盘高于MA7＋0.2ATR；或最高/最低价连续4日不刷新。任一成立，止损倍数次日直接降到0.5，实际价格只收窄。</p>'+body
    renderer=MARKET/'v3_stoplines_chart_20260913.js'
    js=COIN_JS.replace("'M_MANAGE'","'AS'")+SETUP_JS+renderer.read_text()+ENDING_JS+FLOOR_JS
    reasons={'filled':'实际开仓','not_ready':'指标未就绪','sample_end':'样本末','slope_rejected':'斜率未达标','position_occupied':'已有持仓','exit_priority_same_hour':'该小时先退出','nonpositive_equity':'权益不足'}
    data={'names':NAMES,'segments':{'HYPE__seg001':seg},'reasons':reasons,
          'floorReasons':{'floor_adverse_ma':'反向超过MA7 0.2ATR','floor_stagnation':'最高/最低价四日未刷新','floor_both':'两条同时满足'}}
    (out/'coins/HYPE.html').write_text(page('HYPE · 双触发一步收紧 · 全部交易路径',body,data,js))
    cmp=pd.read_csv(R/'comparison.csv');paired=pd.read_csv(R/'trade_comparison.csv')
    for p in [cmp,paired]:p.replace([float('inf'),float('-inf')],None,inplace=True)
    body='''<p><a href="coins/HYPE.html"><b>打开全部K线、移动止损与逐笔触发原因</b></a></p><p>四个方案采用相同输入、起点和成本。默认图显示用户指定双触发方案，可切换原V3或单独一条改动；没有运行全市场。</p><div id="summary" class="scroll"></div><h2>逐笔同入场的得失及新增/错失交易</h2><div class="filters">方案<select id="arm"></select></div><div id="pairs" class="scroll"></div><p>同入场配对使用每笔入场权益收益，不能把这些差值相加当完整账户收益。原样本末结算的未自然结束交易仍明确保留。</p><p><a href="../comparison.csv">账户结果CSV</a> · <a href="../trade_comparison.csv">全部交易配对CSV</a> · <a href="../floor_triggers.csv">每次一步收紧CSV</a> · <a href="../../../diagnostics/v3-immediate-floor-results-20260913.md">完整结果说明</a></p>'''
    ix={'names':NAMES,'summary':json.loads(cmp.to_json(orient='records',double_precision=15)),'pairs':json.loads(paired.to_json(orient='records',double_precision=15))}
    ixjs='''$('summary').innerHTML=table(['方案','收益','最大回撤','笔数','胜率','单笔盈亏比','利润因子'],DATA.summary.map(r=>[esc(r.name),sign(r.return_pct),pct(Math.abs(r.max_drawdown_pct)),r.trades,pct(r.win_rate_pct),num(r.unit_payoff_ratio),num(r.profit_factor)]));
    function refresh(){const rs=DATA.pairs.filter(r=>r.arm===$('arm').value);$('pairs').innerHTML=table(['入场 UTC','方向','关系','原编号→新编号','原退出','新退出','原单收益','新单收益','变化百分点'],rs.map(r=>[r.entry_time.slice(0,16),r.side===1?'多':'空',r.relationship==='same_entry'?'同入场':r.relationship==='new_entry'?'新增入场':'原入场错失',(r.baseline_id??'—')+' → '+(r.new_id??'—'),r.baseline_exit?.slice(0,16)??'—',r.new_exit?.slice(0,16)??'—',sign(r.baseline_return_pct),sign(r.new_return_pct),num(r.delta_pp)]));}
    $('arm').innerHTML=options(Object.fromEntries(Object.entries(DATA.names).filter(x=>x[0]!=='B')));$('arm').value='AS';$('arm').oninput=refresh;refresh();'''
    (out/'index.html').write_text(page('HYPE · 原V3与双触发一步收紧',body,ix,ixjs))
    write_json(out/'completion.json',{'complete':True,'pages':2,'displayed_trades':count,'displayed_stops':stops,'default_arm':'AS','generator_sha256':sha(Path(__file__)),'renderer_sha256':sha(renderer),'browser_layout_verified':False})
    write_json(out/'artifact_checksums.json',{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file() and p.name!='artifact_checksums.json'})
    print('HYPE HTML complete',count,'trades',stops,'stops',flush=True)

if __name__=='__main__':main()
