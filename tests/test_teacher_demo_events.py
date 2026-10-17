"""DemoEvent projection and paging never expose raw witness fields."""

import json
import tempfile
import unittest
import uuid
from pathlib import Path

from tools import teacher_demo_events as events


def step(event_type, actor, target, status, payload, reason=None):
    return {
        "event_type": event_type,
        "actor": actor,
        "target": target,
        "status": status,
        "safe_payload": payload,
        "reason_code": reason,
        "observed_at": 1792000000.0,
        "monotonic_ms": 12345,
    }


class EventTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.native = self.folder / "test-results/native"
        self.native.mkdir(parents=True)
        self.run_id = str(uuid.uuid4())

    def tearDown(self):
        self.temp.cleanup()

    def witness(self, case, steps, scenario="stolen-token"):
        path = self.native / f"teacher-demo-witness-{case}.json"
        path.write_text(
            json.dumps(
                {
                    "scenario_id": scenario,
                    "case": case,
                    "steps": steps,
                }
            )
        )

    def stolen_steps(self):
        return [
            step(
                "fixture.setup",
                "attacker",
                "attacker",
                "passed",
                {
                    "token_holder": "executor",
                    "proof_signer_kid": "did:web:identity.agent-guard.test:agents:planner#key-1",
                },
            ),
            step(
                "request.sent",
                "attacker",
                "gateway",
                "in_progress",
                {
                    "endpoint": "/v1/invocations",
                    "token_holder": "executor",
                    "proof_signer_kid": "did:web:identity.agent-guard.test:agents:planner#key-1",
                    "tool_id": "procurement.order.create",
                },
            ),
            step(
                "accept.rejected",
                "gateway",
                "attacker",
                "rejected",
                {
                    "http_status": 401,
                },
                "INVALID_PROOF",
            ),
            step(
                "readback.state",
                "ledger",
                "user",
                "passed",
                {
                    "budget_before": [{"reserved_fen": 0, "settled_fen": 0, "calls": 0}] * 3,
                    "budget_after": [{"reserved_fen": 0, "settled_fen": 0, "calls": 0}] * 3,
                    "orders_before": 0,
                    "orders_after": 0,
                    "notifications_before": 0,
                    "notifications_after": 0,
                },
            ),
        ]

    def test_live_partial_then_terminal_paging_and_replay(self):
        self.witness("stolen", self.stolen_steps())
        self.assertTrue(events.persist(self.folder, self.run_id, "stolen-token"))
        first = events.page(self.folder, self.run_id, "stolen-token", limit=2)
        self.assertEqual([e["seq"] for e in first["events"]], [1, 2])
        self.assertFalse(first["terminal"])
        self.assertFalse(first["complete"])
        self.assertEqual(first["next_after_seq"], 2)
        self.assertTrue(events.persist(self.folder, self.run_id, "stolen-token", terminal=True))
        tail = events.page(self.folder, self.run_id, "stolen-token", after_seq=2)
        self.assertEqual([e["seq"] for e in tail["events"]], [3, 4, 5])
        self.assertTrue(tail["terminal"] and tail["complete"])
        self.assertEqual(tail["events"][-1]["event_type"], "run.terminal")
        self.assertEqual(tail["events"][0]["cause_id"], first["events"][1]["event_id"])
        replay = events.page(self.folder, self.run_id, "stolen-token", replay=True)
        self.assertEqual(replay["source"], "replay")
        self.assertTrue(all(e["source"] == "replay" for e in replay["events"]))

    def test_missing_history_and_invalid_cursor(self):
        empty = events.page(self.folder, self.run_id, "stolen-token", replay=True)
        self.assertEqual(empty["events"], [])
        self.assertFalse(empty["complete"])
        for after, limit in [(-1, 1), (0, 0), (0, 201), (True, 1)]:
            with self.assertRaises(ValueError):
                events.page(self.folder, self.run_id, "stolen-token", after_seq=after, limit=limit)

    def test_program_failure_is_terminal_but_incomplete(self):
        events.fail(self.folder, self.run_id, "stolen-token")
        result = events.page(self.folder, self.run_id, "stolen-token")
        self.assertTrue(result["terminal"])
        self.assertFalse(result["complete"])
        self.assertEqual(result["events"][0]["event_type"], "run.error")
        self.assertEqual(result["events"][0]["reason_code"], "RUN_FAILED")

    def test_secret_or_missing_step_cannot_be_projected(self):
        steps = self.stolen_steps()
        steps[1]["safe_payload"]["token"] = "SECRET"
        self.witness("stolen", steps)
        with self.assertRaises(ValueError):
            events.persist(self.folder, self.run_id, "stolen-token", terminal=True)
        self.assertFalse((self.folder / events.FILE).exists())
        self.witness("stolen", self.stolen_steps()[:-1])
        with self.assertRaises(ValueError):
            events.persist(self.folder, self.run_id, "stolen-token", terminal=True)

    def test_saved_event_tampering_is_rejected(self):
        self.witness("stolen", self.stolen_steps())
        events.persist(self.folder, self.run_id, "stolen-token", terminal=True)
        path = self.folder / events.FILE
        data = json.loads(path.read_text())
        data["events"][1]["safe_payload"]["token"] = "SECRET"
        path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):
            events.page(self.folder, self.run_id, "stolen-token")
        for invalid in ("yes", 1):
            clean = json.loads(path.read_text())
            clean["events"][1]["safe_payload"].pop("token", None)
            clean["complete"] = invalid
            path.write_text(json.dumps(clean))
            with self.assertRaises(ValueError):
                events.page(self.folder, self.run_id, "stolen-token")
        events.persist(self.folder, self.run_id, "stolen-token")
        incomplete = json.loads(path.read_text())
        incomplete["complete"] = True
        path.write_text(json.dumps(incomplete))
        with self.assertRaises(ValueError):
            events.page(self.folder, self.run_id, "stolen-token")

    def test_revocation_causality_uses_real_observation_order(self):
        budget = [{"reserved_fen": 0, "settled_fen": 0, "calls": 0}] * 3
        self.witness(
            "revoke-first",
            [
                step(
                    "request.sent",
                    "executor",
                    "gateway",
                    "in_progress",
                    {
                        "endpoint": "/v1/invocations",
                        "token_holder": "executor",
                        "tool_id": "procurement.order.create",
                    },
                ),
                step(
                    "lock.waiting",
                    "gateway",
                    "ledger",
                    "waiting",
                    {
                        "waiting_on": "root-revocation",
                    },
                ),
                step(
                    "revocation.committed",
                    "ledger",
                    "gateway",
                    "passed",
                    {
                        "grant_alias": "root",
                        "txn_ref": "root-revocation",
                    },
                ),
                step(
                    "accept.rejected",
                    "gateway",
                    "executor",
                    "rejected",
                    {
                        "http_status": 403,
                    },
                    "REVOKED",
                ),
                step(
                    "readback.state",
                    "ledger",
                    "user",
                    "passed",
                    {
                        "budget_before": budget,
                        "budget_after": budget,
                        "orders_before": 0,
                        "orders_after": 0,
                        "notifications_before": 0,
                        "notifications_after": 0,
                    },
                ),
            ],
            scenario="revocation",
        )
        events.persist(self.folder, self.run_id, "revocation", terminal=True)
        page = events.page(self.folder, self.run_id, "revocation")
        self.assertEqual(
            page["events"][1]["safe_payload"]["waiting_on"], page["events"][2]["event_id"]
        )
        self.assertEqual(page["events"][3]["cause_id"], page["events"][2]["event_id"])

    def test_two_case_delegation_prefix_is_incomplete(self):
        limits = {"amount_fen": 100000, "calls": 12}
        scope = ["procurement.order.create"]
        requested = {
            "parent_limits": limits,
            "requested_limits": {"amount_fen": 80000, "calls": 8},
            "parent_scope": scope,
            "requested_scope": scope,
        }
        budget = [{"reserved_fen": 0, "settled_fen": 0, "calls": 0}] * 3
        self.witness(
            "amount",
            [
                step("delegation.requested", "planner", "as", "in_progress", requested),
                step(
                    "delegation.issued",
                    "as",
                    "selector",
                    "passed",
                    {
                        "holder": "selector",
                        "holder_kid": "selector#key-1",
                        "http_status": 200,
                    },
                ),
                step(
                    "delegation.requested",
                    "planner",
                    "as",
                    "in_progress",
                    requested
                    | {
                        "requested_limits": {"amount_fen": 100001, "calls": 8},
                    },
                ),
                step(
                    "delegation.rejected",
                    "as",
                    "planner",
                    "rejected",
                    {
                        "dimension": "amount",
                        "http_status": 400,
                    },
                    "invalid_request",
                ),
                step(
                    "readback.state",
                    "ledger",
                    "user",
                    "passed",
                    {
                        "budget_before": budget,
                        "budget_after": budget,
                        "orders_before": 0,
                        "orders_after": 0,
                        "notifications_before": 0,
                        "notifications_after": 0,
                    },
                ),
            ],
            scenario="delegation-scope",
        )
        self.assertTrue(events.persist(self.folder, self.run_id, "delegation-scope"))
        page = events.page(self.folder, self.run_id, "delegation-scope")
        self.assertEqual(len(page["events"]), 5)
        self.assertEqual(page["events"][1]["safe_payload"]["holder_kid"], "selector#key-1")
        self.assertFalse(page["terminal"] or page["complete"])
        self.assertFalse(
            events.persist(self.folder, self.run_id, "delegation-scope", terminal=True)
        )


if __name__ == "__main__":
    unittest.main()
