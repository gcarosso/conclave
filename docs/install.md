# Install

Ten minutes from clone to first verdict. Nothing here needs sudo or a package manager beyond the vendor CLIs you already use.

## 1. Prerequisites

| Need | Why | Check |
|---|---|---|
| Python 3.9+ | the router, generator, registry | `python3 --version` |
| Bash 3.2+ | the gate, cockpit, handoffs (macOS's default bash is fine) | `bash --version` |
| git | the gate's `--staged` / `--diff` modes and hooks | `git --version` |
| macOS or Linux | tested on both in CI | |

Vendor CLIs are **optional individually**. A vendor you do not install is never routed to; `ai smoke` reports it as failed and every role that defaults to it can be redirected in `policy.json`.

| Vendor | What the router calls | Setup |
|---|---|---|
| Claude | `claude -p --output-format json` | Install [Claude Code](https://claude.com/claude-code), run `claude login` |
| Codex | `codex exec --json` | Install the [Codex CLI](https://github.com/openai/codex), run `codex login` |
| Grok | `grok --single --output-format json` | Install the Grok CLI, run `grok login` |
| Gemini | the `google-genai` Python SDK | `pip install google-genai` and `export GEMINI_API_KEY=…` in your shell profile |

## 2. Get the code

Conclave is designed to live at `<hub>/_system`, where `<hub>` is a folder whose subfolders are your domains. Pick a hub location (any name; `~/hub` below) and clone into it:

```bash
mkdir -p ~/hub && cd ~/hub
git clone https://github.com/gcarosso/conclave _system
```

If you already have a folder of projects you want to govern, that folder is your hub: clone `_system` into it.

## 3. Install the CLI and bootstrap the hub

```bash
_system/install.sh --init
```

This does four things, all reversible:

1. Symlinks `_system/router/ai` to `~/.local/bin/ai` (set `PREFIX=/usr/local` for `/usr/local/bin`, or `--name conclave` to link under another name). It tells you if `~/.local/bin` is not on your PATH.
2. Reports which prerequisites and vendor CLIs it found.
3. Runs `ai init`: copies `shared/governance.example.json` to `shared/governance.json` with `hub` set to `~/hub`, creates a folder for every domain in it (`work/`, `personal/`, `public/`, `_publishing/`) with a `.ai/jobs/` inside and a `.canary-sandbox` file where the governance asks for one.
4. Runs the generator: `CROSS-DOMAIN.md`, `CLAUDE.md` and `AGENTS.md` at the hub root and in every domain, and `.claude/settings.json` deny rules in every domain.

Without `--init` the installer only links the CLI and prints the next steps; run `ai init` yourself when ready. `ai init --hub DIR` bootstraps a hub somewhere other than the parent of the checkout.

## 4. Make the governance yours

Open `_system/shared/governance.json` and edit:

- `operator` — your name; it appears in approval records and instruction files.
- `domains` — rename or add. Each needs `kind` (`private`, `public`, `staging`, `system`), `default_data_class`, `title`; optionally `notes`, `canary`, and `vendors` to restrict who may work there.
- `data_classes` — which vendors may see `private`, `sanitized`, `public` payloads. The example admits only Claude and Codex to private; widen it deliberately.
- `top_model_gate` — the model ids that need per-use approval.

Then regenerate and create any new domain folders:

```bash
make -C ~/hub/_system generate
mkdir -p ~/hub/<new-domain>/.ai/jobs
```

`make -C ~/hub/_system drift-check` must report `0 drifted` afterwards. The full reference is [configuration.md](configuration.md).

## 5. Verify the vendors

```bash
ai smoke
```

```
claude  claude-haiku-4-5-20251001    OK  (4.1s, in=12 out=5)
codex   gpt-5.6-luna                 OK  (6.8s, in=None out=None)
grok    grok-4.5                     OK  (3.2s, in=9 out=4)
gemini  gemini-3.5-flash-lite        OK  (1.1s, in=8 out=3)
```

A `FAIL` names the reason (CLI not found, not logged in, key unset, model rejected). Fix it or edit `_system/router/policy.json`: mark the model `"available": false`, or point the ladder at an id the vendor actually serves. The ids shipped in `policy.json` are an allowlist, not a promise.

## 6. First job

```bash
cd ~/hub/work
ai scout "List the files here with one line each on what they are"
ai roles
ai jobs
```

Open the job directory the last line names. You will find `contract.json`, `events.jsonl`, `attempts/1/`, `verdict.json`, `acceptance.json`, `result.md`. That folder is the unit of work everything else builds on; [usage.md](usage.md#reading-a-job-folder) walks through it.

## 7. Publication safety (recommended)

```bash
cp ~/hub/_system/gate/markers.example.txt ~/hub/_system/gate/markers.txt
$EDITOR ~/hub/_system/gate/markers.txt         # add your home path, private folder names, email, secrets prefixes
~/hub/_system/gate/publish-gate.sh ~/hub/public/<repo>
~/hub/_system/gate/install-hooks.sh ~/hub/public/<repo>   # pre-commit (--staged) and pre-push (--diff)
```

The gate blocks on a missing markers file by design, so this step is required before the first publish. `make -C ~/hub/_system gate-test` runs the fixtures.

## 8. Optional pieces

| Piece | Install | What you get |
|---|---|---|
| Registry | `cp registry/config.example.json registry/config.json` then `make -C ~/hub/_system registry` | `REGISTRY.md` of what is actually reachable; `make audit` for the diff |
| Cockpit | nothing; runs after every job | `~/hub/STATUS.md`; run `make -C ~/hub/_system cockpit` any time |
| Claude Code skill `/wrap` | `mkdir -p ~/.claude/skills && cp -R ~/hub/_system/skills/wrap ~/.claude/skills/` | session handoff + safe archive |
| Claude Code agents | `mkdir -p ~/hub/.claude/agents && cp ~/hub/_system/agents/*.md ~/hub/.claude/agents/` | "check this for private markers", "audit the registry" |
| Vendor failover | nothing | `~/hub/_system/ops/handoff-to-vendor.sh codex "task"` prints the command that hands the coordinator seat over |

## 9. Uninstall

```bash
rm ~/.local/bin/ai
rm -rf ~/hub/_system                      # the package
# your hub, domains, jobs and generated instruction files stay; delete them yourself if you want them gone
```

## Upgrading

`git -C ~/hub/_system pull`, then `make -C ~/hub/_system test` and `make -C ~/hub/_system generate` (the generator's templates may have changed). Your `governance.json`, `policy.json` edits, `markers.txt`, registry config and jobs are gitignored and untouched; check `CHANGELOG.md` for schema changes.
