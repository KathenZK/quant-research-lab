import fs from "node:fs/promises";
import path from "node:path";
import { Workbook, SpreadsheetFile } from "@oai/artifact-tool";

const [input, outdir] = process.argv.slice(2);
if (!input || !outdir) throw new Error("Provide normalized data and output directory");
const data = JSON.parse(await fs.readFile(input, "utf8"));
const wb = Workbook.create();
const money = '#,##0.00;[Red](#,##0.00);"–"';
const pct = '#,##0.00%;[Red](#,##0.00%);"–"';
const shortFund = x => x.startsWith("观察") ? "资金费估算" : x.startsWith("未计") ? "价格对照·资金缺失" : "价格对照";
const color = {ink: "#243449", head: "#25384B", gray: "#667085", loss: "#AD332D", stripe: "#F4F6F8"};
const column = n => { let x = n + 1, s = ""; while (x) { const r = (x - 1) % 26; s = String.fromCharCode(65 + r) + s; x = Math.floor((x - 1) / 26); } return s; };
const sheets = [], formulaChecks = [];
const C = (key, label, type="text", width=18) => ({key, label, type, width});

function tab(name, title, subtitle, columns, rows, formulas={}) {
  const s = wb.worksheets.add(name);
  s.showGridLines = false;
  const last = rows.length + 5, end = column(columns.length - 1);
  s.getRange(`A1:${end}${Math.max(last, 6)}`).format = {font: {name: "Arial", size: 10, color: color.ink}, rowHeight: 24, verticalAlignment: "center"};
  s.getRange("A2").values = [[title]];
  s.getRange("A2").format.font = {name: "Arial", size: 14, bold: true, color: color.ink};
  s.getRange("A3").values = [[subtitle]];
  s.getRange("A3").format.font = {name: "Arial", size: 10, italic: true, color: color.gray};
  s.getRange(`A4:${end}4`).format.borders = {bottom: {style: "thin", color: "#B8C2CC"}};
  s.getRange(`A5:${end}5`).values = [columns.map(c => c.label)];
  const mapped = rows.map(r => columns.map(c => {
    const v = c.key === "funding" ? shortFund(r[c.key]) : r[c.key];
    if (v == null) return c.type === "date" || c.type === "month" ? null : "n.a.";
    if (c.type === "date" || c.type === "month") return new Date(v);
    return v;
  }));
  if (rows.length) s.getRange(`A6:${end}${last}`).values = mapped;
  columns.forEach((c, i) => {
    const col = column(i), used = s.getRange(`${col}5:${col}${Math.max(last, 6)}`);
    used.format.columnWidth = c.width;
    if (c.type === "money") used.setNumberFormat(money);
    if (c.type === "percent") used.setNumberFormat(pct);
    if (c.type === "integer") used.setNumberFormat("0");
    if (c.type === "quantity") used.setNumberFormat("#,##0.########");
    if (c.type === "date") used.setNumberFormat("yyyy-mm-dd hh:mm");
    if (c.type === "month") used.setNumberFormat("yyyy-mm");
    if (["percent", "money", "integer", "quantity"].includes(c.type)) used.format.horizontalAlignment = "right";
    if (["date", "month"].includes(c.type) || ["year", "symbol", "period"].includes(c.key)) used.format.horizontalAlignment = "center";
    if (["held", "initial_names", "holdings", "value", "source", "status"].includes(c.key) && rows.length) {
      s.getRange(`${col}6:${col}${last}`).format.wrapText = true;
    }
    if (["return", "total_return", "pnl", "mdd"].includes(c.key) && rows.length) {
      s.getRange(`${col}6:${col}${last}`).conditionalFormats.add("cellIs", {
        operator: "lessThan", formula: 0, format: {font: {color: color.loss}}
      });
    }
  });
  if (rows.length) {
    const t = s.tables.add(`A5:${end}${last}`, true, `Table${sheets.length + 1}`);
    t.showFilterButton = true;
    t.style = "TableStyleMedium15";
    s.getRange(`A6:${end}${last}`).format.borders = {insideVertical: {style:"thin", color:"#E2E8F0"}};
    const addresses = Object.fromEntries(columns.map((c, i) => [c.key, column(i)]));
    for (const [key, fn] of Object.entries(formulas)) {
      const col = addresses[key];
      const cells = rows.map((r, i) => [r[key] == null ? '= "n.a."' : fn(i + 6, addresses)]);
      s.getRange(`${col}6:${col}${last}`).formulas = cells;
      formulaChecks.push({sheet: s, col, expected: rows.map(r => r[key]), key});
    }
    rows.forEach((r, i) => {
      const long = columns.filter(c => ["held", "initial_names", "holdings", "value", "source", "status"].includes(c.key));
      const lines = Math.max(1, ...long.map(c => Math.ceil(String(r[c.key] ?? "").length / (c.width * .68))));
      if (lines > 1) s.getRange(`A${i+6}:${end}${i+6}`).format.rowHeight = Math.max(28, 16 * lines + 8);
    });
  }
  s.getRange(`A5:${end}5`).format = {fill: color.head, font: {name: "Arial", size: 10, bold: true, color: "#FFFFFF"},
    rowHeight: 30, horizontalAlignment: "center", verticalAlignment: "center",
    borders: {insideVertical: {style: "thin", color: "#FFFFFF"}}};
  if (rows.length > 24) { s.freezePanes.freezeRows(5); s.freezePanes.freezeColumns(2); }
  sheets.push({sheet: s, name, last, end, rows: rows.length});
  return s;
}

