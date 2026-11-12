'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Shirayume-Hibiki          ║
║  Creation date:            12/11/26                  ║
║  Edit dates / contributor:                           ║
╚══════════════════════════════════════════════════════╝
'''

import json
import socket
import struct
import time

FRAME_MAGIC: bytes = b"LC"
HEADER_FORMAT: str = "!2sHI"
HEADER_SIZE: int = struct.calcsize(HEADER_FORMAT)  # 8 bytes

# Message Types
TYPE_CHAT: str = "CHAT"
TYPE_FILE_PROPOSE: str = "FILE_PROPOSE"
TYPE_FILE_ACCEPT: str = "FILE_ACCEPT"
TYPE_FILE_REJECT: str = "FILE_REJECT"
TYPE_FILE_CHUNK: str = "FILE_CHUNK"
TYPE_FILE_COMPLETE: str = "FILE_COMPLETE"
TYPE_LEAVE: str = "LEAVE"

def sendFrame(sock: socket.socket, msg_type: str, metadata: dict | None = None, body: bytes = b"") -> None:
    if metadata is None:
        metadata = {}
    
    meta_copy = dict(metadata)
    meta_copy["type"] = msg_type
    if "ts" not in meta_copy:
        meta_copy["ts"] = time.time()
    
    meta_bytes = json.dumps(meta_copy).encode("utf-8")
    meta_len = len(meta_bytes)
    body_len = len(body)
    
    if meta_len > 65535:
        raise ValueError(f"Metadata too large ({meta_len} bytes, max 65535)")
    
    header = struct.pack(HEADER_FORMAT, FRAME_MAGIC, meta_len, body_len)
    
    # Send atomic frame: header + metadata + body
    packet = header + meta_bytes + body
    sock.sendall(packet)

def recvExact(sock: socket.socket, length: int) -> bytes:
    buffer = bytearray()
    while len(buffer) < length:
        remaining = length - len(buffer)
        chunk = sock.recv(min(remaining, 65536))
        if not chunk:
            raise ConnectionResetError("Connection closed unexpectedly while receiving data.")
        buffer.extend(chunk)
    return bytes(buffer)

def recvFrame(sock: socket.socket) -> tuple[dict, bytes] | None:
    try:
        raw_header = recvExact(sock, HEADER_SIZE)
        magic, meta_len, body_len = struct.unpack(HEADER_FORMAT, raw_header)
        
        if magic != FRAME_MAGIC:
            raise ValueError(f"Invalid frame magic: {magic}")
        
        meta_bytes = recvExact(sock, meta_len) if meta_len > 0 else b"{}"
        metadata = json.loads(meta_bytes.decode("utf-8", errors="replace"))
        
        body_bytes = recvExact(sock, body_len) if body_len > 0 else b""
        return metadata, body_bytes
    except (ConnectionResetError, ConnectionAbortedError, BrokenPipeError, socket.timeout):
        return None
    except Exception:
        return None
