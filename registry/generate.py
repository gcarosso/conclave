#!/usr/bin/env python3
"""Registry: JSON first, Markdown as a view.

Every section records ``observed_at`` and every probe records its own status;
failures are recorded as failures, never as "none".

  generate.py            write registry.json + REGISTRY.md next to this file
  generate.py --probe    print the JSON to stdout, write nothing

Optional inputs next to this file (copy the *.example.json files):
  config.json   launchd_prefixes (list), probe_composio (bool), extra_commands (list of {name, cmd})
  manual.json   hand-verified facts no probe can observe, each with a last_verified date

Paths: this file lives at <checkout>/registry/ and the checkout is installed as
<hub>/_system/. The hub is ``hub`` in <checkout>/shared/governance.json, or the
parent of the checkout when that key is null or the file is absent.
Python 3.9, standard library only.
"""
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
SYSTEM = HERE.parent
POLICY = SYSTEM / "router" / "policy.json"
GOV = SYSTEM / "shared" / "governance.json"
MANUAL = HERE / "manual.json"
CONFIG = HERE / "config.json"
DEFAULT_CONFIG = {"launchd_prefixes": [], "probe_composio": False, "extra_commands": []}
# Probe statuses that are not failures. Anything else is reported as a failure.
OK_STATUSES = ("ok", "skipped", "not-applicable")


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def rel(path):
    try:
        return str(Path(path).relative_to(SYSTEM))
    except ValueError:
        return str(path)


def load_json(path):
    """Return (data, error). error is None, "missing", or a parse message. Never raises."""
    try:
        return json.loads(Path(path).read_text()), None
    except FileNotFoundError:
        return None, "missing"
    except Exception as e:  # malformed file, permission error, ...
        return None, "%s: %s" % (type(e).__name__, e)


def status_of(err):
    return "ok" if err is None else ("missing" if err == "missing" else "error")


def hub_dir():
    d, _ = load_json(GOV)
    h = d.get("hub") if isinstance(d, dict) else None
    if h:
        return Path(os.path.expanduser(str(h))).resolve()
    return SYSTEM.parent


HUB = hub_dir()


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    d, err = load_json(CONFIG)
    if isinstance(d, dict):
        for k in DEFAULT_CONFIG:
            if k in d:
                cfg[k] = d[k]
    elif err is None:
        err = "config.json must be a JSON object"
    if not isinstance(cfg["launchd_prefixes"], list):
        cfg["launchd_prefixes"] = []
    if not isinstance(cfg["extra_commands"], list):
        cfg["extra_commands"] = []
    meta = {"path": rel(CONFIG), "status": status_of(err), "stderr": "" if err in (None, "missing") else err}
    return cfg, meta


def probe(cmd, timeout=25):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
        return {"status": "ok" if r.returncode == 0 else "error", "exit": r.returncode, "stdout": r.stdout, "stderr": r.stderr[-400:]}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "exit": None, "stdout": "", "stderr": "timeout after %ss" % timeout}
    except FileNotFoundError:
        return {"status": "missing", "exit": None, "stdout": "", "stderr": "command not found: %s" % cmd[0]}
    except OSError as e:
        return {"status": "error", "exit": None, "stdout": "", "stderr": str(e)}


def first_line(text):
    text = (text or "").strip()
    return text.splitlines()[0] if text else ""


def version_probe(cmd, timeout=15):
    v = probe(cmd, timeout)
    return {"status": v["status"], "value": first_line(v["stdout"]), "stderr": v["stderr"]}


def toml_mcp_servers(path):
    """Names of [mcp_servers.<name>] tables in a Codex config.toml (no TOML parser in 3.9 stdlib)."""
    names = []
    try:
        text = Path(path).read_text()
    except FileNotFoundError:
        return names, None
    except Exception as e:
        return names, "%s: %s" % (type(e).__name__, e)
    for m in re.finditer(r'^\s*\[mcp_servers\.("?)([^\]"]+)\1\]', text, re.M):
        names.append(m.group(2).strip())
    return names, None


