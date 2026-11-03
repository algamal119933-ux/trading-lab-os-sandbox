# P3-PLN-06 — Host access hardening on hamza-workstation (A1–A4)

**Authority:** [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 PLN-06, executed under
[`OWNER_P3_EXECUTION_AUTHORIZATION.md`](OWNER_P3_EXECUTION_AUTHORIZATION.md) (7b1b1fa1). Each host step needs its own
Owner authorization. The Owner runs every `sudo` step in a local terminal, and Claude verifies.
Host evidence lives in `~/tlos-paper/p3-evidence/` on hamza-workstation. It is not committed, and is cited by sha256.
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO · PAPER_LAUNCH_AUTHORIZED = NO

```text
A4 remote desktop         = COMPLETED 2026-11-03 — AnyDesk and RustDesk stopped and disabled; no listener on 7070/21118/21119
A1 SSH key over Tailscale = PASS 2026-11-03 — Owner Windows device, key-only login proven; sshd unchanged
A2 sshd key-only          = v2 PREPARED for Owner review (risks A/B corrected) — NOT RUN, NOT AUTHORIZED
A3 UFW (SSH on tailscale0) = NOT AUTHORIZED
```

## Starting point (V0, read-only, 2026-11-03T14:07Z, Owner-run)
- **sshd:** `passwordauthentication yes`, `permitrootlogin prohibit-password`, `authenticationmethods any`,
  `maxauthtries 6`, `x11forwarding yes`. It is socket-activated on `0.0.0.0:22` and `[::]:22`.
- **UFW:** inactive.
- **Listeners:** only TCP 22 among the remote-access ports.
- **SMART:** PASSED on both disks.
  - WD30PURX: 0 reallocated, pending or uncorrectable sectors, 0 CRC errors, 25,395 power-on hours.
  - NVMe NM620: 5% used, 0 media errors.
- **Login attempts:** none logged since 2026-10-25, and fail2ban is not installed.

## A1 — PASS (evidence `a1_pass_20261103T144931Z.d`, `SHA256SUMS` sha256 `e107c3c3…5955a1e9`)
- **Device:** the Owner's Windows workstation joined the tailnet as `hamza`, 100.89.64.82.
- **Host key:** the Owner verified the host ED25519 key `SHA256:B85un9svMJenZ54JJa6rEIt0BPael8ir9tm5S2sm6ic`.
- **Public key:** staged as one ssh-ed25519 line with a CRLF ending. It was installed with the reviewed helper
  from a CR-stripped copy; the key blob and fingerprint are byte-identical.
  - `authorized_keys`: 0 → 1 entry, `owner-windows-tlos`, `SHA256:PwePc6BQ90hTSiI4vckwOdAfsN6k8njOxGSznAFrRRY`.
  - Modes: home 750, `~/.ssh` 700, `authorized_keys` 600.
- **Proof:** `2026-11-03T16:48:00+02:00 Accepted publickey for hamza from 100.89.64.82 port 55746 ssh2: ED25519
  SHA256:PwePc6BQ…`. The session has no password line, and there were no failed attempts.
- **Earlier logins:** three `Accepted password` logins came from the same address at 16:42–16:43, before the key
  install. They were the planned first connection and the staging step.
- **sshd:** unchanged (sshd_config sha256 `f5f0b404…`, `sshd_config.d` empty).

## A2 — v2 prepared for review (evidence `a2_prep_v2_20261103T151500Z.d`, `MANIFEST.sha256` sha256 `b3171a6a…99a04c7`)
v2 supersedes the v1 package (`a2_prep_20261103T145019Z.d`, `MANIFEST.sha256` sha256 `67b3b7c8…6ad3fc5`), which
is kept unchanged. The sshd settings are the same approved drop-in,
`/etc/ssh/sshd_config.d/10-tlos-hardening.conf` (sha256 `d1e10cbb…dcd416f`):
`PasswordAuthentication no`, `KbdInteractiveAuthentication no`, `AuthenticationMethods publickey`,
`PermitRootLogin no`, `AllowUsers hamza`, `MaxAuthTries 3`, `X11Forwarding no`.
`ListenAddress` and `ssh.socket` are untouched; restricting the network is A3.

**Risk A — settings active before the rollback is armed.**
- **Lab finding:** a throwaway sshd on 127.0.0.1:2299 shows that a running sshd ignores a new drop-in until it is
  reloaded. Any fresh start applies it at once: a restart, socket activation, a `Restart=on-failure` crash
  restart, an openssh upgrade, or a boot.
- **Correction:**
  1. The proposed effective config is validated *before* install, from a temporary root-owned copy of
     `sshd_config` whose Include points at the proposed drop-in (`sshd -t`, plus `sshd -T` showing all 8 values).
  2. The revert is armed and verified.
  3. Only then is the drop-in installed atomically, followed by `sshd -t` and a reload.
- **Preflight** also refuses while an openssh update is pending, or within 45 minutes of the U1 window.

**Risk B — a reboot loses the transient revert timer.**
The correction is persistent trial-only machinery, removed again by keep or rollback:

| File | Role |
|---|---|
| `/usr/local/sbin/tlos-sshd-a2-revert` | Acts only while `/etc/tlos/sshd-a2-pending` exists |
| `tlos-sshd-a2-revert.service` | `ConditionPathExists=` the marker, `Before=ssh.service`, enabled into `multi-user.target`. A reboot during the trial reverts before sshd starts |
| `tlos-sshd-a2-revert.timer` | `OnActiveSec=15min`, `AccuracySec=1s` |

Keep deletes the marker first, which disarms both paths. `systemd-analyze verify` on both units: exit 0, no
ordering cycle. The independently proven recovery path remains the physical console: A2 changes only sshd, and
console login and `sudo` are untouched.

**Gates.**
- Before apply, the running sshd must offer exactly `publickey,password`.
- After the reload, it must offer exactly `publickey`, and `sshd -T` must show all 8 values. Otherwise the script
  reverts immediately.
- Keep refuses unless all of these hold:
  - the boot is unchanged;
  - the marker and drop-in are present, and the timer is pending;
  - there is a **new** key login from 100.89.64.82 with the Owner fingerprint at or after reload + 1 s. The A1
    login can never qualify;
  - no password or keyboard-interactive login was accepted after the reload;
  - the running sshd offers `publickey`.

**Probe hygiene.**
- OpenSSH 10 `PerSourcePenalties` (noauth:1, min:15) refused 8 of 25 burst probes in the lab, so the scripts
  probe once per phase, after a settle delay.
- `ssh -v` appends `\r`, which the probe strips. Without that, every equality gate failed.

**Tests** (the live sshd configuration was never changed; the live sshd was only probed):

| Case | Result |
|---|---|
| Drop-in installed, no reload | inert |
| Reload | key-only |
| Timer with the marker present | reverted |
| Marker removed before the deadline | no-op |
| Fresh start without the boot path | stays key-only (Risk B shown) |
| Revert before sshd starts | `publickey,password` |
| Marker absent | no-op |
| Base config invalid | drop-in removed, no reload, logged |
| Invalid proposed drop-in | stops before arming |
| Keep gate vs the real journal | reload in the same second as A1, or later → refuse; window with password logins → refuse; control → allow |
| Live non-sudo preflight | 12/12 PASS |

**Residual:** port 22 stays reachable from the LAN, key-only, until A3.
