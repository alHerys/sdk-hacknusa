# Local Laya service

The supplied model is loaded once, offline, with its original questions and token
budgets. Startup verifies the trusted manifest digest, all bundle checksums, the
runtime versions, and all four native smoke fixtures. Assessments execute on one
CPU worker; capacity is four outstanding jobs, including the running job.

This implements semantic classification for the `qris_artifact_context` PoC.
Both tasks remain experimental and uncalibrated. The response never authorizes
payment. QR parsing, CRC checks, evidence selection, local policy, binding
lifetime, UI, and cancellation of stale UI updates belong in the Kotlin SDK/host.

## Run on this workspace's Mac

From `/Users/hery/coding/sdk-hacknusa`:

```bash
services/laya/.venv/bin/python services/laya/run_local.py
```

The isolated Python 3.12 environment is installed. The service listens only at
`http://127.0.0.1:8765`. The launcher creates `services/laya/.env` with mode 0600
containing a random bearer token. It never prints the token. The file and virtual
environment are ignored by Git. Set `QRISHIELD_API_TOKEN` to use a supplied token.

Exercise the real model with synthetic evidence in a second terminal:

```bash
services/laya/.venv/bin/python services/laya/demo_client.py
services/laya/.venv/bin/python services/laya/verify_native_http.py
```

Integrity/load/smoke check without running a server:

```bash
services/laya/.venv/bin/python services/laya/service.py --check
services/laya/.venv/bin/python -m unittest discover -s services/laya -p 'test_*.py' -v
```

For a fresh Mac installation, create a Python 3.12 virtual environment, then run
`python -m pip install -r services/laya/runtime-lock.txt` for the verified complete
Mac runtime, or use `requirements-macos.txt` for just its seven primary pins. The supplied
Linux `torch==2.14.1+cpu` pin has no macOS wheel; the Mac requirements use
`torch==2.14.1` on CPU and require smoke parity at startup. All other inference
pins match the export. `runtime-lock.txt` records the installed local environment.
For a Linux service, install the original bundle's `requirements.txt` with the
official PyTorch CPU wheel index and run the same startup check on that platform.

## HTTP contract, version 1.0

`GET /health` returns only `{"status":"ready"}`. `GET /v1/release` and
`POST /v1/semantic` require `Authorization: Bearer <token>`.
POST also requires `Content-Type: application/json` and a fixed Content-Length.
Bodies are limited to 32 KiB. Duplicate JSON keys, extra fields, invalid Unicode,
and nonfinite numbers are rejected. Access/request-content logging is disabled.
Responses use `Cache-Control: no-store`.

POST request:

```json
{
  "schema_version": "1.0",
  "request_id": "assessment-uuid",
  "profile": "qris_artifact_context",
  "snapshot_digest": "<64 lowercase hexadecimal characters>",
  "deadline_unix_ms": 0,
  "processing_permissions": {"semantic_remote": true},
  "state": {
    "message": "bro tf 350rb ke budi ya",
    "payment": {"merchant": "BUDI STORE", "amount_minor": 350000}
  }
}
```

Replace the example deadline with current Unix milliseconds plus at most 30,000.
Request IDs contain 1–128 ASCII letters, digits, underscores, dots, or hyphens.
Message and merchant must be nonblank, valid Unicode, and at most 4,096 UTF-16
code units each. Messages are intended to be reviewed Indonesian context; the
service does not detect language or establish evidence authority. The host must
reject incomplete acquisition text before calling this service.

`amount_minor` means **whole rupiah**, not cents. It may be omitted, explicitly
null, or a positive signed-64-bit integer. Omission and null are preserved as
different native states. The app's absent tag54 maps to null. Raw QR, image,
currency, sender identity, and context linkage are not sent to the model.

The SDK creates `snapshot_digest` from its frozen artifact/context; the service
echoes it for correlation, without authenticating its evidence. `state_digest`
is SHA-256 of the exact state serialized as UTF-8 JSON with recursively sorted
keys, no insignificant whitespace, unescaped Unicode, and decimal integers.
The SDK must validate request ID, profile, both digests, release identity, and
native result before applying an answer to the same active snapshot.

The response always includes `schema_version`, `request_id`, `profile`,
`snapshot_digest`, `state_digest`, `release`, `status`, `unavailable_reason`, and
`native`. On HTTP 200, `status` is `experimental`, `unavailable_reason` is null,
and `native` contains the unchanged adapter response: native schema/model ID,
both task labels/confidence/probabilities, and usage. Release metadata includes
fingerprints, settings, runtime pins and per-task readiness. Policy approval is
false and calibration version is null for this release.

