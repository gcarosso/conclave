"""Contracts, routing, job state, enforcement. No vendor calls here except through adapters.run."""
import datetime
import json
import os
import sys

import adapters
import verify

HERE = os.path.dirname(os.path.abspath(__file__))
SYSTEM = os.path.normpath(os.path.join(HERE, ".."))
GOV_PATH = os.environ.get("AI_GOVERNANCE") or os.path.join(SYSTEM, "shared", "governance.json")
GOV_EXAMPLE = os.path.join(SYSTEM, "shared", "governance.example.json")
POLICY_PATH = os.environ.get("AI_POLICY") or os.path.join(HERE, "policy.json")
INDEX_PATH = os.path.join(HERE, "jobs", "index.jsonl")


class RouteError(Exception):
    pass


def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def load():
    """Load governance + policy. `hub` defaults to the parent of this checkout; `operator` to "operator"."""
    if not os.path.exists(GOV_PATH):
        raise RouteError("no governance file at %s — run `ai init` (or copy shared/governance.example.json)" % GOV_PATH)
    with open(GOV_PATH) as f:
        g = json.load(f)
    if not g.get("hub"):
        g["hub"] = os.path.dirname(SYSTEM)
    g["hub"] = os.path.expanduser(g["hub"])
    g.setdefault("operator", "operator")
    with open(POLICY_PATH) as f:
        p = json.load(f)
    return g, p


# ---------- domain ----------

def detect_domain(cwd, g):
    hub = os.path.realpath(g["hub"])
    cur = os.path.realpath(cwd)
    if cur == hub:
        return "_system"
    while cur.startswith(hub + os.sep):
        parent = os.path.dirname(cur)
        if parent == hub:
            name = os.path.basename(cur)
            if name in g["domains"]:
                return name
            raise RouteError("cwd is under the hub but not inside a known domain: %s" % name)
        cur = parent
    raise RouteError("cwd is outside the hub; pass --domain")


def domain_dir(g, domain):
    return os.path.join(g["hub"], domain)


def jobs_root(g, domain):
    if domain == "_system":
        return os.path.join(HERE, "jobs")
    return os.path.join(domain_dir(g, domain), ".ai", "jobs")


# ---------- models / routing ----------

def catalog(p):
    return {m["id"]: m for m in p["models"]}


def eligible_vendors(g, domain, data_class):
    dom = g["domains"][domain]
    dv = set(dom.get("vendors", g["vendors"]))
    cv = set(g["data_classes"][data_class]["vendors"])
    return sorted(dv & cv)


def resolve(g, p, domain, role, data_class, vendor=None, model=None, tier=None, max_tier=None):
    """Pick (vendor, model, tier). Raises RouteError with a machine-readable reason."""
    if role not in p["roles"]:
        raise RouteError("unknown role %s" % role)
    r = p["roles"][role]
    if r.get("hub_only") and domain != "_system":
        raise RouteError("role %s is hub-only; run it from the hub root" % role)
    allowed = eligible_vendors(g, domain, data_class)
    cat = catalog(p)
    if model:
        if model not in cat:
            raise RouteError("unknown model id %s (policy.models is the allowlist)" % model)
        m = cat[model]
        if not m.get("available", False):
            raise RouteError("model %s is marked unavailable" % model)
        vendor = vendor or m["vendor"]
        if vendor != m["vendor"]:
            raise RouteError("model %s belongs to %s, not %s" % (model, m["vendor"], vendor))
        tier = m["tier"]
    vendor = vendor or r["default_vendor"]
    if vendor not in allowed:
        raise RouteError("blocked: data_class=%s in %s admits only %s; %s refused" % (data_class, domain, "/".join(allowed) or "nobody", vendor))
    tier = int(tier or r["default_tier"])
    if max_tier is not None and tier > int(max_tier):
        tier = int(max_tier)
    if not model:
        model = p["ladders"][vendor][str(tier)]
        m = cat.get(model)
        if not m or not m.get("available", False):
            raise RouteError("ladder %s tier %s -> %s is not an available model" % (vendor, tier, model))
    return vendor, model, tier


