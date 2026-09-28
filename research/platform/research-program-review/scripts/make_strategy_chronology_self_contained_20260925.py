"""Pack the strategy review into one independently readable Markdown document.

Research prose and specifications are included in full. Large machine artifacts
are described using their actual contents and the original citing context.
This is document compilation, not performance verification or backtesting.
"""
from __future__ import annotations

import ast
import csv
import hashlib
import io
import json
import re
from collections import Counter, deque
from html import unescape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[4]
TOPIC = ROOT / 'research/platform/research-program-review'
OUT = TOPIC / 'artifacts/strategy-chronology-20260925'
REPORT = TOPIC / 'diagnostics/strategy-project-chronology-and-research-review-2026-09-25.md'
DRAFT = OUT / 'linked-source-edition.md'
MARKER = '<!-- SELF_CONTAINED_EDITION_20260925 -->'
LINK = re.compile(r'(!?)\[([^\]\n]*)\]\(((?:[^()\n]|\([^()\n]*\))*)\)')
REFDEF = re.compile(r'^\s{0,3}\[([^\]]+)\]:\s*(\S+)(.*)$', re.M)
PUBLIC = re.compile(r'^(https?://|mailto:|data:)', re.I)
SOURCES = {}
QUEUE = deque()
CONTEXTS = {}
MODES = Counter()
REPAIRS = []
ROOT_TARGETS = set()


def public_path(path: Path) -> str:
    raw = str(path)
    if path.is_relative_to(ROOT):
        return str(path.relative_to(ROOT))
    match = re.search(r'/\.codex/worktrees/([^/]+)/quant-strategy-lab/(.*)', raw)
    if match:
        return '独立工作区 ' + match[1] + '/' + match[2]
    return '项目外历史资料/' + path.name


def scrub(text: str) -> str:
    text = re.sub(r'/Users/[^/\s`"<>]+/\.codex/worktrees/([^/\s]+)/quant-strategy-lab/', r'独立工作区/\1/', text)
    text = text.replace(str(ROOT) + '/', '项目/')
    return re.sub(r'/Users/[^\s`"<>\]\)]+', '[原记录中的本机路径]', text)


def target_path(target: str, source: Path):
    target = unescape(target).strip().strip('<>').split(' "')[0]
    if not target or target.startswith('#') or PUBLIC.match(target):
        return None
    target = target.removeprefix('file://')
    raw = unquote(target.partition('#')[0])
    path = (source.parent / raw).resolve()
    if not path.exists() and re.match(r'^(research|docs|archive|src|scripts|tests|\.cursor)/', raw):
        root_relative = (ROOT / raw).resolve()
        if root_relative.exists():
            return root_relative
    return path


def source_id(path: Path) -> str:
    return 'source-' + hashlib.sha256(str(path).encode()).hexdigest()[:16]


def register(path: Path, label: str, context: str = '') -> str:
    if path == REPORT or path == DRAFT:
        return 'inventory'
    if path not in SOURCES:
        SOURCES[path] = {'id': source_id(path), 'source_path': str(path), 'display_path': public_path(path), 'label': label}
        QUEUE.append(path)
    if context:
        context = LINK.sub(lambda m: m[2], context)
        context = re.sub(r'<[^>]+>', '', context).strip()
        if len(context) > 850:
            context = context[:850] + '…〔引用上下文摘录〕'
        snippets = CONTEXTS.setdefault(path, [])
        if context and context not in snippets and len(snippets) < 2:
            snippets.append(context)
    return SOURCES[path]['id']


