# Freqtrade Strategy Verification

The product lane chartered by `charters/COMMERCIAL-VERIFICATION-LANE-1.json`.

- `sample/SAMPLE_REPORT.md` is what a customer receives, shown on a public GPL-3.0 strategy.
- `sample/case.json` pins every input the sample is rendered from by sha256.
- `report.py` renders a report from a case file. It runs no backtest and fetches nothing.

```bash
python3 verification/report.py            # check the committed sample still matches its inputs
python3 verification/report.py --write    # regenerate it
```

Customer code and customer data are never committed here.

PAPER / RESEARCH ONLY. REAL_MONEY_AUTHORIZED = NO.
