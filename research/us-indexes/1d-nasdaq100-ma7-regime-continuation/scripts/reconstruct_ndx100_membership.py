from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import re
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import exchange_calendars as xcals
import pandas as pd


FAMILY_DIR = Path(__file__).resolve().parents[1]
CONFIG_DIR = FAMILY_DIR / "configs"
ARTIFACT_DIR = FAMILY_DIR / "artifacts"
SOURCE_DIR = ARTIFACT_DIR / "membership-sources"
OVERRIDE_PATH = CONFIG_DIR / "ndx100-membership-overrides.json"
STUDY_CONFIG_PATH = CONFIG_DIR / "ndx100-1d-ma7-regime-continuation-p0.json"

HISTORY_TITLE = "Historical_components_of_the_Nasdaq-100"
CURRENT_TITLE = "List_of_NASDAQ-100_companies"
WIKI_API = "https://en.wikipedia.org/w/api.php"
USER_AGENT = "quant-research-lab-ndx100-membership/1.0"
OFFICIAL_DOMAINS = (
    "nasdaq.com",
    "nasdaqomx.com",
    "nasdaqtrader.com",
    "sec.gov",
)

HISTORY_SOURCE_PATH = SOURCE_DIR / "historical_components.wikitext"
CURRENT_SOURCE_PATH = SOURCE_DIR / "current_components.wikitext"
SOURCE_MANIFEST_PATH = SOURCE_DIR / "source_manifest.json"
CHANGE_LOG_PATH = ARTIFACT_DIR / "ndx100_1d_ma7_rc_p0_membership_change_log.csv"
SNAPSHOT_PATH = ARTIFACT_DIR / "ndx100_1d_ma7_rc_p0_membership_snapshots.csv"
INTERVAL_PATH = ARTIFACT_DIR / "ndx100_1d_ma7_rc_p0_membership_intervals.csv"
DAILY_PATH = ARTIFACT_DIR / "ndx100_1d_ma7_rc_p0_membership_daily.parquet"
AUDIT_PATH = ARTIFACT_DIR / "ndx100_1d_ma7_rc_p0_membership_audit.json"
ARTIFACT_MANIFEST_PATH = (
    ARTIFACT_DIR / "ndx100_1d_ma7_rc_p0_membership_artifact_manifest.json"
)

_REF_PAIR = re.compile(r"<ref\b[^>]*>.*?</ref\s*>", re.IGNORECASE | re.DOTALL)
_REF_SELF = re.compile(r"<ref\b[^>]*/\s*>", re.IGNORECASE)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_TEMPLATE = re.compile(r"\{\{[^{}]*\}\}")
_WIKILINK = re.compile(r"\[\[(?:[^\]|]*\|)?([^\]|]+)\]\]")
_URL = re.compile(r"https?://[^\s|}\]<>]+")
_NAMED_REF_DEFINITION = re.compile(
    r"<ref\s+name\s*=\s*[\"']?([^\"'\s>/]+)[\"']?\s*>(.*?)</ref\s*>",
    re.IGNORECASE | re.DOTALL,
)
_NAMED_REF_USE = re.compile(
    r"<ref\s+name\s*=\s*[\"']?([^\"'\s>/]+)[\"']?\s*/\s*>",
    re.IGNORECASE,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh-sources", action="store_true")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def sha256_bytes(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def request_bytes(url: str) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def mediawiki_page(title: str) -> tuple[bytes, dict[str, Any]]:
    params = urllib.parse.urlencode(
        {
            "action": "query",
            "prop": "revisions",
            "rvprop": "ids|timestamp|content",
            "rvslots": "main",
            "titles": title,
            "format": "json",
            "formatversion": "2",
        }
    )
    payload = json.loads(request_bytes(f"{WIKI_API}?{params}"))
    page = payload["query"]["pages"][0]
    revision = page["revisions"][0]
    content = revision["slots"]["main"]["content"].encode("utf-8")
    metadata = {
        "title": page["title"],
        "page_id": int(page["pageid"]),
        "revision_id": int(revision["revid"]),
        "parent_revision_id": int(revision["parentid"]),
        "revision_timestamp_utc": revision["timestamp"],
        "api_url": f"{WIKI_API}?{params}",
        "article_url": "https://en.wikipedia.org/wiki/" + title,
        "license": "CC BY-SA 4.0",
    }
    return content, metadata


def refresh_sources(*, force: bool) -> dict[str, Any]:
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    if SOURCE_MANIFEST_PATH.exists() and not force:
        raise FileExistsError(f"source manifest exists: {SOURCE_MANIFEST_PATH}")
    history, history_meta = mediawiki_page(HISTORY_TITLE)
    current, current_meta = mediawiki_page(CURRENT_TITLE)
    HISTORY_SOURCE_PATH.write_bytes(history)
    CURRENT_SOURCE_PATH.write_bytes(current)
    history_meta.update(
        {
            "local_path": str(HISTORY_SOURCE_PATH.relative_to(FAMILY_DIR)),
            "bytes": len(history),
            "sha256": sha256_bytes(history),
        }
    )
    current_meta.update(
        {
            "local_path": str(CURRENT_SOURCE_PATH.relative_to(FAMILY_DIR)),
            "bytes": len(current),
            "sha256": sha256_bytes(current),
        }
    )
    manifest = {
        "retrieved_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "attribution": (
            "Revision-pinned source snapshots from Wikipedia are retained under "
            "CC BY-SA 4.0. Row-level citations in the historical table are parsed "
            "and official Nasdaq/SEC sources are preferred in the audit."
        ),
        "sources": [history_meta, current_meta],
    }
    SOURCE_MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return manifest


