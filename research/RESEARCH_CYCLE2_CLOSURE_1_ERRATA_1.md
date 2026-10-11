# RESEARCH-CYCLE2-CLOSURE-1 — Errata 1

Append-only correction to [`RESEARCH_CYCLE2_CLOSURE_1.md`](RESEARCH_CYCLE2_CLOSURE_1.md). The closure record
itself is not edited. Text frozen in the Owner-approved AUTH-2 final package (§ERRATA_DRAFT), added with
AUTH-2-DISCOVERY-QUALIFICATION-1.

```text
LOCATION         RESEARCH_CYCLE2_CLOSURE_1.md §F, bullet "Universe limits"
INCORRECT        "BTC/USDT only in every Cycle-2 run"
CORRECT          The Donchian run (TRIAL-C2-TREND-DONCHIAN-1, GitHub run 37155789386) used BTC/USDT + ETH/USDT, as
                 preregistered (research/cycle2/prereg/TRIAL-C2-TREND-DONCHIAN-1.json pair_universe), applied by
                 research/cycle2/driver.py apply_pair_universe, and reflected in the RESULT's passive ("2 leg(s)").
                 The two null-control runs used BTC/USDT only, as recorded in their preregistrations:
                   research/cycle2/prereg/TRIAL-C2-NULL-MATCHFREQ-1.json  pair_universe = ["BTC/USDT"]
                   research/cycle2/prereg/TRIAL-C2-NULL-BLOCKSHUF-1.json  pair_universe = ["BTC/USDT"]
                 Correct statement: "BTC/USDT only in the two null-control runs; BTC/USDT + ETH/USDT in the Donchian run."
VERDICT_CHANGE         = NONE
RESULT_CHANGE          = NONE
LEDGER_HISTORY_CHANGE  = NONE
FUNNEL_LAW_2_RETROACTIVE = NO
```

Re-confirmation before commit (as the package requires): on main `390bf4bf66ae92f49ff8a9490b59e142ed592724`, read
2026-10-10, the preregistrations give `pair_universe` = `["BTC/USDT"]` for TRIAL-C2-NULL-MATCHFREQ-1 and
TRIAL-C2-NULL-BLOCKSHUF-1 and `["BTC/USDT", "ETH/USDT"]` for TRIAL-C2-TREND-DONCHIAN-1; the closure's §F bullet
reads "Universe limits: BTC/USDT only in every Cycle-2 run"; the Donchian RESULT's passive methodology reads
"10.00 each across 2 leg(s)". The Cycle-2 verdict, every trial result and the trial ledger history are unchanged.
