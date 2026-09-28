"""Read only current-audit derived snapshots after content verification."""
from pathlib import Path
import json
import hashlib
import pandas as pd

FAMILY=Path(__file__).resolve().parents[1]
INPUTS=FAMILY/'artifacts/inputs'
END=pd.Timestamp('2026-09-05T15:00:00Z')

def load_checked(name):
    manifest=json.loads((INPUTS/'manifest.json').read_text())
    p=INPUTS/name
    if hashlib.sha256(p.read_bytes()).hexdigest()!=manifest['files'][name]['sha256']:
        raise ValueError(f'Current-audit input hash mismatch: {name}')
    return pd.read_parquet(p)

def load_prices(asset='HYPE',tf='15m'):
    f=load_checked(f'{asset}_{tf}.parquet')
    if not f.research_window_valid.all() or f.research_segment_id.nunique()!=1:
        raise ValueError('Invalid price windows')
    return f

def load_funding(asset='HYPE'):
    f=load_checked(f'{asset}_funding_observed.parquet').sort_values('ts').reset_index(drop=True)
    if not f.event_unambiguous.all() or f.ts.duplicated().any():
        raise ValueError('Ambiguous observed funding')
    f.attrs['funding_window_verified']=False
    f.attrs['interpretation']='Observed-funding-adjusted estimate only; no missing-event zero fill.'
    return f
