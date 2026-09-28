import fs from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { Workbook, SpreadsheetFile } from '@oai/artifact-tool';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = '/Users/ZK/OpenCode/quant-strategy-lab';
const family = path.join(root, 'research/asset-portfolios/1d-monthly-cs-momentum-long10');
const source = path.join(family, 'artifacts/recent36-monthly-holdings-20260924/report-data.json');
const data = JSON.parse(await fs.readFile(source, 'utf8'));
const dest = path.join(here, '..', '月频Top10_最近36个月持仓与换仓.xlsx');
const wb = Workbook.create();
const main = wb.worksheets.add('月度换仓');
const detail = wb.worksheets.add('单币持仓');
const ink = '#243449', navy = '#213B5B', muted = '#64748B';
const pct = '0.00%;[Red](0.00%);"–"';
const num = '#,##0.00;[Red](#,##0.00);"–"';
const names = (list,limit=28,maxCount=3) => {
  if(!list.length) return '无';
  const lines=[]; let current=[],size=0;
  for(const name of list) {
    const width=[...name].reduce((n,c)=>n+(c.charCodeAt(0)>255?2:1),0);
    if(current.length && (size+width+2>limit || current.length===maxCount)) {lines.push(current.join('、'));current=[];size=0;}
    current.push(name);size+=width+2;
  }
  if(current.length) lines.push(current.join('、'));
  return lines.join('\n');
};
const term = list => list.map(e => `${e.symbol} ${e.date.slice(5,10)} ${e.date.slice(11,16)} UTC`).join('\n') || '无';
const near = (a,b,label) => { if (!Number.isFinite(a) || Math.abs(a-b) > Math.max(1e-8,Math.abs(b)*1e-10)) throw Error(`${label}: ${a} != ${b}`); };

