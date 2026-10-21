import sys
import os
import socket
import time
import tomllib

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from UI import UI as ui
from cn_logging import CNLogger as log

CLIENT_CONFIG_PATH = "./socket project/configs/client_config.toml"

def loadClientConfig(configpath: str = CLIENT_CONFIG_PATH) -> dict:
    if os.path.exists(configpath):
        with open(configpath, "rb") as cfg:
            data = tomllib.load(cfg)
            return data.get("client", data)
    return {}

CLIENT_CONFIG = loadClientConfig()
DEFAULT_HOST: str = CLIENT_CONFIG.get("server_host", "127.0.0.1")
BUFFER_SIZE: int = CLIENT_CONFIG.get("buffer_size", 1024)
MAX_RETRIES: int = CLIENT_CONFIG.get("max_retries", 3)
RETRY_DELAY: int = CLIENT_CONFIG.get("retry_delay", 1)
TIMEOUT: int = CLIENT_CONFIG.get("timeout", 5)

class ClientTCP:
    def __init__(self, host: str = DEFAULT_HOST, port: int = 0):
        self.host = host
        self.port = port
        self.clientsocket: socket.socket | None = None
        self.log = log(instancepfx="client_tcp")

    # Init socket
    def setupSocket(self):
        if not self.log.filepath:
            self.log.initLogger()

        if self.clientsocket is not None:
            self.log.logWarn(f"Existing socket running, instance: '{self.clientsocket}'. Closing to reinitiate.")
            self.closeSocket()

        self.clientsocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.clientsocket.settimeout(TIMEOUT)
        self.log.logClient("Client socket initiated. Protocol: [TCP].", action = "INITIATION", console = True)

    # Connect to TCP server
    def connectServer(self, host: str | None = None, port: int | None = None, maxretries: int = MAX_RETRIES) -> bool:
        if self.clientsocket is None:
            self.log.logError("Client socket is not initialized. Call setupSocket() first.", action = "CONNECT")
            return False

        if host is not None:
            self.host = host
        if port is not None:
            self.port = port

        for attempt in range(1, maxretries + 1):
            try:
                self.clientsocket.connect((self.host, self.port))
                self.log.logClient(f"Connected to server at {self.host}:{self.port}.", action = "CONNECT", console = True)
                return True
            except socket.error as err:
                self.log.logError(f"Connect error ({attempt}/{maxretries}) to {self.host}:{self.port}: {err}.", action = "CONNECT")
                if attempt < maxretries:
                    time.sleep(RETRY_DELAY)

        self.log.logError(f"Failed to connect to {self.host}:{self.port} after maximum retries.", action = "CONNECT")
        return False

    def sendData(self, data: bytes | str, maxretries: int = MAX_RETRIES) -> bool:
        if self.clientsocket is None:
            self.log.logError("Client socket is not initialized. Call setupSocket() & connectServer() first.", action = "SEND")
            return False

        if isinstance(data, str):
            data = data.encode("utf-8")

        for attempt in range(1, maxretries + 1):
            try:
                self.clientsocket.sendall(data)
                self.log.logClient(f"Sent {len(data)} bytes.", action = "SEND", console = False)
                return True
            except (BrokenPipeError, ConnectionResetError) as err:
                self.log.logError(f"Connection lost during send: {err}.", action = "SEND")
                return False
            except socket.error as err:
                self.log.logError(f"Socket send error ({attempt}/{maxretries}): {err}.", action = "SEND")
                if attempt < maxretries:
                    time.sleep(RETRY_DELAY)
        return False

    def receiveData(self, buffersize: int = BUFFER_SIZE, maxretries: int = MAX_RETRIES) -> bytes:
        if self.clientsocket is None:
            self.log.logError("Client socket is not initialized. Call setupSocket() & connectServer() first.", action = "RECEIVE")
            return b""

        for attempt in range(1, maxretries + 1):
            try:
                data = self.clientsocket.recv(buffersize)
                if not data:
                    self.log.logServer("Server closed the connection.", action = "DISCONNECT", console = True)
                else:
                    self.log.logClient(f"Received {len(data)} bytes.", action = "RECEIVE", console = False)
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
        if self.clientsocket is None:
            return

        for attempt in range(1, maxretries + 1):
            try:
                if self.clientsocket is not None:
                    self.clientsocket.close()
                    self.clientsocket = None
                self.log.logClient("Client TCP socket closed successfully.", action = "CLOSE", console = True)
                return
            except socket.error as err:
                self.log.logError(f"Socket close error ({attempt}/{maxretries}): {err}.", action = "CLOSE")
                if attempt < maxretries:
                    time.sleep(RETRY_DELAY)
