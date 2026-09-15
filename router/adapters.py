"""Vendor transports. The only place a vendor CLI or SDK is invoked.

Every adapter returns the same envelope:
  execution_status  succeeded | failed | timeout
  exit_code, text, session_id, input_tokens, output_tokens, cost_usd (None = unknown), billing,
  elapsed_s, error, raw_stdout, raw_stderr

Adding a vendor: write one function with this signature and envelope, add it to `run`, add its
models and ladder to policy.json, and add its name to `vendors` in governance.json.
PROMPT_ONLY_VENDORS selects an empty working directory for adapters that do not need project files.
This reduces incidental context; it does not restrict a local process's host access.
"""
import json
import os
import subprocess
import tempfile
import time

VENDORS = ("claude", "codex", "grok", "gemini")
PROMPT_ONLY_VENDORS = ("grok", "gemini")


def envelope(**kw):
    base = {
        "execution_status": "failed", "exit_code": None, "text": "", "session_id": None,
        "input_tokens": None, "output_tokens": None, "cost_usd": None, "billing": None,
        "elapsed_s": None, "error": None, "raw_stdout": "", "raw_stderr": "",
    }
    base.update(kw)
    return base


def _run(cmd, cwd, timeout, env=None):
    start = time.time()
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                           env=env, stdin=subprocess.DEVNULL)
        return r.returncode, r.stdout or "", r.stderr or "", round(time.time() - start, 1), None
    except subprocess.TimeoutExpired:
        return None, "", "timeout after %ss" % timeout, round(time.time() - start, 1), "timeout"
    except FileNotFoundError as e:
        return None, "", str(e), 0.0, "cli-not-found"


def _env_with_gemini_key():
    """GEMINI_API_KEY from the environment, else from a login shell (for keys exported in a profile)."""
    env = dict(os.environ)
    if not env.get("GEMINI_API_KEY"):
        shell = os.environ.get("SHELL") or "/bin/sh"
        try:
            out = subprocess.run([shell, "-lc", 'printf %s "$GEMINI_API_KEY"'],
                                 capture_output=True, text=True, timeout=20, stdin=subprocess.DEVNULL).stdout.strip()
            if out:
                env["GEMINI_API_KEY"] = out
        except Exception:
            pass
    return env


def _last_json(out):
    for line in reversed(out.strip().splitlines()):
        try:
            return json.loads(line)
        except Exception:
            continue
    try:
        return json.loads(out)
    except Exception:
        return {}


def claude(model, prompt, cwd, timeout, settings=None, max_turns=10, json_schema=None, no_tools=False):
    cmd = ["claude", "-p", "--model", model, "--output-format", "json", "--max-turns", str(max_turns)]
    if settings and os.path.exists(settings):
        cmd += ["--settings", settings]
    if json_schema:
        cmd += ["--json-schema", json.dumps(json_schema)]
    if no_tools:
        cmd += ["--tools", "", "--strict-mcp-config", "--disable-slash-commands"]
    cmd.append(prompt)
    rc, out, err, el, e = _run(cmd, cwd, timeout)
    env = envelope(exit_code=rc, elapsed_s=el, error=e, billing="subscription", raw_stdout=out, raw_stderr=err)
    if e:
        env["execution_status"] = "timeout" if e == "timeout" else "failed"
        return env
    d = _last_json(out) if out.strip() else {}
    if not isinstance(d, dict):
        d = {}
    text = d.get("result", "")
    if d.get("structured_output") is not None:
        text = json.dumps(d["structured_output"])
    u = d.get("usage") or {}
    env.update(text=text or out, session_id=d.get("session_id"),
               input_tokens=u.get("input_tokens"), output_tokens=u.get("output_tokens"),
               cost_usd=d.get("total_cost_usd"))
    ok = rc == 0 and not d.get("is_error") and bool((text or "").strip())
    env["execution_status"] = "succeeded" if ok else "failed"
    if not ok:
        env["error"] = (text or err or out)[-2000:] or "empty output"
    return env


def codex(model, prompt, cwd, timeout, sandbox="read-only", network=False, output_schema=None):
    fd, last = tempfile.mkstemp(prefix="ai-codex-", suffix=".md")
    os.close(fd)
    cmd = ["codex", "exec", "-m", model, "-s", sandbox, "-C", cwd, "--skip-git-repo-check",
           "--ephemeral", "--json", "-o", last]
    schema_path = None
    if network and sandbox != "read-only":
        cmd += ["-c", "sandbox_workspace_write.network_access=true"]
    if output_schema:
        fd2, schema_path = tempfile.mkstemp(prefix="ai-codex-schema-", suffix=".json")
        os.close(fd2)
        with open(schema_path, "w") as f:
            json.dump(output_schema, f)
        cmd += ["--output-schema", schema_path]
    cmd.append(prompt)
    rc, out, err, el, e = _run(cmd, cwd, timeout)
    text = ""
    if os.path.exists(last):
        with open(last) as f:
            text = f.read()
        os.unlink(last)
    if schema_path and os.path.exists(schema_path):
        os.unlink(schema_path)
    usage, sid = {}, None
    for line in out.splitlines():
        try:
            o = json.loads(line)
        except Exception:
            continue
        if not isinstance(o, dict):
            continue
        if isinstance(o.get("usage"), dict):
            usage = o["usage"]
        if o.get("type") == "thread.started":
            sid = o.get("thread_id") or o.get("id")
    env = envelope(exit_code=rc, elapsed_s=el, error=e, billing="subscription", raw_stdout=out, raw_stderr=err,
                   text=text, session_id=sid, input_tokens=usage.get("input_tokens"),
                   output_tokens=usage.get("output_tokens"), cost_usd=None)
    if e:
        env["execution_status"] = "timeout" if e == "timeout" else "failed"
        return env
    ok = rc == 0 and bool(text.strip())
    env["execution_status"] = "succeeded" if ok else "failed"
    if not ok:
        env["error"] = (err or out)[-2000:] or "empty output"
    return env