# ---------------------------------------------------------------- vendors

def claude_section():
    s = {"observed_at": now(), "mcp": [], "skills": [], "agents": [], "probes": {}}
    cfg = Path.home() / ".claude.json"
    d, err = load_json(cfg)
    s["probes"]["claude.json"] = {"status": status_of(err), "stderr": "" if err is None else err}
    if isinstance(d, dict):
        for name in sorted(d.get("mcpServers") or {}):
            s["mcp"].append({"name": name, "scope": "user"})
        proj = (d.get("projects") or {}).get(str(HUB)) or {}
        for name in sorted(proj.get("mcpServers") or {}):
            s["mcp"].append({"name": name, "scope": "project"})
    d, err = load_json(HUB / ".mcp.json")
    if err != "missing":
        s["probes"][".mcp.json"] = {"status": status_of(err), "stderr": "" if err is None else err}
    if isinstance(d, dict):
        for name in sorted(d.get("mcpServers") or {}):
            s["mcp"].append({"name": name, "scope": "project-file"})
    for base, scope in ((Path.home() / ".claude" / "skills", "user"), (HUB / ".claude" / "skills", "project")):
        if base.is_dir():
            for sk in sorted(base.iterdir()):
                if sk.is_dir() and any((sk / n).exists() for n in ("SKILL.md", "skill.md")):
                    s["skills"].append({"name": sk.name, "scope": scope, "path": str(sk)})
    agents = HUB / ".claude" / "agents"
    s["agents"] = sorted(p.stem for p in agents.glob("*.md")) if agents.is_dir() else []
    s["probes"]["version"] = version_probe(["claude", "--version"])
    return s


def codex_section():
    s = {"observed_at": now(), "mcp": [], "agents": [], "probes": {}}
    for p, scope in ((Path.home() / ".codex" / "config.toml", "user"), (HUB / ".codex" / "config.toml", "project")):
        names, err = toml_mcp_servers(p)
        if err:
            s["probes"]["config.toml[%s]" % scope] = {"status": "error", "stderr": err}
        for n in names:
            s["mcp"].append({"name": n, "scope": scope})
    agents = HUB / ".codex" / "agents"
    s["agents"] = sorted(p.stem for p in agents.glob("*.toml")) if agents.is_dir() else []
    s["probes"]["version"] = version_probe(["codex", "--version"])
    return s


def grok_section():
    s = {"observed_at": now(), "models": [], "probes": {}}
    s["probes"]["version"] = version_probe(["grok", "--version"])
    m = probe(["grok", "models"], 90)
    s["probes"]["models"] = {"status": m["status"], "stderr": m["stderr"]}
    for line in m["stdout"].splitlines():
        mm = re.match(r"\s*[*-]\s*([a-z0-9.\-]+)", line)
        if mm:
            s["models"].append(mm.group(1))
    return s


def gemini_section():
    s = {"observed_at": now(), "api_key": "unknown", "probes": {}}
    if os.environ.get("GEMINI_API_KEY"):
        s["api_key"] = "set"
        s["probes"]["api_key"] = {"status": "ok", "source": "environment", "stderr": ""}
    else:
        shell = os.environ.get("SHELL") or "/bin/sh"
        found = None
        # login shell first (the documented path), then an interactive shell for rc-file-only exports
        for flag in ("-lc", "-ic"):
            r = probe([shell, flag, '[ -n "$GEMINI_API_KEY" ] && echo set || echo unset'], 20)
            val = r["stdout"].strip().splitlines()[-1].strip() if r["stdout"].strip() else ""
            if val in ("set", "unset"):
                found = (flag, val, r)
                if val == "set":
                    break
        if found:
            flag, val, r = found
            s["api_key"] = val
            s["probes"]["api_key"] = {"status": "ok", "source": "%s %s" % (os.path.basename(shell), flag), "stderr": ""}
        else:
            s["probes"]["api_key"] = {"status": r["status"] if r["status"] != "ok" else "error", "source": os.path.basename(shell),
                                      "stderr": r["stderr"] or "shell did not report set/unset"}
    sdk = probe(["python3", "-c", "import google.genai as g; print(getattr(g, '__version__', ''))"], 20)
    s["probes"]["sdk"] = {"status": sdk["status"], "value": first_line(sdk["stdout"]), "stderr": sdk["stderr"]}
    return s