def table_text(wikitext: str, table_id: str) -> str:
    start_match = re.search(
        rf"^\{{\|[^\n]*\bid=[\"']{re.escape(table_id)}[\"'][^\n]*$",
        wikitext,
        flags=re.MULTILINE,
    )
    if not start_match:
        raise ValueError(f"table id={table_id!r} not found")
    end_match = re.search(r"^\|}\s*$", wikitext[start_match.end() :], re.MULTILINE)
    if not end_match:
        raise ValueError(f"table id={table_id!r} has no closing marker")
    end = start_match.end() + end_match.end()
    return wikitext[start_match.start() : end]


def row_cells(row: str) -> list[str]:
    cells: list[str] = []
    current: list[str] = []
    for line in row.splitlines():
        stripped = line.lstrip()
        if stripped.startswith("|") and not stripped.startswith(("|-", "|}")):
            if current:
                cells.append("\n".join(current).strip())
            current = [stripped[1:].strip()]
        elif current:
            current.append(line.strip())
    if current:
        cells.append("\n".join(current).strip())
    return cells


def plain_text(value: str) -> str:
    value = _REF_SELF.sub("", value)
    value = _REF_PAIR.sub("", value)
    value = _COMMENT.sub("", value)
    previous = None
    while previous != value:
        previous = value
        value = _TEMPLATE.sub("", value)
    value = _WIKILINK.sub(r"\1", value)
    value = value.replace("'''", "").replace("''", "")
    return re.sub(r"\s+", " ", value).strip()


def parse_us_date(value: str) -> dt.date | None:
    cleaned = plain_text(value)
    for fmt in ("%B %d, %Y", "%b %d, %Y"):
        try:
            return dt.datetime.strptime(cleaned, fmt).date()
        except ValueError:
            pass
    return None


def ticker(value: str) -> str:
    cleaned = plain_text(value).upper()
    match = re.match(r"[A-Z0-9.\-]+", cleaned)
    return match.group(0) if match else ""


def named_reference_definitions(wikitext: str) -> dict[str, str]:
    return {match.group(1): match.group(2) for match in _NAMED_REF_DEFINITION.finditer(wikitext)}


def source_urls(raw_reason: str, references: dict[str, str]) -> list[str]:
    material = [raw_reason]
    material.extend(
        references[name]
        for name in _NAMED_REF_USE.findall(raw_reason)
        if name in references
    )
    urls = []
    for value in material:
        urls.extend(url.rstrip(".,;") for url in _URL.findall(value))
    return list(dict.fromkeys(urls))


