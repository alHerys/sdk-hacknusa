"""Start the loopback-only service with a persistent local token, never printed."""
import os
from pathlib import Path
import secrets
import sys


def main():
    folder = Path(__file__).resolve().parent
    token_file = folder / ".env"
    token = os.environ.get("QRISHIELD_API_TOKEN")
    if not token:
        if not token_file.exists():
            token = secrets.token_urlsafe(32)
            descriptor = os.open(token_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(descriptor, "w") as file:
                file.write("QRISHIELD_API_TOKEN=" + token + "\n")
        key, separator, token = token_file.read_text().strip().partition("=")
        if key != "QRISHIELD_API_TOKEN" or not separator:
            raise ValueError("Invalid token file")
        token_file.chmod(0o600)
    environment = {**os.environ, "QRISHIELD_API_TOKEN": token}
    os.execve(sys.executable, [sys.executable, str(folder / "service.py"), *sys.argv[1:]], environment)


if __name__ == "__main__":
    main()