# ---------------------------------------------------------------- optional probes

def composio_section(cfg):
    s = {"observed_at": now(), "connections": [], "probes": {}}
    if not cfg.get("probe_composio"):
        s["probes"]["connections"] = {"status": "skipped", "stderr": "probe_composio is false in registry/config.json"}
        return s
    if shutil.which("composio") is None:
        s["probes"]["connections"] = {"status": "missing", "stderr": "probe_composio is true but composio is not on PATH"}
        return s
    r = probe(["composio", "connections", "list"], 90)
    s["probes"]["connections"] = {"status": r["status"], "stderr": r["stderr"]}
    try:
        data = json.loads(r["stdout"]) if r["stdout"].strip() else {}
        items = []
        if isinstance(data, dict):
            for app, entries in data.items():
                for e in (entries if isinstance(entries, list) else [entries]):
                    items.append((app, e))
        elif isinstance(data, list):
            for e in data:
                if isinstance(e, dict):
                    items.append((e.get("app") or e.get("toolkit") or e.get("appName") or "?", e))
        for app, e in items:
            if isinstance(e, dict):
                s["connections"].append({"app": app, "id": e.get("id") or e.get("connection_id") or e.get("word_id"), "status": e.get("status")})
    except Exception as e:
        s["probes"]["connections"]["parse_error"] = str(e)
        if s["probes"]["connections"]["status"] == "ok":
            s["probes"]["connections"]["status"] = "error"
    return s


def launchd_section(cfg):
    prefixes = [str(p) for p in cfg.get("launchd_prefixes") or []]
    s = {"observed_at": now(), "jobs": [], "prefixes": prefixes, "probes": {}}
    if sys.platform != "darwin" or shutil.which("launchctl") is None:
        s["status"] = "not-applicable"
        s["probes"]["launchctl"] = {"status": "not-applicable", "stderr": "launchctl not present (not macOS)"}
        return s
    if not prefixes:
        s["status"] = "no prefixes configured"
        s["probes"]["launchctl"] = {"status": "skipped", "stderr": "no launchd_prefixes in registry/config.json"}
        return s
    lst = probe(["launchctl", "list"], 20)
    s["status"] = lst["status"]
    s["probes"]["launchctl"] = {"status": lst["status"], "stderr": lst["stderr"]}
    loaded = {}
    for line in lst["stdout"].splitlines():
        parts = line.split("\t")
        if len(parts) == 3:
            loaded[parts[2]] = {"pid": parts[0], "last_exit": parts[1]}
    agents = Path.home() / "Library" / "LaunchAgents"
    if not agents.is_dir():
        s["probes"]["LaunchAgents"] = {"status": "missing", "stderr": "%s not found" % agents}
        return s
    for plist in sorted(agents.glob("*.plist")):
        if not any(plist.name.startswith(p) for p in prefixes):
            continue
        label = plist.stem
        try:
            txt = plist.read_text(errors="replace")
        except Exception as e:
            s["probes"][plist.name] = {"status": "error", "stderr": str(e)}
            txt = ""
        wd = re.search(r"<key>WorkingDirectory</key>\s*<string>([^<]+)</string>", txt)
        wd = wd.group(1) if wd else None
        s["jobs"].append({"label": label, "plist": str(plist), "loaded": label in loaded,
                          "last_exit": loaded.get(label, {}).get("last_exit"),
                          "working_directory": wd, "working_directory_exists": bool(wd and Path(wd).exists())})
    return s


