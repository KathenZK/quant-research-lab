"""Read frozen acceleration summaries and add one offline descriptive table page."""
from __future__ import annotations
import json,os,re,shutil,hashlib
from pathlib import Path
import pandas as pd

BASE=Path(__file__).resolve().parents[1];ROUND=BASE/'artifacts/state_machine_20260910'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def main():
    source=ROUND/'acceleration_diagnostics';out=ROUND/'html_current';evidence=out/'acceleration_integration';assert not evidence.exists();evidence.mkdir()
    hashes=json.loads((source/'artifact_checksums.json').read_text())
    for rel,digest in hashes.items():assert sha(source/rel)==digest,rel
    source_sha=sha(source/'artifact_checksums.json');tables={}
    for key,file in [('factors','factor_summary.csv'),('coverage','state_coverage_summary.csv'),('early','early_winner_summary.csv')]:
        d=pd.read_csv(source/file);tables[key]=d.astype(object).where(pd.notna(d),None).to_dict('records')
    tables['labels']={'atr_accel':'单日位移≥1 ATR且加速','pct5_accel':'单日方向涨跌幅≥5%且加速','ma2_atr':'方向MA7偏离≥2 ATR',
      'rsi80_20':'RSI极端：多≥80 / 空≤20','short_rsi30':'空单RSI≤30','short_atr_accel_rsi30':'空单1 ATR加速＋RSI≤30','atr_accel_ma2':'1 ATR加速＋MA7偏离≥2 ATR'}
    tables['metricLabels']={'healthy_pause':'实际暂停减少ATR倍数','sm_defense':'防守条件命中','sm_healthy':'健康条件命中','sm_protect':'衰竭保护命中','watch_started':'开始延伸观察','watch_cleared':'解除延伸观察'}
    tables['links']=[{'href':os.path.relpath(source/n,out),'label':label} for n,label in [('events_and_future_paths.csv','全部事件、未来路径与截尾'),('factor_by_coin.csv','按币分别统计'),('first_event_overlap.csv','首次事件的重叠和时点差异'),('state_coverage_by_coin.csv','逐币状态覆盖'),('early_exit_original_winners.csv','原赢家早退逐币表'),('artifact_checksums.json','来源校验清单')]]
    old_index=(out/'index.html').read_text();style=re.search(r'<style>(.*?)</style>',old_index,re.S)[1]
    html='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>加速信号之后 · 价格路径诊断</title><style>__STYLE__</style></head><body><main><a href="index.html">← 回到四版全市场比较</a><h1>加速、MA7偏离与RSI之后，价格还怎样运动</h1>
