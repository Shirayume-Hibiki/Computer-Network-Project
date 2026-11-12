'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Shirayume-Hibiki          ║
║  Creation date:            12/11/26                  ║
║  Edit dates / contributor:                           ║
╚══════════════════════════════════════════════════════╝
'''

import hashlib
import os
import socket
import threading
import uuid
from typing import Callable

from protocol.tcp_protocol import (
    TYPE_FILE_ACCEPT,
    TYPE_FILE_CHUNK,
    TYPE_FILE_COMPLETE,
    TYPE_FILE_PROPOSE,
    TYPE_FILE_REJECT,
    sendFrame,
)

DEFAULT_CHUNK_SIZE: int = 65536  # 64 KB

def calculateSha256(filepath: str) -> str:
    hasher = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()

def getUniqueDownloadPath(downloads_dir: str, filename: str) -> str:
    os.makedirs(downloads_dir, exist_ok=True)
    base_name, ext = os.path.splitext(os.path.basename(filename))
    candidate = os.path.join(downloads_dir, f"{base_name}{ext}")
    counter = 1
    while os.path.exists(candidate):
        candidate = os.path.join(downloads_dir, f"{base_name}_{counter}{ext}")
        counter += 1
    return candidate

class FileSender(threading.Thread):
    def __init__(
        self,
        sock: socket.socket,
        filepath: str,
        target_name: str,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        on_progress: Callable[[str, int, int, float], None] | None = None,
        on_complete: Callable[[str, str], None] | None = None,
        on_error: Callable[[str, str], None] | None = None,
    ):
        super().__init__(daemon=True, name="FileSenderThread")
        self.sock = sock
        self.filepath = filepath
        self.target_name = target_name
        self.chunk_size = chunk_size
        self.on_progress = on_progress
        self.on_complete = on_complete
        self.on_error = on_error
        self.file_id = str(uuid.uuid4())
        self.accepted_event = threading.Event()
        self.rejected_event = threading.Event()
        self.rejection_reason = ""

    def notifyAccepted(self, offset: int = 0) -> None:
        self.accepted_event.set()

    def notifyRejected(self, reason: str = "") -> None:
        self.rejection_reason = reason
        self.rejected_event.set()

    def run(self) -> None:
        filename = os.path.basename(self.filepath)
        try:
            if not os.path.isfile(self.filepath):
                if self.on_error:
                    self.on_error(filename, f"File not found: {self.filepath}")
                return

            file_size = os.path.getsize(self.filepath)
            checksum = calculateSha256(self.filepath)

            # Send FILE_PROPOSE
            sendFrame(
                self.sock,
                TYPE_FILE_PROPOSE,
                {
                    "file_id": self.file_id,
                    "filename": filename,
                    "file_size": file_size,
                    "sha256": checksum,
                },
            )

            # Wait for response (up to 30s)
            while not self.accepted_event.is_set():
                if self.rejected_event.is_set():
                    if self.on_error:
                        self.on_error(filename, f"Transfer rejected: {self.rejection_reason}")
                    return
                if not self.accepted_event.wait(timeout=30.0):
                    if self.on_error:
                        self.on_error(filename, "Transfer timed out waiting for peer acceptance.")
                    return

            total_chunks = (file_size + self.chunk_size - 1) // self.chunk_size
            bytes_sent = 0

            with open(self.filepath, "rb") as f:
                chunk_idx = 0
                while bytes_sent < file_size:
                    chunk = f.read(self.chunk_size)
                    if not chunk:
                        break
                    sendFrame(
                        self.sock,
                        TYPE_FILE_CHUNK,
                        {
                            "file_id": self.file_id,
                            "chunk_idx": chunk_idx,
                            "offset": bytes_sent,
                            "total_chunks": total_chunks,
                        },
                        body=chunk,
                    )
                    bytes_sent += len(chunk)
                    chunk_idx += 1
                    pct = (bytes_sent / file_size) * 100.0 if file_size > 0 else 100.0
                    if self.on_progress:
                        self.on_progress(filename, bytes_sent, file_size, pct)

            # Send FILE_COMPLETE
            sendFrame(
                self.sock,
                TYPE_FILE_COMPLETE,
                {
                    "file_id": self.file_id,
                    "sha256": checksum,
                },
            )

            if self.on_complete:
                self.on_complete(filename, self.filepath)

        except Exception as e:
            if self.on_error:
                self.on_error(filename, f"Error sending file: {e}")

class ActiveIncomingTransfer:
    def __init__(self, file_id: str, filename: str, file_size: int, expected_sha256: str, dest_path: str):
        self.file_id = file_id
        self.filename = filename
        self.file_size = file_size
        self.expected_sha256 = expected_sha256
        self.dest_path = dest_path
        self.file_handle = open(dest_path, "wb")
        self.hasher = hashlib.sha256()
        self.bytes_received = 0

    def writeChunk(self, chunk: bytes) -> None:
        self.file_handle.write(chunk)
        self.hasher.update(chunk)
        self.bytes_received += len(chunk)

    def finish(self) -> bool:
        self.file_handle.flush()
        self.file_handle.close()
        actual_sha256 = self.hasher.hexdigest()
        return actual_sha256 == self.expected_sha256
