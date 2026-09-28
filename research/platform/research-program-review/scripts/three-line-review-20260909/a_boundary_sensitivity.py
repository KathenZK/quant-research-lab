from pathlib import Path
import json
R=Path('/Users/ZK/.codex/worktrees/5f41/quant-strategy-lab/research/asset-portfolios/1d-small-account-slow-trend')
O=Path('/tmp/three-line-a-review-20260909/boundary');O.mkdir(exist_ok=True)
(O/'raw').symlink_to(R/'artifacts/raw',target_is_directory=True) if not (O/'raw').exists() else None
src=(R/'scripts/run_research.py').read_text()
needle='            mom=tri.loc[d].to_numpy()/tri.loc[month_end[mi-lookback]].to_numpy()-1\n'
assert src.count(needle)==1
src=src.replace(needle,needle+'            if AUDIT_FORCE_BOUNDARY_OFF and d == pd.Timestamp("2018-10-31"):\n                mom[SYMS.index("VNQ")]=-abs(mom[SYMS.index("VNQ")])\n')
ns={'__name__':'audit_isolated','__file__':str(R/'scripts/run_research.py'),'AUDIT_FORCE_BOUNDARY_OFF':False}
exec(compile(src,str(R/'scripts/run_research.py'),'exec'),ns)
ns['ART']=O
frames,sched=ns['load_data']()
eq0,m0=ns['run_account'](frames,sched,'trend_12m_risk10')
ns['AUDIT_FORCE_BOUNDARY_OFF']=True
eq1,m1=ns['run_account'](frames,sched,'trend_12m_boundary_sensitivity')
res={'scope':'One known total-return convention boundary only. Flip VNQ gate OFF at 2018-10-31; retain every other raw input and rule. Not a replacement or selected candidate. Original engine source never modified; temporary in-memory addition only.',
'original':m0,'counterfactual_single_boundary_off':m1,'final_equity_difference':float(eq1.equity.iloc[-1]-eq0.equity.iloc[-1]),'max_daily_equity_difference':float((eq1.equity-eq0.equity).abs().max()),'cagr_difference':m1['cagr']-m0['cagr'],'relative_tradeoff_gate_pass': bool((abs(m1['max_drawdown'])<=.9*.185746860485 and m1['cagr']>=.0605902668496-.01) or (m1['cagr']>=.0605902668496+.01 and abs(m1['max_drawdown'])<=.185746860485+.02))}
(O/'sensitivity.json').write_text(json.dumps(res,indent=2));print(json.dumps(res,indent=2))
