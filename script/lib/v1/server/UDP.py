'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Shirayume_Hibiki          ║
║  Creation date:            21/10/26                  ║
║  Edit dates / contributor:                           ║
║  24/10/26 Shirayume_Hibiki                           ║
╚══════════════════════════════════════════════════════╝
'''

import os
import socket
import sys
import time
import tomllib

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from UI import UI as ui
from cn_logging import CNLogger as log

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
SERVER_CONFIG_PATH = os.path.join(PROJECT_ROOT, "configs", "server_config.toml")

def loadServerConfig(configpath: str = SERVER_CONFIG_PATH) -> dict:
    if os.path.exists(configpath):
        with open(configpath, "rb") as cfg:
            data = tomllib.load(cfg)
            return data.get("server", data)
    return {}

SERVER_CONFIG = loadServerConfig()
DEFAULT_HOST: str = SERVER_CONFIG.get("host", "127.0.0.1")
UDP_PORT: int = SERVER_CONFIG.get("udp_port", 8888)
BUFFER_SIZE: int = SERVER_CONFIG.get("buffer_size", 1024)
MAX_RETRIES: int = SERVER_CONFIG.get("max_retries", 3)
RETRY_DELAY: int = SERVER_CONFIG.get("retry_delay", 1)

class ServerUDP:
    def __init__(self, host: str = DEFAULT_HOST, port: int = UDP_PORT):
        self.host = host
        self.port = port
        self.serversocket: socket.socket | None = None
        self.log = log(instancepfx="server_udp")

    # Init fixed UDP server socket
    def setupSocket(self):
        if not self.log.filepath:
            self.log.initLogger()

        if self.serversocket is not None:
            self.log.logWarn(f"Existing socket running. Closing to reinitiate.")
            self.closeSocket()

        self.serversocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.log.logServer("Server socket initiated. Protocol: [UDP].", action = "INITIATION", console = True)

    # Bind UDP server socket to fixed port
    def bindSocket(self, port: int | None = None, maxretries: int = MAX_RETRIES):
        if self.serversocket is None:
            self.log.logError("Server socket is not initialized. Call setupSocket() first.", action = "BIND")
            return None

        if port is not None:
            self.port = port

        bound = False
        for attempt in range(1, maxretries + 1):
            try:
                self.serversocket.bind((self.host, self.port))
                self.log.logServer(f"Bound UDP socket to fixed port {self.host}:{self.port}.", action = "BIND", console = True)
                bound = True
                break
            except OSError as err:
                self.log.logError(f"Bind error ({attempt}/{maxretries}) on {self.host}:{self.port}: {err}.", action = "BIND")
                if attempt < maxretries:
                    time.sleep(RETRY_DELAY)

        if not bound:
            self.log.logError(f"Failed to bind fixed UDP socket on port {self.port} after maximum retries. Aborting...", action = "BIND")
            self.closeSocket()
            return None

        return self.serversocket

    def sendData(self, addr: tuple[str, int], data: bytes | str, maxretries: int = MAX_RETRIES) -> bool:
        if self.serversocket is None:
            self.log.logError("Socket is not initialized. Call setupSocket() and bindSocket() first.", action = "SEND")
            return False

        if isinstance(data, str):
            data = data.encode("utf-8")

        for attempt in range(1, maxretries + 1):
            try:
                self.serversocket.sendto(data, addr)
                self.log.logServer(f"Sent {len(data)} bytes to {addr}.", action = "SEND", console = False)
                return True
            except socket.error as err:
                self.log.logError(f"UDP send error ({attempt}/{maxretries}) to {addr}: {err}.", action = "SEND")
                if attempt < maxretries:
                    time.sleep(RETRY_DELAY)
        return False

    def receiveData(self, buffersize: int = BUFFER_SIZE, maxretries: int = MAX_RETRIES) -> tuple[bytes, tuple[str, int] | None]:
        if self.serversocket is None:
            self.log.logError("Socket is not initialized. Call setupSocket() and bindSocket() first.", action = "RECEIVE")
            return b"", None

        for attempt in range(1, maxretries + 1):
            try:
                data, addr = self.serversocket.recvfrom(buffersize)
                self.log.logServer(f"Received {len(data)} bytes from {addr}.", action = "RECEIVE", console = False)
                return data, addr
            except ConnectionResetError as err:
                # ICMP Port Unreachable on Windows UDP
                self.log.logError(f"Peer unreachable while receiving: {err}.", action = "RECEIVE")
                return b"", None
            except socket.error as err:
                self.log.logError(f"UDP receive error ({attempt}/{maxretries}): {err}.", action = "RECEIVE")
                if attempt < maxretries:
                    time.sleep(RETRY_DELAY)
        return b"", None

    def closeSocket(self, maxretries: int = MAX_RETRIES):
        if self.serversocket is None:
            return

        for attempt in range(1, maxretries + 1):
            try:
                if self.serversocket is not None:
                    self.serversocket.close()
                    self.serversocket = None
                self.log.logServer("UDP server socket closed successfully.", action = "CLOSE", console = True)
                return
            except socket.error as err:
                self.log.logError(f"Socket close error ({attempt}/{maxretries}): {err}.", action = "CLOSE")
                if attempt < maxretries:
                    time.sleep(RETRY_DELAY)