def extra_section(cfg):
    s = {"observed_at": now(), "probes": {}}
    for i, item in enumerate(cfg.get("extra_commands") or []):
        if not isinstance(item, dict) or not item.get("name") or not item.get("cmd"):
            s["probes"]["extra_commands[%d]" % i] = {"status": "error", "stderr": "entry needs both name and cmd"}
            continue
        name, cmd = str(item["name"]), item["cmd"]
        try:
            argv = [str(a) for a in cmd] if isinstance(cmd, list) else shlex.split(str(cmd))
        except ValueError as e:
            s["probes"][name] = {"status": "error", "stderr": "cannot parse cmd: %s" % e}
            continue
        if not argv:
            s["probes"][name] = {"status": "error", "stderr": "empty cmd"}
            continue
        r = probe(argv, 60)
        s["probes"][name] = {"status": r["status"], "exit": r["exit"], "value": r["stdout"].strip()[-400:], "stderr": r["stderr"]}
    return s


# ---------------------------------------------------------------- policy + manual

def models_section():
    s = {"observed_at": now(), "models": [], "ladders": {}, "probes": {}}
    p, perr = load_json(POLICY)
    g, gerr = load_json(GOV)
    s["probes"]["policy"] = {"status": status_of(perr), "path": rel(POLICY), "stderr": "" if perr is None else perr}
    s["probes"]["governance"] = {"status": status_of(gerr), "path": rel(GOV), "stderr": "" if gerr is None else gerr}
    gate = set(((g or {}).get("top_model_gate") or {}).get("models") or []) if isinstance(g, dict) else set()
    if isinstance(p, dict):
        s["models"] = [dict(m, gated=m.get("id") in gate) for m in p.get("models") or [] if isinstance(m, dict)]
        s["ladders"] = p.get("ladders") or {}
    return s


def manual_section():
    d, err = load_json(MANUAL)
    s = {"observed_at": now(), "path": rel(MANUAL), "status": status_of(err), "entries": {}}
    if err is None and not isinstance(d, dict):
        s["status"], err = "error", "manual.json must be a JSON object"
    if err not in (None, "missing"):
        s["stderr"] = err
    if isinstance(d, dict):
        s["entries"] = d
    return s


# ---------------------------------------------------------------- markdown view

