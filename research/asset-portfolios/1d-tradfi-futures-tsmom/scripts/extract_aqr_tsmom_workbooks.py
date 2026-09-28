#!/usr/bin/env python3
"""Extract the frozen AQR TSMOM workbooks into auditable CSV snapshots."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd


ROOT = Path(__file__).resolve().parents[4]
ARTIFACT_DIR = ROOT / "research/asset-portfolios/1d-tradfi-futures-tsmom/artifacts"
PREFIX = "tf-1d-fut-tsmom-paper-exact-p1-2026-08-19"
SOURCES = {
    "original": {
        "url": "https://www.aqr.com/-/media/AQR/Documents/Insights/Data-Sets/Time-Series-Momentum-Original-Paper-Data.xlsx",
        "filename": f"{PREFIX}-aqr-original-paper-data.xlsx",
        "sheet": "TSMOM factors",
        "header": 10,
    },
    "updated": {
        "url": "https://www.aqr.com/-/media/AQR/Documents/Insights/Data-Sets/Time-Series-Momentum-Factors-Monthly.xlsx",
        "filename": f"{PREFIX}-aqr-updated-factors-monthly.xlsx",
        "sheet": "TSMOM Factors",
        "header": 17,
    },
}
EXPECTED = ["DATE", "TSMOM", "TSMOM^EQ", "TSMOM^FX", "TSMOM^FI", "TSMOM^CM"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def download(url: str, path: Path) -> None:
    request = Request(url, headers={"User-Agent": "quant-research-lab research"})
    with urlopen(request, timeout=60) as response:  # noqa: S310 - frozen HTTPS source
        content = response.read()
    if not content.startswith(b"PK"):
        raise RuntimeError(f"source is not an XLSX archive: {url}")
    path.write_bytes(content)


def extract(key: str, spec: dict[str, object], *, refresh: bool, force: bool) -> dict[str, object]:
    workbook = ARTIFACT_DIR / str(spec["filename"])
    if refresh or not workbook.exists():
        download(str(spec["url"]), workbook)
    raw = pd.read_excel(
        workbook,
        sheet_name=str(spec["sheet"]),
        header=int(spec["header"]),
    )
    raw = raw.rename(columns={raw.columns[0]: "DATE"})
    if set(raw.columns) != set(EXPECTED):
        raise RuntimeError(f"unexpected {key} columns: {list(raw.columns)}")
    frame = raw[EXPECTED].dropna(how="all").copy()
    frame["DATE"] = pd.to_datetime(frame["DATE"], errors="raise")
    for column in EXPECTED[1:]:
        frame[column] = pd.to_numeric(frame[column], errors="raise")
    if frame["DATE"].duplicated().any() or not frame["DATE"].is_monotonic_increasing:
        raise RuntimeError(f"invalid {key} date order")
    periods = frame["DATE"].dt.to_period("M")
    expected_periods = pd.period_range(periods.iloc[0], periods.iloc[-1], freq="M")
    missing = expected_periods.difference(pd.PeriodIndex(periods))
    if len(missing):
        raise RuntimeError(f"{key} workbook has missing months: {missing.tolist()}")
    csv_path = ARTIFACT_DIR / f"{PREFIX}-aqr-{key}-returns.csv"
    content = frame.to_csv(index=False, date_format="%Y-%m-%d")
    if csv_path.exists() and not force and csv_path.read_text(encoding="utf-8") != content:
        raise RuntimeError(f"artifact exists; pass --force: {csv_path}")
    csv_path.write_text(content, encoding="utf-8")
    return {
        "key": key,
        "url": spec["url"],
        "workbook": workbook.name,
        "workbook_sha256": sha256(workbook),
        "csv": csv_path.name,
        "csv_sha256": sha256(csv_path),
        "sheet": spec["sheet"],
        "header_row_zero_based": spec["header"],
        "rows": len(frame),
        "first_month": periods.iloc[0].strftime("%Y-%m"),
        "last_month": periods.iloc[-1].strftime("%Y-%m"),
        "missing_months": [],
        "columns": EXPECTED,
    }


def main() -> None:
    args = parse_args()
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    audits = [
        extract(key, spec, refresh=args.refresh, force=args.force)
        for key, spec in SOURCES.items()
    ]
    payload = {
        "generated_at": datetime.now(UTC).isoformat(),
        "quality_status": "official_published_factor_returns",
        "audits": audits,
    }
    audit_path = ARTIFACT_DIR / f"{PREFIX}-aqr-source-audit.json"
    audit_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
