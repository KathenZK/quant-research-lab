"""Build the inventory and pack a self-contained review; does not run backtests."""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import quote, unquote

ROOT = Path(__file__).resolve().parents[4]
TOPIC = ROOT / 'research/platform/research-program-review'
OUT = TOPIC / 'artifacts/strategy-chronology-20260925'
REPORT = TOPIC / 'diagnostics/strategy-project-chronology-and-research-review-2026-09-25.md'
EXTERNAL = Path('/Users/ZK/.codex/worktrees/5f41/quant-strategy-lab')
SOURCES: dict[str, dict] = {}
MISSING: set[str] = set()
SKIP = {'artifacts', 'scripts', '__pycache__', '.git', '.venv', 'data', 'node_modules'}


def prose_only(s: str) -> str:
    """Do not treat quoted legacy README headings or sample dates as events."""
    result=[]; fence_char=''; fence_len=0
    for line in s.splitlines():
        m=re.match(r'^\s*(`{3,}|~{3,})',line)
        if not fence_len:
            if m:fence_char=m[1][0];fence_len=len(m[1])
            else:result.append(line)
        elif m and m[1][0]==fence_char and len(m[1])>=fence_len:
            fence_len=0
    return '\n'.join(result)


def read(p: Path) -> str:
    b = p.read_bytes()
    SOURCES[str(p)] = {'path': str(p), 'bytes': len(b), 'sha256': hashlib.sha256(b).hexdigest()}
    return b.decode('utf-8')


def link(p: Path, label: str | None = None) -> str:
    if not p.exists():
        MISSING.add(str(p))
        return f'{label or p.name}（原引用目标未留存：`{p.name}`）'
    return f'[{label or p.name}]({quote(os.path.relpath(p, REPORT.parent), safe="/._-#")})'


def rewrite(s: str, source: Path) -> str:
    def sub(m):
        label, target = m[1], m[2].strip().strip('<>')
        if re.match(r'^(https?://|mailto:|#|data:)', target):
            # Source-local heading anchors cannot be carried into this document.
            return label + '（见来源原文对应小节）' if target.startswith('#') else m[0]
        target = target.split(' "')[0]
        if target.startswith('file://'):target=target[7:]
        raw, _, fragment = target.partition('#')
        p = (source.parent / unquote(raw)).resolve()
        if not p.exists():
            MISSING.add(str(p))
            return f'{label}（原引用未留存：`{raw}`）'
        dest = quote(os.path.relpath(p, REPORT.parent), safe='/._-')
        if fragment: dest += '#' + quote(fragment, safe='._-')
        return f'[{label}]({dest})'
    s = re.sub(r'(?<!!)\[([^\]\n]+)\]\(([^)\n]+)\)', sub, s)
    s = re.sub(r'^!\[([^\]]*)\]\(([^)]+)\).*$', r'图表见来源文件：\1。', s, flags=re.M)
    return s


def clean(s: str, source: Path, omit_evidence: bool = False) -> str:
    s = re.sub(r'\A---\n.*?\n---\n', '', s, flags=re.S)
    s = re.sub(r'^# [^\n]*\n', '', s, count=1)
    if omit_evidence:
        s = re.sub(r'^## (?:Evidence Map|证据入口|证据索引|Evidence|Version Rules|版本规则)\b.*?(?=^## |\Z)', '', s, flags=re.S | re.M)
    aliases = {'Family Identity': '家族身份', 'Current State': '主账所记状态', 'Version Table': '版本与观察记录', 'Shared Assumptions': '数据、成本与执行假设', 'Observation Table': '观察记录'}
    def heading(m):
        return '**' + aliases.get(m[1].strip(), m[1].strip()) + '**'
    lines=[]; in_code=False
    for line in s.splitlines():
        if line.lstrip().startswith('```'): in_code=not in_code
        if not in_code: line=re.sub(r'^#{1,6}\s+(.+)$',heading,line)
        lines.append(line)
    s='\n'.join(lines)
    s = rewrite(s, source)
    return s.strip()


