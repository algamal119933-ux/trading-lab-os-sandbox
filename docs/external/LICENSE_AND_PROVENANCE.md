# License and provenance — external benchmark sprint

Required by directive v1.1 §18 and §19, tightened by the verified pinning addendum v1.2.
Machine-readable twins: `research/external/upstream_pins.json`, `research/external/candidate_registry.json`.

## The rule this repository follows

**No external source is committed here.** Every pinned file is fetched on demand at a
frozen upstream commit and checked against a recorded SHA256 before use.

That is not caution for its own sake. Of the six external sources, two are GPL-3.0 and
**three carry no license at all** — no `LICENSE`, no `LICENSE.md`, no `COPYING` at the
reviewed commit, confirmed independently by fetching all three filenames and getting 404
on each. Code with no license grants no rights to copy or redistribute it, so vendoring
the unlicensed three would be worse than vendoring the GPL two, not better.

Directive §18 already points this way: *"Benchmarking GPL code does not require making it
a core dependency."* Pinning by hash and fetching at run time gives us reproducibility
without incorporation.

## Status per source

| Source | Commit | License | Vendoring | Role |
| --- | --- | --- | --- | --- |
| `wiktorj137/btc-strategy-lab` | `b68a551` | **GPL-3.0** (file present) | Not authorised | P0 executable benchmark |
| `francisx1999/crypto-trading-bot-postmortem` | `53babe6` | **GPL-3.0** (byte-identical text) | Not authorised | P0 negative control |
| `thotbreakerr/kronos-gauntlet` | `67a4771` | **none found** | **Prohibited** | P1 process reference |
| `ceyhanmolla/freqtrade-strategies` | `937fefc` | **none found** | **Prohibited** | P2 claim challenge |
| `TheoBrigitte/freqtrade` | `ebc58b1` | **none found** | **Prohibited** | P2 historical claim |
| `iterativv/NostalgiaForInfinity` | unpinned (Wave 2) | GPL-3.0 | Not authorised | P1 stress test |
| `enarjord/passivbot` | unpinned | Unlicense | Method mining only | P0 real-money evidence |

`CODE_COPY_INTO_CORE = NOT AUTHORIZED` for every row above. Nothing in this sprint
changes that; lifting it is an owner decision under §20, and it has not been requested.

## What "no license found" means here

It means exactly what it says: at the reviewed commit, GitHub reports no recognised
license and the three conventional filenames return 404. It does **not** mean the author
intended the work to be unusable, and it is not a criticism of these projects. It means
we have no grant, so we read and measure rather than copy.

Reading source, running it in an ephemeral environment to reproduce a public claim, and
extracting a *method* described in prose are all outside copyright's reach in the way that
matters here. Copying the code into Trading Lab OS is not.

## Provenance chain

Each pin is auditable end to end:

1. The owner's addendum v1.2 fixed each commit **before** any Trading Lab OS result existed
   for these candidates, which is what §7's "no favourable historical commit selection"
   rule requires.
2. `pin_upstream.py` fetches each file from `raw.githubusercontent.com` at that commit.
   (`github.com` and `codeload.github.com` both answer 403 under this session's egress
   policy, so cloning is unavailable; fetching one blob at a pinned commit is in any case
   the narrower operation.)
3. It computes **sha256** — the gate identity — and **git blob SHA1**, the value GitHub
   displays in its UI.
4. The blob SHA is the human link in the chain: five of them were transcribed into the
   addendum from what a person read on GitHub, and all five reproduced exactly on fetch.
   That is what proves we are measuring the same bytes the owner reviewed, and not a
   later edit at a moved branch tip.

```
EmaCrossFunding.py   893f43c5b81cc2e9ab5e2e8f70ad461ea8f18345   match
GeneticEngineV1.py   99a11d0b8d53711c75984356c7e59cfd52c8de3b   match
E0V1E.py             1c04d59421ebd4a9779c554064625c38d4989da5   match
E0V1E.json           ce7a8fb846b47d91f7b365779a35c46bb48205b7   match
config/config.json   e6f930f1476c8aebc8a3a7f6100e431f711b5fe3   match
```

## Attribution

- `EmaCross` / `EmaCrossFunding` — Wiktor J, `btc-strategy-lab`, GPL-3.0. Rules 1–3 are
  upstream's parameterised version of `EMAPriceCrossoverWithThreshold` by
  **Paul Csapak** (`paulcpk/freqtrade-strategies-that-work`, MIT); the funding filter is
  upstream's own addition. Any result we publish for "EmaCross" must carry both
  attributions, because the timing logic is not originally btc-strategy-lab's either.
- `crypto-trading-bot-postmortem` — Francis Oyakhire, GPL-3.0.
- `E0V1E` — origin is a widely-mirrored community strategy; `TheoBrigitte/freqtrade` is the
  benchmark repository the addendum pins, not necessarily the original author.
- `GeneticEngineV1` — ceyhanmolla.
- `kronos-gauntlet` — thotbreakerr.

## Verifying this yourself

```bash
python3 research/external/pin_upstream.py --verify
```

Exit 0 prints `UPSTREAM_PIN_GATE = PASS`. Any changed byte at a pinned commit, any file
that appears where one was pinned absent, and any blob SHA that stops matching the
addendum all fail the gate. It is checked in CI.