def source_tier(urls: Iterable[str]) -> str:
    parsed = [urllib.parse.urlparse(url).netloc.lower().split(":")[0] for url in urls]
    if any(
        domain == official or domain.endswith("." + official)
        for domain in parsed
        for official in OFFICIAL_DOMAINS
    ):
        return "primary_official"
    if parsed:
        return "secondary_cited"
    return "uncited_secondary_index"


def parse_change_rows(wikitext: str) -> list[dict[str, Any]]:
    references = named_reference_definitions(wikitext)
    rows: list[dict[str, Any]] = []
    table = table_text(wikitext, "changes")
    for ordinal, raw_row in enumerate(re.split(r"(?m)^\s*\|-.*$", table), start=1):
        cells = row_cells(raw_row)
        if len(cells) < 6:
            continue
        effective_date = parse_us_date(cells[0])
        if effective_date is None:
            continue
        urls = source_urls(cells[5], references)
        rows.append(
            {
                "source_row_ordinal": ordinal,
                "effective_date": effective_date,
                "added_ticker_raw": ticker(cells[1]),
                "added_security": plain_text(cells[2]),
                "removed_ticker_raw": ticker(cells[3]),
                "removed_security": plain_text(cells[4]),
                "reason": plain_text(cells[5]),
                "source_urls": urls,
                "source_tier": source_tier(urls),
                "manual_override": False,
                "source_augmentation": False,
            }
        )
    if not rows:
        raise RuntimeError("no Nasdaq-100 membership change rows parsed")
    return rows


def parse_current_tickers(wikitext: str) -> set[str]:
    table = table_text(wikitext, "constituents")
    result = set(
        re.findall(r"(?m)^\|\s*([A-Z][A-Z0-9.\-]*)\s*\|\|", table)
    )
    if len(result) < 90:
        raise RuntimeError(f"only {len(result)} current component securities parsed")
    return result


def apply_manual_overrides(
    rows: list[dict[str, Any]], overrides: dict[str, Any]
) -> list[dict[str, Any]]:
    corrected = [dict(row) for row in rows]
    for correction in overrides["change_corrections"]:
        date = dt.date.fromisoformat(correction["effective_date"])
        field = correction["field"] + "_raw"
        matches = [
            row
            for row in corrected
            if row["effective_date"] == date and row.get(field) == correction["from"]
        ]
        if len(matches) != 1:
            raise RuntimeError(f"manual correction expected one row, found {len(matches)}: {correction}")
        matches[0][field] = correction["to"]
        matches[0]["source_urls"] = list(
            dict.fromkeys(matches[0]["source_urls"] + [correction["source_url"]])
        )
        matches[0]["source_tier"] = source_tier(matches[0]["source_urls"])
        matches[0]["manual_override"] = True
        matches[0]["override_note"] = correction["reason"]

    for drop in overrides["drop_change_rows"]:
        date = dt.date.fromisoformat(drop["effective_date"])
        before = len(corrected)
        corrected = [
            row
            for row in corrected
            if not (
                row["effective_date"] == date
                and row["added_ticker_raw"] == drop["added_ticker"]
                and row["removed_ticker_raw"] == drop["removed_ticker"]
            )
        ]
        if len(corrected) != before - 1:
            raise RuntimeError(f"manual drop expected one row: {drop}")

    for augmentation in overrides.get("source_augmentations", []):
        date = dt.date.fromisoformat(augmentation["effective_date"])
        matches = [
            row
            for row in corrected
            if row["effective_date"] == date
            and row["added_ticker_raw"] == augmentation["added_ticker"]
            and row["removed_ticker_raw"] == augmentation["removed_ticker"]
        ]
        if len(matches) != 1:
            raise RuntimeError(
                f"source augmentation expected one row, found {len(matches)}: {augmentation}"
            )
        matches[0]["source_urls"] = list(
            dict.fromkeys(matches[0]["source_urls"] + [augmentation["source_url"]])
        )
        matches[0]["source_tier"] = source_tier(matches[0]["source_urls"])
        matches[0]["source_augmentation"] = True
        matches[0]["override_note"] = augmentation["reason"]

    next_ordinal = max(row["source_row_ordinal"] for row in corrected) + 1
    for synthetic in overrides["synthetic_changes"]:
        urls = [synthetic["source_url"]]
        corrected.append(
            {
                "source_row_ordinal": next_ordinal,
                "effective_date": dt.date.fromisoformat(synthetic["effective_date"]),
                "added_ticker_raw": synthetic["added_ticker"],
                "added_security": "",
                "removed_ticker_raw": synthetic["removed_ticker"],
                "removed_security": "",
                "reason": synthetic["reason"],
                "source_urls": urls,
                "source_tier": source_tier(urls),
                "manual_override": True,
                "source_augmentation": False,
                "override_note": synthetic["reason"],
            }
        )
        next_ordinal += 1
    return sorted(corrected, key=lambda row: (row["effective_date"], row["source_row_ordinal"]))