def gate_check(g, p, model, approved, interactive):
    """Top-model gate. Returns an approval record (or None if the model is not gated) or raises."""
    m = catalog(p)[model]
    if not m.get("requires_approval"):
        return None
    operator = g.get("operator", "operator")
    if approved:
        return {"model": model, "approved_by": operator, "via": "--approve-top-model", "at": now()}
    if interactive and sys.stdin.isatty():
        ans = input("Top model %s requires %s's approval. Proceed? [y/N] " % (model, operator)).strip().lower()
        if ans == "y":
            return {"model": model, "approved_by": operator, "via": "tty", "at": now()}
    raise RouteError("gated: %s requires approval (pass --approve-top-model)" % model)


def refresh_cockpit():
    """Fire-and-forget STATUS.md refresh; never blocks or fails a job."""
    import subprocess
    if os.environ.get("AI_NO_COCKPIT"):
        return
    script = os.path.join(SYSTEM, "ops", "cockpit.sh")
    if not os.path.exists(script):
        return
    try:
        subprocess.Popen(["bash", script], stdin=subprocess.DEVNULL,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception:
        pass


# ---------- jobs ----------

def new_id(role):
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ") + "-" + role


def build_contract(g, p, domain, role, goal, data_class, vendor, model, tier, source, review, declass=None, approval=None, checks=None, effects=None):
    r = p["roles"][role]
    lim = p["limits"]
    chk = checks or [{"id": "nonempty", "kind": "builtin", "rule": "nonempty"}]
    if review and not any(c["kind"] == "review" for c in chk):
        chk.append({"id": "goal-met", "kind": "review", "rule": "The artifact accomplishes the goal; claims are supported; nothing required is missing"})
    c = {
        "version": 1, "id": new_id(role), "domain": domain, "data_class": data_class, "goal": goal, "role": role,
        "inputs": [], "outputs": ["result.md"],
        "scope": {"read": [domain_dir(g, domain)], "write": ["result.md"] if r["codex_sandbox"] == "read-only" else [domain_dir(g, domain)],
                  "effects": effects or (["edit-files"] if r["codex_sandbox"] != "read-only" else []), "writer": "%s/%s" % (vendor, model)},
        "authorization": {"source": source, "declassification": declass, "top_model_approval": approval},
        "limits": {"calls": lim["calls"], "seconds": p["timeouts_s"][str(tier)], "repairs": lim["repairs"], "escalations": lim["escalations"], "review_max_chars": lim["review_max_chars"]},
        "checks": chk,
    }
    errs = verify.validate(c, verify.load_schema("contract.schema.json"))
    if errs:
        raise RouteError("contract invalid: " + "; ".join(errs))
    return c


def _lock_path(g, contract):
    import hashlib
    key = hashlib.sha256("\n".join(sorted(contract["scope"]["write"])).encode()).hexdigest()[:16]
    return os.path.join(jobs_root(g, contract["domain"]), "locks", key + ".lock")


def acquire_writer_lock(g, contract):
    """One writer per write set: an O_EXCL lock file naming the owning job. Stale locks (finished jobs) are reclaimed."""
    lp = _lock_path(g, contract)
    os.makedirs(os.path.dirname(lp), exist_ok=True)
    for _ in range(3):
        try:
            fd = os.open(lp, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            with os.fdopen(fd, "w") as f:
                f.write(contract["id"])
            return lp
        except FileExistsError:
            try:
                with open(lp) as f:
                    owner = f.read().strip()
            except FileNotFoundError:
                continue
            ojd = os.path.join(jobs_root(g, contract["domain"]), owner)
            finished = os.path.exists(os.path.join(ojd, "acceptance.json")) or os.path.exists(os.path.join(ojd, "result.md")) or not os.path.exists(ojd)
            if finished:
                try:
                    os.unlink(lp)
                except FileNotFoundError:
                    pass
                continue
            raise RouteError("write set locked by running job %s (%s)" % (owner, ", ".join(contract["scope"]["write"])))
    raise RouteError("could not acquire writer lock for %s" % ", ".join(contract["scope"]["write"]))


def release_writer_lock(g, contract):
    lp = _lock_path(g, contract)
    try:
        with open(lp) as f:
            owner = f.read().strip()
        if owner == contract["id"]:
            os.unlink(lp)
    except FileNotFoundError:
        pass


def create_job(g, contract):
    jd = os.path.join(jobs_root(g, contract["domain"]), contract["id"])
    acquire_writer_lock(g, contract)
    os.makedirs(os.path.join(jd, "attempts"), exist_ok=True)
    with open(os.path.join(jd, "contract.json"), "w") as f:
        json.dump(contract, f, indent=2)
    event(jd, "created", role=contract["role"], domain=contract["domain"], data_class=contract["data_class"])
    os.makedirs(os.path.dirname(INDEX_PATH), exist_ok=True)
    with open(INDEX_PATH, "a") as f:
        f.write(json.dumps({"id": contract["id"], "domain": contract["domain"], "role": contract["role"], "job_dir": jd, "created_at": now()}) + "\n")
    return jd


def event(jd, kind, **data):
    rec = {"at": now(), "event": kind}
    rec.update(data)
    with open(os.path.join(jd, "events.jsonl"), "a") as f:
        f.write(json.dumps(rec) + "\n")


def settings_for(g, domain):
    s = os.path.join(domain_dir(g, domain), ".claude", "settings.json")
    return s if os.path.exists(s) else None


def attempt(g, p, contract, jd, n, vendor, model, tier, prompt, purpose="work"):
    """One vendor call, fully recorded under attempts/<n>/. n is an int for work/repair/escalation attempts
    and a string such as "1-review-codex" for the reviewer call that judges attempt 1."""
    r = p["roles"][contract["role"]]
    ad = os.path.join(jd, "attempts", str(n))
    os.makedirs(ad, exist_ok=True)
    cwd = domain_dir(g, contract["domain"]) if contract["domain"] != "_system" else SYSTEM
    # Vendors that only receive a prompt (no local CLI with a sandbox) never get a domain as working
    # directory: the prompt is their whole payload, so they run in an empty sandbox under the attempt.
    if vendor in adapters.PROMPT_ONLY_VENDORS:
        cwd = os.path.join(ad, "sandbox")
        os.makedirs(cwd, exist_ok=True)
    with open(os.path.join(ad, "request.json"), "w") as f:
        json.dump({"purpose": purpose, "vendor": vendor, "model": model, "tier": tier, "cwd": cwd, "prompt": prompt, "at": now()}, f, indent=2)
    event(jd, "dispatch", attempt=n, purpose=purpose, vendor=vendor, model=model, tier=tier)
    env = adapters.run(vendor, model, prompt, cwd, contract["limits"]["seconds"],
                       sandbox=r["codex_sandbox"], network="network" in contract["scope"]["effects"],
                       settings=settings_for(g, contract["domain"]), max_turns=r["max_turns"],
                       web_search=(contract["role"] == "live"))
    with open(os.path.join(ad, "stdout.txt"), "w") as f:
        f.write(env.pop("raw_stdout", ""))
    with open(os.path.join(ad, "stderr.txt"), "w") as f:
        f.write(env.pop("raw_stderr", ""))
    with open(os.path.join(ad, "result.md"), "w") as f:
        f.write(env.get("text") or "")
    with open(os.path.join(ad, "result.json"), "w") as f:
        json.dump(env, f, indent=2)
    event(jd, "result", attempt=n, execution_status=env["execution_status"], exit_code=env["exit_code"],
          input_tokens=env["input_tokens"], output_tokens=env["output_tokens"], cost_usd=env["cost_usd"], elapsed_s=env["elapsed_s"])
    return env, ad


def reviewer_callable(g, p, contract, jd, n, writer_vendor, tier):
    """Fresh-context reviewer of a different vendor, subject to the same eligibility. None if nobody eligible."""
    pref = p["reviewer_for"].get(writer_vendor, "claude")
    allowed = eligible_vendors(g, contract["domain"], contract["data_class"])
    candidates = [v for v in [pref] + [x for x in allowed if x != pref] if v in allowed and v != writer_vendor]
    if not candidates:
        return None, None
    rtier = min(int(tier), 2)
    chosen = {"v": candidates[0], "m": p["ladders"][candidates[0]][str(rtier)]}

    def call(prompt, schema):
        # fall through to the next eligible vendor only on execution failure (auth, timeout, empty), never on a verdict
        env = None
        for v in candidates:
            m = p["ladders"][v][str(rtier)]
            env, _ = attempt(g, p, contract, jd, "%s-review-%s" % (n, v), v, m, rtier, prompt, purpose="review")
            if env["execution_status"] == "succeeded":
                chosen["v"], chosen["m"] = v, m
                break
            event(jd, "reviewer-fallback", failed=v, reason=(env.get("error") or "")[:160])
        return env
    return call, (chosen["v"], chosen["m"])


def finalize(jd, contract, verdict, attempts_meta):
    acc = verdict["acceptance_status"]
    with open(os.path.join(jd, "verdict.json"), "w") as f:
        json.dump(verdict, f, indent=2)
    with open(os.path.join(jd, "acceptance.json"), "w") as f:
        json.dump({"job_id": contract["id"], "acceptance_status": acc, "execution_status": verdict["execution_status"],
                   "artifact_sha256": verdict["artifact_sha256"], "checks": verdict["checks"], "attempts": attempts_meta, "at": now()}, f, indent=2)
    event(jd, "accepted" if acc == "pass" else "finished", acceptance_status=acc)
    try:
        g, _ = load()
        release_writer_lock(g, contract)
    except Exception:
        pass
    refresh_cockpit()
    return acc


def run_job(g, p, contract, jd, vendor, model, tier, prompt, approve_top=False, interactive=True, on_progress=None):
    """Execute → verify → (repair) → (escalate) → accept. Returns (final_text, acceptance, meta)."""
    calls = 0
    n = 1
    meta = []
    env, ad = attempt(g, p, contract, jd, n, vendor, model, tier, prompt)
    calls += 1
    meta.append({"attempt": n, "purpose": "work", "vendor": vendor, "model": model, "execution_status": env["execution_status"]})
    text = env.get("text") or ""
    rev, rinfo = (None, None)
    if any(c["kind"] == "review" for c in contract["checks"]):
        rev, rinfo = reviewer_callable(g, p, contract, jd, n, vendor, tier)
    verdict, acc = verify.evaluate(contract, text, jd, ad, reviewer=rev, execution_status=env["execution_status"])
    if rinfo:
        verdict["reviewer"] = {"vendor": rinfo[0], "model": rinfo[1]}
    if on_progress:
        on_progress("attempt %d %s → %s" % (n, env["execution_status"], acc))

    # bounded repair
    repairs = contract["limits"]["repairs"]
    while acc == "fail" and repairs > 0 and calls < contract["limits"]["calls"]:
        repairs -= 1
        n += 1
        issues = "\n".join("- [%s] %s%s" % (i["severity"], i["problem"], (" → " + i["fix"]) if i.get("fix") else "") for i in verdict["issues"]) or "- checks failed: " + "; ".join("%s (%s)" % (c["id"], c["evidence"]) for c in verdict["checks"] if c["status"] == "fail")
        rprompt = prompt + "\n\nA fresh-context reviewer rejected the previous attempt. Fix every issue below and return the complete corrected artifact:\n" + issues + "\n\nPREVIOUS ARTIFACT\n-----\n" + text
        env, ad = attempt(g, p, contract, jd, n, vendor, model, tier, rprompt, purpose="repair")
        calls += 1
        meta.append({"attempt": n, "purpose": "repair", "vendor": vendor, "model": model, "execution_status": env["execution_status"]})
        text = env.get("text") or ""
        if any(c["kind"] == "review" for c in contract["checks"]):
            rev, rinfo = reviewer_callable(g, p, contract, jd, n, vendor, tier)
        verdict, acc = verify.evaluate(contract, text, jd, ad, reviewer=rev, execution_status=env["execution_status"])
        if rinfo:
            verdict["reviewer"] = {"vendor": rinfo[0], "model": rinfo[1]}
        if on_progress:
            on_progress("repair %d %s → %s" % (n, env["execution_status"], acc))

    # bounded escalation: only when the reviewer says a stronger model is needed
    escalations = contract["limits"]["escalations"]
    if acc == "fail" and escalations > 0 and any(i.get("capability_deficit") for i in verdict["issues"]) and int(tier) < 3 and calls < contract["limits"]["calls"]:
        ntier = int(tier) + 1
        nmodel = p["ladders"][vendor][str(ntier)]
        try:
            approval = gate_check(g, p, nmodel, approve_top, interactive)
        except RouteError as e:
            event(jd, "escalation-refused", reason=str(e))
            approval = "refused"
        if approval != "refused":
            if approval:
                contract["authorization"]["top_model_approval"] = approval
                with open(os.path.join(jd, "contract.json"), "w") as f:
                    json.dump(contract, f, indent=2)
            n += 1
            event(jd, "escalate", from_tier=tier, to_tier=ntier, model=nmodel)
            env, ad = attempt(g, p, contract, jd, n, vendor, nmodel, ntier, prompt, purpose="escalation")
            calls += 1
            meta.append({"attempt": n, "purpose": "escalation", "vendor": vendor, "model": nmodel, "execution_status": env["execution_status"]})
            text = env.get("text") or ""
            if any(c["kind"] == "review" for c in contract["checks"]):
                rev, rinfo = reviewer_callable(g, p, contract, jd, n, vendor, ntier)
            verdict, acc = verify.evaluate(contract, text, jd, ad, reviewer=rev, execution_status=env["execution_status"])
            if rinfo:
                verdict["reviewer"] = {"vendor": rinfo[0], "model": rinfo[1]}
            model, tier = nmodel, ntier

    with open(os.path.join(jd, "result.md"), "w") as f:
        f.write(text)
    acc = finalize(jd, contract, verdict, meta)
    return text, acc, {"attempts": meta, "final_model": model, "final_tier": tier, "verdict": verdict}


# ---------- council ----------

COUNCIL_PROMPT = """You are one of two independent advisors. Answer the question below on your own evidence and reasoning; you will not see the other advisor's answer.

QUESTION
{q}

Return ONLY a JSON object: {{"recommendation":"<one sentence>","confidence":"low|medium|high","reasoning":"<≤200 words>","objections":["<blocking objection, if any>"]}}"""

COUNCIL_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["recommendation", "confidence", "reasoning", "objections"],
                  "properties": {"recommendation": {"type": "string"}, "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
                                 "reasoning": {"type": "string"}, "objections": {"type": "array", "items": {"type": "string"}}}}

JUDGE_PROMPT = """Two advisors disagree. Decide. Do not restate both; resolve the disputed propositions and say what to do.

QUESTION
{q}

ADVISOR A ({a_vendor})
{a}

ADVISOR B ({b_vendor})
{b}

Return markdown: a one-paragraph decision, then 'Why A/B is wrong on:' bullets, then 'Do this next:' bullets."""


def council(g, p, domain, data_class, question, jd, approve_top=False, interactive=True, on_progress=None):
    cfg = p["council"]
    allowed = eligible_vendors(g, domain, data_class)
    members = [v for v in cfg["members"] if v in allowed][:2]
    if len(members) < 2:
        raise RouteError("council needs two eligible vendors in %s at data_class=%s; eligible: %s" % (domain, data_class, "/".join(allowed)))
    contract = build_contract(g, p, domain, "plan", question, data_class, members[0], p["ladders"][members[0]][str(cfg["tier"])], cfg["tier"], "council", review=False)
    contract["id"] = contract["id"].replace("-plan", "-council")
    jd = create_job(g, contract)
    release_writer_lock(g, contract)  # a council reads and advises; it owns no domain write set
    outs = []
    for i, v in enumerate(members, 1):
        m = p["ladders"][v][str(cfg["tier"])]
        env, ad = attempt(g, p, contract, jd, i, v, m, cfg["tier"], COUNCIL_PROMPT.format(q=question), purpose="council-member")
        parsed = verify.parse_review(env.get("text") or "") if env["execution_status"] == "succeeded" else None
        errs = verify.validate(parsed, COUNCIL_SCHEMA) if parsed is not None else ["no output"]
        outs.append({"vendor": v, "model": m, "ok": not errs, "answer": parsed if not errs else None, "raw": env.get("text")})
        if on_progress:
            on_progress("member %s/%s → %s" % (v, m, "ok" if not errs else "invalid"))
    if not all(o["ok"] for o in outs):
        event(jd, "council-blocked", reason="a member returned no valid answer")
        return jd, "blocked", outs, None
    a, b = outs[0]["answer"], outs[1]["answer"]
    disagree = a["recommendation"].strip().lower() != b["recommendation"].strip().lower() or bool(a["objections"]) or bool(b["objections"])
    judge_text = None
    if disagree:
        jv = cfg["judge_vendor"]
        jm = p["ladders"][jv][str(cfg["judge_tier"])]
        if jv not in allowed:
            event(jd, "judge-refused", reason="judge vendor not eligible for data_class")
            return jd, "disagree", outs, None
        try:
            approval = gate_check(g, p, jm, approve_top, interactive)
        except RouteError as e:
            event(jd, "judge-refused", reason=str(e))
            return jd, "disagree", outs, None
        contract["authorization"]["top_model_approval"] = approval
        env, _ = attempt(g, p, contract, jd, 3, jv, jm, cfg["judge_tier"],
                         JUDGE_PROMPT.format(q=question, a_vendor=outs[0]["vendor"], a=json.dumps(a, indent=1), b_vendor=outs[1]["vendor"], b=json.dumps(b, indent=1)), purpose="judge")
        judge_text = env.get("text") if env["execution_status"] == "succeeded" else None
    with open(os.path.join(jd, "result.md"), "w") as f:
        f.write(json.dumps({"members": outs, "disagree": disagree, "judge": judge_text}, indent=2))
    event(jd, "finished", acceptance_status="n/a", disagree=disagree, judged=bool(judge_text))
    refresh_cockpit()
    return jd, ("judged" if judge_text else ("disagree" if disagree else "agree")), outs, judge_text


# ---------- stochastic consensus ----------

FRAMINGS = [
    "Analyze the problem objectively.",
    "You are a conservative analyst who weighs downside risks heavily.",
    "You are an aggressive strategist who optimizes for upside.",
    "Challenge conventional wisdom: what does everyone get wrong here?",
    "Reason from first principles; ignore what is conventional.",
    "Think from the end user's perspective: what matters most to them?",
    "Assume limited time and budget: what is the highest-leverage move?",
    "Optimize for the five-year outcome, not the ninety-day one.",
    "Use only what is measurable and provable; ignore intuition.",
    "Map second- and third-order effects of each choice.",
]

CONSENSUS_PROMPT = """{framing}

QUESTION
{q}
{options}
Return ONLY a JSON object: {{"recommendation":"<one short phrase naming your pick>","confidence":<1-10>,"reasons":["<≤3 reasons>"],"unique_idea":"<one idea most analysts would miss, or empty>"}}"""

CONSENSUS_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["recommendation", "confidence", "reasons", "unique_idea"],
                    "properties": {"recommendation": {"type": "string"}, "confidence": {"type": "integer"},
                                   "reasons": {"type": "array", "items": {"type": "string"}}, "unique_idea": {"type": "string"}}}