<p class="notice">这里是未来价格空间的描述，不是可实现收益。各因子首次出现的币种、交易和时间不同，不能把此表当因果排名或从中挑最高一行作为策略。10日为默认解释，5/20日是固定敏感性对照，未按结果挑时间。</p>
<p>只看本轮新成本V3实际持仓的完整日：当日收盘预计扣费后仍盈利时，每笔、每因子只保留首次出现。窗口从次日开盘起，5/10/20日都要求完整小时数据；不足的事件仍留在原分母，另列截尾。ATR使用事件日已知值。多空方向已统一，正值代表继续沿持仓方向运动。</p>
<div class="controls"><select id="accCohort" aria-label="选择样本组"><option value="main_full">完整433天 · 346币</option><option value="partial">其它至少180天 · 193币</option><option value="short">不足180天 · 72币</option></select><select id="accSide" aria-label="方向"><option value="-1">空单</option><option value="1">多单</option></select><select id="accHorizon" aria-label="固定后续窗口"><option value="10">10日 · 主解释</option><option value="5">5日</option><option value="20">20日</option></select><select id="accFactor" aria-label="因子"><option value="all">全部7种预设因子</option></select></div>
<p id="accCount" class="muted"></p><div class="tablewrap"><table><thead><tr><th>因子（保持预设顺序）</th><th>事件/币数</th><th>完整/截尾窗口</th><th>事件时已到V3退出</th><th>终点方向变化中位数 ATR</th><th>最大有利空间中位数 ATR</th><th>最大不利空间中位数 ATR</th><th>完整窗口方向继续%</th></tr></thead><tbody id="accRows"></tbody></table></div>
<p class="muted">“最大有利/不利空间”分别是未来窗口的价格极值，不知道何时成交才可取得，不能把最高价/最低价直接当成交价。空单专用的两个RSI30因子不适用于多单。单日ATR加速要求方向价格位移≥前日ATR，且大于上一日同向价格位移；5%加速使用方向百分比涨跌幅比较。它们与状态机的3日加速分支不是同一条件。</p>
<h2>实际账户中，这些状态覆盖了多少持仓日</h2><p>下列状态覆盖只随样本组筛选。条件可以重叠；“健康条件命中”与“实际暂停”分开列，不把健康标签误当已经改变止损。</p><div class="tablewrap"><table><thead><tr><th>方案</th><th>条件或实际动作</th><th>完整持仓日</th><th>涉及交易 / 本方案全部交易</th></tr></thead><tbody id="coverageRows"></tbody></table></div>
<h2>原本的赢家，有多少在前三个完整日内被提前退出</h2><p>固定V3原入场、数量和入场权益；只含两端都非样本结束结算的原赢家。这是实际退出对照，不能把不同事件样本的未来空间替代它。</p><div class="tablewrap"><table><thead><tr><th>候选</th><th>原赢家</th><th>3完整日前已退出</th><th>其中已变亏</th><th>原赢家最终变亏总数</th></tr></thead><tbody id="earlyRows"></tbody></table></div><footer id="accLinks"></footer></main><script type="application/json" id="frozen-data">__DATA__</script><script>
(()=>{'use strict';const el=id=>document.getElementById(id),D=JSON.parse(el('frozen-data').textContent),fmt=v=>v==null?'—':Number(v).toFixed(2);let visible=[];for(const [v,label]of Object.entries(D.labels))el('accFactor').add(new Option(label,v));
function render(){const cohort=el('accCohort').value,side=Number(el('accSide').value),horizon=Number(el('accHorizon').value),factor=el('accFactor').value;visible=D.factors.filter(r=>r.cohort===cohort&&r.side===side&&r.horizon_days===horizon&&(factor==='all'||r.factor===factor)).sort((a,b)=>Object.keys(D.labels).indexOf(a.factor)-Object.keys(D.labels).indexOf(b.factor));el('accCount').textContent=visible.length?`显示${visible.length}种有事件的预设因子；各行有各自事件分母。`:'所选因子没有可用事件；空单RSI30条件不适用于多单。';el('accRows').innerHTML=visible.map(r=>`<tr><td>${D.labels[r.factor]}</td><td>${r.events} / ${r.coins}</td><td>${r.complete_events} / ${r.censored_events}</td><td>${r.baseline_exits_at_event}</td><td>${fmt(r.median_end_directional_atr)}</td><td>${fmt(r.median_maximum_favorable_atr)}</td><td>${fmt(r.median_maximum_adverse_atr)}</td><td>${fmt(r.continuation_end_positive_pct)}%</td></tr>`).join('');el('coverageRows').innerHTML=D.coverage.filter(r=>r.cohort===cohort).map(r=>`<tr><td>${r.case_id}</td><td>${D.metricLabels[r.metric]}</td><td>${r.days}</td><td>${r.trades_with_state} / ${r.total_trades}</td></tr>`).join('');el('earlyRows').innerHTML=D.early.filter(r=>r.cohort===cohort).map(r=>`<tr><td>${r.case_id}</td><td>${r.original_winners}</td><td>${r.exited_before_three_complete_days}</td><td>${r.became_loss_before_three_days}</td><td>${r.became_loss_total}</td></tr>`).join('');}
for(const id of ['accCohort','accSide','accHorizon','accFactor'])el(id).addEventListener('change',render);el('accLinks').innerHTML=D.links.map(l=>`<a href="${l.href}">${l.label}</a>`).join(' · ')+'<p>基础账户单边手续费0.10%、滑点0.04%；未来价格空间本身没有再模拟交易或资金费。各币共享市场行情，不当作独立周期。浏览器视觉未验，仅做离线JavaScript与链接检查。</p>';render();globalThis.__accelerationPage={data:D,state:()=>({visibleFactors:visible.map(r=>r.factor),cohort:el('accCohort').value,side:Number(el('accSide').value),horizon:Number(el('accHorizon').value)})};})();
</script></body></html>'''
    html=html.replace('__STYLE__',style).replace('__DATA__',json.dumps(tables,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('</','<\\/'))
    assert not (out/'acceleration.html').exists();(out/'acceleration.html').write_text(html)
    shutil.copy2(out/'index.html',evidence/'index_before_integration.html.txt');shutil.copy2(out/'index_payload.json',evidence/'index_payload_before_integration.json')
    shutil.copy2(out/'artifact_checksums.json',evidence/'manifest_before_integration.json');shutil.copy2(out/'chart_audit.json',evidence/'chart_audit_before_integration.json');shutil.copy2(Path(__file__),evidence/'source_script.py.txt')
    data=json.loads((out/'index_payload.json').read_text());data['links'].append({'href':'acceleration.html','label':'加速信号之后：7因子价格路径诊断'})
    text=json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('</','<\\/')
    new=re.sub(r'(<script type="application/json" id="frozen-data">)[\s\S]*?(</script>)',lambda m:m[1]+text+m[2],old_index,count=1)
    new=new.replace('<nav class="tabs" id="tabs">','<p class="note"><a href="acceleration.html">加速、RSI、MA7偏离之后的价格空间：查看7因子诊断表 →</a></p><nav class="tabs" id="tabs">')
    (out/'index.html').write_text(new);write(out/'index_payload.json',data)
    audit=json.loads((out/'chart_audit.json').read_text())
    for file in ['index.html','index_payload.json','acceleration.html']:audit['outputs'][file]=sha(out/file)
    audit['acceleration_diagnostic_integration']={'source_directory':str(source),'source_manifest_sha256':source_sha,'builder_sha256':sha(Path(__file__)),'summary_rows':len(tables['factors']),
      'actual_state_rows':len(tables['coverage']),'early_winner_rows':len(tables['early']),'simulation_or_factor_recalculation_performed':False}
    write(out/'chart_audit.json',audit);write(evidence/'source_manifest.json',audit['acceleration_diagnostic_integration'])
    write(out/'artifact_checksums.json',{str(f.relative_to(out)):sha(f) for f in sorted(out.rglob('*')) if f.is_file() and f!=out/'artifact_checksums.json'})
    print(json.dumps(audit['acceleration_diagnostic_integration']))


if __name__=='__main__':main()
