#!/usr/bin/env python3
"""Offline synthetic boundary tests; never fetches data or computes returns.
SPDX-License-Identifier: GPL-3.0-or-later
"""
import csv,hashlib,importlib.util,io,unittest,zipfile
from pathlib import Path
spec=importlib.util.spec_from_file_location('native_builder',Path(__file__).with_name('rebuild_native12h.py'))
b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b)
class Guards(unittest.TestCase):
 def rows(self):
  start=b.ms(b.START)
  return [[str(start+i*43200000),'100','110','90','105','2',str(start+(i+1)*43200000-1),'200','2','1','100','0'] for i in range(62)]
 def data(self,rows):
  f=io.StringIO();csv.writer(f,lineterminator='\n').writerows(rows);return f.getvalue().encode()
 def reject(self,mutate):
  rows=self.rows();mutate(rows)
  with self.assertRaises(b.CaptureError):b.audit_csv(self.data(rows),'12h','2022-12')
 def test_valid_synthetic_month(self):self.assertEqual(b.audit_csv(self.data(self.rows()),'12h','2022-12')[1]['rows'],62)
 def test_wrong_timeframe(self):
  with self.assertRaises(b.CaptureError):b.audit_csv(self.data(self.rows()),'4h','2022-12')
 def test_missing_bar(self):self.reject(lambda r:r.pop())
 def test_duplicate(self):self.reject(lambda r:r.__setitem__(1,r[0].copy()))
 def test_order(self):self.reject(lambda r:r.__setitem__(slice(0,2),[r[1],r[0]]))
 def test_bad_close(self):self.reject(lambda r:r[0].__setitem__(6,str(int(r[0][6])+1)))
 def test_microsecond_unexpected(self):self.reject(lambda r:r[0].__setitem__(0,str(int(r[0][0])*1000)))
 def test_missing_native_field(self):self.reject(lambda r:r[0].pop())
 def test_negative_volume(self):self.reject(lambda r:r[0].__setitem__(5,'-1'))
 def test_nonfinite(self):self.reject(lambda r:r[0].__setitem__(1,'NaN'))
 def test_price_bounds(self):self.reject(lambda r:r[0].__setitem__(1,'200'))
 def test_quote_bounds(self):self.reject(lambda r:r[0].__setitem__(7,'1000'))
 def test_bad_trade_zero(self):self.reject(lambda r:r[0].__setitem__(8,'0'))
 def archive(self,member):
  o=io.BytesIO()
  with zipfile.ZipFile(o,'w') as z:z.writestr(member,self.data(self.rows()))
  return o.getvalue()
 def test_valid_zip(self):
  fn='BTCUSDT-12h-2022-12.zip';data=self.archive(fn[:-4]+'.csv');check=f'{hashlib.sha256(data).hexdigest()}  {fn}\n'.encode()
  self.assertEqual(b.verify_archive(data,check,fn)[0],self.data(self.rows()))
 def test_bad_checksum(self):
  fn='BTCUSDT-12h-2022-12.zip';data=self.archive(fn[:-4]+'.csv')
  with self.assertRaises(b.CaptureError):b.verify_archive(data,f'{"0"*64}  {fn}\n'.encode(),fn)
 def test_wrong_zip_member(self):
  fn='BTCUSDT-12h-2022-12.zip';data=self.archive('unexpected.csv');check=f'{hashlib.sha256(data).hexdigest()}  {fn}\n'.encode()
  with self.assertRaises(b.CaptureError):b.verify_archive(data,check,fn)
if __name__=='__main__':unittest.main(verbosity=2)
