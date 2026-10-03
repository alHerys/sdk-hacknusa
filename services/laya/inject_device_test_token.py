"""Send token only to the owned test's temporary forwarded socket; no files/logs on device."""
from pathlib import Path
import socket, time
folder=Path(__file__).resolve().parent
token=(folder/'.env').read_text().strip().partition('=')[2]
deadline=time.monotonic()+45
while True:
    try:
        with socket.create_connection(('127.0.0.1',18766),timeout=1) as connection:
            if connection.makefile('rb').readline() != b'READY\n': raise ConnectionError()
            connection.sendall((token+'\n').encode());print('Injected in-memory test token',flush=True);break
    except OSError:
        if time.monotonic()>=deadline:raise RuntimeError('Owned instrumentation token socket not available') from None
        time.sleep(.3)
