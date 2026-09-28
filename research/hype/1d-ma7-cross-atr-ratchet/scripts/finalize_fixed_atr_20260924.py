"""Finalize bounded local research evidence and family records; no strategy mutation."""
from pathlib import Path
import json,sys,os,shutil,platform,re
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parent))
import validate_fixed_atr_20260924_r3 as v
R,X,P,ROOT,BASE,MARKET=v.R,v.X,v.P,v.ROOT,v.BASE,v.MARKET

def prepend(path,section):
 old=path.read_text();head,rest=old.split('\n',1)
 if section.split('\n',1)[0] not in old:path.write_text(head+'\n\n'+section.strip()+'\n'+rest)

def verify():
 v.verify_started()
 h=pd.read_csv(R/'comparison.csv');c=pd.read_csv(X/'comparison.csv');longest=pd.read_csv(X/'longest_per_coin.csv');sums=pd.read_csv(X/'summary.csv');pairs=pd.read_csv(X/'trade_pairs.csv')
 assert len(h)==46 and len(c)==947 and c.slug.nunique()==649 and len(longest)==649
 assert not c.run_key.duplicated().any()
 expected=c.sort_values(['slug','days','D_start'],ascending=[True,False,True]).drop_duplicates('slug');assert expected.run_key.tolist()==longest.run_key.tolist()
 for row in h.itertuples():
  for arm in ['D','F']:
   p=ROOT/getattr(row,arm+'_path');s=json.loads((p/'summary.json').read_text());tr=pd.read_csv(p/'trades.csv')
   np.testing.assert_allclose(s['return_pct'],getattr(row,arm+'_return_pct'),rtol=1e-12,atol=1e-10)
   assert len(tr)==getattr(row,arm+'_trades')
   np.testing.assert_allclose((np.prod(1+tr.return_on_entry_equity)-1)*100,s['return_pct'],rtol=1e-12,atol=1e-9)
 for row in c.itertuples():
  for arm in ['D','F']:
   s=json.loads((ROOT/getattr(row,arm+'_path')/'summary.json').read_text());assert s['start']==getattr(row,arm+'_start')
   np.testing.assert_allclose(s['return_pct'],getattr(row,arm+'_return_pct'),rtol=1e-12,atol=1e-10)
   np.testing.assert_allclose(s['max_drawdown_pct'],getattr(row,arm+'_max_drawdown_pct'),rtol=1e-12,atol=1e-10)
 assert pairs.relationship.ne('missed').sum()==c.F_trades.sum()==21460
 assert pairs.relationship.ne('new').sum()==c.D_trades.sum()==22000
 assert c.same_entries.sum()==pairs.relationship.eq('same').sum()==20849
 for sample,z in [('每币最长连续段',longest),('全部连续段',c)]:
  row=sums[sums['sample'].eq(sample)].iloc[0]
  np.testing.assert_allclose(np.median(z.F_return_pct-z.D_return_pct),row.median_delta_return_pp,atol=1e-12)
  np.testing.assert_allclose(np.median(abs(z.F_max_drawdown_pct)-abs(z.D_max_drawdown_pct)),row.median_delta_drawdown_pp,atol=1e-12)
  assert row.improved==(z.F_return_pct-z.D_return_pct>1e-8).sum()
 episode=pd.read_csv(R/'fixed_entry_pairs.csv');assert len(episode)==18
 original=v.table(P/'reference_original_start/trades.csv');fixed=v.table(R/'accounts/original/F/trades.csv')
 np.testing.assert_allclose(episode.D_return_pct,original.return_on_entry_equity*100,atol=1e-10)
 np.testing.assert_allclose(episode.F_return_pct,fixed.return_on_entry_equity*100,atol=1e-10)
 for p in [R/'html_paths_audit.json',R/'html_tables_audit.json']:assert json.loads(p.read_text())['complete']
 return {'complete':True,'HYPE_account_pairs':46,'cross_account_pairs':947,'cross_coin_count':649,'summary_to_saved_account_checks':1986,'same_entry_pairs':20849,'all_cross_pair_rows':22611,'longest_selected_only_by_duration':True,'18_fixed_entry_outcomes_agree':True,'frozen_pins_unchanged':True}

