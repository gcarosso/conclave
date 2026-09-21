#!/usr/bin/env python3
"""Offline router tests. No vendor is called: adapters.run is replaced with a fake.

Every test runs against a throwaway hub built from shared/governance.example.json, so the suite
needs no governance.json, no vendor CLI, and no network. `python3 tests.py` or `make test`.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
os.environ["AI_NO_COCKPIT"] = "1"

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import adapters  # noqa: E402
import generate  # noqa: E402
import kernel  # noqa: E402
import verify  # noqa: E402

EXAMPLE = os.path.join(HERE, "..", "shared", "governance.example.json")


class FakeVendor:
    def __init__(self):
        self.calls = []
        self.script = []  # list of (execution_status, text)

    def __call__(self, vendor, model, prompt, cwd, timeout, **kw):
        self.calls.append({"vendor": vendor, "model": model, "prompt": prompt, "cwd": cwd, **kw})
        status, text = self.script.pop(0) if self.script else ("succeeded", "ok " * 20)
        return adapters.envelope(execution_status=status, exit_code=0 if status == "succeeded" else 1, text=text,
                                 input_tokens=10, output_tokens=5, cost_usd=0.0, elapsed_s=0.1)


class Base(unittest.TestCase):
    """A temp hub: governance from the example, every domain directory created, jobs kept in the temp tree."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="ai-test-")
        self.hub = os.path.join(self.tmp, "hub")
        with open(EXAMPLE) as f:
            g = json.load(f)
        g["hub"] = self.hub
        for name in g["domains"]:
            os.makedirs(os.path.join(self.hub, name), exist_ok=True)
        self.gov_path = os.path.join(self.tmp, "governance.json")
        with open(self.gov_path, "w") as f:
            json.dump(g, f)
        self._orig = (kernel.GOV_PATH, kernel.INDEX_PATH, kernel.jobs_root, adapters.run)
        kernel.GOV_PATH = self.gov_path
        kernel.INDEX_PATH = os.path.join(self.tmp, "index.jsonl")
        kernel.jobs_root = lambda g, d: os.path.join(self.tmp, "jobs", d)
        self.fake = FakeVendor()
        adapters.run = self.fake
        self.g, self.p = kernel.load()

    def tearDown(self):
        for key, handle in list(kernel._WRITER_LOCKS.items()):
            if key[0].startswith(self.tmp):
                handle.close()
                del kernel._WRITER_LOCKS[key]
        kernel.GOV_PATH, kernel.INDEX_PATH, kernel.jobs_root, adapters.run = self._orig
        shutil.rmtree(self.tmp, ignore_errors=True)


class Routing(Base):
    def test_private_domain_refuses_prompt_only_vendor(self):
        with self.assertRaises(kernel.RouteError):
            kernel.resolve(self.g, self.p, "work", "live", "private", vendor="grok")

    def test_sanitized_admits_grok(self):
        v, m, t = kernel.resolve(self.g, self.p, "work", "live", "sanitized", vendor="grok")
        self.assertEqual((v, m), ("grok", "grok-4.6"))

    def test_public_domain_admits_gemini(self):
        v, m, t = kernel.resolve(self.g, self.p, "public", "scout", "public", vendor="gemini")
        self.assertEqual(m, "gemini-3.5-flash-lite")

    def test_system_rejects_grok_even_if_sanitized(self):
        with self.assertRaises(kernel.RouteError):
            kernel.resolve(self.g, self.p, "_system", "scout", "sanitized", vendor="grok")

    def test_unknown_model_rejected(self):
        with self.assertRaises(kernel.RouteError):
            kernel.resolve(self.g, self.p, "work", "scout", "private", model="claude-opus-9")

    def test_unavailable_model_rejected(self):
        with self.assertRaises(kernel.RouteError):
            kernel.resolve(self.g, self.p, "work", "scout", "private", model="gpt-5.5-pro")

    def test_ladder_defaults(self):
        self.assertEqual(kernel.resolve(self.g, self.p, "work", "scout", "private")[1], "claude-haiku-4-5-20251001")
        self.assertEqual(kernel.resolve(self.g, self.p, "work", "code", "private")[1], "gpt-5.6-sol")

    def test_max_tier_caps(self):
        self.assertEqual(kernel.resolve(self.g, self.p, "work", "code", "private", max_tier=1)[1], "gpt-5.6-luna")

    def test_explicit_model_cannot_bypass_tier_cap(self):
        with self.assertRaises(kernel.RouteError):
            kernel.resolve(self.g, self.p, "work", "code", "private", model="gpt-6-astra", max_tier=1)

    def test_bad_tier_and_cross_vendor_ladder_are_rejected(self):
        with self.assertRaises(kernel.RouteError):
            kernel.resolve(self.g, self.p, "work", "scout", "private", tier=0)
        self.p["ladders"]["claude"]["1"] = "gpt-5.6-luna"
        with self.assertRaises(kernel.RouteError):
            kernel.resolve(self.g, self.p, "work", "scout", "private")

    def test_publish_is_not_a_role(self):
        self.assertNotIn("publish", self.p["roles"])
        with self.assertRaises(kernel.RouteError):
            kernel.resolve(self.g, self.p, "_system", "publish", "private")

    def test_gate_refuses_without_approval_non_interactive(self):
        with self.assertRaises(kernel.RouteError):
            kernel.gate_check(self.g, self.p, "claude-fable-5-1", approved=False, interactive=False)
        with self.assertRaises(kernel.RouteError):
            kernel.gate_check(self.g, self.p, "gpt-6-astra", approved=False, interactive=False)
        rec = kernel.gate_check(self.g, self.p, "gpt-6-astra", approved=True, interactive=False)
        self.assertEqual(rec["approved_by"], self.g["operator"])
        self.assertIsNone(kernel.gate_check(self.g, self.p, "gpt-5.6-sol", approved=False, interactive=False))

    def test_domain_detection(self):
        hub = self.g["hub"]
        self.assertEqual(kernel.detect_domain(hub, self.g), "_system")
        self.assertEqual(kernel.detect_domain(os.path.join(hub, "work", "deep", "path"), self.g), "work")
        with self.assertRaises(kernel.RouteError):
            kernel.detect_domain(tempfile.gettempdir(), self.g)
        with self.assertRaises(kernel.RouteError):
            kernel.detect_domain(os.path.join(hub, "not-a-domain"), self.g)

    def test_hub_defaults_to_parent_of_checkout(self):
        with open(self.gov_path) as f:
            g = json.load(f)
        g["hub"] = None
        with open(self.gov_path, "w") as f:
            json.dump(g, f)
        g2, _ = kernel.load()
        self.assertEqual(g2["hub"], os.path.dirname(kernel.SYSTEM))

    def test_missing_governance_is_a_route_error(self):
        kernel.GOV_PATH = os.path.join(self.tmp, "nope.json")
        with self.assertRaises(kernel.RouteError):
            kernel.load()


