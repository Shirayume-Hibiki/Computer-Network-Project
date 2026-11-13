'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Shirayume-Hibiki          ║
║  Creation date:            12/11/26                  ║
║  Edit dates / contributor:                           ║
║  13/11/26 Shirayume-Hibiki                           ║
╚══════════════════════════════════════════════════════╝
'''

import socket
import threading
import time
import uuid
from typing import Callable

from protocol.udp_protocol import (
    MSG_BEACON,
    MSG_GOODBYE,
    MSG_STATUS_UPDATE,
    createBeacon,
    createGoodbye,
    createStatusUpdate,
    parseDatagram,
)
from peer.peer_table import Peer, PeerTable

class UdpBroadcaster:
    def __init__(
        self,
        name: str,
        tcp_port: int,
        discovery_port: int = 9999,
        interval: float = 3.0,
        broadcast_addr: str = "255.255.255.255",
        status: str = "online",
        node_id: str | None = None,
    ):
        self.name = name
        self.tcp_port = tcp_port
        self.discovery_port = discovery_port
        self.interval = interval
        self.broadcast_addr = broadcast_addr
        self.status = status
        self.node_id = node_id if node_id else str(uuid.uuid4())
        self.running = False
        self._thread: threading.Thread | None = None
        self._wake_event = threading.Event()
        self._socket: socket.socket | None = None

    def _setupSocket(self) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        return sock

    def start(self) -> None:
        self.running = True
        self._socket = self._setupSocket()
        self._thread = threading.Thread(target=self._broadcastLoop, daemon=True, name="UDP-Broadcaster")
        self._thread.start()

    def stop(self) -> None:
        if not self.running:
            return
        self.sendGoodbye()
        self.running = False
        self._wake_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

    def setStatus(self, new_status: str) -> None:
        self.status = new_status
        self.sendStatusUpdate(new_status)

    def _sendDatagram(self, payload: bytes) -> None:
        if not self._socket:
            return
        targets = [
            (self.broadcast_addr, self.discovery_port),
            ("127.0.0.1", self.discovery_port),
        ]
        for target in targets:
            try:
                self._socket.sendto(payload, target)
            except Exception:
                pass

    def sendStatusUpdate(self, status: str) -> None:
        payload = createStatusUpdate(self.name, self.tcp_port, status, node_id=self.node_id)
        self._sendDatagram(payload)

    def sendGoodbye(self) -> None:
        payload = createGoodbye(self.name, self.tcp_port, node_id=self.node_id)
        self._sendDatagram(payload)

    def _broadcastLoop(self) -> None:
        while self.running:
            beacon = createBeacon(self.name, self.tcp_port, self.status, node_id=self.node_id)
            self._sendDatagram(beacon)
            self._wake_event.wait(timeout=self.interval)
            self._wake_event.clear()

class UdpListener:
    def __init__(
        self,
        peer_table: PeerTable,
        my_name: str,
        my_tcp_port: int,
        discovery_port: int = 9999,
        my_node_id: str = "",
        on_peer_join: Callable[[Peer], None] | None = None,
        on_peer_leave: Callable[[Peer], None] | None = None,
        on_peer_status_change: Callable[[Peer, str], None] | None = None,
        on_peer_timeout: Callable[[Peer], None] | None = None,
    ):
        self.peer_table = peer_table
        self.my_name = my_name
        self.my_tcp_port = my_tcp_port
        self.discovery_port = discovery_port
        self.my_node_id = my_node_id
        self.on_peer_join = on_peer_join
        self.on_peer_leave = on_peer_leave
        self.on_peer_status_change = on_peer_status_change
        self.on_peer_timeout = on_peer_timeout
        self.running = False
        self._socket: socket.socket | None = None
        self._recv_thread: threading.Thread | None = None
        self._prune_thread: threading.Thread | None = None

    def _setupSocket(self) -> socket.socket:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        # Bind to all interfaces on discovery port
        sock.bind(("", self.discovery_port))
        sock.settimeout(1.0)
        return sock

    def start(self) -> None:
        self.running = True
        self._socket = self._setupSocket()
        self._recv_thread = threading.Thread(target=self._listenLoop, daemon=True, name="UDP-Listener")
        self._prune_thread = threading.Thread(target=self._pruneLoop, daemon=True, name="UDP-Pruner")
        self._recv_thread.start()
        self._prune_thread.start()

    def stop(self) -> None:
        self.running = False
        if self._recv_thread and self._recv_thread.is_alive():
            self._recv_thread.join(timeout=1.0)
        if self._prune_thread and self._prune_thread.is_alive():
            self._prune_thread.join(timeout=1.0)
        if self._socket:
            try:
                self._socket.close()
            except Exception:
                pass
            self._socket = None

    def _listenLoop(self) -> None:
        while self.running and self._socket:
            try:
                data, addr = self._socket.recvfrom(4096)
                sender_ip = addr[0]
                payload = parseDatagram(data)
                if not payload:
                    continue
                
                peer_name = payload["name"]
                peer_tcp_port = int(payload["port"])
                msg_type = payload["type"]
                status = payload.get("status", "online")

                # Discard packets from ourselves using node_id
                sender_node_id = payload.get("node_id")
                if sender_node_id and sender_node_id == self.my_node_id:
                    continue
                # Fallback for packets without node_id: only discard if BOTH name and port match AND IP is local
                if not sender_node_id:
                    if peer_name.lower() == self.my_name.lower() and peer_tcp_port == self.my_tcp_port:
                        if sender_ip.startswith("127.") or sender_ip == socket.gethostbyname(socket.gethostname()):
                            continue

                if msg_type == MSG_GOODBYE:
                    removed = self.peer_table.removePeer(sender_ip, peer_tcp_port)
                    if removed and self.on_peer_leave:
                        self.on_peer_leave(removed)
                elif msg_type in (MSG_BEACON, MSG_STATUS_UPDATE):
                    is_new, status_changed, peer = self.peer_table.addOrUpdatePeer(
                        name=peer_name,
                        ip=sender_ip,
                        port=peer_tcp_port,
                        status=status,
                    )
                    if is_new and self.on_peer_join:
                        self.on_peer_join(peer)
                    elif status_changed and self.on_peer_status_change:
                        self.on_peer_status_change(peer, status)

            except (socket.timeout, TimeoutError):
                continue
            except Exception:
                if not self.running:
                    break

    def _pruneLoop(self) -> None:
        while self.running:
            time.sleep(1.0)
            expired_peers = self.peer_table.pruneExpiredPeers()
            for peer in expired_peers:
                if self.on_peer_timeout:
                    self.on_peer_timeout(peer)
