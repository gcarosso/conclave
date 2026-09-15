# Troubleshooting

| Symptom | Check |
|---|---|
| `ai: command not found` | Add the install directory to `PATH`, or use `<hub>/_system/router/ai` directly |
| Missing governance | Run `router/ai init` from the intended checkout, then inspect `shared/governance.json` |
| Outside-hub routing error | Change to a configured domain or pass `--domain` |
| Vendor refused | Compare domain and data-class vendor sets. Declassify only material you have reviewed |
| Missing client or authentication failure | Install/authenticate that client or choose a configured, working vendor. Routing does not detect missing clients automatically |
| Unknown or unavailable model | Update `policy.json` from your account's supported models. Check the ladder and model entry together |
| Gated model refused | Supply explicit approval when appropriate; noninteractive calls cannot answer a prompt |
| Review blocked | Inspect `review-raw.txt`, reviewer request/result files, eligibility, and remaining call budget |
| `pass` despite incorrect content | Inspect the declared checks. The default scout check only measures response length |
| `ai accept` blocks review checks | It reruns deterministic checks only. Start a new reviewed job for a fresh review |
| Write set locked | Find the owning job in the lock file and confirm its process status. Do not unlink an active lock file; OS locks release on process exit |
| Gate blocks | Read the finding or scan error. Check marker configuration, permissions, index state, and revision range |
| No upstream for a scan | Supply an explicit revision range; installed pre-push hooks derive one from pushed refs |
| Governance drift | Edit the source JSON, then run `make generate` and `make drift-check` |
| Registry says a client exists but a task fails | A version probe does not verify login, quota, or model access |
| `?` in recent jobs | No standard acceptance record exists; check for council/consensus output or an interrupted job |
| `auto --dry-run` shows no selected route | Classification was intentionally skipped. Preview an explicit role |

For a reproducible issue, include the command, package revision, platform, client version, and relevant sanitized job records. Remove prompts, identifiers, paths, and credentials that should not be public.
