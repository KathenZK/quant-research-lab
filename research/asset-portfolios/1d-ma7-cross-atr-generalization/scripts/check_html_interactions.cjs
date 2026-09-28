// Execute generated JavaScript locally with a minimal DOM/canvas implementation.
// These checks do not claim browser rendering or real pointer-device verification.
'use strict';
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),crypto=require('node:crypto'),assert=require('node:assert/strict');
const directory=path.resolve(process.argv[2]||path.join(__dirname,'../artifacts/html_20260909_v2'));
const digest=value=>crypto.createHash('sha256').update(value).digest('hex');
const audit=JSON.parse(fs.readFileSync(path.join(directory,'chart_audit.json'),'utf8'));
const checks=[],stats={coin_pages:0,cases_executed:0,all_trade_rows:0,all_stop_rows:0,individual_trade_selections:0,canvas_draw_calls:0};
const check=(name,action)=>{action();checks.push({name,status:'PASS'})};
function boot(relative,hash=''){
  const html=fs.readFileSync(path.join(directory,relative),'utf8');
  assert.equal(digest(html),audit.outputs[relative]);
  const payload=html.match(/<script type="application\/json" id="frozen-data">([\s\S]*?)<\/script>/)[1],data=JSON.parse(payload);
  const script=html.match(/<script>\s*([\s\S]*?)<\/script>/)[1],isCoin=!!data.arms;
  const expose=isCoin?'({armKey,selected,left,right,frames:Object.fromEntries(Object.entries(frames).map(([k,f])=>[k,{lo:f.lo,hi:f.hi}])),targets:targets.map(p=>({id:p.t.id,kind:p.kind,x:p.x,y:p.y}))})':'({rows:currentRows.map(r=>r.slug),filters:state()})';
  const instrumented=script.replace(/\}\)\(\);\s*$/,'globalThis.__probe=()=>'+expose+';\n})();');assert.notEqual(instrumented,script);
  const nodes={},ctx=new Proxy({measureText:t=>({width:String(t).length*6})},{get:(t,k)=>k in t?t[k]:(...args)=>{if(['moveTo','lineTo','fillRect','rect','arc','clearRect','setTransform'].includes(k))assert(args.every(Number.isFinite),'Finite canvas '+k+': '+args);stats.canvas_draw_calls++},set:(t,k,v)=>{t[k]=v;return true}});
  class NodeStub{
    constructor(id){this.id=id;this.handlers={};this.dataset={};this.style={};this.options=[];this.value='';this._html='';this.textContent='';this.disabled=false;this.classes=new Set();this.classList={add:n=>this.classes.add(n),remove:n=>this.classes.delete(n),toggle:(n,on)=>on?this.classes.add(n):this.classes.delete(n)}}
    addEventListener(k,fn){(this.handlers[k]??=[]).push(fn)}
    fire(k,args={}){const e={target:this,button:0,pointerId:1,clientX:600,clientY:200,preventDefault(){this.prevented=true},...args};for(const fn of this.handlers[k]??[])fn(e);return e}
    set innerHTML(v){this._html=v;if(this.id.endsWith('Select'))this.options=[...v.matchAll(/<option value="([^"]*)"/g)].map(m=>({value:m[1]}));if(this.id==='tradeRows')this.rows=[...v.matchAll(/<tr data-trade="(\d+)">/g)].map(m=>{const r=new NodeStub('row-'+m[1]);r.dataset.trade=m[1];r.closest=()=>r;return r})}
    get innerHTML(){return this._html}add(o){this.options.push(o)}
    getBoundingClientRect(){return{left:0,top:0,width:1200,height:({price:440,progress:105,rsi:95,equity:122,charts:762}[this.id]??100)}}
    getContext(){return ctx}setPointerCapture(p){this.captured=p}releasePointerCapture(){this.captured=null}scrollIntoView(){this.scrolled=true}
    querySelectorAll(selector){assert.equal(selector,'tr[data-trade]');return nodes.tradeRows.rows??[]}
    get offsetWidth(){return 300}get offsetHeight(){return 150}
  }
  for(const m of html.matchAll(/\bid="([^"]+)"/g))nodes[m[1]]=new NodeStub(m[1]);
  for(const m of html.matchAll(/<select id="([^"]+)"[^>]*>([\s\S]*?)<\/select>/g)){nodes[m[1]].innerHTML=m[2];nodes[m[1]].value=nodes[m[1]].options[0]?.value??''}
  nodes['frozen-data'].textContent=payload;
  const handlers={},location={hash},context={document:{getElementById:id=>{assert(nodes[id],'Existing DOM id '+id);return nodes[id]},title:''},location,
    window:{devicePixelRatio:1,addEventListener:(kind,fn)=>(handlers[kind]??=[]).push(fn)},Option:class{constructor(text,value){this.text=text;this.value=value}},ResizeObserver:class{constructor(fn){this.fn=fn}observe(){this.fn()}}};
  vm.createContext(context);vm.runInContext(instrumented,context,{timeout:30000});
  return{nodes,data,context,location,handlers,state:()=>context.__probe()};
}
const dashboard=boot('index.html'),{nodes:n,data:d}=dashboard;
const fixedPrimaryText=n.primaryOutcome.textContent,fixedDelayedText=n.delayedOutcome.textContent;
check('Dashboard default is H4_D0 and complete-period cohort; all four cases available',()=>{assert.equal(dashboard.state().filters.strategy,'H4_D0');assert.equal(dashboard.state().filters.cohort,'main_full');assert.equal(n.caseSelect.options.length,4);assert.equal(dashboard.state().rows.length,d.rows.filter(r=>r.cohort==='main_full').length)});
check('All market cohorts and all case filters retain their declared denominator',()=>{
  for(const cohort of ['main_full','partial_long','short','excluded','all'])for(const strategy of ['F0','H4_D0','H4_D2','H4_D3']){n.cohortSelect.value=cohort;n.caseSelect.value=strategy;n.caseSelect.fire('change');const expected=d.rows.filter(r=>cohort==='all'||r.cohort===cohort);assert.equal(dashboard.state().rows.length,expected.length);assert.equal((n.marketRows.innerHTML.match(/<tr>/g)||[]).length,expected.length);}
});
check('Search, candidate classification, negative results and reset all execute',()=>{
  n.cohortSelect.value='all';n.search.value='HYPE';n.search.fire('input');assert.equal(dashboard.state().rows.length,d.rows.filter(r=>r.symbol.includes('HYPE')).length);
  n.search.value='';for(const quality of ['stable','risk','positive','negative']){n.qualitySelect.value=quality;n.qualitySelect.fire('change');const expected=d.rows.filter(r=>{const a=r.cases.H4_D3;return a&&(quality==='stable'?a.stable:quality==='risk'?a.risk:quality==='positive'?a.returnPct>0:a.returnPct<=0)});assert.equal(dashboard.state().rows.length,expected.length)}
  n.reset.fire('click');assert.equal(dashboard.state().filters.strategy,'H4_D0');assert.equal(dashboard.state().filters.cohort,'main_full');assert.equal(dashboard.state().filters.query,'');assert.equal(dashboard.state().filters.quality,'all');
});
check('Fixed full-market result stays visible during searches and quality filters',()=>{assert.equal(n.primaryOutcome.textContent,fixedPrimaryText);assert.equal(n.delayedOutcome.textContent,fixedDelayedText);const main=d.rows.filter(r=>r.cohort==='main_full').map(r=>r.cases.H4_D0);if(main.length){assert(fixedPrimaryText.includes(main.length+'个币'));assert(fixedPrimaryText.includes(main.filter(a=>a.returnPct>0).length+'个赚钱'));}});
check('Every sorting control executes without merging unlike history lengths',()=>{n.cohortSelect.value='all';for(const key of ['return','drawdown','trades','delay3','delay2','improvement','symbol']){n.sortSelect.value=key;n.sortSelect.fire('change');assert.equal(dashboard.state().rows.length,d.rows.length);const cohorts=dashboard.state().rows.map(slug=>d.rows.find(r=>r.slug===slug).cohort),orders={main_full:0,partial_long:1,short:2,excluded:3};for(let i=1;i<cohorts.length;i++)assert(orders[cohorts[i]]>=orders[cohorts[i-1]])}});
const pageRows=d.rows.filter(r=>r.hasPage);let example=null;
for(const row of pageRows){
  const relative=`coins/${row.slug}.html`,page=boot(relative),{nodes,data,state}=page;
  assert.equal(state().armKey,'H4_D0');assert.equal(nodes.armSelect.options.length,4);assert.equal(nodes.comparisonRows.innerHTML.match(/<tr>/g).length,4);assert.equal(data.symbol,row.symbol);assert.equal(data.defaultArm,'H4_D0');assert.equal(nodes.boundaryNotice.hidden,!data.dataEndedEarly);if(data.dataEndedEarly)assert(nodes.boundaryNotice.textContent.includes('数据提前结束结算'));
  const thoroughly=row.symbol.includes('HYPE')||stats.coin_pages<3;
  for(const [key,arm]of Object.entries(data.arms)){
    nodes.armSelect.value=key;nodes.armSelect.fire('change');assert.equal(state().armKey,key);assert.equal(nodes.tradeRows.rows.length,arm.trades.length);assert.equal(nodes.tradeSelect.options.length,arm.trades.length+1);assert.equal(state().targets.length,arm.trades.length*2);assert.equal(nodes.rules.textContent,arm.rules);assert.equal(arm.summary.trades,arm.trades.length);assert.equal(nodes.bankruptcyNotice.hidden,!arm.summary.bankrupt);if(arm.summary.bankrupt){assert(nodes.bankruptcyNotice.textContent.includes('账户耗尽（未模拟强平）'));assert(arm.summary.ending_equity<=0);}
    if(!arm.trades.length){assert(nodes.previous.disabled);assert(nodes.next.disabled)}
    const selected=thoroughly?arm.trades:arm.trades.length?[arm.trades[0],arm.trades.at(-1)]:[];
    for(const t of selected){nodes.tradeSelect.value=String(t.id);nodes.tradeSelect.fire('change');assert.equal(state().selected,t.id);assert(nodes.tradeDetail.innerHTML.includes(`${key} #${t.id}`));assert(nodes.tradeDetail.innerHTML.includes('原穿越'));assert.equal((nodes.auditRows.innerHTML.match(/<tr>/g)||[]).length,t.progress.length);if(t.waitDays)assert(nodes.tradeDetail.innerHTML.includes(`等待${t.waitDays}天`));stats.individual_trade_selections++;}
    stats.cases_executed++;stats.all_trade_rows+=arm.trades.length;stats.all_stop_rows+=arm.trades.reduce((sum,t)=>sum+t.progress.length,0);
  }
  if(!example&&Object.values(data.arms).some(a=>a.trades.length))example=relative;
  stats.coin_pages++;if(stats.coin_pages%100===0)process.stdout.write(`Checked ${stats.coin_pages} coin pages\n`);
}
check('Every coin, every case, every saved trade row and stop row is included',()=>{assert.equal(stats.coin_pages,audit.coin_pages);assert.equal(stats.all_trade_rows,audit.total_trades_included);assert.equal(stats.all_stop_rows,audit.total_stop_rows_included);assert.equal(stats.cases_executed,audit.coin_pages*4)});
if(example){const page=boot(example,'#H4_D3'),{nodes,data,state}=page,DAY=86400000,FIRST=data.candles[0][0],LAST=data.end;
  check('Case deep links and hash changes execute',()=>{assert.equal(state().armKey,'H4_D3');page.location.hash='#H4_D0';for(const fn of page.handlers.hashchange)fn();assert.equal(state().armKey,'H4_D0')});
  check('Zoom, keyboard, drag, hover and full-history controls execute',()=>{nodes.full.fire('click');assert.equal(state().left,FIRST);assert.equal(state().right,LAST);nodes.price.fire('keydown',{key:'+'});assert(state().right-state().left<LAST-FIRST);const before=state().right-state().left;assert(nodes.progress.fire('wheel',{deltaY:-100}).prevented);assert(state().right-state().left<=before);if(before>8*DAY)assert(state().right-state().left<before);nodes.price.fire('pointerdown',{clientX:600});nodes.price.fire('pointermove',{clientX:700});nodes.price.fire('pointerup',{clientX:700});nodes.price.fire('pointermove',{clientX:650,clientY:220});assert.equal(nodes.tooltip.hidden,false);nodes.price.fire('pointerleave');assert.equal(nodes.tooltip.hidden,true);nodes.equity.fire('keydown',{key:'Home'});assert.equal(state().right,LAST);nodes.recent.fire('click');assert(state().right-state().left<=120*DAY);nodes.price.fire('dblclick');assert.equal(state().left,FIRST)});
}
check('All actual early-boundary and exhausted-account notices are present',()=>{assert.equal(d.rows.filter(r=>r.dataEndedEarly).length,audit.data_ended_early_coin_pages);assert.equal(d.rows.reduce((count,r)=>count+Object.values(r.cases).filter(a=>a.bankrupt).length,0),audit.bankrupt_coin_case_views);});
const report={status:'PASS',scope:'Actual generated JavaScript with minimal DOM/canvas stubs; not a real browser visual or hardware-pointer check',network_used:false,browser_used:false,checks,checks_passed:checks.length,...stats,source_chart_audit_sha256:digest(fs.readFileSync(path.join(directory,'chart_audit.json'))),probe_sha256:digest(fs.readFileSync(__filename)),node_version:process.version,generated_at_utc:new Date().toISOString()};
fs.writeFileSync(path.join(directory,'local_interaction_probe.json'),JSON.stringify(report,null,2)+'\n');process.stdout.write(JSON.stringify({status:report.status,checks_passed:report.checks_passed,...stats})+'\n');
