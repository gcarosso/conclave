"""Deterministic checks, structured review, and the acceptance decision.

Acceptance is decided here from contract-declared checks. Workers never award PASS.
"""
import hashlib
import json
import os
import re
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))


# ---------- minimal JSON-schema validator (type / enum / required / properties / items / additionalProperties) ----------

def validate(obj, schema, path="$"):
    errs = []
    t = schema.get("type")
    if t:
        types = t if isinstance(t, list) else [t]
        ok = False
        for tt in types:
            if tt == "object" and isinstance(obj, dict): ok = True
            elif tt == "array" and isinstance(obj, list): ok = True
            elif tt == "string" and isinstance(obj, str): ok = True
            elif tt == "integer" and isinstance(obj, int) and not isinstance(obj, bool): ok = True
            elif tt == "number" and isinstance(obj, (int, float)) and not isinstance(obj, bool): ok = True
            elif tt == "boolean" and isinstance(obj, bool): ok = True
            elif tt == "null" and obj is None: ok = True
        if not ok:
            return ["%s: expected %s" % (path, t)]
    if "enum" in schema and obj not in schema["enum"]:
        errs.append("%s: %r not in %s" % (path, obj, schema["enum"]))
    if isinstance(obj, dict):
        for r in schema.get("required", []):
            if r not in obj:
                errs.append("%s: missing %s" % (path, r))
        props = schema.get("properties", {})
        for k, v in obj.items():
            if k in props:
                errs += validate(v, props[k], path + "." + k)
            elif schema.get("additionalProperties") is False:
                errs.append("%s: unexpected field %s" % (path, k))
    if isinstance(obj, list) and "items" in schema:
        for i, v in enumerate(obj):
            errs += validate(v, schema["items"], "%s[%d]" % (path, i))
    return errs


def load_schema(name):
    with open(os.path.join(HERE, name)) as f:
        return json.load(f)


def sha256_text(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ---------- checks ----------

def run_builtin(rule, artifact_text, job_dir):
    if rule in ("nonempty", "markdown_nonempty"):
        ok = bool(artifact_text.strip()) and len(artifact_text.strip()) > 20
        return ("pass" if ok else "fail", "artifact length %d" % len(artifact_text))
    if rule.startswith("contains:"):
        needle = rule[len("contains:"):]
        ok = needle in artifact_text
        return ("pass" if ok else "fail", "contains %r" % needle)
    if rule.startswith("not_contains:"):
        needle = rule[len("not_contains:"):]
        ok = needle not in artifact_text
        return ("pass" if ok else "fail", "absent %r" % needle)
    if rule.startswith("regex:"):
        ok = re.search(rule[len("regex:"):], artifact_text, re.M) is not None
        return ("pass" if ok else "fail", "regex %r" % rule[6:])
    if rule.startswith("file_exists:"):
        p = rule[len("file_exists:"):]
        p = p if os.path.isabs(p) else os.path.join(job_dir, p)
        ok = os.path.exists(p) and os.path.getsize(p) > 0
        return ("pass" if ok else "fail", "file %s" % p)
    if rule.startswith("min_words:"):
        n = int(rule[len("min_words:"):])
        w = len(artifact_text.split())
        return ("pass" if w >= n else "fail", "%d words (min %d)" % (w, n))
    return ("blocked", "unknown builtin rule %r" % rule)


def run_command(rule, cwd, timeout=300):
    try:
        r = subprocess.run(rule, shell=True, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                           stdin=subprocess.DEVNULL)
        tail = (r.stdout + r.stderr)[-500:].strip()
        return ("pass" if r.returncode == 0 else "fail", "exit %s: %s" % (r.returncode, tail))
    except subprocess.TimeoutExpired:
        return ("blocked", "command timed out after %ss" % timeout)


REVIEW_PROMPT = """You are a fresh-context reviewer. You did not write this artifact and must not edit anything.
Judge ONLY the artifact against the goal and the listed checks. Cite evidence by quoting ≤20 words or naming a line.

GOAL
{goal}

CHECKS TO JUDGE (review kind)
{checks}

ARTIFACT (sha256 {sha})
-----
{artifact}
-----

Return ONLY a JSON object with exactly these fields:
{{"checks":[{{"id":"<check id>","status":"pass|fail|blocked","evidence":"<quote or line>"}}],
  "issues":[{{"id":"R1","severity":"critical|major|minor","problem":"...","fix":"...","capability_deficit":false}}]}}
Every listed check must appear once. Mark a check "blocked" only when the artifact does not contain enough to judge it.
Set capability_deficit true only when the failure needs a stronger model, not a correction."""

REVIEW_OUTPUT_SCHEMA = {
    "type": "object", "additionalProperties": False, "required": ["checks", "issues"],
    "properties": {
        "checks": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["id", "status", "evidence"],
                   "properties": {"id": {"type": "string"}, "status": {"type": "string", "enum": ["pass", "fail", "blocked"]}, "evidence": {"type": "string"}}}},
        "issues": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["id", "severity", "problem", "fix", "capability_deficit"],
                   "properties": {"id": {"type": "string"}, "severity": {"type": "string", "enum": ["critical", "major", "minor"]},
                                  "problem": {"type": "string"}, "fix": {"type": "string"}, "capability_deficit": {"type": "boolean"}}}},
    },
}


