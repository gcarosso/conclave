# Security

conclave's job is to keep private material from reaching the wrong model or the wrong repository. If you find a way around that, please report it privately rather than in a public issue.

**Report to:** open a GitHub security advisory on this repository (Security → Report a vulnerability).

## What counts

- A path by which a job's payload reaches a vendor that the job's `data_class` does not admit.
- A way for a prompt-only vendor (Grok, Gemini) to receive anything other than the prompt.
- A publish-gate mode that reports `clean` when a marker is present (including in binaries, dotfiles, or history), or that reports `clean` on a scan error.
- A way to launch a gated model without an approval record in the contract.
- A way for two jobs to hold the same write set at once.

## What does not count

- Behavioral limits documented as behavioral in `docs/architecture.md` (for example, a vendor CLI's own read confinement). The enforcement boundary is stated honestly there; please read it first.
- Vendor CLI or API bugs. Report those upstream.

## Scope of the guarantee

The router enforces eligibility, data class, the model allowlist, the approval gate, timeouts, the writer lock and acceptance for everything launched through `ai`. A desktop session or a raw vendor CLI in the same shell is governed by the generated instruction files only.
