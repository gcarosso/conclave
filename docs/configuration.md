# Configuration

Four files, one concern each. Every real file is gitignored; every shipped example is the documentation.

| File | Concern | Shipped example |
|---|---|---|
| `shared/governance.json` | who you are, your domains, data classes, the gate, the rules | `shared/governance.example.json` |
| `router/policy.json` | roles, model allowlist, ladders, timeouts, limits, reviewer pairing, council | committed (edit in place) |
| `gate/markers.txt` | what must never reach a public repo | `gate/markers.example.txt` |
| `registry/config.json` | what the registry probes beyond the defaults | `registry/config.example.json` |

## `shared/governance.json`

```jsonc
{
  "version": 1,
  "operator": "you",              // name written into approval and declassification records and instruction files
  "hub": "/path/to/hub",          // null → parent directory of this checkout; `ai init` writes the resolved path
  "vendors": ["claude", "codex", "grok", "gemini"],   // every vendor the hub may ever use

  "data_classes": {
    "private":   {"vendors": ["claude", "codex"], "meaning": "…"},
    "sanitized": {"vendors": ["claude", "codex", "grok", "gemini"], "meaning": "…"},
    "public":    {"vendors": ["claude", "codex", "grok", "gemini"], "meaning": "…"}
  },

  "top_model_gate": {
    "models": ["claude-fable-5-1", "gpt-6-astra"],   // mirrors requires_approval in policy.json; used in generated text
    "rule": "…"                                       // the sentence vendors read
  },
  "unavailable_models": [],       // listed in CROSS-DOMAIN.md so agents stop asking for them

  "domains": {
    "work": {
      "kind": "private",                 // private | public | staging | system
      "default_data_class": "private",
      "title": "Projects, drafts, working notes",
      "notes": ["…"],                    // bullets in the domain's instruction file
      "canary": ".canary-sandbox",       // optional file that must be unreadable from other domains
      "vendors": ["claude", "codex"]     // optional: restrict this domain below the hub-wide list
    },
    "public":      {"kind": "public",  "default_data_class": "public",  "title": "…"},
    "_publishing": {"kind": "staging", "default_data_class": "private", "title": "…"},
    "_system":     {"kind": "system",  "default_data_class": "private", "vendors": ["claude", "codex"], "title": "…"}
  },

  "rules": {                       // rendered into CROSS-DOMAIN.md; known keys get their paragraph, any other key is appended
    "header": "Orchestration: <role> <vendor>/<model>",
    "isolation": "…", "publish": "…", "canary": "…", "router": "…"
  }
}
```

**Eligibility** for a job is `domains[d].vendors ∩ data_classes[c].vendors` (domain vendors default to the hub-wide list). A vendor absent from both a domain and a class is never even a candidate.

**`_system` is a domain** like any other, with the checkout as its directory; keep its vendors to those with local sandboxes.

After any edit: `make generate`, then `make drift-check` should say `0 drifted`. Add a domain → also `mkdir -p <hub>/<domain>/.ai/jobs`.

### What the generator writes