def parse_review(text):
    text = text.strip()
    try:
        return json.loads(text)
    except Exception:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            return json.loads(m.group(0))
        except Exception:
            return None
    return None


def evaluate(contract, artifact_text, job_dir, attempt_dir, reviewer=None, execution_status="succeeded"):
    """Return (verdict_dict, acceptance_status). reviewer = callable(prompt, json_schema) -> envelope, or None."""
    limits = contract.get("limits", {})
    checks_out, issues = [], []
    review_checks = [c for c in contract["checks"] if c["kind"] == "review"]
    sha = sha256_text(artifact_text)

    if execution_status != "succeeded":
        for c in contract["checks"]:
            checks_out.append({"id": c["id"], "status": "blocked", "evidence": "execution %s" % execution_status})
    else:
        for c in contract["checks"]:
            if c["kind"] == "builtin":
                s, ev = run_builtin(c["rule"], artifact_text, job_dir)
                checks_out.append({"id": c["id"], "status": s, "evidence": ev})
            elif c["kind"] == "command":
                s, ev = run_command(c["rule"], job_dir)
                checks_out.append({"id": c["id"], "status": s, "evidence": ev})
        if review_checks:
            if reviewer is None:
                for c in review_checks:
                    checks_out.append({"id": c["id"], "status": "blocked", "evidence": "no eligible reviewer"})
            elif len(artifact_text) > int(limits.get("review_max_chars", 80000)):
                for c in review_checks:
                    checks_out.append({"id": c["id"], "status": "blocked", "evidence": "artifact %d chars exceeds review limit; split the job" % len(artifact_text)})
            else:
                prompt = REVIEW_PROMPT.format(goal=contract["goal"], checks="\n".join("- %s: %s" % (c["id"], c["rule"]) for c in review_checks), sha=sha, artifact=artifact_text)
                env = reviewer(prompt, REVIEW_OUTPUT_SCHEMA)
                with open(os.path.join(attempt_dir, "review-raw.txt"), "w") as f:
                    f.write(env.get("text") or "")
                parsed = parse_review(env.get("text") or "") if env.get("execution_status") == "succeeded" else None
                errs = validate(parsed, REVIEW_OUTPUT_SCHEMA) if parsed is not None else ["no parseable review"]
                if errs:
                    for c in review_checks:
                        checks_out.append({"id": c["id"], "status": "blocked", "evidence": "reviewer output invalid: %s" % "; ".join(errs[:3])})
                else:
                    got = {c["id"]: c for c in parsed["checks"]}
                    for c in review_checks:
                        if c["id"] in got:
                            checks_out.append(got[c["id"]])
                        else:
                            checks_out.append({"id": c["id"], "status": "blocked", "evidence": "reviewer omitted this check"})
                    issues = parsed["issues"]

    statuses = [c["status"] for c in checks_out]
    if execution_status != "succeeded":
        acceptance = "blocked"
    elif any(s == "blocked" for s in statuses):
        acceptance = "blocked"
    elif any(s == "fail" for s in statuses):
        acceptance = "fail"
    else:
        acceptance = "pass"
    verdict = {
        "version": 1, "job_id": contract["id"], "artifact_sha256": sha,
        "reviewer": {"vendor": "kernel", "model": "verify.py"} if not review_checks else {"vendor": "reviewer", "model": "see events"},
        "execution_status": execution_status, "acceptance_status": acceptance,
        "checks": checks_out, "issues": issues,
    }
    return verdict, acceptance
