# M0256 / M0259 bounded official-data contract

## Current state

Prepared for the two assigned IDs only. **ZIP capture and actual public-source rebuild are paused for review of the newly discovered dataset terms.** No input prices, input hash or successful online QA is asserted by this document. A single 88-byte official CHECKSUM reachability probe succeeded before the terms were discovered. All tests are offline synthetic parser fixtures, not research data.

The immutable handoff is `KathenZK/quant-research-lab@a7b7ea4c09863306ed41427c19af072c0db20139:research/public-strategies/dot-batch001-handoff-20261003.md`; governance reference is `797a8e7d1dda2a1009ab03baac0bf770dab8a806`. Exact source snapshots and SHA256/Git-blob identities are in `evidence/source-document-manifest.json`.

## Scope and identities

- M0256: Binance BTCUSDT spot, native 4h archives, 2022-12 through 2024-12 (25 months)
- M0259: same market and window, native 1h archives (25 months)
- Input opens: `[2022-12-01T00:00:00Z, 2025-01-01T00:00:00Z)`
- Prespecified evaluation opens: `[2023-01-01T00:00:00Z, 2025-01-01T00:00:00Z)`
- UTC, continuous 24/7, expected full-grid input counts 4,572 and 18,288 respectively (expectations, not observed claims)
- Rows: `exchange=binance`, `market_type=spot`, `symbol=BTC/USDT`, `native_symbol=BTCUSDT`, `source=binance_vision`, `timeframe=4h|1h`
- No current-universe scan, leverage, futures, funding, parameter selection, return computation or strategy execution

## Deterministic CSV

UTF-8, comma-separated, LF records, one header. The original 12 fields retain their exact source strings, order and decimal precision. No sort, dedup, fill, interpolation or numeric reformatting is permitted. Header:

```text
open_time,open,high,low,close,volume,close_time,quote_volume,trade_count,taker_buy_base_volume,taker_buy_quote_volume,ignore,ts,exchange,market_type,timeframe,symbol,native_symbol,source,bar_close_ts,source_archive
```

| Field | Meaning / unit |
|---|---|
| open_time | Native Unix millisecond kline open time, integer |
| open/high/low/close | Native BTC spot prices, USDT per BTC |
| volume | Native base-asset (BTC) volume |
| close_time | Native Unix millisecond interval close time, integer; equals open_time + interval_ms - 1 |
| quote_volume | Native quote-asset (USDT) volume; Binance column “Quote asset volume” |
| trade_count | Native nonnegative integer “Number of trades” |
| taker_buy_base_volume | Native taker-buy base-asset (BTC) volume |
| taker_buy_quote_volume | Native taker-buy quote-asset (USDT) volume |
| ignore | Original unused field, retained without semantic invention |
| ts | Deterministic ISO UTC rendering of open_time, with `.000Z` |
| bar_close_ts | Deterministic ISO UTC rendering of native close_time, with `.999Z` |
| source_archive | Exact originating monthly ZIP filename |

There is **no fabricated `vwap` or `is_closed`**. Native interval-end time is not a native finality boolean. Consumers must parse `ts` as timezone-aware UTC and enforce the declared identity. Standardized CSV is a lossless, canonical raw diagnostic representation, **not acceptance into `data/normalized`**.

The official README states SPOT timestamps change to microseconds from 2025-01-01 onward. This request ends before that change; every row is audited as milliseconds against the exact UTC grid. Futures field definitions must not be substituted for spot.

## Storage and invocation

Proposed immutable output directories under the shared data root:

```text
data/raw/ohlcv/exchange=binance/market_type=spot/timeframe=4h/source=binance_vision/snapshot=dot-b001-primary-v1/
data/raw/ohlcv/exchange=binance/market_type=spot/timeframe=1h/source=binance_vision/snapshot=dot-b001-primary-v1/
```

Each contains 25 `archives/YYYY-MM/` directories with the original ZIP, CHECKSUM, unpacked CSV, HTTP metadata, then `BTCUSDT-<tf>-202212-202412-native12.csv` and `manifest.json`.

After applicable authorization has been obtained, the standalone stdlib command is:

```sh
python data-tools/rebuild_official_bars.py --timeframe 4h --target NEW_SNAPSHOT_DIRECTORY --terms-reviewed
```

An actual independent network rebuild uses another new directory and the frozen primary manifest:

```sh
python data-tools/rebuild_official_bars.py --timeframe 4h --target ANOTHER_NEW_SNAPSHOT_DIRECTORY --expected-manifest PRIMARY_MANIFEST_JSON --terms-reviewed
```

