"""Offline interactive evidence, with complete HYPE dashed stop paths."""
from report_fixed_atr_20260924 import *
NOTICE='<p class="note">每边手续费0.1%、滑点0.04%；已扣这两项，未包含完整资金费及强平执行。冻结行情截至2026-09-05 00:00 UTC。D=原V3每日ATR；F=固定入场信号日ATR。正式V3保持不变。</p>'
PAIR_JS=r'''
function pairTable(rs){return table(['入场 UTC','方向','关系','D退出','F退出','D单笔收益','F单笔收益','变化百分点','末尾估值'],rs.map(r=>[esc(r.entry_time.slice(0,16)),r.side===1?'多':'空',esc({same:'同入场',new:'新增',missed:'错失'}[r.relationship]||'固定入场'),esc(r.D_exit?.slice(0,16)||'—'),esc(r.F_exit?.slice(0,16)||'—'),sign(r.D_return_pct),sign(r.F_return_pct),num(r.delta_pp??(r.F_return_pct-r.D_return_pct)),r.D_terminal||r.F_terminal?'是':'否']));}
function accountTable(rs,coin=false){return table([coin?'币 / 连续段':'方案','起点 UTC','D收益','F收益','变化百分点','D回撤','F回撤','D/F笔数','同入场','错失/新增','原赢家转亏','前5赢家保留'],rs.map(r=>[coin?`<a href="${DATA.coinPrefix||''}${encodeURIComponent(r.slug)}.html">${esc(r.slug)}</a> / ${esc(r.run_key.split('__')[1])}`:`<button onclick="choose('${r.case_id}')">${esc(r.label)}</button>`,r.D_start.slice(0,10),sign(r.D_return_pct),sign(r.F_return_pct),num(r.delta_return_pp),pct(Math.abs(r.D_max_drawdown_pct)),pct(Math.abs(r.F_max_drawdown_pct)),r.D_trades+' / '+r.F_trades,r.same_entries,r.missed_baseline_entries+' / '+r.new_entries,r.winners_to_loss,pct(r.top5_retention_pct)]));}
'''
INDEX_JS=PAIR_JS+r'''
function choose(id){$('case').value=id;showCase();}
function showCase(){const id=$('case').value,r=DATA.hype.find(x=>x.case_id===id);$('account').innerHTML=accountTable([r]);$('pairs').innerHTML=pairTable(DATA.pairs.filter(x=>x.case_id===id));}
function near(){const g=DATA.neighbors.filter(r=>r.parameter===$('parameter').value).sort((a,b)=>a.value-b.value);$('near').innerHTML=accountTable(g.map(r=>({...r,label:String(r.value)+(r.case_id==='B'?' · V3':'' )})));}
function market(){let rs=DATA.market.filter(r=>$('scope').value==='all'||DATA.longest.includes(r.run_key));let q=$('search').value.toLowerCase();rs=rs.filter(r=>r.slug.toLowerCase().includes(q));
 if($('outcome').value==='better')rs=rs.filter(r=>r.delta_return_pp>1e-8);if($('outcome').value==='worse')rs=rs.filter(r=>r.delta_return_pp< -1e-8);
 const order=$('order').value;rs.sort((a,b)=>order==='alpha'?a.slug.localeCompare(b.slug):order==='worst'?a.delta_return_pp-b.delta_return_pp:order==='dd'?Math.abs(a.F_max_drawdown_pct)-Math.abs(b.F_max_drawdown_pct):b.delta_return_pp-a.delta_return_pp);
 $('count').textContent=`显示${rs.length}个连续段；各币起止不同。点币名可查全部连续段及交易。`;$('market').innerHTML=accountTable(rs,true);}
$('case').innerHTML=options(Object.fromEntries(DATA.hype.map(r=>[r.case_id,r.case_id==='original'?'原起点V3参数':r.label+' · 共同起点'])));$('case').value='original';$('case').oninput=showCase;
$('parameter').innerHTML=options(DATA.labels);$('parameter').oninput=near;
for(const id of ['scope','search','outcome','order'])$(id).oninput=market;
$('periods').innerHTML=table(['完整窗口','币数/可算收益','改善/恶化/不变','D/F盈利币','配对收益变化中位','配对回撤变化中位'],DATA.summaries.map(r=>[esc(r.sample),r.count+' / '+r.valid_pairs,r.improved+' / '+r.worsened+' / '+r.unchanged,r.D_profitable+' / '+r.F_profitable,num(r.median_delta_return_pp)+' pp',num(r.median_delta_drawdown_pp)+' pp']));
$('episodes').innerHTML=pairTable(DATA.episodes);showCase();near();market();
'''
COIN_TABLE_JS=PAIR_JS+r'''
function refresh(){const key=$('segment').value;const r=DATA.rows.find(r=>r.run_key===key);$('account').innerHTML=accountTable([r],true);$('pairs').innerHTML=pairTable(DATA.pairs.filter(r=>r.run_key===key));}
$('segment').innerHTML=options(Object.fromEntries(DATA.rows.map(r=>[r.run_key,r.run_key+' '+r.D_start.slice(0,10)+'—'+r.D_end_exclusive.slice(0,10)])));$('segment').oninput=refresh;refresh();
'''

