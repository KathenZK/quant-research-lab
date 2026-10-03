# Catalog daily input/view adapter v1

This immutable, standard-library-only adapter checks input identity and projects an
already computed canonical feature trace into the existing daily-cash v1 view.
It does not compute indicators, signals, orders, returns or benchmarks, and does
not read files or access a network. Batch020 intended consumers are M2903, M3710
and M0974. Their research gates remain separate.

## API

`load_input(body: bytes, profile_name: str) -> InputView` is the production entry.
Only `warmup100` (831 rows, 100 warmup, offset 69) and `warmup735` (1466 rows,
735 warmup, offset 704) are accepted. Their canonical byte identities are fixed
in `PROFILES`. Both produce 762 rows with 31 warmup and 731 evaluation rows,
128196 bytes and SHA256
`48e4e785ee3366a459cf09f64617c89e04fb19b91da6c6125e86835506f6b9f5`.
The validator checks original UTF-8 CSV/CRLF bytes, exact header, UTC daily grid,
timestamps, finite and bounded OHLCV, trades, taker volumes and zero ignore field.
No normalization or approximate identity is accepted.

`InputView` fields: `profile`, `full_rows`, `view_rows`, `view_bytes`. Rows are
tuples of read-only mappings with original CSV string values. `view_bytes` is
the exact serialized view, suitable for an explicitly created private input file
passed to the unchanged old loader/verifier. Do not send full canonical rows to
the old engine with its implicit `start=31`.

`align_features(input_view, full_features, *, required_ready_fields: tuple[str,...])`
returns `FeatureView(full_features, view_features, required_ready_fields)`.
Supply a full list/tuple of canonical feature mappings with these mandatory keys:

- `canonical_feature_index`: strict integer 0 through canonical rows minus one.
- `open_time`, `close_time`: strict integer Binance timestamps; `close_time` is
  inclusive native close (`open_time + 86400000 - 1`), not the next execution instant.
- `close`: exact input CSV string.
- `ready`, `raw_entry`, `raw_exit`: strict integers 0 or 1; booleans are rejected.

The consumer freezes its nonempty `required_ready_fields` schema in C0. Every
named field must exist at every row, and when ready must be a finite Decimal or
Decimal numeric string. Before readiness, None is permitted and both raw signals
must be zero. Every evaluation row must be ready. This does not decide a family's
first ready index: M0974 must separately distinguish RSI/SMA readiness from cross
readiness. Other keys are preserved recursively; values may be strings, integers,
finite Decimals, None, sequences or mappings. Float and boolean values are rejected.
Output is recursively read-only; use `dict(record)` for flat CSV/JSON records,
and convert Decimal explicitly to strings for JSON. No indicator values are rounded.

Full canonical feature trace is retained, then sliced by the fixed offset.
The adapter proves length, alignment, readiness declarations and unchanged projection;
it **cannot prove** that upstream indicators were never reseeded or never used future
data. Consumers must pin indicator code, retain the full trace and perform independent
oracle, prefix/future and initialization QA before their own C0 release.

`map_index(profile_name, index, namespace)` accepts namespace `canonical`, `view`
or `eval`. It returns `canonical_index`, `view_index`, `eval_index`; absent earlier
warmup correspondences are None. Actual-bar indices are bounded, never future ordinals.
In unchanged engine CSVs `input_index` means view index. Preserve that schema and
write a separate explicit mapping. First evaluation is canonical W = view 31 = eval 0.

`map_pending(profile_name, signal_index, due_index, delay_bars)` accepts **evaluation**
indices, delay 1 or 2 and exact due = signal + delay. It returns signal's map,
`due_eval_ordinal`, `due_view_ordinal`, `due_canonical_ordinal`, `due_in_window`.
Last signal eval730 can be due731/732, which remains pending. These are ordinals,
not actual rows: no price, future bar or terminal execution is generated.
`map_roundtrip(profile_name, entry_index, exit_index)` likewise takes evaluation
indices for actual fills, strictly increasing, and returns entry/exit maps and
holding_bars. No re-entry or order reconciliation is implemented here.

## Consumer boundary and validation

Pin adapter.py and this version's manifest before import. Consumer runners must
reject Python optimization (`-O`) before reading their gates/input or importing the
account engine, as required by frozen rules. Adapter validation itself uses explicit
exceptions, never removable asserts. `_validate_input`, `_serialize`, dataclass
construction and underscore helpers are internal, not alternative production loaders.
There is no production synthetic bypass. Unit tests replace byte pins only inside the
private structural validator to exercise fabricated constant-price rows. An InputView
is an in-process validated value, not an authentication token for untrusted callers.

Run synthetic tests from repository root:

```sh
python research/_shared-kernels/catalog-daily-input-view/v1/tests/test_adapter.py
python -O research/_shared-kernels/catalog-daily-input-view/v1/tests/test_adapter.py
```

Tests cover both profiles, public pin rejection, encoding/hash/grid/OHLCV failures,
full-trace projection and future/offset perturbation, readiness and strict-type failures,
all 1462 evaluation mappings, pending tail ordinals and roundtrip bounds. No real input
is opened and no accounting run is performed. Independent review is required after
the local source commit; unit-test success does not authorize history.

`manifest.json` pins implementation, tests and this README, excluding itself to avoid
circular hashing. The kernel root README pins the manifest. Future changes after
consumer pinning require a new version directory.
