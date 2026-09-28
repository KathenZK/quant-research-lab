"""Inventory every assigned HYPE 15m/30m/1h family; no result-driven selection."""
from pathlib import Path
import json, hashlib
ROOT=Path(__file__).resolve().parents[4]; OUT=ROOT/'research/asset-portfolios/multi-legacy-post-registration-audit/artifacts/hype_other'
items={
'15m-bollinger-keltner-squeeze-breakout':('2026-07-23','fixed baseline',['bksb_15m'],'REPLAYED',''),
'15m-factor-ml':('2026-07-16','Round 2 final OOS candidate',[],'MISSING_FROZEN_ARTIFACTS','artifacts/model_round2_final_oos/model_manifest.json and trained LightGBM ensemble model files are absent; directory contains README only'),
'15m-keltner-trend-breakout':('2026-07-21','three predeclared K1 hypotheses',['keltner15_outer_break_mid_exit','keltner15_compression_expansion_break','keltner15_trend_pullback_mid_reclaim'],'REPLAYED','Three equal hypotheses; no winner selected'),
'15m-ma7-ma30-pyramiding':('2026-07-30','two frozen exits',['mapt_opposite_cross','mapt_close_through_ma7'],'REPLAYED','Both predeclared exits retained; original simulator terminal path omitted closing fee entry, explicitly appended original terminal equity'),
'15m-multi-horizon-ema-forecast':('2026-07-28','V2 unregistered frozen candidate',[],'MISSING_FROZEN_ARTIFACTS','artifacts/hype_15m_mhef_v2_prefit_candidate.json is absent; report specifies selected fields but not every searched calibration/volatility field, so defaults cannot substitute'),
'15m-multi-mechanism-trend-following':('2026-07-22','V3',['mmtf_15m_v3'],'REPLAYED',''),
'15m-multi-timeframe-probe-pyramiding':('2026-08-03','trader_full predeclared 1/3/10% risk both directions',[f'mtpp_{side}_{risk}pct' for side in ('long','short') for risk in (1,3,10)],'REPLAYED','One family; all six predeclared side/risk combinations reported, not six strategy families'),
'15m-multidimensional-trend-pyramiding':('2026-07-31','V1',['mdtp_v1'],'REPLAYED_WITH_ORIGINAL_LIMITATION','Original allocation-return simulator lacks explicit quantity accounting; fixed rule diagnostic only'),
'15m-price-kinematics-continuation':('2026-08-02','initial statistical diagnostic',[],'NOT_A_TRADING_STRATEGY','No frozen entry/exit/position sizing; pure prediction/statistical association study'),
'15m-pullback-trail':('2026-06-30','bracket representative in core ledger',['pbtr'],'REPLAYED_WITH_ORIGINAL_LIMITATION','V3.3 trailing transplant has a documented non-executable unlocked stop, so only the distinct explicitly named bracket representative is replayed; inherited live-average costs are overridden to family ledger .001/.0004'),
'15m-riptide':('2026-06-30','external V13 unaligned observation',[],'UNRESOLVED_REPRODUCTION_FAILURE','Original external acceptance was not reproduced (419 vs 431 trades), no external source spec retained here; source short return is entry/exit-1 rather than linear perpetual 1-exit/entry; fixed and rolling-cut observations have no accepted unique local strategy'),
'15m-sequential-drift-state':('2026-07-28','KCS failed frozen reference',['sds'],'REPLAYED','Explicit reference config from prefit summary; no re-ranking'),
'15m-sma-crossover-slope':('2026-07-28','failed frozen reference hybrid_both__k6__confirm1',['sma'],'REPLAYED','Explicit reference config and SHA from prefit selection; no re-ranking'),
'1h-adaptive-regime':('2026-07-07','V4',['ar_v4'],'REPLAYED','Parameters registered 7/7; exact joint execution correction documented 7/10, separately disclosed'),
'1h-bollinger-keltner-squeeze-breakout':('2026-07-23','fixed baseline',['bksb_1h'],'REPLAYED',''),
'1h-multi-horizon-ema-forecast':('2026-07-14','fixed baseline with two original buffers',['mhef_1h_buffer0.00','mhef_1h_buffer0.10'],'REPLAYED','Two co-equal original buffers; no winner selected; final real close plus terminal closing costs included'),
'1h-multi-mechanism-trend-following':('2026-07-22','V3',['mmtf_1h_v3'],'REPLAYED',''),
'1h-price-kinematic-trend-survival-control':('2026-08-03','dynamic policy with daily fixed-hyperparameter retraining',['pktsc_long','pktsc_short'],'REPLAYED_IF_ARTIFACTS_PRESENT','Original diagnostic filters test rows by available future labels; forward adapter requires known features only while retaining strictly matured training labels and unchanged daily fitting'),
'1h-price-kinematics-continuation':('2026-08-02','initial statistical diagnostic',[],'NOT_A_TRADING_STRATEGY','No frozen entry/exit/position sizing; pure prediction/statistical association study'),
'30m-keltner-breakout-retest':('2026-07-17','initial search without accepted freeze',[],'NO_UNIQUE_FROZEN_STRATEGY','864 searched entries, zero selected candidate; closest failed row is described, but no strategy/spec freeze or registered version. Not choosing that row merely because it was the best search result'),
'30m-keltner-trend-breakout':('2026-07-13','V3',['keltner_v3'],'REPLAYED','')}
rows=[]
for family,(date,version,cases,status,reason) in items.items():
    p=ROOT/'research/hype'/family; ledger=next(p.glob('*core-ledger.md')); specs=list(p.glob('specs/*md'))
    evidence=[ledger,*specs]; replayed=cases and all((OUT/c/'summary.json').exists() for c in cases)
    if status=='REPLAYED_IF_ARTIFACTS_PRESENT': status='SPEC_RULE_CAUSAL_CORRECTION_NOT_EXACT_CODE_REPRODUCTION' if replayed else 'RUNNING_NOT_YET_COMPLETE'
    for case in cases:
        summary=OUT/case/'summary.json'
        if summary.exists():
            exact=ROOT/json.loads(summary.read_text())['date_evidence']
            if exact not in evidence:evidence.append(exact)
    rows.append({'family':family,'version_or_observation':version,'freeze_date':date,'replay_from_next_utc_day':True,'unique_config_or_equal_predeclared_configs':bool(cases),'status':status,'cases':cases,'specific_limitation_or_missing_item':reason,'date_and_identity_evidence':[str(x.relative_to(ROOT)) for x in evidence],'evidence_sha256':{str(x.relative_to(ROOT)):hashlib.sha256(x.read_bytes()).hexdigest() for x in evidence},'replay_artifacts_present':bool(replayed)})
(OUT/'inventory.json').write_text(json.dumps({'families':len(rows),'count_families_not_variants':True,'rows':rows},ensure_ascii=False,indent=2))
print('saved',len(rows),'families;',sum(x['replay_artifacts_present'] for x in rows),'replayed')
