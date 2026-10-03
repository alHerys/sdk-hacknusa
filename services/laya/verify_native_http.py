"""Verify a running local service using export fixtures and synthetic failures."""
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import time

from service import canonical, digest, validate_native


def main():
    folder = Path(__file__).resolve().parent
    token = os.environ.get("QRISHIELD_API_TOKEN")
    if not token:
        key, separator, token = (folder / ".env").read_text().strip().partition("=")
        if key != "QRISHIELD_API_TOKEN" or not separator:
            raise ValueError("Invalid token file")

    def send(state, identifier, budget=30000, authorization=True):
        request = {"schema_version": "1.0", "request_id": identifier,
                   "profile": "qris_artifact_context", "snapshot_digest": digest({"fixture": identifier, "state": state}),
                   "deadline_unix_ms": int(time.time() * 1000) + budget,
                   "processing_permissions": {"semantic_remote": True}, "state": state}
        headers = {"Content-Type": "application/json"}
        if authorization:
            headers["Authorization"] = "Bearer " + token
        connection = HTTPConnection("127.0.0.1", 8765, timeout=31)
        start = time.monotonic()
        try:
            connection.request("POST", "/v1/semantic", canonical(request), headers)
            response = connection.getresponse()
            result = json.loads(response.read())
            if "request_id" in result:
                assert result["request_id"] == request["request_id"]
                assert result["snapshot_digest"] == request["snapshot_digest"]
                assert result["state_digest"] == digest(state)
            return response.status, result, round((time.monotonic() - start) * 1000, 1)
        finally:
            connection.close()

    fixtures = json.loads((folder.parents[1] / "hacknusa-laya-450-50-v1/smoke_tests.json").read_text())
    checks = []
    for fixture in fixtures:
        source = fixture["input"]
        payment = {"merchant": source["merchant"]}
        if "amount_minor" in source:
            payment["amount_minor"] = source["amount_minor"]
        state = {"message": source["message"], "payment": payment}
        status, result, latency = send(state, "native-" + str(fixture["id"]))
        assert status == 200 and result["status"] == "experimental"
        validate_native(result["native"], "hacknusa-laya-450-50-v1")
        for task in ("intent", "recipient_relation"):
            actual, expected = result["native"][task], fixture["expected"][task]
            assert actual["label"] == expected["label"]
            assert abs(actual["confidence"] - expected["confidence"]) <= 1e-4
            assert all(abs(actual["probabilities"][label] - probability) <= 1e-4
                       for label, probability in expected["probabilities"].items())
            assert result["release"]["task_readiness"][task]["policy_approved"] is False
        checks.append({"fixture": fixture["id"], "http": status, "latency_ms": latency, "native_parity": "passed"})
    state = {"message": "bayar ke BUDI STORE", "payment": {"merchant": "BUDI STORE"}}
    assert send(state, "omitted-amount")[0] == 200
    assert send(state, "unauthenticated", authorization=False)[0] == 401
    assert send(state, "expired-deadline", budget=-1)[0] == 408
    state["message"] = "x " * 2000
    status, result, _ = send(state, "native-truncated")
    assert status == 422 and result["unavailable_reason"] == "incomplete_input"
    state["message"] = "x" * 4097
    assert send(state, "oversized-context")[0] == 400
    print(json.dumps({"status": "passed", "native_http_fixtures": checks,
                      "omitted_amount_auth_deadline_truncation_oversize": "passed"}, indent=2))


if __name__ == "__main__":
    main()