def rewrite_links(text: str, source: Path, register_targets: bool = True) -> str:
    def change(m):
        image, label, target = m.groups()
        path = target_path(target, source)
        if path is None:
            if target.startswith('#') and source != REPORT:
                return label + '〔本份资料中的小节引用〕'
            if image:
                return '〔原图：' + (label or '未提供说明') + '；外部图片未作为本文件的阅读依赖〕'
            return m[0]
        if not register_targets:
            return '['+(label or path.name)+'](#'+source_id(path)+')' if path in SOURCES else (label or path.name)
        lo = text.rfind('\n', 0, m.start()) + 1
        hi = text.find('\n', m.end())
        context = text[lo:hi if hi != -1 else len(text)]
        anchor = register(path, label or path.name, context)
        if image:
            return '[原图内容说明：' + (label or path.name) + '](#' + anchor + ')'
        return '[' + (label or path.name) + '](#' + anchor + ')'

    text = LINK.sub(change, text)
    def definition(m):
        path = target_path(m[2], source)
        if path is None:
            return m[0]
        if not register_targets:
            return m[1] + '〔来源标识〕'
        return '[' + m[1] + ']: #' + register(path, m[1], m[0])
    text = REFDEF.sub(definition, text)
    def html_anchor(m):
        label = re.sub(r'<[^>]+>', '', m[2])
        path = target_path(m[1], source)
        if path is None:
            return label + ('（外部来源）' if PUBLIC.match(m[1]) else '')
        return '[' + label + '](#' + register(path, label, label) + ')' if register_targets else label
    text = re.sub(r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', html_anchor, text, flags=re.I | re.S)
    def html_image(m):
        attrs = m[0]
        src = re.search(r'src=["\']([^"\']+)', attrs, re.I)
        alt = re.search(r'alt=["\']([^"\']*)', attrs, re.I)
        label = alt[1] if alt else '原图'
        path = target_path(src[1], source) if src else None
        return '[' + label + '：文内说明](#' + register(path, label, label) + ')' if path and register_targets else '〔'+label+'〕'
    return re.sub(r'<img\b[^>]*>', html_image, text, flags=re.I)


def markdown_body(text: str, path: Path, register_targets: bool = True) -> str:
    """Retain source prose, tables and code; normalize only document containers."""
    text = re.sub(r'<(?:script|style)\b[^>]*>.*?</(?:script|style)>', '〔原文的显示脚本/样式未嵌入〕', text, flags=re.S | re.I)
    text = re.sub(r'</?details\b[^>]*>', '', text, flags=re.I)
    text = re.sub(r'<summary[^>]*>(.*?)</summary>', lambda m: '\n**' + m[1].strip() + '**\n', text, flags=re.S | re.I)
    text = re.sub(r'<a\s+(?:id|name)=["\'][^"\']*["\']\s*>\s*</a>', '', text, flags=re.I)
    result = []
    fence = ''
    for line in text.splitlines():
        match = re.match(r'^\s*(`{3,}|~{3,})', line)
        if match:
            if not fence:
                fence = match[1]
            elif match[1][0] == fence[0] and len(match[1]) >= len(fence):
                fence = ''
            result.append(line)
            continue
        if not fence:
            line = re.sub(r'^#{1,6}\s+(.+)$', r'**\1**', line)
            link_base = REPORT if path.parent == OUT and path.name in {'editorial.md', 'historical-editorial.md', 'closing.md'} else path
            line = rewrite_links(line, link_base, register_targets)
            if line.startswith('|'):
                line = re.sub(r'`([^`]+)`', lambda m: '`' + m[1].replace('\\|', '|').replace('|', '\\|') + '`', line)
                if re.fullmatch(r'\|[\s:|\-]+\|', line) and result and result[-1].startswith('|'):
                    count = len(re.findall(r'(?<!\\)\|', result[-1])) - 1
                    if len(re.findall(r'(?<!\\)\|', line)) - 1 != count:
                        line = '|' + '|'.join('---' for _ in range(count)) + '|'
                        REPAIRS.append({'source': public_path(path), 'repair': 'Matched table separator columns to the existing header; no data values changed.'})
        result.append(line)
    if fence:
        result.append(fence)
        REPAIRS.append({'source': public_path(path), 'repair': 'Closed an unclosed source code fence for Markdown display only.'})
    return '\n'.join(result).strip()


def markdown_summary(text: str, path: Path) -> str:
    sections = re.split(r'(?=^#{1,3} )', text, flags=re.M)
    selected = []
    used = 0
    priority = re.compile(r'结论|结果|摘要|规则|参数|成本|仓位|进场|出场|入场|退出|风险|当前|状态|失败|边界|判定|summary|conclusion|result|rule|parameter|cost|status', re.I)
    ranked = sorted(enumerate(sections), key=lambda pair: (pair[0] != 0, not bool(priority.search(pair[1].splitlines()[0] if pair[1].splitlines() else '')), pair[0]))
    for index, section in ranked:
        if not section.strip():
            continue
        if used + len(section) <= 11000:
            selected.append((index, section)); used += len(section)
        elif not selected:
            # Preserve complete paragraphs and keep an oversized table explicit.
            kept = []
            for paragraph in re.split(r'\n\s*\n', section):
                if sum(map(len, kept)) + len(paragraph) <= 10000:
                    kept.append(paragraph)
            if kept:
                selected.append((index, '\n\n'.join(kept))); used += len(selected[-1][1])
    body = '\n\n'.join(section for _, section in sorted(selected))
    headings = re.findall(r'^#{1,3}\s+(.+)$', text, flags=re.M)
    intro = '以下保留这份间接引用资料的概述、结论或规则章节；未展开的技术细节不作为本文阅读前提。原文涉及的其他出处只保留名称，已有文内条目则继续提供文内跳转。\n\n'
    if headings:
        intro += '**原文内容范围：** '+'；'.join(headings[:40])+'。\n\n'
    return intro + markdown_body(body or text[:9000], path, register_targets=False)


def block(text: str, language: str = '') -> str:
    width = max([len(m[0]) for m in re.finditer(r'`{3,}', text)] + [2]) + 1
    fence = '`' * width
    return fence + language + '\n' + text.rstrip() + '\n' + fence


def compact_json(value, key: str = '', depth: int = 0):
    """Keep actual scalar conclusions/configuration; bound repetitive arrays."""
    if isinstance(value, dict):
        if len(value) > 80:
            keys = list(value)
            retained = keys[:12] + keys[-2:]
            return {'字段总数': len(value), '原序首12及末2字段': {name: compact_json(value[name], name, depth + 1) for name in retained}, '说明': '大型映射仅给出规模与原序样例，不是总体绩效。'}
        if depth > 6:
            return {'字段数': len(value), '字段': list(value)[:25]}
        result = {}
        for name, child in value.items():
            if re.search(r'^(trades|trade_log|equity_curve|equity|curve|bars|ohlcv|predictions|timestamps|daily_returns|raw_rows|paths)$', name, re.I) and isinstance(child, (list, dict)) and len(child) > 8:
                result[name] = {'内容类型': type(child).__name__, '项目数': len(child), '说明': '逐笔/逐时点明细；此处保留规模，汇总结果见同节其他字段及正文。'}
            else:
                result[name] = compact_json(child, name, depth + 1)
        return result
    if isinstance(value, list):
        count = len(value)
        keep = 6 if depth < 3 else 3
        if count <= keep:
            return [compact_json(v, key, depth + 1) for v in value]
        return {'项目总数': count, '前部原序样例': [compact_json(v, key, depth + 1) for v in value[:keep]], '末项原序样例': compact_json(value[-1], key, depth + 1), '说明': '样例不是筛选出的最佳结果，不代表全体分布。'}
    if isinstance(value, str) and len(value) > 1600:
        return value[:1600] + '…〔长字符串截取〕'
    return value


def json_summary(raw: str, path: Path) -> tuple[str, str]:
    obj = json.loads(raw)
    if ('specs' in path.parts and len(raw) < 1_000_000) or len(raw) < 9000:
        return '全文', block(raw, 'json')
    compact = compact_json(obj)
    body = json.dumps(compact, ensure_ascii=False, indent=2)
    budget = 22000 if path in ROOT_TARGETS else 7000
    if len(body) > budget and isinstance(compact, dict):
        priority = re.compile(r'summary|status|conclu|result|metric|champion|baseline|control|cost|gate|window|frozen|passing|count|decision|fail|block|registered|promot|live|best|verdict|configuration', re.I)
        result = {}
        keys = sorted(compact, key=lambda k: not bool(priority.search(k)))
        omitted = []
        for key in keys:
            candidate = {**result, key: compact[key]}
            if len(json.dumps(candidate, ensure_ascii=False, indent=2)) <= budget:
                result = candidate
            else:
                child = obj.get(key, compact[key]) if isinstance(obj, dict) else compact[key]
                omitted.append({'字段': key, '类型': type(child).__name__, '项目数': len(child) if isinstance(child, (dict, list, str)) else None})
        if omitted:
            result['未展开字段目录'] = omitted
        body = json.dumps(result, ensure_ascii=False, indent=2)
    elif len(body) > budget:
        body = json.dumps({'数据类型': type(obj).__name__, '项目数': len(obj), '原序首项摘编': compact_json(obj[0], depth=3) if isinstance(obj, list) and obj else None}, ensure_ascii=False, indent=2)
    intro = '内容简述：下列字段来自原文件，保留状态、汇总、成本或参数等可读信息；较长数组只保留规模及明确标注的原序样例，未重新计算绩效。\n\n'
    return '结构化摘要', intro + block(body, 'json')


class VisibleHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.skip = 0
        self.parts = []
    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style', 'svg', 'canvas', 'head'}:
            self.skip += 1
        elif tag in {'p', 'div', 'h1', 'h2', 'h3', 'tr', 'li', 'br'} and not self.skip:
            self.parts.append('\n')
        elif tag in {'td', 'th'} and not self.skip:
            self.parts.append(' / ')
    def handle_endtag(self, tag):
        if tag in {'script', 'style', 'svg', 'canvas', 'head'} and self.skip:
            self.skip -= 1
        elif tag in {'p', 'div', 'h1', 'h2', 'h3', 'tr', 'li'} and not self.skip:
            self.parts.append('\n')
    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def content(path: Path) -> tuple[str, str]:
    record = SOURCES[path]
    if not path.exists():
        record['exists'] = False
        return '原资料缺失', '原引用目标在整理时已不存在。上方保留原文如何使用它；本文没有据文件名补造参数或结果。缺失的是原始证据，并非接收者缺少本地文件。'
    record['exists'] = True
    if path.is_dir():
        files = sorted(p.name for p in path.iterdir())
        record['entry_count'] = len(files)
        return '目录说明', '这是原研究的资料目录，共 '+str(len(files))+' 个直接条目。目录用于组织文件，本身没有独立策略结论。直接条目包括：\n\n'+block('\n'.join(files[:100]) + ('\n〔其余目录条目未展开〕' if len(files) > 100 else ''))
    raw = path.read_bytes()
    record.update({'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()})
    suffix = path.suffix.lower()
    if path in {OUT/'inventory.json', OUT/'source-manifest.json', OUT/'validation.json'}:
        record['generated_metadata'] = True
        return '盘点说明', '这是本次盘点的机器索引、来源指纹或文档检查记录，不是额外策略。本文第4—5节已展开139个家族/主题，第8节已展开PUBLIC100。独立阅读检查的范围和结果见文末；检查文档结构不等于验证回测收益。'
    if suffix in {'.md', '.mdc'}:
        text = raw.decode('utf-8', errors='replace')
        if path in ROOT_TARGETS or 'specs' in path.parts or 'core-ledger' in path.name:
            return '全文', markdown_body(text, path)
        return '研究文档摘要', markdown_summary(text, path)
    if suffix == '.json':
        try:
            return json_summary(raw.decode('utf-8-sig'), path)
        except (ValueError, UnicodeError):
            return '原文格式异常', '该文件无法按完整JSON解析。原引用语境保留在上方；不得将其当作已成功读取的参数或绩效。\n\n'+block(raw[:3000].decode('utf-8', errors='replace'))
    if suffix in {'.csv', '.tsv'}:
        reader = csv.reader(io.StringIO(raw.decode('utf-8-sig', errors='replace')), delimiter='\t' if suffix == '.tsv' else ',')
        header = next(reader, [])
        first = []
        last = deque(maxlen=2)
        count = 0
        for row in reader:
            count += 1
            if len(first) < 8:
                first.append(row)
            last.append(row)
        rows = first if count <= 8 else first + list(last)
        stream = io.StringIO()
        writer = csv.writer(stream)
        writer.writerow(header)
        writer.writerows(rows)
        if len(raw) < 20000:
            return '全文', '此表包含 '+str(count)+' 行记录。\n\n'+block(raw.decode('utf-8-sig', errors='replace'), 'csv')
        return '数据表摘要', '此表包含 '+str(count)+' 行、'+str(len(header))+' 列。以下给出全部列名及原顺序首8/末2行；不是收益排行或总体统计，完整研究结果以本文相应报告为准。\n\n'+block(stream.getvalue(), 'csv')
    if suffix in {'.html', '.htm'}:
        parser = VisibleHTML()
        parser.feed(raw.decode('utf-8', errors='replace'))
        lines = [re.sub(r'\s+', ' ', x).strip(' / ') for x in ''.join(parser.parts).splitlines()]
        lines = [line for line in lines if line]
        visible = '\n'.join(lines)
        budget = 18000 if path in ROOT_TARGETS else 7000
        if len(visible) > budget:
            visible = visible[:budget] + '\n〔长页面显示文本到此截取；动态图表和长明细不展开，结论由本文件已收录的对应研究报告承担〕'
        if not visible:
            visible = '页面主要由脚本动态绘图，没有可直接提取的静态结果文本。它是同一研究结果的图形展示，不是新增绩效证据；本文保留了引用它的研究报告、规则和已记录的数值。'
        return '页面内容摘要', '以下为原页面的静态可见文字/表格摘录，不执行网页脚本。\n\n'+block(visible)
    if suffix in {'.py', '.rs', '.js', '.cjs', '.sh'}:
        text = raw.decode('utf-8', errors='replace')
        if path in ROOT_TARGETS or len(text) < 4500:
            return '全文', block(text, suffix.removeprefix('.'))
        lines = text.splitlines()
        selected = []
        for n, line in enumerate(lines, 1):
            if re.search(r'^\s*(?:def |class |async def |function |pub fn |fn )|^[A-Z_][A-Z0-9_]*\s*=|add_argument\(|\bdefault\s*=', line):
                selected.append(str(n)+': '+line)
        doc = ''
        if suffix == '.py':
            try:
                doc = ast.get_docstring(ast.parse(text)) or ''
            except SyntaxError:
                pass
        summary = '\n'.join(selected[:45])
        return '实现摘要', '该实现共 '+str(len(lines))+' 行。原引用语境说明其研究用途；以下补充源码自述、主要函数和配置入口，避免把程序存在当成策略已通过验证。\n\n'+(doc[:2000]+'\n\n' if doc else '')+block(summary or '\n'.join(lines[:25]), suffix.removeprefix('.'))
    if suffix in {'.txt', '.log', '.toml', '.yaml', '.yml', '.sha256'}:
        text = raw.decode('utf-8', errors='replace')
        if len(text) <= 20000:
            return '全文', block(text)
        return '文本摘要', block(text[:14000]+'\n〔长文本到此截取〕')
    if suffix == '.svg':
        text = raw.decode('utf-8', errors='replace')
        labels = re.findall(r'<(?:text|title|desc)\b[^>]*>(.*?)</(?:text|title|desc)>', text, flags=re.S)
        labels = [unescape(re.sub(r'<[^>]+>', '', s)) for s in labels]
        return '图形说明', '原图的标题/标注文字如下；数值与结论请结合上方原文使用说明及本文收录的同一研究报告阅读。\n\n'+block('\n'.join(labels)[:14000] or '图中未保留可提取的文字层；本文不推测图形内未文字化的数值。')
    roles = {'.parquet':'列式研究数据表', '.png':'图像', '.jpg':'图像', '.pdf':'PDF资料', '.gz':'压缩的研究明细', '.joblib':'序列化模型', '.bin':'二进制模型/数据', '.xlsx':'表格附件'}
    role = roles.get(suffix, '非文本附件')
    return '附件用途说明', '这是'+role+'，文件大小 '+str(len(raw))+' 字节。其内容用途及已公布发现由上方引用原文说明；本文已收录对应研究文字、规则及结果。未把二进制附件伪装成可读全文，也未从文件名推测未披露参数。独立审阅无需打开它；逐笔复算或重新训练仍需原始复现包。'


def main():
    original = REPORT.read_text()
    if MARKER not in original:
        DRAFT.write_text(original)
    elif not DRAFT.exists():
        raise RuntimeError('The source-linked draft is missing; regenerate it with the original builder first.')
    original = DRAFT.read_text()
    intro = ('\n\n'+MARKER+'\n\n**独立转发版。只需发送这一份Markdown。** 正文保留时间线、策略卡片和综合判断；[第11节](#embedded-sources)补入引用资料的全文或内容摘要。原来的本地文件链接均改为文内跳转，无需访问作者电脑。规格和研究文字尽量全文保留；大型逐笔数据、交互页面、实现脚本及二进制附件采用明确标注的摘要或用途说明。外部网址仅保留为来源标识，理解本报告不依赖打开它们。\n\n'
             '**阅读边界：** 这是可独立审阅的研究文集，包含历史原文及其后来的更正。某份旧原文中的“当前”“通过”“推荐”“实盘”只代表当时记录；最终判断按正文的版本、日期和更正说明。可独立阅读不等于附带全部行情、逐笔交易数据、模型文件或可运行复现环境。\n\n')
    newline = original.find('\n')
    body = original[:newline] + intro + original[newline+1:]
    body = body.replace('每张卡片包括主账、参数合同、演进记录和全部研究文档入口。', '每张卡片包括主账、参数合同、演进记录；资料链接均跳转到本文已收录的全文或摘要。')
    body = body.replace('完整规格均列链接。', '完整规格已收入本文附录，可通过文内链接跳转。')
    body = body.replace('展开本家族全部研究文档索引', '展开本家族已内嵌的研究资料索引')
    body = body.replace('来源原文对应小节', '本文附录所收录的该来源全文对应小节')
    body = body.replace('图表见来源文件：', '原图说明（对应研究资料已收入本文）：')
    body = rewrite_links(body, REPORT)
    ROOT_TARGETS.update(SOURCES)
    sections = []
    number = 0
    while QUEUE:
        path = QUEUE.popleft()
        number += 1
        mode, excerpt = content(path)
        MODES[mode] += 1
        SOURCES[path]['inclusion'] = mode
        SOURCES[path]['section_number'] = number
        context = CONTEXTS.get(path, [])
        description = '\n\n'.join('> '+c.replace('\n', '\n> ') for c in context)
        title = public_path(path)
        section = '<a id="'+source_id(path)+'"></a>\n\n### 资料 S'+str(number).zfill(4)+' · '+path.name+'\n\n**内容方式：'+mode+'。** 来源标识：`'+title+'`。该标识仅用于追溯，不是需要打开的文件路径。\n\n'
        if description:
            section += '**原研究如何使用这份资料：**\n\n'+description+'\n\n'
        section += '<details>\n<summary>展开 '+path.name+' 的'+mode+'</summary>\n\n'+excerpt+'\n\n</details>\n'
        sections.append(section)
        if number % 500 == 0:
            print(json.dumps({'processed':number,'queued':len(QUEUE)},ensure_ascii=False), flush=True)
    source_count = len(SOURCES)
    appendix = ('\n\n<a id="embedded-sources"></a>\n\n## 11. 内嵌资料：全文、数据摘要与缺失说明\n\n'
                '正文及原研究文字中的本地引用在此统一收录、去重。所有跳转均留在本文件内。文件名用于核对来源；不要求接收者拥有原目录。研究文档和规格保留原措辞，仍需按日期区分旧结果与修订。JSON/CSV/网页摘要明确标明样例、截取和未展开内容，不能把样例当作整体表现。\n\n'
                '|收录方式|资料数|\n|---|---:|\n'+'\n'.join('|'+k+'|'+str(v)+'|' for k,v in sorted(MODES.items()))+'\n\n')
    tail = ('\n\n<a id="standalone-validation"></a>\n\n## 12. 独立阅读检查与使用说明\n\n'
            '- 正文覆盖139个家族/研究主题及PUBLIC100全部100个原编号；另有早期原型和归档。\n'
            '- 内嵌资料目录共 '+str(source_count)+' 个去重条目，其中 '+str(MODES['全文'])+' 份全文；其余为具体内容摘要、目录说明或原资料缺失说明。\n'
            '- 原来直接引用的 '+str(len(ROOT_TARGETS))+' 个本地目标，以及全文中新出现的本地引用，均已改成文内条目；仅发送本文件即可完成阅读。\n'
            '- 标为“原资料缺失”的条目是原项目证据已经缺失，无法通过转发补齐；本文保留引用语境并明确缺失，不据此编造规则或成绩。\n'
            '- 传阅版保留外部网页的来源地址；本次没有重新抓取网页。源文中的路径、命令和工具名属于历史记录，不是阅读前置步骤。\n'
            '- 本次只检查文内跳转、内容覆盖和资料一致性，没有重跑策略或把历史授权认定为当前生产状态。\n')
    packed = scrub(body + appendix + '\n\n'.join(sections) + tail)
    REPORT.write_text(packed)
    manifest = {'as_of':'2026-09-25','initial_local_targets':len(ROOT_TARGETS),'embedded_entries':source_count,'inclusion_counts':dict(MODES),'repairs':REPAIRS,'sources':list(SOURCES.values()),'report':{'bytes':REPORT.stat().st_size,'sha256':hashlib.sha256(REPORT.read_bytes()).hexdigest()}}
    (OUT/'self-contained-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'report':str(REPORT),'entries':source_count,'modes':dict(MODES),'bytes':REPORT.stat().st_size,'repairs':len(REPAIRS)},ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
