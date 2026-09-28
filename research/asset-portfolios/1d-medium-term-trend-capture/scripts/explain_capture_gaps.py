"""结果揭示后的路径解释；不重跑策略、不新增筛选或改变任何收益。"""
from pathlib import Path
import json

import pandas as pd

FAMILY=Path(__file__).resolve().parents[1]
RUN=FAMILY/'artifacts/research-20260909'


def main():
    out=FAMILY/'artifacts/capture-gap-explanation'
    out.mkdir(exist_ok=False)
    daily=pd.read_parquet(RUN/'portfolio_daily.parquet')
    units=pd.read_parquet(RUN/'unit_daily.parquet')
    actions=pd.read_parquet(RUN/'portfolio_actions.parquet')
    obs=pd.read_parquet(RUN/'opportunities.parquet')
    wide=obs[obs.cost_id.eq('base') & obs.complete_window_60 & obs.normal_complete].pivot(
        index='origin_id',columns='policy',values=['return','entered','entry_price','entry_ts'])
    entered=wide['entered']['C'].astype(bool)
    decomposition={}
    for key,mask in [('C_entered',entered),('C_not_entered',~entered)]:
        g=wide[mask]
        decomposition[key]=dict(n=len(g),means={p:float(g['return'][p].mean()) for p in 'ABC'},
                                C_minus_B_total=float((g['return']['C']-g['return']['B']).sum()),
                                C_minus_B_contribution_per_original_opportunity=float(
                                    (g['return']['C']-g['return']['B']).sum()/len(wide)))
    entry_difference=(wide['entry_price']['C'][entered]/wide['entry_price']['B'][entered]-1).astype(float)
    wait_days=(pd.to_datetime(wide['entry_ts']['C'][entered],utc=True)-
               pd.to_datetime(wide['entry_ts']['B'][entered],utc=True)).dt.total_seconds()/86400
    decomposition['entry_price_difference']=dict(mean=float(entry_difference.mean()),
             median=float(entry_difference.median()),higher_fraction=float(entry_difference.gt(0).mean()),
             mean_wait_days=float(wait_days.mean()),median_wait_days=float(wait_days.median()))
    drawdowns=[]
    held_states=[]
    for policy in 'ABC':
        curve=daily[daily.cost_id.eq('base') & daily.policy.eq(policy)].reset_index(drop=True)
        trough_index=curve.drawdown.idxmin()
        peak_index=curve.equity.iloc[:trough_index+1].idxmax()
        peak,trough=curve.iloc[peak_index],curve.iloc[trough_index]
        admissions=actions[actions.cost_id.eq('base') & actions.policy.eq(policy) & actions.event.eq('ADMIT')]
        budgets=admissions[['origin_id','budget']].set_index('origin_id')
        punit=units[units.cost_id.eq('base') & units.policy.eq(policy)]
        at_peak=punit[punit.ts.eq(peak.ts)&punit.qty_close.gt(0)].join(budgets,on='origin_id').dropna(subset=['budget'])
        at_peak['exposure']=at_peak.budget*at_peak.qty_close*at_peak.close
        largest=at_peak.sort_values('exposure',ascending=False).iloc[0]
        event=punit[punit.origin_id.eq(largest.origin_id)]
        event_summary=obs[obs.cost_id.eq('base')&obs.policy.eq(policy)&obs.origin_id.eq(largest.origin_id)].iloc[0]
        common_end=event[event.ts.le(trough.ts)].iloc[-1]
        largest_change=float(largest.budget*(common_end.close_value-largest.close_value))
        drawdowns.append(dict(policy=policy,peak_bar_open=str(peak.ts),peak_close_ts=str(peak.close_ts),
                              trough_bar_open=str(trough.ts),trough_close_ts=str(trough.close_ts),
                              peak_equity=float(peak.equity),trough_equity=float(trough.equity),
                              drawdown=float(trough.equity/peak.equity-1),
                              largest_symbol=largest.symbol,largest_origin_id=largest.origin_id,
                              largest_exposure_at_peak=float(largest.exposure),
                              largest_weight_at_peak=float(largest.exposure/peak.equity),
                              largest_unit_path_pnl_peak_to_trough=largest_change,
                              portfolio_pnl_peak_to_trough=float(trough.equity-peak.equity),
                              largest_pnl_fraction_of_drawdown=float(largest_change/(trough.equity-peak.equity)),
                              origin_ts=str(event_summary.origin_ts),entry_ts=str(event_summary.entry_ts),
                              entry_price=float(event_summary.entry_price),exit_ts=str(event_summary.exit_ts),
                              exit_price=float(event_summary.exit_price),exit_reason=event_summary.exit_reason,
                              initial_budget=float(largest.budget)))
        trace=event.copy()
        trace['account_budget']=largest.budget
        trace['account_position_value']=trace.qty_close*trace.close*largest.budget
        trace['account_slot_value']=trace.close_value*largest.budget
        trace=trace.merge(curve[['ts','equity']],on='ts',how='left')
        trace['position_fraction_of_account']=trace.account_position_value/trace.equity
        held_states.append(trace)
    pd.concat(held_states,ignore_index=True).to_parquet(out/'largest-drawdown-position-paths.parquet',index=False)
    pd.DataFrame(drawdowns).to_csv(out/'largest-drawdown-explanations.csv',index=False)
    payload=dict(role='POST_RESULT_EXPLANATION_ONLY_NO_RULE_CHANGE',
                 waiting_decomposition=decomposition,drawdown_paths=drawdowns,
                 causal_mechanism_proven=False,
                 rule_changes_tested=False)
    (out/'explanation.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps(payload,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