| HTTP | Meaning |
| --- | --- |
| 400 | Invalid request; generic error code, no sensitive input echo |
| 401 | Missing or incorrect bearer token |
| 408 | Deadline exceeded; correlated unavailable envelope for a valid assessment |
| 413 / 415 | Body too large / non-JSON body |
| 422 | Native token budget exceeded or options collapsed; incomplete input |
| 502 | Native output fails identity/schema/probability/usage checks |
| 503 | Worker capacity exhausted, stopped worker, or native inference unavailable |

Timed-out native work may finish in the background, keeping its capacity slot
until it finishes. Its answer is discarded. Expired queued jobs are skipped
before inference. No automatic retry, evidence persistence, or request cache is
implemented. The service has bounded HTTP connection threads as well.

This is a loopback development service. Android integration needs an explicit
development tunnel/ADB forwarding and debug network configuration; shared
deployment needs an HTTPS/auth deployment contract. Remote assessment also
requires the app's network permission and accurate processing disclosure.

## Model updates

Stage a complete bundle and a new trusted `release.json`, then start and check a
new service process with `--release /absolute/path/release.json`. Compatible
weight-only releases retain this wire contract. Startup rejects changed label
sets, budgets, runtime pins, or inference settings until compatibility is
implemented. Do not edit a live bundle. A new process pins its own immutable
descriptor and fingerprint; native smoke expectations come from that bundle.
Production calibration, approval, traffic promotion and rollback orchestration
remain the later plan stages.

## Validation performed

On 3 October 2026: all 16 bundle hashes matched; installed dependencies passed
`pip check`; the actual checkpoint passed all four export smoke fixtures on Mac
CPU; 11 synthetic service contract/queue/deadline/HTTP tests passed. Authenticated
HTTP repeated all four fixture outputs, including the known fixture-66 model
mistake, and checked amount omission, explicit null, unauthorized access, expired
deadline, native token overflow, and oversized context. These checks validate
wiring and export parity, not production classification quality.

## Revision 6: context matcher

`POST /v1/context-match` is separate from the unchanged semantic endpoint. It
requires bearer auth, fixed JSON Content-Length, `matching_local: true`, at most
20 candidate ID/text pairs, a 512 KiB body and a deadline at most30 seconds.

```json
{
  "schema_version": "1.0",
  "request_id": "match-uuid",
  "profile": "qris_artifact_context",
  "snapshot_digest": "<64 lowercase hexadecimal characters>",
  "deadline_unix_ms": 0,
  "processing_permissions": {"matching_local": true},
  "qr": {"merchant": "BUDI STORE", "city": "JAKARTA", "amount_minor": 350000},
  "candidates": [{"candidate_id": "opaque-id", "text": "bayar ke Budi Store ya"}]
}
```

Use a real deadline instead of0. `city` and `amount_minor` are nullable. Merchant,
city and amount are QR observations, never extracted from candidate text. No raw
QR, sender, image or conversation IDs enter the matcher request.

Response correlation fields echo schema/request/profile/snapshot and include
`input_digest` (canonical SHA256 of `{qr,candidates}`), `matcher_fingerprint`,
`status`, `unavailable_reason`, `suggestions` and `skipped`. Each suggestion has
`candidate_id`/`cosine`; each skip has `candidate_id`/`reason`. At most three
suggestions, descending finite cosine, stable input order for ties. There is no
threshold asserting a match, no automatic context selection or payment verdict.

E5 uses the pinned revision/checksum lock in `matcher-release.json`, CPU FP32,
masked mean attention pooling/L2,384 dimensions, query/passage prefixes and
512-token preflight. Candidates exceeding512 tokens,4096 UTF-16 units or blank
text are skipped explicitly. No hidden truncation. Model batches are at most4.
Run `stage_matcher.py` once to provision files; startup never downloads them.

The shared executor has one worker and four outstanding jobs total across both
endpoints. Native timeout does not release capacity until work finishes. Matcher
load/inference failure leaves manual semantic assessment available. Both models
remain experimental. `--check` verifies the supplied Laya release only; E5 smoke
runs at normal integrated-service startup and `benchmark_matcher.py` records the
synthetic retrieval benchmark. Fifteen regression tests now pass (including the
original eleven Laya service tests). Native HTTP smoke remains unchanged.
