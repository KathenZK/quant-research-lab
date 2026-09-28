"""Restore the earlier stop-first chart presentation, using saved evidence only."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import pandas as pd
from v3_opportunity_study_20260913 import ROOT,BASE,R,write_json
from v3_opportunity_inputs_20260913 import load_sources,table

OUT=R/'html_stoplines'
DETAIL_COLUMNS=['trade_id','timestamp','signal_day','old_mult','new_mult','tightened','no_new_extreme_days',
                'new_armed','old_stop','new_stop','extreme_price','tp_protect_active','tp_protect_candidate',
                'expected_profit_at_close','full_holding_day']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def packed(d,cols):return json.loads(d.reindex(columns=cols).to_json(orient='values',date_format='epoch',date_unit='ms',double_precision=15))

CSS='''
*{box-sizing:border-box}main{max-width:1540px;padding:22px 26px}.stop-toolbar{display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin:12px 0}.stop-toolbar select{max-width:340px}button:focus-visible,select:focus-visible,input:focus-visible{outline:2px solid #347eb1;outline-offset:2px}button:disabled{opacity:.4;cursor:default}.stop-legend{display:flex;gap:16px;flex-wrap:wrap;font-size:12px;line-height:1.5;margin:8px 0 12px}.stop-legend span{display:inline-flex;align-items:center;gap:6px}.stop-swatch{display:inline-block;width:24px;height:0;border-top:2px solid #347eb1}.stop-swatch.actual{border-top:2px dashed #a17124}.stop-charts{position:relative;background:#fff;border:1px solid #d9dfdb;overflow:hidden}#chart,#atrChart{width:100%;min-width:0;cursor:crosshair}#atrChart{border-top:1px solid #e6eae6;height:130px}.stop-detail{line-height:1.9;font-size:13px;background:#eef2ed;border-left:3px solid #347eb1;padding:11px 14px;margin:13px 0;min-height:64px}#viewRange{margin-left:auto;color:#64726e;font-size:12px}#hint{font-size:12px;line-height:1.8;min-height:25px}#chartTooltip{position:absolute;pointer-events:none;z-index:5;max-width:280px;background:rgba(255,255,255,.98);border:1px solid #cbd5ce;padding:9px 11px;font-size:12px;line-height:1.8;box-shadow:0 4px 15px #1527211c;border-radius:5px}details.optional-evidence{background:transparent;padding:0;margin:20px 0}details.optional-evidence>summary{cursor:pointer;font-size:15px;color:#3b5e54;padding:9px 0}#stopAuditRows{max-height:390px}#tradeRows{max-height:330px}td button{padding:3px 7px}button,input,select{max-width:100%}@media(max-width:680px){main{padding:15px 10px}h1{font-size:21px}.stop-toolbar select{width:100%;max-width:none}.stop-legend{gap:8px 12px}.stop-detail{font-size:12px}#viewRange{margin-left:0;width:100%}.stop-toolbar{gap:6px}#chartTooltip{max-width:260px}.stop-toolbar button{font-size:12px;padding:7px}}
'''
CHART_BODY='''<p><a href="../index.html">← 全市场结果</a></p>
<div class="filters stop-toolbar"><label for="segment">连续段</label><select id="segment"></select><label for="arm">方案</label><select id="arm"></select></div>
<div class="stop-toolbar"><label for="trade">定位交易</label><select id="trade"></select><button id="previousTrade" type="button">← 上一笔</button><button id="nextTrade" type="button">下一笔 →</button><button id="fullView" type="button">全部交易</button><button id="recentView" type="button">最近120天</button><span id="viewRange"></span></div>
<div class="stop-legend"><span><i class="stop-swatch"></i>MA7（当日收盘）</span><span><i class="stop-swatch actual"></i>实际移动止损</span><span style="color:#a17124">○ 减少ATR倍数</span><span style="color:#167566">▲ 开多</span><span style="color:#c34e59">▼ 开空</span><span style="color:#a17124">◆ 止损退出</span><span style="color:#8560ac">● RSI止盈</span><span style="color:#64726e">■ 样本结算</span><label><input type="checkbox" id="showMA30"> MA30参考线</label></div>
<div class="stop-charts"><canvas id="chart" aria-label="日K与逐笔移动止损"></canvas><canvas id="atrChart" aria-label="逐笔ATR止损倍数"></canvas><div id="chartTooltip" hidden></div></div>
<p id="hint">绿色持仓背景为多单，浅红色为空单；连线绿为盈利、红为亏损。滚轮缩放，拖动平移，双击返回全部。</p>
<div id="tradeDetail" class="stop-detail" aria-live="polite"></div>
<div id="tradeRows" class="scroll"></div>
<h2>每日止损怎样收紧</h2><p class="note">空心圆表示ATR倍数减少；已有止损只能收窄，所以倍数减少当天，实际止损价格也可能保持不动。</p><div id="stopAuditRows" class="scroll"></div>
<details class="optional-evidence"><summary>原始穿越、候选和退出后走势</summary><div class="filters"><label for="cross">原始穿越</label><select id="cross"></select><label><input type="checkbox" id="showCrosses">显示原穿越标记</label></div><p class="note">方框：绿色为成交、橙色为斜率拒绝、灰色为其他原因。以下诊断以原V3为基准。</p><h2>全部原始穿越</h2><div id="crossRows" class="scroll"></div><h2>候选建立、等待、失效和确认</h2><div id="candidates" class="scroll"></div><h2>退出与停滞之后</h2><div id="eventRows" class="scroll"></div></details>'''

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--rebuild-display',action='store_true');args=ap.parse_args()
    assert not OUT.exists() or args.rebuild_display,'Only this new display directory can be regenerated explicitly'
    OUT.mkdir(exist_ok=True);(OUT/'coins').mkdir(exist_ok=True)
    old=R/'html';old_manifest=json.loads((old/'artifact_checksums.json').read_text());sources=load_sources()
    account_manifests={arm:json.loads((R/'accounts'/arm/'artifact_checksums.json').read_text()) for arm in ['E_STATE','TP_PROTECT']}
    js=Path(__file__).with_name('v3_stoplines_chart_20260913.js');subprocess.run(['node','--check',str(js)],check=True)
    source_pins={str(js.relative_to(ROOT)):sha(js),str(Path(__file__).relative_to(ROOT)):sha(Path(__file__)),str((old/'artifact_checksums.json').relative_to(ROOT)):sha(old/'artifact_checksums.json')}
    write_json(OUT/'started.json',{'display_only':True,'strategy_replayed':False,'old_html_preserved':True,'source_pins':source_pins})
    used={};counts={'pages':0,'segments':0,'stop_details':0}
    for i,p in enumerate(sorted(old.glob('coins/*.html')),1):
        assert sha(p)==old_manifest[str(p.relative_to(old))]
        document=p.read_text();script=re.search(r'<script>([\s\S]*?)</script>',document).group(1)
        decoder=json.JSONDecoder();data,end=decoder.raw_decode(script[len('const DATA='):]);rest=script[len('const DATA=')+end:]
        for key,seg in data['segments'].items():
            info=sources[key];seg['stopDetails']={}
            dpath=ROOT/info['daily_source'];assert sha(dpath)==info['daily_sha256'];used[str(dpath.relative_to(ROOT))]=info['daily_sha256']
            d=pd.read_parquet(dpath,columns=['timestamp','atr','rsi']);seg['dayIndicators']=packed(d,['timestamp','atr','rsi'])
            for arm in data['names']:
                sp=(ROOT/info['baseline_dir'] if arm=='V3' else R/'accounts'/arm/'runs'/key/arm/'full')/'stops.csv'
                digest=info['baseline_sha256']['stops.csv'] if arm=='V3' else account_manifests[arm][str(sp.relative_to(R/'accounts'/arm))]
                assert sha(sp)==digest;used[str(sp.relative_to(ROOT))]=digest;s=table(sp)
                for c in ['tp_protect_active']:
                    if c not in s:s[c]=False
                seg['stopDetails'][arm]=packed(s,DETAIL_COLUMNS) if len(s) else []
                counts['stop_details']+=len(s)
            counts['segments']+=1
        # Keep every original numeric/display array unchanged; append evidence fields.
        payload=json.dumps(data,ensure_ascii=False,separators=(',',':'),allow_nan=False).replace('</','<\\/')
        title=document[:document.index('<main>')].replace('</style>',CSS+'</style>')
        head=document[document.index('<main>')+6:document.index('</h1>')+5]
        notice=re.search(r'<p class="note">[\s\S]*?</p>',document).group(0)
        revised=title+'<main>'+head+notice+CHART_BODY+'</main><script>const DATA='+payload+rest+'\n'+js.read_text()+'</script></html>'
        (OUT/'coins'/p.name).write_text(revised);counts['pages']+=1
        if i%200==0:print('Stop charts',i,680,flush=True)
    index=old/'index.html';assert sha(index)==old_manifest['index.html']
    content=index.read_text();content=content.replace('<h2>两个改动有没有改善完整账户</h2>','<p><a href="coins/HYPE.html"><b>查看HYPE：全部止损虚线、每日收紧和ATR倍数</b></a>；点下表任意币名可看相同完整路径。</p><h2>两个改动有没有改善完整账户</h2>')
    (OUT/'index.html').write_text(content);counts['pages']+=1
    (OUT/'stoplines.js').write_text(js.read_text());write_json(OUT/'consumed_files.json',used)
    write_json(OUT/'completion.json',{'complete':True,'display_only':True,'strategy_replayed':False,'original_arrays_preserved':True,**counts,'source_pins':source_pins,'browser_render_verified':False})
    write_json(OUT/'artifact_checksums.json',{str(p.relative_to(OUT)):sha(p) for p in OUT.rglob('*') if p.is_file() and p.name!='artifact_checksums.json'})
    print(counts,flush=True)

if __name__=='__main__':main()
