from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import json
import shutil

import pandas as pd

from strategy_lab.data.lake import DataLakeLayout
from strategy_lab.data.fs import atomic_write_path


DEFAULT_BLOCKED_SOURCE_PATTERNS = (
    "scenario",
    "seed",
    "test",
    "proxy",
    "hourlyized",
)

DEFAULT_REAL_SOURCE_ALLOWLIST = (
    "binance_api",
    "binance_ccxt",
    "binance_fapi_funding_freeze_gap",
    "binance_fapi_freeze_gap",
    "binance_fapi_kline_freeze_gap",
    "binance_fapi_kline_prospective_oos",
    "binance_fapi_klines",
    "binance_fapi_prospective_oos",
    "binance_fapi_refresh",
    "binance_funding_daily",
    "binance_futures_funding_rate_api",
    "binance_futures_kline_api",
    "binance_futures_kline_api_direct",
    "binance_kline_api",
    "binance_mark_index",
    "binance_mark_price",
    "binance_premium_index",
    "binance_rest",
    "binance_vision",
    "binance_vision_kline_daily_gap_repair",
    "binance_vision_kline_monthly",
    "binance_vision_kline_monthly_overlap_repair",
    "binance_vision_monthly",
    "binance_vision_usdm_daily_metrics",
    "ccxt",
    "eastmoney_kline_api",
    "fapi_rest",
    "gateio_contract_stats",
    "okx_ccxt",
    "okx_ccxt_daily",
    "okx_mark_index",
    "polygon_api",
    "yahoo_finance",
)


@dataclass(frozen=True, slots=True)
class DataAuthenticityIssue:
    path: str
    layer: str
    dataset: str
    rows: int
    blocked_rows: int
    sources: dict[str, int]
    action: str
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class DataAuthenticitySummary:
    root_dir: str
    dry_run: bool
    blocked_patterns: tuple[str, ...]
    allowed_sources: tuple[str, ...]
    issues: list[DataAuthenticityIssue] = field(default_factory=list)

    @property
    def blocked_files(self) -> int:
        return sum(1 for issue in self.issues if issue.blocked_rows > 0)

    @property
    def blocked_rows(self) -> int:
        return sum(issue.blocked_rows for issue in self.issues)

    @property
    def quarantined_files(self) -> int:
        return sum(
            1
            for issue in self.issues
            if issue.action in {"quarantine_file", "rewrite_rows"}
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "root_dir": self.root_dir,
            "dry_run": self.dry_run,
            "blocked_patterns": list(self.blocked_patterns),
            "allowed_sources": list(self.allowed_sources),
            "blocked_files": self.blocked_files,
            "blocked_rows": self.blocked_rows,
            "quarantined_files": self.quarantined_files,
            "issues": [asdict(issue) for issue in self.issues],
        }


def _matches_blocked_source(value: object, patterns: tuple[str, ...]) -> bool:
    source = str(value).strip().lower()
    return any(pattern in source for pattern in patterns)


COMPOSITE_SOURCE_PREFIX = "composite:"


def composite_source_parts(value: object) -> tuple[str, ...] | None:
    source = str(value).strip().lower()
    if not source.startswith(COMPOSITE_SOURCE_PREFIX):
        return None
    body = source[len(COMPOSITE_SOURCE_PREFIX) :]
    parts = tuple(part.strip() for part in body.split("+") if part.strip())
    return parts or None


def make_composite_source(sources: tuple[str, ...] | list[str]) -> str:
    unique = tuple(sorted({str(item).strip().lower() for item in sources if str(item).strip()}))
    if not unique:
        raise ValueError("composite source requires at least one constituent")
    if len(unique) == 1:
        return unique[0]
    return COMPOSITE_SOURCE_PREFIX + "+".join(unique)


def _is_unverified_source(
    value: object,
    *,
    allowed_sources: tuple[str, ...],
    blocked_patterns: tuple[str, ...],
) -> bool:
    source = str(value).strip().lower()
    parts = composite_source_parts(source)
    if parts is None:
        return source not in allowed_sources or _matches_blocked_source(
            source, blocked_patterns
        )
    if len(parts) < 2:
        return True
    return any(
        part not in allowed_sources or _matches_blocked_source(part, blocked_patterns)
        for part in parts
    )


