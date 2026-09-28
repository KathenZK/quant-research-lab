"""Apply the later official-source adjudication to display only, with before/after hashes."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import hashlib
import pandas as pd

BASE=Path(__file__).resolve().parents[1]
ROUND=BASE/'artifacts/state_machine_20260910'


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,x):p.write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def payload(html):return json.loads(re.search(r'<script type="application/json" id="frozen-data">([\s\S]*?)</script>',html)[1])
def inject(html,data):
    text=json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('</','<\\/')
    return re.sub(r'(<script type="application/json" id="frozen-data">)[\s\S]*?(</script>)',lambda m:m[1]+text+m[2],html,count=1)


def main():
    p=argparse.ArgumentParser();p.add_argument('--html',type=Path,default=ROUND/'html_current')
    p.add_argument('--adjudication',type=Path,default=ROUND/'official_hour_repair/source_adjudication_summary.json')
    p.add_argument('--history-analysis',type=Path,default=ROUND/'analysis_history')
    p.add_argument('--extra-link',action='append',default=[],help='Label=path to a completed artifact');a=p.parse_args()
    output=a.html;record=output/'display_source_adjudication';assert not record.exists();record.mkdir()
    manifest=json.loads((output/'artifact_checksums.json').read_text())
    for rel,h in manifest.items():assert sha(output/rel)==h,rel
    adjudication=json.loads(a.adjudication.read_text());assert adjudication['new_dataset_published'] is False and adjudication['old_inputs_changed'] is False
    shutil.copy2(output/'artifact_checksums.json',record/'build_manifest_before_update.json')
    shutil.copy2(output/'chart_audit.json',record/'chart_audit_before_update.json')
    shutil.copy2(output/'index_payload.json',record/'index_payload_before_update.json')
    shutil.copy2(Path(__file__),record/'display_update_script.py.txt')
    replacements=[
      ('原冻结历史有已知来源不一致：2024-10-28小时数据与币安官方不一致。本页仅作受此限制的历史诊断，不能认定完整周期验证通过。',
       '官方历史来源之间存在未解决冲突：部分币的官方API与官方带校验日档不能相互对上，尚未确定哪一份可采纳，也未完成可确认的修复。本页仅作受此限制的历史诊断，不能认定完整周期验证通过。'),
      ('原冻结历史有已知来源不一致：2024-10-28的小时行情与币安官方原始数据不一致，部分共同缺口切断了连续账户。本页只作受此限制的诊断，不能认定完整周期验证通过，不能依据这里的收益选新策略。',
       '官方历史来源之间存在未解决冲突：322个核对代码中，298币的官方API与官方带校验日档存在冲突；24币可采纳的数据并未改动旧价格。没有发布修复后的历史数据。本页只作受此限制的诊断，不能认定完整周期验证通过，不能依据这里的收益选新策略。'),
      ('历史来源有已知不一致','官方历史来源有未解决冲突'),
      ('这些段仍受上述冻结来源问题限制','这些段仍受上述官方来源冲突限制'),
      ('本轮全部方案统一单边手续费','当前主组为2025-06-29至2026-09-04 UTC，共433天。本轮全部方案统一单边手续费'),
      ('实际终点</th>','实际终点（不含）</th>'),
      ('同一历史组内排序。四格依次列收益 / 回撤 / 交易笔数。','同一历史组内排序，表中数据终点不含当天。四格依次列收益 / 回撤 / 交易笔数。')]
    audit=json.loads((output/'chart_audit.json').read_text());changes=[];checked=0
    for relative in list(audit['outputs']):
        if not relative.endswith('.html'):continue
        path=output/relative;old=path.read_text();new=old
        for before,after in replacements:new=new.replace(before,after)
        if relative!='index.html':
            before_data=payload(old);after_data=payload(new)
            assert before_data['candles']==after_data['candles'] and before_data['arms']==after_data['arms'] and before_data['comparison']==after_data['comparison']
            checked+=1
        else:
            data=payload(new)
            for coin in data['coins']:
                if coin['reason']=='NO_USABLE_TRADING_WINDOW':coin['reason']='无通过检查且完成预热的连续交易窗口'
            data['links'].append({'href':os.path.relpath(a.adjudication,output),'label':'官方历史来源冲突核对'})
            for part in a.extra_link:
                label,filename=part.split('=',1);target=Path(filename).resolve();assert target.exists();data['links'].append({'href':os.path.relpath(target,output),'label':label})
            hist_hashes=json.loads((a.history_analysis/'artifact_checksums.json').read_text())
            assert sha(a.history_analysis/'scope.csv')==hist_hashes['scope.csv']
            sc=pd.read_csv(a.history_analysis/'scope.csv')
            sc['status']=sc.status.map({'JOINT_PRICE_WINDOWS_VERIFIED':'有可交易的联合有效段；受来源冲突限制','RETAINED_NO_TRADING_WINDOW':'保留历史，但无完成预热后的交易窗口'})
            cols=['symbol','source_group','status','all_retained_segments','segments_with_trading_window','total_trade_days_across_all_segments']
            data['historyScope']=sc[cols].where(pd.notna(sc[cols]),None).to_dict('records')
            assert len(data['historyScope'])==680
            extra='<details><summary>查看全部680个历史代码，包含无可交易段代码（与上方币种搜索同步）</summary><p class="muted">可交易总天数只是各独立段天数相加，不能视为一段连续可交易历史。</p><div class="tablewrap"><table><thead><tr><th>币种</th><th>来源</th><th>状态</th><th>保留段</th><th>可交易段</th><th>各段可交易天数总计</th></tr></thead><tbody id="historyScopeRows"></tbody></table></div></details>'
            marker='<div id="historyLinks"></div>';assert marker in new;new=new.replace(marker,marker+extra)
            marker='function history(){';assert new.count(marker)==1
            render="function history(){const sq=el('historySearch').value.trim().toUpperCase(),ss=el('historySource').value;el('historyScopeRows').innerHTML=D.historyScope.filter(r=>r.symbol.toUpperCase().includes(sq)&&(ss==='all'||r.source_group===ss)).map(r=>`<tr><td>${esc(r.symbol)}</td><td>${esc(r.source_group)}</td><td>${esc(r.status)}</td><td>${r.all_retained_segments}</td><td>${r.segments_with_trading_window}</td><td>${r.total_trade_days_across_all_segments}</td></tr>`).join('');"
            new=new.replace(marker,render);new=inject(new,data)
            write(output/'index_payload.json',data);audit['outputs']['index_payload.json']=sha(output/'index_payload.json')
        if new!=old:
            before=sha(path);path.write_text(new);after=sha(path);changes.append({'path':relative,'before_sha256':before,'after_sha256':after});audit['outputs'][relative]=after
    assert checked==audit['total_chart_pages'] and len(changes)>0
    report={'source_adjudication_path':str(a.adjudication.resolve()),'source_adjudication_sha256':sha(a.adjudication),
      'official_source_adjudication':adjudication,'replacements':replacements,'files_changed':changes,'chart_candle_trade_stop_and_comparison_payloads_unchanged':checked,
      'analysis_or_replay_performed':False,'before_manifest':'build_manifest_before_update.json','before_chart_audit':'chart_audit_before_update.json',
      'history_scope_source_sha256':sha(a.history_analysis/'scope.csv'),'script_sha256':sha(Path(__file__))}
    write(record/'display_update_manifest.json',report);audit['display_source_adjudication']=report
    write(output/'chart_audit.json',audit)
    write(output/'artifact_checksums.json',{str(f.relative_to(output)):sha(f) for f in sorted(output.rglob('*')) if f.is_file() and f!=output/'artifact_checksums.json'})
    print(json.dumps({'display_files_updated':len(changes),'chart_payloads_verified_unchanged':checked,'manifest_sha256':sha(output/'artifact_checksums.json')}))


if __name__=='__main__':main()