def build_paths(hype):
 raw=pd.read_parquet(R/'input_daily.parquet');out=R/'html/coins';out.mkdir(parents=True,exist_ok=True);segments={}
 for case,key in [('original','原起点_2025-06-15'),('B','邻域共同起点_2025-06-19')]:
  row=hype[hype.case_id.eq(case)].iloc[0]
  seg={'from':'2025-06-01','to':str(raw.timestamp.iloc[-1].date()),'bars':packed(raw,['timestamp','open','high','low','close','ma','ma30']),'dayIndicators':packed(raw,['timestamp','atr','rsi']),'trades':{},'stops':{},'stopDetails':{},'candidates':{},'starts':{},'summaries':{},'crossByArm':{},'crosses':[],'events':[]}
  seg['from']=str(raw.timestamp.iloc[0].date())
  for arm in ['D','F']:
   p=ROOT/row[arm+'_path'];s,t,eq,st,_=v.read_result(p)
   event=p/'entry_events.csv'
   if not event.exists():
    event=v.NATURAL/'accounts/HYPE__seg001/V3/entry_events.csv';v.checked(event,v.manifest(str(v.NATURAL))[str(event.relative_to(v.NATURAL))])
   ev=v.table(event)
   seg['starts'][arm]=pd.Timestamp(s['start']).value//10**6;seg['summaries'][arm]={k:s[k] for k in ['return_pct','max_drawdown_pct','trades']}
   seg['trades'][arm]=packed(t,['trade_id','entry_time','exit_time','side','entry_price','exit_price','net_pnl','return_on_entry_equity','exit_reason'])
   st['display_state']='每日ATR' if arm=='D' else '固定入场ATR';st['tp_protect_active']=False
   seg['stops'][arm]=packed(st,['trade_id','timestamp','new_stop','display_state']);seg['stopDetails'][arm]=packed(st,DETAIL_COLUMNS);seg['candidates'][arm]=[]
   seg['crossByArm'][arm]=crosses(raw,t,ev,pd.Timestamp(s['start']),pd.Timestamp(s['end_exclusive']))
  segments[key]=seg
 body=CHART_BODY.split('<details class="optional-evidence">')[0].replace('← 全市场结果','← 固定ATR验证报告').replace('连续段</label>','账户起点</label>')
 body=body.replace('<div class="stop-charts">','<div id="admission" class="stop-detail"></div><div class="stop-charts">')
 body+='''<details class="optional-evidence"><summary>全部穿越与未开仓原因</summary><div class="filters"><select id="cross"></select><label><input type="checkbox" id="showCrosses">图中标记穿越</label></div><div id="crossRows" class="scroll"></div><div id="candidates"></div></details>'''
 body=NOTICE+'<p><b>先选账户起点，再切换D/F。</b>原起点结果544.76% → 537.60%；共同起点463.60% → 585.08%。虚线为实际生效的止损，不是事后计算的参考线。图中提示的收盘ATR仍是当天指标；固定版止损使用各自入场信号日ATR。</p>'+body
 js=COIN_JS.replace("'M_MANAGE'","'F'")+SETUP_JS+(MARKET/'scripts/v3_stoplines_chart_20260913.js').read_text()+ENDING_JS+"\n$('showMA30').oninput=draw;draw();"
 data={'names':{'D':'D · 原V3，每日ATR','F':'F · 固定入场ATR'},'segments':segments,'reasons':{'filled':'实际开仓','not_ready':'指标未就绪','sample_end':'样本末','slope_rejected':'斜率未达标','position_occupied':'已有持仓','exit_priority_same_hour':'该小时先退出'}}
 (out/'HYPE.html').write_text(page('HYPE · 固定入场ATR与原V3交易路径',body,data,js))