def unverified_source_mask(
    frame: pd.DataFrame,
    *,
    allowed_sources: tuple[str, ...] = DEFAULT_REAL_SOURCE_ALLOWLIST,
    blocked_patterns: tuple[str, ...] = DEFAULT_BLOCKED_SOURCE_PATTERNS,
) -> pd.Series:
    if "source" not in frame.columns:
        return pd.Series(True, index=frame.index, dtype=bool)
    normalized_allowlist = tuple(source.strip().lower() for source in allowed_sources)
    return frame["source"].map(
        lambda value: _is_unverified_source(
            value,
            allowed_sources=normalized_allowlist,
            blocked_patterns=blocked_patterns,
        )
    )


def _source_counts(frame: pd.DataFrame) -> dict[str, int]:
    if "source" not in frame.columns:
        return {}
    return {
        str(key): int(value)
        for key, value in frame["source"].astype(str).value_counts(dropna=False).items()
    }


class DataAuthenticityAuditor:
    def __init__(
        self,
        layout: DataLakeLayout,
        *,
        allowed_sources: tuple[str, ...] = DEFAULT_REAL_SOURCE_ALLOWLIST,
        blocked_patterns: tuple[str, ...] = DEFAULT_BLOCKED_SOURCE_PATTERNS,
    ) -> None:
        self.layout = layout
        self.allowed_sources = tuple(source.lower() for source in allowed_sources)
        self.blocked_patterns = blocked_patterns

    def audit(self, *, report_path: Path | None = None) -> DataAuthenticitySummary:
        issues = self._scan_source_issues(dry_run=True)
        summary = DataAuthenticitySummary(
            root_dir=str(self.layout.root_dir),
            dry_run=True,
            blocked_patterns=self.blocked_patterns,
            allowed_sources=self.allowed_sources,
            issues=issues,
        )
        self._write_report(summary, report_path)
        return summary

    def clean(
        self,
        *,
        dry_run: bool = True,
        confirm_destructive: bool = False,
        quarantine_unverified_features: bool = True,
        quarantine_duckdb: bool = True,
        report_path: Path | None = None,
    ) -> DataAuthenticitySummary:
        if not dry_run and not confirm_destructive:
            raise ValueError(
                "destructive authenticity cleanup requires confirm_destructive=True"
            )
        issues = self._scan_source_issues(dry_run=dry_run)
        if quarantine_unverified_features:
            issues.extend(self._quarantine_features(dry_run=dry_run))
        if quarantine_duckdb:
            issues.extend(self._quarantine_duckdb(dry_run=dry_run))
        summary = DataAuthenticitySummary(
            root_dir=str(self.layout.root_dir),
            dry_run=dry_run,
            blocked_patterns=self.blocked_patterns,
            allowed_sources=self.allowed_sources,
            issues=issues,
        )
        self._write_report(summary, report_path)
        return summary

    def _scan_source_issues(self, *, dry_run: bool) -> list[DataAuthenticityIssue]:
        issues: list[DataAuthenticityIssue] = []
        for layer in ("raw", "normalized"):
            layer_root = self.layout.root_dir / layer
            if not layer_root.exists():
                continue
            for path in sorted(layer_root.rglob("*.parquet")):
                issues.extend(
                    self._inspect_source_file(
                        layer_root=layer_root, layer=layer, path=path, dry_run=dry_run
                    )
                )
        return issues

    def _inspect_source_file(
        self, *, layer_root: Path, layer: str, path: Path, dry_run: bool
    ) -> list[DataAuthenticityIssue]:
        dataset = path.relative_to(layer_root).parts[0]
        try:
            frame = pd.read_parquet(path)
        except Exception as exc:
            return [
                DataAuthenticityIssue(
                    path=str(path),
                    layer=layer,
                    dataset=dataset,
                    rows=0,
                    blocked_rows=0,
                    sources={},
                    action="read_failed",
                    reason=f"{type(exc).__name__}: {exc}",
                )
            ]
        if frame.empty:
            return []
        if "source" not in frame.columns:
            quarantine_path = self._quarantine_path(
                "non_real_sources", layer, path.relative_to(layer_root)
            )
            if not dry_run:
                quarantine_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(quarantine_path))
            return [
                DataAuthenticityIssue(
                    path=str(path),
                    layer=layer,
                    dataset=dataset,
                    rows=int(len(frame)),
                    blocked_rows=int(len(frame)),
                    sources={},
                    action="quarantine_file",
                    reason="missing source lineage",
                )
            ]
        blocked_mask = frame["source"].map(
            lambda value: _is_unverified_source(
                value,
                allowed_sources=self.allowed_sources,
                blocked_patterns=self.blocked_patterns,
            )
        )
        blocked_rows = int(blocked_mask.sum())
        if blocked_rows <= 0:
            return []

        quarantine_path = self._quarantine_path(
            "non_real_sources", layer, path.relative_to(layer_root)
        )
        action = "quarantine_file" if blocked_rows == len(frame) else "rewrite_rows"
        if not dry_run:
            if blocked_rows == len(frame):
                quarantine_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(path), str(quarantine_path))
            else:
                blocked = frame.loc[blocked_mask].reset_index(drop=True)
                kept = frame.loc[~blocked_mask].reset_index(drop=True)
                atomic_write_path(
                    quarantine_path,
                    lambda temp_path: blocked.to_parquet(temp_path, index=False),
                )
                atomic_write_path(
                    path, lambda temp_path: kept.to_parquet(temp_path, index=False)
                )

        return [
            DataAuthenticityIssue(
                path=str(path),
                layer=layer,
                dataset=dataset,
                rows=int(len(frame)),
                blocked_rows=blocked_rows,
                sources=_source_counts(frame.loc[blocked_mask]),
                action=action,
            )
        ]

    def _quarantine_features(self, *, dry_run: bool) -> list[DataAuthenticityIssue]:
        features_dir = self.layout.features_dir
        parquet_count = (
            sum(1 for _ in features_dir.rglob("*.parquet"))
            if features_dir.exists()
            else 0
        )
        if parquet_count == 0:
            return []
        target = self._quarantine_root("unverified_features") / "features"
        if not dry_run:
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                target = (
                    target.parent
                    / f"features-{pd.Timestamp.now(tz='UTC').strftime('%Y%m%dT%H%M%SZ')}"
                )
            shutil.move(str(features_dir), str(target))
            features_dir.mkdir(parents=True, exist_ok=True)
        return [
            DataAuthenticityIssue(
                path=str(features_dir),
                layer="features",
                dataset="features",
                rows=0,
                blocked_rows=parquet_count,
                sources={},
                action="quarantine_unverified_features",
                reason="feature files do not carry source lineage; regenerate from verified normalized data",
            )
        ]

    def _quarantine_duckdb(self, *, dry_run: bool) -> list[DataAuthenticityIssue]:
        files = sorted(self.layout.root_dir.glob("*.duckdb"))
        if not files:
            return []
        target_root = self._quarantine_root("stale_duckdb")
        issues: list[DataAuthenticityIssue] = []
        if not dry_run:
            target_root.mkdir(parents=True, exist_ok=True)
        for path in files:
            if not dry_run:
                shutil.move(str(path), str(target_root / path.name))
            issues.append(
                DataAuthenticityIssue(
                    path=str(path),
                    layer="duckdb",
                    dataset="duckdb",
                    rows=0,
                    blocked_rows=1,
                    sources={},
                    action="quarantine_duckdb",
                    reason="duckdb cache may reference pre-cleanup parquet state; it is safe to regenerate",
                )
            )
        return issues

    def _quarantine_root(self, name: str) -> Path:
        return self.layout.root_dir / "_quarantine" / name

    def _quarantine_path(self, name: str, layer: str, relative_path: Path) -> Path:
        return self._quarantine_root(name) / layer / relative_path

    @staticmethod
    def _write_report(
        summary: DataAuthenticitySummary, report_path: Path | None
    ) -> None:
        if report_path is None:
            return
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            json.dumps(summary.to_dict(), indent=2, sort_keys=True, default=str),
            encoding="utf-8",
        )
