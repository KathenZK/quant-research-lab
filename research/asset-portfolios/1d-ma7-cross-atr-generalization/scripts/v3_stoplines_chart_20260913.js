// Display-only restoration. Every price, stop and multiplier comes from saved accounts.
const stopColors={long:'#167566',short:'#c34e59',ma:'#347eb1',stop:'#a17124',tp:'#8560ac',muted:'#64726e'};
const DAY_MS=86400000;
const exitText={stop_intrahour:'盘中移动止损',stop_gap:'开盘越过止损',accel1_rsi30:'加速下跌＋RSI止盈',sample_end:'样本末结算'};
const utcDay=t=>new Date(t).toISOString().slice(0,10);
const utcTime=t=>new Date(t).toISOString().slice(0,16).replace('T',' ');
const priceText=x=>x==null?'—':num(x,Math.abs(x)<1?5:3);
function activeSegment(){return DATA.segments[$('segment').value]||{};}
function stopDetails(){return activeSegment().stopDetails?.[$('arm').value]||[];}
function detailsFor(t){return stopDetails().filter(s=>s[0]===t[0]);}
function initializeCanvas(canvas,height){
  const width=Math.max(300,canvas.clientWidth||cv.clientWidth||1000);
  const scale=globalThis.devicePixelRatio||1;
  canvas.width=Math.round(width*scale);canvas.height=Math.round(height*scale);
  canvas.style.height=height+'px';
  const c=canvas.getContext('2d');c.setTransform(scale,0,0,scale,0,0);c.clearRect(0,0,width,height);
  return {ctx:c,width,height};
}
function plotClip(c,g,height){c.save();c.beginPath();c.rect(g.left,g.top,g.right-g.left,height-g.top-g.bottom);c.clip();}
function marker(c,x,y,kind,color,size=5){
  c.fillStyle=color;c.strokeStyle=color;c.lineWidth=1.7;c.beginPath();
  if(kind==='long'){c.moveTo(x,y-size);c.lineTo(x+size,y+size);c.lineTo(x-size,y+size);c.closePath();c.fill();}
  else if(kind==='short'){c.moveTo(x,y+size);c.lineTo(x+size,y-size);c.lineTo(x-size,y-size);c.closePath();c.fill();}
  else if(kind==='stop'){c.moveTo(x,y-size);c.lineTo(x+size,y);c.lineTo(x,y+size);c.lineTo(x-size,y);c.closePath();c.fill();}
  else if(kind==='end')c.fillRect(x-size,y-size,size*2,size*2);
  else{c.arc(x,y,size,0,Math.PI*2);c.fill();}
}
function visibleStopSegments(){
  const result=[];
  for(const t of trades){
    const rows=detailsFor(t);
    for(let i=0;i<rows.length;i++){
      const s=rows[i],end=Math.min(t[2],rows[i+1]?.[1]??t[2]);
      if(s[1]>t[2]||end<s[1])continue;
      result.push({tradeId:t[0],start:s[1],end,price:s[9],mult:s[4],tightened:s[5],row:s});
    }
  }
  return result;
}
function drawStopPaths(c,g,segments,valueField){
  const drawn=[];let previous=null;
  for(const s of segments){
    const value=s[valueField];if(value==null)continue;
    c.globalAlpha=!chosen||chosen[0]===s.tradeId?1:.3;
    c.strokeStyle=stopColors.stop;c.lineWidth=chosen?.[0]===s.tradeId?2.5:1.7;
    c.setLineDash(valueField==='price'?[5,3]:[]);
    if(s.end>=g.start&&s.start<=g.finish){
      const a=Math.max(s.start,g.start),b=Math.min(s.end,g.finish);
      c.beginPath();c.moveTo(g.X(a),g.Y(value));c.lineTo(g.X(b),g.Y(value));c.stroke();
      // Only join consecutive updates of the same position, never two trades.
      if(previous?.tradeId===s.tradeId&&previous.end===s.start&&s.start>=g.start&&s.start<=g.finish){
        c.beginPath();c.moveTo(g.X(s.start),g.Y(previous[valueField]));c.lineTo(g.X(s.start),g.Y(value));c.stroke();
      }
      drawn.push({...s,drawStart:a,drawEnd:b});
      if(s.tightened&&s.start>=g.start&&s.start<=g.finish){
        c.setLineDash([]);c.fillStyle='#fff';c.beginPath();c.arc(g.X(s.start),g.Y(value),chosen?.[0]===s.tradeId?4:2.8,0,Math.PI*2);c.fill();c.stroke();
      }
    }
    previous=s;
  }
  c.globalAlpha=1;c.setLineDash([]);return drawn;
}
function updateTradeDetail(){
  const t=chosen;
  if(!t){
    const tightened=new Set(stopDetails().filter(s=>s[5]).map(s=>s[0])).size;
    $('tradeDetail').innerHTML=`<b>全部 ${trades.length} 笔交易 · 多 ${trades.filter(t=>t[3]===1).length} / 空 ${trades.filter(t=>t[3]===-1).length} · ${tightened} 笔触发ATR倍数收紧</b><br>土黄虚线是每笔仓位的实际止损，空心圆表示ATR倍数减少；下方阶梯显示倍数变化。点交易编号可放大并查看每天怎样收紧。`;
    $('stopAuditRows').innerHTML='<p>选择一笔交易，查看每一天的计时、ATR倍数和实际止损。</p>';
  }else{
    const rows=detailsFor(t),first=rows[0],last=rows.at(-1),changes=rows.filter(s=>s[5]);
    const armed=rows.find(s=>s[7]);
    $('tradeDetail').innerHTML=`<b>#${t[0]} ${t[3]===1?'做多':'做空'} · ${sign(t[7]*100)}</b><br>${utcTime(t[1])} @ ${priceText(t[4])} → ${utcTime(t[2])} @ ${priceText(t[5])} · ${esc(exitText[t[8]]||t[8])}<br><b>ATR倍数 ${num(first?.[4],1)} → ${num(last?.[4],1)}</b> · 减少 ${changes.length} 次 · 实际止损 ${priceText(first?.[9])} → ${priceText(last?.[9])}${armed?' · '+utcDay(armed[1])+' 起收紧生效':''}`;
    $('stopAuditRows').innerHTML=table(['止损生效时间 UTC','依据日K收盘','未创新高/低','收紧状态','ATR倍数','实际止损','备注'],rows.map(s=>[
      utcTime(s[1]),utcDay(s[2]),s[14]?s[6]+'天':'入场',s[7]?'已启动':'未启动',num(s[3],1)+' → '+num(s[4],1),
      priceText(s[8])+' → '+priceText(s[9]),s[5]?(s[8]===s[9]?'倍数减少；实际线未移动':'倍数减少；实际线收紧'):s[11]?'空单保护已启动':s[8]!==s[9]?'跟随中轴收紧':'保持']));
  }
  const index=t?trades.findIndex(x=>x[0]===t[0]):-1;
  $('previousTrade').disabled=!trades.length||index===0;
  $('nextTrade').disabled=!trades.length||index===trades.length-1;
}
draw=function(){
  const height=(cv.clientWidth||1000)<640?400:490,frame=initializeCanvas(cv,height),c=frame.ctx,w=frame.width;
  const atrCanvas=$('atrChart'),af=initializeCanvas(atrCanvas,130);
  cv._stopSegments=[];atrCanvas._stopSegments=[];
  if(!bars.length){cv._range=null;atrCanvas._range=null;$('hint').textContent='没有本轮可用价格段';$('viewRange').textContent='无可用连续交易段';updateTradeDetail();return;}
  lo=Math.max(0,Math.min(Math.round(lo),Math.max(0,bars.length-1)));
  hi=Math.min(bars.length,Math.max(lo+1,Math.round(hi)));
  const visible=bars.slice(lo,hi),start=visible[0][0],finish=visible.at(-1)[0]+DAY_MS;
  const segments=visibleStopSegments(),vals=visible.flatMap(b=>[b[2],b[3]]);
  for(const b of bars){const at=b[0]+DAY_MS;if(at>=start&&at<=finish){if(b[5]!=null)vals.push(b[5]);if($('showMA30').checked&&b[6]!=null)vals.push(b[6]);}}
  for(const s of segments)if(s.end>=start&&s.start<=finish)vals.push(s.price);
  for(const t of trades){if(t[1]>=start&&t[1]<=finish)vals.push(t[4]);if(t[2]>=start&&t[2]<=finish)vals.push(t[5]);}
  let min=Math.min(...vals),max=Math.max(...vals),pad=(max-min)*.08||Math.abs(max)*.01||1;min-=pad;max+=pad;
  const g={start,finish,left:w<640?57:70,right:w-16,top:24,bottom:30};
  g.X=t=>g.left+(t-start)/(finish-start)*(g.right-g.left);
  g.Y=p=>height-g.bottom-(p-min)/(max-min)*(height-g.top-g.bottom);
  c.font='11px system-ui';c.fillStyle=stopColors.muted;
  for(let i=0;i<=5;i++){const p=min+(max-min)*i/5,y=g.Y(p);c.strokeStyle='#e6eae6';c.lineWidth=1;c.beginPath();c.moveTo(g.left,y);c.lineTo(g.right,y);c.stroke();c.fillText(priceText(p),3,y+4);}
  plotClip(c,g,height);
  for(const t of trades){if(t[2]<start||t[1]>finish)continue;c.fillStyle=t[3]===1?(chosen?.[0]===t[0]?'#16756620':'#1675660b'):(chosen?.[0]===t[0]?'#c34e5920':'#c34e590b');c.fillRect(g.X(Math.max(start,t[1])),g.top,g.X(Math.min(finish,t[2]))-g.X(Math.max(start,t[1])),height-g.top-g.bottom);}
  const bw=Math.max(.7,(g.right-g.left)/visible.length*.58);
  for(const b of visible){const x=g.X(b[0]+DAY_MS/2);c.strokeStyle=b[4]>=b[1]?stopColors.long:stopColors.short;c.fillStyle=c.strokeStyle;c.lineWidth=1;c.beginPath();c.moveTo(x,g.Y(b[2]));c.lineTo(x,g.Y(b[3]));c.stroke();c.fillRect(x-bw/2,Math.min(g.Y(b[1]),g.Y(b[4])),bw,Math.max(1,Math.abs(g.Y(b[1])-g.Y(b[4]))));}
  for(const [col,color] of [[5,stopColors.ma],...( $('showMA30').checked?[[6,'#9aa5a5']]:[])]){
    c.strokeStyle=color;c.lineWidth=col===5?1.7:1.1;c.beginPath();let begun=false;
    for(const b of bars){const at=b[0]+DAY_MS;if(at<start-DAY_MS||at>finish+DAY_MS||b[col]==null)continue;if(begun)c.lineTo(g.X(at),g.Y(b[col]));else{c.moveTo(g.X(at),g.Y(b[col]));begun=true;}}c.stroke();
  }
  cv._stopSegments=drawStopPaths(c,g,segments,'price');
  if(chosen){const armed=detailsFor(chosen).find(s=>s[7]);if(armed&&armed[1]>=start&&armed[1]<=finish){c.strokeStyle=stopColors.stop;c.setLineDash([3,5]);c.beginPath();c.moveTo(g.X(armed[1]),g.top);c.lineTo(g.X(armed[1]),height-g.bottom);c.stroke();c.setLineDash([]);c.fillStyle=stopColors.stop;c.fillText('启动收紧',g.X(armed[1])+5,g.top+12);}}
  for(const t of trades){
    if(t[2]<start||t[1]>finish)continue;c.globalAlpha=!chosen||chosen[0]===t[0]?1:.35;
    c.strokeStyle=t[7]>=0?stopColors.long:stopColors.short;c.lineWidth=chosen?.[0]===t[0]?1.8:1;c.beginPath();c.moveTo(g.X(t[1]),g.Y(t[4]));c.lineTo(g.X(t[2]),g.Y(t[5]));c.stroke();
    for(const entry of [true,false]){const at=entry?t[1]:t[2],price=entry?t[4]:t[5];if(at<start||at>finish)continue;
      const kind=entry?(t[3]===1?'long':'short'):t[8].startsWith('stop')?'stop':t[8]==='sample_end'?'end':'tp';
      const color=kind==='long'?stopColors.long:kind==='short'?stopColors.short:kind==='stop'?stopColors.stop:kind==='tp'?stopColors.tp:stopColors.muted;
      marker(c,g.X(at),g.Y(price),kind,color,chosen?.[0]===t[0]?6:4.5);
      if(!chosen||chosen[0]===t[0]){const label=entry?'#'+t[0]+(t[3]===1?' 多':' 空'):chosen?'#'+t[0]+' '+(kind==='stop'?'止损':kind==='tp'?'止盈':'结算'):'';c.fillStyle=color;if(label)c.fillText(label,g.X(at)+5,g.Y(price)+(entry?-9:17));}
    }
  }
  c.globalAlpha=1;
  const marked=focusCross?[focusCross]:$('showCrosses').checked?crosses:[];
  for(const r of marked){if(r[0]<start||r[0]>finish)continue;const b=bars.find(b=>b[0]===r[0]);if(!b)continue;const x=g.X(r[0]),y=g.Y(b[1]);c.strokeStyle=r[2]==='slope_rejected'?'#ba8114':r[2]==='filled'?stopColors.long:'#87918a';c.lineWidth=focusCross?2.5:1.2;c.beginPath();c.rect(x-5,y-5,10,10);c.stroke();}
  c.restore();
  c.fillStyle=stopColors.muted;const ticks=w<640?2:4;
  for(let i=0;i<=ticks;i++){const at=start+(finish-start)*i/ticks;c.fillText(utcDay(at),Math.max(g.left,Math.min(g.right-66,g.X(at)-30)),height-9);}
  cv._range=g;
  const ac=af.ctx,ag={...g,left:g.left,right:af.width-16,top:19,bottom:25};
  ag.X=t=>ag.left+(t-start)/(finish-start)*(ag.right-ag.left);ag.Y=m=>af.height-ag.bottom-(m-.4)/(1.6-.4)*(af.height-ag.top-ag.bottom);
  ac.font='11px system-ui';ac.fillStyle=stopColors.muted;ac.fillText('ATR倍数',3,12);
  for(const m of [.5,1,1.5]){ac.fillText(num(m,1),25,ag.Y(m)+4);ac.strokeStyle='#e6eae6';ac.beginPath();ac.moveTo(ag.left,ag.Y(m));ac.lineTo(ag.right,ag.Y(m));ac.stroke();}
  plotClip(ac,ag,af.height);atrCanvas._stopSegments=drawStopPaths(ac,ag,segments,'mult');ac.restore();atrCanvas._range=ag;
  ac.fillStyle=stopColors.muted;ac.fillText('1.5 → 0.5；每笔重新开始，空仓断开',ag.left,af.height-5);
  $('viewRange').textContent=utcDay(start)+' — '+utcDay(finish-DAY_MS)+' · '+visible.length+'根日K · UTC';
  updateTradeDetail();
};
function refreshTradeTable(){
  $('tradeRows').innerHTML=table(['交易','方向','开仓 UTC','平仓 UTC','单笔收益','退出原因','ATR倍数'],trades.map(t=>{const s=detailsFor(t);return [`<button type="button" onclick="selectStopTrade(${t[0]})">#${t[0]} 查看</button>`,t[3]===1?'做多':'做空',utcTime(t[1]),utcTime(t[2]),sign(t[7]*100),esc(exitText[t[8]]||t[8]),num(s[0]?.[4],1)+' → '+num(s.at(-1)?.[4],1)];}));
}
const earlierLoadStopView=loadSegment;
loadSegment=function(){earlierLoadStopView();refreshTradeTable();draw();};
focusTrade=function(){
  chosen=currentTrade();focusCross=null;$('cross').value='';
  if(chosen){let i=bars.findIndex(b=>b[0]+DAY_MS>chosen[1]),j=bars.findIndex(b=>b[0]>=chosen[2]);lo=Math.max(0,i-12);hi=Math.min(bars.length,(j<0?bars.length:j)+15);}else{lo=0;hi=bars.length;}draw();
};
function selectStopTrade(id){$('trade').value=String(id);focusTrade();}
function stepStopTrade(direction){const i=chosen?trades.findIndex(t=>t[0]===chosen[0]):direction>0?-1:trades.length;const t=trades[i+direction];if(t)selectStopTrade(t[0]);}
function showAllStops(){chosen=null;focusCross=null;$('trade').value='';$('cross').value='';lo=0;hi=bars.length;draw();}
$('previousTrade').onclick=()=>stepStopTrade(-1);$('nextTrade').onclick=()=>stepStopTrade(1);
$('fullView').onclick=showAllStops;$('recentView').onclick=()=>{chosen=null;focusCross=null;$('trade').value='';lo=Math.max(0,bars.length-120);hi=bars.length;draw();};
$('showMA30').oninput=draw;$('segment').oninput=loadSegment;$('arm').oninput=loadSegment;$('trade').oninput=focusTrade;
let stopDrag=null;
function hoverStopChart(e,target){
  if(stopDrag){const span=stopDrag.hi-stopDrag.lo;const n=Math.round((stopDrag.x-e.clientX)/(target.clientWidth||1000)*span);lo=Math.max(0,Math.min(bars.length-span,stopDrag.lo+n));hi=lo+span;draw();return;}
  const g=target._range;if(!g||!bars.length)return;
  const box=target.getBoundingClientRect(),at=g.start+(e.clientX-box.left-g.left)/(g.right-g.left)*(g.finish-g.start);
  const day=Math.floor(at/DAY_MS)*DAY_MS,b=bars.find(x=>x[0]===day);if(!b)return;
  const trade=trades.find(t=>t[1]<=at&&t[2]>=at),s=trade?detailsFor(trade).filter(r=>r[1]<=at).at(-1):null;
  const ind=activeSegment().dayIndicators?.find(r=>r[0]===day),f=priceText;
  const message=`${utcDay(day)} · 开 ${f(b[1])} 高 ${f(b[2])} 低 ${f(b[3])} 收 ${f(b[4])} · 收盘MA7 ${f(b[5])}`+(s?` · #${trade[0]} ${trade[3]===1?'多':'空'} 当时止损 ${f(s[9])} · ATR倍数 ${num(s[4],1)} · 未刷新 ${s[6]}天${s[5]?' · 当日减少倍数':''}${s[11]?' · 空单保护':''}`:' · 此时空仓')+(ind?` · 当日收盘ATR14 ${f(ind[1])}`:'');
  $('hint').textContent=message;
  const tip=$('chartTooltip');tip.textContent=message;tip.hidden=false;
  tip.style.left=Math.max(4,Math.min((cv.clientWidth||1000)-285,e.clientX-box.left+12))+'px';tip.style.top=Math.max(8,(e.clientY??80)-box.top-25)+'px';
}
for(const target of [cv,$('atrChart')]){
  target.onwheel=e=>{e.preventDefault();if(!bars.length)return;const span=hi-lo,change=Math.max(2,Math.round(span*.15)),g=target._range;const fraction=g?Math.max(0,Math.min(1,((e.clientX??(g.left+g.right)/2)-target.getBoundingClientRect().left-g.left)/(g.right-g.left))):.5;const next=Math.min(bars.length,Math.max(Math.min(10,bars.length),span+(e.deltaY>0?change:-change)));lo=Math.max(0,Math.min(bars.length-next,Math.round(lo+span*fraction-next*fraction)));hi=lo+next;draw();};
  target.onpointerdown=e=>{stopDrag={x:e.clientX,lo,hi};target.setPointerCapture(e.pointerId);$('chartTooltip').hidden=true;};
  target.onpointerup=()=>{stopDrag=null;};target.onpointercancel=()=>{stopDrag=null;};
  target.onpointermove=e=>hoverStopChart(e,target);target.onpointerleave=()=>{$('chartTooltip').hidden=true;};target.ondblclick=showAllStops;
}
if(globalThis.addEventListener)globalThis.addEventListener('resize',draw);
loadSegment();
