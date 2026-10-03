"""Synthetic only: no files containing market prices are opened."""
import hashlib
import sys
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import adapter as a


def fixture(name):
    p = a.PROFILES[name]
    rows = []
    for i in range(p.rows):
        t = a.EVAL_START + (i-p.warmup)*a.DAY
        rows.append(dict(zip(a.COLS, [str(t), '10', '12', '8', '11', '100',
            str(t+a.DAY-1), '1000', '5', '20', '200', '0'])))
    return rows


def load_synthetic(rows, name='warmup100', body=None):
    p = a.PROFILES[name]
    body = a._serialize(rows) if body is None else body
    view = a._serialize(rows[p.offset:])
    p = replace(p, size=len(body), sha256=hashlib.sha256(body).hexdigest(),
                view_size=len(view), view_sha256=hashlib.sha256(view).hexdigest())
    return a._validate_input(body, p)


def features(inp):
    return [dict(canonical_feature_index=i, open_time=int(r['open_time']),
        close_time=int(r['close_time']), close=r['close'], ready=int(i >= 19),
        raw_entry=int(i >= 19), raw_exit=0, indicator=str(i) if i >= 19 else None)
        for i, r in enumerate(inp.full_rows)]


class AdapterTests(unittest.TestCase):
    def test_both_profiles_full_projection_and_immutability(self):
        for name in a.PROFILES:
            with self.subTest(profile=name):
                inp = load_synthetic(fixture(name), name)
                f = features(inp)
                aligned = a.align_features(inp, f, required_ready_fields=('indicator',))
                self.assertEqual(len(aligned.full_features), inp.profile.rows)
                self.assertEqual(len(aligned.view_features), 762)
                self.assertEqual(aligned.view_features[31]['indicator'], str(inp.profile.warmup))
                self.assertEqual(aligned.view_features[0]['canonical_feature_index'], inp.profile.offset)
                self.assertEqual(inp.view_bytes, a._serialize(inp.view_rows))
                f[-1]['indicator'] = '999999'
                self.assertNotEqual(aligned.full_features[-1]['indicator'], '999999')
                with self.assertRaises(TypeError):
                    inp.full_rows[0]['close'] = '9'
                with self.assertRaises(TypeError):
                    aligned.full_features[0]['ready'] = 1

    def test_public_pins_fail_closed(self):
        body = a._serialize(fixture('warmup100'))
        for name in ('warmup100', 'warmup735', 'unknown', True, 100, None):
            with self.subTest(name=name), self.assertRaises(ValueError):
                a.load_input(body, name)
        with self.assertRaises(ValueError):
            a.load_input(bytearray(body), 'warmup100')

    def test_projection_prefix_future_and_decimal_identity(self):
        for name in a.PROFILES:
            inp = load_synthetic(fixture(name), name)
            f = features(inp)
            f[inp.profile.warmup]['indicator'] = Decimal('1.0000000000000000000000000000000000000000000000001')
            original = a.align_features(inp, f, required_ready_fields=('indicator',))
            f[-1]['indicator'] = '1234567'
            f[0]['indicator'] = '42'
            changed = a.align_features(inp, f, required_ready_fields=('indicator',))
            self.assertEqual(original.view_features[:-1], changed.view_features[:-1])
            self.assertNotEqual(original.full_features[0], changed.full_features[0])
            self.assertEqual(original.view_features[31]['indicator'], f[inp.profile.warmup]['indicator'])
            shifted = features(inp)
            for r in shifted: r['canonical_feature_index'] += inp.profile.offset
            with self.assertRaises(ValueError):
                a.align_features(inp, shifted, required_ready_fields=('indicator',))

    def test_byte_pins(self):
        rows = fixture('warmup100')
        inp = load_synthetic(rows)
        body = a._serialize(rows)
        for p in (replace(inp.profile, size=len(body)+1), replace(inp.profile, sha256='0'*64),
                  replace(inp.profile, view_size=1), replace(inp.profile, view_sha256='0'*64)):
            with self.subTest(profile=p), self.assertRaises(ValueError):
                a._validate_input(body, p)

    def test_input_corruptions(self):
        changes = [('open_time','0'),('close_time','0'),('open','NaN'),('close','Infinity'),
                   ('open','0'),('high','9'),('low','11'),('volume','-1'),('quote_volume','-1'),
                   ('trade_count','1.5'),('trade_count','-1'),('taker_base','101'),
                   ('taker_quote','1001'),('ignore','1'),('volume','abc')]
        for key, value in changes:
            with self.subTest(key=key,value=value):
                rows = fixture('warmup100'); rows[100][key] = value
                with self.assertRaises(ValueError): load_synthetic(rows)
        rows = fixture('warmup100')
        for body in (a._serialize(rows).replace(b'\r\n', b'\n'),
                     a._serialize(rows).replace(b'open_time', b'wrong', 1),
                     a._serialize(rows)+b'\r\n'):
            with self.subTest(encoding=True), self.assertRaises(ValueError):
                load_synthetic(rows, body=body)
        for rows in (fixture('warmup100')[:-1], fixture('warmup100')+[fixture('warmup100')[-1]]):
            with self.assertRaises(ValueError): load_synthetic(rows)

    def test_feature_rejection(self):
        inp = load_synthetic(fixture('warmup100'))
        changes = [('canonical_feature_index',True),('canonical_feature_index',0),
                   ('open_time',True),('open_time',0),('close_time',0),('close','11.0'),
                   ('ready',True),('ready',2),('raw_entry',True),('raw_entry',-1),
                   ('raw_exit',1.0),('indicator',None),('indicator','NaN'),
                   ('indicator',Decimal('Infinity')),('indicator',True),('indicator',1.0)]
        for key,value in changes:
            f = features(inp); f[100][key] = value
            with self.subTest(key=key,value=value), self.assertRaises(ValueError):
                a.align_features(inp, f, required_ready_fields=('indicator',))
        for schema in ((), ['indicator'], ('indicator','indicator'), (True,)):
            with self.assertRaises(ValueError): a.align_features(inp, features(inp), required_ready_fields=schema)
        for kind in ('short','viewonly','notready','immature','missing','missingindicator'):
            f = features(inp)
            if kind == 'short': f.pop()
            if kind == 'viewonly': f = f[69:]
            if kind == 'notready': f[100].update(ready=0,raw_entry=0)
            if kind == 'immature': f[0]['raw_entry'] = 1
            if kind == 'missing': del f[0]['close']
            if kind == 'missingindicator': del f[0]['indicator']
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                a.align_features(inp, f, required_ready_fields=('indicator',))

    def test_index_namespaces_and_pending_tail(self):
        for name,p in a.PROFILES.items():
            self.assertEqual(a.map_index(name,0,'eval'), dict(canonical_index=p.warmup,view_index=31,eval_index=0))
            self.assertEqual(a.map_index(name,0,'view'), dict(canonical_index=p.offset,view_index=0,eval_index=None))
            self.assertEqual(a.map_index(name,0,'canonical'), dict(canonical_index=0,view_index=None,eval_index=None))
            for j in range(731):
                self.assertEqual(a.map_index(name,j,'eval'), a.map_index(name,j+31,'view'))
            for lag in (1,2):
                pending = a.map_pending(name,730,730+lag,lag)
                self.assertFalse(pending['due_in_window'])
                self.assertEqual(pending['due_canonical_ordinal'], p.rows-1+lag)
            self.assertTrue(a.map_pending(name,0,1,1)['due_in_window'])
            self.assertEqual(a.map_roundtrip(name,1,730)['holding_bars'],729)
        for index,ns in ((True,'eval'),(-1,'eval'),(731,'eval'),(762,'view'),(831,'canonical'),(1,'input_index')):
            with self.assertRaises(ValueError): a.map_index('warmup100', index, ns)
        for args in ((0,2,1),(730,733,3),(True,1,1),(0,True,1),(0,1,True),(-1,0,1)):
            with self.assertRaises(ValueError): a.map_pending('warmup100',*args)
        for args in ((1,1),(2,1),(0,731),(True,2)):
            with self.assertRaises(ValueError): a.map_roundtrip('warmup100',*args)


if __name__ == '__main__':
    unittest.main(verbosity=2)
