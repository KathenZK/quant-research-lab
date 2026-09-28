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

const b=boot(path.join(htmlRoot,'index.html')),e=id=>b.elements.get(id),D=b.data;
assert.equal(D.rows.length,121);assert.equal(e('case').options.length,121);assert.equal(e('parameter').options.length,11);
let checkedTrades=0,parameters=0,pairMatrices=0;
for(const k of Object.keys(D.grid)){
 e('parameter').value=k;trigger(e('parameter'));assert.equal(rows(e('localTable')),5);assert(!/NaN|Infinity/.test(e('localCharts').innerHTML));parameters++;
}
for(const k of e('pair').options){e('pair').value=k;trigger(e('pair'));assert.equal(rows(e('heatmap')),3);pairMatrices++;}
for(const group of ['ablation','neighbor','pair','joint','all']){
 e('group').value=group;trigger(e('group'));const n=group==='all'?121:new Set(['B',...D.members.filter(x=>x.group===group).map(x=>x.case_id)]).size;
 assert.equal(rows(e('resultTable')),n);
 for(const sort of ['declared','return','drawdown']){e('sort').value=sort;trigger(e('sort'));assert.equal(rows(e('resultTable')),n);}
}
e('search').value='unmatched_random_key';trigger(e('search'));assert.equal(rows(e('resultTable')),0);e('search').value='';trigger(e('search'));
for(const r of D.rows){b.run(`choose(${JSON.stringify(r.case_id)})`);assert.equal(e('case').value,r.case_id);assert.equal(rows(e('trades')),D.paths[r.case_id].trades.length);assert.equal(rows(e('periods')),2);assert(!/NaN|Infinity/.test(e('equityChart').innerHTML));assert.equal(rows(e('tradePairs')),D.pairs.filter(x=>x.case_id===r.case_id).length);checkedTrades+=D.paths[r.case_id].trades.length;}
const report={complete:true,html_cases:D.rows.length,case_selections:121,trade_rows_checked:checkedTrades,parameters,pair_matrices:pairMatrices,group_filters:5,sort_options:3,empty_search:true,finite_svg_coordinates:true,browser_layout_verified:false};
fs.writeFileSync(outFile,JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify(report));