def main():
 verification=verify();v.write_json(R/'summary_audit.json',verification)
 tests={'complete':True,'command':'.venv/bin/python -m pytest -q tests/test_v3_fixed_atr_validation_20260924.py','result':'7 passed in 0.77s','cases':['fixed ATR unchanged under future ATR perturbation both sides','price scale invariance two scales','prefix causality and per-trade reset','exact rolling crossing equality','no new entry after insolvency'],'test_sha256':v.sha(ROOT/'tests/test_v3_fixed_atr_validation_20260924.py')};v.write_json(R/'tests.json',tests)
 browser={'actual_browser_layout_verified':False,'attempt':'cua.createBrowserTab iab file URL','blocked':True,'reason':'Browser URL policy blocks local file URL','workaround_attempted':False,'offline_interactive_and_stopline_audits_pass':True};v.write_json(R/'browser_review.json',browser)
 local='''## 2026-09-24：固定入场ATR验证完成，保留原V3

保持其他规则与成本，完成HYPE原起点、45组邻域和18组固定入场双臂对照，再验证非HYPE的649币947连续段；原全市场动态ATR账户复用，仅新增固定版。原起点HYPE **544.76% → 537.60%**，回撤 **27.26% → 28.98%**，同18笔。共同起点463.60% → 585.08%的增益几乎来自6月28日单笔；剔除它，其余16笔457.66% → 456.51%。34/45邻域改善，但初始止损倍数四邻点全部变差。

649币最长段仅295改善，配对收益变化中位−0.87个百分点、回撤变化+0.34个百分点；完整2025至截止255币仅111改善，收益变化中位−1.50、回撤变化+0.81个百分点。不支持普遍替换，不登记V4。所有历史均已见；完整牛熊、资金费、身份、强平和流动性证据仍不足。

[完整结论](diagnostics/v3-fixed-atr-validation-results-20260924.md) · [交互报告与全部币](artifacts/v3_fixed_atr_validation_20260924/html/index.html) · [HYPE止损虚线](artifacts/v3_fixed_atr_validation_20260924/html/coins/HYPE.html) · [冻结契约](specs/v3-fixed-entry-atr-validation-20260924.md)。7项测试、新993个完整账户及36个单笔探针核验通过。浏览器安全策略拒绝自动访问本地HTML，离线交互、70条HYPE交易路径及649币22,611条配对展示检查通过。
'''
 for f in ['README.md','hype-1d-ma7-car-core-ledger.md','decision-log.md']:prepend(BASE/f,local)
 cross='''## 2026-09-24：固定入场ATR跨币对照，未支持普遍替换

沿用V3自然指标就绪与每边0.1%手续费/0.04%滑点；仅改变持仓止损ATR是否固定在入场信号日。排除HYPE及UNKNOWN，649币947连续段全部保留，原动态ATR账户只核对旧产物，新固定ATR947账户独立核验通过（21,460笔、235,118条止损、25,706,840个权益节点）。

每币最长段295/649改善，收益变化中位−0.87个百分点、回撤变化+0.34；完整2025年至截止255币111改善，变化中位−1.50、回撤变化+0.81。原/固定都有6个账户权益耗尽，不剔除；模型无强平层，极端低于−100%结果不是可执行永续净收益。完整2020—2024仅BTC、ETH两币，不支持全市场牛熊结论。正式V3不变，不登记V4。

[统一中文报告](../../../hype/1d-ma7-cross-atr-ratchet/diagnostics/v3-fixed-atr-validation-results-20260924.md) · [全部币HTML](artifacts/v3_fixed_atr_validation_20260924/html/index.html) · [固定窗口汇总](artifacts/v3_fixed_atr_validation_20260924/summary.csv) · [账户复核](artifacts/v3_fixed_atr_validation_20260924/audit_r2.json) · [保留与复算](artifacts/v3_fixed_atr_validation_20260924/README.md)。本轮可再生大型证据仅存本地忽略目录，未新增普通Git大对象。
'''
 # Family sits at research/asset-portfolios/<family>, two parent levels to research.
 cross=cross.replace('../../../hype/','../../hype/')
 for f in ['README.md','bin-1d-ma7-car-gen-core-ledger.md','decision-log.md']:prepend(MARKET/f,cross)
 report=BASE/'diagnostics/v3-fixed-atr-validation-results-20260924.md'
 content=report.read_text().replace('HTML通过离线交互与虚线记录核验；实际浏览器布局验证状态以交付记录为准。','HTML通过离线交互与虚线记录核验；浏览器安全策略阻止自动打开本地文件，未进行真实浏览器布局检查，未尝试绕过。')
 report.write_text(content)
 for directory,role in [(R,'HYPE46账户、36单笔探针、45组邻域与统一报告'),(X,'649币947段固定ATR账户与交易页面')]:
  readme=f'''# 固定入场ATR验证证据 · 2026-09-24

{role}。仅结构对照，不晋升、不改变正式V3。冻结成本每边0.1%+0.04%，数据截至2026-09-05 UTC。

## 保留与预算

账户、小时权益、HTML与输入帧是可再生的本地忽略产物；原D账户只引用，不复制。此次新增轮次上限为46个HYPE完整账户、36单笔探针、947个跨币固定版账户，不追加参数或选币。HYPE约23 MiB、跨币约472 MiB；家族既有产物总预算已较大，本轮不新增普通Git大对象。仓库保留脚本、中文结论和本说明，小型JSON/CSV以本地证据与散列清单保留。

可逆外置评估：大型权益可置于私有制品库冷存储；先复制、记录URI/版本/散列并回取核验，再在获得迁移授权后切引用。当前没有配置外部存储、没有迁移、没有删除旧证据、没有强行加入Git或声称预算治理全仓通过。干净克隆需先恢复冻结输入及原D产物，散列文件不能代替原始对象。

## 来源和运行

source_manifest.json记录代码与源报告散列；started.json固定原配置和样本；validation_revision*.json说明独立校验器边界修正；source_snapshots保留运行和展示所用代码。原失败记录不覆盖。共享v8引擎未改。

在仓库根，首次新建目标目录时执行 validate_fixed_atr_20260924.py prepare；本轮保留原prepare，HYPE由 validate_fixed_atr_20260924_r3.py hype完成，跨币由 validate_fixed_atr_20260924_r2.py cross --workers 4完成。已有账户读取后复核，不重复计算。报告执行 report_fixed_atr_20260924.py 和 build_fixed_atr_html_20260924.py；两项 audit_fixed_atr_*_20260924.cjs检查HTML。运行环境与散列见source_manifest.json；完整命令路径以hype家族scripts为前缀。

## 验收

HYPE7项机制测试、993新完整账户及36单笔探针独立核验；跨币固定版21,460笔全部对账。649币22,611条交易配对可查，HYPE70条两起点双方案路径逐条核验虚线、倍数与缩放，390像素宽离线交互通过。真实浏览器因本地URL安全策略未打开；不声称已做截图或视觉布局验收。

completion.json为完成锚点；artifact_checksums.json对本目录全部最终文件（自身除外）记录SHA256。旧动态账户以源目录冻结清单校验，输入沿用原质量边界，未知资金费不是零。
'''
  (directory/'README.md').write_text(readme)
 scripts=BASE/'scripts';own=[p for p in scripts.iterdir() if 'fixed_atr' in p.name and p.suffix in ['.py','.cjs']]
 sources=own+[ROOT/'tests/test_v3_fixed_atr_validation_20260924.py',v.SPEC,v.E,BASE/'scripts/audit_v3_parameters_20260924.py',BASE/'scripts/v3_parameter_study_20260924.py',BASE/'scripts/report_v3_parameters_20260924.py']
 sources += [MARKET/'scripts'/n for n in ['common.py','run_market.py','v3_no_extra_warmup_20260913.py','v3_opportunity_inputs_20260913.py','run_exit_state_history_20260910.py','build_ma30_report_20260911.py','revise_v3_stoplines_20260913.py','report_v3_no_extra_warmup_20260913.py','v3_stoplines_chart_20260913.js','audit_v3_opportunity_20260913.py']]
 pins={str(p.relative_to(ROOT)):v.sha(p) for p in sources}
 snap=R/'source_snapshots';snap.mkdir(exist_ok=True)
 for p in sources:
  target=snap/p.relative_to(ROOT);target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,target)
 source={'source_files':pins,'environment':{'python':platform.python_version(),'pandas':pd.__version__,'numpy':np.__version__},'original_source_pins':json.loads((R/'started.json').read_text())['pins'],'source_snapshots':str(snap.relative_to(ROOT)),'original_dynamic_accounts_reused':True,'source_refresh':False}
 # Verify document and static HTML links generated by this round.
 checked_links=0
 docs=[report,*[BASE/f for f in ['README.md','hype-1d-ma7-car-core-ledger.md','decision-log.md']],*[MARKET/f for f in ['README.md','bin-1d-ma7-car-gen-core-ledger.md','decision-log.md']]]
 for p in docs:
  for target in re.findall(r'\]\(([^)]+)\)',p.read_text()):
   if 'fixed_atr' not in target and 'fixed-atr' not in target:continue
   assert (p.parent/target.split('#')[0]).resolve().exists(),(p,target);checked_links+=1
 for directory in [R,X]:
  v.write_json(directory/'source_manifest.json',source)
  v.write_json(directory/'completion.json',{'complete':True,'decision':'NOT_SUPPORTED_AS_GENERAL_REPLACEMENT','strategy_V3_unchanged':True,'source_hashes_verified':True,'independent_account_audit':True,'html_offline_audit':True,'browser_layout_verified':False,'browser_local_url_blocked':True,'checked_document_links':checked_links})
  files={str(p.relative_to(directory)):v.sha(p) for p in directory.rglob('*') if p.is_file() and p.name!='artifact_checksums.json'}
  v.write_json(directory/'artifact_checksums.json',files)
  for rel,digest in files.items():assert v.sha(directory/rel)==digest
 print(json.dumps({'complete':True,'document_links':checked_links,'source_pins':len(pins),'HYPE_artifacts':len(json.loads((R/'artifact_checksums.json').read_text())),'cross_artifacts':len(json.loads((X/'artifact_checksums.json').read_text()))},indent=2))
if __name__=='__main__':main()
