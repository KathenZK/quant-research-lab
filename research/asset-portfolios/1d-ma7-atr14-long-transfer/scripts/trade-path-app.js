(() => {
  'use strict';
  const ALL = JSON.parse(document.getElementById('backtest-data').textContent);
  let coin='BTC', windowName='available', D=ALL[coin][windowName];
  const $ = id => document.getElementById(id);
  let dates = D.bars.map(b => b.date), indexByDate = new Map(dates.map((d,i) => [d,i]));
  const C = {ink:'#35473e',muted:'#7a8278',grid:'#eceee7',green:'#277963',red:'#b35d59',gold:'#b59249',blue:'#62859a',grey:'#aeb7ae'};
  const f = (n, digits=2) => Number(n).toLocaleString('en-US',{minimumFractionDigits:digits,maximumFractionDigits:digits});
  const pct = n => (n >= 0 ? '+' : '') + f(n) + '%';
  const sign = n => n >= 0 ? 'positive' : 'negative';
  const pad = n => String(n+1).padStart(2,'0');
  let mode='causal_binance_cost', selected=null, showMA=true, showStop=true;
  const current = () => D.runs[mode];
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const chart = echarts.init($('chart'),null,{renderer:'canvas',devicePixelRatio:Math.min(window.devicePixelRatio||1,2)});

  function displayStats() {
    const m=current().metrics;
    $('total-return').textContent=pct(m.total_return_pct);
    $('max-dd').textContent=f(m.max_drawdown_pct)+'%';
    $('avg-hold').textContent=f(m.avg_hold_days)+' 天';
    $('trade-count').innerHTML=m.n_trades+`<small>终点结算 ${m.final_valuation_exits} 笔</small>`;
    $('win-rate').textContent=f(m.win_rate_pct,1)+'%';
    $('total-return').className=sign(m.total_return_pct);
    $('header-range').textContent=dates[0]+' — '+dates[dates.length-1];
    $('header-count').textContent=dates.length+' 根完整日K · UTC';
    $('eyebrow').textContent=coin+' / BINANCE / LONG ONLY / DAILY';
    $('mode-select').value=mode;
    $('chart').setAttribute('aria-label',coin+' 日K图，标注 '+m.n_trades+' 笔多头交易及净值、回撤');
    $('mode-description').textContent = (mode==='literal'
      ? '原规则：信号日收盘买入，当天完整 MA / ATR 上调后的止损检查当天最低价，存在日内前视，仅供原稿对拍。'
      : '时序修正：收盘信号后次日开盘买入；前日收盘确定本日止损，跳空按开盘价退出。')
      + ` 每次成交手续费 ${m.fee_bps_per_fill} bps，滑点 ${m.slippage_bps_per_fill} bps；未计资金费率。各币独立本金 1，不是组合收益。`
      + (windowName==='common'?'共同窗口从 2025-12-24 重新空仓开始。':'可用长窗口：六币从 2024-12-05 开始，LIT 从 2025-12-24 开始。');
    $('summary-body').innerHTML=Object.keys(ALL).map(c=>{const x=ALL[c][windowName].runs[mode].metrics;return `<tr data-coin="${c}" class="${c===coin?'selected':''}"><td><button class="trade-link" data-coin="${c}">${c}</button></td><td>${x.first_date}</td><td class="${sign(x.total_return_pct)}">${pct(x.total_return_pct)}</td><td>${f(x.max_drawdown_pct)}%</td><td>${x.n_trades}</td><td class="${sign(x.buyhold_return_pct)}">${pct(x.buyhold_return_pct)}</td></tr>`}).join('');
    $('trade-select').innerHTML=`<option value="all">全部 ${m.n_trades} 笔</option>`+current().trades.map((t,i)=>`<option value="${i}">#${pad(i)} · ${t.entry_date} · ${pct(t.ret_pct)}</option>`).join('');
    $('trade-select').value=selected===null?'all':String(selected);
  }

  function renderInspector() {
    const r=current(), t=selected===null?null:r.trades[selected];
    $('prev').disabled=selected===null || selected===0;
    $('next').disabled=r.trades.length===0||selected===r.trades.length-1;
    $('inspection-label').textContent=t?`TRADE ${pad(selected)} / ${r.trades.length}`:'TRADE EXPLORER';
    const el=$('inspector-body');
    el.className='inspector-body '+(t?'selected':'overview');
    if(!t) {
      el.innerHTML=`<h2>沿着 ${r.trades.length} 笔交易看</h2><p>底色标记持仓区间，虚线连接实际买卖价。点击下方编号，放大一段完整交易。</p><div class="trade-map">${r.trades.map((x,i)=>`<button type="button" data-trade="${i}" aria-label="查看第 ${i+1} 笔交易，收益 ${pct(x.ret_pct)}"><span>#${pad(i)}</span><span class="${sign(x.ret_pct)}">${pct(x.ret_pct)}</span></button>`).join('')}</div><div class="note">绿色区间为最终盈利交易，红色为亏损交易。底色依据已知结果标注，不是交易信号。<br><br>◆ 菱形表示回测终点估值结算，不是策略卖出信号。</div>`;
      return;
    }
    const exitLabel=t.reason==='end_of_test'?'终点结算':t.reason==='gap_stop'?'跳空止损':'日内止损';
    const entryLabel=mode==='literal'?'信号日收盘':'次日开盘';
    const kind=t.reason==='end_of_test'?'回测终点结算':t.ret_pct>0?'盈利交易':'亏损交易';
    el.innerHTML=`<h2>第 ${pad(selected)} 笔 · ${kind}</h2><div class="big-return ${sign(t.ret_pct)}">${pct(t.ret_pct)}</div>
      <div class="detail-row"><span>买入 · ${entryLabel}</span><div><strong>$${f(t.entry_price,4)}</strong><span class="date">${t.entry_date}</span></div></div>
      <div class="detail-row"><span>退出 · ${exitLabel}</span><div><strong>$${f(t.exit_price,4)}</strong><span class="date">${t.exit_date}</span></div></div>
      <div class="detail-row"><span>持仓天数</span><strong>${t.hold_days} 天</strong></div>
      <div class="detail-row"><span>交易前 → 交易后净值</span><strong>${f(t.equity_before,3)} → ${f(t.equity_after,3)}</strong></div>
      <div class="detail-pair"><div><span>最高日收盘浮盈</span><strong class="${sign(t.max_close_return_pct)}">${pct(t.max_close_return_pct)}</strong></div><div><span>退出相对最高估值回落</span><strong>${f(t.giveback_from_peak_pct)}%</strong></div></div>
      <div class="event-track"><div><b>${t.signal_date} · 入场信号</b><span>收盘上穿 MA7，MA7 斜率为正</span></div><div><b>初始止损 $${f(t.initial_stop,3)}</b><span>只上移，不随价格回落而下移</span></div><div><b>${t.reason==='end_of_test'?'终点时止损':'离场时止损'} $${f(t.final_stop,3)}</b><span>${exitLabel} · ${t.exit_date}</span></div></div>
      <div class="note">${t.reason==='end_of_test'?'此处按最后一根已收盘日K估值平仓，不能视为策略卖出信号。':'最高浮盈只使用入场后、退出前的日收盘估值；回落同时计入最终成交价。'}<br>图中虚线仅连接买卖价，不表示日内价格路径。</div>`;
  }

  function renderTable() {
    $('trade-table').innerHTML=current().trades.map((t,i)=>`<tr data-trade="${i}" class="${i===selected?'selected':''}" aria-selected="${i===selected}"><td><button type="button" data-trade="${i}" class="trade-link" aria-label="查看第 ${i+1} 笔交易">#${pad(i)}</button></td><td>${t.entry_date}</td><td>${f(t.entry_price,4)}</td><td>${t.exit_date}</td><td>${f(t.exit_price,4)}</td><td class="${sign(t.ret_pct)}">${pct(t.ret_pct)}</td><td>${t.hold_days} 天<span class="holding-bar" style="width:${t.hold_days}px"></span></td><td>${t.reason==='end_of_test'?'<span class="end-tag">终点结算</span>':t.reason==='gap_stop'?'跳空止损':'止损离场'}</td></tr>`).join('');
  }

  function tooltip(params) {
    if(!Array.isArray(params)) params=[params];
    const p=params.find(x=>x.axisValue!==undefined);
    if(!p) return '';
    const date=String(p.axisValue),i=indexByDate.get(date);
    if(i===undefined) return '';
    const b=D.bars[i],r=current();
    const holdings=r.trades.map((t,j)=>({t,j})).filter(x=>i>=x.t.entry_idx&&i<=x.t.exit_idx);
    const rows=[['开盘',f(b.open,3)],['最高 / 最低',f(b.high,3)+' / '+f(b.low,3)],['收盘',f(b.close,3)]];
    if(showMA&&D.ma[i]!==null) rows.push(['MA7',f(D.ma[i],3)]);
    if(showStop&&r.display_stops[i]!==null) rows.push(['本日绘制止损',f(r.display_stops[i],3)]);
    rows.push(['策略净值',f(r.nav[i],4)],['日收盘回撤',f(-r.drawdowns[i]*100)+'%']);
    let events='';
    for(const {t,j} of holdings) {
      const action=i===t.entry_idx?'买入':i===t.exit_idx?(t.reason==='end_of_test'?'终点结算':'止损退出'):'持仓中';
      const mark=i===t.exit_idx?t.exit_price:(mode==='literal'&&i===t.entry_idx?t.entry_price:b.close);
      events+=`<div class="tooltip-event"><b>#${pad(j)} ${action}</b> · ${pct((mark/t.entry_price-1)*100)}<br>${i===t.entry_idx?'买入价 $'+f(t.entry_price,4):i===t.exit_idx?'退出价 $'+f(t.exit_price,4):'以当日日收盘价估值'}</div>`;
    }
    return `<div class="tooltip-wrap"><div class="tooltip-title">${date} · UTC</div>${rows.map(([k,v])=>`<div class="tooltip-row"><span>${k}</span><b>${v}</b></div>`).join('')}${events}</div>`;
  }

  function renderChart() {
    const r=current(), h=$('chart').clientHeight, w=$('chart').clientWidth, narrow=w<570;
    const left=narrow?46:55,right=narrow?14:25;
    const priceTop=25,priceHeight=Math.round(h*.48),navTop=Math.round(h*.58),navHeight=Math.round(h*.13),ddTop=Math.round(h*.79),ddHeight=Math.round(h*.08);
    let start=0,end=dates.length-1;
    if(selected!==null) { const t=r.trades[selected];start=Math.max(0,t.entry_idx-16);end=Math.min(dates.length-1,t.exit_idx+14); }
    $('range-label').textContent=dates[start]+' — '+dates[end];
    $('chart-title').textContent=selected===null?`${coin} 日K · 全部交易`:`${coin} 日K · 第 ${pad(selected)} 笔`;
    const area=r.trades.map((t,j)=>[{name:'#'+pad(j),xAxis:dates[t.entry_idx],itemStyle:{color:t.ret_pct>=0?'rgba(81,140,102,'+(selected===j?.12:.045)+')':'rgba(174,87,78,'+(selected===j?.12:.04)+')'},label:{show:selected===j,color:C.muted,fontSize:11,position:'insideTop'}},{xAxis:dates[t.exit_idx]}]);
    const connectors=r.trades.filter((t,j)=>selected===null||selected===j).map(t=>[{coord:[dates[t.entry_idx],t.entry_price],lineStyle:{color:t.ret_pct>=0?C.green:C.red,width:selected===null?1.2:1.8,type:'dashed',opacity:.8}},{coord:[dates[t.exit_idx],t.exit_price]}]);
    const buy=r.trades.map((t,j)=>({value:[dates[t.entry_idx],t.entry_price],tradeId:j,symbolSize:selected===j?17:11,itemStyle:{color:C.green,opacity:selected===null||selected===j?1:.35},label:{show:selected===j||selected===null,formatter:selected===j?'买入 '+f(t.entry_price,3):'#'+pad(j),position:'bottom',distance:selected===j?8:6,color:selected===j?C.green:C.muted,fontSize:11}}));
    const sell=r.trades.map((t,j)=>({value:[dates[t.exit_idx],t.exit_price],tradeId:j,symbol:t.reason==='end_of_test'?'diamond':'triangle',symbolRotate:t.reason==='end_of_test'?0:180,symbolSize:selected===j?17:10,itemStyle:{color:t.reason==='end_of_test'?'#686f74':C.red,opacity:selected===null||selected===j?1:.4},label:{show:selected===j,formatter:(t.reason==='end_of_test'?'终点 ':'退出 ')+f(t.exit_price,3),position:'top',distance:8,color:t.reason==='end_of_test'?C.ink:C.red,fontSize:11}}));
    const axisBase={type:'category',data:dates,boundaryGap:true,axisLine:{lineStyle:{color:'#dce0d5'}},axisTick:{show:false},axisPointer:{show:true,label:{show:false}},splitLine:{show:false},min:'dataMin',max:'dataMax'};
    const yBase={type:'value',scale:true,position:'left',splitNumber:4,axisLine:{show:false},axisTick:{show:false},splitLine:{lineStyle:{color:C.grid}},axisLabel:{color:C.muted,fontSize:11,fontFamily:'monospace',margin:8}};
    const opts={animation:false,textStyle:{fontFamily:'"PingFang SC","Microsoft YaHei",sans-serif',color:C.ink},backgroundColor:'transparent',
      tooltip:{trigger:'axis',confine:true,appendToBody:false,transitionDuration:0,backgroundColor:'#fffffc',borderColor:'#dde3d7',borderWidth:1,padding:[9,11],extraCssText:'box-shadow:0 3px 14px rgba(30,40,20,.07);border-radius:5px;',axisPointer:{type:'line',lineStyle:{color:'#9ba898',type:'dashed',width:1}},formatter:tooltip},
      axisPointer:{link:[{xAxisIndex:[0,1,2]}]},
      grid:[{left,right,top:priceTop,height:priceHeight},{left,right,top:navTop,height:navHeight},{left,right,top:ddTop,height:ddHeight}],
      xAxis:[{...axisBase,gridIndex:0,axisLabel:{show:false}},{...axisBase,gridIndex:1,axisLabel:{show:false}},{...axisBase,gridIndex:2,axisLabel:{show:true,color:C.muted,fontSize:11,hideOverlap:true,showMinLabel:false,showMaxLabel:true,formatter:v=>(end-start>150?v.slice(2,7):v.slice(5)),margin:9}}],
      yAxis:[{...yBase,gridIndex:0,axisLabel:{...yBase.axisLabel,formatter:v=>Math.abs(v)>=1000?f(v/1000,Math.abs(v)>=10000?0:1)+'k':f(v,Math.abs(v)<1?3:Math.abs(v)<10?2:0)},min:value=>{const span=value.max-value.min,step=Math.pow(10,Math.floor(Math.log10(Math.max(span,1e-8))))/2;return Math.max(0,Math.floor((value.min-span*.11)/step)*step);},max:value=>{const span=value.max-value.min,step=Math.pow(10,Math.floor(Math.log10(Math.max(span,1e-8))))/2;return Math.ceil((value.max+span*.14)/step)*step;}},
        {...yBase,gridIndex:1,splitNumber:2,axisLabel:{...yBase.axisLabel,formatter:v=>f(v,1)}},
        {...yBase,gridIndex:2,splitNumber:2,max:0,axisLabel:{...yBase.axisLabel,formatter:v=>f(v,0)+'%'}}],
      dataZoom:[{type:'inside',xAxisIndex:[0,1,2],startValue:start,endValue:end,filterMode:'filter',minValueSpan:12,zoomOnMouseWheel:'ctrl',moveOnMouseMove:true,moveOnMouseWheel:false,preventDefaultMouseMove:true},
        {type:'slider',xAxisIndex:[0,1,2],startValue:start,endValue:end,filterMode:'filter',minValueSpan:12,left,right,bottom:3,height:23,borderColor:'#e2e5db',backgroundColor:'#f5f6f0',fillerColor:'rgba(118,149,111,.16)',handleStyle:{color:'#fafbf6',borderColor:'#92a78c'},moveHandleSize:4,moveHandleStyle:{color:'#a4b299'},dataBackground:{lineStyle:{color:'#a9b3a2',width:.8},areaStyle:{color:'#e2e7db'}},selectedDataBackground:{lineStyle:{color:'#7e9577'},areaStyle:{color:'#c8d4bf'}},textStyle:{fontSize:10,color:C.muted},showDetail:false,brushSelect:true}],
      graphic:[{type:'text',left,top:3,style:{text:'价格 / USD',fill:C.muted,font:'11px sans-serif'}},
        {type:'text',left,top:navTop-21,style:{text:'累计净值',fill:C.muted,font:'11px sans-serif'}},
        {type:'text',left:left+80,top:navTop-21,style:{text:'— 策略',fill:C.green,font:'11px sans-serif'}},
        {type:'text',left:left+140,top:navTop-21,style:{text:'— 买入持有',fill:C.grey,font:'11px sans-serif'}},
        {type:'text',left,top:ddTop-21,style:{text:'策略日收盘回撤 / %',fill:C.muted,font:'11px sans-serif'}}],
      series:[
        {id:'candles',name:'日K',type:'candlestick',data:D.bars.map(b=>[b.open,b.close,b.low,b.high]),itemStyle:{color:'#7aa38c',color0:'#c48d86',borderColor:'#51806a',borderColor0:'#ad716b'},barMaxWidth:15,z:3,markArea:{silent:true,data:area},markLine:{silent:true,symbol:['none','none'],label:{show:false},data:connectors}},
        {id:'ma',name:'MA7',type:'line',data:D.ma,showSymbol:false,connectNulls:false,lineStyle:{color:C.gold,width:1.4,opacity:showMA?1:0},z:4},
        {id:'stop',name:'止损',type:'line',data:r.display_stops,showSymbol:false,connectNulls:false,step:'end',lineStyle:{color:C.blue,width:1.4,type:'dashed',opacity:showStop?1:0},z:5},
        {id:'buy',name:'买入',type:'scatter',symbol:'triangle',data:buy,z:10,labelLayout:{hideOverlap:true},emphasis:{scale:1.3}},
        {id:'sell',name:'退出',type:'scatter',data:sell,z:10,emphasis:{scale:1.3}},
        {id:'nav',name:'策略净值',type:'line',xAxisIndex:1,yAxisIndex:1,data:r.nav,showSymbol:false,lineStyle:{color:C.green,width:1.7},z:4},
        {id:'buyhold',name:'买入持有',type:'line',xAxisIndex:1,yAxisIndex:1,data:D.bh,showSymbol:false,lineStyle:{color:C.grey,width:1.2},z:3},
        {id:'dd',name:'回撤',type:'line',xAxisIndex:2,yAxisIndex:2,data:r.drawdowns.map(v=>-100*v),showSymbol:false,lineStyle:{color:C.blue,width:1},areaStyle:{color:'rgba(98,133,154,.16)'},z:3}
      ]};
    chart.setOption(opts,{notMerge:true,lazyUpdate:false});
  }

  function selectTrade(value, fromTable=false) {
    const n=value==='all'||value===null?null:Number(value);
    if(n!==null&&(!Number.isInteger(n)||n<0||n>=current().trades.length))return;
    selected=n;displayStats();renderInspector();renderTable();renderChart();
    if(fromTable)$('chart-title').scrollIntoView({behavior:reduced?'auto':'smooth',block:'start'});
    window.__tradeViewState={coin,windowName,mode,selected,ready:true};
  }
  function changeDataset(){
    coin=$('coin-select').value;windowName=$('window-select').value;
    D=ALL[coin][windowName];dates=D.bars.map(b=>b.date);indexByDate=new Map(dates.map((d,i)=>[d,i]));
    selected=null;selectTrade(null);
  }
  $('coin-select').addEventListener('change',changeDataset);
  $('window-select').addEventListener('change',changeDataset);
  $('mode-select').addEventListener('change',e=>{mode=e.target.value;selectTrade(null);});
  document.addEventListener('click',e=>{
    const cb=e.target.closest('[data-coin]');
    if(cb){$('coin-select').value=cb.dataset.coin;changeDataset();return;}

    const button=e.target.closest('[data-mode]');
    if(button){mode=button.dataset.mode;selectTrade(selected);return;}
    const trade=e.target.closest('[data-trade]');
    if(trade){selectTrade(trade.dataset.trade,!!trade.closest('#trade-table'));}
  });
  $('trade-select').addEventListener('change',e=>selectTrade(e.target.value));
  $('reset').addEventListener('click',()=>selectTrade(null));
  $('prev').addEventListener('click',()=>selectTrade(selected===null?0:Math.max(0,selected-1)));
  $('next').addEventListener('click',()=>selectTrade(selected===null?0:Math.min(current().trades.length-1,selected+1)));
  $('ma-toggle').addEventListener('click',()=>{showMA=!showMA;$('ma-toggle').setAttribute('aria-pressed',String(showMA));chart.setOption({series:[{id:'ma',lineStyle:{opacity:showMA?1:0}}]});});
  $('stop-toggle').addEventListener('click',()=>{showStop=!showStop;$('stop-toggle').setAttribute('aria-pressed',String(showStop));chart.setOption({series:[{id:'stop',lineStyle:{opacity:showStop?1:0}}]});});
  chart.on('click',p=>{if(p.data&&Number.isInteger(p.data.tradeId))selectTrade(p.data.tradeId);});
  chart.on('datazoom',()=>{
    const dz=chart.getOption().dataZoom[0];
    const start=typeof dz.startValue==='number'?dz.startValue:Math.round(dz.start*(dates.length-1)/100);
    const end=typeof dz.endValue==='number'?dz.endValue:Math.round(dz.end*(dates.length-1)/100);
    $('range-label').textContent=dates[Math.max(0,start)]+' — '+dates[Math.min(dates.length-1,end)];
  });
  $('download').addEventListener('click',()=>{
    const head=['trade','entry_date_utc','entry_price_usd','exit_date_utc','exit_price_usd','return_pct','hold_days','exit_reason','mode'];
    const rows=current().trades.map((t,i)=>[i+1,t.entry_date,t.entry_price,t.exit_date,t.exit_price,t.ret_pct,t.hold_days,t.reason,mode]);
    const blob=new Blob(['\ufeff'+[head,...rows].map(r=>r.join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'});
    const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=coin+'_'+windowName+'_'+mode+'_trades.csv';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  });
  const observer=new ResizeObserver(()=>{chart.resize();});observer.observe($('chart'));
  selectTrade(null);
  window.__tradeChart=chart;
})();