class Contracts(Base):
    def test_contract_validates_and_review_added_for_write(self):
        c = kernel.build_contract(self.g, self.p, "work", "write", "draft", "private", "claude", "claude-sonnet-5", 2, "test", review=True)
        self.assertEqual([k["kind"] for k in c["checks"]], ["builtin", "review"])
        self.assertEqual(c["data_class"], "private")

    def test_schema_rejects_unknown_field(self):
        c = kernel.build_contract(self.g, self.p, "work", "scout", "x", "private", "claude", "claude-haiku-4-5-20251001", 1, "test", review=False)
        c["extra"] = 1
        self.assertTrue(verify.validate(c, verify.load_schema("contract.schema.json")))

    def test_verdict_schema(self):
        v = {"version": 1, "job_id": "j", "artifact_sha256": "x", "reviewer": {"vendor": "codex", "model": "m"},
             "execution_status": "succeeded", "acceptance_status": "pass", "checks": [], "issues": []}
        self.assertEqual(verify.validate(v, verify.load_schema("verdict.schema.json")), [])
        v["acceptance_status"] = "ACCEPTED"
        self.assertTrue(verify.validate(v, verify.load_schema("verdict.schema.json")))

    def test_builtin_rules(self):
        self.assertEqual(verify.run_builtin("contains:needle", "hay needle stack", self.tmp)[0], "pass")
        self.assertEqual(verify.run_builtin("not_contains:needle", "hay needle stack", self.tmp)[0], "fail")
        self.assertEqual(verify.run_builtin("regex:^## Result", "intro\n## Result\n", self.tmp)[0], "pass")
        self.assertEqual(verify.run_builtin("min_words:3", "one two", self.tmp)[0], "fail")
        self.assertEqual(verify.run_builtin("no_such_rule", "x", self.tmp)[0], "blocked")


