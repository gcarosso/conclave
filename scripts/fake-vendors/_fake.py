"""Offline stand-ins for the `claude` and `codex` CLIs, used by scripts/e2e.sh.

They accept the flags router/adapters.py passes and print output in the shape each adapter parses, so the
end-to-end run exercises the real `ai` entry point, kernel, verifier and job records without a vendor account.

Behavior
- `--version` prints a fake version string.
- A review prompt (from router/verify.py) gets a JSON verdict with one entry per listed check: pass, unless
  CONCLAVE_FAKE_FAIL_FIRST_REVIEW=1, in which case the first review in CONCLAVE_FAKE_STATE fails with one
  located issue so the kernel's repair path runs.
- Any other prompt gets a short deterministic answer.
"""
import json
import os
import re
import sys


def _review(prompt):
    block = prompt.split("CHECKS TO JUDGE", 1)[1].split("ARTIFACT", 1)[0]
    ids = re.findall(r"^- ([A-Za-z0-9_.-]+): ", block, re.M)
    fail = False
    if os.environ.get("CONCLAVE_FAKE_FAIL_FIRST_REVIEW") == "1":
        state = os.environ.get("CONCLAVE_FAKE_STATE")
        marker = os.path.join(state, "reviewed-once") if state else None
        if marker and not os.path.exists(marker):
            open(marker, "w").close()
            fail = True
    status = "fail" if fail else "pass"
    issues = [{"id": "R1", "severity": "major", "problem": "fake reviewer: first draft rejected to exercise repair",
               "fix": "return the corrected artifact", "capability_deficit": False}] if fail else []
    return json.dumps({"checks": [{"id": i, "status": status, "evidence": "fake reviewer"} for i in ids], "issues": issues})


def _answer(prompt, vendor):
    if "You are a fresh-context reviewer" in prompt:
        return _review(prompt)
    task = prompt.strip().splitlines()[-1][:80]
    repaired = " (repaired)" if "rejected the previous attempt" in prompt else ""
    return "Fake %s answer%s for: %s\n\nThis text is long enough to pass the nonempty check." % (vendor, repaired, task)


def main(vendor):
    args = sys.argv[1:]
    if "--version" in args:
        print("%s 0.0.0 (conclave fake)" % vendor)
        return 0
    prompt = args[-1] if args else ""
    text = _answer(prompt, vendor)
    if vendor == "claude":
        print(json.dumps({"type": "result", "is_error": False, "result": text, "session_id": "fake-session",
                          "usage": {"input_tokens": len(prompt.split()), "output_tokens": len(text.split())}, "total_cost_usd": 0}))
        return 0
    if vendor == "codex":
        out = args[args.index("-o") + 1] if "-o" in args else None
        if out:
            with open(out, "w") as f:
                f.write(text)
        print(json.dumps({"type": "thread.started", "thread_id": "fake-thread"}))
        print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": len(prompt.split()), "output_tokens": len(text.split())}}))
        return 0
    print("unknown fake vendor %s" % vendor, file=sys.stderr)
    return 2
