"""Private Bit2Me OHLCV snapshots, never fabricated trusted schema columns."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

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
    raise ValueError('V3 fetcher retired: use fetch_market_v4.py with a reviewed rights artifact; a free-form audit cannot grant research use')


if __name__ == '__main__':
    main()
