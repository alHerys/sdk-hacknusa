"""Exercise the local service with one synthetic, explicitly permitted assessment."""
import argparse
from http.client import HTTPConnection
import json
import os
from pathlib import Path
import time
import uuid

from service import canonical, digest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--token-file", type=Path, default=Path(__file__).with_name(".env"))
    args = parser.parse_args()
    token = os.environ.get("QRISHIELD_API_TOKEN")
    if token is None and args.token_file.exists():
        key, separator, token = args.token_file.read_text().strip().partition("=")
        if key != "QRISHIELD_API_TOKEN" or not separator:
            parser.error("Invalid token file")
    if not token:
        parser.error("Set QRISHIELD_API_TOKEN or create the local token file")
    state = {"message": "Pak, tolong transfer 4,2 juta ke CV Berkah Motor untuk servis",
             "payment": {"merchant": "CV BERKAH MOTOR", "amount_minor": 4200000}}
    body = {"schema_version": "1.0", "request_id": str(uuid.uuid4()), "profile": "qris_artifact_context",
            "snapshot_digest": digest({"fixture": "export-smoke-7", "state": state}),
            "deadline_unix_ms": int(time.time() * 1000) + 30000,
            "processing_permissions": {"semantic_remote": True}, "state": state}
    connection = HTTPConnection("127.0.0.1", args.port, timeout=31)
    try:
        connection.request("POST", "/v1/semantic", canonical(body),
                           {"Content-Type": "application/json", "Authorization": "Bearer " + token})
        response = connection.getresponse()
        result = json.loads(response.read())
        if result.get("request_id") != body["request_id"] or result.get("snapshot_digest") != body["snapshot_digest"] or result.get("state_digest") != digest(state):
            raise ValueError("Uncorrelated service response")
        print(json.dumps({"http_status": response.status, **result}, indent=2))
    finally:
        connection.close()


if __name__ == "__main__":
    main()
