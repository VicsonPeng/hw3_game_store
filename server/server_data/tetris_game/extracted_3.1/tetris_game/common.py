# common.py
import json
import socket
import struct
import time

MAX_LEN = 65536

def send_frame(sock: socket.socket, payload: bytes) -> None:
    if not isinstance(payload, (bytes, bytearray)):
        raise TypeError("payload must be bytes")
    n = len(payload)
    if n <= 0 or n > MAX_LEN:
        raise ValueError(f"Invalid payload length {n}, must be 1..{MAX_LEN}")
    hdr = struct.pack('!I', n)
    sock.sendall(hdr + payload)

def recv_exact(sock: socket.socket, n: int) -> bytes:
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return b''
        buf.extend(chunk)
    return bytes(buf)

def recv_frame(sock: socket.socket) -> bytes:
    hdr = recv_exact(sock, 4)
    if len(hdr) < 4:
        return b''
    (n,) = struct.unpack('!I', hdr)
    if n <= 0 or n > MAX_LEN:
        return b''
    body = recv_exact(sock, n)
    if len(body) < n:
        return b''
    return body

def send_json(sock: socket.socket, obj) -> None:
    data = json.dumps(obj, separators=(',', ':'), ensure_ascii=False).encode('utf-8')
    send_frame(sock, data)

def recv_json(sock: socket.socket):
    data = recv_frame(sock)
    if not data:
        return None
    try:
        return json.loads(data.decode('utf-8'))
    except Exception:
        return None

def now_ms() -> int:
    return int(time.time() * 1000)

def pick_free_port(start=10000, end=20000) -> int:
    import random, socket
    for _ in range(2000):
        p = random.randint(start, end)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind(('', p))
                return p
            except OSError:
                continue
    raise RuntimeError("No free port found")

def sha256(s: str) -> str:
    import hashlib
    return hashlib.sha256(s.encode('utf-8')).hexdigest()
