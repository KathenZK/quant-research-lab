"""Offline coverage audit of issuer snapshots; never substitutes NAV for prices.

Input snapshots remain private raw_unaccepted data. Output contains only source
fingerprints and coverage diagnostics, not provider prices or corpus contents.
"""

import argparse
import datetime as dt
import hashlib
import json
import re
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path


def coverage(values: list[str], date_format: str) -> dict:
    dates = [dt.datetime.strptime(value, date_format).date() for value in values]
    if not dates:
        raise ValueError("empty date series")
    return {
        "rows": len(dates),
        "start": min(dates).isoformat(),
        "end": max(dates).isoformat(),
        "duplicate_dates": len(dates) - len(set(dates)),
    }


def audit(root: Path) -> dict:
    result = {"strategy_id": "M0004", "status": "BLOCKED_DATA", "backtest_runs": 0}
    sources = {}
    ns = {"s": "urn:schemas-microsoft-com:office:spreadsheet"}
    for ticker in ("efa", "ief", "gsg"):
        path = root / f"{ticker}-download.response"
        raw = path.read_bytes()
        # The issuer export has bare ampersands in disclaimers. Repair only the
        # parsing view; fingerprint and retain the exact original bytes.
        clean, repairs = re.subn(
            r"&(?!amp;|lt;|gt;|quot;|apos;|#[0-9]+;|#x[0-9a-fA-F]+;)",
            "&amp;",
            raw.decode(),
        )
        tree = ET.fromstring(clean)
        sheets = [
            sheet for sheet in tree.findall("s:Worksheet", ns)
            if sheet.get("{" + ns["s"] + "}Name") == "Historical"
        ]
        if len(sheets) != 1:
            raise ValueError(f"{ticker}: ambiguous Historical worksheet")
        rows = [
            [cell.text for cell in row.findall("s:Cell/s:Data", ns)]
            for row in sheets[0].findall("s:Table/s:Row", ns)
        ]
        if rows[0][:3] != ["As Of", "NAV per Share", "Ex-Dividends"]:
            raise ValueError(f"{ticker}: unexpected schema")
        sources[ticker.upper()] = {
            **coverage([row[0] for row in rows[1:]], "%b %d, %Y"),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "fields": rows[0], "parser_ampersand_repairs": repairs,
            "market_price_available": False,
        }

    path = root / "ssga-spy-nav.response"
    with zipfile.ZipFile(path) as archive:
        ns = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        strings = [
            "".join(item.itertext())
            for item in ET.fromstring(archive.read("xl/sharedStrings.xml"))
        ]
        sheet = ET.fromstring(archive.read("xl/worksheets/sheet1.xml"))
        dates = []
        for row in sheet.findall("s:sheetData/s:row", ns):
            cells = row.findall("s:c", ns)
            if not cells:
                continue
            cell = cells[0]
            value = cell.find("s:v", ns)
            if value is None:
                continue
            text = strings[int(value.text)] if cell.get("t") == "s" else value.text
            if re.fullmatch(r"\d{2}-[A-Za-z]{3}-\d{4}", text):
                dates.append(text)
    sources["SPY"] = {
        **coverage(dates, "%d-%b-%Y"),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "market_price_available": False, "distributions_in_snapshot": False,
    }
    path = root / "vnq-additional.response"
    history = json.loads(path.read_bytes())["historicalPrice"]
    sources["VNQ"] = {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "daily_1Y": coverage([x["asOfDate"] for x in history["1Y"]["nav"]], "%m/%d/%Y"),
        "monthly_10Y": coverage([x["asOfDate"] for x in history["10Y"]["nav"]], "%m/%d/%Y"),
        "market_price_available": False,
        "daily_252_roc_minimum_observations": 253,
    }
    result["sources"] = sources
    result["limits"] = [
        "Coverage audit only: no session-calendar, corporate-action or PIT acceptance.",
        "NAV is not an executable ETF market price; no OHLCV fields fabricated.",
        "Monthly observations cannot satisfy a 252-trading-observation ROC.",
        "Current issuer revisions do not prove historical publication timestamps.",
    ]
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshot_directory", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.snapshot_directory), ensure_ascii=False, indent=2))