const groupFirst = (a,b) => a.group.localeCompare(b.group) || a.strategy.localeCompare(b.strategy) || a.funding.localeCompare(b.funding) || a.slippage-b.slippage;
const overview = data.summary.map(r => ({...r, period: r.group.startsWith("76") ? "2020-03—2026-06" : "2020-04—2026-06"}));
tab("策略总览", "Top10 研究结果", "USDT；全部为历史研究", [
  C("strategy","策略", "text",26), C("funding","资金费处理","text",24), C("slippage","单边滑点","percent",12),
  C("total_return","累计收益","percent",16), C("cagr","年化收益","percent",15), C("mdd","最大回撤","percent",15),
  C("final","期末权益 USDT","money",23), C("period","测试月份","text",24), C("initial","初始权益 USDT","money",21),
  C("price_pnl","价格损益 USDT","money",23), C("funding_pnl","资金损益 USDT","money",23),
  C("fees","手续费 USDT","money",20), C("slip_cost","滑点成本 USDT","money",20), C("status","状态","text",58)
], overview, {total_return:(r,c)=>`=IF(ISNUMBER(${c.final}${r}),${c.final}${r}/${c.initial}${r}-1,"n.a.")`});

tab("年度汇总", "逐年收益与盈亏", "USDT；年收益正确复利", [
  C("year","年份","integer",14), C("strategy","策略","text",26), C("funding","资金费处理","text",24),
  C("slippage","单边滑点","percent",12), C("return","年度收益","percent",17), C("pnl","年度盈亏 USDT","money",24),
  C("months","覆盖月数","integer",12), C("start_equity","年初权益 USDT","money",24), C("end_equity","年末权益 USDT","money",24),
  C("price_pnl","价格损益 USDT","money",23), C("funding_pnl","资金损益 USDT","money",23),
  C("fees","手续费 USDT","money",20), C("slip_cost","滑点成本 USDT","money",20), C("group","比较区间","text",23)
], data.yearly.sort((a,b)=>a.year-b.year || groupFirst(a,b)), {
  return:(r,c)=>`=${c.end_equity}${r}/${c.start_equity}${r}-1`, pnl:(r,c)=>`=${c.end_equity}${r}-${c.start_equity}${r}`
});

