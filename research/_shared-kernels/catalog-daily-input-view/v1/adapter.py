"""Pinned canonical daily input and feature projection; no indicators or accounting."""
import csv
import hashlib
import io
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from types import MappingProxyType
from collections.abc import Mapping

DAY = 86400000
EVAL_START = 1672531200000
VIEW_START = 1669852800000
END = 1735689600000
COLS = ('open_time', 'open', 'high', 'low', 'close', 'volume', 'close_time',
        'quote_volume', 'trade_count', 'taker_base', 'taker_quote', 'ignore')


def require(condition, message):
    if not condition:
        raise ValueError(message)


def integer(value, name, low, high):
    require(type(value) is int and low <= value <= high, name)
    return value


def number(value, name):
    require(type(value) in (str, Decimal), name)
    try:
        n = Decimal(value)
    except InvalidOperation as exc:
        raise ValueError(name) from exc
    require(n.is_finite(), name)
    return n


@dataclass(frozen=True)
class Profile:
    name: str
    rows: int
    warmup: int
    offset: int
    size: int
    sha256: str
    view_size: int = 128196
    view_sha256: str = '48e4e785ee3366a459cf09f64617c89e04fb19b91da6c6125e86835506f6b9f5'


PROFILES = MappingProxyType({
    'warmup100': Profile('warmup100', 831, 100, 69, 139983,
        'a21612759ddd7e849f4a5e5b3ac62f74b003c84bf9e0e77d45ab8670b59eb550'),
    'warmup735': Profile('warmup735', 1466, 735, 704, 247171,
        'db05acd35ad9f09d08a3a2126fc0aba62c40ba12a90eef2faa00af0d3cd7ae26'),
})


@dataclass(frozen=True)
class InputView:
    profile: Profile
    full_rows: tuple
    view_rows: tuple
    view_bytes: bytes


@dataclass(frozen=True)
class FeatureView:
    full_features: tuple
    view_features: tuple
    required_ready_fields: tuple


def _serialize(rows):
    s = io.StringIO(newline='')
    w = csv.DictWriter(s, fieldnames=COLS)
    w.writeheader()
    w.writerows(rows)
    return s.getvalue().encode('utf-8')


def _validate_input(body, p):
    """Internal structural implementation; synthetic tests replace only byte pins."""
    require(type(body) is bytes, 'input must be bytes')
    require(len(body) == p.size and hashlib.sha256(body).hexdigest() == p.sha256,
            'canonical byte identity')
    require((p.rows, p.warmup, p.offset) in ((831, 100, 69), (1466, 735, 704)),
            'fixed profile dimensions')
    reader = csv.DictReader(io.StringIO(body.decode('utf-8'), newline=''))
    require(reader.fieldnames == list(COLS), 'CSV header')
    rows = list(reader)
    require(len(rows) == p.rows, 'canonical row count')
    for i, r in enumerate(rows):
        require(set(r) == set(COLS) and all(type(v) is str for v in r.values()), 'CSV width')
        start = EVAL_START - p.warmup * DAY + i * DAY
        require(r['open_time'] == str(start) and r['close_time'] == str(start + DAY - 1), 'UTC grid')
        n = {k: number(r[k], k) for k in COLS if k not in ('open_time', 'close_time')}
        require(all(n[k] > 0 for k in ('open', 'high', 'low', 'close')), 'positive OHLC')
        require(n['low'] <= min(n['open'], n['close']) <= max(n['open'], n['close']) <= n['high'], 'OHLC bounds')
        require(all(n[k] >= 0 for k in ('volume', 'quote_volume', 'trade_count', 'taker_base', 'taker_quote')), 'nonnegative volume')
        require(r['trade_count'].isascii() and r['trade_count'].isdigit(), 'integer trade count')
        require(n['taker_base'] <= n['volume'] and n['taker_quote'] <= n['quote_volume'], 'taker bounds')
        require(n['ignore'] == 0, 'ignore field')
    require(_serialize(rows) == body, 'canonical CSV encoding / CRLF')
    view = rows[p.offset:]
    vbytes = _serialize(view)
    require(len(view) == 762 and view[0]['open_time'] == str(VIEW_START), 'view start')
    require(view[31]['open_time'] == str(EVAL_START) and int(view[-1]['close_time']) + 1 == END, 'evaluation bounds')
    require(len(vbytes) == p.view_size and hashlib.sha256(vbytes).hexdigest() == p.view_sha256, 'view byte identity')
    full = tuple(MappingProxyType(r) for r in rows)
    return InputView(p, full, full[p.offset:], vbytes)