def markdown(reg):
    def sec(name):
        return reg.get(name) or {}

    def pr(name, key):
        return (sec(name).get("probes") or {}).get(key) or {}

    def ver(name):
        p = pr(name, "version")
        return p.get("value") or ("probe %s" % p.get("status", "?"))

    L = ["# Registry", "",
         "Generated %s by `%s/registry/generate.py` · hub `%s`. Source of truth: `registry.json`. Failed probes are listed as failed, not omitted."
         % (reg.get("generated", "?"), SYSTEM.name, reg.get("hub", "?")), ""]
    c = sec("claude")
    L += ["## Claude (%s)" % ver("claude"),
          "- MCP: " + (", ".join("%s [%s]" % (m["name"], m["scope"]) for m in c.get("mcp") or []) or "none found (probe %s)" % pr("claude", "claude.json").get("status", "?")),
          "- Skills: " + (", ".join("%s [%s]" % (s["name"], s["scope"]) for s in c.get("skills") or []) or "none"),
          "- Agents: " + (", ".join(c.get("agents") or []) or "none"), ""]
    x = sec("codex")
    L += ["## Codex (%s)" % ver("codex"),
          "- MCP: " + (", ".join("%s [%s]" % (m["name"], m["scope"]) for m in x.get("mcp") or []) or "none"),
          "- Agents: " + (", ".join(x.get("agents") or []) or "none"), ""]
    gk = sec("grok")
    L += ["## Grok (%s)" % ver("grok"),
          "- Models: %s (probe %s)" % (", ".join(gk.get("models") or []) or "none", pr("grok", "models").get("status", "?")), ""]
    ge = sec("gemini")
    L += ["## Gemini",
          "- API key: %s (%s) · SDK probe: %s%s" % (ge.get("api_key", "?"), pr("gemini", "api_key").get("source", "?"),
                                                    pr("gemini", "sdk").get("status", "?"),
                                                    (" " + pr("gemini", "sdk")["value"]) if pr("gemini", "sdk").get("value") else ""), ""]
    co = sec("composio")
    cst = pr("composio", "connections").get("status", "?")
    L += ["## Composio (probe %s)" % cst]
    L += ["- %s (%s) [%s]" % (k.get("app"), k.get("id"), k.get("status")) for k in co.get("connections") or []] or ["- " + (pr("composio", "connections").get("stderr") or "no connections")]
    L += [""]
    ld = sec("launchd")
    L += ["## Launchd (%s)" % (ld.get("status") or pr("launchd", "launchctl").get("status", "?"))]
    if ld.get("jobs"):
        L += ["- %s: %s, last exit %s, cwd %s" % (j["label"], "loaded" if j["loaded"] else "NOT LOADED", j["last_exit"],
                                                  "ok" if j["working_directory_exists"] else "MISSING " + str(j["working_directory"])) for j in ld["jobs"]]
    else:
        L += ["- no jobs (prefixes: %s)" % (", ".join(ld.get("prefixes") or []) or "none configured")]
    L += [""]
    ex = sec("extra")
    if ex.get("probes"):
        L += ["## Extra commands"] + ["- %s: %s%s" % (n, p.get("status"), (" · " + first_line(p.get("value", ""))) if p.get("value") else "") for n, p in ex["probes"].items()] + [""]
    mo = sec("models")
    L += ["## Models (%s · gate from %s: %s)" % (pr("models", "policy").get("path", "router/policy.json"), pr("models", "governance").get("path", "shared/governance.json"),
                                                  pr("models", "governance").get("status", "?"))]
    if mo.get("models"):
        L += ["- %s · %s t%s · %s%s%s" % (m.get("id"), m.get("vendor"), m.get("tier"), "available" if m.get("available") else "UNAVAILABLE",
                                          " · gated" if m.get("gated") else "", (" · verified " + m["verified"]) if m.get("verified") else "") for m in mo["models"]]
    else:
        L += ["- none (policy probe %s)" % pr("models", "policy").get("status", "?")]
    L += [""]
    man = sec("manual")
    if man.get("entries"):
        L += ["## Manual (hand-verified facts, last_verified per entry)"]
        L += ["- %s: %s (last verified %s)" % (k, v.get("value"), v.get("last_verified")) if isinstance(v, dict) else "- %s: %s" % (k, v)
              for k, v in man["entries"].items()]
        L += [""]
    elif man.get("status") == "error":
        L += ["## Manual", "- manual.json unreadable: %s" % man.get("stderr"), ""]
    return "\n".join(L) + "\n"


# ---------------------------------------------------------------- main

def failures(reg):
    out = []
    for name, sec in reg.items():
        if isinstance(sec, dict):
            for key, p in (sec.get("probes") or {}).items():
                if isinstance(p, dict) and p.get("status") not in OK_STATUSES:
                    out.append("%s.%s=%s" % (name, key, p.get("status")))
    return out


def main():
    cfg, cfg_meta = load_config()
    reg = {"generated": now(), "checkout": str(SYSTEM), "hub": str(HUB), "config": cfg_meta,
           "claude": claude_section(), "codex": codex_section(), "grok": grok_section(), "gemini": gemini_section(),
           "composio": composio_section(cfg), "launchd": launchd_section(cfg), "extra": extra_section(cfg),
           "models": models_section(), "manual": manual_section()}
    if "--probe" in sys.argv:
        print(json.dumps(reg, indent=2))
        return 0
    (HERE / "registry.json").write_text(json.dumps(reg, indent=2) + "\n")
    (HERE / "REGISTRY.md").write_text(markdown(reg))
    failed = failures(reg)
    print("registry written to %s; probe failures: %s" % (rel(HERE / "registry.json"), ", ".join(failed) or "none"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
