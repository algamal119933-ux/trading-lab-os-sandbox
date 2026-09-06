# Trading Lab OS — BASELINE-V1 v1.3 Safety Correction
Date: 2026-09-06

## Confirmed gate
DATA_INTEGRITY_GATE = PASS

Dataset fingerprints:
- BTC/USDT 1h: b29689f5d0c0e86c95b5ec15e63e6bcfbcb8ad4596408dcc0f9040b3bbdfb4f9
- BTC/USDT 5m: 2ab332f23d2376677b61d5a02492b5a4b67f2d37ac68f89a925697252cc7b908
- ETH/USDT 1h: a5de3ae5e9c3c73439eb8aec8ff496f9e9d5ebc7cec83842b2b2827880201ccf
- ETH/USDT 5m: 4fa5ca782864ee84aff0e02786be3ca663de159288a7fb4baf12398fcdcca5c4

5m -> 1h reconciliation:
- BTC/USDT: zero OHLCV mismatches
- ETH/USDT: zero OHLCV mismatches

## Important correction from v1.2
The earlier passive benchmark script computed and printed DEVELOPMENT, VALIDATION and LOCKED_OOS in one run.
That would unnecessarily expose the locked OOS before the active strategy was frozen.

v1.3 fixes this:
- default = DEVELOPMENT only
- VALIDATION requires an explicit period flag
- OOS refuses to run unless `--unlock-oos` is explicitly supplied

## Immediate next step

1. Do not run `download-data` again during BASELINE-V1.
2. Replace `baseline_benchmarks.py` with the v1.3 version.
3. Run DEVELOPMENT passive benchmark only:

docker compose run --rm --entrypoint python freqtrade /freqtrade/user_data/baseline_benchmarks.py

4. Return the four printed numbers:
- BTC net B&H
- ETH net B&H
- Full 50/50
- Exposure-matched

Do not run Validation or OOS yet.
