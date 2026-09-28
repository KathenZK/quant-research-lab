# MA7 execution kernel v4: supplied admission and exit routes

This is a code version, not an official strategy V4. It copies the frozen v3
engine and adds one opt-in control, `Config.admission_routing` (default `False`).
Existing V3 entry qualification, sizing, costs, closed-bar stop updates and
hourly fill ordering are retained.

When enabled, every daily input row must contain:

| Columns | Allowed values |
| --- | --- |
| `admit_long`, `admit_short` | Boolean only; missing, numbers and strings fail |
| `route_long`, `route_short` | `v3`, `defense`, `trend`, `extension` |
| `rule_id_long`, `rule_id_short` | Nonempty strings |

The caller supplies the already-frozen decision table and is responsible for
proving that training and each row's features used only information available
at that day's close. This engine validates table values and execution timing;
it does not infer or certify how the external rules were trained.

A crossing must first pass the original entry qualification. At the next
day's open, the engine uses the preceding fully closed signal day's admission
and route. A refusal increments `admission_rejected`, retains the crossing and
attempt counts, and writes an entry event with stage `admission` and reason
`admission_rejected`. It does not alter `ready` or reclassify the refusal as a
slope failure.

At entry, the accepted route remains fixed for that entire position, including
across a subsequent model or calendar-year change. `extension` uses no old
short hard take profit; other routes use `accel1_rsi30`. The configuration
object is never mutated while flat or while holding. Gap stops keep precedence
over closed-bar take profit and prevent reopening on the same signal.

Decision metadata (`admission_allowed`, `admission_rule_id`,
`admission_signal_day`, `exit_route`, `route_short_exit`) appears in entry
events and, for accepted trades, in the trade and each stop record. Rejected
signals have no invented trade or stop records. When routing is disabled,
existing event/trade/stop fields and all previous calculation fields remain
identical; the summary adds only the default-disabled configuration flag.

Synthetic verification lives in
`tests/test_ma7_car_admission_routing.py`. It includes disabled-mode exact
comparisons with v3, uniform-route exact comparisons with all four v3 exits,
independent fixed-episode reconciliation of mixed routes, strict input
validation, long/short refusals, original slope priority, closed-day timing,
gap priority, and inherited positions across the 2025 model boundary.

The parent experiment pins the final source digest in its run contract. This
directory alone does not promote any fitted rule or strategy result.
