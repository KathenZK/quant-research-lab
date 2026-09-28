#!/usr/bin/env python3
"""Offline deterministic carry feasibility accounting. Standard library only."""
from pathlib import Path
import argparse, csv, datetime as dt, hashlib, json, math, platform, sys
ROOT=Path(__file__).resolve().parents[1]
DAY=86400000; HOUR=3600000

def read(p):return json.loads(Path(p).read_text())
def iso(ms):return dt.datetime.fromtimestamp(ms/1000,dt.timezone.utc).isoformat()
def dump(p,x):Path(p).write_text(json.dumps(x,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def csvout(p,rows):
    if not rows:return
    keys=list(dict.fromkeys(k for r in rows for k in r));
    with Path(p).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=keys);w.writeheader();w.writerows(rows)
def floorlot(x,lot):return math.floor((x+1e-12)/lot)*lot
def ceillot(x,lot):return math.ceil((x-1e-12)/lot)*lot
def series(raw,prefix,kind):
    files=sorted(raw.glob(prefix+'_[0-9][0-9].json'));by={};duplicates=0
    for f in files:
        for r in read(f)['data']:
            ts=int(r['fundingTime'] if kind=='funding' else r[0])
            if ts in by:
                assert by[ts]==r,('conflicting duplicate',prefix,ts)
                duplicates+=1
            by[ts]=r
    if kind=='funding':
        return {t:float(r['realizedRate']) for t,r in sorted(by.items())}, {'files':len(files),'rows':len(by),'duplicates_equal':duplicates}
    out={}
    for t,r in sorted(by.items()):
        if r[-1]!='1':continue
        o,h,l,c=map(float,r[1:5]);assert 0<l<=min(o,c)<=max(o,c)<=h,(prefix,t,r)
        out[t]={'open':o,'high':h,'low':l,'close':c}
    return out,{'files':len(files),'rows':len(out),'duplicates_equal':duplicates}
def book_vwap(levels,qty,inverse=False):
    left=qty;total=0.
    for p,q,*_ in levels:
        take=min(left,float(q));price=float(p);total+=take/price if inverse else take*price;left-=take
        if left<=1e-10:return qty/total if inverse else total/qty
    raise ValueError(f'insufficient captured depth: requested {qty}, unfilled {left}')
def draw_svg(p,rows,title):
    vals=[r['equity_usd'] for r in rows]; ts=[r['ts'] for r in rows]; W=960;H=420;lo=min(vals+[10000]);hi=max(vals+[10000]);span=max(hi-lo,1);x=lambda t:60+(t-ts[0])/(ts[-1]-ts[0])*860;y=lambda v:340-(v-lo)/span*270
    pts=' '.join(f'{x(t):.2f},{y(v):.2f}' for t,v in zip(ts,vals));d=[];peak=10000
    for v in vals:peak=max(v,peak);d.append(v/peak-1)
    text=f'<svg xmlns="http://www.w3.org/2000/svg" width="960" height="420" viewBox="0 0 960 420"><rect width="960" height="420" fill="#fcfaf7"/><text x="60" y="34" font-family="sans-serif" font-size="22">{title}</text><text x="60" y="58" font-family="sans-serif" font-size="13">Historical diagnostic: OHLC fills, mark-at-funding proxy, 10000 USD capital</text><polyline points="{pts}" fill="none" stroke="#256d85" stroke-width="2"/><line x1="60" x2="920" y1="{y(10000):.2f}" y2="{y(10000):.2f}" stroke="#aaa" stroke-dasharray="5 4"/><text x="60" y="380" font-family="sans-serif">{iso(ts[0])[:10]} to {iso(ts[-1])[:10]} | Equity {vals[-1]:.2f} | Hourly MDD {min(d)*100:.3f}%</text></svg>'
    Path(p).write_text(text)

def tests():
    # Independent dollar examples; short linear is arithmetic difference, not reciprocal return.
    assert abs(2*(100-110)+2*(110-100))<1e-12
    assert abs(2*100*.001-.2)<1e-12
    assert abs(2*100*(-.001)+.2)<1e-12
    for terminal in [50,100,200]:
        N=1000;F=105;q=N/F
        assert abs((q+N*(1/terminal-1/F))*terminal-N)<1e-10
    assert abs(book_vwap([['100','1'],['200','1']],2,True)-400/3)<1e-10
    assert abs(floorlot(.12345,.0001)-.1234)<1e-10
    return {'independent_examples_passed':6,'linear_long_short_cancellation':True,'funding_signs':True,'inverse_terminal_invariance':True,'inverse_harmonic_vwap':True,'lot_rounding':True}

def analyze(raw,out):
    out.mkdir(parents=True,exist_ok=True);cfg=read(ROOT/'specs/contract.json');sel=read(raw/'selection.json');start,end=sel['history_start'],sel['history_end'];spotinst={x['instId']:x for x in read(ROOT/'artifacts/raw/spot_instruments.json')['data']};swapinst={x['instId']:x for x in read(ROOT/'artifacts/raw/swap_instruments.json')['data']};fundinst=sel['selected']
    clock=[]
    for f in sorted(raw.glob('*clock.json'))+[f for f in sorted(raw.glob('server_time_*.json')) if '.meta.' not in f.name]:
        m=read(f.with_name(f.stem+'.meta.json'));s=int(read(f)['data'][0]['ts']);a=dt.datetime.fromisoformat(m['local_start_utc']).timestamp()*1000;b=dt.datetime.fromisoformat(m['local_end_utc']).timestamp()*1000
        clock.append({'file':f.name,'server_utc':iso(s),'local_start_utc':m['local_start_utc'],'local_end_utc':m['local_end_utc'],'server_minus_local_midpoint_ms':s-(a+b)/2,'within_request_interval':a-1000<=s<=b+1000,'absolute_clock_valid':abs(s-(a+b)/2)<=60000})
    quotechecks=[];quotes=[];perps=[];expiryhist=[];stress=[];orders=[];hand=[];dq=[];basisrows=[];rollingrows=[];cashsens=[]
    for asset in ['BTC','ETH']:
        spinst=spotinst[asset+'-USDT'];swinst=swapinst[asset+'-USDT-SWAP'];exinst=fundinst[asset];sp_lot=float(spinst['lotSz']);sw_lot=float(swinst['lotSz'])*float(swinst['ctVal']);ex_lot=float(exinst['lotSz']);face=float(exinst['ctVal']);expid=exinst['instId'];expiry_mmr=max(.01,float(read(raw/('expiry_tiers_'+asset+'.json'))['data'][0]['mmr']))
        for roundno in range(3):
            clk=read(raw/f'book_r{roundno}_clock.json')['data'][0];ct=int(clk['ts']);sp=read(raw/f'book_r{roundno}_{asset}-USDT.json')['data'][0]
            for structure,instid in [('expiry',expid),('perpetual',asset+'-USDT-SWAP')]:
                de=read(raw/f'book_r{roundno}_{instid}.json')['data'][0];skew=abs(int(sp['ts'])-int(de['ts']));age=max(abs(ct-int(sp['ts'])),abs(ct-int(de['ts'])));cm=next(x for x in clock if x['file']==f'book_r{roundno}_clock.json');valid=skew<=2000 and age<=10000 and cm['absolute_clock_valid'];quotechecks.append({'asset':asset,'structure':structure,'round':roundno,'spot_utc':iso(int(sp['ts'])),'derivative_utc':iso(int(de['ts'])),'pair_skew_ms':skew,'absolute_age_vs_clock_ms':age,'valid':valid})
                for mult in [1,2]:
                    sf=cfg['spot_taker_fee']*mult;df=cfg['derivative_taker_fee']*mult;sl=cfg['extra_adverse_slippage_each_leg']*mult
                    if structure=='expiry':
                        # Contract count fixed by budget, then reduce until two-leg fill and fee-adjusted spot fit.
                        n=floorlot(5000*(1-sf)/(float(sp['asks'][0][0])*(1+sl))*(float(de['bids'][0][0])*(1-sl))/face,ex_lot)
                        while n>0:
                            F=book_vwap(de['bids'],n,True)*(1-sl);N=n*face;q=N/F;gross=ceillot(q/(1-sf),sp_lot);S=book_vwap(sp['asks'],gross)*(1+sl);spent=gross*S
                            if spent<=5000+1e-8:break
                            n=round(n-ex_lot,8)
                        netq=gross*(1-sf);ef=N/F*df;cash=10000-spent;days=(int(exinst['expTime'])-ct)/DAY
                        terminal_S=(float(sp['asks'][0][0])+float(sp['bids'][0][0]))/2
                        # Flat terminal price scenario; fee-coin residual is explicitly price sensitive.
                        terminal_coins=netq-ef+N*(1/terminal_S-1/F)-N/terminal_S*cfg['expiry_settlement_fee']*mult
                        terminal_equity=cash+terminal_coins*terminal_S*(1-sf)*(1-sl);pnl=terminal_equity-10000;opp=10000*.04*days/365
                        row={'asset':asset,'structure':'inverse_expiry','round':roundno,'cost_multiplier':mult,'quote_valid':valid,'instrument':instid,'days_to_expiry':days,'contracts':n,'face_notional_usd':N,'spot_gross_qty':gross,'spot_net_qty':netq,'spot_cost_usdt':spent,'spot_entry_vwap':S,'futures_entry_harmonic_vwap':F,'entry_fee_coin':ef,'other_cash_usdt':cash,'encumbered_spot_coin':.8*netq,'entry_basis_pct':(F/S-1)*100,'conditional_flat_terminal_net_usd':pnl,'conditional_full_account_return_pct':pnl/100,'simple_annualized_full_capital_pct':pnl/10000*365/days*100,'cash_4pct_opportunity_usd':opp,'surplus_over_cash_usd':pnl-opp,'terminal_spot_equals_index_assumed':True}
                        quotes.append(row)
                        if roundno==0 and mult==1:
                            hand.append({'case':asset+'_inverse_quote','N':N,'F':F,'q':q,'gross_spot':gross,'spot_cash_spent':spent,'entry_fee_coin':ef,'formula':'cash + (net_spot - entry_fee_coin + N*(1/settlement - 1/F) - N/settlement*settlement_fee) * terminal_spot_sale_price*(1-spot_sale_fee)','flat_terminal_equity':terminal_equity})
                            for ret in [-.5,0,.5,1.0,4.0]:
                                st=terminal_S*(1+ret)
                                for widen in [0,.02,.05]:
                                    ft=st*(1+widen);coinpnl=N*(1/ft-1/F);margin_coin=.8*netq-ef+coinpnl;mm_coin=N/ft*expiry_mmr;mark_equity=cash+(netq-ef+coinpnl)*st
                                    stress.append({'asset':asset,'structure':'inverse_expiry','spot_shock':ret,'basis_widening':widen,'account_equity_usd':mark_equity,'account_return_pct':(mark_equity/10000-1)*100,'isolated_margin_coin':margin_coin,'maintenance_proxy_coin':mm_coin,'maintenance_rate_used':expiry_mmr,'isolated_liquidation_proxy':margin_coin<=mm_coin,'coin_fee_residual_included':True})
                            for mismatch in [-.01,-.001,0,.001,.01]:
                                terminal=cash+terminal_coins*terminal_S*(1+mismatch)*(1-sf)*(1-sl)
                                stress.append({'asset':asset,'structure':'expiry_settlement_tracking','terminal_spot_vs_index':mismatch,'account_equity_usd':terminal,'account_return_pct':(terminal/10000-1)*100})
                    else:
                        q=floorlot(5000*(1-sf)/(float(sp['asks'][0][0])*(1+sl)),sw_lot)
                        while q>0:
                            gross=ceillot(q/(1-sf),sp_lot);S=book_vwap(sp['asks'],gross)*(1+sl);spent=gross*S
                            if spent<=5000+1e-8:break
                            q=round(q-sw_lot,10)
                        n=q/float(swinst['ctVal']);F=book_vwap(de['bids'],n)*(1-sl);Se=book_vwap(sp['bids'],q)*(1-sl);Fe=book_vwap(de['asks'],n)*(1+sl);netq=gross*(1-sf);residual=netq-q
                        immediate=q*Se*(1-sf)-spent+q*(F-Fe)-q*(F+Fe)*df+residual*Se
                        # Event rate threshold is a scenario at constant starting mark over 270 events.
                        quotes.append({'asset':asset,'structure':'linear_perpetual','round':roundno,'cost_multiplier':mult,'quote_valid':valid,'instrument':instid,'spot_net_hedged_qty':q,'spot_rounding_residual_qty':residual,'contracts':n,'spot_cost_usdt':spent,'spot_entry_vwap':S,'futures_entry_vwap':F,'immediate_roundtrip_net_usd':immediate,'funding_90d_break_even_each_8h':(-immediate+10000*.04*90/365)/(270*q*F),'funding_90d_break_even_each_8h_zero_cash':-immediate/(270*q*F),'funding_future_locked':False})
        spot,ds=series(raw,'spot_'+asset,'candle');swap,dw=series(raw,'swap_'+asset,'candle');mark,dm=series(raw,'mark_'+asset,'candle');fund,dfd=series(raw,'funding_'+asset,'funding');expiry,de=series(raw,'expiry_'+asset,'candle')
        entry=start+HOUR;needed=list(range(entry,end+1,HOUR));gaps={k:[iso(t) for t in needed if t not in d] for k,d in [('spot',spot),('swap',swap),('mark',mark)]}
        events={t:r for t,r in fund.items() if entry<t<=end};expected=set(range(start+8*HOUR,end+1,8*HOUR));missing_event=sorted(expected-set(events));extra_event=sorted(set(events)-expected)
        dq.append({'asset':asset,'start':iso(entry),'end':iso(end),'price_gaps':gaps,'actual_funding_events':len(events),'default8h_missing':list(map(iso,missing_event)),'default8h_extra':list(map(iso,extra_event)),'historical_frequency_independently_proven':False,'historical_funding_mark_exact':False,'candle_validation':'closed OHLC range positive; exact duplicate conflicts rejected; hourly grid exact','datasets':{'spot':ds,'swap':dw,'mark':dm,'funding':dfd,'expiry':de}})
        assert all(not v for v in gaps.values()),(asset,'price gap');assert not missing_event and not extra_event,(asset,'event calendar mismatch')
        for mult,delay in [(1,0),(2,0),(1,1)]:
            et=entry+delay*HOUR;sf=cfg['spot_taker_fee']*mult;tf=cfg['derivative_taker_fee']*mult;sl=cfg['extra_adverse_slippage_each_leg']*mult;S=spot[et]['open']*(1+sl);F=swap[et]['open']*(1-sl);q=floorlot(5000*(1-sf)/S,sw_lot);gross=ceillot(q/(1-sf),sp_lot);spent=gross*S
            if spent>5000:q=round(q-sw_lot,10);gross=ceillot(q/(1-sf),sp_lot);spent=gross*S
            netq=gross*(1-sf);margin=4000-q*F*tf;cash=10000-spent-4000;cum=0.;flow=[];equity=[];minmargin=4000;fundlo=0.;fundhi=0.;peak=10000;mdd=0.;liquidated=False
            for t in range(et,end+1,HOUR):
                r=events.get(t) if et<t else None
                if r is not None:
                    amt=q*mark[t]['open']*r;cum+=amt;low=q*min(mark[t]['low']*r,mark[t]['high']*r);high=q*max(mark[t]['low']*r,mark[t]['high']*r);fundlo+=low;fundhi+=high
                    flow.append({'ts':t,'utc':iso(t),'asset':asset,'quantity':q,'realized_rate':r,'funding_mark_open_proxy':mark[t]['open'],'mark_low':mark[t]['low'],'mark_high':mark[t]['high'],'funding_received_usdt':amt,'funding_lower_bound':low,'funding_upper_bound':high,'cumulative_funding':cum})
                sp=spot[t]['open'];mk=mark[t]['open'];deeq=margin+q*(F-mk)+cum;eq=cash+netq*sp+deeq;mm=q*mk*.01;peak=max(peak,eq);mdd=min(mdd,eq/peak-1);minmargin=min(minmargin,deeq)
                if deeq<=mm: raise ValueError(('HISTORICAL_MARGIN_BREACH_STOP_REPLAY', asset, iso(t), deeq, mm))
                equity.append({'ts':t,'utc':iso(t),'asset':asset,'spot_qty':netq,'short_qty':q,'cash_usdt':cash,'isolated_wallet_usdt':margin+cum,'derivative_unrealized_usdt':q*(F-mk),'isolated_equity_usdt':deeq,'spot_value_usdt':netq*sp,'funding_cumulative':cum,'maintenance_proxy_usdt':mm,'equity_usd':eq,'drawdown':eq/peak-1,'cash_benchmark_usd':10000*(1+.04*(t-et)/DAY/365)})
            So=spot[end]['open']*(1-sl);Fo=swap[end]['open']*(1+sl);final=cash+netq*So*(1-sf)+margin+q*(F-Fo)+cum-q*Fo*tf;peak=max(peak,final);mdd=min(mdd,final/peak-1);net=final-10000;days=(end-et)/DAY
            costs=(spent-netq*spot[et]['open'])+q*(swap[et]['open']-F)+q*F*tf+netq*(spot[end]['open']-So*(1-sf))+q*(Fo-swap[end]['open'])+q*Fo*tf
            result={'asset':asset,'structure':'linear_perpetual','variant':f'cost{mult}_delay{delay}h','initial_capital_usd':10000,'start_utc':iso(et),'end_utc':iso(end),'days':days,'quantity':q,'spot_gross_purchase_qty':gross,'spot_cost_usdt':spent,'other_cash_usdt':cash,'isolated_collateral_usdt':4000,'actual_events':len(flow),'funding_received_usdt_proxy':cum,'funding_lower_bound_usdt':fundlo,'funding_upper_bound_usdt':fundhi,'price_hedge_pnl_before_cost_usdt':net-cum+costs,'all_execution_cost_usdt':costs,'net_pnl_usd_proxy':net,'net_return_pct':net/100,'simple_annualized_return_pct':net/10000*365/days*100,'hourly_mdd_pct':mdd*100,'final_equity_usd':final,'min_isolated_margin_equity_usdt':minmargin,'liquidation_proxy_encountered':liquidated,'cash_4pct_pnl_usd':10000*.04*days/365,'surplus_over_cash_usd':net-10000*.04*days/365,'evidence_class':'REUSED_DIAGNOSTIC_OHLC_EXECUTION_AND_MARK_NOTIONAL_PROXY','exact_account_claim_allowed':False}
            perps.append(result)
            if mult==1 and delay==0:
                equity[-1]={**equity[-1],'equity_usd':final,'cash_usdt':final,'spot_qty':0,'short_qty':0,'isolated_wallet_usdt':0,'derivative_unrealized_usdt':0,'isolated_equity_usdt':0,'spot_value_usdt':0,'maintenance_proxy_usdt':0,'drawdown':final/peak-1,'event':'closed_both_legs'}
                csvout(out/f'{asset.lower()}_funding_events.csv',flow);csvout(out/f'{asset.lower()}_account_hourly.csv',equity);draw_svg(out/f'{asset.lower()}_equity.svg',equity,asset+' spot / perpetual carry')
                orders.extend([{'asset':asset,'ts':et,'utc':iso(et),'leg':'spot','side':'buy','gross_base_qty':gross,'net_base_qty':netq,'price':S,'quote_cash_delta':-spent,'fee_base':gross*sf,'source':'next-hour-open proxy'}, {'asset':asset,'ts':et,'utc':iso(et),'leg':'linear_perpetual','side':'sell','base_qty':q,'price':F,'quote_fee':q*F*tf,'source':'next-hour-open proxy'}, {'asset':asset,'ts':end,'utc':iso(end),'leg':'spot','side':'sell','base_qty':netq,'price':So,'quote_cash_delta':netq*So*(1-sf),'quote_fee':netq*So*sf,'source':'hour-open proxy'}, {'asset':asset,'ts':end,'utc':iso(end),'leg':'linear_perpetual','side':'buy','base_qty':q,'price':Fo,'quote_pnl':q*(F-Fo),'quote_fee':q*Fo*tf,'source':'hour-open proxy'}]);hand.append({'case':asset+'_first_actual_funding_event',**flow[0]})
                # Same fixed q path in chronological 30-day blocks, no compounding or block winner selection.
                for block in range(3):
                    a=et+block*30*DAY;b=min(a+30*DAY,end)
                    if a>=b:continue
                    funding=sum(x['funding_received_usdt'] for x in flow if a<x['ts']<=b);rollingrows.append({'asset':asset,'block':block+1,'start_utc':iso(a),'end_utc':iso(b),'same_fixed_quantity':q,'funding_received_usdt_proxy':funding,'price_hedge_change_usdt':netq*(spot[b]['open']-spot[a]['open'])+q*(swap[a]['open']-swap[b]['open']),'note':'holding-block attribution, not independent roundtrip strategy return'})
                for ret in [-.5,.5,1.0]:
                    for wide in [.02,.05]:
                        Sp=spot[et]['open']*(1+ret);Fp=Sp*(1+wide);margin_after=4000-q*F*tf+q*(F-Fp);eq=cash+netq*Sp+margin_after
                        stress.append({'asset':asset,'structure':'linear_perpetual','spot_shock':ret,'basis_widening':wide,'account_equity_usd':eq,'account_return_pct':(eq/10000-1)*100,'isolated_margin_usdt':margin_after,'maintenance_proxy_usdt':q*Fp*.01,'isolated_liquidation_proxy':margin_after<=q*Fp*.01})
                for rate in [-.0001,-.0003,0,.0001]:
                    fr=q*F*rate*270;scenario=10000-costs+fr
                    stress.append({'asset':asset,'structure':'linear_perpetual_funding','rate_each8h':rate,'days':90,'funding_received_usdt':fr,'execution_cost_assumed':costs,'account_equity_usd':scenario,'account_return_pct':(scenario/10000-1)*100,'surplus_over_4pct_cash':scenario-10000-10000*.04*90/365,'assumption':'constant entry price and basis; no forecast'})
        # One already-selected dated contract history; positive basis not converted to settled income.
        common=sorted(t for t in expiry if t in spot and t>=max(start,int(exinst['listTime'])) and t<=end)
        for t in common:
            basisrows.append({'asset':asset,'instrument':expid,'ts':t,'utc':iso(t),'spot_open_usdt':spot[t]['open'],'expiry_open_usd':expiry[t]['open'],'basis_pct_at_usdt_usd_parity':(expiry[t]['open']/spot[t]['open']-1)*100,'remaining_days':(int(exinst['expTime'])-t)/DAY,'status':'unsettled same-contract quote diagnostic'})
        e0=common[0];e1=common[-1];S0=spot[e0]['open']*(1+.0002);F0=expiry[e0]['open']*(1-.0002);nc=floorlot(5000*(1-.001)*F0/S0/face,ex_lot);N=nc*face;q=N/F0;gross=ceillot(q/(1-.001),sp_lot);spent=gross*S0
        if spent>5000:nc=round(nc-ex_lot,8);N=nc*face;q=N/F0;gross=ceillot(q/(1-.001),sp_lot);spent=gross*S0
        netq=gross*(1-.001);ef=N/F0*.0005;cash=10000-spent;elist=[];mincoll=math.inf
        for t in common:
            St=spot[t]['open'];Ft=expiry[t]['open'];cp=N*(1/Ft-1/F0);coll=.8*netq-ef+cp;mincoll=min(mincoll,coll);assert coll>N/Ft*expiry_mmr,('EXPIRY_HISTORICAL_MARGIN_BREACH_STOP',asset,iso(t));eq=cash+(netq-ef+cp)*St
            elist.append({'asset':asset,'ts':t,'utc':iso(t),'instrument':expid,'face_notional_usd':N,'spot_qty_before_pnl':netq,'inverse_pnl_coin':cp,'entry_fee_coin':ef,'collateral_coin':coll,'unencumbered_coin':.2*netq,'cash_usdt':cash,'equity_usd':eq,'spot_open':St,'future_open':Ft,'status':'unsettled diagnostic'})
        ST=spot[e1]['open']*(1-.0002);FT=expiry[e1]['open']*(1+.0002);cp=N*(1/FT-1/F0);cf=N/FT*.0005;final=cash+(netq-ef+cp-cf)*ST*(1-.001);peak=10000;dd=0
        for z in elist:peak=max(peak,z['equity_usd']);dd=min(dd,z['equity_usd']/peak-1)
        dd=min(dd,final/peak-1)
        # Terminal cash and quantity state closes exactly; preclose mark is retained as a separate event.
        elist[-1]['status']='preclose_mark'
        elist.append({**elist[-1], 'equity_usd':final,'face_notional_usd':0,'spot_qty_before_pnl':0,'inverse_pnl_coin':0,'entry_fee_coin':0,'collateral_coin':0,'unencumbered_coin':0,'cash_usdt':final,'status':'closed_both_legs','event_sequence':1})
        csvout(out/f'{asset.lower()}_expiry_account.csv',elist)
        coins_for_sale=netq-ef+cp-cf
        orders.extend([
            {'asset':asset,'structure':'inverse_expiry','ts':e0,'utc':iso(e0),'leg':'spot','side':'buy','gross_base_qty':gross,'net_base_qty':netq,'price':S0,'quote_cash_delta':-spent,'fee_base':gross*.001,'source':'first complete listed-hour open proxy'},
            {'asset':asset,'structure':'inverse_expiry','ts':e0,'utc':iso(e0),'leg':'inverse_expiry','side':'sell','instrument':expid,'contracts':nc,'usd_face_notional':N,'price':F0,'fee_base':ef,'source':'same-hour open proxy'},
            {'asset':asset,'structure':'inverse_expiry','ts':e1,'utc':iso(e1),'leg':'inverse_expiry','side':'buy','instrument':expid,'contracts':nc,'usd_face_notional':N,'price':FT,'pnl_base':cp,'fee_base':cf,'source':'same-hour open proxy'},
            {'asset':asset,'structure':'inverse_expiry','ts':e1,'utc':iso(e1),'leg':'spot','side':'sell','gross_base_qty':coins_for_sale,'price':ST,'quote_cash_delta':coins_for_sale*ST*(1-.001),'quote_fee':coins_for_sale*ST*.001,'source':'same-hour open proxy'}])
        expiryhist.append({'asset':asset,'instrument':expid,'start_utc':iso(e0),'end_utc':iso(e1),'hours':len(common),'expected_hours':(e1-e0)//HOUR+1,'gap_hours':(e1-e0)//HOUR+1-len(common),'contracts':nc,'face_notional_usd':N,'spot_spent_usdt':spent,'initial_capital_usd':10000,'funding_applicable':False,'net_pnl_usd_proxy':final-10000,'net_return_pct':(final/10000-1)*100,'hourly_mdd_pct':dd*100,'min_collateral_coin':mincoll,'maintenance_rate_used':expiry_mmr,'historical_actual_maintenance_unverified':True,'liquidation_proxy_encountered':False,'same_contract_basis_min_pct':min((expiry[t]['open']/spot[t]['open']-1)*100 for t in common),'same_contract_basis_max_pct':max((expiry[t]['open']/spot[t]['open']-1)*100 for t in common),'status':'UNSETTLED_HISTORY_OHLC_CLOSE_PROXY_NOT_LOCKED_RETURN'})
    # Currency and cash benchmarks are scenarios, no Earn yield or FDIC-equivalent assumption.
    for leg_gap in [-.01,.01]:stress.append({'structure':'unhedged_leg_gap','move_before_second_leg':leg_gap,'one_leg_notional_usd':5000,'unhedged_pnl_usd':5000*leg_gap,'account_return_pct':50*leg_gap,'execution_status':'scenario, no atomic two-leg fill demonstrated'})
    for fx in [.99,.95]:stress.append({'structure':'stablecoin_usd_conversion','usdt_usd':fx,'unhedged_full_account_stablecoin_cash_return_pct':(fx-1)*100,'interpretation':'if all final proceeds in USDT; no coin/USD hedge credit'})
    for r in quotes:
        if r['structure']=='inverse_expiry' and r['round']==0:
            for cashrate in [0,.02,.04,.06]:
                opportunity=10000*cashrate*r['days_to_expiry']/365
                cashsens.append({'asset':r['asset'],'structure':'inverse_expiry','cost_multiplier':r['cost_multiplier'],'cash_benchmark_rate':cashrate,'net_pnl_usd_proxy':r['conditional_flat_terminal_net_usd'],'cash_pnl_usd':opportunity,'surplus_over_cash':r['conditional_flat_terminal_net_usd']-opportunity,'cash_yield_assumption_not_verified_offer':True})
    for r in perps:
        if r['variant']=='cost1_delay0h':
            for cashrate in [0,.02,.04,.06]:
                opportunity=10000*cashrate*r['days']/365
                cashsens.append({'asset':r['asset'],'structure':'linear_perpetual','cost_multiplier':1,'cash_benchmark_rate':cashrate,'net_pnl_usd_proxy':r['net_pnl_usd_proxy'],'cash_pnl_usd':opportunity,'surplus_over_cash':r['net_pnl_usd_proxy']-opportunity,'cash_yield_assumption_not_verified_offer':True})
    csvout(out/'cash_sensitivity.csv',cashsens)
    csvout(out/'quote_validation.csv',quotechecks);csvout(out/'quotes_and_economics.csv',quotes);csvout(out/'perpetual_comparison.csv',perps);csvout(out/'expiry_history_comparison.csv',expiryhist);csvout(out/'stress_scenarios.csv',stress);csvout(out/'orders.csv',orders);csvout(out/'historical_basis.csv',basisrows);csvout(out/'funding_blocks.csv',rollingrows);dump(out/'data_quality.json',dq);dump(out/'clock_validation.json',clock);dump(out/'manual_checks.json',{'unit_examples':tests(),'real_examples':hand});dump(out/'environment.json',{'python':sys.version,'platform':platform.platform(),'dependency_policy':'standard library only; no trained model'})
    best={a:{} for a in ['BTC','ETH']}
    for a in best:
        eq=[r for r in quotes if r['asset']==a and r['structure']=='inverse_expiry' and r['cost_multiplier']==1];valid=[r for r in eq if r['quote_valid']];chosen=(valid or eq)[0]
        best[a]={'expiry_selected_first_valid_else_first':chosen,'perpetual_history_base':next(r for r in perps if r['asset']==a and r['variant']=='cost1_delay0h'),'expiry_history':next(r for r in expiryhist if r['asset']==a),'all_quotes_valid_count':sum(r['valid'] for r in quotechecks if r['asset']==a)}
    summary={'family':cfg['family'],'family_id':cfg['family_id'],'version':'C0 / C0-E1','status':'explore / not promoted / not live-ready','result_label':'NO_EXECUTABLE_NET_PROFIT_VERIFIED','economic_decision':'Do not allocate capital after first-round limited feasibility study','initial_capital_usd':10000,'independent_accounts_not_additive':True,'data_coverage':{'perpetual_start_utc':iso(start+HOUR),'perpetual_end_utc':iso(end),'funding_events_each':len(range(start+8*HOUR,end+1,8*HOUR)),'original_usdt_expiry_surface':'ABSENT; final maturity 2026-06-26','expiry_same_contract_only':True},'clock_validation':clock,'exposure':'2025+ ITERATIVE_REUSED_DIAGNOSTIC_2025_PLUS; newly fixed economic contracts, no blind history','assets':best,'blockers':['Original OKX BTC/ETH USDT expiry products discontinued; inverse extension uses different collateral and settlement.','Public default fees do not prove user region/account access or actual fee tier.','Historical mark at exact funding assessment and historical complete interval change archive unavailable; rates actual, notional proxy bounded by candle high/low.','Historical book fills unavailable; OHLC executions remain scenario.','Dated inverse settlement spot/index tracking and USD/USDT parity unproven; entry coin fee leaves small residual.','Future perpetual funding is not locked; sign reversals tested.'],'artifacts':{'report':'diagnostics/carry-feasibility-2026-09-08.md','raw':str(raw.relative_to(ROOT)),'reproduce':'scripts/reproduce.py','quotes':str((out/'quotes_and_economics.csv').relative_to(ROOT)),'accounts':str(out.relative_to(ROOT)),'config':'specs/contract.json','inverse_contract':'specs/expiry-inverse-amendment.json'}}
    dump(out/'summary.json',summary)
    return summary

def main():
    p=argparse.ArgumentParser();p.add_argument('--raw',default=str(ROOT/'artifacts/raw/capture_curl_20260908'));p.add_argument('--output',default=str(ROOT/'artifacts/results'));p.add_argument('--verify',action='store_true');a=p.parse_args();raw=Path(a.raw);out=Path(a.output)
    if a.verify:
        manifest=read(ROOT/'artifacts/input_manifest.json')
        for row in manifest['files']:
            path=ROOT/row['path'];assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256'],row['path']
    s=analyze(raw,out);print(json.dumps({'status':s['result_label'],'assets':{k:{'expiry_surplus':v['expiry_selected_first_valid_else_first']['surplus_over_cash_usd'],'perp_net':v['perpetual_history_base']['net_pnl_usd_proxy'],'perp_surplus':v['perpetual_history_base']['surplus_over_cash_usd']} for k,v in s['assets'].items()}},indent=2))
if __name__=='__main__':main()