const monthlySheet = tab("每月持仓盈亏", "每月持仓与盈亏", "币种与损益可筛选核查", [
  C("month","月份","month",15), C("strategy","策略","text",26), C("funding","资金费处理","text",24),
  C("slippage","单边滑点","percent",12), C("return","本月收益","percent",15), C("pnl","本月盈亏 USDT","money",23),
  C("held","本月实际持过的币","text",80), C("exits","提前退出个数","integer",16),
  C("start_equity","期初权益 USDT","money",23), C("end_equity","期末权益 USDT","money",23),
  C("price_pnl","价格损益 USDT","money",23), C("funding_pnl","资金损益 USDT","money",23),
  C("fees","手续费 USDT","money",20), C("slip_cost","滑点成本 USDT","money",20),
  C("initial_names","月初实际持仓","text",80), C("start","估值开始 UTC","date",24), C("end","估值结束 UTC","date",24),
  C("time_rule","月份计算方式","text",48), C("group","比较区间","text",23)
], data.monthly.sort((a,b)=>a.month.localeCompare(b.month) || groupFirst(a,b)), {
  return:(r,c)=>`=${c.end_equity}${r}/${c.start_equity}${r}-1`, pnl:(r,c)=>`=${c.end_equity}${r}-${c.start_equity}${r}`
});

tab("逐币进出", "逐币持仓明细", "整段持仓损益，非月归属", [
  C("month","入场月份","month",15), C("strategy","策略","text",26), C("funding","资金费处理","text",24), C("slippage","单边滑点","percent",12),
  C("symbol","币种","text",17), C("entry","入场 UTC","date",24), C("exit","实际退出 UTC","date",24),
  C("price_pnl","价格盈亏 USDT","money",23), C("funding_pnl","资金盈亏 USDT","money",23),
  C("quantity","实际模型数量","quantity",25), C("entry_price","入场参考价","quantity",22), C("exit_price","退出参考价","quantity",22),
  C("exit_kind","退出类型","text",25), C("exit_fee","提前/终止退出费","money",23), C("exit_slip","提前退出滑点","money",23)
], data.legs.sort((a,b)=>a.month.localeCompare(b.month) || groupFirst(a,b) || a.symbol.localeCompare(b.symbol)));

tab("频率换仓明细", "逐次换仓与收益", "周频仅计划，无完整收益", [
  C("strategy","策略","text",26), C("slippage","单边滑点","percent",12), C("entry","本次换仓 UTC","date",24), C("exit","下次换仓 UTC","date",24),
  C("return","周期收益","percent",16), C("pnl","周期盈亏 USDT","money",23), C("holdings","本期十币","text",85),
  C("start_equity","期初权益 USDT","money",23), C("end_equity","期末权益 USDT","money",23), C("funding","资金费处理","text",24),
  C("status","回放结果 / 仅选币计划","text",62)
], data.periods.sort((a,b)=>a.entry.localeCompare(b.entry) || groupFirst(a,b)), {
  return:(r,c)=>`=${c.end_equity}${r}/${c.start_equity}${r}-1`, pnl:(r,c)=>`=${c.end_equity}${r}-${c.start_equity}${r}`
});

const dd = data.drawdown.map(r=>({...r, window: r.window === "maximum_drawdown" ? "最大回撤" : r.window,
  account: `${r.account.includes("single_exit") ? "S1 逐币退出" : "B0 原月度"} · ${r.account.startsWith("price_only") ? "价格对照" : "资金费估算"} · 0.04%`,
  funding_pnl: r.account.startsWith("price_only") ? null : r.funding_pnl,
  btc: r.market_references.btc_return, eth: r.market_references.eth_return,
  refstart: r.market_references.reference_start_utc, refend: r.market_references.reference_end_utc,
  total_cost: r.fees + r.slippage}));
tab("回撤来源", "回撤来源拆解", "统计相关不等于因果", [
  C("window","区间","text",18), C("account","账户","text",42), C("start_ts","开始 UTC","date",24), C("end_ts","结束 UTC","date",24),
  C("return","账户收益","percent",17), C("equity_change","权益变化 USDT","money",23), C("price_pnl","价格损益 USDT","money",23),
  C("funding_pnl","观察资金现金 USDT","money",23), C("total_cost","手续费及滑点 USDT","money",23),
  C("market_related_price_pnl","模型市场相关损益","money",25), C("modeled_residual_price_pnl","模型剩余价格损益","money",25),
  C("complete_day_beta_unavailable_price_pnl","过去样本不足损益","money",25), C("boundary_or_unavailable_day_price_pnl","边界等未分解损益","money",25),
  C("btc","同期BTC","percent",16), C("eth","同期ETH","percent",16), C("refstart","市场参考开始 UTC","date",24), C("refend","市场参考结束 UTC","date",24)
], dd);