for (const sheet of [main,detail]) {
  sheet.showGridLines = false;
  sheet.getRange(sheet === main ? 'A1:I57' : 'A1:K369').format.font = { name:'Arial', size:10, color:ink };
  sheet.getRange(sheet === main ? 'A1:I57' : 'A1:K369').format.verticalAlignment = 'center';
}
main.tabColor = navy;
detail.tabColor = '#DACCB7';
const widths = {A:91,B:106,C:280,D:245,E:245,F:124,G:169,H:112,I:87};
for (const [col,width] of Object.entries(widths)) main.getRange(`${col}1:${col}57`).format.columnWidthPx = width;
main.getRange('A2').values = [['月频Top10：最近36个月买入与换出']];
main.getRange('A2:I2').format.font = {name:'Arial',size:16,bold:true,color:navy};
main.getRange('A2:I2').format.rowHeightPx = 29;
main.getRange('A3').values = [['2023年7月—2026年6月。原始月频Top10，不加MA120。每边手续费0.10% + 滑点0.04%，不含资金费。']];
main.getRange('A4').values = [['收益沿用自然月口径；名单是月初00:15 UTC换仓后的十币。续持也会加减仓。下架结算为条件指数估算。']];
main.getRange('A3:I4').format.font = {name:'Arial',size:10,color:muted};
main.getRange('A3:I4').format.rowHeightPx = 22;
main.getRange('A5:B6').values = [['36个月收益',null],['最大回撤',data.stats.max_drawdown]];
main.getRange('C5:D6').values = [['年化收益',null],['盈利月份 / 36',null]];
main.getRange('E5:F6').values = [['平均每月续持币数',null],['三年涉及标的数',data.stats.distinct_symbols]];
main.getRange('B5').formulas = [['=H45-1']];
main.getRange('D5').formulas = [['=H45^(365.25/1096.0104166666667)-1']];
main.getRange('D6').formulas = [['=COUNTIFS(B10:B45,">0")']];
main.getRange('F5').formulas = [['=AVERAGE(I10:I45)']];
main.getRange('B5:B6').setNumberFormat(pct);
main.getRange('D5').setNumberFormat(pct);
main.getRange('F5').setNumberFormat('0.00');
main.getRange('A5:I6').format.rowHeightPx = 25;
main.getRange('B5:B6').format.font = {name:'Arial',size:12,bold:true,color:navy};
main.getRange('A8').values = [['“新买入”不包括续持调仓；“月初换出”不重复计算上月已经下架的币。月末净值以2023年7月初为1。']];
main.getRange('A8:I8').format.font = {name:'Arial',size:10,color:muted};
main.getRange('A9:I9').values = [['月份','自然月收益','月初持有的十币','本月新买入','月初换出','续持','月中提前结算','月末净值','续持数量']];
const monthlyRows = data.months.map(r => [new Date(r.date),r.return,names(r.selected),names(r.new),names(r.exited),names(r.retained,14,2),term(r.early_exits),null,null]);
main.getRange('A10:I45').values = monthlyRows;
main.getRange('A10:A45').setNumberFormat('yyyy-mm');
main.getRange('B10:B45').setNumberFormat(pct);
main.getRange('H10:H45').setNumberFormat('0.0000');
main.getRange('I10:I45').setNumberFormat('0');
main.getRange('H10:H45').formulas = data.months.map((_,i)=>[i ? `=H${9+i}*(1+B${10+i})` : '=1+B10']);
main.getRange('I10:I45').formulas = data.months.map((_,i)=>[`=COUNTIFS('单币持仓'!$A$8:$A$367,A${10+i},'单币持仓'!$C$8:$C$367,"续持调仓")`]);
main.getRange('C10:G45').format.wrapText = true;
main.getRange('A10:I45').format.rowHeightPx = 86;
main.getRange('C10:G45').format.verticalAlignment = 'center';
main.getRange('B10:B45').format.horizontalAlignment = 'right';
main.getRange('H10:I45').format.horizontalAlignment = 'right';
const table = main.tables.add('A9:I45',true,'MonthlyRotation36');
table.showFilterButton = true;
main.getRange('A9:I9').format = {fill:navy,font:{name:'Arial',size:10,color:'#FFFFFF',bold:true},horizontalAlignment:'center',verticalAlignment:'center',rowHeightPx:32};
for(let i=10;i<=45;i++) {
  main.getRange(`A${i}:I${i}`).format.fill = i%2===0?'#F2F5F9':'#FFFFFF';
  if(data.months[i-10].early_exits.length) main.getRange(`G${i}`).format.fill = '#FFF1CC';
}
main.getRange('B10:B45').conditionalFormats.add('cellIs',{operator:'lessThan',formula:0,format:{fill:'#FCE8E6',font:{color:'#9C2B28'}}});
main.getRange('B10:B45').conditionalFormats.add('cellIs',{operator:'greaterThan',formula:0,format:{fill:'#E8F3ED',font:{color:'#235C43'}}});
main.freezePanes.freezeRows(9);
main.freezePanes.freezeColumns(1);
main.getRange('A47').values = [['年度分段']];
main.getRange('A47:I47').format.font = {name:'Arial',size:12,bold:true,color:navy};
main.getRange('A48:D48').values = [['区间','月份数','复合收益','盈利月份']];
main.getRange('A48:D48').format = {fill:navy,font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},horizontalAlignment:'center'};
let startRow=10;
for(let i=0;i<data.years.length;i++) {
  const y=data.years[i], row=49+i, endRow=startRow+y.months-1;
  main.getRange(`A${row}:D${row}`).values = [[`${y.year}${y.year===2023?'H2':y.year===2026?'H1':''}`,y.months,null,null]];
  main.getRange(`C${row}`).formulas = [[startRow===10?`=H${endRow}-1`:`=H${endRow}/H${startRow-1}-1`]];
  main.getRange(`D${row}`).formulas = [[`=COUNTIFS(B${startRow}:B${endRow},">0")`]];
  startRow=endRow+1;
}
main.getRange('C49:C52').setNumberFormat(pct);
main.getRange('A48:D52').format.rowHeightPx=25;
main.getRange('A54').values=[['H2为下半年，H1为上半年。2026-07-01为样本结束清仓，不代表7月选币。收益不含完整资金费或日内强平模拟。']];
main.getRange('A55').values=[['最大回撤区间：2024-04-01至2025-08-03。仅列本36个月内的日末与换仓边界采样。']];
main.getRange('A54:I55').format.font={name:'Arial',size:10,color:muted};