def documents(d: Path) -> list[Path]:
    result = []
    for base, dirs, fs in os.walk(d):
        dirs[:] = [x for x in dirs if x not in SKIP]
        if d == ROOT / 'research/mu':
            dirs[:] = [x for x in dirs if x in {'diagnostics', 'notes', 'specs', 'legacy-canvas'}]
        result += [Path(base) / f for f in fs if f.endswith('.md')]
    return sorted(result)


def date_candidates(d: Path, docs: list[Path], git_dates: dict) -> list[dict]:
    candidates = []
    for p in docs:
        if 'legacy-canvas' not in p.parts:
            for m in re.finditer(r'(2026)[-_]?(\d\d)[-_]?(\d\d)', p.name):
                dt = '-'.join(m.groups())
                if '2026-04-20' <= dt <= '2026-09-25':
                    candidates.append({'date': dt, 'source': str(p), 'kind': '日期化研究文档（最迟已存在）'})
        s = read(p)
        if p.name == 'decision-log.md':
            for l in prose_only(s).splitlines():
                m = re.match(r'^(?:#{1,6}\s+|[-*]\s+`?)(2026-\d\d-\d\d)', l)
                if m and '2026-04-20' <= m[1] <= '2026-09-25' and not re.match(r'^[-*].*?2026-\d\d-\d\d`?\s*(?:至|→|到|—)',l):
                    candidates.append({'date': m[1], 'source': str(p), 'kind': '决策日志日期（最迟已存在）'})
        rel = str(p.relative_to(ROOT)) if p.is_relative_to(ROOT) else None
        if rel in git_dates:
            candidates.append({'date': git_dates[rel]['date'], 'source': str(p), 'kind': 'Git 当前路径首次加入（可能晚于研究）', 'commit': git_dates[rel]['commit']})
    return sorted(candidates, key=lambda a: (a['date'], a['kind'], a['source']))


def get_name(s: str, directory: Path) -> str:
    m = re.search(r'(?:完整家族名|Full family name|Full name|Family ID|family_id)[：:]\s*`([^`]+)`', s, re.I)
    if m: return m[1]
    m = re.search(r'^# (.+)', s, re.M)
    if m:
        title = re.sub(r'\s*(?:Core Ledger|核心主账|主账|版本主账).*$', '', m[1], flags=re.I).strip(' ：:—-')
        if len(title) > 4: return title
    return directory.name


def overview(s: str, kind: str) -> str:
    patterns = {
        'market': r'(?:市场(?:/周期)?|标的|研究对象|资产范围|交易标的|Universe)[：:]\s*(.+)',
        'mechanism': r'(?:机制|核心机制|核心问题|核心逻辑)[：:]\s*(.+)',
    }
    m = re.search(patterns[kind], s, re.I)
    return m[1].strip() if m else ''


def spec_excerpt(p: Path, limit: int = 5000) -> str:
    s = read(p)
    if p.suffix == '.json':
        try:
            obj = json.loads(s)
            if isinstance(obj, dict):
                selected = {k: v for k, v in obj.items() if re.search(r'param|rule|config|signal|entry|exit|risk|cost|fee|slippage|position|universe|instrument|execution|account|capital|model|label|threshold|holding|strategy|comparison', k, re.I)}
                if not selected: selected = obj
                body = json.dumps(selected, ensure_ascii=False, indent=2)
                # JSON must remain valid: use complete top-level fields within the budget.
                if len(body) > limit:
                    reduced = {}
                    for k, v in selected.items():
                        candidate = json.dumps({**reduced, k: v}, ensure_ascii=False, indent=2)
                        if len(candidate) <= limit: reduced[k] = v
                    body = json.dumps(reduced, ensure_ascii=False, indent=2) if reduced else ''
                return '```json\n' + body + '\n```' if body else '合同包含较大嵌套配置，完整参数直接见上方来源。'
        except json.JSONDecodeError:
            return '机器合同需按原文件读取。'
    blocks=[]; block=[]; in_code=False
    for line in s.splitlines():
        if not in_code and re.match(r'^#{1,6} ',line) and block:
            blocks.append('\n'.join(block));block=[]
        block.append(line)
        if line.lstrip().startswith('```'):in_code=not in_code
    if block:blocks.append('\n'.join(block))
    selected = []
    for b in blocks:
        heading = b.splitlines()[0] if b else ''
        if re.search(r'参数|入场|退出|仓位|止损|止盈|执行|成本|特征|模型|标签|信号|候选|规则|指标|交易|方向|基准|parameter|entry|exit|position|cost|execution|universe|label|feature|baseline', heading, re.I):
            if re.search(r'验收|检查清单|产物|输出|代码路径|修改纪律|命名|登记', heading): continue
            selected.append(b)
    if not selected:
        selected = blocks[:3]
    kept = []
    used = 0
    for b in selected:
        # Keep whole small blocks; large tables/code are retained as whole paragraphs.
        if used + len(b) <= limit:
            kept.append(b); used += len(b); continue
        for para in re.split(r'\n\s*\n', b):
            if used + len(para) <= limit and (not para.startswith('```') or para.count('```') % 2 == 0):
                kept.append(para); used += len(para)
    return clean('\n\n'.join(kept), p) or '具体字段见原合同；本摘要不补填未机械定义的规则。'