def _norm(s):
    import re
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def consensus(g, p, domain, data_class, question, n=5, options=None, on_progress=None):
    """N cheap independent samples (tier 1), framings cycled, vendors rotated over the eligible set; mechanical aggregation."""
    from concurrent.futures import ThreadPoolExecutor
    n = max(3, min(int(n), 10))
    allowed = eligible_vendors(g, domain, data_class)
    members = [v for v in g["vendors"] if v in allowed]
    if not members:
        raise RouteError("no eligible vendor in %s at data_class=%s" % (domain, data_class))
    lead = members[0]
    contract = build_contract(g, p, domain, "scout", question, data_class, lead, p["ladders"][lead]["1"], 1, "consensus", review=False)
    contract["id"] = contract["id"].replace("-scout", "-consensus")
    contract["limits"]["calls"] = n
    jd = create_job(g, contract)
    release_writer_lock(g, contract)
    opts = ("OPTIONS (pick one): " + "; ".join(options)) if options else ""

    def one(i):
        v = members[i % len(members)]
        m = p["ladders"][v]["1"]
        prompt = CONSENSUS_PROMPT.format(framing=FRAMINGS[i % len(FRAMINGS)], q=question, options=opts)
        parsed, ok = None, False
        for retry in range(2):  # one cheap retry: tier-1 models occasionally drop a key
            env, _ = attempt(g, p, contract, jd, i + 1 if retry == 0 else i + 1 + n, v, m, 1, prompt, purpose="sample" if retry == 0 else "sample-retry")
            parsed = verify.parse_review(env.get("text") or "") if env["execution_status"] == "succeeded" else None
            ok = parsed is not None and not verify.validate(parsed, CONSENSUS_SCHEMA)
            if ok or env["execution_status"] != "succeeded":
                break
        if on_progress:
            on_progress("sample %d %s/%s → %s" % (i + 1, v, m, "ok" if ok else "invalid"))
        return {"i": i + 1, "vendor": v, "model": m, "framing": FRAMINGS[i % len(FRAMINGS)], "ok": ok, "answer": parsed if ok else None}

    with ThreadPoolExecutor(max_workers=min(n, 5)) as ex:
        samples = list(ex.map(one, range(n)))
    valid = [s for s in samples if s["ok"]]
    groups = {}
    for s in valid:
        key = _norm(s["answer"]["recommendation"])
        if options:  # snap to the option it names, if any
            for o in options:
                if _norm(o) and _norm(o) in key:
                    key = _norm(o)
                    break
        groups.setdefault(key, []).append(s)
    ranked = sorted(groups.items(), key=lambda kv: (-len(kv[1]), -sum(x["answer"]["confidence"] for x in kv[1])))
    mode = ranked[0] if ranked else None
    result = {
        "question": question, "n": n, "valid": len(valid), "vendors": members,
        "mode": {"recommendation": mode[1][0]["answer"]["recommendation"], "share": len(mode[1]) / len(valid), "count": len(mode[1]),
                 "mean_confidence": sum(x["answer"]["confidence"] for x in mode[1]) / len(mode[1])} if mode else None,
        "splits": [{"recommendation": grp[0]["answer"]["recommendation"], "count": len(grp), "vendors": sorted({x["vendor"] for x in grp})} for _, grp in ranked],
        "outliers": sorted({s["answer"]["unique_idea"].strip() for s in valid if s["answer"]["unique_idea"].strip()}),
        "samples": samples,
    }
    with open(os.path.join(jd, "result.md"), "w") as f:
        json.dump(result, f, indent=2)
    status = "blocked" if len(valid) < max(3, n // 2) else ("consensus" if mode and result["mode"]["share"] >= 0.6 else "split")
    event(jd, "finished", acceptance_status="n/a", consensus=status, valid=len(valid))
    refresh_cockpit()
    return jd, status, result


# ---------- auto triage: scout then specialist ----------

TRIAGE_PROMPT = """Classify this task for a router. Do not do the task.

TASK
{task}

Roles: scout (lookup/triage), plan (architecture/strategy), code (write or fix code), write (prose/docs), review (critique), live (needs current web data), longdoc (very long reading).
Tiers: 1 = cheap model suffices (lookups, formatting, short answers); 2 = workhorse (most real work); 3 = top model, only for architecture-grade judgment or adversarial review of high-stakes output.

Return ONLY JSON: {{"role":"<role>","tier":1|2|3,"review":true|false,"reason":"<≤20 words>"}}"""

TRIAGE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["role", "tier", "review", "reason"],
                 "properties": {"role": {"type": "string"}, "tier": {"type": "integer"}, "review": {"type": "boolean"}, "reason": {"type": "string"}}}


def triage(g, p, domain, data_class, task):
    """One tier-1 call that picks role/tier/review. Returns dict or raises RouteError."""
    allowed = eligible_vendors(g, domain, data_class)
    if not allowed:
        raise RouteError("no eligible vendor in %s at data_class=%s" % (domain, data_class))
    v = "claude" if "claude" in allowed else allowed[0]
    m = p["ladders"][v]["1"]
    cwd = os.path.join(SYSTEM, "router", "jobs", "_triage")
    os.makedirs(cwd, exist_ok=True)
    env = adapters.run(v, m, TRIAGE_PROMPT.format(task=task), cwd, p["timeouts_s"]["1"], max_turns=2, json_schema=TRIAGE_SCHEMA)
    parsed = verify.parse_review(env.get("text") or "") if env["execution_status"] == "succeeded" else None
    if parsed is None or verify.validate(parsed, TRIAGE_SCHEMA) or parsed["role"] not in p["roles"]:
        raise RouteError("triage failed: %s" % (env.get("error") or "unusable classification"))
    parsed["tier"] = max(1, min(int(parsed["tier"]), 3))
    parsed["triaged_by"] = "%s/%s" % (v, m)
    return parsed