const notes = [
  ["这轮结论", "先退出弱的一半，比首次转弱就全部清仓更能留住领涨币后续利润；但最大回撤仍超过87%，不能实盘。"],
  ["价格对照", "扣手续费和滑点，故意不计算资金费；不是永续合约完整净收益。资金现金显示n.a.，不能理解为历史实际没有资金费。"],
  ["资金费估算", "原760腿观察到的97,421个事件，原生mark优先，其余仍有价差代理；完整资金日历和精确标记价未认证。"],
  ["资金计价依据", "Binance历史接口分别提供fundingRate、fundingTime和对应费用的markPrice，不可仅拿费率或普通成交价当精确资金现金。"],
  ["固定成本", "每边手续费0.10%；基准滑点0.04%，压力滑点0.08%。BNX/VIDT旧终止估价沿用0.10%结算费、零市场滑点。"],
  ["初始资金", "每条账户独立100,000 USDT；每次换仓按成本后权益各10%建十币，数量在期内固定，同名交易净额计费。"],
  ["资产范围", "Binance USDT永续资产池，只做多，包括币安原生TradFi合约；不额外加入外部现货美股。分类与历史身份仍非全池PIT认证。"],
  ["76个月退出比较", "2020-03-01 00:15至2026-07-01 00:15 UTC；B0原月度、S1逐币退出、X5首次退出最弱5币、X10首次退出全部。"],
  ["75个月频率比较", "2020-04-01 00:15至2026-07-01 00:15 UTC；3月初严格31日资格只有9币。四方案从同一时点、同一本金重新回放。"],
  ["M28与W28", "同看过去28个闭合日收益Top10；前者每月换，后者每周一换。W7改看过去7日，同时改变排名长度。"],
  ["BZRX缺价", "2021-12-19 02:00 UTC期货自动结算下架已获官方公告证实，但实际结算价格未有证据。W7不得跳过该持仓、映射OOKI或猜价后报告完整收益。"],
  ["BZRX官方公告", "https://www.binance.com/en/support/announcement/detail/dff27dc6bcbb432c902bcbea5e24ddfa"],
  ["KEEP缺价", "2022-02-15 02:00 UTC期货自动结算下架，发生在W28预定2月21日换仓之前。旧材料没有实际结算价，周频全期收益不能计算；不能直接改持T代币。"],
  ["KEEP官方公告", "https://www.binance.com/en/support/announcement/detail/96698a6a80f64cb1ae27f813032bfaa9"],
  ["月表两个时点规则", "76月方案沿用换仓后至下月换仓后，含下一边界交易成本；75月频率方案按自然月00:00估值，首尾实际00:15。不要跨组把一月当成完全同段。"],
  ["年度差异", "本表年度从每月权益/收益正确复利；76月组年界00:15，前轮旧报告年界00:00，少量年度差异不是策略或全期收益改变。2020和2026是不完整年份。"],
  ["月初币种", "周频月初指自然月00:00真实还在持有的上一篮子；本月实际持过的币可能多于10个。跨月持仓按市值计算月盈亏，不只统计平仓交易。"],
  ["未完成周频计划", "频率换仓明细保留W28/W7各327次事前已锁选币计划，非完整实际交易；周期收益/盈亏及权益全部n.a.，不加入月账/年账。每计划只列一次，不按两档滑点重复。"],
  ["逐币损益", "列实际数量对应整段持仓的价格/资金现金和提前退出费，不虚构每腿完整净利润。周频跨月腿不能按入场月份相加当自然月盈亏；月盈亏看每月总账。净额换仓费用以每月总账为准，包括下一月新增币的边界交易费。"],
  ["X5", "每月第一次S1信号时，卖原触发币与当时7日收益最弱5币的并集；之后其余币仍按原S1判断，当月不补位。不是参数最优值。"],
  ["S1并非只卖1币", "每币独立按20/7/2退出，76月共314次；70月有退出，其中65月退出多个币，最高一个月8币。"],
  ["回撤模型", "仅对完整恒定数量持仓日，用此前60自然日且至少45对有效收益估计对BTC/ETH等权因子的敏感度。边界和样本不足分开，不是可交易对冲回测。"],
  ["广谱市场参照", "事前合格币池存在缺价日，整日设不可用；不去掉事后缺价币，不跳日拼全期指数，因此不显示伪完整累计回报。"],
  ["历史与实盘", "全部历史已揭示，不是盲测；历史身份/全池PIT、实际成交容量、保证金/强平/ADL及未来观察均未通过。没有启动生产、下单或新增交易授权。"],
  ["记录数量", JSON.stringify(data.counts)],
  ["研究合同SHA256", data.contract_sha256],
  ["数据与报告位置", path.dirname(path.dirname(input))],
  ["官方资金字段", "https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data#get-funding-rate-history"]
].map(([item,value])=>({item,value,source:"本轮固定合同、逐笔账户及独立复核"}));
notes.push(...data.sources.map(s=>({item:"结果来源",value:s.file,source:s.sha256})));
tab("说明与来源", "说明与来源", "缺失不填零；单位USDT", [C("item","事项","text",27),C("value","解释 / 路径","text",110),C("source","来源 / SHA256","text",90)], notes);

