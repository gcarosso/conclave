# Contributing

Conclave uses standard-library Python and Bash. Keep changes focused and preserve offline testing of routing, acceptance, and publication scans.

## Validation

```bash
make test
make lint
```

`make test` uses fake vendor responses and temporary repositories. It must not call a model, use credentials, or require a personal governance file. Test the acceptance decision or protected boundary when changing control logic. Add a failing-case fixture for scanner changes.

`make lint` compiles Python and runs ShellCheck when installed. A ShellCheck failure fails the target; an absent installation is reported as skipped. CI installs ShellCheck for its Linux lint job.

## Extension points

- **Vendor:** add an adapter returning the standard envelope, its dispatch branch, model entries, ladder, and governance membership. Test eligibility, permissions, and failure handling.
- **Role:** add a policy entry and, if needed, an instruction in `ROLE_PROMPT`.
- **Check:** add a builtin in `verify.py`, or pass a command/review check through the kernel API.
- **Governance:** edit the source JSON and regenerate instructions. Test drift detection and relevant permission syntax.

`PROMPT_ONLY_VENDORS` selects an empty working directory. It does not provide process isolation; document the tools and host permissions of any new adapter.

## Documentation and examples

Explain the input, operation, output, and relevant limit. Use concrete terms such as adapter call, response artifact, check, and verdict. Distinguish a configured setting, an offline test, and a live observation. Quantified performance claims need a reproducible measurement.

Keep examples synthetic or sanitized, with their provenance stated. Do not commit local paths, credentials, personal configuration, or private job records. Preserve captured example output as evidence rather than polishing its wording.

Open a pull request describing the behavior change and validation. Include remaining limitations that affect use or review.