class Acceptance(Base):
    def _job(self, role="scout", review=False, checks=None, domain="public", data_class="public"):
        v, m, t = kernel.resolve(self.g, self.p, domain, role, data_class)
        c = kernel.build_contract(self.g, self.p, domain, role, "say hello", data_class, v, m, t, "test", review=review, checks=checks)
        jd = kernel.create_job(self.g, c)
        return c, jd, v, m, t

    def test_exit_zero_empty_output_is_not_accepted(self):
        c, jd, v, m, t = self._job()
        self.fake.script = [("succeeded", ""), ("succeeded", "")]
        text, acc, meta = kernel.run_job(self.g, self.p, c, jd, v, m, t, "hi", interactive=False)
        self.assertEqual(acc, "fail")
        self.assertEqual([a["purpose"] for a in meta["attempts"]], ["work", "repair"])

    def test_execution_failure_blocks(self):
        c, jd, v, m, t = self._job()
        self.fake.script = [("failed", "")] * 6
        text, acc, meta = kernel.run_job(self.g, self.p, c, jd, v, m, t, "hi", interactive=False)
        self.assertEqual(acc, "blocked")
        self.assertTrue(os.path.exists(os.path.join(jd, "acceptance.json")))
        with open(os.path.join(jd, "events.jsonl")) as f:
            fallbacks = [e for e in map(json.loads, f) if e["event"] == "vendor-fallback"]
        self.assertEqual([e["failed"] for e in fallbacks],
                         [a["vendor"] for a in meta["attempts"][:-1]])

    def test_work_vendor_fallback_on_execution_failure(self):
        c, jd, v, m, t = self._job()
        self.fake.script = [("failed", ""), ("succeeded", "A perfectly adequate answer with enough words in it.")]
        text, acc, meta = kernel.run_job(self.g, self.p, c, jd, v, m, t, "hi", interactive=False)
        self.assertEqual(acc, "pass")
        used = [k["vendor"] for k in self.fake.calls]
        self.assertEqual(len(used), 2); self.assertNotEqual(used[0], used[1])
        self.assertEqual([a["execution_status"] for a in meta["attempts"]], ["failed", "succeeded"])
        with open(os.path.join(jd, "events.jsonl")) as f:
            ev = f.read()
        self.assertIn("vendor-fallback", ev)

    def test_no_fallback_on_a_failed_verdict(self):
        c, jd, v, m, t = self._job()
        self.fake.script = [("succeeded", ""), ("succeeded", "")]
        kernel.run_job(self.g, self.p, c, jd, v, m, t, "hi", interactive=False)
        self.assertEqual({k["vendor"] for k in self.fake.calls}, {v})

    def test_writing_role_falls_back_only_to_vendors_that_can_write(self):
        c, jd, v, m, t = self._job(role="code")
        self.fake.script = [("failed", "")] * 6
        kernel.run_job(self.g, self.p, c, jd, v, m, t, "hi", interactive=False)
        work = [k["vendor"] for k in self.fake.calls]
        self.assertTrue(set(work) <= {"claude", "codex"}, work)

    def test_fallback_never_reaches_a_gated_model(self):
        c, jd, v, m, t = self._job()
        candidate = next(x for x in kernel.eligible_vendors(self.g, "public", "public") if x != v)
        gated_model = self.p["ladders"][candidate][str(t)]
        for entry in self.p["models"]:
            if entry["id"] == gated_model:
                entry["requires_approval"] = True
        self.fake.script = [("failed", "")] * 6
        kernel.run_job(self.g, self.p, c, jd, v, m, t, "hi", interactive=False, approve_top=True)
        self.assertNotIn(gated_model, {k["model"] for k in self.fake.calls})

    def test_verdict_names_the_reviewer_that_answered_after_fallback(self):
        c, jd, v, m, t = self._job(role="write", review=True)
        good = json.dumps({"checks": [{"id": "goal-met", "status": "pass", "evidence": "checked"}], "issues": []})
        self.fake.script = [("succeeded", "a draft " * 10), ("failed", ""), ("succeeded", good)]
        text, acc, meta = kernel.run_job(self.g, self.p, c, jd, v, m, t, "hi", interactive=False)
        calls = [k["vendor"] for k in self.fake.calls]
        self.assertEqual(meta["verdict"]["reviewer"]["vendor"], calls[-1])
        self.assertNotEqual(calls[1], calls[2])
        with open(os.path.join(jd, "verdict.json")) as f:
            reviewer = json.load(f)["reviewer"]
        self.assertEqual(reviewer, {"vendor": self.fake.calls[-1]["vendor"],
                                    "model": self.fake.calls[-1]["model"]})

    def test_builtin_pass(self):
        c, jd, v, m, t = self._job()
        self.fake.script = [("succeeded", "A perfectly adequate answer with enough words in it.")]
        text, acc, meta = kernel.run_job(self.g, self.p, c, jd, v, m, t, "hi", interactive=False)
        self.assertEqual(acc, "pass")
        with open(os.path.join(jd, "acceptance.json")) as f:
            acc_json = json.load(f)
        self.assertEqual(acc_json["acceptance_status"], "pass")
        self.assertTrue(os.path.exists(os.path.join(jd, "contract.json")))
        self.assertTrue(os.path.exists(os.path.join(jd, "verdict.json")))
        self.assertTrue(os.path.exists(os.path.join(jd, "attempts", "1", "request.json")))

    def test_command_check_runs_in_job_dir(self):
        c, jd, v, m, t = self._job(checks=[{"id": "nonempty", "kind": "builtin", "rule": "nonempty"},
                                          {"id": "grep", "kind": "command", "rule": "grep -q hello result.md"}])
        self.fake.script = [("succeeded", "hello world, a sufficiently long artifact for the nonempty rule")]
        text, acc, meta = kernel.run_job(self.g, self.p, c, jd, v, m, t, "hi", interactive=False)
        self.assertEqual(acc, "pass")

    def test_review_fail_then_repair_pass_uses_other_vendor(self):
        c, jd, v, m, t = self._job(role="write", review=True)
        good = json.dumps({"checks": [{"id": "goal-met", "status": "pass", "evidence": "line 1"}], "issues": []})
        bad = json.dumps({"checks": [{"id": "goal-met", "status": "fail", "evidence": "line 2"}],
                          "issues": [{"id": "R1", "severity": "major", "problem": "missing X", "fix": "add X", "capability_deficit": False}]})
        self.fake.script = [("succeeded", "draft one " * 10), ("succeeded", bad), ("succeeded", "draft two with X " * 10), ("succeeded", good)]
        text, acc, meta = kernel.run_job(self.g, self.p, c, jd, v, m, t, "write", interactive=False)
        self.assertEqual(acc, "pass")
        vendors = [k["vendor"] for k in self.fake.calls]
        self.assertEqual(vendors, ["claude", "codex", "claude", "codex"])
        self.assertEqual(len(meta["attempts"]), 2)
        self.assertIn("PREVIOUS ARTIFACT", self.fake.calls[2]["prompt"])
        # every call has its own attempt directory: the reviewer never overwrites the worker's record
        for d, purpose in (("1", "work"), ("1-review-codex", "review"), ("2", "repair"), ("2-review-codex", "review")):
            with open(os.path.join(jd, "attempts", d, "request.json")) as f:
                self.assertEqual(json.load(f)["purpose"], purpose, d)
        with open(os.path.join(jd, "attempts", "1", "result.md")) as f:
            self.assertTrue(f.read().startswith("draft one"))
        self.assertTrue(os.path.exists(os.path.join(jd, "attempts", "1", "review-raw.txt")))

    def test_review_not_accepted_phrase_does_not_pass(self):
        c, jd, v, m, t = self._job(role="write", review=True)
        self.fake.script = [("succeeded", "draft " * 10), ("succeeded", "NOT ACCEPTED. ACCEPTED? no. prose without json")]
        text, acc, meta = kernel.run_job(self.g, self.p, c, jd, v, m, t, "write", interactive=False)
        self.assertEqual(acc, "blocked")

    def test_escalation_needs_capability_deficit_and_gate(self):
        c, jd, v, m, t = self._job(role="write", review=True)
        bad_cap = json.dumps({"checks": [{"id": "goal-met", "status": "fail", "evidence": "l"}],
                              "issues": [{"id": "R1", "severity": "critical", "problem": "needs deeper reasoning", "fix": "", "capability_deficit": True}]})
        self.fake.script = [("succeeded", "d1 " * 10), ("succeeded", bad_cap), ("succeeded", "d2 " * 10), ("succeeded", bad_cap)]
        text, acc, meta = kernel.run_job(self.g, self.p, c, jd, v, m, t, "write", interactive=False, approve_top=False)
        self.assertEqual(acc, "fail")  # tier 3 for claude is gated; refused without approval
        with open(os.path.join(jd, "events.jsonl")) as f:
            events = [json.loads(l)["event"] for l in f]
        self.assertIn("escalation-refused", events)

    def test_escalation_runs_when_approved(self):
        c, jd, v, m, t = self._job(role="write", review=True)
        bad_cap = json.dumps({"checks": [{"id": "goal-met", "status": "fail", "evidence": "l"}],
                              "issues": [{"id": "R1", "severity": "critical", "problem": "needs deeper reasoning", "fix": "", "capability_deficit": True}]})
        good = json.dumps({"checks": [{"id": "goal-met", "status": "pass", "evidence": "ok"}], "issues": []})
        self.fake.script = [("succeeded", "d1 " * 10), ("succeeded", bad_cap), ("succeeded", "d2 " * 10), ("succeeded", bad_cap),
                            ("succeeded", "d3 from the top model " * 5), ("succeeded", good)]
        text, acc, meta = kernel.run_job(self.g, self.p, c, jd, v, m, t, "write", interactive=False, approve_top=True)
        self.assertEqual(acc, "pass")
        self.assertEqual(meta["final_model"], "claude-fable-5-1")
        with open(os.path.join(jd, "contract.json")) as f:
            contract = json.load(f)
        self.assertEqual(contract["authorization"]["top_model_approval"]["approved_by"], self.g["operator"])

    def test_tier_cap_also_prevents_escalation(self):
        c, jd, v, m, t = self._job(role="write", review=True)
        bad = json.dumps({"checks": [{"id": "goal-met", "status": "fail", "evidence": "missing result"}],
                          "issues": [{"id": "R1", "severity": "major", "problem": "incomplete", "fix": "complete", "capability_deficit": True}]})
        self.fake.script = [("succeeded", "draft " * 10), ("succeeded", bad)] * 2
        _, acc, _ = kernel.run_job(self.g, self.p, c, jd, v, m, t, "write", approve_top=True, interactive=False, max_tier=2)
        self.assertEqual(acc, "fail")
        self.assertEqual(len(self.fake.calls), 4)
        self.assertNotIn("claude-fable-5-1", [call["model"] for call in self.fake.calls])

    def test_private_review_prefers_codex_for_claude_writer(self):
        c, jd, v, m, t = self._job(role="write", review=True, domain="personal", data_class="private")
        good = json.dumps({"checks": [{"id": "goal-met", "status": "pass", "evidence": "ok"}], "issues": []})
        self.fake.script = [("succeeded", "a private draft " * 5), ("succeeded", good)]
        kernel.run_job(self.g, self.p, c, jd, v, m, t, "x", interactive=False)
        self.assertEqual([k["vendor"] for k in self.fake.calls], ["claude", "codex"])

    def test_oversized_artifact_blocks_review(self):
        c, jd, v, m, t = self._job(role="write", review=True)
        self.fake.script = [("succeeded", "x" * (self.p["limits"]["review_max_chars"] + 1))]
        text, acc, meta = kernel.run_job(self.g, self.p, c, jd, v, m, t, "write", interactive=False)
        self.assertEqual(acc, "blocked")
        self.assertEqual(len(self.fake.calls), 1)  # no reviewer call was spent

    def test_review_uses_read_only_permissions_and_schema(self):
        c, jd, v, m, t = self._job(role="write", review=True)
        good = json.dumps({"checks": [{"id": "goal-met", "status": "pass", "evidence": "line 1"}], "issues": []})
        self.fake.script = [("succeeded", "draft " * 10), ("succeeded", good)]
        kernel.run_job(self.g, self.p, c, jd, v, m, t, "write", interactive=False)
        review = self.fake.calls[1]
        self.assertEqual(review["sandbox"], "read-only")
        self.assertTrue(review["cwd"].endswith("/sandbox"))
        self.assertTrue(review["no_tools"])
        self.assertFalse(review["network"])
        self.assertEqual(review["json_schema"], verify.REVIEW_OUTPUT_SCHEMA)

    def test_reviewer_fallback_records_actual_vendor(self):
        c, jd, v, m, t = self._job(role="write", review=True)
        good = json.dumps({"checks": [{"id": "goal-met", "status": "pass", "evidence": "line 1"}], "issues": []})
        self.fake.script = [("succeeded", "draft " * 10), ("failed", ""), ("succeeded", good)]
        _, acc, meta = kernel.run_job(self.g, self.p, c, jd, v, m, t, "write", interactive=False)
        self.assertEqual(acc, "pass")
        self.assertEqual(meta["verdict"]["reviewer"]["vendor"], self.fake.calls[-1]["vendor"])

    def test_review_and_fallback_count_toward_budget(self):
        c, jd, v, m, t = self._job(role="write", review=True)
        c["limits"]["calls"] = 2
        self.fake.script = [("succeeded", "draft " * 10), ("failed", "")]
        _, acc, _ = kernel.run_job(self.g, self.p, c, jd, v, m, t, "write", interactive=False)
        self.assertEqual(acc, "blocked")
        self.assertEqual(len(self.fake.calls), 2)

    def test_unavailable_reviewer_is_never_called(self):
        c, jd, v, m, t = self._job(role="write", review=True, domain="personal", data_class="private")
        for entry in self.p["models"]:
            if entry["id"] == "gpt-5.6-sol":
                entry["available"] = False
        _, acc, _ = kernel.run_job(self.g, self.p, c, jd, v, m, t, "write", interactive=False)
        self.assertEqual(acc, "blocked")
        self.assertEqual(len(self.fake.calls), 1)

    def test_duplicate_review_checks_block(self):
        c, jd, v, m, t = self._job(role="write", review=True)
        check = {"id": "goal-met", "status": "pass", "evidence": "line 1"}
        self.fake.script = [("succeeded", "draft " * 10), ("succeeded", json.dumps({"checks": [check, check], "issues": []}))]
        _, acc, _ = kernel.run_job(self.g, self.p, c, jd, v, m, t, "write", interactive=False)
        self.assertEqual(acc, "blocked")

    def test_invalid_builtin_blocks_with_record(self):
        c, jd, v, m, t = self._job(checks=[{"id": "pattern", "kind": "builtin", "rule": "regex:["}])
        _, acc, _ = kernel.run_job(self.g, self.p, c, jd, v, m, t, "read", interactive=False)
        self.assertEqual(acc, "blocked")
        self.assertTrue(os.path.exists(os.path.join(jd, "acceptance.json")))


