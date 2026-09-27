"""Private Bit2Me OHLCV snapshots, never fabricated trusted schema columns."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
import urllib.parse
import requests

ROOT = Path(__file__).resolve().parents[4]
API = 'https://gateway.bit2me.com/v1/trading/candle'


def capture(session, url, destination, name):
    response = session.get(url, timeout=40)
    raw = response.content
    (destination/name).write_bytes(raw)
    (destination/(name+'.request.json')).write_text(json.dumps(dict(
        url=url, status=response.status_code, downloaded_at=datetime.now(timezone.utc).isoformat(),
        retry_after=response.headers.get('Retry-After'), sha256=hashlib.sha256(raw).hexdigest()), indent=2)+'\n')
    # 429/403 stop the run; do not switch IPs or retry around provider limits.
    response.raise_for_status()
    return raw


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--contract', type=Path, required=True)
    parser.add_argument('--proxy')
    parser.add_argument('--rights-audit', type=Path, required=True)
    a = parser.parse_args()
    contract = json.loads(a.contract.read_text())
    date = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    dest = ROOT / 'data/raw/bit2me_ohlcv' / date / str(contract['minutes'])
    dest.mkdir(parents=True, exist_ok=False)
    session = requests.Session()
    session.trust_env = False
    session.proxies = {'https': a.proxy} if a.proxy else {}
    raw = a.rights_audit.read_bytes()
    (dest/'rights-audit.md').write_bytes(raw)
    refs = [dict(path='rights-audit.md', url='https://legal.bit2me.com/en/support/solutions/articles/35000293283-market-data',
                 sha256=hashlib.sha256(raw).hexdigest(), kind='AGENT_REVIEW_NOT_ORIGINAL_HTML')]
    for name, url in [('api-schema.json', 'https://api.bit2me.com/openapi/trading-spot-rest.json')]:
        raw = capture(session, url, dest, name)
        refs.append(dict(path=name, url=url, sha256=hashlib.sha256(raw).hexdigest()))
    start = int(datetime.fromisoformat(contract['requested_start']).timestamp()*1000)
    end = int(datetime.fromisoformat(contract['end_exclusive']).timestamp()*1000)
    step = contract['minutes']*60_000
    pages = []
    for n, cursor in enumerate(range(start, end, 999*step)):
        query = dict(symbol=contract['symbol'], interval=contract['minutes'], startTime=cursor,
                     endTime=min(end-1, cursor+999*step-1), limit=1000)
        url = API+'?'+urllib.parse.urlencode(query)
        name = f'page-{n:03d}.json'
        raw = capture(session, url, dest, name)
        body = json.loads(raw)
        if not isinstance(body, list) or any(not isinstance(r, list) or len(r) != 6 for r in body):
            raise ValueError('Unexpected native response; preserved bytes, stop')
        pages.append(dict(path=name, url=url, sha256=hashlib.sha256(raw).hexdigest(), rows=len(body)))
        time.sleep(.3)
    manifest = dict(data_source='bit2me_public_rest', exchange='bit2me', symbol=contract['symbol'],
                    minutes=contract['minutes'], downloaded_at=datetime.now(timezone.utc).isoformat(),
                    acceptance_status='raw_unaccepted', real_market_data=True,
                    missing_native_fields=['trade_count', 'quote_volume', 'vwap'],
                    closure_evidence='API schema states last row is current; exclude unfinished and boundary rows; not sufficient for trusted admission alone',
                    requested_start=contract['requested_start'], end_exclusive=contract['end_exclusive'],
                    contract_sha256=hashlib.sha256(a.contract.read_bytes()).hexdigest(), references=refs, pages=pages,
                    rights=dict(research_use_allowed=True, research_use_scope='PRIVATE_INTERNAL_RESEARCH',
                                commercial_use_allowed=None, redistribution_allowed=False, derivative_allowed=True,
                                rationale='Market Data Terms section 2 permits internal analyses; section 3 prohibits third-party distribution. No commercial product permission inferred.'))
    (dest/'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2)+'\n')
    print(str(dest/'manifest.json'))


if __name__ == '__main__':
    main()
