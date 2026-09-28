'use strict';
// Executes the delivered JavaScript offline. This is not browser/layout/pixel QA.
const fs=require('fs'),path=require('path'),vm=require('vm'),assert=require('assert');
const [htmlRoot,outFile]=process.argv.slice(2);
const decode=s=>String(s).replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&amp;/g,'&');
function boot(file,width=1000,transform=null){
  const html=fs.readFileSync(file,'utf8'),elements=new Map(),calls={draw:0,strokes:[],fills:[]};
  function element(tag,id){
    let text='',value='',opts=[],dash=[],current=[],stack=[];
    const target={strokeStyle:'#000',fillStyle:'#000',globalAlpha:1,lineWidth:1};
    const ctx=new Proxy(target,{get(t,k){
      if(k in t)return t[k];
      return (...args)=>{
        if(['moveTo','lineTo','fillRect','arc','clearRect','rect'].includes(k)){
          assert(args.every(Number.isFinite),`${id}.${k} non-finite coordinates: ${args}`);calls.draw++;
        }
        if(k==='setLineDash')dash=[...args[0]];
        if(k==='beginPath')current=[];
        if(['moveTo','lineTo','arc','rect'].includes(k))current.push([k,...args]);
        if(k==='stroke')calls.strokes.push({id,style:t.strokeStyle,width:t.lineWidth,alpha:t.globalAlpha,dash:[...dash],points:current.map(p=>[...p])});
        if(k==='fill')calls.fills.push({id,style:t.fillStyle,points:current.map(p=>[...p])});
        if(k==='save')stack.push({style:t.strokeStyle,fill:t.fillStyle,width:t.lineWidth,alpha:t.globalAlpha,dash:[...dash]});
        if(k==='restore'){const p=stack.pop();if(p){t.strokeStyle=p.style;t.fillStyle=p.fill;t.lineWidth=p.width;t.globalAlpha=p.alpha;dash=p.dash;}}
        if(k==='measureText')return {width:String(args[0]).length*6};
      };
    }});
    const listeners={};
    return {tag,id,checked:false,hidden:false,textContent:'',clientWidth:width,clientHeight:id==='atrChart'?110:460,style:{},dataset:{},listeners,
      classList:{toggle(){},add(){},remove(){}},
      get innerHTML(){return text;},set innerHTML(v){text=String(v);if(tag==='select'){opts=[...text.matchAll(/<option\s+value="([^"]*)"[^>]*>/g)].map(m=>decode(m[1]));value=opts[0]??'';}},
      get value(){return value;},set value(v){value=tag==='select'&&!opts.includes(String(v))?'':String(v);},
      get options(){return opts;},add(o){opts.push(String(o.value));if(opts.length===1)value=opts[0];},
      getContext:()=>ctx,setPointerCapture(){},releasePointerCapture(){},scrollIntoView(){},setAttribute(){},
      querySelectorAll(){return[];},querySelector(){return null;},
      addEventListener(k,fn){listeners[k]=fn;},
      getBoundingClientRect:()=>({left:0,top:0,width,height:id==='atrChart'?110:460})};
  }
  for(const m of html.matchAll(/<([a-z][a-z0-9]*)[^>]*\bid="([^"]+)"[^>]*>/gi)){
    assert(!elements.has(m[2]),'duplicate id '+m[2]);elements.set(m[2],element(m[1],m[2]));
  }
  for(const m of html.matchAll(/<select[^>]*\bid="([^"]+)"[^>]*>([\s\S]*?)<\/select>/g))elements.get(m[1]).innerHTML=m[2];
  const document={getElementById:id=>{assert(elements.has(id),'missing id '+id);return elements.get(id);},querySelectorAll:()=>[],addEventListener(){}};
  const win={devicePixelRatio:2,innerWidth:width,addEventListener(){}};
  let source=[...html.matchAll(/<script>([\s\S]*?)<\/script>/g)].map(m=>m[1]).join('\n');
  if(transform)source=transform(source);
  const context=vm.createContext({document,window:win,devicePixelRatio:2,location:{hash:''},Option:function(t,v){this.text=t;this.value=v;},requestAnimationFrame:fn=>fn(),console,Date,Math,Number,String,Boolean,Object,Array,Set,Map,JSON});
  vm.runInContext(source,context,{timeout:30000,filename:file});
  const run=code=>vm.runInContext(code,context,{timeout:30000});
  return {elements,calls,run,data:run('DATA'),width};
}
const rows=e=>{const m=e.innerHTML.match(/<tbody>([\s\S]*?)<\/tbody>/);return (m?m[1]:e.innerHTML).match(/<tr(?:\s|>)/g)?.length||0;};
const trigger=(e,event='input',arg={})=>{const fn=e['on'+event]||e.listeners[event];assert(fn,'missing '+event+' handler '+e.id);fn(arg);};
function checkVisibleStops(b){
  b.calls.strokes=[];b.calls.fills=[];b.run('draw()');
  const g=b.elements.get('chart')._range;if(!g)return 0;
  assert(g.left>=0&&g.right<=b.width,'plot spills outside CSS width');
  const trades=b.run('trades'),stops=b.run('stops'),expected=[];
  for(const t of trades){
    const ss=stops.filter(s=>s[0]===t[0]);
    for(let i=0;i<ss.length;i++){
      const start=ss[i][1],end=Math.min(t[2],ss[i+1]?.[1]??t[2]);
      if(start>t[2]||end<start||end<g.start||start>g.finish)continue;
      expected.push({tradeId:t[0],start,end,price:ss[i][2],drawStart:Math.max(start,g.start),drawEnd:Math.min(end,g.finish)});
    }
  }
  const actual=b.elements.get('chart')._stopSegments;
  assert.equal(actual.length,expected.length,'not every visible stop interval drawn');
  const near=(a,z)=>assert(Math.abs(a-z)<1e-6,`coordinate ${a} != ${z}`);
  for(let i=0;i<expected.length;i++)for(const f of Object.keys(expected[i]))near(actual[i][f],expected[i][f]);
  const paths=b.calls.strokes.filter(s=>s.id==='chart'&&s.style==='#a17124'&&s.dash.join(',')==='5,3');
  const horizontals=paths.filter(s=>s.points.length===2&&s.points[0][0]==='moveTo'&&s.points[1][0]==='lineTo'&&Math.abs(s.points[0][2]-s.points[1][2])<1e-8);
  // Zero-height vertical updates may duplicate a point; require one unique matching horizontal for every interval.
  for(const s of expected){
    const index=horizontals.findIndex(p=>Math.abs(p.points[0][1]-g.X(s.drawStart))<1e-6&&Math.abs(p.points[1][1]-g.X(s.drawEnd))<1e-6&&Math.abs(p.points[0][2]-g.Y(s.price))<1e-6);
    assert(index>=0,'missing actual dashed horizontal for trade '+s.tradeId);horizontals.splice(index,1);
  }
  for(const p of paths){
    assert.equal(p.points.length,2);const a=p.points[0],z=p.points[1];
    assert(Math.abs(a[1]-z[1])<1e-8||Math.abs(a[2]-z[2])<1e-8,'stop is diagonal');
    if(Math.abs(a[2]-z[2])>1e-8){
      assert(expected.some((s,i)=>i&&expected[i-1].tradeId===s.tradeId&&expected[i-1].end===s.start&&Math.abs(g.X(s.start)-a[1])<1e-6&&Math.abs(g.Y(expected[i-1].price)-a[2])<1e-6&&Math.abs(g.Y(s.price)-z[2])<1e-6),'vertical joins different trades or wrong effective day');
    }
  }
  const atr=b.elements.get('atrChart'),at=atr._stopSegments;
  assert.equal(at.length,actual.length,'ATR subplot loses intervals');
  near(atr._range.start,g.start);near(atr._range.finish,g.finish);
  for(let i=0;i<at.length;i++){near(at[i].start,actual[i].start);near(at[i].end,actual[i].end);near(at[i].mult,actual[i].mult);}
  const circles=b.calls.strokes.filter(s=>s.id==='chart'&&s.style==='#a17124'&&s.points.some(p=>p[0]==='arc'));
  assert.equal(circles.length,actual.filter(s=>s.tightened&&s.start>=g.start&&s.start<=g.finish).length,'ATR reduction circles missing');
  if(!b.elements.get('showMA30').checked)assert(!b.calls.strokes.some(s=>s.style==='#9aa5a5'),'MA30 visible by default');
  const ma=b.calls.strokes.find(s=>s.id==='chart'&&s.style==='#347eb1');
  if(ma){const mb=b.run('bars').filter(x=>x[0]+86400000>=g.start-86400000&&x[0]+86400000<=g.finish+86400000&&x[5]!=null);assert.equal(ma.points.length,mb.length);for(let i=0;i<mb.length;i++){near(ma.points[i][1],g.X(mb[i][0]+86400000));near(ma.points[i][2],g.Y(mb[i][5]));}}
  return paths.length;
}
function coinCheck(slug,width=1000){
  const b=boot(path.join(htmlRoot,'coins',slug+'.html'),width),e=id=>b.elements.get(id),D=b.data;
  assert.equal(e('arm').value,'F');assert(!e('showMA30').checked,'MA30 should start hidden');
  let states=0,focused=0,dashed=0;
  for(const key of Object.keys(D.segments))for(const arm of Object.keys(D.names)){
    e('segment').value=key;e('arm').value=arm;trigger(e('segment'));
    assert.equal(b.run('chosen'),null);
    assert.equal(rows(e('tradeRows')),D.segments[key].trades[arm].length);
    dashed+=checkVisibleStops(b);
    const ts=D.segments[key].trades[arm];
    for(const t of ts){
      e('trade').value=String(t[0]);trigger(e('trade'));assert.equal(b.run('chosen[0]'),t[0]);
      assert.equal(rows(e('stopAuditRows')),D.segments[key].stopDetails[arm].filter(s=>s[0]===t[0]).length,'missing daily stop rows');
      dashed+=checkVisibleStops(b);focused++;
    }
    trigger(e('fullView'),'click');
    assert.equal(b.run('lo'),0);assert.equal(b.run('hi'),D.segments[key].bars.length);
    e('showMA30').checked=true;trigger(e('showMA30'));e('showMA30').checked=false;trigger(e('showMA30'));
    const span=b.run('hi-lo');trigger(e('chart'),'wheel',{deltaY:-1,clientX:width/2,preventDefault(){}});
    assert(b.run('hi-lo')<=span);trigger(e('chart'),'dblclick');
    trigger(e('chart'),'pointermove',{clientX:width/2});
    states++;
  }
  if(!Object.keys(D.segments).length){assert.equal(rows(e('tradeRows')),0);for(const arm of Object.keys(D.names)){e('arm').value=arm;trigger(e('arm'));}}
  return {slug,width,states,focused,dashed,finite_canvas_operations:b.calls.draw};
}
function syntheticChecks(){
  const file=path.join(htmlRoot,'coins','HYPE.html'),original=boot(file).data;
  const results=[];
  for(const kind of ['zero_segments','no_trades','one_bar']){
    const D=JSON.parse(JSON.stringify(original));
    if(kind==='zero_segments')D.segments={};
    else for(const seg of Object.values(D.segments)){
      seg.bars=seg.bars.slice(0,kind==='one_bar'?1:2);seg.dayIndicators=seg.dayIndicators.slice(0,seg.bars.length);seg.crosses=[];seg.events=[];
      for(const a of Object.keys(D.names)){seg.trades[a]=[];seg.stops[a]=[];seg.stopDetails[a]=[];seg.candidates[a]=[];}
    }
    const b=boot(file,320,s=>s.replace('const DATA=','const DATA='+JSON.stringify(D)+';const ORIGINAL_UNUSED_DATA='));
    for(const a of Object.keys(D.names)){
      b.elements.get('arm').value=a;trigger(b.elements.get('arm'));
      trigger(b.elements.get('fullView'),'click');trigger(b.elements.get('recentView'),'click');
      for(const id of ['chart','atrChart']){trigger(b.elements.get(id),'wheel',{deltaY:-1,clientX:160,preventDefault(){}});trigger(b.elements.get(id),'pointermove',{clientX:160});}
      assert.equal(b.run('trades.length'),0);assert.equal(rows(b.elements.get('tradeRows')),0);
      if(kind==='one_bar'){assert.equal(b.run('lo'),0);assert.equal(b.run('hi'),1);}
    }
    results.push({kind,width:320,finite_canvas_operations:b.calls.draw});
  }
  return results;
}
function main(){
  const result={complete:true,method:'Offline JavaScript DOM and canvas recording; not a browser/layout or screenshot test',
    browser_used:false,actual_browser_layout_verified:false,
    cases:['HYPE'].map(s=>coinCheck(s)),mobile:coinCheck('HYPE',390),synthetic:syntheticChecks()};
  fs.mkdirSync(path.dirname(outFile),{recursive:true});fs.writeFileSync(outFile,JSON.stringify(result,null,2)+'\n');console.log(JSON.stringify(result));
}
if(require.main===module)main();
module.exports={boot,trigger,rows};
