// Offline DOM/canvas checks only. This does not claim browser rendering.
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import crypto from 'node:crypto';
import assert from 'node:assert/strict';
const root=path.resolve('research/asset-portfolios/1d-ma7-cross-atr-generalization/artifacts/ma30_states_20260911');
const htmlDir=path.join(root,'html'), out=path.join(root,'html_audit');
fs.mkdirSync(out,{recursive:true});
const hash=p=>crypto.createHash('sha256').update(fs.readFileSync(p)).digest('hex');
const counts={pages:0,segments:0,arm_segments:0,trades:0,stop_rows:0,bars:0,chart_focus_checks:0,filter_checks:0,draw_calls:0,local_links:0};
const errors=[];
const canvas=new Proxy({}, {get:(t,k)=>k in t?t[k]:(...args)=>{for(const a of args)if(typeof a==='number')assert(Number.isFinite(a),`non-finite canvas ${String(k)}`);counts.draw_calls++;},set:(t,k,v)=>{t[k]=v;return true;}});
class Element{
  constructor(tag){this.tag=tag;this.value='';this.textContent='';this._html='';this.clientWidth=1000;}
  set innerHTML(x){this._html=x;if(this.tag==='select'){const m=[...x.matchAll(/<option\b([^>]*)>([\s\S]*?)<\/option>/g)];const first=m.find(t=>/\bselected\b/.test(t[1]))||m[0];this.value=first?(first[1].match(/value="([^"]*)"/)?.[1]??first[2]):'';}}
  get innerHTML(){return this._html;}
  getContext(){return canvas;}
  getBoundingClientRect(){return {left:0,width:this.clientWidth};}
  setPointerCapture(){}
}
function setup(file){
  const text=fs.readFileSync(file,'utf8'),elements={};
  for(const m of text.matchAll(/<(select|input|canvas|div|p)\b[^>]*\bid="([^"]+)"[^>]*>/g)){
    elements[m[2]]=new Element(m[1]);
    if(m[1]==='select')elements[m[2]].innerHTML=text.slice(m.index+m[0].length).split('</select>')[0];
  }
  const staticMarkup=text.replace(/<script>[\s\S]*?<\/script>/g,'');
  for(const m of staticMarkup.matchAll(/(?:href|src)="([^"]+)"/g)){
    const url=m[1];assert(!/^https?:\/\//i.test(url),'unexpected remote dependency');
    if(url.startsWith('#'))continue;
    assert(fs.existsSync(path.resolve(path.dirname(file),decodeURIComponent(url.split('#')[0]))),`missing link ${url}`);counts.local_links++;
  }
  assert(!/<img\b/i.test(text),'unexpected static image');
  const scripts=[...text.matchAll(/<script>([\s\S]*?)<\/script>/g)];assert.equal(scripts.length,1);
  const context=vm.createContext({document:{getElementById:id=>{assert(elements[id],`missing DOM ${id}`);return elements[id];}}});
  vm.runInContext(scripts[0][1],context,{timeout:10000});
  const data=vm.runInContext('DATA',context);counts.pages++;
  return {context,data,elements};
}
function runPage(file){
  const {context:c,data:d,elements:e}=setup(file);
  if(d.rows){
    // The dashboard exposes seven declared periods; CSV retains additional old comparison periods.
    assert.equal(d.rows.length,41790);assert.equal(d.sums.length,160);
    for(const period of Object.keys(d.labels))for(const arm of Object.keys(d.names))for(const coverage of ['COMPLETE','PARTIAL'])for(const sort of ['return','dd','delta']){
      e.period.value=period;e.arm.value=arm;e.coverage.value=coverage;e.sort.value=sort;e.search.value='';
      vm.runInContext('refresh()',c);
      const expected=d.rows.filter(r=>r[3]===period&&r[2]===arm&&r[4]===coverage);
      assert.equal((e.coins.innerHTML.match(/<tr>/g)||[]).length,expected.length+1);
      for(const r of expected)assert(fs.existsSync(path.join(htmlDir,'coins',r[0]+'.html')));
      counts.filter_checks++;
    }
    e.period.value='phase_2025_2026';e.arm.value='M_MANAGE';e.coverage.value='COMPLETE';e.search.value='bTc';
    vm.runInContext('refresh()',c);assert(e.coins.innerHTML.includes('BTC'));assert(!e.coins.innerHTML.includes('HYPE'));
    e.search.value='does-not-exist';vm.runInContext('refresh()',c);assert.equal((e.coins.innerHTML.match(/<tr>/g)||[]).length,1);
    return;
  }
  for(const [key,s] of Object.entries(d.segments)){
    counts.segments++;counts.bars+=s.bars.length;
    for(let i=0;i<s.bars.length;i++){
      const b=s.bars[i];assert.equal(b.length,7);assert(b.slice(0,5).every(Number.isFinite));
      assert(b[2]>=Math.max(b[1],b[4])&&b[3]<=Math.min(b[1],b[4]));
      if(i)assert.equal(b[0]-s.bars[i-1][0],86400000);
      assert(b.slice(5).every(x=>x===null||Number.isFinite(x)));
    }
    e.segment.value=key;
    for(const arm of Object.keys(d.names)){
      assert(Array.isArray(s.trades[arm])&&Array.isArray(s.stops[arm]));
      e.arm.value=arm;vm.runInContext('loadSegment()',c);counts.arm_segments++;
      const trades=s.trades[arm],stops=s.stops[arm];counts.trades+=trades.length;counts.stop_rows+=stops.length;
      assert.equal((e.tradeRows.innerHTML.match(/<tr>/g)||[]).length,trades.length+1);
      const ids=new Set(trades.map(t=>t[0]));assert.equal(ids.size,trades.length);
      for(const t of trades){assert.equal(t.length,9);assert(t.slice(0,8).every(Number.isFinite));assert(t[2]>=t[1]);assert([1,-1].includes(t[3]));assert(t[1]>=s.bars[0][0]&&t[2]<=s.bars.at(-1)[0]+86400000);}
      for(const s of stops){assert(ids.has(s[0]));assert(s.slice(0,3).every(Number.isFinite));assert(typeof s[3]==='string');}
      for(const idx of new Set([0,Math.floor(trades.length/2),trades.length-1]))if(idx>=0&&trades[idx]){
        e.trade.value=String(trades[idx][0]);vm.runInContext('focusTrade()',c);counts.chart_focus_checks++;
        assert.equal(vm.runInContext('chosen[0]',c),trades[idx][0]);
        e.chart.onpointermove({clientX:400});assert(/MA7 .* MA30/.test(e.hint.textContent));
        const afterExit=s.bars.find(b=>b[0]>trades[idx][2]);
        if(afterExit){const g=e.chart._range;const clientX=g.left+(afterExit[0]-g.start)/(g.finish-g.start)*(g.right-g.left);e.chart.onpointermove({clientX});assert(!e.hint.textContent.includes('止损'),'stop tooltip shown after exit');}
        e.chart.onwheel({deltaY:-1,preventDefault(){}});e.chart.onwheel({deltaY:1,preventDefault(){}});
        e.chart.onpointerdown({clientX:400,pointerId:1});e.chart.onpointermove({clientX:440});e.chart.onpointerup();e.chart.ondblclick();
      }
      e.chart.clientWidth=375;vm.runInContext('draw()',c);e.chart.clientWidth=1000;
    }
  }
  if(!Object.keys(d.segments).length)assert.equal(e.hint.textContent,'没有本轮可用价格段');
}
const files=[path.join(htmlDir,'index.html'),...fs.readdirSync(path.join(htmlDir,'coins')).filter(x=>x.endsWith('.html')).sort().map(x=>path.join(htmlDir,'coins',x))];
for(const file of files){try{runPage(file);}catch(e){errors.push({file,error:e.stack});}}
try{assert.equal(counts.pages,681);assert.equal(counts.segments,954);assert.equal(counts.arm_segments,9540);assert.equal(counts.trades,157776);}catch(e){errors.push({error:e.stack});}
const result={status:errors.length?'FAIL':'PASS',mode:'offline DOM and canvas mocks; browser rendering not performed',...counts,errors,html_manifest_sha256:hash(path.join(htmlDir,'artifact_checksums.json')),source_script_sha256:hash(new URL(import.meta.url))};
fs.writeFileSync(path.join(out,'final.json'),JSON.stringify(result,null,2)+'\n');
fs.copyFileSync(new URL(import.meta.url),path.join(out,'source_script.mjs.txt'));
console.log(JSON.stringify(result,null,2));if(errors.length)process.exitCode=1;