| Target | Content |
|---|---|
| `<hub>/CROSS-DOMAIN.md` | Isolation, data classes, top models, publish, canaries, header, router, plus any extra rule keys |
| `<hub>/CLAUDE.md`, `<hub>/AGENTS.md` | Hub-root instructions for Claude Code and Codex |
| `<hub>/<domain>/CLAUDE.md`, `AGENTS.md` | Scope, data class → eligible vendors, notes, canary |
| `<hub>/<domain>/.claude/settings.json` | `permissions.deny` for Read/Edit/Write on every sibling domain (absolute paths; this is what makes Claude Code's isolation technical) |

Paths shown in instruction files are `~`-relative when the hub is under your home directory, so a public domain's `CLAUDE.md` never contains an absolute home path.

## `router/policy.json`

```jsonc
{
  "roles": {
    "scout": {
      "description": "Quick lookup or triage",
      "default_vendor": "claude",
      "default_tier": 1,
      "max_turns": 5,                 // agentic turn budget passed to the vendor CLI
      "codex_sandbox": "read-only",   // read-only | workspace-write; also decides the contract's write set and effects
      "review": false,                // cross-vendor review by default
      "hub_only": false               // optional: refuse outside _system
    },
    "code":  {"default_vendor": "codex", "default_tier": 2, "max_turns": 30, "codex_sandbox": "workspace-write", "review": true},
    "write": {"default_vendor": "claude", "default_tier": 2, "max_turns": 15, "codex_sandbox": "workspace-write", "review": true},
    "live":  {"default_vendor": "grok", "default_tier": 2, "max_turns": 40, "codex_sandbox": "read-only", "review": false}
  },

  "models": [                        // THE ALLOWLIST: the router launches nothing else
    {"id": "claude-haiku-4-5-20251001", "vendor": "claude", "tier": 1, "requires_approval": false, "available": true, "billing": "subscription"},
    {"id": "claude-fable-5-1",          "vendor": "claude", "tier": 3, "requires_approval": true,  "available": true, "billing": "subscription"},
    {"id": "gemini-3.5-pro",            "vendor": "gemini", "tier": 3, "requires_approval": false, "available": false, "note": "…"}
  ],

  "ladders": {                       // tier → model id, per vendor; every tier must resolve to an available model
    "claude": {"1": "claude-haiku-4-5-20251001", "2": "claude-sonnet-5", "3": "claude-fable-5-1"},
    "gemini": {"1": "gemini-3.5-flash-lite", "2": "gemini-3.5-flash", "3": "gemini-3.5-flash"}
  },

  "timeouts_s": {"1": 240, "2": 900, "3": 1200},   // per tier, per attempt
  "limits": {"repairs": 1, "escalations": 1, "review_max_chars": 80000, "calls": 6},
  "reviewer_for": {"claude": "codex", "codex": "claude", "grok": "claude", "gemini": "claude"},
  "council": {"members": ["claude", "codex"], "tier": 2, "judge_vendor": "claude", "judge_tier": 3}
}
```

- **Model ids change.** When a vendor renames or retires a model, edit the entry and the ladder, then `ai smoke`. Mark an id `"available": false` rather than deleting it if you want the router to explain the refusal.
- **`requires_approval`** is the gate. Keep `governance.top_model_gate.models` in step so the generated rules say the same thing.
- **`reviewer_for`** names the preferred reviewer; if that vendor is not eligible for the job's data class, the next eligible vendor other than the writer is used.
- **Adding a role** needs only an entry here (and a line in `ROLE_PROMPT` in `router/ai` if it wants a system prompt).

## `gate/markers.txt`

One POSIX extended regex per line; blank lines and `#` comments ignored; matched case-insensitively.

```
# home-directory paths — never in a public repo
/Users/[a-z0-9_.-]+/
/home/[a-z0-9_.-]+/
# private folder or project names
acme-private
# your personal email (put the real one here)
someone@example\.com
# secrets
BEGIN (RSA |OPENSSH |EC )?PRIVATE KEY
AKIA[0-9A-Z]{16}
```

Resolution order: `--markers FILE` → `$PUBLISH_GATE_MARKERS` → `<target repo>/.publish-gate-markers` → `gate/markers.txt`. A path given by flag or variable that does not exist **blocks** (misconfiguration must not silently switch marker sets). No markers at all blocks.

Exceptions: `<target repo>/.publish-gate-allow`, one exact finding line per entry (as printed by the gate, e.g. `README.md:12:contact someone@example.com`). Review these by hand; they are the only way past the gate.

## `registry/config.json`

```jsonc
{
  "launchd_prefixes": ["com.example."],   // macOS LaunchAgents to report (label prefixes); [] → section says "no prefixes configured"
  "probe_composio": false,                // run `composio connections list` if the CLI is on PATH
  "extra_commands": [                     // any command whose exit code you want recorded
    {"name": "docker", "cmd": ["docker", "--version"]}
  ]
}
```

`registry/manual.json` holds facts no probe can discover (a cloud connector, an account tier), each with `value` and `last_verified`.

## Environment variables

See [usage.md](usage.md#environment-variables).
