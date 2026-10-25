# OWNER P3 EXECUTION AUTHORIZATION — P3 PAPER BETA RELEASE

**Granted by:** the Owner, and by no one else. This file exists only because the Owner decided it
should. It is created by an Owner-merged PR at the moment authority is granted, and never before.

**Authority:** [`P3_CONTRACT.md`](P3_CONTRACT.md) §9, frozen by the Owner merge of PR #72. This record
does not restate the contract and does not extend it.

This is **PAPER-ONLY** authority. It authorizes one thing: executing P3 workstreams PLN-02 to PLN-11
exactly as the frozen contract defines them. It authorizes nothing else: no real money, no strategy,
risk or dataset change, no new stage or workstream, no candidate research or trials, no H1 launch,
no live trading, and no reopening of the frozen product shape.

---

## The authorization

```text
AUTHORIZED_STAGE = P3 — PAPER BETA RELEASE
P3_CONTRACT_PATH = docs/p3/P3_CONTRACT.md
P3_CONTRACT_SHA256 = 2c057cb57db1a75ec54d1f5b6f76c2e022e91822b3e1417049b12e270d487f4d
P3_CONTRACT_FREEZE_MERGE = fcd06b2124445c12808aa259f070d9e9a39999aa
SCOPE = PLN-02..PLN-11 as defined in P3_CONTRACT.md §3; no new stage or workstream
REAL_MONEY_AUTHORIZED = NO
H1_LAUNCH_AUTHORIZED = NO
EXPIRES_UTC = 2027-01-31T23:59:59Z
```

Each field appears exactly once, by requirement. A file that says two things about one field is not
an authorization but an ambiguity.

## Known blockers that remain under this authorization
These gate specific workstream **acceptance**. They do not gate starting P3:
- PLN-09 stays BLOCKED until the frozen Control Room product-shape reference is identified (contract §6).
- PLN-05 acceptance needs an independent host (Tier 3).
- Storage capacity (root fs about 9 GiB) constrains the PLN-03 restore drills and the PLN-10 acceptance run.
- The PLN-04 power posture (UPS) is an Owner decision.
