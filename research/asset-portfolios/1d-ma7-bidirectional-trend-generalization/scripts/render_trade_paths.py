"""从冻结回放产物构建独立HTML，全部蜡烛/仓位/止损/权益/交易端点留在载荷。"""
from pathlib import Path
import json
import gzip
import argparse
import pandas as pd
from engine import Config,replay
from run_research import FAMILY,INPUT,sha,save,clean,groups,btc_reference

def main():
    p=argparse.ArgumentParser();p.add_argument('--run-id',default='p4-trade-paths-20260908')
    p.add_argument('--evaluation-dir',default='p1-evaluation-20260908-r1')
    p.add_argument('--selection-dir',default='p1-development-20260908-r1');args=p.parse_args()
    ev=FAMILY/'artifacts'/args.evaluation_dir;assert (ev/'completed.json').exists()
    out=FAMILY/'artifacts'/args.run_id;assert not out.exists();out.mkdir()
    candidate=json.loads((FAMILY/'artifacts'/args.selection_dir/'selection-lock.json').read_text())['selected_bidirectional_candidate']
    df=pd.read_csv(ev/'results.csv');main=df[df.window.eq('main')&df.asset_class.eq('COIN')&df.candidate.eq(candidate)].sort_values(['return_pct','symbol'])
    symbols=list(dict.fromkeys([main.symbol.iloc[0],main.symbol.iloc[len(main)//2],main.symbol.iloc[-1],'BTC/USDT:USDT','ETH/USDT:USDT','HYPE/USDT:USDT']))
    chosen=[];manifest=json.loads((INPUT/'frame-manifest.json').read_text());btc=btc_reference(manifest)
    for symbol in symbols:
        path=ev/'main-paths'/f'{symbol.split("/")[0]}.json.gz'
        if path.exists():
            with gzip.open(path,'rt') as h:j=json.load(h)
            chosen.append({'symbol':symbol,'label':symbol+' · 主639天','bars':j['bars'],'run':j['runs'][candidate],'scope':'主窗口，完整预热',
                'source_file':str(path.relative_to(FAMILY)),'source_sha256':sha(path)})
        else:
            gs=groups(symbol,manifest,btc)
            if not gs:continue
            f=max(gs,key=lambda x:len(x));r=replay(f,Config(candidate),start_idx=121)
            chosen.append({'symbol':symbol,'label':symbol+' · 部分历史','bars':f[['ts','open','high','low','close','ma7','atr14','quote_volume']].to_dict('records'),
                'run':r,'scope':'主窗口不合格；展示全部可用连续段，不计主分母','source_file':'artifacts/p0-inputs-20260908/frame-manifest.json','source_sha256':sha(INPUT/'frame-manifest.json')})
    stocknames=['AMZN','COIN','CRCL','HOOD','INTC','MSTR','PLTR','TSLA']
    for stock in stocknames:
        symbol=stock+'/USDT:USDT';gs=groups(symbol,manifest,btc);f=max(gs,key=lambda x:len(x));r=replay(f,Config(candidate),start_idx=121)
        chosen.append({'symbol':symbol,'label':stock+' · 股票合约短历史','bars':f[['ts','open','high','low','close','ma7','atr14','quote_volume']].to_dict('records'),
            'run':r,'scope':'真实股票合约，短历史价格诊断；不计主639天分母','source_file':'artifacts/p0-inputs-20260908/frame-manifest.json','source_sha256':sha(INPUT/'frame-manifest.json')})
    for case in chosen:
        r=case['run'];ts=r['trades'];n=len(case['bars'])
        assert len(r['nav'])==n and len(ts)==r['metrics']['n_trades']
        assert len({t['trade_id'] for t in ts})==len(ts)
        assert all(0<=t['entry_idx']<=t['exit_idx']<n for t in ts)
        for t in ts:
            assert str(case['bars'][t['entry_idx']]['ts'])==t['entry_ts']
            assert str(case['bars'][t['exit_idx']]['ts'])==t['exit_ts']
    payload=clean({'candidate':candidate,'selection_rule':'主样本收益最差/中位/最好 + 预先指定BTC/ETH/HYPE；八只180日股票全部展示','cases':chosen})
    html=TEMPLATE.replace('PAYLOAD_JSON',json.dumps(payload,ensure_ascii=False,separators=(',',':')))
    target=out/'MA7多空趋势_交易路径.html';target.write_text(html)
    save(out/'verification.json',{'status':'PAYLOAD_PASS','cases':len(chosen),'trades':sum(len(c['run']['trades']) for c in chosen),
        'cases_by_symbol':[{'symbol':c['symbol'],'trades':len(c['run']['trades']),'bars':len(c['bars'])} for c in chosen],
        'unique_ids_per_case':True,'all_endpoints_valid':True,'line_render_loop':'for(const t of c.run.trades)',
        'self_contained':True,'no_cdn':True,'html_sha256':sha(target),'renderer_sha256':sha(Path(__file__))})
    print(target)

TEMPLATE=r'''<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MA7 多空趋势 · 交易路径</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f5f4ef;color:#212925;font:14px system-ui,-apple-system,sans-serif}header{padding:25px 32px 14px;border-bottom:1px solid #cdd2cb}h1{font-size:25px;margin:0 0 7px;font-weight:600}p{margin:5px 0;color:#5c665e;line-height:1.6}.controls{display:flex;gap:10px;align-items:center;flex-wrap:wrap;padding:18px 32px 6px}select,button{font:inherit;border:1px solid #bdc6bd;background:#fff;padding:8px 12px;border-radius:4px}button{cursor:pointer}.metrics{display:flex;gap:30px;padding:10px 32px;flex-wrap:wrap}.metric{font-size:21px}.metric small{display:block;font-size:11px;color:#657367}.chart{margin:5px 24px;background:#fff;border:1px solid #d7dcd3;position:relative}canvas{display:block;width:100%;height:590px;touch-action:none}#tip{position:absolute;display:none;pointer-events:none;background:#20352eea;color:#fff;font-size:12px;padding:9px;border-radius:4px;white-space:pre;line-height:1.5}.range{padding:5px 32px 15px;display:flex;gap:12px;align-items:center}.range input{flex:1}main{padding:0 32px 30px}table{width:100%;border-collapse:collapse;font-size:12px;background:white}td,th{text-align:right;padding:9px 8px;border-bottom:1px solid #e3e7df}th{position:sticky;top:0;background:#ecf0e9}td:first-child,th:first-child{text-align:left}tr:hover{background:#f3f6ee}tbody tr{cursor:pointer}.tablebox{max-height:390px;overflow:auto;border:1px solid #d7dcd3}.long{color:#078562}.short{color:#c34450}#scope{font-size:12px}.legend{font-size:12px}footer{padding:0 32px 30px;color:#758173;font-size:12px}</style>
<header><h1>MA7 多空趋势 · 交易路径</h1><p id="intro"></p><p><strong>手续费与滑点后的价格诊断，未认证完整资金费与实际强平。</strong>绿色做多，红色做空；同日反手包含两边收费。日内止损只能定位到日K，不能把图上的日期当作精确成交时刻。</p></header>
<div class="controls"><select id="asset" aria-label="选择标的"></select><button id="tradewindow">研究窗口</button><button id="all">完整输入</button><button id="last">最近90天</button><span class="legend">MA7 蓝色 · 已生效止损虚线 · 开平仓以连线对应</span></div>
<div class="metrics" id="metrics"></div><div class="controls" id="scope"></div>
<div class="chart"><canvas id="chart"></canvas><div id="tip"></div></div><div class="range"><span id="dates"></span><input id="pan" type="range" min="0" max="1000" value="0" aria-label="平移时间窗口"></div>
<main><p>滚轮缩放，拖动平移，悬停查看行情与权益；点击逐笔交易定位。选择规则：收益最差、中位、最好，加预先指定标的；八只股票合约全部展示。</p><div class="tablebox"><table><thead><tr><th>交易 / 方向</th><th>信号收盘日</th><th>开仓</th><th>平仓</th><th>入场价</th><th>退出价</th><th>仓位数量</th><th>交易收益</th><th>退出原因</th></tr></thead><tbody id="trades"></tbody></table></div></main>
<footer>初始研究本金=1，入场名义上限约1倍。截尾估值不是策略退出信号。离线文件无需网络服务；保留完整输入、有效止损、仓位和逐笔记录。</footer>
<script id="payload" type="application/json">PAYLOAD_JSON</script><script>
const data=JSON.parse(document.getElementById('payload').textContent);const $=s=>document.querySelector(s);const cv=$('#chart'),ctx=cv.getContext('2d');let c,left=0,right=0,drag=null,hover=null;
const fmt=(n,k=2)=>n==null?'—':Number(n).toFixed(k);const date=s=>String(s).slice(0,10);const reasons={stop:'保护止损',gap_stop:'跳空止损',reverse_signal:'确认反手',confirmed_exit:'反向确认退出',raw_ma7_exit:'MA7退出',filter_exit:'筛选条件退出',end_of_test:'截尾估值',economic_bankruptcy:'经济本金耗尽'};
$('#intro').textContent='冻结候选 '+data.candidate+' · '+data.selection_rule;
data.cases.forEach((x,i)=>$('#asset').add(new Option(x.label,i)));
function select(i){c=data.cases[i];left=c.run.start_idx;right=c.bars.length-1;const m=c.run.metrics;
$('#metrics').innerHTML=[['价格诊断收益',fmt(m.return_pct)+'%'],['收盘权益最大回撤',fmt(m.mdd_pct)+'%'],['闭合交易',m.n_trades],['反手退出',m.reversal_exits],['持仓日占比',fmt(m.exposure_pct)+'%']].map(([a,b])=>`<div class="metric"><small>${a}</small>${b}</div>`).join('');$('#scope').textContent=c.scope;
$('#trades').innerHTML=c.run.trades.map(t=>`<tr data-id="${t.trade_id}"><td class="${t.side>0?'long':'short'}">${t.trade_id} · ${t.side>0?'多':'空'}${t.reversal_entry?' ↔反手':''}</td><td>${date(t.signal_ts)}</td><td>${date(t.entry_ts)}</td><td>${date(t.exit_ts)}</td><td>${fmt(t.entry_price,5)}</td><td>${fmt(t.exit_price,5)}</td><td>${fmt(t.units,6)}</td><td>${fmt(t.ret_pct)}%</td><td>${reasons[t.reason]||t.reason}</td></tr>`).join('');document.querySelectorAll('#trades tr').forEach(row=>row.onclick=()=>{let t=c.run.trades.find(x=>x.trade_id===Number(row.dataset.id));left=Math.max(0,t.entry_idx-10);right=Math.min(c.bars.length-1,Math.max(t.entry_idx+30,t.exit_idx+10));draw()});draw()}
function line(arr,col,yfun,dash=[]){ctx.beginPath();ctx.strokeStyle=col;ctx.lineWidth=1.3;ctx.setLineDash(dash);let drawing=false;for(let i=left;i<=right;i++){let v=arr[i];if(v==null||!Number.isFinite(v)){drawing=false;continue}let x=X(i),y=yfun(v);if(!drawing)ctx.moveTo(x,y);else ctx.lineTo(x,y);drawing=true}ctx.stroke();ctx.setLineDash([])}
let W,H,X,Y,YE;
function draw(){if(!c)return;left=Math.max(0,Math.round(left));right=Math.min(c.bars.length-1,Math.max(left+1,Math.round(right)));const dpr=window.devicePixelRatio||1;W=cv.clientWidth;H=590;cv.width=W*dpr;cv.height=H*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,W,H);const A=62,B=W-26;X=i=>A+(i-left)/(right-left)*(B-A);let view=c.bars.slice(left,right+1);let lo=Math.min(...view.map(x=>x.low)),hi=Math.max(...view.map(x=>x.high));let pad=(hi-lo)*.08||1;lo-=pad;hi+=pad;Y=v=>300-(v-lo)/(hi-lo)*265;let eq=c.run.nav.slice(left,right+1);let elo=Math.min(1,...eq),ehi=Math.max(1,...eq);let ep=(ehi-elo)*.1||.1;YE=v=>525-(v-elo+ep)/(ehi-elo+2*ep)*125;
ctx.font='11px system-ui';ctx.strokeStyle='#e8ede5';ctx.fillStyle='#687365';for(let j=0;j<5;j++){let y=35+j*265/4;ctx.beginPath();ctx.moveTo(A,y);ctx.lineTo(B,y);ctx.stroke();ctx.fillText(fmt(hi-j*(hi-lo)/4,2),6,y+4)}ctx.fillText('合约价格 / SMA7',A,18);ctx.fillText('持仓方向 / 数量见悬停',A,330);ctx.fillText('权益 · 初始本金1',A,386);
const width=Math.max(.7,Math.min(10,(B-A)/(right-left+1)*.65));for(let i=left;i<=right;i++){let b=c.bars[i],x=X(i);ctx.strokeStyle=ctx.fillStyle=b.close>=b.open?'#168d69':'#c7515a';ctx.beginPath();ctx.moveTo(x,Y(b.high));ctx.lineTo(x,Y(b.low));ctx.stroke();ctx.fillRect(x-width/2,Math.min(Y(b.open),Y(b.close)),width,Math.max(1,Math.abs(Y(b.close)-Y(b.open))));let side=c.run.active_sides[i];ctx.fillStyle=side>0?'#168d69':side<0?'#c7515a':'#e4e7df';ctx.fillRect(x-width/2,side>0?337:side<0?349:346,width,side?10:2)}
line(c.bars.map(x=>x.ma7),'#3b75b0',Y);line(c.run.active_stops,'#a07836',Y,[3,4]);line(c.run.nav,'#344d83',YE);
ctx.save();ctx.beginPath();ctx.rect(A-8,20,B-A+16,286);ctx.clip();for(const t of c.run.trades){if(t.exit_idx<left||t.entry_idx>right)continue;ctx.strokeStyle=t.side>0?'#06845b':'#c64051';ctx.fillStyle=ctx.strokeStyle;ctx.lineWidth=1.5;ctx.beginPath();ctx.moveTo(X(t.entry_idx),Y(t.entry_price));ctx.lineTo(X(t.exit_idx),Y(t.exit_price));ctx.stroke();for(const [i,p] of [[t.entry_idx,t.entry_price],[t.exit_idx,t.exit_price]]){ctx.beginPath();ctx.arc(X(i),Y(p),3,0,Math.PI*2);ctx.fill()}if(t.reversal_entry){ctx.font='bold 13px system-ui';ctx.fillText('↔',X(t.entry_idx)-5,Y(t.entry_price)-8)}}ctx.restore();ctx.fillStyle='#687365';ctx.fillText(fmt(ehi+ep),6,404);ctx.fillText(fmt(elo-ep),6,529);
for(let j=0;j<=5;j++){let i=Math.round(left+(right-left)*j/5);ctx.fillText(date(c.bars[i].ts),Math.max(A-22,Math.min(B-65,X(i)-25)),563)}$('#dates').textContent=date(c.bars[left].ts)+' → '+date(c.bars[right].ts);$('#pan').value=c.bars.length>right-left+1?left/(c.bars.length-(right-left+1))*1000:0;if(hover!=null){ctx.strokeStyle='#819280';ctx.setLineDash([3,3]);ctx.beginPath();ctx.moveTo(X(hover),25);ctx.lineTo(X(hover),535);ctx.stroke();ctx.setLineDash([])}}
cv.addEventListener('wheel',e=>{e.preventDefault();let span=right-left;const frac=Math.max(0,Math.min(1,(e.offsetX-62)/(cv.clientWidth-88)));let next=Math.max(20,Math.min(c.bars.length-1,Math.round(span*(e.deltaY>0?1.18:.84))));const centre=left+span*frac;left=Math.max(0,Math.min(c.bars.length-1-next,centre-next*frac));right=left+next;draw()},{passive:false});
cv.addEventListener('pointerdown',e=>{drag={x:e.clientX,left,right};cv.setPointerCapture(e.pointerId)});cv.addEventListener('pointerup',()=>drag=null);cv.addEventListener('pointermove',e=>{if(drag){const n=drag.right-drag.left;const shift=(e.clientX-drag.x)/(cv.clientWidth-88)*n;left=Math.max(0,Math.min(c.bars.length-1-n,drag.left-shift));right=left+n;draw();return}hover=Math.max(left,Math.min(right,Math.round(left+(e.offsetX-62)/(cv.clientWidth-88)*(right-left))));let b=c.bars[hover];$('#tip').style.display='block';$('#tip').style.left=Math.min(e.offsetX+12,cv.clientWidth-230)+'px';$('#tip').style.top=Math.max(8,Math.min(410,e.offsetY-25))+'px';$('#tip').textContent=date(b.ts)+'\nO '+fmt(b.open,5)+' H '+fmt(b.high,5)+'\nL '+fmt(b.low,5)+' C '+fmt(b.close,5)+'\nMA7 '+fmt(b.ma7,5)+' 止损 '+fmt(c.run.active_stops[hover],5)+'\n方向 '+c.run.active_sides[hover]+' 数量 '+fmt(c.run.active_units[hover],6)+'\n权益 '+fmt(c.run.nav[hover],4);draw()});cv.addEventListener('pointerleave',()=>{hover=null;$('#tip').style.display='none';draw()});
$('#asset').onchange=()=>select(Number($('#asset').value));$('#tradewindow').onclick=()=>{left=c.run.start_idx;right=c.bars.length-1;draw()};$('#all').onclick=()=>{left=0;right=c.bars.length-1;draw()};$('#last').onclick=()=>{right=c.bars.length-1;left=Math.max(0,right-89);draw()};$('#pan').oninput=()=>{const n=right-left;left=Number($('#pan').value)/1000*(c.bars.length-1-n);right=left+n;draw()};window.addEventListener('resize',draw);select(0);
</script></html>'''

if __name__=='__main__':main()
