# P3-PLN-06 — Host access hardening on hamza-workstation (A1–A4)

**Authority:** [`P3_CONTRACT.md`](P3_CONTRACT.md) §3 PLN-06, executed under
[`OWNER_P3_EXECUTION_AUTHORIZATION.md`](OWNER_P3_EXECUTION_AUTHORIZATION.md) (7b1b1fa1). Each host step needs its own
Owner authorization. The Owner runs every `sudo` step in a local terminal, and Claude verifies.
Host evidence lives in `~/tlos-paper/p3-evidence/` on hamza-workstation. It is not committed, and is cited by sha256.
PAPER / RESEARCH ONLY · REAL_MONEY_AUTHORIZED = NO · PAPER_LAUNCH_AUTHORIZED = NO

```text
A4 remote desktop         = COMPLETED 2026-11-03 — AnyDesk and RustDesk stopped and disabled; no listener on 7070/21118/21119
A1 SSH key over Tailscale = PASS 2026-11-03 — Owner Windows device, key-only login proven; sshd unchanged
A2 sshd key-only          = PREPARED for Owner review — NOT RUN, NOT AUTHORIZED
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

## A2 — prepared for review (evidence `a2_prep_20261103T145019Z.d`, `MANIFEST.sha256` sha256 `67b3b7c8…6ad3fc5`)
**The change** is one drop-in, `/etc/ssh/sshd_config.d/10-tlos-hardening.conf` (sha256 `d1e10cbb…dcd416f`):
`PasswordAuthentication no`, `KbdInteractiveAuthentication no`, `AuthenticationMethods publickey`,
`PermitRootLogin no`, `AllowUsers hamza`, `MaxAuthTries 3`, `X11Forwarding no`.

**What stays untouched:** `ListenAddress` and `ssh.socket`. A tailnet bind could race `tailscale0` at boot and
lock SSH out after a reboot; restricting the network belongs to A3.

**Tested off-host** with a non-root `sshd -T` on a copy of the live config:
- With the drop-in, the effective values are as listed for both hamza@tailnet and root@LAN.
- The control run, without the drop-in, reproduces V0.

**The apply script stops with nothing changed unless:**
- the hashes match;
- `sshd_config.d` is empty;
- the Owner key is present;
- the journal proves A1;
- sudo works.

**Its order of operations:**
1. Install the drop-in, then run `sshd -t`. If validation fails, the drop-in is removed.
2. Arm a 15-minute `systemd-run` auto-revert **before** the reload. If it cannot be armed, the drop-in is
   removed and sshd is not reloaded.
3. Reload sshd. Existing sessions are not cut.
4. Check the effective config. If it is wrong, the script rolls back immediately.

**The keep script** cancels the auto-revert only if both of these hold:
- the journal shows a **new** key login from 100.89.64.82 with the Owner fingerprint after the apply;
- no password or keyboard-interactive login was accepted after the apply.

The keep gate was tested against the real journal:
- a window containing the 16:42 password logins is refused;
- a window with no new key login is refused;
- a window with only the 16:48 key login is allowed.

**Residual:** port 22 stays reachable from the LAN, key-only, until A3.
