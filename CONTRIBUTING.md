# Contributing

Thanks for looking. conclave is small on purpose: standard-library Python and Bash, no dependencies, everything testable offline. Keep it that way.

## Ground rules

- **Offline tests must stay offline.** `make test` runs the router against a fake vendor and the gate against fixtures. Nothing in the test suite may call a vendor, touch the network, or need a `governance.json`.
- **Exit 0 is not done.** A change to the kernel or verifier needs a test that shows the acceptance decision, not just that the code ran.
- **Fail closed at the boundary.** Anything that touches `gate/` must keep the property "a scan error blocks". Add a fixture for every new behavior.
- **No personal data, ever.** No home paths, emails, private folder names, or account details in code, fixtures, or docs. The gate's own fixtures use `example.com`-style placeholders.
- **One source of truth.** Rules live in `shared/governance.json`; instruction files are generated. Do not hand-edit a generated file in a PR.

## Adding a vendor

1. Write one adapter function in `router/adapters.py` returning the standard envelope; wire it into `run()`.
2. Add its models to `policy.json` (`models` + a ladder with tiers 1–3) and its name to `vendors` in `shared/governance.example.json`.
3. If it only ever receives a prompt (no local CLI with a sandbox), add it to `PROMPT_ONLY_VENDORS` so it runs from an empty sandbox.
4. Add routing tests to `router/tests.py`.

## Adding a role

Add an entry to `policy.json` `roles` (description, default vendor/tier, `max_turns`, `codex_sandbox`, `review`) and, if the role needs a system prompt, to `ROLE_PROMPT` in `router/ai`.

## Workflow

```bash
make test        # router + gate
make lint        # shellcheck + py_compile
```

Open a PR with a one-paragraph description of the behavior change and the test that proves it. Keep the diff focused.