class Isolation(Base):
    def test_sanitized_grok_never_gets_private_cwd(self):
        v, m, t = kernel.resolve(self.g, self.p, "work", "live", "sanitized", vendor="grok")
        c = kernel.build_contract(self.g, self.p, "work", "live", "x", "sanitized", v, m, t, "test", review=False)
        jd = kernel.create_job(self.g, c)
        self.fake.script = [("succeeded", "answer " * 10)]
        kernel.run_job(self.g, self.p, c, jd, v, m, t, "x", interactive=False)
        cwd = self.fake.calls[0]["cwd"]
        self.assertTrue(cwd.endswith("/sandbox"))
        self.assertEqual(os.listdir(cwd), [])
        self.assertFalse(cwd.startswith(os.path.join(self.g["hub"], "work")))

    def test_grok_sandboxed_even_in_public_domain(self):
        v, m, t = kernel.resolve(self.g, self.p, "public", "live", "public", vendor="grok")
        c = kernel.build_contract(self.g, self.p, "public", "live", "x", "public", v, m, t, "test", review=False)
        jd = kernel.create_job(self.g, c)
        self.fake.script = [("succeeded", "answer " * 10)]
        kernel.run_job(self.g, self.p, c, jd, v, m, t, "x", interactive=False)
        self.assertTrue(self.fake.calls[0]["cwd"].endswith("/sandbox"))

    def test_local_vendor_gets_domain_cwd(self):
        v, m, t = kernel.resolve(self.g, self.p, "work", "scout", "private")
        c = kernel.build_contract(self.g, self.p, "work", "scout", "x", "private", v, m, t, "test", review=False)
        jd = kernel.create_job(self.g, c)
        kernel.run_job(self.g, self.p, c, jd, v, m, t, "x", interactive=False)
        self.assertEqual(self.fake.calls[0]["cwd"], os.path.join(self.g["hub"], "work"))

    def test_one_writer_per_write_set(self):
        v, m, t = kernel.resolve(self.g, self.p, "public", "code", "public")
        c1 = kernel.build_contract(self.g, self.p, "public", "code", "a", "public", v, m, t, "test", review=False)
        c2 = kernel.build_contract(self.g, self.p, "public", "code", "b", "public", v, m, t, "test", review=False)
        kernel.create_job(self.g, c1)
        with self.assertRaises(kernel.RouteError):
            kernel.create_job(self.g, c2)
        kernel.release_writer_lock(self.g, c1)
        kernel.create_job(self.g, c2)

    def test_released_lock_file_can_be_reused(self):
        v, m, t = kernel.resolve(self.g, self.p, "public", "code", "public")
        c1 = kernel.build_contract(self.g, self.p, "public", "code", "a", "public", v, m, t, "test", review=False)
        jd = kernel.create_job(self.g, c1)
        kernel.release_writer_lock(self.g, c1)
        self.assertTrue(os.path.exists(kernel._lock_path(self.g, c1)))
        c2 = kernel.build_contract(self.g, self.p, "public", "code", "b", "public", v, m, t, "test", review=False)
        kernel.create_job(self.g, c2)

    def test_lock_cannot_be_stolen_before_job_creation_or_on_partial_output(self):
        v, m, t = kernel.resolve(self.g, self.p, "public", "code", "public")
        c1 = kernel.build_contract(self.g, self.p, "public", "code", "a", "public", v, m, t, "test", review=False)
        c2 = kernel.build_contract(self.g, self.p, "public", "code", "b", "public", v, m, t, "test", review=False)
        kernel.acquire_writer_lock(self.g, c1)
        with self.assertRaises(kernel.RouteError):
            kernel.create_job(self.g, c2)
        jd = os.path.join(kernel.jobs_root(self.g, "public"), c1["id"])
        os.makedirs(jd)
        with open(os.path.join(jd, "result.md"), "w") as f:
            f.write("partial output")
        with self.assertRaises(kernel.RouteError):
            kernel.create_job(self.g, c2)

    def test_read_jobs_do_not_share_a_writer_lock(self):
        for _ in range(2):
            v, m, t = kernel.resolve(self.g, self.p, "public", "scout", "public")
            c = kernel.build_contract(self.g, self.p, "public", "scout", "read", "public", v, m, t, "test", review=False)
            kernel.create_job(self.g, c)
        self.assertEqual(kernel._WRITER_LOCKS, {})

    def test_exited_process_releases_os_lock(self):
        v, m, t = kernel.resolve(self.g, self.p, "public", "code", "public")
        c = kernel.build_contract(self.g, self.p, "public", "code", "edit", "public", v, m, t, "test", review=False)
        lp = kernel._lock_path(self.g, c)
        os.makedirs(os.path.dirname(lp))
        script = "import fcntl,sys; f=open(sys.argv[1], 'w'); fcntl.flock(f, fcntl.LOCK_EX); f.write('exited-job'); f.flush()"
        subprocess.run([sys.executable, "-c", script, lp], check=True)
        kernel.create_job(self.g, c)


