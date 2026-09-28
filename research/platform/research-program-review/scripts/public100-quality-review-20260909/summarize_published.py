"""Describe frozen published results; no strategy engine, new inputs or selection."""
from pathlib import Path
import json
import math

ROOT = Path('/tmp/public100-quality-root-20260909')
F = ROOT / 'source-snapshot'
rows = json.loads((F / 'artifacts/equity-diagnostic/results.json').read_text())['results']
rows += json.loads((F / 'artifacts/equity-diagnostic/calendar-results.json').read_text())['results']
eq = [r for r in rows if r.get('cost_bps') == 10 and r['id'] != 'BENCHMARK']
benchmark = next(r for r in rows if r.get('cost_bps') == 10 and r['id'] == 'BENCHMARK')
result = {
    'scope': 'Published nineteen original IDs: 18 ETF implementations plus four crypto implementations. B5 continuation remains separate.',
    'equity_original_ids': len({r['id'] for r in eq}),
    'equity_variants': len(eq),
    'positive_variants': sum(r['total_return'] > 0 for r in eq),
    'positive_with_historical_mdd_le_30pct': [r['variant'] for r in eq if r['total_return'] > 0 and abs(r['mdd']) <= .30],
    'cagr_above_spy': [r['variant'] for r in eq if r['cagr'] > benchmark['cagr']],
    'sharpe_above_spy': [r['variant'] for r in eq if r['sharpe_rf0'] > benchmark['sharpe_rf0']],
    'benchmark': benchmark,
    'selected_yearly_excess': {},
}
names = ['A9_TEXT_ROC252', 'A9_CODE_MOM63', 'A36_JANUARY_BAROMETER',
         'C4_KDA100', 'A7_TEXT_ROC252', 'C1_GEM']
for name in names:
    r = next(r for r in eq if r['variant'] == name)
    logs = {y: math.log1p(v) - math.log1p(benchmark['yearly'][y]) for y, v in r['yearly'].items()}
    result['selected_yearly_excess'][name] = {
        'cagr': r['cagr'], 'mdd': r['mdd'],
        'years_beating_spy': sum(v - benchmark['yearly'][y] > 1e-10 for y, v in r['yearly'].items()),
        'years_tied_spy_tolerance_1e_minus10': sum(abs(v - benchmark['yearly'][y]) <= 1e-10 for y, v in r['yearly'].items()),
        'years': len(logs), 'log_relative_wealth_by_year': logs,
        'total_log_relative_wealth': sum(logs.values()),
        'largest_positive_year': max(logs, key=logs.get),
        'largest_year_log_relative': max(logs.values()),
        'scope': 'Descriptive yearly return and relative-compounding attribution. Includes partial 2026. Not a requirement to win each year, not a removed-year account and not a significance test.',
    }
(ROOT / 'root-result-summary.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({k: v for k, v in result.items() if k not in ['benchmark', 'selected_yearly_excess']}, ensure_ascii=False))
