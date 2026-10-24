'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Shirayume_Hibiki          ║
║  Creation date:            18/10/26                  ║
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
import common_functions as commonf

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
BUFFER_SIZE: int = SERVER_CONFIG.get("buffer_size", 1024)
MAX_RETRIES: int = SERVER_CONFIG.get("max_retries", 3)
RETRY_DELAY: int = SERVER_CONFIG.get("retry_delay", 1)
DISCOVERY_PORT: int = SERVER_CONFIG.get("discovery_port", 9999)

class ServerTCP:
    def __init__(self, host: str = DEFAULT_HOST, port: int = 0, discoveryport: int = DISCOVERY_PORT, backlog: int = 5):
        self.host = host
        self.port = port
        self.discoveryport = discoveryport
        self.backlog = backlog
        self.serversocket: socket.socket | None = None
        self.discovery: socket.socket | None = None
        self.log = log(instancepfx="server_tcp")

    # Init sockets (main TCP socket + UDP discovery socket)
    def setupSockets(self):
        if not self.log.filepath:
            self.log.initLogger()

        if self.serversocket is not None or self.discovery is not None:
            self.log.logWarn(f"Existing socket running. Closing to reinitiate.")
            self.closeSocket()

        self.serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.discovery = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.discovery.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.log.logSystem("Server socket initiated. Protocol: [TCP].", action = "INITIATION", console = True)
        self.log.logSystem("Discovery socket initiated. Protocol: [UDP].", action = "INITIATION", console = True)

    # Bind main TCP socket and UDP discovery socket
    def bindSockets(self, port: int | None = None, maxretries: int = MAX_RETRIES):
        if self.serversocket is None or self.discovery is None:
            self.log.logError("Server sockets are not initialized. Call setupSockets() first.", action = "BIND")
            return None

        self.port = port if port is not None else commonf.portFinder()

        # 1. Bind main TCP socket
        bound = False
        for attempt in range(1, maxretries + 1):
            try:
                self.serversocket.bind((self.host, self.port))
                self.port = self.serversocket.getsockname()[1]
                self.serversocket.listen(self.backlog)
                self.log.logServer(f"Listening on {self.host}:{self.port}.", action = "LISTEN", console = False)
                bound = True
                break
            except OSError as err:
                self.log.logError(f"Bind error ({attempt}/{maxretries}) on {self.host}:{self.port} ({err}), switching port...", action = "BIND")
                self.port = commonf.portFinder()
                if attempt < maxretries:
                    time.sleep(RETRY_DELAY)

        if not bound:
            self.log.logError("Failed to bind main TCP socket after maximum retries. Aborting...", action = "BIND")
            self.closeSocket()
            return None

        # 2. Bind discovery UDP socket
        discoverybound = False
        for attempt in range(1, maxretries + 1):
            try:
                self.discovery.bind((self.host, self.discoveryport))
                self.log.logServer(f"Discovery port bound to {self.host}:{self.discoveryport}.", action = "BIND", console = True)
                discoverybound = True
                break
            except OSError as err:
                self.log.logError(f"Discovery port binding error ({attempt}/{maxretries}) on {self.host}:{self.discoveryport} ({err}). Reconnecting...", action = "BIND")
                if attempt < maxretries:
                    time.sleep(RETRY_DELAY)

        if not discoverybound:
            self.log.logError("Failed to bind discovery port after maximum retries. Aborting...", action = "BIND")
            self.closeSocket()
            return None

        return self.serversocket

    # Announce TCP port to discovering clients via UDP port 9999
    def announcePort(self) -> tuple[str, int] | None:
        if self.discovery is None:
            self.log.logError("Discovery socket not initiated. Use setupSockets() first.", action = "ANNOUNCE")
            return None

        try:
            data, clientaddr = self.discovery.recvfrom(BUFFER_SIZE)
            if clientaddr is not None:
                msg = f"Server's TCP socket is listening on {self.host}:{self.port}."
                self.discovery.sendto(msg.encode("utf-8"), clientaddr)
                self.log.logServer(f"Announced TCP port ({self.port}) to {clientaddr}.", action = "ANNOUNCE", console = True)
                return clientaddr
        except (socket.timeout, TimeoutError):
            return None
        except socket.error as err:
            self.log.logError(f"Discovery announce error: {err}.", action = "ANNOUNCE")
        return None

    def acceptConnection(self, maxretries: int = MAX_RETRIES):
        if self.serversocket is None:
            self.log.logError("Server socket is not initialized. Call setupSockets() & bindSockets() first.", action = "ACCEPT")
            return None, None

        for attempt in range(1, maxretries + 1):
            try:
                conn, addr = self.serversocket.accept()
                self.log.logServer(f"Connection accepted from {addr}.", action = "ACCEPT", console = True)
                return conn, addr
            except socket.error as err:
                self.log.logError(f"Accept error ({attempt}/{maxretries}): {err}.", action = "ACCEPT")
                if attempt < maxretries:
                    time.sleep(RETRY_DELAY)
        return None, None

    def switchPort(self):
        newport = commonf.portFinder()
        self.log.logSystem(f"Switching to a new available port... Target: {newport}.", action = "SWITCH_PORT", console = True)
        self.setupSockets()
        self.bindSockets(newport)

    def sendData(self, conn: socket.socket, data: bytes | str, maxretries: int = MAX_RETRIES) -> bool:
        if isinstance(data, str):
            data = data.encode("utf-8")

        for attempt in range(1, maxretries + 1):
            try:
                conn.sendall(data)
                self.log.logServer(f"Sent {len(data)} bytes.", action = "SEND", console = False)
                return True
            except (BrokenPipeError, ConnectionResetError) as err:
                self.log.logError(f"Connection lost during send: {err}.", action = "SEND")
                return False
            except socket.error as err:
                self.log.logError(f"Socket send error ({attempt}/{maxretries}): {err}.", action = "SEND")
                if attempt < maxretries:
                    time.sleep(RETRY_DELAY)
        return False

    def receiveData(self, conn: socket.socket, buffersize: int = BUFFER_SIZE, maxretries: int = MAX_RETRIES) -> bytes:
        for attempt in range(1, maxretries + 1):
            try:
                data = conn.recv(buffersize)
                if not data:
                    self.log.logClient("Client disconnected.", action = "DISCONNECT", console = True)
                else:
                    self.log.logServer(f"Received {len(data)} bytes.", action = "RECEIVE", console = False)
                return data
            except (BrokenPipeError, ConnectionResetError) as err:
                self.log.logError(f"Connection lost while receiving: {err}.", action = "RECEIVE")
                return b""
            except socket.error as err:
                self.log.logError(f"Socket receive error ({attempt}/{maxretries}): {err}.", action = "RECEIVE")
                if attempt < maxretries:
                    time.sleep(RETRY_DELAY)
        return b""

    def closeSocket(self, maxretries: int = MAX_RETRIES):
        if self.serversocket is None and self.discovery is None:
            return

        for attempt in range(1, maxretries + 1):
            try:
                if self.serversocket is not None:
                    self.serversocket.close()
                    self.serversocket = None
                if self.discovery is not None:
                    self.discovery.close()
                    self.discovery = None
                self.log.logServer("Server TCP and discovery sockets closed successfully.", action = "CLOSE", console = True)
                return
            except socket.error as err:
                self.log.logError(f"Socket close error ({attempt}/{maxretries}): {err}.", action = "CLOSE")
                if attempt < maxretries:
                    time.sleep(RETRY_DELAY)