def grok(model, prompt, cwd, timeout, max_turns=20, json_schema=None, web_search=True):
    cmd = ["grok", "--model", model, "--cwd", cwd, "--max-turns", str(max_turns),
           "--always-approve", "--output-format", "json"]
    if not web_search:
        cmd.append("--disable-web-search")
    if json_schema:
        cmd += ["--json-schema", json.dumps(json_schema)]
    cmd += ["--single", prompt]
    rc, out, err, el, e = _run(cmd, cwd, timeout)
    env = envelope(exit_code=rc, elapsed_s=el, error=e, billing="subscription", raw_stdout=out, raw_stderr=err)
    if e:
        env["execution_status"] = "timeout" if e == "timeout" else "failed"
        return env
    d = _last_json(out) if out.strip() else {}
    if not isinstance(d, dict):
        d = {}
    u = d.get("usage") or {}
    text = d.get("text") if isinstance(d.get("text"), str) else out
    env.update(text=text, session_id=d.get("sessionId"),
               input_tokens=u.get("input_tokens", u.get("prompt_tokens")),
               output_tokens=u.get("output_tokens", u.get("completion_tokens")),
               cost_usd=d.get("total_cost_usd"))
    ok = rc == 0 and bool((text or "").strip())
    env["execution_status"] = "succeeded" if ok else "failed"
    if not ok:
        env["error"] = (err or out)[-2000:] or "empty output"
    return env


_GEMINI_SNIPPET = r'''
import json, os, sys, warnings
warnings.filterwarnings("ignore")
from google import genai
p = json.load(open(sys.argv[1]))
c = genai.Client(api_key=os.environ["GEMINI_API_KEY"])
r = c.models.generate_content(model=p["model"], contents=p["prompt"])
um = getattr(r, "usage_metadata", None)
usage = {"input_tokens": getattr(um, "prompt_token_count", None), "output_tokens": getattr(um, "candidates_token_count", None)} if um else {}
print(json.dumps({"text": r.text or "", "usage": usage}))
'''


def gemini(model, prompt, cwd, timeout):
    env_ = _env_with_gemini_key()
    if not env_.get("GEMINI_API_KEY"):
        return envelope(error="GEMINI_API_KEY not set", billing="api_key")
    fd, pf = tempfile.mkstemp(prefix="ai-gemini-", suffix=".json")
    os.close(fd)
    with open(pf, "w") as f:
        json.dump({"model": model, "prompt": prompt}, f)
    rc, out, err, el, e = _run(["python3", "-c", _GEMINI_SNIPPET, pf], cwd, timeout, env=env_)
    os.unlink(pf)
    env = envelope(exit_code=rc, elapsed_s=el, error=e, billing="api_key", raw_stdout=out, raw_stderr=err)
    if e:
        env["execution_status"] = "timeout" if e == "timeout" else "failed"
        return env
    d = _last_json(out) if out.strip() else {}
    if not isinstance(d, dict):
        d = {}
    u = d.get("usage") or {}
    text = d.get("text", "")
    env.update(text=text, input_tokens=u.get("input_tokens"), output_tokens=u.get("output_tokens"), cost_usd=None)
    ok = rc == 0 and bool(text.strip())
    env["execution_status"] = "succeeded" if ok else "failed"
    if not ok:
        env["error"] = (err or out)[-2000:] or "empty output"
    return env


def run(vendor, model, prompt, cwd, timeout, sandbox="read-only", network=False, settings=None,
        max_turns=10, json_schema=None, web_search=True, no_tools=False):
    """Uniform entry point. json_schema (a JSON Schema dict) requests structured output where the vendor supports it."""
    if vendor == "claude":
        return claude(model, prompt, cwd, timeout, settings=settings, max_turns=max_turns, json_schema=json_schema, no_tools=no_tools)
    if vendor == "codex":
        return codex(model, prompt, cwd, timeout, sandbox=sandbox, network=network, output_schema=json_schema)
    if vendor == "grok":
        return grok(model, prompt, cwd, timeout, max_turns=max_turns, json_schema=json_schema, web_search=web_search)
    if vendor == "gemini":
        return gemini(model, prompt, cwd, timeout)
    return envelope(error="unknown vendor %s" % vendor)
