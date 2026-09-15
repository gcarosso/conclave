#!/usr/bin/env python3
"""Generate governance surfaces from shared/governance.json.

  generate.py --check                 # report drift (exit 1 if any generated file differs)
  generate.py --write                 # write all generated files
  generate.py --governance PATH ...   # use another governance file (default: shared/governance.json or $AI_GOVERNANCE)

Generated, for every domain including _publishing and _system:
  <hub>/CROSS-DOMAIN.md                 the rules every vendor reads
  <hub>/CLAUDE.md, <hub>/AGENTS.md      hub-root instructions (Claude Code reads CLAUDE.md, Codex reads AGENTS.md)
  <hub>/<domain>/CLAUDE.md, AGENTS.md   per-domain scope, data class, notes
  <hub>/<domain>/.claude/settings.json  Claude file-tool deny rules for sibling domains

Nothing here is hand-edited: change governance.json, regenerate, and `--check` in CI or the cockpit catches drift.
"""
import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SYSTEM = os.path.normpath(os.path.join(HERE, ".."))
GOV_PATH = os.environ.get("AI_GOVERNANCE") or os.path.join(SYSTEM, "shared", "governance.json")
GEN_LINE = "<!-- generated from _system/shared/governance.json — edit that file, then `make -C _system/router generate` -->"
KNOWN_RULES = ("isolation", "publish", "canary", "header", "router")


def load(path=None):
    path = path or GOV_PATH
    with open(path) as f:
        g = json.load(f)
    if not g.get("hub"):
        g["hub"] = os.path.dirname(SYSTEM)
    g["hub"] = os.path.expanduser(g["hub"])
    g.setdefault("operator", "operator")
    return g


def display_hub(g):
    """The hub path as shown in instruction files: ~-relative when it lives under $HOME."""
    hub = os.path.realpath(g["hub"])
    home = os.path.realpath(os.path.expanduser("~"))
    if hub == home or hub.startswith(home + os.sep):
        return "~" + hub[len(home):]
    return hub


def cross_domain(g):
    dc = g["data_classes"]
    r = g["rules"]
    op = g["operator"]
    private = [d for d, v in g["domains"].items() if v["kind"] != "public"]
    public = [d for d, v in g["domains"].items() if v["kind"] == "public"]
    gate = g.get("top_model_gate", {"models": [], "rule": ""})
    classes = " ".join("`%s` → %s." % (name, ", ".join(v["vendors"]) or "nobody") for name, v in dc.items())
    lines = ["# Cross-domain rules", GEN_LINE, ""]
    if "isolation" in r:
        lines += ["**Isolation.** " + r["isolation"], ""]
    lines += ["**Data classes.** %s Private by default: %s. Public: %s. A private payload reaches a wider vendor set only through a per-task declassification by %s (`ai --data-class sanitized`), recorded in the job contract." % (classes, " ".join(private) or "none", " ".join(public) or "none", op), ""]
    if gate.get("models"):
        unavailable = g.get("unavailable_models") or []
        lines += ["**Top models.** %s: %s%s" % (", ".join(gate["models"]), gate.get("rule", ""), (" Unavailable on current accounts: %s." % ", ".join(unavailable)) if unavailable else ""), ""]
    if "publish" in r:
        lines += ["**Publish.** " + r["publish"], ""]
    if "canary" in r:
        lines += ["**Canaries.** " + r["canary"], ""]
    if "header" in r:
        lines += ["**Header.** Start every response with `%s`." % r["header"], ""]
    if "router" in r:
        lines += ["**Router.** " + r["router"], ""]
    for k, v in r.items():
        if k not in KNOWN_RULES:
            lines += ["**%s.** %s" % (k.capitalize(), v), ""]
    return "\n".join(lines)


def root_file(g, vendor):
    who = "Claude" if vendor == "claude" else "Codex"
    hdr = g["rules"].get("header", "Orchestration: <role> <vendor>/<model>")
    return f"""# {display_hub(g)} — hub root ({who})
{GEN_LINE}

Domain work happens inside a domain directory; only cross-domain queries and hub administration that {g['operator']} explicitly requests run from here. Read `CROSS-DOMAIN.md` first. Start every response with `{hdr}`.

- Router and policy: `_system/router/ai`, `_system/router/policy.json`
- Governance source: `_system/shared/governance.json` (regenerate with `make -C _system/router generate`)
- Registry: `_system/registry/REGISTRY.md` · Ops: `_system/ops/` · Gate: `_system/gate/publish-gate.sh`
- One writer per file set. Archive, never delete.
"""


def domain_file(g, name, vendor):
    d = g["domains"][name]
    vendors = d.get("vendors", g["vendors"])
    hdr = g["rules"].get("header", "Orchestration: <role> <vendor>/<model>")
    notes = "\n".join(f"- {n}" for n in d.get("notes", []))
    canary = f"\n- Contains `{d['canary']}` for sandbox verification." if d.get("canary") else ""
    return f"""# {name}/ — {d['title']}
{GEN_LINE}

Read `../CROSS-DOMAIN.md`. Start every response with `{hdr}`.

**Scope.** Work inside `{display_hub(g)}/{name}/`. Do not read or write outside it.{' Claude file-tool deny rules are in .claude/settings.json; shell and other tools require separate controls.' if vendor == 'claude' else ''}

**Data class.** `{d['default_data_class']}` → eligible vendors: {', '.join(v for v in vendors if v in g['data_classes'][d['default_data_class']]['vendors'])}.
{('**Notes.**' + chr(10) + notes) if notes else ''}{canary}
"""


def settings(g, name):
    hub = g["hub"]
    others = [d for d in g["domains"] if d != name]
    deny = []
    for o in others:
        for op in ("Read", "Edit", "Write"):
            deny.append(f"{op}(/{os.path.abspath(os.path.join(hub, o))}/**)")
    return json.dumps({"permissions": {"deny": deny}}, indent=2) + "\n"


def targets(g):
    hub = g["hub"]
    out = {
        os.path.join(hub, "CROSS-DOMAIN.md"): cross_domain(g),
        os.path.join(hub, "CLAUDE.md"): root_file(g, "claude"),
        os.path.join(hub, "AGENTS.md"): root_file(g, "codex"),
    }
    for name in g["domains"]:
        out[os.path.join(hub, name, "CLAUDE.md")] = domain_file(g, name, "claude")
        out[os.path.join(hub, name, "AGENTS.md")] = domain_file(g, name, "codex")
        out[os.path.join(hub, name, ".claude", "settings.json")] = settings(g, name)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--governance")
    a = ap.parse_args()
    path = a.governance or GOV_PATH
    if not os.path.exists(path):
        print("no governance file at %s — run `ai init`" % path)
        return 2
    g = load(path)
    t = targets(g)
    drift = []
    for p, content in t.items():
        cur = open(p).read() if os.path.exists(p) else None
        if cur != content:
            drift.append(p)
    if a.write:
        for p, content in t.items():
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w") as f:
                f.write(content)
        print(f"wrote {len(t)} files ({len(drift)} changed)")
        return 0
    for p in drift:
        print("DRIFT", os.path.relpath(p, g["hub"]))
    print(f"{len(t)} generated targets, {len(drift)} drifted")
    biggest = max(len(c) for c in t.values())
    print(f"largest generated file: {biggest} bytes (~{biggest // 4} tokens)")
    return 1 if (a.check and drift) else 0


if __name__ == "__main__":
    sys.exit(main())