def canonical_symbol(value: str, aliases: dict[str, str]) -> str:
    return aliases.get(value, value)


def normalized_changes(
    rows: list[dict[str, Any]], overrides: dict[str, Any]
) -> list[dict[str, Any]]:
    aliases = overrides["canonical_aliases"]
    output = []
    for row in rows:
        item = dict(row)
        item["added_ticker"] = canonical_symbol(item["added_ticker_raw"], aliases)
        item["removed_ticker"] = canonical_symbol(item["removed_ticker_raw"], aliases)
        output.append(item)
    return output


def grouped_changes(rows: list[dict[str, Any]]) -> list[tuple[dt.date, set[str], set[str]]]:
    grouped: dict[dt.date, tuple[set[str], set[str]]] = defaultdict(lambda: (set(), set()))
    for row in rows:
        added, removed = grouped[row["effective_date"]]
        if row["added_ticker"]:
            added.add(row["added_ticker"])
        if row["removed_ticker"]:
            removed.add(row["removed_ticker"])
    return [(date, *grouped[date]) for date in sorted(grouped)]


def insert_carry_snapshot(
    snapshots: dict[dt.date, set[str]], effective_date: dt.date
) -> None:
    if effective_date in snapshots:
        return
    prior = [date for date in snapshots if date < effective_date]
    if prior:
        snapshots[effective_date] = set(snapshots[max(prior)])


def reconstruct_canonical_snapshots(
    current: set[str], changes: list[tuple[dt.date, set[str], set[str]]]
) -> tuple[dict[dt.date, set[str]], list[dict[str, Any]]]:
    state = set(current)
    descending: dict[dt.date, set[str]] = {}
    integrity: list[dict[str, Any]] = []
    for effective_date, added, removed in reversed(changes):
        descending[effective_date] = set(state)
        for symbol in sorted(added - removed):
            if symbol not in state:
                integrity.append(
                    {
                        "effective_date": effective_date.isoformat(),
                        "issue": "addition_not_present_in_forward_state",
                        "ticker": symbol,
                    }
                )
        for symbol in sorted(removed - added):
            if symbol in state:
                integrity.append(
                    {
                        "effective_date": effective_date.isoformat(),
                        "issue": "removal_still_present_in_forward_state",
                        "ticker": symbol,
                    }
                )
        state = (state - added) | removed
    return dict(sorted(descending.items())), integrity


def rename_records(overrides: dict[str, Any]) -> list[dict[str, Any]]:
    records = []
    aliases = overrides["canonical_aliases"]
    for record in overrides["ticker_renames"]:
        item = dict(record)
        item["effective_date"] = dt.date.fromisoformat(item["effective_date"])
        item["canonical_ticker"] = canonical_symbol(item["new_ticker"], aliases)
        records.append(item)
    return records


def display_symbol(
    canonical: str,
    effective_date: dt.date,
    renames: list[dict[str, Any]],
    google_split: dict[str, Any],
) -> str:
    google_date = dt.date.fromisoformat(google_split["effective_date"])
    if canonical == "GOOGL" and effective_date < google_date:
        return google_split["pre_split_display_ticker"]
    for record in renames:
        if canonical == record["canonical_ticker"]:
            return record["new_ticker"] if effective_date >= record["effective_date"] else record["old_ticker"]
    return canonical