class Council(Base):
    def test_agreement_no_judge(self):
        ans = json.dumps({"recommendation": "Do A", "confidence": "high", "reasoning": "r", "objections": []})
        self.fake.script = [("succeeded", ans), ("succeeded", ans)]
        jd, status, outs, judge = kernel.council(self.g, self.p, "public", "public", "A or B?", None, interactive=False)
        self.assertEqual(status, "agree")
        self.assertIsNone(judge)
        self.assertEqual(len(self.fake.calls), 2)

    def test_disagreement_judge_gated(self):
        a = json.dumps({"recommendation": "Do A", "confidence": "high", "reasoning": "r", "objections": []})
        b = json.dumps({"recommendation": "Do B", "confidence": "medium", "reasoning": "r", "objections": ["A breaks X"]})
        self.fake.script = [("succeeded", a), ("succeeded", b)]
        jd, status, outs, judge = kernel.council(self.g, self.p, "public", "public", "A or B?", None, interactive=False, approve_top=False)
        self.assertEqual(status, "disagree")
        self.assertEqual(len(self.fake.calls), 2)
        self.fake.script = [("succeeded", a), ("succeeded", b), ("succeeded", "Decision: A.")]
        jd, status, outs, judge = kernel.council(self.g, self.p, "public", "public", "A or B?", None, interactive=False, approve_top=True)
        self.assertEqual(status, "judged")
        self.assertEqual(self.fake.calls[-1]["model"], "claude-fable-5-1")
        with open(os.path.join(jd, "contract.json")) as f:
            self.assertEqual(json.load(f)["authorization"]["top_model_approval"]["model"], "claude-fable-5-1")

    def test_council_private_domain_uses_configured_members(self):
        ans = json.dumps({"recommendation": "Do A", "confidence": "high", "reasoning": "r", "objections": []})
        self.fake.script = [("succeeded", ans), ("succeeded", ans)]
        kernel.council(self.g, self.p, "personal", "private", "q", None, interactive=False)
        self.assertEqual(sorted(k["vendor"] for k in self.fake.calls), ["claude", "codex"])

    def test_invalid_member_output_blocks(self):
        ans = json.dumps({"recommendation": "Do A", "confidence": "high", "reasoning": "r", "objections": []})
        self.fake.script = [("succeeded", ans), ("succeeded", "not json at all")]
        jd, status, outs, judge = kernel.council(self.g, self.p, "public", "public", "q", None, interactive=False)
        self.assertEqual(status, "blocked")

    def test_council_records_declassification_and_source(self):
        ans = json.dumps({"recommendation": "Do A", "confidence": "high", "reasoning": "r", "objections": []})
        self.fake.script = [("succeeded", ans), ("succeeded", ans)]
        declass = {"from": "private", "to": "sanitized", "by": "test operator"}
        jd, _, _, _ = kernel.council(self.g, self.p, "work", "sanitized", "q", None, interactive=False, declass=declass, source="explicit request")
        with open(os.path.join(jd, "contract.json")) as f:
            auth = json.load(f)["authorization"]
        self.assertEqual(auth["declassification"], declass)
        self.assertEqual(auth["source"], "explicit request")

    def test_unavailable_council_member_is_not_dispatched(self):
        for entry in self.p["models"]:
            if entry["id"] == "claude-sonnet-5":
                entry["available"] = False
        _, status, _, _ = kernel.council(self.g, self.p, "public", "public", "q", None, interactive=False)
        self.assertEqual(status, "blocked")
        self.assertNotIn("claude", [call["vendor"] for call in self.fake.calls])


