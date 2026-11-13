'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Shirayume-Hibiki          ║
║  Creation date:            12/11/26                  ║
║  Edit dates / contributor:                           ║
║  13/11/26 Shirayume-Hibiki                           ║
╚══════════════════════════════════════════════════════╝
'''

import threading
import time

class Peer:
    def __init__(self, name: str, ip: str, port: int, status: str = "online", last_seen: float | None = None):
        self.name = name
        self.ip = ip
        self.port = port
        self.status = status
        self.last_seen = last_seen if last_seen is not None else time.time()

    @property
    def key(self) -> str:
        return f"{self.ip}:{self.port}"

    def isExpired(self, timeout: float = 10.0, current_time: float | None = None) -> bool:
        now = current_time if current_time is not None else time.time()
        return (now - self.last_seen) > timeout

    def __repr__(self) -> str:
        return f"<Peer {self.name} ({self.ip}:{self.port}) [{self.status}]>"

class PeerTable:
    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout
        self._lock = threading.Lock()
        self._peers: dict[str, Peer] = {}

    def addOrUpdatePeer(self, name: str, ip: str, port: int, status: str, ts: float | None = None) -> tuple[bool, bool, Peer]:
        with self._lock:
            now = ts if ts is not None else time.time()
            name_key = name.lower()
            if name_key in self._peers:
                peer = self._peers[name_key]
                old_status = peer.status
                peer.name = name
                # Update IP: prefer non-loopback IP, but update if previous was loopback or current is non-loopback
                if not ip.startswith("127."):
                    peer.ip = ip
                elif peer.ip.startswith("127."):
                    peer.ip = ip
                # Always update port to handle dynamic port re-allocations / restarts
                peer.port = port
                peer.status = status
                peer.last_seen = now
                status_changed = (old_status != status)
                return False, status_changed, peer
            else:
                peer = Peer(name=name, ip=ip, port=port, status=status, last_seen=now)
                self._peers[name_key] = peer
                return True, False, peer

    def removePeer(self, ip: str, port: int) -> Peer | None:
        with self._lock:
            for k, peer in list(self._peers.items()):
                if (peer.ip == ip or peer.ip.startswith("127.") or ip.startswith("127.")) and peer.port == port:
                    del self._peers[k]
                    return peer
            return None

    def removePeerByName(self, name: str) -> Peer | None:
        with self._lock:
            return self._peers.pop(name.lower(), None)

    def pruneExpiredPeers(self, timeout: float | None = None) -> list[Peer]:
        expiry = timeout if timeout is not None else self.timeout
        now = time.time()
        expired: list[Peer] = []
        with self._lock:
            keys_to_remove = []
            for key, peer in self._peers.items():
                if peer.isExpired(expiry, now):
                    keys_to_remove.append(key)
                    expired.append(peer)
            for key in keys_to_remove:
                del self._peers[key]
        return expired

    def getActivePeers(self) -> list[Peer]:
        with self._lock:
            return sorted(self._peers.values(), key=lambda p: p.name.lower())

    def getPeerByIndex(self, index: int) -> Peer | None:
        peers = self.getActivePeers()
        if 1 <= index <= len(peers):
            return peers[index - 1]
        return None

    def getPeerByName(self, name: str) -> Peer | None:
        with self._lock:
            for peer in self._peers.values():
                if peer.name.lower() == name.lower():
                    return peer
            return None

    def getPeerByKey(self, ip: str, port: int) -> Peer | None:
        with self._lock:
            for peer in self._peers.values():
                if (peer.ip == ip or peer.ip.startswith("127.") or ip.startswith("127.")) and peer.port == port:
                    return peer
            return None
