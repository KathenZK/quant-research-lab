// Offline execution of the delivered JS with a minimal DOM/canvas mock.
// This is not a browser, screenshot, layout, font or pixel-rendering test.
'use strict';
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
const [htmlRoot,output]=process.argv.slice(2);
const decode=s=>String(s).replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&');
function boot(file){
  const html=fs.readFileSync(file,'utf8'), elements=new Map(),calls={draw:0};
  function element(tag,id){
    let text='',value='',opts=[];
    const ctx=new Proxy({}, {get(target,key){
      if(!(key in target)) target[key]=(...args)=>{
        if(['moveTo','lineTo','fillRect','arc','clearRect'].includes(key)){
          for(const v of args)assert(Number.isFinite(v),`${id}.${key} nonfinite ${v}`);
          calls.draw++;
        }
      };
      return target[key];
    }});
    return {tag,id,checked:false,textContent:'',clientWidth:1000,
      get innerHTML(){return text;},set innerHTML(v){text=String(v);if(tag==='select'){
        opts=[...text.matchAll(/<option\s+value="([^"]*)"[^>]*>/g)].map(x=>decode(x[1]));value=opts[0]??'';
      }},
      get value(){return value;},set value(v){value=tag==='select'&&!opts.includes(String(v))?'':String(v);},
      get options(){return opts;},getContext:()=>ctx,setPointerCapture:()=>{},
      getBoundingClientRect:()=>({left:0,top:0,width:1000,height:460})};
  }
  for(const m of html.matchAll(/<(select|input|canvas|div|p)[^>]*\bid="([^"]+)"[^>]*>/g)){
    assert(!elements.has(m[2]),'duplicate id '+m[2]);elements.set(m[2],element(m[1],m[2]));
  }
  for(const m of html.matchAll(/<select[^>]*\bid="([^"]+)"[^>]*>([\s\S]*?)<\/select>/g))elements.get(m[1]).innerHTML=m[2];
  const source=html.match(/<script>([\s\S]*?)<\/script>/)[1];
  const context=vm.createContext({document:{getElementById:id=>{assert(elements.has(id),'missing id '+id);return elements.get(id);}},console,Date,Math,Number,String,Boolean,Object,Array,Set,JSON});
  vm.runInContext(source,context,{timeout:30000,filename:file});
  const run=code=>vm.runInContext(code,context,{timeout:30000});
  return {elements,calls,run,data:run('DATA')};
}
const rows=e=>((e.innerHTML.match(/<tbody>([\s\S]*?)<\/tbody>/)||[])[1]||'').match(/<tr>/g)?.length||0;
function mainChecks(){
  const b=boot(path.join(htmlRoot,'index.html')),e=id=>b.elements.get(id),D=b.data;
  assert.equal(e('period').value,'phase_2025_2026');assert.equal(e('arm').value,'V3');
  assert.equal(e('coverage').value,'COMPLETE');assert.equal(e('days').value,'20');assert.equal(e('side').value,'0');
  const checkAccounts=()=>{
    const status=e('period').value==='full_segment'?'ORIGINAL_SEGMENT':e('coverage').value;
    const expected=D.accounts.filter(x=>x.block===e('period').value&&x.case_id===e('arm').value&&x.status===status&&x.slug.toLowerCase().includes(e('search').value.toLowerCase()));
    assert.equal(rows(e('accounts')),expected.length);
    assert(e('count').textContent.startsWith(expected.length+' 个连续段'));
    assert(!e('accounts').innerHTML.includes('NaN'));
    for(const r of expected.slice(0,10))assert(e('accounts').innerHTML.includes(r.return_pct==null?'—%':Number(r.return_pct).toFixed(2)+'%'));
    const sums=D.sums.filter(x=>x.block===e('period').value&&x.status==='COMPLETE');
    assert.equal(rows(e('overview')),sums.length);
  };
  let accountStates=0,groupStates=0;
  for(const p of e('period').options)for(const a of e('arm').options)for(const coverage of ['COMPLETE','PARTIAL']){
    e('period').value=p;e('arm').value=a;e('coverage').value=coverage;e('period').oninput();checkAccounts();accountStates++;
  }
  e('period').value='full_segment';e('arm').value='V3';e('search').value='hype';e('search').oninput();checkAccounts();
  assert(rows(e('accounts'))>=1);assert(e('accounts').innerHTML.includes('coins/HYPE.html'));
  for(const sort of ['return','dd','delta']){e('sort').value=sort;e('sort').oninput();checkAccounts();}
  for(const event of e('event').options)for(const phase of e('phase').options)for(const side of ['0','1','-1'])for(const days of ['5','10','20']){
    e('event').value=event;e('phase').value=phase;e('side').value=side;e('days').value=days;e('event').oninput();
    for(const feature of e('feature').options){
      e('feature').value=feature;e('feature').oninput();
      const expected=D.groups.filter(r=>r.event_set===event&&r.phase===phase&&r.side===Number(side)&&r.days===Number(days)&&r.feature===feature);
      assert.equal(rows(e('groups')),expected.length);assert(!e('groups').innerHTML.includes('NaN'));groupStates++;
    }
  }
  assert.equal((e('allCodes').innerHTML.match(/<a /g)||[]).length,680);
  assert.equal(rows(e('pairs')),D.pairs.filter(r=>r.cohort==='original_short_tp').length);
  return {default_period:'phase_2025_2026',default_arm:'V3',account_filter_states:accountStates,
          opportunity_filter_states:groupStates,all_codes:680,search_hype:true,sorting_no_error:true};
}
function coinChecks(slug){
  const b=boot(path.join(htmlRoot,'coins',slug+'.html')),e=id=>b.elements.get(id),D=b.data;
  assert.equal(e('arm').value,'V3');
  if(!Object.keys(D.segments).length){
    assert.equal(e('segment').value,'');assert.equal(rows(e('tradeRows')),0);
    assert.equal(e('hint').textContent,'没有本轮可用价格段');
    e('arm').value='E_STATE';e('arm').oninput();assert(e('candidates').innerHTML.includes('无等待候选'));
    return {slug,empty:true,arm_switch:true};
  }
  let states=0,focusedTrades=0,focusedSignals=0,candidateRows=0;
  for(const key of Object.keys(D.segments))for(const arm of Object.keys(D.names)){
    const seg=D.segments[key];e('segment').value=key;e('arm').value=arm;e('segment').oninput();
    assert.equal(rows(e('tradeRows')),seg.trades[arm].length);assert.equal(rows(e('crossRows')),seg.crosses.length);
    assert.equal(rows(e('eventRows')),seg.events.length);assert.equal(rows(e('candidates')),(seg.candidates[arm]||[]).length);
    candidateRows+=(seg.candidates[arm]||[]).length;
    for(const t of seg.trades[arm].length?[seg.trades[arm][0],seg.trades[arm].at(-1)]:[]){
      e('trade').value=String(t[0]);e('trade').oninput();
      assert.equal(b.run('chosen[0]'),t[0]);assert(e('chart')._range.start<=t[1]);
      assert(e('chart')._range.finish>=Math.min(t[2],seg.bars.at(-1)[0]+86400000));focusedTrades++;
    }
    e('chart').ondblclick();assert.equal(b.run('lo'),0);assert.equal(b.run('hi'),seg.bars.length);
    let before=b.run('hi-lo');e('chart').onwheel({deltaY:-1,preventDefault(){}});
    assert(b.run('hi-lo')<before || before<=10);
    const left=b.run('lo');e('chart').onpointerdown({clientX:500,pointerId:1});
    e('chart').onpointermove({clientX:450});e('chart').onpointerup();assert(b.run('lo')>=left);
    e('chart').onpointermove({clientX:500});assert(e('hint').textContent.includes('MA7'));
    for(const i of seg.crosses.length?[0,seg.crosses.length-1]:[]){
      e('cross').value=String(i);e('cross').oninput();assert.equal(b.run('focusCross[0]'),seg.crosses[i][0]);
      assert.equal(b.run('chosen'),null);assert(e('chart')._range.start<=seg.crosses[i][0]);
      assert(e('chart')._range.finish>=seg.crosses[i][0]);focusedSignals++;
    }
    e('showCrosses').checked=true;e('showCrosses').oninput();states++;
  }
  return {slug,empty:false,segment_arm_states:states,focused_trades:focusedTrades,
          focused_signals:focusedSignals,candidate_rows_checked:candidateRows,
          finite_canvas_calls:b.calls.draw,zoom_pan_hover_reset:true};
}
const result={complete:true,method:'offline Node vm with minimal DOM and canvas mocks',
              browser_used:false,actual_browser_render_or_layout_verified:false,
              main:mainChecks(),coins:['HYPE','BTC','BTCST','DOS','MARSCOIN','牛来'].map(coinChecks)};
fs.writeFileSync(output,JSON.stringify(result,null,2)+'\n');
console.log(JSON.stringify(result));
