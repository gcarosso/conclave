# Install

## Requirements

- Python 3.9+, Bash 3.2+, and Git.
- macOS or Linux. CI is configured for both; check the repository's Actions results for a specific revision.
- At least one installed and authenticated vendor client for live tasks.

The router and offline tests use the Python standard library. Gemini additionally requires `google-genai` in the environment used by `python3` and `GEMINI_API_KEY`. ShellCheck is optional for local linting and installed by the Linux lint job in CI.

| Adapter | Client |
|---|---|
| Claude | [Claude Code](https://code.claude.com/docs/en/overview); authenticate through its `auth` command |
| Codex | [Codex CLI](https://github.com/openai/codex); authenticate with `codex login` |
| Grok | A compatible `grok` CLI with `--single`, `--cwd`, and JSON output; inspect `router/adapters.py` for the required interface |
| Gemini | [Google Gen AI SDK](https://github.com/googleapis/python-genai); install `google-genai` and export `GEMINI_API_KEY` |

The Grok adapter is tied to that CLI interface; it is not a direct xAI API adapter. Configure model IDs for your accounts before running paid calls. `available: true` is an operator setting, not a live capability check.

## Create a hub

A hub contains domain folders and this checkout at `_system/`:

```bash
mkdir -p ~/hub && cd ~/hub
git clone https://github.com/gcarosso/conclave _system
_system/install.sh --init
```

The installer links `router/ai` to `~/.local/bin/ai`. Use `PREFIX` to select another install prefix or `--name conclave` to change the command name. It reports a missing PATH entry.

`--init` creates `shared/governance.json` from the example, sets the hub path, creates the example domains, and generates instruction files. It also creates canary files where configured. Existing governance is preserved unless `ai init --force` is used; regeneration overwrites generated instruction files.

Use a new directory for the first installation. Review existing instructions before bootstrapping a hub around an established workspace. A nonstandard `--hub DIR` is supported, but ops scripts and generated references assume the checkout is at `<hub>/_system`.

## Configure routing

Edit `_system/shared/governance.json` for the operator name, domains, and permitted vendors. Edit `_system/router/policy.json` for role defaults and model IDs. Then:

```bash
make -C ~/hub/_system generate
make -C ~/hub/_system drift-check
make -C ~/hub/_system test
```

Missing vendor clients are not automatically removed from routing. Choose an installed vendor with `--vendor`, update role defaults, or restrict the eligible set in governance. Review requires a second eligible, working vendor. [Configuration reference](configuration.md).

## Run a task

```bash
cd ~/hub/work
../_system/router/ai scout "List the files here with a one-line description" --vendor codex --dry-run
../_system/router/ai scout "List the files here with a one-line description" --vendor codex
```

Once `~/.local/bin` is on `PATH`, use `ai` directly. `ai smoke` makes a tier-1 call to each configured vendor and exits 1 if any probe fails. It consumes live usage and does not verify tier-2 or tier-3 models.

## Configure publication scans

```bash
cd ~/hub/_system
cp gate/markers.example.txt gate/markers.txt
# Edit gate/markers.txt with the patterns relevant to your material.
gate/publish-gate.sh ../public/example-repo
gate/install-hooks.sh ../public/example-repo
```

A missing or empty marker file blocks scans. The hook installer preserves unrelated existing hooks unless `--force` is specified. Hooks use this checkout's absolute path; reinstall them after moving it.

## Optional integrations

| Integration | Setup |
|---|---|
| Registry | Copy `registry/config.example.json` to `registry/config.json`; run `make registry` |
| Status page | Run `make cockpit`; the router also requests a refresh after jobs |
| Claude `/wrap` | Copy `skills/wrap` into `~/.claude/skills/` |
| Claude agents | Copy `agents/*.md` into `<hub>/.claude/agents/` |

## Upgrade or remove

Before pulling updates, inspect `git status` and preserve local changes. `router/policy.json` is tracked and may conflict with an upstream edit. Personal governance, marker files, registry configuration, and job records are ignored by Git.

After an upgrade, run `make test`, review `CHANGELOG.md`, then regenerate instructions and check drift.

To stop using the CLI, remove only the installed symlink. Archive the checkout if it contains local configuration or job history. Domain files and generated instructions remain in the hub.