const dw={A:91,B:133,C:104,D:125,E:125,F:106,G:162,H:238,I:82,J:143,K:155};
for(const [col,width] of Object.entries(dw)) detail.getRange(`${col}1:${col}369`).format.columnWidthPx=width;
detail.getRange('A2').values=[['360笔月持仓：参考价格、续持与退出']];
detail.getRange('A2:K2').format.font={name:'Arial',size:16,bold:true,color:navy};
detail.getRange('A2:K2').format.rowHeightPx=29;
detail.getRange('A3').values=[['单币区间为当月00:15换仓至下次换仓或下架结算。边界价不表示全部卖出。以下价格盈亏未分摊费用、不含资金费。']];
detail.getRange('A4').values=[['来源：2026-09-24已独立核对的Top10月频B0中心价格账户。360笔原始价格/数量逐行保留。']];
detail.getRange('A5').values=[['金额为原连续账户的实际USDT规模，不是三年前重新投入10万。月表为自然月收益，二者前后相差月初15分钟。']];
detail.getRange('A3:K5').format.font={name:'Arial',size:10,color:muted};
detail.getRange('A3:K5').format.rowHeightPx=22;
detail.getRange('A7:K7').values=[['月份','标的','入选方式','买入参考价','退出/边界参考价','单币价格涨跌','退出/边界时刻 UTC','退出说明','初始权重','持币数量','价格盈亏 USDT']];
detail.getRange('A8:K367').values=data.legs.map(r=>[new Date(r.date),r.symbol,r.action,r.entry_price,r.exit_price,null,new Date(r.exit_date),r.exit_reason,r.weight,r.quantity,null]);
detail.getRange('F8:F367').formulas=data.legs.map((_,i)=>[`=E${8+i}/D${8+i}-1`]);
detail.getRange('K8:K367').formulas=data.legs.map((_,i)=>[`=J${8+i}*(E${8+i}-D${8+i})`]);
detail.getRange('A8:A367').setNumberFormat('yyyy-mm');
detail.getRange('D8:E367').setNumberFormat('0.########');
detail.getRange('F8:F367').setNumberFormat(pct);
detail.getRange('G8:G367').setNumberFormat('yyyy-mm-dd hh:mm');
detail.getRange('I8:I367').setNumberFormat('0%');
detail.getRange('J8:J367').setNumberFormat('#,##0.0000');
detail.getRange('K8:K367').setNumberFormat(num);
const dt=detail.tables.add('A7:K367',true,'MonthlyPosition360');
dt.showFilterButton=true;
detail.getRange('A7:K7').format={fill:navy,font:{name:'Arial',size:10,bold:true,color:'#FFFFFF'},horizontalAlignment:'center',rowHeightPx:33};
detail.getRange('A8:K367').format.rowHeightPx=26;
for(let i=8;i<=367;i++) detail.getRange(`A${i}:K${i}`).format.fill=i%2===0?'#F2F5F9':'#FFFFFF';
detail.getRange('D8:G367').format.horizontalAlignment='right';
detail.getRange('I8:K367').format.horizontalAlignment='right';
detail.getRange('F8:F367').conditionalFormats.add('cellIs',{operator:'lessThan',formula:0,format:{font:{color:'#9C2B28'}}});
detail.freezePanes.freezeRows(7);
detail.freezePanes.freezeColumns(2);

// Check a real input change propagates, then restore it before the single final recalculation.
const old=data.months[0].return;
main.getRange('B10').values=[[old+0.01]];
near(main.getRange('H10').values[0][0],1+old+0.01,'changed first-month formula');
main.getRange('B10').values=[[old]];
wb.recalculate();
near(main.getRange('B5').values[0][0],data.stats.total_return,'total return');
near(main.getRange('D5').values[0][0],data.stats.annualized_365_25,'annualized');
near(main.getRange('D6').values[0][0],data.stats.positive_months,'positive months');
near(main.getRange('F5').values[0][0],data.stats.average_retained_names,'retained average');
const retain=main.getRange('I10:I45').values;
data.months.forEach((r,i)=>near(retain[i][0],r.retained.length,`retained ${r.month}`));
const growth=detail.getRange('F8:F367').values, cash=detail.getRange('K8:K367').values;
data.legs.forEach((r,i)=>{near(growth[i][0],r.gross_return,`leg return ${i}`);near(cash[i][0],r.price_pnl_usdt,`leg cash ${i}`);});
data.years.forEach((r,i)=>near(main.getRange(`C${49+i}`).values[0][0],r.return,`year ${r.year}`));
const inspection=await wb.inspect({kind:'table',range:'月度换仓!A5:F6',include:'values,formulas',tableMaxRows:3,tableMaxCols:6,maxChars:2000});
const errors=await wb.inspect({kind:'match',searchTerm:'#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A|#NUM!|#NULL!|#SPILL!|#CALC!',options:{useRegex:true,maxResults:30},maxChars:2000,summary:'final formula errors'});
await fs.writeFile(path.join(here,'inspection.json'),JSON.stringify({inspection:inspection.ndjson,errors:errors.ndjson,rows:36,legs:360,formulasChecked:true},null,2));
for(const [name,range,file] of [['月度换仓','A1:I13','monthly-top.png'],['月度换仓','A38:I45','monthly-bottom.png'],['单币持仓','A1:K13','coin-detail.png']]) {
  const preview=await wb.render({sheetName:name,range,scale:1.4,format:'png'});
  await fs.writeFile(path.join(here,file),new Uint8Array(await preview.arrayBuffer()));
}
const output=await SpreadsheetFile.exportXlsx(wb);
await output.save(dest);
console.log(JSON.stringify({workbook:dest,rows:36,legs:360,checks:'source values and recalculated formulas match',errors:errors.ndjson}));
