'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Shirayume-Hibiki          ║
║  Creation date:            12/11/26                  ║
║  Edit dates / contributor:                           ║
║  13/11/26 Shirayume-Hibiki                           ║
║  14/11/26 Shirayume-Hibiki                           ║
╚══════════════════════════════════════════════════════╝
'''

import os
import socket
import threading
import uuid
from typing import Callable

from cn_logging import CNLogger as log
from common_functions import loadLanChatConfig
from file_transfer.file_manager import (
    ActiveIncomingTransfer,
    FileSender,
    getUniqueDownloadHandle,
)
from peer.discovery import UdpBroadcaster, UdpListener
from peer.peer_table import Peer, PeerTable
from protocol.tcp_protocol import (
    TYPE_CHAT,
    TYPE_FILE_ACCEPT,
    TYPE_FILE_CHUNK,
    TYPE_FILE_COMPLETE,
    TYPE_FILE_PROPOSE,
    TYPE_FILE_REJECT,
    TYPE_HANDSHAKE,
    TYPE_HANDSHAKE_ACK,
    TYPE_HANDSHAKE_REJECT,
    TYPE_LEAVE,
    recvFrame,
    sendFrame,
)

class PeerNode:
    def __init__(
        self,
        name: str,
        tcp_port: int,
        discovery_port: int = 9999,
        downloads_dir: str = "downloads",
        broadcast_addr: str = "255.255.255.255",
        status: str = "online",
        on_message: Callable[[str, str], None] | None = None,
        on_file_progress: Callable[[str, int, int, float, bool], None] | None = None,
        on_file_complete: Callable[[str, str, bool], None] | None = None,
        on_file_error: Callable[[str, str], None] | None = None,
        on_notice: Callable[[str], None] | None = None,
    ):
        config = loadLanChatConfig()
        self.name = name
        self.tcp_port = tcp_port
        self.discovery_port = discovery_port if discovery_port != 9999 else int(config.get("discovery_port", 9999))
        self.beacon_interval = float(config.get("beacon_interval", 3.0))
        self.peer_timeout = float(config.get("peer_timeout", 10.0))
        self.downloads_dir = downloads_dir if downloads_dir != "downloads" else str(config.get("downloads_dir", "downloads"))
        self.broadcast_addr = broadcast_addr if broadcast_addr != "255.255.255.255" else str(config.get("broadcast_address", "255.255.255.255"))
        self.status = status if status != "online" else str(config.get("default_status", "online"))
        self.file_chunk_size = int(config.get("file_chunk_size", 65536))
        self.max_file_size = int(config.get("max_file_size", 104857600))
        self.max_concurrent_downloads = int(config.get("max_concurrent_downloads", 3))
        self.session_timeout = float(config.get("session_timeout", 60.0))
        self.node_id = str(uuid.uuid4())

        self.log = log(instancepfx=f"peer_{self.name.lower()}")
        self.log.initLogger()
        self.log.logSystem(f"P2P Node initiated for '{self.name}'. TCP Port: {self.tcp_port}, Discovery: {self.discovery_port}", action="INIT")

        self.on_message = on_message
        self.on_file_progress = on_file_progress
        self.on_file_complete = on_file_complete
        self.on_file_error = on_file_error
        self.on_notice = on_notice

        self.peer_table = PeerTable(timeout=self.peer_timeout)
        self.broadcaster = UdpBroadcaster(
            name=self.name,
            tcp_port=self.tcp_port,
            discovery_port=self.discovery_port,
            interval=self.beacon_interval,
            broadcast_addr=self.broadcast_addr,
            status=self.status,
            node_id=self.node_id,
        )
        self.listener = UdpListener(
            peer_table=self.peer_table,
            my_name=self.name,
            my_tcp_port=self.tcp_port,
            discovery_port=self.discovery_port,
            my_node_id=self.node_id,
            on_peer_join=self._handlePeerJoin,
            on_peer_leave=self._handlePeerLeave,
            on_peer_status_change=self._handlePeerStatusChange,
            on_peer_timeout=self._handlePeerTimeout,
        )

        self.tcp_server_sock: socket.socket | None = None
        self._server_thread: threading.Thread | None = None
        self.running = False

        # Active chat session
        self._session_lock = threading.Lock()
        self.sock_write_lock = threading.Lock()
        self.active_sock: socket.socket | None = None
        self.active_peer_name: str | None = None
        self.active_peer_addr: tuple[str, int] | None = None
        self._session_rx_thread: threading.Thread | None = None

        # Active file transfers
        self.active_senders: dict[str, FileSender] = {}
        self.active_receivers: dict[str, ActiveIncomingTransfer] = {}

    def _emitNotice(self, msg: str) -> None:
        if self.on_notice:
            self.on_notice(msg)

    def _closeActiveSession(self) -> None:
        if self.active_sock is not None:
            try:
                self.active_sock.close()
            except Exception:
                pass
            self.active_sock = None
            self.active_peer_name = None
            self.active_peer_addr = None

    def _handlePeerJoin(self, peer: Peer) -> None:
        self.log.logSystem(f"Peer '{peer.name}' joined ({peer.ip}:{peer.port}) [{peer.status}]", action="DISCOVERY")
        self._emitNotice(f"[Discovery] Peer '{peer.name}' is now {peer.status} ({peer.ip}:{peer.port})")

    def _handlePeerLeave(self, peer: Peer) -> None:
        self.log.logSystem(f"Peer '{peer.name}' left the network", action="DISCOVERY")
        self._emitNotice(f"[Discovery] Peer '{peer.name}' left the network.")
        with self._session_lock:
            if self.active_peer_name and self.active_peer_name.lower() == peer.name.lower():
                self._closeActiveSession()
                self._emitNotice(f"[Chat] Active chat peer '{peer.name}' departed. Chat session closed.")

    def _handlePeerStatusChange(self, peer: Peer, new_status: str) -> None:
        self.log.logSystem(f"Peer '{peer.name}' is now {new_status}", action="STATUS")
        self._emitNotice(f"[Discovery] Peer '{peer.name}' is now {new_status}.")

    def _handlePeerTimeout(self, peer: Peer) -> None:
        self.log.logWarn(f"Peer '{peer.name}' timed out (inactive > {self.peer_timeout}s)", action="TIMEOUT")
        self._emitNotice(f"[Discovery] Peer '{peer.name}' timed out (inactive > 10s).")
        with self._session_lock:
            if self.active_peer_name and self.active_peer_name.lower() == peer.name.lower():
                self._closeActiveSession()
                self._emitNotice(f"[Chat] Active chat peer '{peer.name}' timed out. Chat session closed.")

    def start(self) -> None:
        self.running = True

        # 1. Start TCP Server
        self.tcp_server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp_server_sock.bind(("", self.tcp_port))
        self.tcp_server_sock.listen(5)
        self.tcp_server_sock.settimeout(0.5)
        # If dynamic port (0) was requested, update actual port
        self.tcp_port = self.tcp_server_sock.getsockname()[1]
        self.broadcaster.tcp_port = self.tcp_port
        self.listener.my_tcp_port = self.tcp_port

        self._server_thread = threading.Thread(target=self._tcpAcceptLoop, daemon=True, name="TCP-Acceptor")
        self._server_thread.start()

        # 2. Start UDP Discovery
        self.listener.start()
        self.broadcaster.start()

    def stop(self) -> None:
        if not self.running:
            self.log.close()
            return
        self.running = False
        self.log.logSystem(f"P2P Node '{self.name}' shutting down.", action="SHUTDOWN")

        # Close active chat session
        self.leaveChat()

        # Stop UDP discovery
        self.broadcaster.stop()
        self.listener.stop()

        # Close TCP Server socket
        if self.tcp_server_sock:
            try:
                self.tcp_server_sock.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                self.tcp_server_sock.close()
            except Exception:
                pass
            self.tcp_server_sock = None
        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=0.5)
        self.log.close()

    def setStatus(self, status: str) -> None:
        self.status = status
        self.broadcaster.setStatus(status)

    def connectToPeer(self, target: str) -> bool:
        """Connect to peer by username or index number."""
        target_peer: Peer | None = None
        if target.isdigit():
            target_peer = self.peer_table.getPeerByIndex(int(target))
        else:
            target_peer = self.peer_table.getPeerByName(target)

        if not target_peer:
            self._emitNotice(f"Peer '{target}' not found in active peer list. Use /list to see peers.")
            return False

        with self._session_lock:
            if self.active_sock is not None:
                self._emitNotice(f"Already in an active chat with '{self.active_peer_name}'. Use /leave first.")
                return False

        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
            sock.settimeout(5.0)
            sock.connect((target_peer.ip, target_peer.port))

            # Send formal handshake
            sendFrame(sock, TYPE_HANDSHAKE, {"sender": self.name, "listen_port": self.tcp_port})

            # Wait for handshake response (acknowledgement or rejection)
            resp = recvFrame(sock)
            if not resp:
                sock.close()
                self._emitNotice(f"Connection closed by {target_peer.name} without handshake response.")
                return False

            resp_meta, _ = resp
            resp_type = resp_meta.get("type", "")
            if resp_type != TYPE_HANDSHAKE_ACK:
                reason = resp_meta.get("reason", "Connection rejected by remote peer.")
                sock.close()
                self._emitNotice(f"Could not chat with {target_peer.name}: {reason}")
                return False

            # Confirmed handshake
            verified_name = resp_meta.get("sender", target_peer.name)
            sock.settimeout(self.session_timeout)

            with self._session_lock:
                self.active_sock = sock
                self.active_peer_name = verified_name
                self.active_peer_addr = (target_peer.ip, target_peer.port)

            self._session_rx_thread = threading.Thread(
                target=self._connectionRxLoop, args=(sock, verified_name), daemon=True, name=f"TCP-Rx-{verified_name}"
            )
            self._session_rx_thread.start()
            self.log.logClient(f"Connected to {verified_name} ({target_peer.ip}:{target_peer.port})", action="CONNECT")
            self._emitNotice(f"Connected to {verified_name} ({target_peer.ip}:{target_peer.port}). Start typing messages!")
            return True

        except socket.timeout:
            self._emitNotice(f"Connection attempt to {target_peer.name} timed out during handshake.")
            return False
        except Exception as e:
            self._emitNotice(f"Failed to connect to {target_peer.name} ({target_peer.ip}:{target_peer.port}): {e}")
            return False

    def leaveChat(self) -> None:
        with self._session_lock:
            if self.active_sock is not None:
                try:
                    sendFrame(self.active_sock, TYPE_LEAVE, {"sender": self.name, "reason": "User left"}, write_lock=self.sock_write_lock)
                except Exception:
                    pass
                try:
                    self.active_sock.close()
                except Exception:
                    pass
                name = self.active_peer_name
                self.active_sock = None
                self.active_peer_name = None
                self.active_peer_addr = None
                if name:
                    self.log.logClient(f"Disconnected from chat with {name}", action="DISCONNECT")
                    self._emitNotice(f"Disconnected from chat with {name}.")

    def sendMessage(self, text: str) -> bool:
        with self._session_lock:
            if not self.active_sock:
                self._emitNotice("Not in a chat session. Use /chat <username|index> to connect to a peer.")
                return False
            try:
                sendFrame(self.active_sock, TYPE_CHAT, {"sender": self.name}, text.encode("utf-8"), write_lock=self.sock_write_lock)
                self.log.logClient(f"Sent message to {self.active_peer_name}: {text}", action="CHAT_SEND")
                return True
            except Exception as e:
                self.log.logError(f"Failed to send message: {e}", action="CHAT_SEND")
                self._emitNotice(f"Failed to send message: {e}")
                return False

    def sendFile(self, filepath: str) -> bool:
        with self._session_lock:
            if not self.active_sock:
                self._emitNotice("Not in a chat session. Connect to a peer before sending a file.")
                return False

            if not os.path.isfile(filepath):
                self._emitNotice(f"File not found: {filepath}")
                return False

            sock = self.active_sock
            target_name = self.active_peer_name or "Peer"

            self.log.logClient(f"Proposing file '{os.path.basename(filepath)}' to {target_name}", action="FILE_SEND")
            sender = FileSender(
                sock=sock,
                filepath=filepath,
                target_name=target_name,
                write_lock=self.sock_write_lock,
                on_progress=lambda fn, done, total, pct: self.on_file_progress(fn, done, total, pct, True) if self.on_file_progress else None,
                on_complete=lambda fn, path: self.on_file_complete(fn, path, True) if self.on_file_complete else None,
                on_error=lambda fn, err: self.on_file_error(fn, err) if self.on_file_error else None,
                on_cleanup=lambda fid: self.active_senders.pop(fid, None),
            )
            self.active_senders[sender.file_id] = sender
            sender.start()
            self._emitNotice(f"Proposing file '{os.path.basename(filepath)}' to {target_name}...")
            return True

    def _tcpAcceptLoop(self) -> None:
        while self.running and self.tcp_server_sock:
            try:
                conn, addr = self.tcp_server_sock.accept()
                with self._session_lock:
                    if self.active_sock is not None:
                        # Reject concurrent chat connections if one is active
                        try:
                            sendFrame(conn, TYPE_HANDSHAKE_REJECT, {"sender": self.name, "reason": "Busy in another chat"})
                            conn.close()
                        except Exception:
                            pass
                        continue

                # Read incoming handshake frame
                try:
                    conn.settimeout(5.0)
                    req = recvFrame(conn)
                    if not req or req[0].get("type") != TYPE_HANDSHAKE:
                        conn.close()
                        continue

                    req_meta, _ = req
                    sender_name = req_meta.get("sender", f"{addr[0]}:{addr[1]}")

                    with self._session_lock:
                        if self.active_sock is not None:
                            sendFrame(conn, TYPE_HANDSHAKE_REJECT, {"sender": self.name, "reason": "Busy in another chat"})
                            conn.close()
                            continue

                        # Acknowledge handshake
                        sendFrame(conn, TYPE_HANDSHAKE_ACK, {"sender": self.name, "listen_port": self.tcp_port})
                        conn.settimeout(self.session_timeout)
                        conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)

                        self.active_sock = conn
                        self.active_peer_name = sender_name
                        self.active_peer_addr = addr

                    self._emitNotice(f"Incoming connection accepted from {sender_name} ({addr[0]}:{addr[1]}).")

                    self._session_rx_thread = threading.Thread(
                        target=self._connectionRxLoop, args=(conn, sender_name), daemon=True, name=f"TCP-Rx-{sender_name}"
                    )
                    self._session_rx_thread.start()

                except (socket.timeout, Exception):
                    try:
                        conn.close()
                    except Exception:
                        pass

            except (socket.timeout, TimeoutError):
                continue
            except Exception:
                if not self.running:
                    break

    def _connectionRxLoop(self, sock: socket.socket, default_peer_name: str) -> None:
        peer_name = default_peer_name
        try:
            while self.running:
                result = recvFrame(sock)
                if not result:
                    break
                meta, body = result
                msg_type = meta.get("type", "")
                sender = meta.get("sender", peer_name)

                if msg_type == TYPE_CHAT:
                    text = body.decode("utf-8", errors="replace")
                    self.log.logServer(f"Received chat from {sender}: {text}", action="CHAT_RECV")
                    if self.on_message:
                        self.on_message(sender, text)

                elif msg_type == TYPE_FILE_PROPOSE:
                    file_id = meta["file_id"]
                    filename = meta["filename"]
                    file_size = meta["file_size"]
                    expected_sha256 = meta["sha256"]

                    # Check file size limit
                    if file_size > self.max_file_size or file_size < 0:
                        reason = f"File size exceeds maximum allowed limit ({file_size} > {self.max_file_size} bytes)"
                        self.log.logWarn(f"Rejected file '{filename}' from {sender}: {reason}", action="FILE_REJECT")
                        sendFrame(sock, TYPE_FILE_REJECT, {"file_id": file_id, "reason": reason}, write_lock=self.sock_write_lock)
                        self._emitNotice(f"Rejected file '{filename}' from {sender}: {reason}")
                        continue

                    # Check max concurrent incoming transfers limit
                    if len(self.active_receivers) >= self.max_concurrent_downloads:
                        reason = f"Max concurrent downloads limit reached ({self.max_concurrent_downloads})"
                        self.log.logWarn(f"Rejected file '{filename}' from {sender}: {reason}", action="FILE_REJECT")
                        sendFrame(sock, TYPE_FILE_REJECT, {"file_id": file_id, "reason": reason}, write_lock=self.sock_write_lock)
                        self._emitNotice(f"Rejected file '{filename}' from {sender}: {reason}")
                        continue

                    dest_path, file_handle = getUniqueDownloadHandle(self.downloads_dir, filename)

                    self.log.logServer(f"Receiving file '{filename}' ({file_size} bytes) from {sender} -> {dest_path}", action="FILE_RECV")
                    receiver = ActiveIncomingTransfer(
                        file_id=file_id,
                        filename=filename,
                        file_size=file_size,
                        expected_sha256=expected_sha256,
                        dest_path=dest_path,
                        file_handle=file_handle,
                    )
                    self.active_receivers[file_id] = receiver
                    self._emitNotice(f"Receiving file '{filename}' ({file_size} bytes) from {sender} into {dest_path}...")
                    # Automatically accept transfer using socket write lock
                    sendFrame(sock, TYPE_FILE_ACCEPT, {"file_id": file_id, "offset": 0}, write_lock=self.sock_write_lock)

                elif msg_type == TYPE_FILE_ACCEPT:
                    file_id = meta["file_id"]
                    self.log.logClient(f"File transfer accepted by remote peer: {file_id}", action="FILE_ACCEPT")
                    if file_id in self.active_senders:
                        self.active_senders[file_id].notifyAccepted()

                elif msg_type == TYPE_FILE_REJECT:
                    file_id = meta["file_id"]
                    reason = meta.get("reason", "")
                    self.log.logWarn(f"File transfer rejected by remote peer: {reason}", action="FILE_REJECT")
                    if file_id in self.active_senders:
                        self.active_senders[file_id].notifyRejected(reason)

                elif msg_type == TYPE_FILE_CHUNK:
                    file_id = meta["file_id"]
                    if file_id in self.active_receivers:
                        rx = self.active_receivers[file_id]
                        try:
                            rx.writeChunk(body)
                            pct = (rx.bytes_received / rx.file_size) * 100.0 if rx.file_size > 0 else 100.0
                            if self.on_file_progress:
                                self.on_file_progress(rx.filename, rx.bytes_received, rx.file_size, pct, False)
                        except ValueError as ve:
                            # Transfer exceeded declared size - abort to protect disk space
                            rx.abort()
                            self.active_receivers.pop(file_id, None)
                            self.log.logError(f"File transfer '{rx.filename}' aborted: {ve}", action="FILE_OVERFLOW")
                            if self.on_file_error:
                                self.on_file_error(rx.filename, f"Transfer aborted: {ve}")
                            sendFrame(sock, TYPE_FILE_REJECT, {"file_id": file_id, "reason": str(ve)}, write_lock=self.sock_write_lock)

                elif msg_type == TYPE_FILE_COMPLETE:
                    file_id = meta["file_id"]
                    if file_id in self.active_receivers:
                        rx = self.active_receivers.pop(file_id)
                        is_valid = rx.finish()
                        if is_valid:
                            self.log.logServer(f"File '{rx.filename}' downloaded and verified (SHA-256 match)", action="FILE_COMPLETE")
                            if self.on_file_complete:
                                self.on_file_complete(rx.filename, rx.dest_path, False)
                        else:
                            rx.abort()  # Delete corrupted file on SHA-256 verification failure
                            self.log.logError(f"File '{rx.filename}' failed SHA-256 verification, discarded", action="FILE_ERROR")
                            if self.on_file_error:
                                self.on_file_error(rx.filename, "SHA256 checksum verification failed! Corrupted file discarded.")

                elif msg_type == TYPE_LEAVE:
                    reason = meta.get("reason", "Disconnected")
                    self._emitNotice(f"{sender} left the chat ({reason}).")
                    break

        except (socket.timeout, TimeoutError):
            self.log.logWarn(f"Connection with {peer_name} timed out", action="TIMEOUT")
            self._emitNotice(f"Chat connection with {peer_name} timed out.")
        except Exception as e:
            self._emitNotice(f"Chat connection error with {peer_name}: {e}")
        finally:
            # Clean up and abort any in-flight incoming transfers to avoid file handle leaks
            for f_id, rx in list(self.active_receivers.items()):
                rx.abort()
            self.active_receivers.clear()

            # Abort any in-flight outgoing transfers
            for f_id, tx in list(self.active_senders.items()):
                tx.notifyRejected("Connection closed")
            self.active_senders.clear()

            with self._session_lock:
                if self.active_sock is sock:
                    self.active_sock = None
                    self.active_peer_name = None
                    self.active_peer_addr = None
                    self._emitNotice(f"Chat session with {peer_name} closed.")
            try:
                sock.close()
            except Exception:
                pass
