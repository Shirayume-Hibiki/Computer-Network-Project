'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Shirayume-Hibiki          ║
║  Creation date:            12/11/26                  ║
║  Edit dates / contributor:                           ║
╚══════════════════════════════════════════════════════╝
'''

import os
import socket
import threading
from typing import Callable

from file_transfer.file_manager import (
    ActiveIncomingTransfer,
    FileSender,
    getUniqueDownloadPath,
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
        self.name = name
        self.tcp_port = tcp_port
        self.discovery_port = discovery_port
        self.downloads_dir = downloads_dir
        self.broadcast_addr = broadcast_addr
        self.status = status

        self.on_message = on_message
        self.on_file_progress = on_file_progress
        self.on_file_complete = on_file_complete
        self.on_file_error = on_file_error
        self.on_notice = on_notice

        self.peer_table = PeerTable(timeout=10.0)
        self.broadcaster = UdpBroadcaster(
            name=self.name,
            tcp_port=self.tcp_port,
            discovery_port=self.discovery_port,
            broadcast_addr=self.broadcast_addr,
            status=self.status,
        )
        self.listener = UdpListener(
            peer_table=self.peer_table,
            my_name=self.name,
            my_tcp_port=self.tcp_port,
            discovery_port=self.discovery_port,
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

    def _handlePeerJoin(self, peer: Peer) -> None:
        self._emitNotice(f"[Discovery] Peer '{peer.name}' is now {peer.status} ({peer.ip}:{peer.port})")

    def _handlePeerLeave(self, peer: Peer) -> None:
        self._emitNotice(f"[Discovery] Peer '{peer.name}' left the network.")

    def _handlePeerStatusChange(self, peer: Peer, new_status: str) -> None:
        self._emitNotice(f"[Discovery] Peer '{peer.name}' is now {new_status}.")

    def _handlePeerTimeout(self, peer: Peer) -> None:
        self._emitNotice(f"[Discovery] Peer '{peer.name}' timed out (inactive > 10s).")

    def start(self) -> None:
        self.running = True

        # 1. Start TCP Server
        self.tcp_server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.tcp_server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.tcp_server_sock.bind(("", self.tcp_port))
        self.tcp_server_sock.listen(5)
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
        self.running = False

        # Close active chat session
        self.leaveChat()

        # Stop UDP discovery
        self.broadcaster.stop()
        self.listener.stop()

        # Close TCP Server socket
        if self.tcp_server_sock:
            try:
                self.tcp_server_sock.close()
            except Exception:
                pass
            self.tcp_server_sock = None

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
                sock.connect((target_peer.ip, target_peer.port))
                self.active_sock = sock
                self.active_peer_name = target_peer.name
                self.active_peer_addr = (target_peer.ip, target_peer.port)

                # Send initial handshake frame with our name
                sendFrame(sock, TYPE_CHAT, {"sender": self.name}, f"*** {self.name} connected to chat ***".encode("utf-8"))

                self._session_rx_thread = threading.Thread(
                    target=self._connectionRxLoop, args=(sock, target_peer.name), daemon=True, name=f"TCP-Rx-{target_peer.name}"
                )
                self._session_rx_thread.start()
                self._emitNotice(f"Connected to {target_peer.name} ({target_peer.ip}:{target_peer.port}). Start typing messages!")
                return True
            except Exception as e:
                self._emitNotice(f"Failed to connect to {target_peer.name} ({target_peer.ip}:{target_peer.port}): {e}")
                return False

    def leaveChat(self) -> None:
        with self._session_lock:
            if self.active_sock is not None:
                try:
                    sendFrame(self.active_sock, TYPE_LEAVE, {"sender": self.name, "reason": "User left"})
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
                    self._emitNotice(f"Disconnected from chat with {name}.")

    def sendMessage(self, text: str) -> bool:
        with self._session_lock:
            if not self.active_sock:
                self._emitNotice("Not in a chat session. Use /chat <username|index> to connect to a peer.")
                return False
            try:
                sendFrame(self.active_sock, TYPE_CHAT, {"sender": self.name}, text.encode("utf-8"))
                return True
            except Exception as e:
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

            sender = FileSender(
                sock=sock,
                filepath=filepath,
                target_name=target_name,
                on_progress=lambda fn, done, total, pct: self.on_file_progress(fn, done, total, pct, True) if self.on_file_progress else None,
                on_complete=lambda fn, path: self.on_file_complete(fn, path, True) if self.on_file_complete else None,
                on_error=lambda fn, err: self.on_file_error(fn, err) if self.on_file_error else None,
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
                            sendFrame(conn, TYPE_LEAVE, {"sender": self.name, "reason": "Busy in another chat"})
                            conn.close()
                        except Exception:
                            pass
                        continue

                    self.active_sock = conn
                    # Identify peer by address lookup in PeerTable or fallback to IP:port
                    found_peer = self.peer_table.getPeerByKey(addr[0], addr[1])
                    if not found_peer:
                        # Scan by IP
                        for p in self.peer_table.getActivePeers():
                            if p.ip == addr[0]:
                                found_peer = p
                                break

                    peer_name = found_peer.name if found_peer else f"{addr[0]}:{addr[1]}"
                    self.active_peer_name = peer_name
                    self.active_peer_addr = addr

                    self._emitNotice(f"Incoming connection accepted from {peer_name} ({addr[0]}:{addr[1]}).")

                    self._session_rx_thread = threading.Thread(
                        target=self._connectionRxLoop, args=(conn, peer_name), daemon=True, name=f"TCP-Rx-{peer_name}"
                    )
                    self._session_rx_thread.start()

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
                    if self.on_message:
                        self.on_message(sender, text)

                elif msg_type == TYPE_FILE_PROPOSE:
                    file_id = meta["file_id"]
                    filename = meta["filename"]
                    file_size = meta["file_size"]
                    expected_sha256 = meta["sha256"]
                    dest_path = getUniqueDownloadPath(self.downloads_dir, filename)

                    receiver = ActiveIncomingTransfer(
                        file_id=file_id,
                        filename=filename,
                        file_size=file_size,
                        expected_sha256=expected_sha256,
                        dest_path=dest_path,
                    )
                    self.active_receivers[file_id] = receiver
                    self._emitNotice(f"Receiving file '{filename}' ({file_size} bytes) from {sender} into {dest_path}...")
                    # Automatically accept transfer
                    sendFrame(sock, TYPE_FILE_ACCEPT, {"file_id": file_id, "offset": 0})

                elif msg_type == TYPE_FILE_ACCEPT:
                    file_id = meta["file_id"]
                    if file_id in self.active_senders:
                        self.active_senders[file_id].notifyAccepted()

                elif msg_type == TYPE_FILE_REJECT:
                    file_id = meta["file_id"]
                    reason = meta.get("reason", "")
                    if file_id in self.active_senders:
                        self.active_senders[file_id].notifyRejected(reason)

                elif msg_type == TYPE_FILE_CHUNK:
                    file_id = meta["file_id"]
                    if file_id in self.active_receivers:
                        rx = self.active_receivers[file_id]
                        rx.writeChunk(body)
                        pct = (rx.bytes_received / rx.file_size) * 100.0 if rx.file_size > 0 else 100.0
                        if self.on_file_progress:
                            self.on_file_progress(rx.filename, rx.bytes_received, rx.file_size, pct, False)

                elif msg_type == TYPE_FILE_COMPLETE:
                    file_id = meta["file_id"]
                    if file_id in self.active_receivers:
                        rx = self.active_receivers.pop(file_id)
                        is_valid = rx.finish()
                        if is_valid:
                            if self.on_file_complete:
                                self.on_file_complete(rx.filename, rx.dest_path, False)
                        else:
                            if self.on_file_error:
                                self.on_file_error(rx.filename, "SHA256 checksum verification failed!")

                elif msg_type == TYPE_LEAVE:
                    reason = meta.get("reason", "Disconnected")
                    self._emitNotice(f"{sender} left the chat ({reason}).")
                    break

        except Exception as e:
            self._emitNotice(f"Chat connection error with {peer_name}: {e}")
        finally:
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
