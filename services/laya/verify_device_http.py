"""Owned Android HTTP acceptance; inject token over memory-only READY socket."""
from pathlib import Path
import argparse
import os
import shutil
import socket
import subprocess
import time


def main():
    folder = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--serial', help='ADB device serial; omit when only one device is attached')
    parser.add_argument('--adb', default=shutil.which('adb') or str(Path(os.environ.get('ANDROID_HOME', str(Path.home() / 'Library/Android/sdk'))) / 'platform-tools/adb'))
    args = parser.parse_args()
    # Caller installs APKs and sets reverse8765 / forward18766 in its device slot.
    command = [args.adb, *(['-s', args.serial] if args.serial else []), 'shell', 'am', 'instrument', '-w', '-e', 'class', 'com.example.hacknusa.SdkIntegrationTest', 'com.example.hacknusa.test/com.example.hacknusa.OwnedTestRunner']
    key, separator, token = (folder / '.env').read_text().strip().partition('=')
    if key != 'QRISHIELD_API_TOKEN' or not separator or len(token) < 32:
        raise ValueError('Invalid local test token configuration')
    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    cutoff = time.monotonic() + 25
    while process.poll() is None and time.monotonic() < cutoff:
        try:
            with socket.create_connection(('127.0.0.1', 18766), timeout=1) as connection:
                connection.settimeout(1)
                if connection.makefile('rb').readline() != b'READY\n':
                    raise ConnectionError()
                connection.sendall((token + '\n').encode())
                break
        except OSError:
            time.sleep(.2)
    output = process.communicate(timeout=60)[0].replace(token, '[redacted]')
    print(output)
    (folder / 'device-http-result.txt').write_text(output)
    if 'OK (1 test)' not in output:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