// All output return/cash formulas must reproduce the independently checked inputs.
wb.recalculate();
let maxFormulaError = 0;
for (const check of formulaChecks) {
  const actual = check.sheet.getRange(`${check.col}6:${check.col}${check.expected.length + 5}`).values;
  for (let i=0; i<actual.length; i++) {
    if (check.expected[i] == null) { if (actual[i][0] !== "n.a.") throw new Error("Missing result became a number"); continue; }
    const error = Math.abs(actual[i][0] - check.expected[i]);
    maxFormulaError = Math.max(maxFormulaError, error);
    if (!Number.isFinite(error) || error > 1e-4) throw new Error(`Formula mismatch ${check.key} row ${i+6}`);
  }
}
// Reversible one-cell sensitivity check; restore historical values before export.
const originalEnd = monthlySheet.getRange("J6").values[0][0];
const originalPnl = monthlySheet.getRange("F6").values[0][0];
monthlySheet.getRange("J6").values = [[originalEnd + 1]];
if (Math.abs(monthlySheet.getRange("F6").values[0][0] - originalPnl - 1) > 1e-6) throw new Error("P&L formula did not respond");
monthlySheet.getRange("J6").values = [[originalEnd]];
wb.recalculate();
await fs.mkdir(outdir, {recursive: true});
const previews = path.join(outdir, "previews");
await fs.mkdir(previews, {recursive: true});
const inspections = [];
for (const item of sheets) {
  const inspect = await wb.inspect({kind: "table", sheetId: item.name, range: `A5:${item.end}${Math.min(item.last, 9)}`, include: "values,formulas", maxChars: 1800});
  inspections.push({sheet: item.name, rows: item.rows, inspect});
  const errors = await wb.inspect({kind: "match", sheetId: item.name, searchTerm: "#REF!|#DIV/0!|#VALUE!|#N/A|#NAME\\?|#NUM!", options: {useRegex:true, maxResults:30}, range: `A1:${item.end}${Math.max(item.last, 6)}`, maxChars: 2000});
  inspections.push({sheet: item.name, formulaErrorScan: errors});
  const lastColumn = item.name === "说明与来源" ? "C" : item.name === "每月持仓盈亏" ? "H" : column(Math.min(7, item.end.charCodeAt(0)-65));
  const preview = await wb.render({sheetName:item.name, range:`A1:${lastColumn}${Math.min(item.last, 14)}`, scale:1.4, format:"png"});
  await fs.writeFile(path.join(previews, `${item.name}.png`), new Uint8Array(await preview.arrayBuffer()));
}
const xlsx = path.join(outdir, "Top10_月度持仓盈亏与年度比较_20260911.xlsx");
const exported = await SpreadsheetFile.exportXlsx(wb);
await exported.save(xlsx);
await fs.writeFile(path.join(outdir, "workbook-qa.json"), JSON.stringify({counts:data.counts, maxFormulaError,
  sensitivityCheckRestored:true, recalculated:true, renderedEverySheet:true, inspections}, null, 2));
console.log(JSON.stringify({xlsx, counts:data.counts, maxFormulaError, previews}));
