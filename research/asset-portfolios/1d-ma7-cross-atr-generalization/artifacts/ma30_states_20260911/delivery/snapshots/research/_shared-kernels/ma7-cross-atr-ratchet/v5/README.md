# MA30 management overlay, shared code v5

Default ma30_mode=none keeps all v4 account and stop fields unchanged. Modes defense/extend/both add closed-bar MA30 gates to early protection, healthy tightening pauses, acceleration observation and conditional short take-profit suppression. Requires original V3 routes with admission_routing enabled.

The state and all thresholds are defined in the consuming family contract-ma30-states-20260911.md. Codes v5 and official strategy V1/V2/V3 are separate identities. Existing pinned v1-v4 sources are unchanged. Tests: tests/test_ma7_car_ma30_states.py, 28 passed.
