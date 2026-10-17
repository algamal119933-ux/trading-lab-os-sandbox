# G5 — H1/H2 byte-identical source check on the Owner host

**Result:** `H1_H2_BYTE_IDENTICAL_COPY = RECOVERED`. This is a record only. It
launches nothing, and it vendors nothing: the GPL-3.0 files stay on the Owner host.

```text
AUTHORITY   Owner decision card, option "G5 host check", 2026-10-17T14:39:56Z
COMMAND     PROFIT_FIRST_EXECUTION_REVIEW §B.6, unchanged, run once under nice 19 / ionice idle; read-only
HOST        hamza-workstation · start 2026-10-17T16:23:51Z · end 2026-10-17T16:24:57Z · exit 0
SCOPE       find / -xdev. /home is on the root ext4 filesystem, so it was scanned.
            No separate data filesystem exists.
NOT SCANNED tmpfs (/tmp, /run, /dev/shm), snap squashfs mounts, and the Docker overlay rootfs mounts
            (these may belong to the running FP-CONTROL-3 runtime and were deliberately left alone)
P2          untouched: no file written, no git command, no service, container, key or network
```

## Matches (all five pinned sha256 found)

| sha256 | Pinned as | Path on the Owner host |
|---|---|---|
| `387cf39f58d266bb63d06865a0784bc2e08676edf54f4610c7d7709bb2a95f24` | H1 `EmaCross.py` | `/home/hamza/projects/trading/tlos-control/.upstream-cache/btc_strategy_lab/user_data/strategies/EmaCross.py` |
| `9209a90e5092216af166fd10b9e7415690ab16af0fb3010c7e94e162c027e3ee` | H1 `EmaCross.json` | `…/btc_strategy_lab/user_data/strategies/EmaCross.json` |
| `3972dc9744f6499f0f9b2dbf76696f2ae7ad8af9b23dde66d6af86c9dfb36986` | `LICENSE` (GPL-3.0) | `…/btc_strategy_lab/LICENSE`, and also `…/postmortem_negative_control/LICENSE` |
| `0f0d3d4677647da2e11d4dc8195adbb95fce201ce400300df0a78741cf9a9564` | H2 `EmaCrossFunding.py` | `…/btc_strategy_lab/user_data/strategies/EmaCrossFunding.py` |
| `1641ce3122ccc0c216aaae1af77bedb15dd77670643201d1c7453066eca38f0b` | H2 `EmaCrossFunding.json` | `…/btc_strategy_lab/user_data/strategies/EmaCrossFunding.json` |

The pins are the ones in `research/external/upstream_pins.json` (source `btc_strategy_lab`, commit
`b68a5518b4a3eba2fde1733160d7d7de356023b5`) and in `research/paper/h1/package/cohort.json`.

## Consequence

- **H1.** The default `DO_NOT_LAUNCH` (source not found) no longer applies. Launch stays governed by
  `H1_AMENDMENTS_G6.md` and the package's §9 preconditions.
- **H2.** `DROP` (source not found) no longer applies. Recovery admits H2 nowhere. Its placement is a separate
  Owner decision, which has not been taken.
