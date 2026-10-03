"""Contract, deadline, queue and HTTP tests; synthetic data, no native model."""
from copy import deepcopy
from http.client import HTTPConnection
import json
from pathlib import Path
import threading
import time
import unittest

from service import (decode_json, digest, IncompleteInput, InputError, LocalServer,
                     NativeOutputError, SemanticService, TASK_LABELS,
                     validate_native, validate_request)


def request(amount=None, budget=1000):
    return {
        "schema_version": "1.0", "request_id": "synthetic-01", "profile": "qris_artifact_context",
        "snapshot_digest": "a" * 64, "deadline_unix_ms": int(time.time() * 1000) + budget,
        "processing_permissions": {"semantic_remote": True},
        "state": {"message": "bayar ke toko uji", "payment": {"merchant": "TOKO UJI", "amount_minor": amount}},
    }


def native():
    result = json.loads((Path(__file__).parents[2] / "hacknusa-laya-450-50-v1/smoke_tests.json").read_text())[0]["expected"]
    return {"schema_version": "1.0", "model_id": "synthetic-model", **result,
            "usage": {"input_tokens": 100, "output_tokens": 0, "state_tokens": 30,
                      "state_tokens_dropped": 0, "truncated": False, "truncated_questions": []}}


class FakeRunner:
    release = {"model_id": "synthetic-model", "fingerprint": "b" * 64,
               "task_readiness": {task: {"policy_approved": False} for task in TASK_LABELS}}

    def __init__(self):
        self.states = []

    def predict(self, state):
        self.states.append(state)
        return native()


class ContractTests(unittest.TestCase):
    def test_null_omitted_and_whole_rupiah_are_distinct(self):
        runner = FakeRunner()
        service = SemanticService(runner)
        self.addCleanup(service.close)
        states = []
        for amount in (None, 350000, "omit"):
            item = request(amount)
            if amount == "omit":
                del item["state"]["payment"]["amount_minor"]
            status, answer = service.assess(item)
            self.assertEqual(200, status)
            self.assertEqual("experimental", answer["status"])
            self.assertEqual(item["request_id"], answer["request_id"])
            self.assertEqual(item["snapshot_digest"], answer["snapshot_digest"])
            self.assertEqual(digest(item["state"]), answer["state_digest"])
            self.assertIsNone(answer["unavailable_reason"])
            self.assertFalse(answer["release"]["task_readiness"]["intent"]["policy_approved"])
            states.append(answer["state_digest"])
        self.assertEqual(3, len(set(states)))
        self.assertEqual(350000, runner.states[1]["payment"]["amount_minor"])
        self.assertNotIn("amount_minor", runner.states[2]["payment"])

    def test_rejects_invalid_money(self):
        for amount in (True, False, 1.5, "350000", 0, -1, 9223372036854775808):
            with self.subTest(amount=amount), self.assertRaises(InputError):
                validate_request(request(amount))

    def test_rejects_missing_unpermitted_unsupported_or_incomplete_context(self):
        mutations = [
            lambda r: r["processing_permissions"].update(semantic_remote=False),
            lambda r: r.update(profile="qris_presubmit_context"),
            lambda r: r.update(schema_version="2.0"),
            lambda r: r.update(snapshot_digest="fake"),
            lambda r: r.update(request_id="sensitive\nvalue"),
            lambda r: r.update(raw_qr="unexpected"),
            lambda r: r["state"].update(message="x" * 4097),
            lambda r: r["state"].update(message="😀" * 2049),
            lambda r: r["state"].update(message="\ud800"),
            lambda r: r["state"].update(message=" "),
            lambda r: r["state"]["payment"].update(merchant=""),
            lambda r: r.update(deadline_unix_ms=True),
            lambda r: r.update(deadline_unix_ms=int(time.time() * 1000) + 60000),
        ]
        for mutation in mutations:
            item = request()
            mutation(item)
            with self.assertRaises(InputError):
                validate_request(item)

    def test_duplicate_keys_and_nonfinite_json_are_rejected(self):
        for data in (b'{"state":{},"state":{}}', b'{"x":NaN}', b'{"x":Infinity}', b'[]', b'\xff'):
            with self.assertRaises(InputError):
                decode_json(data)

    def test_native_probabilities_and_task_identity_are_checked(self):
        validate_native(native(), "synthetic-model")
        mutations = [
            lambda n: n.update(model_id="another-release"),
            lambda n: n["intent"].update(label="SAFE"),
            lambda n: n["intent"].update(confidence=float("nan")),
            lambda n: n["intent"].update(confidence=True),
            lambda n: n["intent"]["probabilities"].update(OTHER=0),
            lambda n: n["intent"]["probabilities"].update(PAYMENT_REQUEST=0.5),
            lambda n: n.update(usage={}),
        ]
        for mutation in mutations:
            answer = native()
            mutation(answer)
            with self.assertRaises(NativeOutputError):
                validate_native(answer, "synthetic-model")
        for usage in ({"truncated": True, "state_tokens_dropped": 1}, {"options": {"intent": {"total": 5, "distinct": 4}}}):
            answer = native()
            answer["usage"].update(usage)
            with self.assertRaises(IncompleteInput):
                validate_native(answer, "synthetic-model")

    def test_owned_timeout_does_not_deliver_a_late_result_or_release_running_slot(self):
        started, finish = threading.Event(), threading.Event()

        class Blocking(FakeRunner):
            def predict(self, state):
                started.set()
                finish.wait(2)
                return super().predict(state)

        runner = Blocking()
        service = SemanticService(runner, capacity=1)
        try:
            status, answer = service.assess(request(budget=30))
            self.assertTrue(started.is_set())
            self.assertEqual((408, "deadline_exceeded", None), (status, answer["unavailable_reason"], answer["native"]))
            self.assertEqual(503, service.assess(request())[0])
            finish.set()
        finally:
            finish.set()
            service.close()
        self.assertEqual("unavailable", answer["status"])

    def test_expired_request_never_calls_runner(self):
        runner = FakeRunner()
        service = SemanticService(runner)
        self.addCleanup(service.close)
        self.assertEqual(408, service.assess(request(budget=-1))[0])
        self.assertEqual([], runner.states)

    def test_expired_queued_work_stays_bounded_and_is_skipped(self):
        started, finish = threading.Event(), threading.Event()

        class Blocking(FakeRunner):
            def predict(self, state):
                started.set()
                finish.wait(2)
                return super().predict(state)

        runner = Blocking()
        service = SemanticService(runner, capacity=2)
        thread = threading.Thread(target=lambda: service.assess(request()), daemon=True)
        thread.start()
        try:
            self.assertTrue(started.wait(1))
            self.assertEqual(408, service.assess(request(budget=30))[0])
            self.assertEqual(503, service.assess(request())[0])
        finally:
            finish.set()
            thread.join()
            service.close()
        self.assertEqual(1, len(runner.states))

    def test_worker_failure_is_sanitized(self):
        class Broken(FakeRunner):
            def predict(self, state):
                raise RuntimeError("private message should never appear")
        service = SemanticService(Broken())
        self.addCleanup(service.close)
        status, answer = service.assess(request())
        self.assertEqual((503, "inference_unavailable"), (status, answer["unavailable_reason"]))
        self.assertNotIn("private", json.dumps(answer))


