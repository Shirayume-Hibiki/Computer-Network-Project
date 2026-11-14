'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Shirayume-Hibiki          ║
║  Creation date:            12/11/26                  ║
║  Edit dates / contributor:                           ║
║  13/11/26 Shirayume-Hibiki                           ║
║  14/11/26 Shirayume-Hibiki                           ║
╚══════════════════════════════════════════════════════╝
'''

from __future__ import annotations

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

def sanitizeFilename(raw_name: str) -> str:
    """Sanitize raw incoming filename against directory traversal, invalid chars, and hidden files."""
    # Strip any forward or backward slash path prefixes
    clean = raw_name.replace("\\", "/").split("/")[-1].strip()
    # Replace dangerous or invalid filesystem characters
    for ch in '<>:"/\\|?*\0':
        clean = clean.replace(ch, "_")
    # Strip leading/trailing dots and whitespace
    clean = clean.strip(". ")
    # Guard against Windows reserved device names
    base_check = os.path.splitext(clean)[0].upper()
    if base_check in (
        "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4",
        "COM5", "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2",
        "LPT3", "LPT4", "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
    ):
        clean = f"file_{clean}"
    if not clean or clean in (".", ".."):
        clean = f"download_{uuid.uuid4().hex[:8]}.bin"
    return clean

def getUniqueDownloadHandle(downloads_dir: str, raw_filename: str) -> tuple[str, any]:
    """
    Atomically creates a unique file in downloads_dir, resolving collisions without TOCTOU race.
    Returns (resolved_file_path, open_file_handle).
    """
    os.makedirs(downloads_dir, exist_ok=True)
    safe_name = sanitizeFilename(raw_filename)
    base_name, ext = os.path.splitext(safe_name)

    counter = 0
    while True:
        if counter == 0:
            candidate_name = f"{base_name}{ext}"
        else:
            candidate_name = f"{base_name}_{counter}{ext}"

        candidate_path = os.path.join(downloads_dir, candidate_name)

        # Enforce boundary: path must reside strictly within downloads_dir
        real_cand = os.path.abspath(candidate_path)
        real_down = os.path.abspath(downloads_dir)
        if os.path.commonpath([real_cand, real_down]) != real_down:
            candidate_name = f"safe_{uuid.uuid4().hex[:8]}{ext}"
            candidate_path = os.path.join(downloads_dir, candidate_name)

        try:
            # Exclusive creation mode ("xb") guarantees atomic creation without TOCTOU race
            handle = open(candidate_path, "xb")
            return candidate_path, handle
        except FileExistsError:
            counter += 1
        except Exception:
            # Fallback for unexpected FS restrictions
            fallback_path = os.path.join(downloads_dir, f"file_{uuid.uuid4().hex[:8]}{ext}")
            return fallback_path, open(fallback_path, "wb")

class FileSender(threading.Thread):
    def __init__(
        self,
        sock: socket.socket,
        filepath: str,
        target_name: str,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        write_lock: threading.Lock | None = None,
        on_progress: Callable[[str, int, int, float], None] | None = None,
        on_complete: Callable[[str, str], None] | None = None,
        on_error: Callable[[str, str], None] | None = None,
        on_cleanup: Callable[[str], None] | None = None,
    ):
        super().__init__(daemon=True, name="FileSenderThread")
        self.sock = sock
        self.filepath = filepath
        self.target_name = target_name
        self.chunk_size = chunk_size
        self.write_lock = write_lock
        self.on_progress = on_progress
        self.on_complete = on_complete
        self.on_error = on_error
        self.on_cleanup = on_cleanup
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
                write_lock=self.write_lock,
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
                        write_lock=self.write_lock,
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
                write_lock=self.write_lock,
            )

            if self.on_complete:
                self.on_complete(filename, self.filepath)

        except Exception as e:
            if self.on_error:
                self.on_error(filename, f"Error sending file: {e}")
        finally:
            if self.on_cleanup:
                self.on_cleanup(self.file_id)

class ActiveIncomingTransfer:
    def __init__(self, file_id: str, filename: str, file_size: int, expected_sha256: str, dest_path: str, file_handle):
        self.file_id = file_id
        self.filename = filename
        self.file_size = file_size
        self.expected_sha256 = expected_sha256
        self.dest_path = dest_path
        self.file_handle = file_handle
        self.hasher = hashlib.sha256()
        self.bytes_received = 0
        self.is_closed = False

    def writeChunk(self, chunk: bytes) -> None:
        if not self.is_closed:
            if self.bytes_received + len(chunk) > self.file_size:
                raise ValueError(
                    f"Received chunk exceeds declared file size ({self.bytes_received + len(chunk)} > {self.file_size})"
                )
            self.file_handle.write(chunk)
            self.hasher.update(chunk)
            self.bytes_received += len(chunk)

    def finish(self) -> bool:
        if not self.is_closed:
            self.file_handle.flush()
            self.file_handle.close()
            self.is_closed = True
        actual_sha256 = self.hasher.hexdigest()
        return actual_sha256 == self.expected_sha256

    def abort(self) -> None:
        if not self.is_closed:
            try:
                self.file_handle.close()
            except Exception:
                pass
            self.is_closed = True
        if os.path.exists(self.dest_path):
            try:
                os.remove(self.dest_path)
            except Exception:
                pass