def history(d: Path) -> str:
    p = d / 'decision-log.md'
    if not p.exists(): return '未找到独立 decision log；演进以版本表、规格日期和历史报告为准。'
    s = prose_only(read(p))
    events = []
    for b in re.split(r'(?=^## )', s, flags=re.M):
        ls = b.strip().splitlines()
        if not ls: continue
        m = re.search(r'2026-\d\d-\d\d', ls[0])
        if m and ls[0].startswith('##'):
            title = re.sub(r'^##\s*', '', ls[0])
            paras = [z.strip() for z in '\n'.join(ls[1:]).split('\n\n') if z.strip()]
            first = paras[0] if paras else ''
            if len(first) > 780:
                first = first.split('。')[0] + '。'
            events.append((m[0], title, first))
    for m in re.finditer(r'^[-*] `?(2026-\d\d-\d\d)`?[：:]([^\n]*(?:\n(?![-*] |##)[^\n]+)*)', s, flags=re.M):
        text = m[2].strip()
        if len(text) > 650: text = text.split('。')[0] + '。'
        events.append((m[1], m[1], text))
    events = sorted(set(events))
    if not events:
        return clean(s, p)[:6000] + '\n\n完整记录：' + link(p)
    return '\n\n'.join('**' + t + '**\n\n' + rewrite(b, p) for _, t, b in events) + '\n\n完整记录：' + link(p)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for name in ['inventory.json','source-manifest.json','validation.json']:
        if not (OUT/name).exists():(OUT/name).write_text('{}\n')
    git_dates = {}; date = ''; commit = ''
    log = subprocess.check_output(['git', 'log', '--reverse', '--format=STAMP:%H %aI', '--name-only', '--diff-filter=A', '--', 'research'], cwd=ROOT, text=True)
    for line in log.splitlines():
        if line.startswith('STAMP:'):
            commit, date = line[6:].split(); date = date[:10]
        elif line.strip(): git_dates.setdefault(line, {'date': date, 'commit': commit})
    dirs = []
    for a in sorted((ROOT / 'research').iterdir()):
        if not a.is_dir() or a.name.startswith('_') or a.name in {'platform', 'industry'}: continue
        dirs += [d for d in sorted(a.iterdir()) if d.is_dir() and d.name not in {'artifacts','diagnostics','legacy-canvas','scripts','specs','notes'}]
    dirs.append(ROOT / 'research/mu')
    for n in ['1d-small-account-slow-trend','1d-tpsa-long-account','8h-btceth-small-account-carry']:
        dirs.append(EXTERNAL / 'research/asset-portfolios' / n)
    overrides = {
        'research/hype/15m-candle-count-reversal': ('2026-05-13', 'src/strategy_lab/strategies/candle_count_short/strategy.py', 'Git 初始机制代码；后续家族名另行形成'),
        'research/hype/15m-ema-trend-breakout': ('2026-05-26', 'src/strategy_lab/strategies/hype_pullback_trend/strategy.py', 'Git 家族 V1 回踩前身；后续转为突破'),
        'research/hype/15m-ema-crossover': ('2026-06-10', 'src/strategy_lab/strategies/hype_ema_crossover_trend/strategy.py', 'Git 独立 EMA 交叉实现'),
        'research/mu': ('2026-06-17', 'scripts/compare_mu_binance_polygon_alignment.py', 'Git MU 历史研究脚本'),
    }
    families = []
    for d in dirs:
        external = not d.is_relative_to(ROOT)
        base = EXTERNAL if external else ROOT
        rel = str(d.relative_to(base))
        docs = documents(d)
        ledgers = sorted(d.glob('*core-ledger.md'))
        primary = ledgers[0] if ledgers else d / 'README.md'
        s = read(primary)
        candidates = date_candidates(d, docs, git_dates)
        first = candidates[0] if candidates else {'date': '日期待核', 'source': str(primary), 'kind': '未能确认'}
        if external: first = {'date': '2026-09-08', 'source': str(d/'decision-log.md'), 'kind': '独立工作区立项/冻结记录'}
        if rel in overrides:
            dt, oldpath, kind = overrides[rel]
            g = subprocess.check_output(['git','log','--reverse','--format=%H','--diff-filter=A','--',oldpath],cwd=ROOT,text=True).splitlines()
            if not g: raise RuntimeError(oldpath)
            rev = g[0]
            actual_date = subprocess.check_output(['git','show','-s','--format=%as',rev],cwd=ROOT,text=True).strip()
            if actual_date != dt: raise RuntimeError((oldpath,actual_date,dt))
            b = subprocess.check_output(['git','show',rev+':'+oldpath],cwd=ROOT)
            snap = OUT/'historical-source'/('family-origin-'+d.name+Path(oldpath).suffix)
            snap.write_bytes(b)
            read(snap)
            first = {'date':dt,'source':str(snap),'kind':kind,'original_path':oldpath,'commit':rev}
        specs = sorted([p for p in (d/'specs').glob('*') if p.suffix in {'.md','.json'}])
        # Large data requests, lock files and source manifests are evidence, not parameter specs.
        excerpt_specs = [p for p in specs if not re.search(r'request|manifest|requirements|exposure|loading|input|data-admissibility|audit-note|verification-plan',p.name)]
        families.append({'path':rel,'absolute_path':str(d),'external_worktree':external,'name':get_name(s,d),'primary':str(primary),'ledgers':[str(p) for p in ledgers],'docs':[str(p) for p in docs],'specs':[str(p) for p in specs],'excerpt_specs':[str(p) for p in excerpt_specs],'first_evidence':first,'date_candidates':candidates,'market':overview(s,'market'),'mechanism':overview(s,'mechanism')})
    families.sort(key=lambda a:(a['first_evidence']['date'],a['path']))
    for n,f in enumerate(families,1): f['id']=f'F{n:03d}'
    index_text = read(ROOT/'research/README.md')
    for f in families:
        if f['path'].endswith('1d-ma7-cross-atr-ratchet'): f['name']='HYPE-1D-MA7-Cross-ATR-Ratchet（MA7-CAR）'
        if f['path'].endswith('6h-rs4-regime-switch'): f['name']='HYPE-6H-RS4-Regime-Switch'
        if f['path']=='research/mu':f['name']='MU-HYPE-Transfer（扁平历史家族）'
        if f['path'].endswith('1d-ewmac-universal-trend'):
            latest=read(Path(f['absolute_path'])/'README.md')
            f['name']='Multi-Asset-1D-EWMAC-Universal-Trend'
            f['market']=overview(latest,'market');f['mechanism']=overview(latest,'mechanism')
        if not f['mechanism']:
            row=next((l for l in index_text.splitlines() if f['path'].removeprefix('research/')+'/' in l and l.startswith('|')),'')
            f['index_row']=row
    write = []
    replay_path=ROOT/'research/asset-portfolios/multi-legacy-post-registration-audit/artifacts/repository_ranking_20260911/results.json'
    replay=json.loads(read(replay_path))
    write.append(read(OUT/'editorial.md'))
    write.append('<a id="inventory"></a>\n\n## 4. 全项目家族时间索引\n\n日期为下文定义的“最早可证记录”，不是行情起点。F 编号仅用于本文定位，不是策略版本。详情按同一时间顺序排列。工作区中的重复家族沿用主仓库版本，仅把主仓库没有的三条线补入。\n')
    write.append('|编号|最早可证日期|家族/主题|交易对象或研究对象|位置|\n|---|---|---|---|---|')
    for f in families:
        market = re.sub(r'\[([^\]]+)\]\([^)]+\)',r'\1',f['market']).replace('|',' / ')
        if not market:
            a=Path(f['path']).parts[1]
            market={'hype':'HYPE；具体场所/周期见卡片','asset-portfolios':'多资产/组合或诊断主题；具体池见卡片','mu':'MU；股票与同名永续必须区分','btc':'BTC；具体周期见卡片','gold':'黄金；代理/合约见卡片','us-indexes':'美国指数/成分股；见卡片','cn-indexes':'沪深300指数代理；见卡片','sox':'SOX指数代理；见卡片'}.get(a,a.upper())
        write[-1] += '\n'+f'|{f["id"]}|{f["first_evidence"]["date"]}|[{f["name"]}](#{f["id"].lower()})|{market}|'+('5f41工作区' if f['external_worktree'] else '主仓库')+'|'
    write.append('\n<a id="families"></a>\n\n## 5. 每个家族的规则、参数、演进与证据\n\n以下主账摘录保留原结果的版本语境。**“当前”“最新”“live”均指来源文件在所记日期的叙述，不代表本次查询了生产状态。** 一个家族中的旧失败表和新修正表可同时存在；按日期阅读更正。参数摘录来自各自规格，研究合同、候选和正式版本不能合并成一套参数。完整规格均列链接。\n')
    for f in families:
        d=Path(f['absolute_path']);p=Path(f['primary']);s=read(p)
        write.append(f'<a id="{f["id"].lower()}"></a>\n\n### {f["id"]} · {f["first_evidence"]["date"]} · {f["name"]}\n')
        ev=f['first_evidence'];evp=Path(ev['source'])
        write.append(f'**时间证据：** {ev["kind"]}；{link(evp)}。'+(f' Git `{ev["commit"][:12]}`。' if ev.get('commit') else ''))
        write.append(f'**归属：** `{f["path"]}`；'+('未合并独立工作区 `5f41`。' if f['external_worktree'] else '主仓库。')+' 主来源：'+link(p)+'。')
        if f['mechanism']:write.append('**研究的交易逻辑：** '+rewrite(f['mechanism'],p))
        write.append('\n#### 家族规则、各版结果与现有边界\n\n'+clean(s,p,omit_evidence=True))
        if f['path'].endswith('1d-ewmac-universal-trend'):
            current=d/'README.md'
            write.append('\n**本次发现的身份/范围差异：** 上述旧式主账仍写Binance家族，README及P1—P4合同明确为Multi-Asset跨市场家族。本文索引采用后者；原记录不覆盖，以下补充其四轮结论，避免只看初始9资产。\n\n'+clean(read(current),current))
        later=[r for r in replay if r['family_path']==f['path']]
        if later:
            write.append('\n#### 定稿后回放：与上面的开发期成绩分开看\n\n来源：'+link(replay_path,'2026-09-11全仓固定方案结果')+'。截至9月5日的历史回放，**不是实盘净值或全新前瞻实验**；资金费完整性、不同估值频率与部分原版执行语义仍有限制。')
            write.append('|方案|身份|起止UTC|收益|最大回撤|数量|原成本/限制|\n|---|---|---|---:|---:|---|---|')
            for r in later:
                note=(r.get('cost','')+'；'+r.get('limitation','')).replace('|',' / ')
                write[-1] += '\n'+f'|{r["name"]}|{r["status"]}|{r["start"]} → {r["end"]}|{r["return_value"]*100:+.2f}%|{r["drawdown"]*100:.2f}%|{r["trades"]} {r["count_unit"]}|{note}|'
        if f['path']=='research/hype/15m-ema-trend-breakout':
            hp=d/'notes/hype-ema-tb-historical-evolution-archive-2026-08-06.md'
            write.append('\n#### 早期 V1—V34 的机制演进\n\n'+clean(read(hp),hp,True))
        write.append('\n<details>\n<summary>按日期展开决策与演进记录</summary>\n\n'+history(d)+'\n\n</details>\n')
        specs=[Path(z) for z in f['specs']]
        write.append('\n<details>\n<summary>展开参数、交易规则与执行合同</summary>\n\n**阅读方式：** 每一小节独立对应上方文件；这些是重点字段摘录，不是把全部历史实验合并后的交易规格。旧规格的费用、预热或执行时点如已修订，以同家族较新的明确修订为准。')
        if not specs:
            write.append('\n未找到独立 specs 文件。参数以主账和下列研究报告为准；未披露字段不猜填。')
            fallback=[Path(z) for z in f['docs'] if Path(z).parent.name in {'notes','diagnostics'}][:2]
            for sp in fallback:write.append('\n**'+link(sp)+'**\n\n'+spec_excerpt(sp,2500))
        else:
            for sp in [Path(z) for z in f['excerpt_specs']]:
                write.append('\n**规格：'+link(sp)+'**\n\n'+spec_excerpt(sp))
            write.append('\n**完整规格目录（含数据/执行修订）：**\n\n'+'\n'.join('- '+link(sp) for sp in specs))
        write.append('\n</details>\n')
        # All documents are discoverable even where an excerpt is intentionally short.
        write.append('\n<details>\n<summary>展开本家族全部研究文档索引</summary>\n\n'+'\n'.join('- '+link(Path(z)) for z in f['docs'])+'\n\n</details>\n')
    write.append('\n<a id="prototypes"></a>\n\n## 6. 4—6月早期代码原型与历史策略\n\n以下12项按最早机制或配置记录排序。部分发生过改名、重构，不能当12个互相独立的盈利发现。参数为退役前可恢复源码的 **默认配置快照**，不是所有历史运行的实际参数；实际运行曾通过配置覆盖。源码现已不在活跃包中，本次从Git只读恢复为证据，未重新运行。\n')
    proto=json.loads(read(OUT/'historical-prototypes.json'))
    for row in proto:
        read(ROOT/row['snapshot'])
        write.append(f'### H-{row["id"]} · {row["date"]} · {row["name"]}\n\n历史路径：`{row["original_path"]}`；参数快照提交 `{row["commit"][:12]}`；'+link(ROOT/row['snapshot'],'原始源码快照')+'。\n\n默认交易池表达：'+('；'.join('`'+v+'`' for v in row['symbol_defaults']) or '专用 BTC 实现；具体输入池由运行配置提供')+'。')
        write.append('|字段|默认值|\n|---|---|\n'+'\n'.join('|`'+k+'`|`'+v.replace('|',' / ')+'`|' for k,v in row['parameters']))
    write.append(read(OUT/'historical-editorial.md'))
    write.append('\n<a id="archive"></a>\n\n## 7. 归档研究：早期迁移、外部21策略与浅层实验\n\n这里保留历史来源、已知标的与参数/结论。旧 Canvas 转换曾丢失表格，空白数字或“未完全解析”不补造；原文中的推荐、当前、最优和实盘语句只是当时记录，不能覆盖现行主账。Minara榜单收益是原文声称，不能当作本仓复现。\n')
    archive_docs=[p for p in sorted((ROOT/'archive/research').rglob('*.md')) if p.name!='README.md' and not p.name.startswith('15m-live-execution')]
    for i,p in enumerate(archive_docs,1):
        s=read(p); title=re.search(r'^# (.+)',s,re.M)
        write.append(f'### A-H{i:02d} · '+(title[1] if title else p.stem)+'\n\n来源：'+link(p)+'。原始研究日期未逐份确认；位于早期归档，文件迁移日期不当成创建日。\n\n'+clean(s,p))
    write.append('\n<a id="public100"></a>\n\n## 8. PUBLIC100：100个原编号逐项规则与状态\n\n本项目从2026-09-08开始整理这份清单，9月9日续测、9月10日整理规则、9月24日修正分类和未完成原因。这里的时间是**本项目研究时间**，不是外部策略发明时间。100项包含同源变体和组件；不得与139个家族/主题简单相加成独立策略数量。\n\n最新归档：26项账户诊断（25项有交易，D2零交易），D6为部分仓位估算，73项无数值，正式验证通过0项。以下采用9月24日修正后的说明，并保留R2已经存在的账户结果。\n')
    pub=ROOT/'research/asset-portfolios/multi-public-strategies-100'
    classification=json.loads(read(pub/'artifacts/classification-audit-20260924/classification-100.json'))
    status=json.loads(read(pub/'artifacts/continuation-r2/status-100.json'))
    state={r['id']:r for r in status['rows']}
    reviews={r['id']:r for r in json.loads(read(pub/'artifacts/strategy-review-100.json'))['rows']}
    r2_results=[]
    for folder in ['b5','equities','funding','source-corrections']:
        r2_results+=json.loads(read(pub/'artifacts/continuation-r2'/folder/'results.json'))['results']
    groups={r['id']:r['name'] for r in classification['groups']}
    write.append('|主要主题|条目数|已有账户诊断|\n|---|---:|---:|\n'+'\n'.join(f'|{g["name"]}|{g["count"]}|{g["account_count"]}|' for g in classification['groups']))
    for r in classification['rows']:
        write.append(f'\n<a id="public-{r["id"].lower()}"></a>\n\n### PUBLIC100-{r["id"]} · {r["name"]}\n')
        fields=[('类型',groups[r['primary_theme_13']]),('交易工具',r['instrument']),('资产池/持仓结构',r['structure']),('信号输入',r['primary_information']),('处理方法',r['model_method']),('观察/决策周期',r['decision_clock_group']),('入场与主要参数',r['entry']),('持仓/仓位',r['holding']),('退出',r['exit']),('最新证据状态',r['current_status']),('实际结果/障碍',r['current_detail']),('继续研究前缺什么',r['next_needed'])]
        if r.get('audit_correction'):fields.append(('9月24日更正',r['audit_correction']))
        if r.get('scope_notes'):fields.append(('边界',r['scope_notes']))
        write.append('|项目|记录|\n|---|---|\n'+'\n'.join('|'+k+'|'+str(v).replace('|',' / ').replace('\n','；')+'|' for k,v in fields))
        write.append('\n**演进与身份：** '+r['specific_version_chronology']+' 本项目原编号不变；文字版、源码版、修正版保留为不同对象。')
        variants=state.get(r['id'],{}).get('variants',[])
        if any(isinstance(v,str) for v in variants):
            variant_names=[v for v in variants if isinstance(v,str)]
            variants=[v for v in variants if isinstance(v,dict)]+[v for v in r2_results if v['id']==r['id'] and v.get('variant') in variant_names]
        if variants:
            write.append('\n**已有账户变体结果（归档资料，未重新回测）：**\n\n|变体/标的|每边成本口径|样本|总收益|年复合|回撤|交易/订单数|证据状态|\n|---|---|---|---:|---:|---:|---|---|')
            for v in variants:
                def percent(z): return '未列' if z is None else f'{z*100:.2f}%'
                fee=str(v['cost_bps'])+' bps' if 'cost_bps' in v else str(v.get('fee','未列'))+' fee'
                dd=v.get('mdd',v.get('wallet_stats',{}).get('max_drawdown_account',v.get('realized_drawdown')))
                write[-1] += '\n'+'|'+str(v.get('variant',v.get('strategy',r['id'])))+' '+str(v.get('symbol',''))+'|'+fee+'|'+str(v.get('start',''))+' → '+str(v.get('end',''))+'|'+percent(v.get('total_return'))+'|'+percent(v.get('cagr'))+'|'+percent(dd)+'|'+str(v.get('trades',v.get('order_count','未列')))+'|'+str(v.get('status',''))+'|'
            write.append('\n回撤正负号保留各来源惯例；D组钱包/账户回撤与其他逐日净值口径不同，不能直接排名。')
        code_meta=reviews.get(r['id'],{}).get('extracted_code',{})
        cp=pub/code_meta.get('path','__absent__')
        if cp.is_file():
            code=read(cp);clines=[]
            for n,line in enumerate(code.splitlines(),1):
                if re.search(r'\b(?:self\.)?[A-Za-z_]\w*\s*=\s*[-+]?\d|\.\b(?:SMA|EMA|RSI|ADX|ATR|MOM|ROC|BB|SetHoldings|SetCash|SetWarmUp|AddEquity|AddCrypto|AddFuture|AfterMarketOpen|BeforeMarketClose)\(',line) or ('[:' in line and re.search(r'\d',line)):
                    if not line.strip().startswith('#'):clines.append((n,line.strip()))
            if clines:
                write.append('\n<details>\n<summary>展开已恢复源码中的具体数值/工具设置（不是额外冻结版本）</summary>\n\n“原清单未给”不表示源码没有。以下按原行号摘录配置与规则常数，可能含源码缺陷或与文字冲突；应和上方更正一起读。完整上下文：'+link(cp)+'。\n\n|源码行|字段或语句原文|\n|---:|---|\n'+'\n'.join('|'+str(n)+'|<code>'+line.replace('&','&amp;').replace('<','&lt;').replace('>','&gt;').replace('|','&#124;')+'</code>|' for n,line in clines[:55])+'\n\n</details>')
        sf=[pub/z for z in r.get('local_source_files',[])]
        write.append('\n**来源：** '+link(pub/'artifacts/classification-audit-20260924/classification-100.json','9月24日逐项分类与修正')+'；'+link(pub/'artifacts/continuation-r2/status-100.json','R2逐项结果')+'。')
        if sf:write.append('\n本地原始材料：'+' · '.join(link(z) for z in sf if z.exists()))
        if r.get('source_url'):write.append('\n原始外部入口（本次不重抓网页）：[原始来源]('+r['source_url']+')。')
    write.append(read(OUT/'closing.md'))
    write.append('\n<a id="audit"></a>\n\n## 10. 覆盖、来源和限制\n\n')
    write.append(f'- 本轮逐目录覆盖主仓库 **{sum(not f["external_worktree"] for f in families)}** 个策略家族或研究主题（其中MU扁平历史家族单计），并补充工作区 **{sum(f["external_worktree"] for f in families)}** 个独有家族；合计 **{len(families)}** 张卡片。\n- 主仓库卡片直接引用 **{sum(len(f["ledgers"]) for f in families if not f["external_worktree"])}** 份家族主账。其他README兼任入口；`artifacts/`内主账备份没有重复计数；平台数据治理主账不计入策略。\n- 另收录12个早期源码原型、{len(archive_docs)}份历史研究记录，以及PUBLIC100的100个原编号。Minara 21项位于历史记录内；上述数字互相重叠，不能加总成“总策略数”。\n- 所有本次使用来源按字节数和SHA256登记；这验证资料引用的一致性，不是验证其回测或数据正确。\n- 本轮完成文档与参数资料整理，没有重跑所有引擎、重新训练模型、重验市场数据或查看生产服务。统计采用截至2026-09-25本机可读取的工作副本，含已有未提交材料。\n- 工作区0498的同名家族已在主仓库找到，避免重复；5f41的三家族独立保留。未遍历项目外的其他研究仓库或所有已删除Git历史产物；已删除且无留存的研究不可凭文件名还原。\n')
    counts=Counter(Path(f['path']).parts[1] for f in families)
    write.append('\n|资产/研究目录|本次卡片数|\n|---|---:|\n'+'\n'.join(f'|{k}|{v}|' for k,v in sorted(counts.items())))
    write.append('\n结构化盘点：'+link(OUT/'inventory.json','inventory.json')+'；来源指纹：'+link(OUT/'source-manifest.json','source-manifest.json')+'；覆盖与链接验证：'+link(OUT/'validation.json','validation.json')+'。\n')
    # Create named artifacts before linking; they are replaced below with final contents.
    (OUT/'inventory.json').write_text(json.dumps(families,ensure_ascii=False,indent=2))
    REPORT.write_text('\n\n'.join(write).strip()+'\n')
    (OUT/'source-manifest.json').write_text(json.dumps({'as_of':'2026-09-25','sources':list(SOURCES.values()),'missing_inherited_references':sorted(MISSING)},ensure_ascii=False,indent=2))
    print(json.dumps({'report':str(REPORT),'families':len(families),'archive_docs':len(archive_docs),'spec_files':sum(len(f['specs']) for f in families),'sources':len(SOURCES),'characters':len(REPORT.read_text()),'bytes':REPORT.stat().st_size,'inherited_missing_refs':len(MISSING)},ensure_ascii=False))
    subprocess.run([sys.executable, str(TOPIC/'scripts/make_strategy_chronology_self_contained_20260925.py')], check=True)


if __name__ == '__main__':
    main()
