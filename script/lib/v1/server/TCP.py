import sys
import os
import socket
import time
import tomllib

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import common_functions as commonf
from UI import UI as ui
from cn_logging import CNLogger as log

SERVER_CONFIG_PATH = "./socket project/configs/server_config.toml"

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

class ServerTCP:
    def __init__(self, host: str = DEFAULT_HOST, port: int = 0, backlog: int = 5):
        self.host = host
        self.port = port
        self.backlog = backlog
        self.serversocket: socket.socket | None = None
        self.log = log(instancepfx="server_tcp")

    # Init socket
    def setupSocket(self):
        if not self.log.filepath:
            self.log.initLogger()

        if self.serversocket is not None: 
            self.closeSocket()

        self.serversocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.serversocket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        self.log.logSystem(f"Server socket initiated. Protocol: [TCP].", action = "INITIATION", console = True)

    # Bind socket
    def bindSocket(self, port: int):
        if self.serversocket is None:
            self.log.logError("Server socket is not initialized. Call setupSocket() first.", action = "BIND")
            return None
        
        try:
            self.serversocket.bind((self.host, port))
        except OSError as err:
            self.log.logError(f"Bind error on {self.host}:{self.port} ({err}), switching port...")
            fallbackport = commonf.portFinder()
            self.serversocket.bind((self.host, fallbackport))
        
        # Update self.port
        self.port = self.serversocket.getsockname()[1]
        self.serversocket.listen(self.backlog)
        self.log.logServer(f"Listening on {self.host}:{self.port}.", action = "LISTEN", console = False)
        return self.serversocket

    def acceptConnection(self, maxretries = MAX_RETRIES):
        if self.serversocket is None:
            self.log.logError("Server socket is not initialized. Call setupSocket() & bindSocket() first.")
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
        self.setupSocket()
        self.bindSocket(newport)

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

    def closeSocket(self, maxretries = MAX_RETRIES):
        if self.serversocket is None:
            return
        
        for attempt in range(1, maxretries + 1):
            try:
                if self.serversocket is not None:
                    self.serversocket.close()
                    self.serversocket = None
                self.log.logServer("Server socket closed successfully.", action = "CLOSE", console = True)
                return
            except socket.error as err:
                self.log.logError(f"Socket close error ({attempt}/{maxretries}): {err}.", action = "CLOSE")
                if attempt < maxretries:
                    time.sleep(RETRY_DELAY)