class HttpTests(unittest.TestCase):
    def setUp(self):
        self.service = SemanticService(FakeRunner())
        self.server = LocalServer(("127.0.0.1", 0), self.service, "synthetic-test-token-" + "x" * 32)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.service.close()

    def send(self, method, path, value=None, auth=True):
        headers = {"Content-Type": "application/json"}
        if auth:
            headers["Authorization"] = "Bearer " + self.server.token
        connection = HTTPConnection(*self.server.server_address, timeout=2)
        try:
            connection.request(method, path, body=None if value is None else json.dumps(value), headers=headers)
            response = connection.getresponse()
            return response.status, decode_json(response.read()), response.getheader("Cache-Control")
        finally:
            connection.close()

    def test_health_authentication_and_correlated_response(self):
        status, answer, _ = self.send("GET", "/health", auth=False)
        self.assertEqual((200, {"status": "ready"}), (status, answer))
        self.assertEqual(401, self.send("GET", "/v1/release", auth=False)[0])
        self.assertEqual(401, self.send("POST", "/v1/semantic", request(), auth=False)[0])
        status, answer, cache = self.send("POST", "/v1/semantic", request(350000))
        self.assertEqual((200, "experimental", "no-store"), (status, answer["status"], cache))
        self.assertNotIn("message", answer)

    def test_bad_request_and_unsupported_path(self):
        self.assertEqual(400, self.send("POST", "/v1/semantic", {"state": {}})[0])
        self.assertEqual(404, self.send("POST", "/unknown", {})[0])


if __name__ == "__main__":
    unittest.main()