Repeat for 1h. The flag records operator review; it is not a substitute for required approval. The script never signs up, authenticates, transmits credentials, installs dependencies or changes permissions. It does not accept an explicit agreement on the user's behalf.

Existing targets and `.partial` staging targets are refused. Capture failures retain partial raw evidence and `failure.json`; they never publish a completed snapshot. The source host is pinned, redirects refused, and no retry or alternative network route is attempted. Network denial is `UNAVAILABLE`. Changed source ZIP, CHECKSUM, original CSV, code hash or canonical input is `MISMATCH`. Both captures remain retained. HTTP capture timestamps necessarily differ; stable content hashes, not dynamic response metadata, are compared.

## QA and acceptance boundaries

The builder checks official SHA256 CHECKSUM content and basename, ZIP single-member identity and CRC, bounded decompression, every native column, Decimal OHLC relationships, finite/nonnegative volumes, taker totals not exceeding full totals, quote totals consistent with low/high bounds allowing one source precision unit, nonnegative integer trade counts, exact UTC open/close phase, full calendar counts, original order and no duplicates or missing bars. Native zero-volume/trade rows are retained and counted; `reject_gap_policy_eligible` is false if they occur. At least 5 GiB free disk must remain. There are per-object size caps and only the prespecified 25-month scope.

Gate status cannot be inferred from parser tests. Pending an actual capture, all online gates remain NOT_RUN. After capture, row/hash integrity may pass independently of acceptance:

- Identity: official spot archive path and explicit native symbol are observed identity; historical instrument eligibility/tradability not proven
- Schema: all 12 raw fields preserved; default LAB_OHLCV_V1 is not claimed because vwap/is_closed are absent
- Coverage/calendar/integrity/hashes: exact scoped checks are performed; they do not prove point-in-time availability
- Finality: official completed-month archive schedule, full grid and native close_time support interval completion; the stricter core protocol additionally requires a newer current bucket, provider clock agreement, independent review and full stable recapture. No native final flag exists in the 12-field archive, and no local-clock-based closed=true is created
- License: explicit CC BY-NC-SA 4.0 plus Binance Vision Dataset Terms; purpose/acceptance pending review. MIT on source code does not cover market data
- Provenance/PIT: present-day archives can be revised (official README “Updates”); a double capture proves stable bytes during the two captures, not original release-time information or permanent immutability

The result remains `registered_status=UNACCEPTED`, `scope=EXPLICIT_DIAGNOSTIC`, `quality_status=DIAGNOSTIC_ONLY`, `trusted=false`. It cannot be used to claim live-ready, strict reproduction, clean OOS, author-selected universe, reliable DSR/PBO, exact intrabar execution or global lake registration. This bounded handoff does not modify or bypass the repository's global startup/registration machinery.

## Dataset terms and distribution

Official terms: https://github.com/binance/binance-public-data/blob/f446ce3812bd4e5521f21faecd4ae3c6460e49fc/TERMS_AND_CONDITIONS.md

The terms file is 9,798 bytes, SHA256 `dcf358e9d18f598a7a635fac80f6e643fa24a0e111a4d39bda47f1e246b31eb1`, Git blob `87d04e216f62c86a2c797fbb7637404d6d602687`. Key sections:

- 1.4 (line 15), 3.2 (line 33): access, attempted access, download and use entail agreement to these terms and the linked Binance Terms of Use
- 2.4 (line 27): charts, models and derivative indicators are included
- 3.1–3.4 (lines 31–38): noncommercial CC BY-NC-SA 4.0 plus additional terms; commercial use requires separate written permission
- 4.1–4.5 (lines 42–50): personal non-production historical backtesting is listed; live execution/commercial tools/paid signals are excluded; derivative redistribution requires Binance Vision attribution and identical licensing
- 11.3 (line 106), 12 (line 112): indemnification and incorporated arbitration provisions

Publishing only a backtest chart/summary rather than raw candles does not by itself resolve these obligations. Public Graph or repository derivative output needs its own distribution assessment. No raw data is uploaded or published by this workflow.

## Offline testing

```sh
cd data-tools
PYTHONDONTWRITEBYTECODE=1 python -m unittest -v test_rebuild_official_bars.py
```

Tests exercise parser/serialization, malformed rows, duplicate/order/gap refusal, volume/price inconsistencies, hash mismatch, ZIP path safety, disk threshold, network source restriction and no-request guards. Synthetic fixtures live only in test memory and never become canonical market inputs. Passing unit tests does not imply successful archive retrieval or rebuild.
