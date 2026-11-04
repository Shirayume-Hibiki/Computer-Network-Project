'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Koro_Gold                 ║
║  Creation date:            30/10/26                  ║
║  Edit dates / contributor:                           ║
╚══════════════════════════════════════════════════════╝
'''

import os
import sys
import json
import time
import uuid

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib", "v1"))

from client.UDP import ClientUDP
from server.UDP import ServerUDP
from UI import UI as ui

DISCOVERY_PORT = 9999
BROADCAST_INTERVAL = 3
PEER_TIMEOUT = 10
BUFFER_SIZE = 1024
BROADCAST_ADDRESS = "255.255.255.255"

class PeerDiscovery:
    def __init__(self, username: str, tcp_port: int):
        self.username = username
        self.tcp_port = tcp_port
        self.peer_id = str(uuid.uuid4())
        self.peers = {}
        self.status = "online"
        self.running = False

        self.client = ClientUDP(host = BROADCAST_ADDRESS, port = DISCOVERY_PORT)
        self.server = ServerUDP(host = "0.0.0.0", port = DISCOVERY_PORT)

    def setup(self):
        ui.systemMsg("Initializing peer discovery...", action = "START")
        self.client.setupSocket()
        self.server.setupSocket()
        bound = self.server.bindSocket()

        if bound is None:
            ui.errorMsg("Failed to initialize peer discovery listener.", action = "ERROR")
            self.client.closeSocket()
            return False

        ui.systemMsg(f"Broadcasting presence on UDP port {DISCOVERY_PORT}", action = "READY")
        ui.systemMsg(f"Your username is '{self.username}' with TCP port {self.tcp_port}.", action = "CONFIG")
        return True

    def broadcastPresence(self):
        message = {
            "type": "DISCOVER",
            "id": self.peer_id,
            "name": self.username,
            "tcp_port": self.tcp_port,
            "status": self.status
        }

        payload = json.dumps(message)
        sent = self.client.sendData(payload)

        if sent:
            ui.clientMsg(f"Broadcasting presence as '{self.username}.", action = "BROADCAST")
        else:
            ui.errorMsg("Failed to broadcast presence.", action = "BROADCAST")

    def receivePresence(self):
        data, address = self.server.receiveData(buffersize = BUFFER_SIZE)
        if not data or address is None:
            return

        try:
            message = json.loads(data.decode("utf-8"))

            if message.get("type") != "DISCOVER":
                return

            peer_id = message.get("id")
            name = message.get("name")
            tcp_port = message.get("tcp_port")
            status = message.get("status")

            if not isinstance(peer_id, str) or not peer_id:
                return
            
            if not isinstance(name, str) or not name:
                return
            
            if (
                isinstance(tcp_port, bool)
                or not isinstance(tcp_port, int)
                or not 1 <= tcp_port <= 65535
            ):
                return
            
            if status not in ("online", "away"):
                return

            if peer_id == self.peer_id:
                return

            ip_address = address[0]

            is_new = peer_id not in self.peers
            old_status = (self.peers[peer_id]['status'] if not is_new else None)
            self.peers[peer_id] = {
                "name": name,
                "ip": ip_address,
                "tcp_port": tcp_port,
                "status": status,
                "last_seen": time.monotonic()
            }

            if is_new:
                ui.systemMsg(f"{name} ({ip_address}) is now online.", action = "PEER ONLINE")
            elif old_status != status:
                ui.systemMsg(f"{name} changed status to {status}.", action = "STATUS")

        except (json.JSONDecodeError, UnicodeDecodeError):
            ui.warningMsg("Received an invalid discovery message.", action = "INVALID")

    def checkTimeouts(self):
        current_time = time.monotonic()
        offline_peers = []
        for peer_id, peer in self.peers.items():
            elapsed = current_time - peer["last_seen"]
            if elapsed > PEER_TIMEOUT:
                offline_peers.append(peer_id)
                
        for peer_id in offline_peers:
            peer = self.peers.pop(peer_id)
            ui.systemMsg(f"{peer['name']} ({peer['ip']}) went offline.", action = "PEER OFFLINE")

    def displayPeers(self):
        ui.systemMsg("=== ONLINE PEERS ===", action = "PEER LIST")

        if not self.peers:
            ui.warningMsg("No other peers currently online.", action = "EMPTY")
            return

        for index, peer in enumerate(self.peers.values(), start = 1):
            ui.clientMsg(f"{index} {peer['name']} {peer['ip']} TCP: {peer['tcp_port']} {peer['status']}", action = "PEER")

    def start(self):
        if not self.setup():
            return

        self.running = True
        last_broadcast = 0
        ui.systemMsg("Peer discovery started. Press Ctrl+C to stop.", action = "RUNNING")

        try:
            while self.running:
                current_time = time.monotonic()

                if (current_time - last_broadcast >= BROADCAST_INTERVAL):
                    self.broadcastPresence()
                    last_broadcast = current_time

                self.receivePresence()
                self.checkTimeouts()
        except KeyboardInterrupt:
            ui.warningMsg("Interrupt received. Stopping peer discovery...", action = "STOP")
        finally:
            self.running = False
            self.client.closeSocket()
            self.server.closeSocket()
            ui.systemMsg("Peer discovery stopped.", action = "FINISH")

def main():
    username = input("Enter your username: ").strip()

    if not username:
        username = "Anonymous"

    tcp_port = int(input("Enter your TCP port: ").strip())

    discovery = PeerDiscovery(username=username, tcp_port=tcp_port)
    discovery.start()

if __name__ == "__main__":
    main()
