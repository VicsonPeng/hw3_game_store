import socket
import json
import struct
import os

def send_json(sock, data):
    try:
        json_str = json.dumps(data)
        encoded = json_str.encode('utf-8')
        header = struct.pack('!I', len(encoded))
        sock.sendall(header + encoded)
        return True
    except (socket.error, BrokenPipeError, AttributeError):
        # 對方斷線或 socket 已關閉
        return False

def recv_json(sock):
    try:
        header = recv_all(sock, 4)
        if not header:
            return None
        length = struct.unpack('!I', header)[0]
        data = recv_all(sock, length)
        if not data:
            return None
        return json.loads(data.decode('utf-8'))
    except (socket.error, ConnectionResetError, struct.error, json.JSONDecodeError, AttributeError):
        return None

def recv_all(sock, n):
    data = b''
    try:
        while len(data) < n:
            packet = sock.recv(n - len(data))
            if not packet:
                return None
            data += packet
        return data
    except socket.error:
        return None

def send_file(sock, filepath):
    try:
        if not os.path.exists(filepath):
            return False
        filesize = os.path.getsize(filepath)
        # 先送檔案資訊
        if not send_json(sock, {'type': 'FILE_INFO', 'size': filesize}):
            return False
        
        with open(filepath, 'rb') as f:
            while True:
                chunk = f.read(4096)
                if not chunk: break
                sock.sendall(chunk)
        return True
    except Exception as e:
        print(f"[Transport Error] Send file failed: {e}")
        return False

def recv_file(sock, output_path, size):
    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        remaining = size
        with open(output_path, 'wb') as f:
            while remaining > 0:
                chunk_size = 4096 if remaining > 4096 else remaining
                data = sock.recv(chunk_size)
                if not data: return False
                f.write(data)
                remaining -= len(data)
        return True
    except Exception as e:
        print(f"[Transport Error] Recv file failed: {e}")
        return False