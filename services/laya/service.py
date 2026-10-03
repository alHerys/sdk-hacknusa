"""Local, authenticated QRIShield semantic service. No request-content logging."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.metadata
import importlib.util
import json
import math
import os
from pathlib import Path
import platform
import re
import secrets
import threading
import time
from typing import Any

SCHEMA = "1.0"
TASK_LABELS = {
    "intent": ("PAYMENT_REQUEST", "PAST_PAYMENT", "PAYMENT_PROHIBITION", "NON_PAYMENT", "AMBIGUOUS"),
    "recipient_relation": ("CONSISTENT", "INCONSISTENT", "INSUFFICIENT_EVIDENCE"),
}
MAX_BODY_BYTES = 32768
MAX_TEXT_UNITS = 4096
MAX_DEADLINE_MS = 30000
SHA256 = re.compile(r"[0-9a-f]{64}\Z")
REQUEST_ID = re.compile(r"[A-Za-z0-9_.-]{1,128}\Z")
RUNTIME_PINS = {
    "laya": "0.3.24", "torch": "2.14.1", "transformers": "5.18.0",
    "safetensors": "0.8.0", "tokenizers": "0.23.2", "numpy": "2.5.3",
    "huggingface-hub": "1.33.0",
}


class InputError(ValueError):
    pass


class IncompleteInput(ValueError):
    pass


class NativeOutputError(ValueError):
    pass


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise InputError("duplicate_json_key")
        result[key] = value
    return result


def _nonfinite(_):
    raise InputError("nonfinite_json_number")


def decode_json(data: bytes) -> dict:
    try:
        result = json.loads(data.decode("utf-8"), object_pairs_hook=_object, parse_constant=_nonfinite)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise InputError("invalid_json") from error
    if not isinstance(result, dict):
        raise InputError("object_required")
    return result


def _keys(value, required, optional=()):
    if not isinstance(value, dict) or not set(required).issubset(value) or set(value) - set(required) - set(optional):
        raise InputError("invalid_fields")


def _text(value):
    if not isinstance(value, str) or not value.strip():
        raise InputError("nonempty_text_required")
    try:
        units = len(value.encode("utf-16-le")) // 2
    except UnicodeError as error:
        raise InputError("invalid_unicode") from error
    if units > MAX_TEXT_UNITS:
        raise InputError("text_too_long")


def validate_request(request: dict, now_ms: int | None = None) -> float:
    _keys(request, ("schema_version", "request_id", "profile", "snapshot_digest",
                    "deadline_unix_ms", "processing_permissions", "state"))
    if request["schema_version"] != SCHEMA or request["profile"] != "qris_artifact_context":
        raise InputError("unsupported_schema_or_profile")
    if not isinstance(request["request_id"], str) or not REQUEST_ID.fullmatch(request["request_id"]):
        raise InputError("invalid_request_id")
    if not isinstance(request["snapshot_digest"], str) or not SHA256.fullmatch(request["snapshot_digest"]):
        raise InputError("invalid_snapshot_digest")
    deadline = request["deadline_unix_ms"]
    if type(deadline) is not int:
        raise InputError("invalid_deadline")
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    remaining = deadline - now_ms
    if remaining > MAX_DEADLINE_MS:
        raise InputError("deadline_too_far")
    _keys(request["processing_permissions"], ("semantic_remote",))
    if request["processing_permissions"]["semantic_remote"] is not True:
        raise InputError("semantic_permission_required")
    state = request["state"]
    _keys(state, ("message", "payment"))
    _text(state["message"])
    _keys(state["payment"], ("merchant",), ("amount_minor",))
    _text(state["payment"]["merchant"])
    if "amount_minor" in state["payment"]:
        amount = state["payment"]["amount_minor"]
        if amount is not None and (type(amount) is not int or not 0 < amount <= 9223372036854775807):
            raise InputError("amount_must_be_positive_whole_rupiah_or_null")
    return time.monotonic() + remaining / 1000


def validate_native(answer: dict, model_id: str) -> None:
    if not isinstance(answer, dict) or set(answer) != {"schema_version", "model_id", "usage", *TASK_LABELS}:
        raise NativeOutputError("native_fields")
    if answer["schema_version"] != SCHEMA or answer["model_id"] != model_id:
        raise NativeOutputError("native_identity")
    usage = answer["usage"]
    usage_fields = {"input_tokens", "output_tokens", "state_tokens", "state_tokens_dropped", "truncated", "truncated_questions"}
    if not isinstance(usage, dict) or not usage_fields.issubset(usage) or set(usage) - usage_fields - {"options"}:
        raise NativeOutputError("native_usage")
    for field in ("input_tokens", "output_tokens", "state_tokens", "state_tokens_dropped"):
        if type(usage[field]) is not int or usage[field] < 0:
            raise NativeOutputError("native_usage_counts")
    if type(usage["truncated"]) is not bool or usage["truncated"] != (usage["state_tokens_dropped"] > 0):
        raise NativeOutputError("native_usage_truncation")
    questions = usage["truncated_questions"]
    if not isinstance(questions, list) or any(type(q) is not str or q not in TASK_LABELS for q in questions) or len(set(questions)) != len(questions):
        raise NativeOutputError("native_usage_questions")
    options = usage.get("options", {})
    if not isinstance(options, dict) or any(task not in TASK_LABELS for task in options):
        raise NativeOutputError("native_usage_options")
    if usage["truncated"] or questions or options:
        raise IncompleteInput("native_token_budget")
    if usage["output_tokens"] != 0:
        raise NativeOutputError("native_generated_output")
    for task, labels in TASK_LABELS.items():
        value = answer[task]
        if not isinstance(value, dict) or set(value) != {"label", "confidence", "probabilities"}:
            raise NativeOutputError("native_task_fields")
        probabilities = value["probabilities"]
        if value["label"] not in labels or not isinstance(probabilities, dict) or set(probabilities) != set(labels):
            raise NativeOutputError("native_labels")
        numbers = [value["confidence"], *probabilities.values()]
        if any(type(p) not in (int, float) or not math.isfinite(p) or not 0 <= p <= 1 for p in numbers):
            raise NativeOutputError("native_probabilities")
        if abs(sum(probabilities.values()) - 1) > 0.001 or abs(value["confidence"] - probabilities[value["label"]]) > 0.0001:
            raise NativeOutputError("native_probability_agreement")


class LayaRunner:
    """One immutable release, loaded offline once. Worker access is serialized."""

    def __init__(self, descriptor_path: Path):
        descriptor_path = descriptor_path.resolve()
        descriptor_bytes = descriptor_path.read_bytes()
        descriptor = decode_json(descriptor_bytes)
        self.bundle = (descriptor_path.parent / descriptor["bundle"]).resolve()
        manifest_bytes = (self.bundle / "manifest.json").read_bytes()
        if hashlib.sha256(manifest_bytes).hexdigest() != descriptor["expected_manifest_sha256"]:
            raise ValueError("Untrusted model manifest")
        if descriptor["native_schema_version"] != SCHEMA or descriptor["descriptor_version"] != SCHEMA:
            raise ValueError("Unsupported release contract")
        required_settings = {"device": "cpu", "amp": "off", "fast": False, "compile": False,
                             "threads": 6, "max_len": 1024, "head_max_len": 512}
        if descriptor["inference_settings"] != required_settings:
            raise ValueError("Inference settings require separate compatibility validation")
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        os.environ["LAYA_CPU_AMP"] = "off"
        runtime = {name: importlib.metadata.version(name) for name in RUNTIME_PINS}
        runtime_environment = {distribution.metadata["Name"]: distribution.version
                               for distribution in importlib.metadata.distributions()}
        runtime_fingerprint = digest({"packages": runtime_environment,
                                      "python": platform.python_version(), "platform": platform.platform()})
        for name, version in runtime.items():
            if version.split("+")[0] != RUNTIME_PINS[name]:
                raise ValueError("Runtime version differs from selected release")
        import torch
        torch.set_num_threads(required_settings["threads"])
        torch.set_num_interop_threads(1)
        spec = importlib.util.spec_from_file_location("qrishield_bundle_adapter", self.bundle / "sdk_adapter.py")
        adapter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(adapter)
        manifest = adapter.verify_bundle(self.bundle)
        if manifest["model_id"] != descriptor["model_id"] or manifest["schema_version"] != SCHEMA:
            raise ValueError("Release identity differs from manifest")
        contract = decode_json((self.bundle / "contract.json").read_bytes())
        if contract["tasks"] != {k: list(v) for k, v in TASK_LABELS.items()} or contract["token_budgets"] != {"max_len": 1024, "head_max_len": 512}:
            raise ValueError("Unsupported model tasks or budgets")
        self.model = adapter.HacknusaLaya(self.bundle, device="cpu", verify=True)
        self.unset = adapter.UNSET
        # Promotion to inference_ready requires the selected release's actual fixtures.
        self.smoke = self.model.self_test()
        identity = {
            "manifest_sha256": descriptor["expected_manifest_sha256"],
            "descriptor_sha256": hashlib.sha256(descriptor_bytes).hexdigest(),
            "files_sha256": manifest["files_sha256"], "runtime": runtime,
            "runtime_fingerprint": runtime_fingerprint,
            "service_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "python": platform.python_version(), "platform": platform.platform(),
            "inference_settings": required_settings,
        }
        # This release has no independently approved or calibrated policy tasks.
        if descriptor["task_policy_approved"] != {task: False for task in TASK_LABELS}:
            raise ValueError("This PoC runner does not implement policy approval")
        self.release = {
            "model_id": manifest["model_id"], "fingerprint": digest(identity),
            "manifest_sha256": descriptor["expected_manifest_sha256"],
            "contract_sha256": manifest["files_sha256"]["contract.json"],
            "questions_sha256": manifest["files_sha256"]["questions.json"],
            "tokenizer_sha256": manifest["files_sha256"]["model/tokenizer/tokenizer.json"],
            "adapter_sha256": manifest["files_sha256"]["sdk_adapter.py"],
            "runtime": runtime, "runtime_fingerprint": runtime_fingerprint,
            "inference_settings": required_settings,
            "policy_version": descriptor["policy_version"], "calibration_version": None,
            "task_readiness": {task: {"loadable": True, "inference_ready": True, "policy_approved": False}
                               for task in TASK_LABELS},
        }

    def predict(self, state: dict) -> dict:
        payment = state["payment"]
        try:
            answer = self.model.predict(state["message"], payment["merchant"], payment.get("amount_minor", self.unset))
        except ValueError as error:
            if str(error) == "Input exceeded token budgets or options were collapsed":
                raise IncompleteInput("native_token_budget") from error
            raise
        validate_native(answer, self.release["model_id"])
        return answer


class SemanticService:
    def __init__(self, runner, capacity=4, matcher=None):
        self.runner = runner
        self.matcher = matcher
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="laya-inference")
        self.slots = threading.BoundedSemaphore(capacity)

    def assess(self, request: dict) -> tuple[int, dict]:
        cutoff = validate_request(request)
        # Canonical round trip freezes caller-owned structures before queued execution.
        state = decode_json(canonical(request["state"]))
        envelope = {
            "schema_version": SCHEMA, "request_id": request["request_id"],
            "profile": request["profile"], "snapshot_digest": request["snapshot_digest"],
            "state_digest": digest(state), "release": self.runner.release,
            "status": "unavailable", "unavailable_reason": None, "native": None,
        }

        def unavailable(status, reason):
            return status, {**envelope, "unavailable_reason": reason}

        if time.monotonic() >= cutoff:
            return unavailable(408, "deadline_exceeded")
        if not self.slots.acquire(blocking=False):
            return unavailable(503, "busy")

        def invoke():
            if time.monotonic() >= cutoff:
                raise FutureTimeout()
            result = self.runner.predict(state)
            validate_native(result, self.runner.release["model_id"])
            if time.monotonic() >= cutoff:
                raise FutureTimeout()
            return result

        try:
            future = self.executor.submit(invoke)
        except Exception:
            self.slots.release()
            return unavailable(503, "worker_unavailable")
        future.add_done_callback(lambda _: self.slots.release())
        try:
            result = future.result(timeout=max(0, cutoff - time.monotonic()))
            return 200, {**envelope, "status": "experimental", "native": result}
        except FutureTimeout:
            # Keep the slot until the worker dequeues the expired job. Cancelling a
            # Future releases callbacks early but leaves work in the executor's
            # queue, allowing cancelled entries to accumulate behind native work.
            # invoke() skips expired queued work; running work cannot answer late.
            return unavailable(408, "deadline_exceeded")
        except IncompleteInput:
            return unavailable(422, "incomplete_input")
        except NativeOutputError:
            return unavailable(502, "invalid_model_output")
        except Exception:
            return unavailable(503, "inference_unavailable")

    def find_context(self, request):
        from matcher import context_match
        return context_match(self, request)

    def close(self):
        self.executor.shutdown(wait=True, cancel_futures=True)


class LocalServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address, service, token):
        self.service = service
        self.token = token
        self.connections = threading.BoundedSemaphore(16)
        super().__init__(address, Handler)

    def process_request(self, request, address):
        if not self.connections.acquire(blocking=False):
            try:
                request.settimeout(1)
                request.sendall(b'HTTP/1.1 503 Service Unavailable\r\nContent-Length: 0\r\nConnection: close\r\n\r\n')
            finally:
                self.shutdown_request(request)
            return
        try:
            super().process_request(request, address)
        except Exception:
            self.connections.release()
            raise

    def process_request_thread(self, request, address):
        try:
            super().process_request_thread(request, address)
        finally:
            self.connections.release()

    def handle_error(self, request, client_address):
        # Never emit traceback/request headers or body to logs.
        pass


class Handler(BaseHTTPRequestHandler):
    server_version = "QRIShieldLocal/1"
    sys_version = ""

    def setup(self):
        super().setup()
        self.connection.settimeout(5)

    def log_message(self, *_):
        pass

    def _reply(self, status, value):
        body = canonical(value)
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _authenticated(self):
        values = self.headers.get_all("Authorization", [])
        valid = len(values) == 1 and secrets.compare_digest(values[0].encode(), ("Bearer " + self.server.token).encode())
        if not valid:
            self._reply(401, {"error": "unauthorized"})
        return valid

    def do_GET(self):
        if self.path == "/health":
            self._reply(200, {"status": "ready"})
        elif self.path == "/v1/release" and self._authenticated():
            self._reply(200, {"schema_version": SCHEMA, "release": self.server.service.runner.release})
        elif self.path != "/v1/release":
            self._reply(404, {"error": "not_found"})

    def do_POST(self):
        if self.path not in ("/v1/semantic", "/v1/context-match"):
            self._reply(404, {"error": "not_found"})
            return
        if not self._authenticated():
            return
        lengths = self.headers.get_all("Content-Length", [])
        if len(lengths) != 1 or not re.fullmatch(r"[0-9]{1,8}", lengths[0]) or self.headers.get("Transfer-Encoding"):
            self._reply(400, {"error": "content_length_required"})
            return
        length = int(lengths[0])
        if not 0 < length <= (524288 if self.path == "/v1/context-match" else MAX_BODY_BYTES):
            self._reply(413, {"error": "body_too_large"})
            return
        if self.headers.get_content_type() != "application/json":
            self._reply(415, {"error": "json_required"})
            return
        try:
            body = self.rfile.read(length)
            if len(body) != length:
                raise InputError("incomplete_body")
            request = decode_json(body)
            status, answer = (self.server.service.find_context(request) if self.path == "/v1/context-match" else self.server.service.assess(request))
        except InputError as error:
            self._reply(400, {"error": str(error)})
            return
        except (TimeoutError, ConnectionError, OSError):
            self._reply(408, {"error": "body_timeout"})
            return
        self._reply(status, answer)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", type=Path, default=Path(__file__).with_name("release.json"))
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--check", action="store_true", help="Verify integrity, load the model, run native smoke fixtures, then exit")
    args = parser.parse_args()
    token = os.environ.get("QRISHIELD_API_TOKEN", "")
    if not args.check and (len(token) < 32 or not token.isascii() or any(c.isspace() for c in token)):
        parser.error("Set QRISHIELD_API_TOKEN to at least 32 ASCII characters without whitespace")
    runner = LayaRunner(args.release)
    if args.check:
        print(json.dumps({"status": "inference_ready", "smoke": runner.smoke, "release": runner.release}, indent=2))
        return
    from matcher import E5Runner
    try:
        matcher = E5Runner()
    except Exception:
        matcher = None  # Manual semantic assessment remains independently available.
        print("Matcher unavailable; manual-context Laya remains available", flush=True)
    service = SemanticService(runner, matcher=matcher)
    server = LocalServer(("127.0.0.1", args.port), service, token)
    print(f"QRIShield local service ready at http://127.0.0.1:{args.port}; native smoke passed; tasks experimental", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        service.close()


if __name__ == "__main__":
    import sys
    sys.modules["service"] = sys.modules[__name__]
    main()