def load_input(body, profile_name):
    """Production entry: only the two frozen canonical byte identities are accepted."""
    require(type(profile_name) is str and profile_name in PROFILES, 'unknown profile')
    return _validate_input(body, PROFILES[profile_name])


def _freeze(value):
    if isinstance(value, Mapping):
        require(all(type(k) is str for k in value), 'feature keys')
        return MappingProxyType({k: _freeze(v) for k, v in value.items()})
    if type(value) in (tuple, list):
        return tuple(_freeze(v) for v in value)
    require(value is None or type(value) in (str, int, Decimal), 'feature value type (no bool/float)')
    if type(value) is Decimal:
        require(value.is_finite(), 'finite feature Decimal')
    return value


def align_features(input_view, full_features, *, required_ready_fields):
    """Validate full canonical trace, then project without modifying indicator values."""
    require(type(input_view) is InputView, 'InputView required')
    require(type(full_features) in (list, tuple), 'full feature sequence')
    require(type(required_ready_fields) is tuple and len(required_ready_fields) > 0
            and all(type(k) is str and k for k in required_ready_fields)
            and len(set(required_ready_fields)) == len(required_ready_fields), 'ready field schema')
    require(len(full_features) == input_view.profile.rows, 'full canonical feature length')
    result = []
    for i, (r, f) in enumerate(zip(input_view.full_rows, full_features)):
        require(isinstance(f, Mapping), 'feature record')
        for key in ('canonical_feature_index', 'open_time', 'close_time', 'close', 'ready', 'raw_entry', 'raw_exit'):
            require(key in f, 'missing feature ' + key)
        integer(f['canonical_feature_index'], 'canonical feature index', i, i)
        integer(f['open_time'], 'feature open time', int(r['open_time']), int(r['open_time']))
        integer(f['close_time'], 'feature close time', int(r['close_time']), int(r['close_time']))
        require(type(f['close']) is str and f['close'] == r['close'], 'feature close identity')
        for k in ('ready', 'raw_entry', 'raw_exit'):
            integer(f[k], k, 0, 1)
        require(f['ready'] == 1 or (f['raw_entry'] == 0 and f['raw_exit'] == 0), 'immature signal')
        require(i < input_view.profile.warmup or f['ready'] == 1, 'evaluation feature not ready')
        for key in required_ready_fields:
            require(key in f, 'missing readiness field ' + key)
            if f['ready']:
                number(f[key], 'ready ' + key)
        result.append(_freeze(f))
    full = tuple(result)
    return FeatureView(full, full[input_view.profile.offset:], required_ready_fields)


def map_index(profile_name, index, namespace):
    """Map actual bars only; eval_index is None for canonical warmup bars."""
    require(type(profile_name) is str and profile_name in PROFILES, 'unknown profile')
    p = PROFILES[profile_name]
    require(type(namespace) is str and namespace in ('canonical', 'view', 'eval'), 'index namespace')
    if namespace == 'canonical':
        c = integer(index, 'canonical index', 0, p.rows - 1)
    elif namespace == 'view':
        c = integer(index, 'view index', 0, 761) + p.offset
    else:
        c = integer(index, 'eval index', 0, 730) + p.warmup
    return dict(canonical_index=c, view_index=c-p.offset if c >= p.offset else None,
                eval_index=c-p.warmup if c >= p.warmup else None)


def map_pending(profile_name, signal_index, due_index, delay_bars):
    """Pending indices belong to evaluation namespace, including unfilled future ordinals."""
    signal = map_index(profile_name, signal_index, 'eval')
    integer(delay_bars, 'delay bars', 1, 2)
    integer(due_index, 'due index', signal_index + delay_bars, signal_index + delay_bars)
    p = PROFILES[profile_name]
    return dict(signal=signal, due_eval_ordinal=due_index,
                due_view_ordinal=due_index + 31, due_canonical_ordinal=due_index + p.warmup,
                due_in_window=due_index < 731)


def map_roundtrip(profile_name, entry_index, exit_index):
    entry = map_index(profile_name, entry_index, 'eval')
    exit_ = map_index(profile_name, exit_index, 'eval')
    require(exit_index > entry_index, 'roundtrip ordering')
    return dict(entry=entry, exit=exit_, holding_bars=exit_index-entry_index)
