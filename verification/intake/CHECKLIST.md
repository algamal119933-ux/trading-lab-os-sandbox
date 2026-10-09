# Intake checklist

Run before any case is executed. Every line must hold; the first one that fails stops the case.

1. `triage.py` returned **ACCEPT** on the intake as received.
2. **No secret anywhere.** Not in the intake, the config or the archive. If one is found after acceptance, stop
   and tell the customer to rotate it.
3. **Identity pinned, all five parts:** strategy source, parameter file (or its stated absence), config,
   engine version, market window. A source hash alone does not identify a run.
4. **Bytes match the hashes.** The received strategy, params and config hash to the values in the intake.
5. **Safety boundary:** spot, long only, `can_short = false`, leverage 1, `dry_run = true`.
6. **Rights:** a recognised licence, or the customer's statement that they hold the rights.
7. **Claim fixed first:** the claim and its source are recorded before any result exists.
8. **Isolation:** the case runs only on the isolated runner, on a machine that is not the P2 host, with no
   network for the strategy code.
9. **Nothing committed:** customer code and data stay out of this repository. Only the case id, and later an
   evidence ticket, may be recorded.