def main():
 h=pd.read_csv(R/'comparison.csv');c=pd.read_csv(X/'comparison.csv');longest=pd.read_csv(X/'longest_per_coin.csv');neighbors=pd.read_csv(R/'neighborhoods.csv');sums=pd.read_csv(X/'summary.csv');tp=pd.read_csv(X/'trade_pairs.csv');analysis=json.loads((R/'analysis.json').read_text())
 out=R/'html';out.mkdir(exist_ok=True);build_paths(h)
 crossroot=X/'html/coins';crossroot.mkdir(parents=True,exist_ok=True)
 for slug,g in c.groupby('slug',sort=False):
  body=NOTICE+'<p><a href="../index.html">← 全市场对照表</a></p><label>连续段 <select id="segment"></select></label><div id="account" class="scroll"></div><h2>全部交易配对</h2><p>单笔按入场权益收益比较。末尾估值不是自然退出；新增与错失包含持仓占用变化。无定义收益不补0。</p><div id="pairs" class="scroll"></div>'
  data={'rows':records(g),'pairs':records(tp[tp.slug.eq(slug)]),'coinPrefix':''}
  (crossroot/(slug+'.html')).write_text(page(slug+' · 动态与固定ATR全部交易',body,data,COIN_TABLE_JS))
 coinprefix=os.path.relpath(crossroot,out)+'/'
 body=NOTICE+'''<div class="stats"><b>结论：固定ATR不支持普遍替换V3。</b><br>HYPE原起点略差；较晚起点的高收益依赖一笔多单；649币仅295币改善。</div>
<p><a href="coins/HYPE.html"><b>打开HYPE K线、全部交易与ATR止损虚线</b></a> · <a href="../../../diagnostics/v3-fixed-atr-validation-results-20260924.md">完整中文报告</a></p>
<p>保持MA7更新与四日停滞后的每日收紧，只把持仓止损用的ATR固定在入场信号日。不是参数调优。所有原V3账户沿用旧结果，不重复全市场回测。</p>
<h2>两个起点与全部45组邻域</h2><p>原起点2025-06-15：544.76% → 537.60%，回撤27.26% → 28.98%。邻域共同起点2025-06-19：463.60% → 585.08%，剔除6月28日同一笔后，其余16笔457.66% → 456.51%。</p>
<label>参数 <select id="parameter"></select></label><div id="near" class="scroll"></div>
<h2>HYPE完整账户与逐笔得失</h2><label>账户 <select id="case"></select></label><div id="account" class="scroll"></div><div id="pairs" class="scroll"></div>
<details><summary>18笔固定入场对照：保持时间、方向、数量与权益</summary><p>每笔独立跑到自己的退出，不把这些探针串成复利账户。</p><div id="episodes" class="scroll"></div></details>
<h2>完整时间窗与等币对照</h2><p>配对变化先同币相减，再求中位数。回撤变化为正表示恶化。每币最长段起止不同，不能当统一市场周期。年2026只到9月4日；3币期初已破产，百分比无定义并单列。</p><div id="periods" class="scroll"></div>
<h2>全部币种：收益、回撤和交易</h2><p>649币、947段，排除HYPE及28个UNKNOWN。两方案各6个账户权益耗尽，未剔除。完整2020—2024只有BTC、ETH两币，不能代表全市场牛熊。</p>
<div class="filters"><label>样本 <select id="scope"><option value="longest">每币最长连续段 · 649</option><option value="all">全部连续段 · 947</option></select></label><label>结果 <select id="outcome"><option value="all">全部</option><option value="better">固定ATR收益改善</option><option value="worse">固定ATR收益变差</option></select></label><label>搜索 <input id="search" placeholder="例如 BTC、ETH"></label><label>排序 <select id="order"><option value="alpha">币名</option><option value="best">改善最多</option><option value="worst">恶化最多</option><option value="dd">固定版回撤最小</option></select></label></div><p id="count"></p><div id="market" class="scroll"></div>
<p class="note">已见历史诊断，非独立样本外证明。没有真实资金费完整核验、保证金强平及流动性执行，低于−100%的极端模型结果是风险失效证据，不能当真实永续最终净值。</p>'''
 data={'hype':records(h),'neighbors':records(neighbors),'pairs':records(pd.read_csv(R/'trade_pairs.csv')),'episodes':records(pd.read_csv(R/'fixed_entry_pairs.csv')),'labels':{r['parameter']:r['label'] for r in analysis['hype_neighborhoods']},'market':records(c),'longest':longest.run_key.tolist(),'summaries':records(sums),'coinPrefix':coinprefix}
 (out/'index.html').write_text(page('V3固定入场ATR · HYPE与649币验证',body,data,INDEX_JS))
 relative=os.path.relpath(out/'index.html',X/'html')
 (X/'html/index.html').write_text('<!doctype html><html lang="zh"><meta charset="utf-8"><title>固定ATR跨币验证</title><p><a href="'+relative+'">打开统一交互报告：649币、947段与全部交易</a></p></html>')
 v.write_json(R/'html_complete.json',{'complete':True,'hype_path_windows':2,'hype_path_arms':2,'hype_path_trades':int(h[h.case_id.isin(['B','original'])][['D_trades','F_trades']].sum().sum()),'cross_coin_pages':649,'cross_accounts':947,'all_cross_trade_pairs':len(tp),'browser_layout_verified':False})
 print('Built report, HYPE dashed stops and 649 coin trade pages',len(tp),flush=True)
if __name__=='__main__':main()
