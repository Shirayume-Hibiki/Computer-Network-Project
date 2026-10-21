'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Shirayume_Hibiki          ║
║  Creation date:            21/10/26                  ║
║  Edit dates / contributor:                           ║
╚══════════════════════════════════════════════════════╝
'''

import sys
import os
import socket
import time
import tomllib

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from UI import UI as ui
from cn_logging import CNLogger as log

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
CLIENT_CONFIG_PATH = os.path.join(PROJECT_ROOT, "configs", "client_config.toml")

def loadClientConfig(configpath: str = CLIENT_CONFIG_PATH) -> dict:
    if os.path.exists(configpath):
        with open(configpath, "rb") as cfg:
            data = tomllib.load(cfg)
            return data.get("client", data)
    return {}

CLIENT_CONFIG = loadClientConfig()
DEFAULT_HOST: str = CLIENT_CONFIG.get("server_host", "127.0.0.1")
DISCOVERY_PORT: int = CLIENT_CONFIG.get("discovery_port", 9999)
BUFFER_SIZE: int = CLIENT_CONFIG.get("buffer_size", 1024)
MAX_RETRIES: int = CLIENT_CONFIG.get("max_retries", 3)
RETRY_DELAY: int = CLIENT_CONFIG.get("retry_delay", 1)
TIMEOUT: int = CLIENT_CONFIG.get("timeout", 5)

class ClientUDP:
    def __init__(self, host: str = DEFAULT_HOST, port: int = 0, discoveryport: int = DISCOVERY_PORT):
        self.host = host
        self.port = port
        self.discoveryport = discoveryport
        self.clientsocket: socket.socket | None = None
        self.log = log(instancepfx="client_udp")

    # Init UDP socket
    def setupSocket(self):
        if not self.log.filepath:
            self.log.initLogger()

        if self.clientsocket is not None:
            self.log.logWarn(f"Existing socket running, instance: '{self.clientsocket}'. Closing to reinitiate.")
            self.closeSocket()

        self.clientsocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.clientsocket.settimeout(TIMEOUT)
        self.log.logClient("Client socket initiated. Protocol: [UDP].", action = "INITIATION", console = True)

    # Discover server main UDP port via port 9999
    def discoverServer(self, pingmsg: str = "DISCOVER_UDP", maxretries: int = MAX_RETRIES) -> tuple[str, int] | None:
        if self.clientsocket is None:
            self.log.logError("Client socket is not initialized. Call setupSocket() first.", action = "DISCOVERY")
            return None

        discoveryaddr = (self.host, self.discoveryport)
        for attempt in range(1, maxretries + 1):
            self.log.logClient(f"Pinging discovery server at {discoveryaddr} ({attempt}/{maxretries})...", action = "DISCOVERY", console = True)
            if self.sendData(pingmsg, addr = discoveryaddr, maxretries = 1):
                data, serveraddr = self.receiveData(maxretries = 1)
                if data:
                    decoded = data.decode("utf-8", errors="ignore").strip().rstrip(".")
                    # Extract host:port from "Server's UDP socket is listening on 127.0.0.1:xxxxx"
                    target = decoded.split()[-1]
                    if ":" in target:
                        hostpart, portpart = target.rsplit(":", 1)
                        if portpart.isdigit():
                            self.host = hostpart
                            self.port = int(portpart)
                            self.log.logClient(f"Discovered server UDP main address: {self.host}:{self.port}.", action = "DISCOVERY", console = True)
                            return self.host, self.port
            if attempt < maxretries:
                time.sleep(RETRY_DELAY)

        self.log.logError("Failed to discover UDP server after maximum retries.", action = "DISCOVERY")
        return None

    def sendData(self, data: bytes | str, addr: tuple[str, int] | None = None, maxretries: int = MAX_RETRIES) -> bool:
        if self.clientsocket is None:
            self.log.logError("Client socket is not initialized. Call setupSocket() first.", action = "SEND")
            return False

        targetaddr = addr or (self.host, self.port)
        if targetaddr[1] == 0:
            self.log.logError("Target server port is 0. Call discoverServer() or set port first.", action = "SEND")
            return False

        if isinstance(data, str):
            data = data.encode("utf-8")

        for attempt in range(1, maxretries + 1):
            try:
                self.clientsocket.sendto(data, targetaddr)
                self.log.logClient(f"Sent {len(data)} bytes to {targetaddr}.", action = "SEND", console = False)
                return True
            except socket.error as err:
                self.log.logError(f"UDP send error ({attempt}/{maxretries}): {err}.", action = "SEND")
                if attempt < maxretries:
                    time.sleep(RETRY_DELAY)
        return False

    def receiveData(self, buffersize: int = BUFFER_SIZE, maxretries: int = MAX_RETRIES) -> tuple[bytes, tuple[str, int] | None]:
        if self.clientsocket is None:
            self.log.logError("Client socket is not initialized. Call setupSocket() first.", action = "RECEIVE")
            return b"", None

        for attempt in range(1, maxretries + 1):
            try:
                data, addr = self.clientsocket.recvfrom(buffersize)
                self.log.logClient(f"Received {len(data)} bytes from {addr}.", action = "RECEIVE", console = False)
                return data, addr
            except ConnectionResetError as err:
                self.log.logError(f"Server unreachable while receiving: {err}.", action = "RECEIVE")
                return b"", None
            except socket.error as err:
                self.log.logError(f"UDP receive error ({attempt}/{maxretries}): {err}.", action = "RECEIVE")
                if attempt < maxretries:
                    time.sleep(RETRY_DELAY)
        return b"", None

    def closeSocket(self, maxretries: int = MAX_RETRIES):
        if self.clientsocket is None:
            return

        for attempt in range(1, maxretries + 1):
            try:
                if self.clientsocket is not None:
                    self.clientsocket.close()
                    self.clientsocket = None
                self.log.logClient("Client UDP socket closed successfully.", action = "CLOSE", console = True)
                return
            except socket.error as err:
                self.log.logError(f"Socket close error ({attempt}/{maxretries}): {err}.", action = "CLOSE")
                if attempt < maxretries:
                    time.sleep(RETRY_DELAY)