class Governance(Base):
    def test_generate_then_check_reports_no_drift(self):
        g = generate.load(self.gov_path)
        for path, content in generate.targets(g).items():
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(content)
        r = subprocess.run([sys.executable, os.path.join(HERE, "generate.py"), "--check", "--governance", self.gov_path], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("0 drifted", r.stdout)

    def test_hand_edit_is_drift(self):
        g = generate.load(self.gov_path)
        for path, content in generate.targets(g).items():
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w") as f:
                f.write(content)
        with open(os.path.join(self.hub, "work", "CLAUDE.md"), "a") as f:
            f.write("\nhand edit\n")
        r = subprocess.run([sys.executable, os.path.join(HERE, "generate.py"), "--check", "--governance", self.gov_path], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("DRIFT work/CLAUDE.md", r.stdout)

    def test_deny_rules_cover_every_sibling(self):
        g = generate.load(self.gov_path)
        s = json.loads(generate.settings(g, "work"))["permissions"]["deny"]
        for other in g["domains"]:
            if other != "work":
                self.assertIn("Read(/%s/%s/**)" % (self.hub, other), s)
        self.assertFalse(any("file_path:" in rule for rule in s))
        self.assertFalse(any("/work/" in rule for rule in s))

    def test_generated_text_carries_operator_and_rules(self):
        g = generate.load(self.gov_path)
        g["operator"] = "Ada"
        g["rules"]["extra"] = "Custom rule text."
        cd = generate.cross_domain(g)
        self.assertIn("declassification by Ada", cd)
        self.assertIn("**Extra.** Custom rule text.", cd)
        self.assertIn("`private` → claude, codex.", cd)


class Consensus(Base):
    def _ans(self, rec, conf=7, idea=""):
        return json.dumps({"recommendation": rec, "confidence": conf, "reasons": ["r"], "unique_idea": idea})

    def test_mode_and_outliers_public_rotates_vendors(self):
        self.fake.script = [("succeeded", self._ans("Option A")), ("succeeded", self._ans("option a", 9, "sell the data")), ("succeeded", self._ans("Option B")),
                            ("succeeded", self._ans("Option A")), ("succeeded", self._ans("Option A", 5))]
        jd, status, r = kernel.consensus(self.g, self.p, "public", "public", "A or B?", n=5, options=["Option A", "Option B"])
        self.assertEqual(status, "consensus")
        self.assertEqual(r["mode"]["count"], 4)
        self.assertEqual(r["outliers"], ["sell the data"])
        self.assertEqual(sorted({k["vendor"] for k in self.fake.calls}), ["claude", "codex", "gemini", "grok"])
        self.assertTrue(all(k["model"] in {v["1"] for v in self.p["ladders"].values()} for k in self.fake.calls))

    def test_private_domain_rotates_eligible_only_and_split(self):
        self.fake.script = [("succeeded", self._ans("X")), ("succeeded", self._ans("Y")), ("succeeded", self._ans("X")), ("succeeded", self._ans("Y")), ("succeeded", self._ans("Z"))]
        jd, status, r = kernel.consensus(self.g, self.p, "personal", "private", "q", n=5)
        self.assertEqual(status, "split")
        self.assertEqual(sorted({k["vendor"] for k in self.fake.calls}), ["claude", "codex"])

    def test_too_few_valid_blocks(self):
        self.fake.script = [("failed", ""), ("succeeded", "prose"), ("succeeded", self._ans("X")), ("failed", ""), ("succeeded", "nope")]
        jd, status, r = kernel.consensus(self.g, self.p, "public", "public", "q", n=5)
        self.assertEqual(status, "blocked")


class Cli(Base):
    """The `ai` entry point, driven as a subprocess with the temp hub and a fake-free dry run."""

    def _ai(self, *args, cwd=None):
        env = dict(os.environ, AI_GOVERNANCE=self.gov_path, AI_NO_COCKPIT="1")
        return subprocess.run([sys.executable, os.path.join(HERE, "ai")] + list(args), capture_output=True, text=True, cwd=cwd or self.hub, env=env)

    def test_roles_and_version(self):
        with open(os.path.join(HERE, "ai")) as f:
            ver = f.read().split('__version__ = "')[1].split('"')[0]
        self.assertEqual(self._ai("version").stdout.strip(), "ai %s" % ver)
        self.assertIn("scout", self._ai("roles").stdout)

    def test_dry_run_prints_header_and_writes_nothing(self):
        r = self._ai("scout", "what is here", "--dry-run", cwd=os.path.join(self.hub, "work"))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith("Orchestration: scout claude/claude-haiku-4-5-20251001"))
        self.assertFalse(os.path.exists(os.path.join(self.hub, "work", ".ai")))

    def test_auto_dry_run_skips_classification(self):
        import contextlib
        import io
        import runpy
        from unittest.mock import patch
        cli = runpy.run_path(os.path.join(HERE, "ai"), run_name="conclave_test")
        with patch.object(kernel, "triage", side_effect=AssertionError("dry run called a model")), contextlib.redirect_stdout(io.StringIO()):
            cli["main"](["auto", "task", "--dry-run", "--domain", "work"])
        self.assertEqual(self.fake.calls, [])

    def test_refused_vendor_is_a_clean_error(self):
        r = self._ai("scout", "x", "--vendor", "grok", "--dry-run", cwd=os.path.join(self.hub, "work"))
        self.assertEqual(r.returncode, 2)
        self.assertIn("blocked: data_class=private", r.stderr)

    def test_outside_hub_needs_domain(self):
        r = self._ai("scout", "x", "--dry-run", cwd=tempfile.gettempdir())
        self.assertEqual(r.returncode, 2)
        self.assertIn("pass --domain", r.stderr)
        r = self._ai("scout", "x", "--dry-run", "--domain", "work", cwd=tempfile.gettempdir())
        self.assertEqual(r.returncode, 0, r.stderr)


class Integration(Base):
    def test_claude_review_disables_tools_and_passes_schema(self):
        from unittest.mock import patch
        schema = verify.REVIEW_OUTPUT_SCHEMA
        with patch.object(adapters, "_run", return_value=(0, '{"result":"a review"}', "", 0.1, None)) as run:
            adapters.claude("example-model", "review", self.tmp, 10, no_tools=True, json_schema=schema)
        args = run.call_args.args[0]
        self.assertEqual(args[args.index("--tools") + 1], "")
        self.assertIn("--strict-mcp-config", args)
        self.assertEqual(json.loads(args[args.index("--json-schema") + 1]), schema)

    def test_claude_edit_permission_tracks_writing_role_and_excludes_reviewers(self):
        from unittest.mock import patch
        c = kernel.build_contract(self.g, self.p, "public", "code", "edit", "public",
                                  "claude", "claude-sonnet-5", 2, "test", review=False)
        jd = kernel.create_job(self.g, c)
        with patch.object(adapters, "run", self._orig[3]), patch.object(
                adapters, "_run", return_value=(0, '{"result":"answer"}', "", 0.1, None)) as run:
            for purpose in ("work", "repair", "escalation", "review"):
                kernel.attempt(self.g, self.p, c, jd, purpose, "claude", "claude-sonnet-5", 2,
                               "task", purpose=purpose,
                               json_schema=verify.REVIEW_OUTPUT_SCHEMA if purpose == "review" else None)
                args = run.call_args.args[0]
                if purpose == "review":
                    self.assertNotIn("--permission-mode", args)
                    self.assertEqual(args[args.index("--tools") + 1], "")
                else:
                    self.assertEqual(args[args.index("--permission-mode") + 1], "acceptEdits")
            adapters.run("claude", "claude-sonnet-5", "read", self.tmp, 10, sandbox="read-only")
            self.assertNotIn("--permission-mode", run.call_args.args[0])

    def test_handoff_requires_approval_before_writing(self):
        system = os.path.join(self.hub, "_system")
        os.makedirs(os.path.join(system, "shared"))
        os.makedirs(os.path.join(system, "router"))
        shutil.copy(self.gov_path, os.path.join(system, "shared", "governance.json"))
        shutil.copy(os.path.join(HERE, "policy.json"), os.path.join(system, "router", "policy.json"))
        shutil.copytree(os.path.join(HERE, "..", "ops"), os.path.join(system, "ops"))
        script = os.path.join(system, "ops", "handoff-to-vendor.sh")
        result = subprocess.run(["bash", script, "codex", "continue"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 2)
        self.assertIn("requires explicit approval", result.stderr)
        self.assertFalse(os.path.exists(os.path.join(system, "handoffs")))
        # Preparing a command is local; this flag never starts a model in the test.
        result = subprocess.run(["bash", script, "--approve-top-model", "codex", "continue"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        handoffs = os.listdir(os.path.join(system, "handoffs"))
        with open(os.path.join(system, "handoffs", handoffs[0])) as f:
            self.assertIn("supplied --approve-top-model", f.read())

    def test_lint_propagates_shellcheck_failure(self):
        bindir = os.path.join(self.tmp, "bin")
        os.mkdir(bindir)
        checker = os.path.join(bindir, "shellcheck")
        with open(checker, "w") as f:
            f.write("#!/bin/sh\necho simulated-shellcheck-failure >&2\nexit 1\n")
        os.chmod(checker, 0o755)
        result = subprocess.run(["make", "-C", os.path.join(HERE, ".."), "lint"], capture_output=True, text=True,
                                env=dict(os.environ, PATH=bindir + os.pathsep + os.environ["PATH"]))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("simulated-shellcheck-failure", result.stderr)
        self.assertNotIn("not installed", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=1)