def entity_key(
    display: str,
    effective_date: dt.date,
    overrides: dict[str, Any],
) -> str:
    for record in overrides["special_security_generations"]:
        if display == record["ticker"]:
            boundary = dt.date.fromisoformat(record["before_date"])
            return (
                record["before_entity_key"]
                if effective_date < boundary
                else record["on_or_after_entity_key"]
            )
    google = overrides["google_class_a_split"]
    google_date = dt.date.fromisoformat(google["effective_date"])
    if display == "GOOGL":
        return google["canonical_entity_key"]
    if display == "GOOG":
        return "ALPHABET_CLASS_A" if effective_date < google_date else "ALPHABET_CLASS_C"
    for record in overrides["ticker_renames"]:
        if display in {record["old_ticker"], record["new_ticker"]}:
            return record["entity_key"]
    return display


def display_snapshots(
    canonical_snapshots: dict[dt.date, set[str]], overrides: dict[str, Any]
) -> dict[dt.date, dict[str, str]]:
    renames = rename_records(overrides)
    carry_dates = [record["effective_date"] for record in renames]
    carry_dates.append(dt.date.fromisoformat(overrides["google_class_a_split"]["effective_date"]))
    carry_dates.extend(
        dt.date.fromisoformat(record["before_date"])
        for record in overrides["special_security_generations"]
    )
    for date in carry_dates:
        insert_carry_snapshot(canonical_snapshots, date)
    output: dict[dt.date, dict[str, str]] = {}
    for date, members in sorted(canonical_snapshots.items()):
        mapped: dict[str, str] = {}
        for canonical in sorted(members):
            shown = display_symbol(
                canonical, date, renames, overrides["google_class_a_split"]
            )
            key = entity_key(shown, date, overrides)
            if shown in mapped and mapped[shown] != key:
                raise RuntimeError(f"display ticker collision on {date}: {shown}")
            mapped[shown] = key
        output[date] = mapped
    return output


def next_xnas_session_date(calendar: Any, date: dt.date) -> dt.date:
    sessions = calendar.sessions_in_range(
        pd.Timestamp(date), pd.Timestamp(date + dt.timedelta(days=10))
    )
    return sessions[0].date() if sessions[0].date() > date else sessions[1].date()


def snapshot_rows(snapshots: dict[dt.date, dict[str, str]]) -> pd.DataFrame:
    rows = []
    for date, members in sorted(snapshots.items()):
        rows.append(
            {
                "effective_date": date.isoformat(),
                "security_count": len(members),
                "entity_count": len(set(members.values())),
                "tickers": ",".join(sorted(members)),
                "entity_keys": ",".join(f"{ticker}:{members[ticker]}" for ticker in sorted(members)),
            }
        )
    return pd.DataFrame(rows)


