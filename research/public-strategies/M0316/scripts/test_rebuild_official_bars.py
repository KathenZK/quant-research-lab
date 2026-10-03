"""Offline synthetic validation fixtures only. Never used as research prices."""
import argparse
import copy
import csv
import hashlib
import io
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

import rebuild_official_bars as subject


def rows():
    start = subject.ms(subject.START)
    return [[str(start + i * 14400000), "100.00000000", "110.00000000", "90.00000000",
             "105.00000000", "2.00000000", str(start + (i + 1) * 14400000 - 1),
             "200.00000000", "2", "1.00000000", "100.00000000", "0"] for i in range(186)]


def encoded(data):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream, lineterminator="\n")
    writer.writerows(data)
    return stream.getvalue().encode()


def archive(member="BTCUSDT-4h-2022-12.csv"):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr(member, encoded(rows()))
    blob = stream.getvalue()
    checksum = (hashlib.sha256(blob).hexdigest() + "  BTCUSDT-4h-2022-12.zip\n").encode()
    return blob, checksum


class QA(unittest.TestCase):
    def test_valid_and_lossless(self):
        observed, audit = subject.audit_csv(encoded(rows()), "4h", "2022-12")
        self.assertEqual(observed, rows())
        self.assertEqual(audit["rows"], 186)
        final = subject.serialize([(r, "BTCUSDT-4h-2022-12.zip") for r in observed], "4h")
        decoded = list(csv.reader(io.StringIO(final.decode())))
        self.assertEqual(decoded[0], subject.NATIVE + subject.ADDED)
        self.assertEqual(decoded[1][:12], rows()[0])
        self.assertEqual(decoded[1][12], "2022-12-01T00:00:00.000Z")
        self.assertEqual(decoded[1][19], "2022-12-01T03:59:59.999Z")

    def test_wrong_row_count(self):
        with self.assertRaisesRegex(subject.CaptureError, "COVERAGE"):
            subject.audit_csv(encoded(rows()[:-1]), "4h", "2022-12")

    def test_invalid_rows(self):
        cases = [
            (0, "1", "GRID_ORDER_GAP"), (6, "1", "CLOSE_TIME"),
            (1, "-1", "OHLC"), (2, "99", "OHLC"), (3, "106", "OHLC"),
            (4, "111", "OHLC"), (5, "-1", "VOLUME_RANGE"),
            (7, "300", "QUOTE_VOLUME_BOUNDS"), (7, "NaN", "nonfinite"),
            (8, "1.5", "trade_count"), (9, "3", "VOLUME_RANGE"),
            (10, "111.00000000", "TAKER_QUOTE_BOUNDS"), (1, " 100", "whitespace"),
            (2, "", "blank"), (1, "abc", "invalid open")]
        for field, value, error in cases:
            with self.subTest(field=field, value=value):
                data = rows(); data[0][field] = value
                with self.assertRaisesRegex(subject.CaptureError, error):
                    subject.audit_csv(encoded(data), "4h", "2022-12")

    def test_duplicate(self):
        data = rows(); data[1] = data[0].copy()
        with self.assertRaisesRegex(subject.CaptureError, "DUPLICATE"):
            subject.audit_csv(encoded(data), "4h", "2022-12")

    def test_out_of_order_no_sort(self):
        data = rows(); data[0], data[1] = data[1], data[0]
        with self.assertRaisesRegex(subject.CaptureError, "GRID_ORDER_GAP"):
            subject.audit_csv(encoded(data), "4h", "2022-12")

    def test_extra_native_column_rejected(self):
        data = rows(); data[0].append("x")
        with self.assertRaisesRegex(subject.CaptureError, "fields"):
            subject.audit_csv(encoded(data), "4h", "2022-12")

    def test_native_zero_volume_retained_and_counted(self):
        data = rows()
        for field in (5, 7, 8, 9, 10):
            data[0][field] = "0"
        observed, audit = subject.audit_csv(encoded(data), "4h", "2022-12")
        self.assertEqual(len(observed), 186)
        self.assertEqual(len(audit["zero_volume_open_times_ms"]), 1)

    def test_zero_volume_nonzero_trades(self):
        data = rows()
        for field in (5, 7, 9, 10):
            data[0][field] = "0"
        with self.assertRaisesRegex(subject.CaptureError, "VOLUME_TRADE_CONSISTENCY"):
            subject.audit_csv(encoded(data), "4h", "2022-12")

    def test_verified_zip(self):
        blob, checksum = archive()
        data, meta = subject.verify_archive(blob, checksum, "BTCUSDT-4h-2022-12.zip")
        self.assertEqual(data, encoded(rows()))
        self.assertEqual(meta["sha256"], hashlib.sha256(data).hexdigest())

    def test_changed_zip_hash(self):
        blob, checksum = archive()
        with self.assertRaisesRegex(subject.CaptureError, "MISMATCH"):
            subject.verify_archive(blob + b"x", checksum, "BTCUSDT-4h-2022-12.zip")

    def test_wrong_checksum_filename(self):
        blob, checksum = archive()
        with self.assertRaisesRegex(subject.CaptureError, "CHECKSUM_FILENAME"):
            subject.verify_archive(blob, checksum.replace(b"2022-12", b"2022-11"), "BTCUSDT-4h-2022-12.zip")

    def test_zip_path_traversal_rejected(self):
        blob, checksum = archive("../../evil.csv")
        with self.assertRaisesRegex(subject.CaptureError, "ZIP_MEMBERS"):
            subject.verify_archive(blob, checksum, "BTCUSDT-4h-2022-12.zip")

    def test_terms_guard_sends_nothing(self):
        args = argparse.Namespace(terms_reviewed=False)
        with patch.object(subject, "fetch") as fetch:
            with self.assertRaisesRegex(subject.CaptureError, "TERMS_NOT_REVIEWED"):
                subject.capture(args)
            fetch.assert_not_called()

    def test_existing_target_guard_sends_nothing(self):
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root:
            args = argparse.Namespace(terms_reviewed=True, target=root)
            with patch.object(subject, "fetch") as fetch:
                with self.assertRaisesRegex(subject.CaptureError, "TARGET_EXISTS_REFUSED"):
                    subject.capture(args)
                fetch.assert_not_called()

    def test_no_alternate_host(self):
        with self.assertRaisesRegex(subject.CaptureError, "SOURCE_REJECTED"):
            subject.fetch("https://example.com/data.zip", Path("never-created"))

    def test_rebuild_hash_mismatch(self):
        manifest = {k: "same" for k in ("protocol", "timeframe", "start_utc", "end_exclusive_utc", "builder_sha256", "schema")}
        manifest["archives"] = [{"month": "2022-12", **{k: {"sha256": "x", "bytes": 1} for k in ("zip", "checksum", "csv")}}]
        manifest["canonical_csv"] = {"sha256": "x", "bytes": 1, "rows": 1}
        subject.compare_expected(manifest, manifest)
        different = copy.deepcopy(manifest)
        different["archives"][0]["csv"]["sha256"] = "y"
        with self.assertRaisesRegex(subject.CaptureError, "MISMATCH: csv archive inventory"):
            subject.compare_expected(different, manifest)

    def test_disk_guard(self):
        with patch.object(subject.shutil, "disk_usage") as usage:
            usage.return_value.free = subject.MIN_FREE
            with self.assertRaisesRegex(subject.CaptureError, "DISK_RESERVE"):
                subject.assert_disk(Path(__file__).parent)


if __name__ == "__main__":
    unittest.main(verbosity=2)
