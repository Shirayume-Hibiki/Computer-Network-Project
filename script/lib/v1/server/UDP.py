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

import common_functions as commonf
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
BUFFER_SIZE: int = SERVER_CONFIG.get("buffer_size", 1024)
MAX_RETRIES: int = SERVER_CONFIG.get("max_retries", 3)
RETRY_DELAY: int = SERVER_CONFIG.get("retry_delay", 1)
DISCOVERY_PORT = 9999

class ServerUDP:
    def __init__(self, host: str = DEFAULT_HOST, port: int = 0, backlog: int = 5):
            self.host = host
            self.port = port
            self.backlog = backlog
            self.serversocket: socket.socket | None = None
            self.discovery: socket.socket | None = None
            self.log = log(instancepfx="server_udp")

    def setupSockets(self):
        if not self.log.filepath:
            self.log.initLogger()
         
        if self.serversocket is not None or self.discovery is not None: 
            self.log.logWarn(f"Existing socket running, instance: '{self.serversocket}'. Closing to reinitiate.")
            self.closeSocket()

        self.serversocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        self.discovery = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.discovery.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        
        self.log.logServer("Server socket initiated. Protocol: [UDP].", "INITIATION", True)
        self.log.logServer("Discovery socket initiated.", "INITIATION")
    
    def bindSockets(self, port: int | None = None, maxretries = MAX_RETRIES):
        if self.serversocket is None or self.discovery is None:
            self.log.logError("Server sockets is not initialized. Call setupSockets() first.", action = "BIND")
            return None

        self.port = port if port is not None else commonf.portFinder()

        bound = False
        for attempt in range(1, maxretries+ 1):
            try:
                self.serversocket.bind((self.host, self.port))
                self.port = self.serversocket.getsockname()[1]
                self.log.logServer(f"Bound main socket to {self.host}:{self.port}.", "BIND")
                bound = True
                break
            except OSError as err:
                self.log.logError(f"Bind error ({attempt}/{maxretries}) on {self.host}:{self.port}, ({err}). Swiitching port...")
                self.port = commonf.portFinder()
                if attempt < maxretries: 
                    time.sleep(RETRY_DELAY)
        if not bound:
            self.log.logError("Failed to bind main UDP socket after maximum retries. Aborting...", "BIND")
            self.closeSocket()
            return None

        bound = False # Reuse def init param to optimize memory
        for attempt in range(1, maxretries + 1):
            try:
                self.discovery.bind((self.host, DISCOVERY_PORT))
                self.log.logServer(f"Discovery port binded to {self.host}:9999.", "BIND")
                bound = True
                break
            except OSError as err:
                self.log.logError(f"Discovery port binding error ({attempt}/{maxretries}) on {self.host}:9999. ({err}). Reconnecting...", "BIND")
                if attempt < maxretries:
                    time.sleep(RETRY_DELAY)
        if not bound:
            self.log.logError("Failed to bind discovery port after maximum retries. Aborting...", "BIND")
            self.closeSocket()
            return None
        
        return self.serversocket

    def announcePort(self):
        if self.discovery is None:
            self.log.logError("Discovery port not initiated. Use setupSockets() first.", "ANNOUNCE")
            return None

        data, clientaddr = self.receiveData(self.discovery)
        if clientaddr is not None:
            msg = f"Server's UDP socket is listening on {self.host}:{self.port}."
            self.sendData(self.discovery, clientaddr, msg)
            self.log.logServer(f"Announced main port ({self.port}) to {clientaddr}.", "ANNOUNCE")
        return clientaddr
            
    def sendData(self, sock: socket.socket | None, addr: tuple[str, int], data: bytes | str, maxretries: int = MAX_RETRIES) -> bool:
        targetsock = sock or self.serversocket
        if targetsock is None:
            self.log.logError("Socket is not initialized.", action="SEND")
            return False
        if isinstance(data, str):
            data = data.encode("utf-8")
        for attempt in range(1, maxretries + 1):
            try:
                targetsock.sendto(data, addr)
                self.log.logServer(f"Sent {len(data)} bytes to {addr}.", action="SEND", console=False)
                return True
            except socket.error as err:
                self.log.logError(f"UDP send error ({attempt}/{maxretries}): {err}.", action="SEND")
                if attempt < maxretries:
                    time.sleep(RETRY_DELAY)
        return False

    def receiveData(self, sock: socket.socket | None = None, buffersize: int = BUFFER_SIZE, maxretries: int = MAX_RETRIES) -> tuple[bytes, tuple[str, int] | None]:
        targetsock = sock or self.serversocket
        if targetsock is None:
            self.log.logError("Socket is not initialized.", action="RECEIVE")
            return b"", None
        for attempt in range(1, maxretries + 1):
            try:
                data, addr = targetsock.recvfrom(buffersize)
                self.log.logServer(f"Received {len(data)} bytes from {addr}.", action="RECEIVE", console=False)
                return data, addr
            except ConnectionResetError as err:
                # On Windows UDP, ICMP Port Unreachable can trigger ConnectionResetError (WSAECONNRESET)
                self.log.logError(f"Peer unreachable while receiving: {err}.", action="RECEIVE")
                return b"", None
            except socket.error as err:
                self.log.logError(f"UDP receive error ({attempt}/{maxretries}): {err}.", action="RECEIVE")
                if attempt < maxretries:
                    time.sleep(RETRY_DELAY)
        return b"", None

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
                self.log.logServer("UDP server sockets closed successfully.", action="CLOSE", console=True)
                return
            except socket.error as err:
                self.log.logError(f"Socket close error ({attempt}/{maxretries}): {err}.", action="CLOSE")
                if attempt < maxretries:
                    time.sleep(RETRY_DELAY)