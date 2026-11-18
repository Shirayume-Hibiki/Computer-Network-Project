'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  diamboy                   ║
║  Creation date:            17/11/26                  ║
║  Edit dates / contributor:                           ║
╚══════════════════════════════════════════════════════╝
'''

from __future__ import annotations
from collections.abc import Callable
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Literal

class LogLevel(IntEnum):
    DEBUG = 0
    INFO = 1
    WARN = 2
    ERROR = 3

# Cap the byte size of all names and statuses to these.
# Be careful when handling UTF-8 code points.
MAX_NAME_BYTES: int = 64
MAX_STATUS_BYTES: int = 128

@dataclass(frozen=True)
class PeerAddress:
    ip: str
    port: int

@dataclass(frozen=True)
class BackendConfig:
    name: str
    status: str = "online"   # Mochi-tan wants to put "🍡🍡mgmg" as her status~
    tcp_port: int = 0        # Auto-assigns an ephemeral port.
    discovery_port: int = 9999
    broadcast_addresses: tuple[str, ...] = ("255.255.255.255",
                                            "127.255.255.255")
    broadcast_interval: float = 3.0
    broadcast_timeout: float = 10.0
    connect_timeout: float = 5.0
    downloads_dir: Path = Path("downloads")
    # Files are split into chunks to allow chatting while sending.
    file_chunk_size: int = 65536
    log: Callable[[LogLevel, str], None] | None = None

@dataclass(frozen=True)
class PeerInfo:
    name: str           # Peer's name.
    status: str         # Peer's last status.
    addr: PeerAddress   # Peer's listening address.
    last_seen: float    # Time of last status.

@dataclass(frozen=True)
class TransferInfo:
    transfer_id: str    # Sent along with every file transfer chunk for IDing.
    addr: PeerAddress   # Peer's listening address.
    name: str           # Peer's name.
    filename: str       # Filename of the file being sent or received.
    # "upload" if the user sending, "download" if the user is receiving.
    direction: Literal["upload", "download"]
    bytes_transferred: int
    bytes_total: int    # Expected total size.
    # Final path on disk once finished. Can only populated if downloading.
    # None while transfer is active or if the transfer failed.
    saved_path: Path | None
    error: str | None   # Human-readable error.

class BackendError(Exception):
    pass

# Event dataclasses.
# Sent via the on_event function provided in the PeerBackend constructor.

@dataclass(frozen=True)
class PeerOnline:
    peer: PeerInfo

# Fired when peer's address or status changes.
@dataclass(frozen=True)
class PeerChanged:
    peer: PeerInfo

@dataclass(frozen=True)
class PeerOffline:
    peer: PeerInfo
    reason: Literal["goodbye", "timeout"]

# We may have purged the peer from the discovery list due to UDP packet loss.
# By not using a PeerInfo, and including a name,
# we can still connect and name the peer properly.
@dataclass(frozen=True)
class PeerConnected:
    addr: PeerAddress
    name: str

@dataclass(frozen=True)
class PeerDisconnected:
    addr: PeerAddress
    name: str
    reason: str

@dataclass(frozen=True)
class MessageReceived:
    addr: PeerAddress
    name: str    # The sender of the message.
    text: str
    timestamp: float

@dataclass(frozen=True)
class TransferProgress:
    transfer: TransferInfo

@dataclass(frozen=True)
class TransferFinished:
    transfer: TransferInfo    # saved_path is populated on downloads.

@dataclass(frozen=True)
class TransferFailed:
    transfer: TransferInfo    # error is populated.

# To avoid concurrency issues, send backend errors in threads using this.
@dataclass(frozen=True)
class BackendNotice:
    message: str

BackendEvent = (PeerOnline | PeerChanged | PeerOffline | PeerConnected
               | PeerDisconnected | MessageReceived | TransferProgress
               | TransferFinished | TransferFailed | BackendNotice)


