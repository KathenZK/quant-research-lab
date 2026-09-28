import os
"""ReportLab standalone SVG charts, using saved CSV only."""
import csv,datetime
from pathlib import Path
from reportlab.graphics.shapes import Drawing,String,Line
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics import renderSVG
from reportlab.lib.colors import HexColor
F=Path(__file__).resolve().parents[1];A=Path(os.environ.get('TPSA_R0_OUTPUT',str(F/'artifacts')))
D=Drawing(1000,670);D.add(String(55,638,'TPSA-LA R0: conditional price/fee account, actual funding excluded',fontName='Helvetica-Bold',fontSize=16));D.add(String(55,616,'USD 10,000 each; reused history; daily open execution proxy; partial runs stop at failure',fontSize=11))
colors=['#185B9D','#BB6D18','#69756A'];names=['ML_p040','ALL_EVENTS','HASH20_EVENTS'];data=[];draw=[]
start=datetime.datetime(2025,1,1,tzinfo=datetime.timezone.utc)
for name in names:
    rows=list(csv.DictReader((A/name/'account_equity.csv').open()));points=[(0,10000.)];dds=[(0,0.)];peak=10000.
    for r in rows:
        day=(datetime.datetime.fromisoformat(r['time'])-start).total_seconds()/86400.;y=float(r['equity_ex_actual_funding']);peak=max(peak,y);points.append((day,y));dds.append((day,100*(y/peak-1)))
    data.append(points);draw.append(dds)
for i,(values,ypos,height,ymin,ymax,step,title) in enumerate([(data,335,240,0,12000,2000,'Account equity / USD'),(draw,70,195,-100,0,20,'Drawdown / %')]):
    lp=LinePlot();lp.x=70;lp.y=ypos;lp.width=870;lp.height=height;lp.data=values;lp.joinedLines=1;lp.xValueAxis.valueMin=0;lp.xValueAxis.valueMax=546;lp.xValueAxis.valueSteps=[0,181,365,546];lp.xValueAxis.labelTextFormat=lambda x:{0:'2025-01',181:'2025-07',365:'2026-01',546:'2026-07'}.get(int(x),'');lp.yValueAxis.valueMin=ymin;lp.yValueAxis.valueMax=ymax;lp.yValueAxis.valueStep=step
    for j,col in enumerate(colors):lp.lines[j].strokeColor=HexColor(col);lp.lines[j].strokeWidth=1.5
    D.add(lp);D.add(String(70,ypos+height+15,title,fontName='Helvetica-Bold',fontSize=12))
for i,(name,col) in enumerate(zip(names,colors)):
    x=80+i*275;D.add(Line(x,27,x+30,27,strokeColor=HexColor(col),strokeWidth=2));D.add(String(x+39,23,name,fontSize=12))
renderSVG.drawToFile(D,str(A/'equity_drawdown.svg'))
print(A/'equity_drawdown.svg')
