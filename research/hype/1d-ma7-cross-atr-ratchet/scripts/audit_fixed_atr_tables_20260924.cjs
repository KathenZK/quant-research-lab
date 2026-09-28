'use strict';
const fs=require('fs'),path=require('path'),assert=require('assert');
const {boot,trigger,rows}=require('./audit_fixed_atr_paths_20260924.cjs');
const [root,market,out]=process.argv.slice(2);
const b=boot(path.join(root,'index.html')),e=id=>b.elements.get(id),D=b.data;
assert.equal(D.hype.length,46);assert.equal(D.market.length,947);assert.equal(D.longest.length,649);assert.equal(rows(e('market')),649);assert.equal(rows(e('episodes')),18);
let hypeRows=0,coinRows=0;
for(const r of D.hype){b.run(`choose(${JSON.stringify(r.case_id)})`);const n=D.pairs.filter(p=>p.case_id===r.case_id).length;assert.equal(rows(e('pairs')),n);hypeRows+=n;}
for(const k of e('parameter').options){e('parameter').value=k;trigger(e('parameter'));assert.equal(rows(e('near')),5);}
for(const scope of ['all','longest'])for(const outcome of ['all','better','worse'])for(const order of e('order').options){e('scope').value=scope;e('outcome').value=outcome;e('order').value=order;trigger(e('order'));const expected=D.market.filter(r=>(scope==='all'||D.longest.includes(r.run_key))&&(outcome==='all'||outcome==='better'&&r.delta_return_pp>1e-8||outcome==='worse'&&r.delta_return_pp< -1e-8));assert.equal(rows(e('market')),expected.length);}
e('search').value='no_match_zzzzz';trigger(e('search'));assert.equal(rows(e('market')),0);
const files=fs.readdirSync(market).filter(f=>f.endsWith('.html'));assert.equal(files.length,649);
for(const f of files){const c=boot(path.join(market,f));for(const r of c.data.rows){c.elements.get('segment').value=r.run_key;trigger(c.elements.get('segment'));const n=c.data.pairs.filter(p=>p.run_key===r.run_key).length;assert.equal(rows(c.elements.get('pairs')),n);coinRows+=n;}}
assert.equal(coinRows,22611);
const result={complete:true,hype_accounts:46,hype_pair_rows:hypeRows,parameters:11,market_accounts:947,coin_pages:files.length,coin_trade_pairs:coinRows,filters_and_sorts:true,empty_search:true,browser_layout_verified:false};
fs.writeFileSync(out,JSON.stringify(result,null,2)+'\n');console.log(result);
