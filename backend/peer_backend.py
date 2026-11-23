'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Shirayume_Hibiki          ║
║  Creation date:            21/11/26                  ║
║  Edit dates / contributor:                           ║
╚══════════════════════════════════════════════════════╝
'''

from __future__ import annotations

import os
from pathlib import Path
import socket
import struct
import threading
import time
from typing import BinaryIO, Callable
import uuid
from uuid import UUID

from .data_types import (
    BackendConfig,
    BackendError,
    BackendEvent,
    BackendNotice,
    LogLevel,
    MAX_NAME_BYTES,
    MAX_STATUS_BYTES,
    MessageReceived,
    PeerAddress,
    PeerChanged,
    PeerConnected,
    PeerDisconnected,
    PeerInfo,
    PeerOffline,
    PeerOnline,
    TransferFailed,
    TransferFinished,
    TransferInfo,
    TransferProgress,
)
from .protocol import (
    MAX_FRAME_SIZE,
    TAG_CHAT,
    TAG_DATA,
    TAG_FBEG,
    TAG_FDAT,
    TAG_FEND,
    TAG_FNAM,
    TAG_FTID,
    TAG_GBYE,
    TAG_HELO,
    TAG_LEAV,
    TAG_NAME,
    TAG_PORT,
    TAG_PRES,
    TAG_SIZE,
    TAG_STAT,
    TAG_TEXT,
    TAG_USID,
    pack_chat,
    pack_fbeg,
    pack_fdat,
    pack_fend,
    pack_gbye,
    pack_helo,
    pack_leav,
    pack_pres,
    parse_subblocks_dict,
    read_frame,
    trim_utf8,
    unpack_subblocks,
)


class _PeerConnection:
    """Internal container for an active peer TCP connection."""

    def __init__(
        self,
        sock: socket.socket,
        addr: PeerAddress,
        peer_name: str,
        peer_instance_id: uuid.UUID,
    ):
        self.sock = sock
        self.addr = addr
        self.peer_name = peer_name
        self.peer_instance_id = peer_instance_id
        self.write_lock = threading.Lock()
        self.closed = False


class _IncomingTransfer:
    """Internal tracker for an in-flight incoming file download."""

    def __init__(
        self,
        transfer_id: uuid.UUID,
        addr: PeerAddress,
        name: str,
        filename: str,
        file_size: int,
        dest_path: Path,
        file_handle: BinaryIO,
    ):
        self.transfer_id = transfer_id
        self.addr = addr
        self.name = name
        self.filename = filename
        self.file_size = file_size
        self.dest_path = dest_path
        self.file_handle = file_handle
        self.bytes_received = 0
        self.last_progress_time = time.time()
        self.last_progress_pct = 0.0


def _sanitize_filename(filename: str) -> str:
    """Sanitizes a received filename across POSIX/Windows path separators and reserved chars."""
    base_name = filename.replace("\\", "/").rsplit("/", 1)[-1]
    invalid_chars = set('<>:"/\\|?*')
    cleaned = "".join("_" if (ord(ch) < 32 or ch in invalid_chars) else ch for ch in base_name)
    cleaned = cleaned.strip().rstrip(".")
    if not cleaned or cleaned in {".", ".."}:
        return "download"
    return cleaned


def _get_unique_dest_path(downloads_dir: Path, filename: str) -> Path:
    """Generates a collision-free destination file path using a numeric suffix."""
    safe_name = _sanitize_filename(filename)
    base, ext = os.path.splitext(safe_name)
    target = downloads_dir / safe_name
    counter = 1
    while target.exists():
        target = downloads_dir / f"{base} ({counter}){ext}"
        counter += 1
    return target


class PeerBackend:
    """
    Main P2P communication backend exposing the specification API from BACKEND_SPECS.md.
    Operates binary TLV frames over TCP and UDP discovery.
    """

    def __init__(self, config: BackendConfig, on_event: Callable[[BackendEvent], None]):
        self.config = config
        self.on_event = on_event

        self._instance_id: uuid.UUID | None = None
        self._tcp_port: int | None = None
        self._name = self._trim_name(config.name)
        self._status = self._trim_status(config.status)

        self._started = False
        self._stopped = False
        self._lifecycle_lock = threading.Lock()

        # Peer Discovery State
        self._peers_lock = threading.Lock()
        self._peers: dict[uuid.UUID, PeerInfo] = {}

        # Active TCP Connections
        self._conn_lock = threading.RLock()
        self._connections: dict[PeerAddress, _PeerConnection] = {}
        self._conns_by_instance: dict[uuid.UUID, _PeerConnection] = {}

        # Active File Transfers
        self._transfers_lock = threading.Lock()
        self._incoming_transfers: dict[uuid.UUID, _IncomingTransfer] = {}
        self._outgoing_transfers: dict[uuid.UUID, threading.Thread] = {}

        # Sockets & Background Threads
        self._tcp_server_sock: socket.socket | None = None
        self._udp_listen_sock: socket.socket | None = None
        self._udp_broadcast_sock: socket.socket | None = None

        self._accept_thread: threading.Thread | None = None
        self._udp_listen_thread: threading.Thread | None = None
        self._udp_broadcast_thread: threading.Thread | None = None
        self._cleanup_thread: threading.Thread | None = None

    # Logging helper
    def _log(self, level: LogLevel, msg: str) -> None:
        if self.config.log is not None:
            try:
                self.config.log(level, msg)
            except Exception:
                pass

    def _emit_event(self, event: BackendEvent) -> None:
        """Dispatches an event to the callback without holding any backend locks."""
        try:
            self.on_event(event)
        except Exception as e:
            self._log(LogLevel.ERROR, f"Exception in on_event callback: {e}")

    # String trimming helpers respecting UTF-8 byte limits
    @staticmethod
    def _trim_name(name: str) -> str:
        return trim_utf8(name, MAX_NAME_BYTES)

    @staticmethod
    def _trim_status(status: str) -> str:
        return trim_utf8(status, MAX_STATUS_BYTES)

    # Property
    @property
    def tcp_port(self) -> int | None:
        return self._tcp_port

    def _ensure_running(self) -> None:
        with self._lifecycle_lock:
            if not self._started or self._stopped:
                raise BackendError("Backend is not running.")

    
    # Public Lifecycle Methods

    def start(self) -> None:
        """Binds TCP socket, starts UDP discovery and TCP acceptor."""
        with self._lifecycle_lock:
            if self._started:
                raise BackendError("Backend already started.")
            if self._stopped:
                raise BackendError("Cannot restart stopped backend.")

            self._instance_id = uuid.uuid4()

            try:
                self._tcp_server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self._tcp_server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self._tcp_server_sock.bind(("", self.config.tcp_port))
                self._tcp_server_sock.listen(16)
                self._tcp_port = self._tcp_server_sock.getsockname()[1]
            except Exception as e:
                self._cleanup_all_sockets()
                raise BackendError(f"Failed to bind TCP server on port {self.config.tcp_port}: {e}")

            try:
                self._udp_listen_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self._udp_listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                self._udp_listen_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
                reuseport = getattr(socket, "SO_REUSEPORT", None)
                if reuseport is not None:
                    try:
                        self._udp_listen_sock.setsockopt(socket.SOL_SOCKET, reuseport, 1)
                    except Exception:
                        pass
                self._udp_listen_sock.bind(("", self.config.discovery_port))
            except Exception as e:
                self._cleanup_all_sockets()
                raise BackendError(f"Failed to bind UDP discovery listener on port {self.config.discovery_port}: {e}")

            try:
                self._udp_broadcast_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                self._udp_broadcast_sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            except Exception as e:
                self._cleanup_all_sockets()
                raise BackendError(f"Failed to setup UDP broadcast socket: {e}")

            self._started = True

            self._accept_thread = threading.Thread(target=self._tcp_accept_loop, daemon=True, name="PeerBackend-Acceptor")
            self._accept_thread.start()

            self._udp_listen_thread = threading.Thread(target=self._udp_listen_loop, daemon=True, name="PeerBackend-UdpRx")
            self._udp_listen_thread.start()

            self._udp_broadcast_thread = threading.Thread(target=self._udp_broadcast_loop, daemon=True, name="PeerBackend-UdpTx")
            self._udp_broadcast_thread.start()

            self._cleanup_thread = threading.Thread(target=self._peer_timeout_cleanup_loop, daemon=True, name="PeerBackend-PeerTimeout")
            self._cleanup_thread.start()

            self._log(LogLevel.INFO, f"PeerBackend started (instance_id={self._instance_id}, port={self._tcp_port})")

    def stop(self) -> None:
        """Sends goodbye signal, closes open sockets, aborts downloads, and stops threads."""
        with self._lifecycle_lock:
            if not self._started or self._stopped:
                return
            self._stopped = True
            self._tcp_port = None

        self._log(LogLevel.INFO, "PeerBackend stopping...")

        self._broadcast_goodbye()

        self._abort_all_transfers("Backend stopped")

        with self._conn_lock:
            conns = list(self._connections.values())
            self._connections.clear()
            self._conns_by_instance.clear()

        for conn in conns:
            self._close_connection_internal(conn, "Backend stopped", emit_event=True)

        self._cleanup_all_sockets()

        self._log(LogLevel.INFO, "PeerBackend stopped cleanly.")

    def _cleanup_all_sockets(self) -> None:
        self._tcp_port = None
        for sock_attr in ("_tcp_server_sock", "_udp_listen_sock", "_udp_broadcast_sock"):
            sock = getattr(self, sock_attr, None)
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
                setattr(self, sock_attr, None)


    # Public Presence & Discovery

    def get_peers(self) -> list[PeerInfo]:
        """Returns an unordered list of the current discovered peers."""
        self._ensure_running()
        with self._peers_lock:
            return list(self._peers.values())

    def set_status(self, status: str) -> None:
        """Sets the user's status and immediately broadcasts it."""
        self._ensure_running()
        trimmed = self._trim_status(status)
        self._status = trimmed
        self._broadcast_presence()


    # Public Chat & Connection

    def connect(self, addr: PeerAddress) -> None:
        """Opens TCP connection to address, exchanges HELO, emits PeerConnected."""
        self._ensure_running()

        with self._conn_lock:
            if addr in self._connections:
                return  # Idempotent no-op

        start_time = time.time()
        timeout = self.config.connect_timeout

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)

        try:
            sock.connect((addr.ip, addr.port))
            if self._instance_id is None:
                raise BackendError("Backend instance_id is not initialized.")
            local_instance_id = self._instance_id

            # Send HELO
            helo_bytes = pack_helo(local_instance_id, self._name, self._tcp_port or 0)
            sock.sendall(helo_bytes)

            # Wait for peer's HELO within remaining timeout budget
            elapsed = time.time() - start_time
            remaining = max(0.1, timeout - elapsed)
            sock.settimeout(remaining)

            frame = read_frame(sock)
            if not frame:
                raise ConnectionResetError("Connection closed before receiving HELO")
            tag, body = frame
            if tag != TAG_HELO:
                raise ValueError(f"Expected HELO frame, received {tag}")

            subblocks = parse_subblocks_dict(body)
            if TAG_USID not in subblocks or TAG_NAME not in subblocks or TAG_PORT not in subblocks:
                raise ValueError("HELO frame missing required subblocks (USID, NAME, PORT)")

            peer_usid = uuid.UUID(bytes=subblocks[TAG_USID])
            peer_name = self._trim_name(subblocks[TAG_NAME].decode("utf-8", errors="replace"))
            struct.unpack("!H", subblocks[TAG_PORT])

            # Switch socket to blocking mode without timeouts for receiver thread
            sock.settimeout(None)

            # Check duplicate simultaneous connection tiebreaker
            conn_to_drop: _PeerConnection | None = None
            with self._conn_lock:
                if peer_usid in self._conns_by_instance:
                    existing = self._conns_by_instance[peer_usid]
                    # Lower instance_id keeps outgoing connection
                    if local_instance_id < peer_usid:
                        # Drop existing incoming connection cleanly
                        conn_to_drop = existing
                        self._connections.pop(existing.addr, None)
                        self._conns_by_instance.pop(existing.peer_instance_id, None)
                    else:
                        # Drop this outgoing connection cleanly
                        try:
                            sock.close()
                        except Exception:
                            pass
                        return

                conn = _PeerConnection(sock, addr, peer_name, peer_usid)
                self._connections[addr] = conn
                self._conns_by_instance[peer_usid] = conn

            if conn_to_drop is not None:
                self._close_connection_internal(conn_to_drop, "Duplicate incoming connection replaced by outgoing", emit_event=False)

            # Start receiver thread
            t = threading.Thread(target=self._tcp_rx_loop, args=(conn,), daemon=True, name=f"PeerRx-{peer_name}")
            t.start()

            self._emit_event(PeerConnected(addr, peer_name))

        except Exception as e:
            try:
                sock.close()
            except Exception:
                pass
            raise BackendError(f"Could not connect to {addr.ip}:{addr.port}: {e}")

    def disconnect(self, addr: PeerAddress) -> None:
        """Sends LEAV and closes the address's socket cleanly."""
        self._ensure_running()

        with self._conn_lock:
            conn = self._connections.get(addr)
            if conn is None:
                return  # Already disconnected / no-op

        self._close_connection_internal(conn, "User disconnected", emit_event=True)

    def _close_connection_internal(self, conn: _PeerConnection, reason: str, emit_event: bool = True) -> None:
        """Closes a connection, aborts transfers on it, and cleans state."""
        leav_packet = pack_leav()
        with conn.write_lock:
            if conn.closed:
                return
            conn.closed = True
            # Send LEAV best-effort non-blocking while holding write_lock so frames never interleave
            try:
                conn.sock.settimeout(0.0)
                conn.sock.sendall(leav_packet)
            except Exception:
                pass

        try:
            conn.sock.shutdown(socket.SHUT_RDWR)
        except Exception:
            pass
        try:
            conn.sock.close()
        except Exception:
            pass

        with self._conn_lock:
            self._connections.pop(conn.addr, None)
            self._conns_by_instance.pop(conn.peer_instance_id, None)

        # Abort transfers associated with this connection
        self._abort_transfers_for_addr(conn.addr, reason)

        if emit_event:
            self._emit_event(PeerDisconnected(conn.addr, conn.peer_name, reason))

    def send_message(self, addr: PeerAddress, message: str) -> None:
        """Sends a CHAT message to the peer address."""
        self._ensure_running()

        with self._conn_lock:
            conn = self._connections.get(addr)

        if conn is None:
            raise BackendError(f"Not connected to {addr.ip}:{addr.port}")

        packet = pack_chat(message)
        try:
            with conn.write_lock:
                if conn.closed:
                    raise BackendError(f"Not connected to {addr.ip}:{addr.port}")
                conn.sock.sendall(packet)
        except BackendError:
            raise
        except Exception as e:
            self._close_connection_internal(conn, f"Send message failed: {e}", emit_event=True)
            raise BackendError(f"Failed to send message: {e}")

    def send_file(self, addr: PeerAddress, filepath: str | Path) -> UUID:
        """Sends a file to the address in background chunks."""
        self._ensure_running()

        file_path = Path(filepath)
        if not file_path.is_file():
            raise BackendError(f"Path does not point to a valid file: {filepath}")

        with self._conn_lock:
            conn = self._connections.get(addr)

        if conn is None or conn.closed:
            raise BackendError(f"Not connected to {addr.ip}:{addr.port}")

        transfer_id = uuid.uuid4()
        t = threading.Thread(
            target=self._file_sender_worker,
            args=(conn, transfer_id, file_path),
            daemon=True,
            name=f"FileSender-{transfer_id.hex[:8]}",
        )
        with self._transfers_lock:
            self._outgoing_transfers[transfer_id] = t
        t.start()
        return transfer_id


    # UDP Discovery

    def _broadcast_presence(self) -> None:
        """Sends PRES packet to all configured broadcast addresses."""
        if self._udp_broadcast_sock is None or self._instance_id is None:
            return
        packet = pack_pres(
            self._instance_id,
            self._name,
            self._tcp_port or 0,
            self._status,
        )
        for b_addr in self.config.broadcast_addresses:
            try:
                self._udp_broadcast_sock.sendto(packet, (b_addr, self.config.discovery_port))
            except Exception as e:
                self._log(LogLevel.DEBUG, f"Failed to send UDP presence to {b_addr}: {e}")

    def _broadcast_goodbye(self) -> None:
        """Sends GBYE packet to all configured broadcast addresses."""
        if self._udp_broadcast_sock is None or self._instance_id is None:
            return
        packet = pack_gbye(self._instance_id)
        for b_addr in self.config.broadcast_addresses:
            try:
                self._udp_broadcast_sock.sendto(packet, (b_addr, self.config.discovery_port))
            except Exception:
                pass

    def _udp_broadcast_loop(self) -> None:
        """Periodically broadcasts PRES beacon every broadcast_interval seconds."""
        while not self._stopped:
            self._broadcast_presence()
            # Sleep with short increments to respond swiftly to stop()
            slept = 0.0
            while slept < self.config.broadcast_interval and not self._stopped:
                time.sleep(0.1)
                slept += 0.1

    def _udp_listen_loop(self) -> None:
        """Listens for PRES and GBYE datagrams on UDP discovery port."""
        buf_size = 65536
        while not self._stopped and self._udp_listen_sock:
            try:
                data, sender_addr = self._udp_listen_sock.recvfrom(buf_size)
                if not data or len(data) < 8:
                    continue

                tag, length = struct.unpack_from("!4sI", data, 0)
                if tag in (TAG_PRES, TAG_GBYE):
                    if length >= MAX_FRAME_SIZE or 8 + length > len(data):
                        self._log(LogLevel.WARN, f"Received malformed UDP {tag!r} frame (length={length}, packet_len={len(data)})")
                        continue
                else:
                    # Unknown UDP frame tag: ignore cleanly
                    continue

                body = data[8:8 + length]

                if tag == TAG_PRES:
                    try:
                        subblocks = parse_subblocks_dict(body)
                        if TAG_USID not in subblocks or TAG_NAME not in subblocks or TAG_PORT not in subblocks or TAG_STAT not in subblocks:
                            self._log(LogLevel.WARN, "Received PRES frame missing required subblocks")
                            continue

                        peer_usid = uuid.UUID(bytes=subblocks[TAG_USID])
                        listen_port = struct.unpack("!H", subblocks[TAG_PORT])[0]
                    except (ValueError, struct.error) as e:
                        self._log(LogLevel.WARN, f"Received malformed PRES frame: {e}")
                        continue

                    # Filter out our own presence beacon
                    if peer_usid == self._instance_id:
                        continue

                    peer_name = self._trim_name(subblocks[TAG_NAME].decode("utf-8", errors="replace"))
                    peer_stat = self._trim_status(subblocks[TAG_STAT].decode("utf-8", errors="replace"))

                    sender_ip = sender_addr[0]
                    now = time.time()

                    event_to_emit: BackendEvent | None = None
                    with self._peers_lock:
                        existing = self._peers.get(peer_usid)
                        if existing is None:
                            # Prefer non-loopback IP
                            peer_addr = PeerAddress(sender_ip, listen_port)
                            # Remove older entry with exact same address if peer restarted
                            for old_usid, old_peer in list(self._peers.items()):
                                if old_peer.addr == peer_addr:
                                    del self._peers[old_usid]

                            new_peer = PeerInfo(peer_name, peer_stat, peer_addr, now)
                            self._peers[peer_usid] = new_peer
                            event_to_emit = PeerOnline(new_peer)
                        else:
                            # Update existing peer info
                            addr_ip = existing.addr.ip
                            # Prefer non-loopback over loopback
                            if addr_ip.startswith("127.") and not sender_ip.startswith("127."):
                                addr_ip = sender_ip

                            new_addr = PeerAddress(addr_ip, listen_port)
                            changed = (existing.name != peer_name or existing.status != peer_stat or existing.addr != new_addr)
                            updated_peer = PeerInfo(peer_name, peer_stat, new_addr, now)
                            self._peers[peer_usid] = updated_peer
                            if changed:
                                event_to_emit = PeerChanged(updated_peer)

                    if event_to_emit is not None:
                        self._emit_event(event_to_emit)

                elif tag == TAG_GBYE:
                    try:
                        subblocks = parse_subblocks_dict(body)
                        if TAG_USID not in subblocks:
                            self._log(LogLevel.WARN, "Received GBYE frame missing required USID subblock")
                            continue
                        peer_usid = uuid.UUID(bytes=subblocks[TAG_USID])
                    except (ValueError, struct.error) as e:
                        self._log(LogLevel.WARN, f"Received malformed GBYE frame: {e}")
                        continue

                    with self._peers_lock:
                        peer_info = self._peers.pop(peer_usid, None)
                    if peer_info:
                        self._emit_event(PeerOffline(peer_info, reason="goodbye"))

            except Exception as e:
                if self._stopped:
                    break
                self._log(LogLevel.DEBUG, f"UDP listen error: {e}")

    def _peer_timeout_cleanup_loop(self) -> None:
        """Periodically purges inactive peers exceeding broadcast_timeout."""
        while not self._stopped:
            time.sleep(1.0)
            now = time.time()
            timed_out: list[PeerInfo] = []

            with self._peers_lock:
                for peer_usid, peer in list(self._peers.items()):
                    if now - peer.last_seen > self.config.broadcast_timeout:
                        timed_out.append(peer)
                        del self._peers[peer_usid]

            for peer in timed_out:
                self._emit_event(PeerOffline(peer, reason="timeout"))


    # TCP Acceptor & Session Handling

    def _tcp_accept_loop(self) -> None:
        """Accepts incoming TCP connections and spawns handshake threads."""
        while not self._stopped and self._tcp_server_sock:
            try:
                sock, client_addr = self._tcp_server_sock.accept()
                t = threading.Thread(
                    target=self._handle_incoming_handshake,
                    args=(sock, client_addr),
                    daemon=True,
                    name=f"InHandshake-{client_addr[0]}:{client_addr[1]}",
                )
                t.start()
            except Exception:
                if self._stopped:
                    break

    def _handle_incoming_handshake(self, sock: socket.socket, client_addr: tuple[str, int]) -> None:
        """Processes HELO exchange for incoming TCP connection."""
        try:
            sock.settimeout(self.config.connect_timeout)

            # Receive HELO
            frame = read_frame(sock)
            if not frame:
                sock.close()
                return

            tag, body = frame
            if tag != TAG_HELO:
                sock.close()
                return

            subblocks = parse_subblocks_dict(body)
            if TAG_USID not in subblocks or TAG_NAME not in subblocks or TAG_PORT not in subblocks:
                sock.close()
                return

            peer_usid = uuid.UUID(bytes=subblocks[TAG_USID])
            peer_name = self._trim_name(subblocks[TAG_NAME].decode("utf-8", errors="replace"))
            listen_port = struct.unpack("!H", subblocks[TAG_PORT])[0]
            peer_addr = PeerAddress(client_addr[0], listen_port)

            if self._instance_id is None:
                sock.close()
                return
            local_instance_id = self._instance_id

            # Reply with our HELO
            helo_bytes = pack_helo(local_instance_id, self._name, self._tcp_port or 0)
            sock.sendall(helo_bytes)

            sock.settimeout(None)

            # Check duplicate simultaneous connection tiebreaker
            conn_to_drop: _PeerConnection | None = None
            with self._conn_lock:
                if peer_usid in self._conns_by_instance:
                    existing = self._conns_by_instance[peer_usid]
                    # Lower instance_id keeps outgoing; higher keeps incoming
                    if local_instance_id < peer_usid:
                        # Drop incoming connection
                        try:
                            sock.close()
                        except Exception:
                            pass
                        return
                    else:
                        # Drop existing outgoing connection
                        conn_to_drop = existing
                        self._connections.pop(existing.addr, None)
                        self._conns_by_instance.pop(existing.peer_instance_id, None)

                conn = _PeerConnection(sock, peer_addr, peer_name, peer_usid)
                self._connections[peer_addr] = conn
                self._conns_by_instance[peer_usid] = conn

            if conn_to_drop is not None:
                self._close_connection_internal(conn_to_drop, "Replaced by incoming connection tiebreaker", emit_event=False)

            t = threading.Thread(target=self._tcp_rx_loop, args=(conn,), daemon=True, name=f"PeerRx-{peer_name}")
            t.start()

            self._emit_event(PeerConnected(peer_addr, peer_name))

        except Exception as e:
            self._log(LogLevel.DEBUG, f"Incoming handshake error from {client_addr}: {e}")
            try:
                sock.close()
            except Exception:
                pass

    def _tcp_rx_loop(self, conn: _PeerConnection) -> None:
        """Continuous frame dispatcher for an active peer connection."""
        while not self._stopped and not conn.closed:
            try:
                frame = read_frame(conn.sock)
                if frame is None:
                    # Clean EOF
                    break
                tag, body = frame

                if tag == TAG_CHAT:
                    subblocks = parse_subblocks_dict(body)
                    if TAG_TEXT not in subblocks:
                        self._emit_event(BackendNotice("Corrupted CHAT frame missing TEXT subblock"))
                        break
                    text = subblocks[TAG_TEXT].decode("utf-8", errors="replace")
                    self._emit_event(MessageReceived(conn.addr, conn.peer_name, text, time.time()))

                elif tag == TAG_FBEG:
                    self._handle_fbeg(conn, body)

                elif tag == TAG_FDAT:
                    self._handle_fdat(conn, body)

                elif tag == TAG_FEND:
                    self._handle_fend(conn, body)

                elif tag == TAG_LEAV:
                    # Graceful disconnect
                    self._log(LogLevel.INFO, f"Peer {conn.peer_name} sent LEAV")
                    break

                else:
                    # Unknown type: skip/ignore as per protocol spec
                    self._log(LogLevel.DEBUG, f"Ignoring unknown frame type: {tag}")

            except (ConnectionResetError, BrokenPipeError):
                break
            except (ValueError, struct.error) as ve:
                self._emit_event(BackendNotice(f"Corrupted frame from {conn.peer_name}: {ve}"))
                break
            except Exception as e:
                self._log(LogLevel.ERROR, f"Error in rx loop with {conn.peer_name}: {e}")
                break

        self._close_connection_internal(conn, "Remote peer closed connection", emit_event=True)


    # File Transfer Handling (Receiver)

    def _handle_fbeg(self, conn: _PeerConnection, body: bytes) -> None:
        subblocks = parse_subblocks_dict(body)
        if TAG_FTID not in subblocks or TAG_FNAM not in subblocks or TAG_SIZE not in subblocks:
            raise ValueError("FBEG missing required subblocks")

        transfer_id = uuid.UUID(bytes=subblocks[TAG_FTID])
        raw_filename = subblocks[TAG_FNAM].decode("utf-8", errors="replace")
        safe_filename = _sanitize_filename(raw_filename)
        file_size = struct.unpack("!Q", subblocks[TAG_SIZE])[0]

        with self._transfers_lock:
            if transfer_id in self._incoming_transfers:
                self._log(LogLevel.WARN, f"Ignoring duplicate FBEG for active transfer {transfer_id}")
                return

        try:
            downloads_dir = self.config.downloads_dir
            downloads_dir.mkdir(parents=True, exist_ok=True)
            dest_path = _get_unique_dest_path(downloads_dir, safe_filename)
            file_handle = open(dest_path, "wb")
        except OSError as e:
            fail_info = TransferInfo(
                transfer_id=transfer_id,
                addr=conn.addr,
                name=conn.peer_name,
                filename=safe_filename,
                direction="download",
                bytes_transferred=0,
                bytes_total=file_size,
                saved_path=None,
                error=f"Could not open download destination: {e}",
            )
            self._emit_event(TransferFailed(fail_info))
            return

        rx = _IncomingTransfer(
            transfer_id=transfer_id,
            addr=conn.addr,
            name=conn.peer_name,
            filename=safe_filename,
            file_size=file_size,
            dest_path=dest_path,
            file_handle=file_handle,
        )
        with self._transfers_lock:
            self._incoming_transfers[transfer_id] = rx

        # Initial progress 0%
        info = TransferInfo(
            transfer_id=transfer_id,
            addr=conn.addr,
            name=conn.peer_name,
            filename=safe_filename,
            direction="download",
            bytes_transferred=0,
            bytes_total=file_size,
            saved_path=None,
            error=None,
        )
        self._emit_event(TransferProgress(info))

    def _handle_fdat(self, conn: _PeerConnection, body: bytes) -> None:
        subblocks = parse_subblocks_dict(body)
        if TAG_FTID not in subblocks or TAG_DATA not in subblocks:
            raise ValueError("FDAT missing required subblocks")

        transfer_id = uuid.UUID(bytes=subblocks[TAG_FTID])
        data = subblocks[TAG_DATA]

        with self._transfers_lock:
            rx = self._incoming_transfers.get(transfer_id)

        if rx is None:
            return  # Unknown or aborted transfer

        rx.file_handle.write(data)
        rx.bytes_received += len(data)

        # Throttled mid-transfer progress (>= 5% or >= 0.2s); 100% is emitted once on FEND
        if rx.bytes_received < rx.file_size:
            now = time.time()
            pct = rx.bytes_received / rx.file_size * 100.0
            if (pct - rx.last_progress_pct >= 5.0) or (now - rx.last_progress_time >= 0.2):
                rx.last_progress_pct = pct
                rx.last_progress_time = now
                info = TransferInfo(
                    transfer_id=transfer_id,
                    addr=conn.addr,
                    name=conn.peer_name,
                    filename=rx.filename,
                    direction="download",
                    bytes_transferred=rx.bytes_received,
                    bytes_total=rx.file_size,
                    saved_path=None,
                    error=None,
                )
                self._emit_event(TransferProgress(info))

    def _handle_fend(self, conn: _PeerConnection, body: bytes) -> None:
        subblocks = parse_subblocks_dict(body)
        if TAG_FTID not in subblocks:
            raise ValueError("FEND missing required FTID subblock")

        transfer_id = uuid.UUID(bytes=subblocks[TAG_FTID])
        with self._transfers_lock:
            rx = self._incoming_transfers.pop(transfer_id, None)

        if rx is None:
            return

        try:
            rx.file_handle.flush()
            rx.file_handle.close()
        except Exception:
            pass

        # Verify size
        if rx.bytes_received != rx.file_size:
            if rx.dest_path.exists():
                try:
                    rx.dest_path.unlink()
                except Exception:
                    pass
            err_info = TransferInfo(
                transfer_id=transfer_id,
                addr=conn.addr,
                name=conn.peer_name,
                filename=rx.filename,
                direction="download",
                bytes_transferred=rx.bytes_received,
                bytes_total=rx.file_size,
                saved_path=None,
                error=f"Size mismatch: expected {rx.file_size}, received {rx.bytes_received}",
            )
            self._emit_event(TransferFailed(err_info))
            return

        # 100% Progress then Finished
        progress_done_info = TransferInfo(
            transfer_id=transfer_id,
            addr=conn.addr,
            name=conn.peer_name,
            filename=rx.filename,
            direction="download",
            bytes_transferred=rx.bytes_received,
            bytes_total=rx.file_size,
            saved_path=None,
            error=None,
        )
        done_info = TransferInfo(
            transfer_id=transfer_id,
            addr=conn.addr,
            name=conn.peer_name,
            filename=rx.filename,
            direction="download",
            bytes_transferred=rx.bytes_received,
            bytes_total=rx.file_size,
            saved_path=rx.dest_path,
            error=None,
        )
        self._emit_event(TransferProgress(progress_done_info))
        self._emit_event(TransferFinished(done_info))


    # File Transfer Handling (Sender Worker)

    def _file_sender_worker(self, conn: _PeerConnection, transfer_id: uuid.UUID, filepath: Path) -> None:
        filename = filepath.name
        file_size = 0
        bytes_sent = 0
        last_progress_pct = 0.0

        try:
            file_size = filepath.stat().st_size

            # 1. Send FBEG
            fbeg_bytes = pack_fbeg(transfer_id, filename, file_size)
            with conn.write_lock:
                if conn.closed:
                    raise ConnectionResetError("Connection closed before sending FBEG")
                conn.sock.sendall(fbeg_bytes)

            last_progress_time = time.time()
            info = TransferInfo(
                transfer_id=transfer_id,
                addr=conn.addr,
                name=conn.peer_name,
                filename=filename,
                direction="upload",
                bytes_transferred=0,
                bytes_total=file_size,
                saved_path=None,
                error=None,
            )
            self._emit_event(TransferProgress(info))

            # 2. Stream FDAT chunks
            with open(filepath, "rb") as f:
                while bytes_sent < file_size:
                    chunk = f.read(self.config.file_chunk_size)
                    if not chunk:
                        break

                    fdat_bytes = pack_fdat(transfer_id, chunk)
                    with conn.write_lock:
                        if conn.closed:
                            raise ConnectionResetError("Connection closed mid-transfer")
                        conn.sock.sendall(fdat_bytes)

                    bytes_sent += len(chunk)

                    if bytes_sent < file_size:
                        now = time.time()
                        pct = bytes_sent / file_size * 100.0
                        if (pct - last_progress_pct >= 5.0) or (now - last_progress_time >= 0.2):
                            last_progress_pct = pct
                            last_progress_time = now
                            progress_info = TransferInfo(
                                transfer_id=transfer_id,
                                addr=conn.addr,
                                name=conn.peer_name,
                                filename=filename,
                                direction="upload",
                                bytes_transferred=bytes_sent,
                                bytes_total=file_size,
                                saved_path=None,
                                error=None,
                            )
                            self._emit_event(TransferProgress(progress_info))

            # 3. Send FEND
            fend_bytes = pack_fend(transfer_id)
            with conn.write_lock:
                if conn.closed:
                    raise ConnectionResetError("Connection closed before sending FEND")
                conn.sock.sendall(fend_bytes)

            done_info = TransferInfo(
                transfer_id=transfer_id,
                addr=conn.addr,
                name=conn.peer_name,
                filename=filename,
                direction="upload",
                bytes_transferred=bytes_sent,
                bytes_total=file_size,
                saved_path=None,
                error=None,
            )
            self._emit_event(TransferProgress(done_info))
            self._emit_event(TransferFinished(done_info))

        except Exception as e:
            failed_info = TransferInfo(
                transfer_id=transfer_id,
                addr=conn.addr,
                name=conn.peer_name,
                filename=filename,
                direction="upload",
                bytes_transferred=bytes_sent,
                bytes_total=file_size,
                saved_path=None,
                error=str(e),
            )
            self._emit_event(TransferFailed(failed_info))
        finally:
            with self._transfers_lock:
                self._outgoing_transfers.pop(transfer_id, None)


    # Abort & Cleanup Utilities

    def _abort_transfers_for_addr(self, addr: PeerAddress, reason: str) -> None:
        with self._transfers_lock:
            aborted_rx = [rx for rx in self._incoming_transfers.values() if rx.addr == addr]
            for rx in aborted_rx:
                del self._incoming_transfers[rx.transfer_id]

        for rx in aborted_rx:
            try:
                rx.file_handle.close()
            except Exception:
                pass
            if rx.dest_path.exists():
                try:
                    rx.dest_path.unlink()
                except Exception:
                    pass
            fail_info = TransferInfo(
                transfer_id=rx.transfer_id,
                addr=rx.addr,
                name=rx.name,
                filename=rx.filename,
                direction="download",
                bytes_transferred=rx.bytes_received,
                bytes_total=rx.file_size,
                saved_path=None,
                error=reason,
            )
            self._emit_event(TransferFailed(fail_info))

    def _abort_all_transfers(self, reason: str) -> None:
        with self._transfers_lock:
            all_rx = list(self._incoming_transfers.values())
            self._incoming_transfers.clear()

        for rx in all_rx:
            try:
                rx.file_handle.close()
            except Exception:
                pass
            if rx.dest_path.exists():
                try:
                    rx.dest_path.unlink()
                except Exception:
                    pass
            fail_info = TransferInfo(
                transfer_id=rx.transfer_id,
                addr=rx.addr,
                name=rx.name,
                filename=rx.filename,
                direction="download",
                bytes_transferred=rx.bytes_received,
                bytes_total=rx.file_size,
                saved_path=None,
                error=reason,
            )
            self._emit_event(TransferFailed(fail_info))