def build_daily_membership(
    snapshots: dict[dt.date, dict[str, str]],
    start: dt.date,
    end: dt.date,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    calendar = xcals.get_calendar("XNAS")
    sessions = [
        session.date()
        for session in calendar.sessions_in_range(
            pd.Timestamp(start), pd.Timestamp(end)
        )
    ]
    snapshot_dates = sorted(snapshots)
    state_by_session: list[tuple[dt.date, dict[str, str]]] = []
    pointer = 0
    current: dict[str, str] | None = None
    for session in sessions:
        while pointer < len(snapshot_dates) and snapshot_dates[pointer] <= session:
            current = snapshots[snapshot_dates[pointer]]
            pointer += 1
        if current is None:
            raise RuntimeError(f"no membership snapshot available for {session}")
        state_by_session.append((session, current))

    entity_start: dict[str, dt.date] = {}
    previous_entities: set[str] = set()
    daily_rows: list[dict[str, Any]] = []
    for session, members in state_by_session:
        entities = set(members.values())
        for key in entities - previous_entities:
            entity_start[key] = session
        for key in previous_entities - entities:
            entity_start.pop(key, None)
        for display, key in sorted(members.items()):
            daily_rows.append(
                {
                    "session_date": session,
                    "ticker": display,
                    "entity_key": key,
                    "membership_interval_start": entity_start[key],
                }
            )
        previous_entities = entities
    daily = pd.DataFrame(daily_rows)

    interval_rows: list[dict[str, Any]] = []
    for (ticker_value, key), group in daily.groupby(["ticker", "entity_key"], sort=True):
        dates = sorted(group["session_date"].unique())
        previous = None
        block_start = None
        calendar_sessions = {date: index for index, date in enumerate(sessions)}
        for date in dates:
            if previous is None or calendar_sessions[date] != calendar_sessions[previous] + 1:
                if previous is not None and block_start is not None:
                    interval_rows.append(
                        {
                            "ticker": ticker_value,
                            "entity_key": key,
                            "start_session": block_start,
                            "end_session_inclusive": previous,
                        }
                    )
                block_start = date
            previous = date
        if previous is not None and block_start is not None:
            interval_rows.append(
                {
                    "ticker": ticker_value,
                    "entity_key": key,
                    "start_session": block_start,
                    "end_session_inclusive": previous,
                }
            )
    intervals = pd.DataFrame(interval_rows).sort_values(
        ["start_session", "ticker", "entity_key"]
    )
    return daily, intervals


def write_change_log(rows: list[dict[str, Any]]) -> None:
    fields = [
        "effective_date",
        "added_ticker_raw",
        "added_ticker",
        "added_security",
        "removed_ticker_raw",
        "removed_ticker",
        "removed_security",
        "reason",
        "source_tier",
        "source_urls",
        "manual_override",
        "source_augmentation",
        "override_note",
        "source_row_ordinal",
    ]
    with CHANGE_LOG_PATH.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            serial = dict(row)
            serial["effective_date"] = row["effective_date"].isoformat()
            serial["source_urls"] = ";".join(row["source_urls"])
            writer.writerow({field: serial.get(field, "") for field in fields})


def build_membership(*, force: bool) -> dict[str, Any]:
    for path in (HISTORY_SOURCE_PATH, CURRENT_SOURCE_PATH, SOURCE_MANIFEST_PATH):
        if not path.exists():
            raise FileNotFoundError(f"missing source snapshot: {path}; run --refresh-sources")
    outputs = [
        CHANGE_LOG_PATH,
        SNAPSHOT_PATH,
        INTERVAL_PATH,
        DAILY_PATH,
        AUDIT_PATH,
        ARTIFACT_MANIFEST_PATH,
    ]
    existing = [path for path in outputs if path.exists()]
    if existing and not force:
        raise FileExistsError(f"membership outputs already exist: {existing[0]}")

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    config = read_json(STUDY_CONFIG_PATH)
    overrides = read_json(OVERRIDE_PATH)
    history_text = HISTORY_SOURCE_PATH.read_text(encoding="utf-8")
    current_text = CURRENT_SOURCE_PATH.read_text(encoding="utf-8")
    raw_rows = parse_change_rows(history_text)
    patched_rows = apply_manual_overrides(raw_rows, overrides)
    normalized = normalized_changes(patched_rows, overrides)
    aliases = overrides["canonical_aliases"]
    current_display = parse_current_tickers(current_text)
    current_canonical = {canonical_symbol(value, aliases) for value in current_display}
    changes = [
        item
        for item in grouped_changes(normalized)
        if item[0] >= dt.date(2009, 1, 1)
    ]
    canonical_snapshots, integrity = reconstruct_canonical_snapshots(
        current_canonical, changes
    )
    snapshots = display_snapshots(canonical_snapshots, overrides)

    start = dt.date.fromisoformat(config["data"]["study_start_session"])
    end = dt.date.fromisoformat(config["data"]["study_end_session_inclusive"])
    daily, intervals = build_daily_membership(snapshots, start, end)
    snapshots_frame = snapshot_rows(snapshots)
    latest_members = set(snapshots[max(date for date in snapshots if date <= end)])
    latest_matches_current = latest_members == current_display

    write_change_log(normalized)
    snapshots_frame.to_csv(SNAPSHOT_PATH, index=False)
    intervals.to_csv(INTERVAL_PATH, index=False)
    daily.to_parquet(DAILY_PATH, index=False, compression="zstd")

    in_scope = [
        row
        for row in normalized
        if dt.date(2009, 1, 1) <= row["effective_date"] <= end
    ]
    tier_counts = pd.Series([row["source_tier"] for row in in_scope]).value_counts()
    membership_counts = daily.groupby("session_date")["ticker"].nunique()
    audit = {
        "study_id": config["study_id"],
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "status": "provisional_point_in_time_reconstruction",
        "source_manifest_sha256": sha256_file(SOURCE_MANIFEST_PATH),
        "history_snapshot_sha256": sha256_file(HISTORY_SOURCE_PATH),
        "current_snapshot_sha256": sha256_file(CURRENT_SOURCE_PATH),
        "override_config_sha256": sha256_file(OVERRIDE_PATH),
        "parsed_change_rows_total": len(raw_rows),
        "in_scope_change_rows_2009_to_end": len(in_scope),
        "source_tier_counts_in_scope": {
            key: int(value) for key, value in tier_counts.to_dict().items()
        },
        "manual_override_rows": int(sum(row["manual_override"] for row in normalized)),
        "source_augmentation_rows": int(
            sum(row.get("source_augmentation", False) for row in normalized)
        ),
        "integrity_findings": integrity,
        "integrity_finding_count": len(integrity),
        "current_component_security_count": len(current_display),
        "latest_reconstructed_security_count": len(latest_members),
        "latest_reconstructed_matches_revision_pinned_current_table": latest_matches_current,
        "study_sessions": int(daily["session_date"].nunique()),
        "study_security_union": int(daily["ticker"].nunique()),
        "study_entity_union": int(daily["entity_key"].nunique()),
        "membership_count_min": int(membership_counts.min()),
        "membership_count_max": int(membership_counts.max()),
        "first_session": daily["session_date"].min().isoformat(),
        "last_session": daily["session_date"].max().isoformat(),
        "known_limitations": [
            "The complete change index is revision-pinned Wikipedia, not a licensed Nasdaq constituent-history feed.",
            "Rows without an official Nasdaq/SEC citation remain secondary-source membership evidence and are enumerated by source tier.",
            "Ticker lineage is manually frozen for known renames and same-symbol entity changes; Massive FIGI resolution is still required before price results are accepted.",
            "CMCSK is corrected from the official 2014 Nasdaq notice and its 2015 conversion is inserted from the issuer/SEC corporate-action record.",
        ],
        "result_permission": (
            "Membership is sufficient for exploratory plumbing. Final event-study results "
            "remain blocked until Massive price and point-in-time identifier audits pass."
        ),
    }
    AUDIT_PATH.write_text(
        json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    manifest_paths = [
        STUDY_CONFIG_PATH,
        OVERRIDE_PATH,
        SOURCE_MANIFEST_PATH,
        HISTORY_SOURCE_PATH,
        CURRENT_SOURCE_PATH,
        CHANGE_LOG_PATH,
        SNAPSHOT_PATH,
        INTERVAL_PATH,
        DAILY_PATH,
        AUDIT_PATH,
    ]
    manifest = {
        "study_id": config["study_id"],
        "generated_at_utc": pd.Timestamp.now(tz="UTC").isoformat(),
        "files": {
            str(path.relative_to(FAMILY_DIR)): {
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
            for path in manifest_paths
        },
    }
    ARTIFACT_MANIFEST_PATH.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return audit


def main() -> None:
    args = parse_args()
    if not args.refresh_sources and not args.build:
        raise SystemExit("pass --refresh-sources and/or --build")
    if args.refresh_sources:
        manifest = refresh_sources(force=args.force)
        print(json.dumps({"source_manifest": manifest}, ensure_ascii=False))
    if args.build:
        audit = build_membership(force=args.force)
        print(json.dumps(audit, ensure_ascii=False))


if __name__ == "__main__":
    main()
