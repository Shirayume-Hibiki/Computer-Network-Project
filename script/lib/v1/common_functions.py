'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Shirayume_Hibiki          ║
║  Creation date:            18/10/26                  ║
║  Edit dates / contributor:                           ║
║  03/11/26 diamboy                                    ║
║  05/11/26 Gemini 3.8 Flash                           ║
║  13/11/26 Shirayume-Hibiki                           ║
╚══════════════════════════════════════════════════════╝
'''

import os
import pydoc
import socket
import sys
import tomllib

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
COMMON_CONFIG_PATH = os.path.join(PROJECT_ROOT, "configs", "common_config.toml")
UI_CONFIG_PATH = os.path.join(PROJECT_ROOT, "configs", "UI_config.toml")

def loadLanChatConfig(configpath: str = COMMON_CONFIG_PATH) -> dict:
    if os.path.exists(configpath):
        try:
            with open(configpath, "rb") as f:
                data = tomllib.load(f)
                return data.get("lan_chat", {})
        except Exception:
            pass
    return {}

def loadUIConfig(configpath: str = UI_CONFIG_PATH) -> dict:
    if os.path.exists(configpath):
        try:
            with open(configpath, "rb") as f:
                data = tomllib.load(f)
                return data.get("UI", {})
        except Exception:
            pass
    return {}

# Ensure UTF-8 output if terminal supports reconfigure
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ANSI color codes for terminal styling
BLUE = '\033[94m'
GREEN = '\033[92m'
CYAN = '\033[96m'
YELLOW = '\033[93m'
RED = '\033[91m'
GRAY = '\033[90m'
BOLD = '\033[1m'
RESET = '\033[0m'

def portFinder() -> int:
    """
    Returns port 0, directing the operating system to dynamically assign
    an ephemeral, unused port for socket binding.
    """
    return 0

def port_reserve(sock: socket.socket, host: str, port: int) -> socket.socket:
    """
    Closes the provided socket and switches to a new dynamically allocated port.
    """
    new_port = portFinder()
    print(f"Switching to new port: {new_port}")
    sock.close()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, new_port))
    return sock

# Library Command Documentation Registry
COMMAND_REGISTRY: dict[str, dict] = {
    "servertcp": {
        "title": "ServerTCP (TCP Server)",
        "module": "server.TCP",
        "class": "ServerTCP",
        "description": "Multithreaded TCP stream server with UDP broadcast announcement for dynamic port discovery.",
        "constructor": "ServerTCP(host='127.0.0.1', port=0, discoveryport=9999, backlog=5)",
        "methods": {
            "setupSockets()": "Initializes TCP stream socket (SO_REUSEADDR) and UDP discovery socket (SO_BROADCAST).",
            "bindSockets(port=None, maxretries=3)": "Binds TCP socket to host:port (uses portFinder() if port=0). Listens for connections.",
            "announcePort(interval=1.0)": "Broadcasts TCP port announcement to 255.255.255.255:9999 and 127.0.0.1:9999. Sleeps for interval seconds.",
            "acceptConnection(maxretries=3)": "Blocks until a client connects. Returns (conn, addr) or (None, None).",
            "switchPort()": "Selects a new available port, closes previous sockets, and rebinds.",
            "sendData(conn, data, maxretries=3)": "Sends bytes or str to connected client socket.",
            "receiveData(conn, buffersize=1024, maxretries=3)": "Receives up to buffersize bytes from client socket.",
            "closeSocket(maxretries=3)": "Gracefully closes both the TCP server socket and the UDP discovery socket.",
        },
        "example": (
            "from server.TCP import ServerTCP\n"
            "srv = ServerTCP()\n"
            "srv.setupSockets()\n"
            "srv.bindSockets()                # Listens on dynamic port, e.g. 54321\n"
            "srv.announcePort(interval=0)     # Broadcasts binded port to LBA 255.255.255.255:9999\n"
            "conn, addr = srv.acceptConnection()\n"
            "data = srv.receiveData(conn)\n"
            "srv.sendData(conn, 'ACK: ' + data.decode())\n"
            "srv.closeSocket()"
        ),
    },
    "clienttcp": {
        "title": "ClientTCP (TCP Client)",
        "module": "client.TCP",
        "class": "ClientTCP",
        "description": "TCP client capable of discovering dynamic server ports via UDP broadcast on port 9999 and streaming data.",
        "constructor": "ClientTCP(host='127.0.0.1', port=0, discoveryport=9999)",
        "methods": {
            "discoverServer(pingmsg='DISCOVER_TCP', maxretries=3)": "Binds UDP port 9999 (SO_REUSEADDR, SO_BROADCAST) and listens for server broadcast announcement. Updates self.host and self.port, returns (host, port).",
            "setupSocket()": "Initializes the TCP stream socket with default timeout.",
            "connectServer(host=None, port=None, maxretries=3)": "Connects to server at target host:port.",
            "sendData(data, maxretries=3)": "Sends bytes or str to the connected TCP server.",
            "receiveData(buffersize=1024, maxretries=3)": "Receives up to buffersize bytes from the TCP server.",
            "closeSocket(maxretries=3)": "Closes the TCP client socket cleanly.",
        },
        "example": (
            "from client.TCP import ClientTCP\n"
            "cli = ClientTCP()\n"
            "host, port = cli.discoverServer() # Listens on 9999 for server LBA broadcast\n"
            "cli.setupSocket()\n"
            "cli.connectServer(host, port)\n"
            "cli.sendData('Hello Server')\n"
            "response = cli.receiveData()\n"
            "cli.closeSocket()"
        ),
    },
    "serverudp": {
        "title": "ServerUDP (Fixed-port UDP Server)",
        "module": "server.UDP",
        "class": "ServerUDP",
        "description": "Fixed-port UDP datagram server with configurable timeout detection (from server_config.toml).",
        "constructor": "ServerUDP(host='127.0.0.1', port=8888, timeout_period=5)",
        "methods": {
            "setupSocket()": "Initializes UDP datagram socket (SO_REUSEADDR) with settimeout(timeout_period).",
            "bindSocket(port=None, maxretries=3)": "Binds UDP socket to host:port (fixed port 8888 by default).",
            "receiveData(buffersize=1024, maxretries=3)": "Receives datagram packet. Detects timeouts and returns (data, addr) or (b'', None).",
            "sendData(addr, data, maxretries=3)": "Sends bytes or str datagram to destination (host, port).",
            "closeSocket(maxretries=3)": "Closes the UDP server socket.",
        },
        "example": (
            "from server.UDP import ServerUDP\n"
            "srv = ServerUDP()\n"
            "srv.setupSocket()\n"
            "srv.bindSocket()\n"
            "data, addr = srv.receiveData()     # Times out after timeout_period if idle\n"
            "if data and addr:\n"
            "    srv.sendData(addr, 'UDP_ACK: ' + data.decode())\n"
            "srv.closeSocket()"
        ),
    },
    "clientudp": {
        "title": "ClientUDP (UDP Client)",
        "module": "client.UDP",
        "class": "ClientUDP",
        "description": "UDP datagram client configured to exchange datagrams with the UDP server.",
        "constructor": "ClientUDP(host='127.0.0.1', port=8888)",
        "methods": {
            "setupSocket()": "Initializes UDP datagram socket with default timeout.",
            "sendData(data, addr=None, maxretries=3)": "Sends bytes or str datagram to target address (or self.host:self.port).",
            "receiveData(buffersize=1024, maxretries=3)": "Receives datagram response. Returns (data, addr) or (b'', None).",
            "closeSocket(maxretries=3)": "Closes the UDP client socket.",
        },
        "example": (
            "from client.UDP import ClientUDP\n"
            "cli = ClientUDP()\n"
            "cli.setupSocket()\n"
            "cli.sendData('Ping Datagram')\n"
            "reply, addr = cli.receiveData()\n"
            "cli.closeSocket()"
        ),
    },
    "ui": {
        "title": "UI (Terminal Output Formatter)",
        "module": "UI",
        "class": "UI",
        "description": "Colorized status messaging utility for console debugging.",
        "constructor": "UI() (Static / Class methods)",
        "methods": {
            "serverMsg(msg, action='RESPONSE')": "Prints blue-tinted SERVER log message with timestamp.",
            "clientMsg(msg, action='REQUEST')": "Prints green-tinted CLIENT log message with timestamp.",
            "systemMsg(msg, action='INFO')": "Prints gray-tinted SYSTEM log message with timestamp.",
            "warningMsg(msg, action='WARNING')": "Prints yellow-tinted WARNING log message with timestamp.",
            "errorMsg(msg, action='ERROR')": "Prints red-tinted ERROR log message with timestamp.",
        },
        "example": (
            "from UI import UI as ui\n"
            "ui.systemMsg('Initiating tests...', action='START')\n"
            "ui.serverMsg('Listening on port 5000', action='LISTEN')\n"
            "ui.clientMsg('Connecting to server...', action='CONNECT')\n"
            "ui.warningMsg('Retrying connection (1/3)...', action='RETRY')\n"
            "ui.errorMsg('Failed to bind port', action='BIND')"
        ),
    },
    "cnlogger": {
        "title": "CNLogger (Session Logger)",
        "module": "cn_logging",
        "class": "CNLogger",
        "description": "Instance-based file and console logger that generates timestamped log files in logs/ directory.",
        "constructor": "CNLogger(instancepfx='session', configpath='configs/log_config.toml')",
        "methods": {
            "initLogger()": "Creates log file in logs/ (e.g., server_tcp_05-11-2026_07-30-00.log) and returns path.",
            "logServer(msg, action='INFO', console=False)": "Appends SERVER log entry; prints via UI if console=True.",
            "logClient(msg, action='INFO', console=False)": "Appends CLIENT log entry; prints via UI if console=True.",
            "logSystem(msg, action='INFO', console=False)": "Appends SYSTEM log entry; prints via UI if console=True.",
            "logWarn(msg, action='WARN', console=True)": "Appends WARN log entry; prints warning to console.",
            "logError(msg, action='ERROR', console=True)": "Appends ERROR log entry; prints error to console.",
        },
        "example": (
            "from cn_logging import CNLogger\n"
            "logger = CNLogger(instancepfx='test_session')\n"
            "logger.initLogger()\n"
            "logger.logServer('Server ready', action='START', console=True)\n"
            "logger.logError('Socket disconnected', action='ERROR')"
        ),
    },
    "common": {
        "title": "common_functions (Socket Utilities)",
        "module": "common_functions",
        "class": "Module functions",
        "description": "Shared socket utility functions and interactive help command for debugging in terminal.",
        "constructor": "N/A",
        "methods": {
            "portFinder()": "Returns 0 to let the OS choose an available dynamic port.",
            "port_reserve(sock, host, port)": "Re-allocates and binds socket to a newly discovered port.",
            "showHelp(command=None)": "Displays formatted documentation for library commands and usage.",
            "help(command=None)": "Alias for showHelp; falls back to standard Python help for external objects.",
        },
        "example": (
            "from common_functions import portFinder, showHelp, help\n"
            "port = portFinder()           # 0\n"
            "showHelp()                    # Displays overview of all library commands\n"
            "showHelp('ServerTCP')         # Explains ServerTCP commands and usage"
        ),
    },
}

# Aliases mapping alternative names to registry keys
COMMAND_ALIASES: dict[str, str] = {
    "tcp": "servertcp",
    "server_tcp": "servertcp",
    "servertcp": "servertcp",
    "client_tcp": "clienttcp",
    "clienttcp": "clienttcp",
    "udp": "serverudp",
    "server_udp": "serverudp",
    "serverudp": "serverudp",
    "client_udp": "clientudp",
    "clientudp": "clientudp",
    "ui": "ui",
    "log": "cnlogger",
    "logging": "cnlogger",
    "cn_logging": "cnlogger",
    "cnlogger": "cnlogger",
    "common": "common",
    "common_functions": "common",
    "commonf": "common",
}

# Method-level lookup mapping method name to (registry_key, method_signature)
METHOD_LOOKUP: dict[str, tuple[str, str]] = {
    "setupsockets": ("servertcp", "setupSockets()"),
    "bindsockets": ("servertcp", "bindSockets(port=None, maxretries=3)"),
    "announceport": ("servertcp", "announcePort(interval=1.0)"),
    "acceptconnection": ("servertcp", "acceptConnection(maxretries=3)"),
    "switchport": ("servertcp", "switchPort()"),
    "discoverserver": ("clienttcp", "discoverServer(pingmsg='DISCOVER_TCP', maxretries=3)"),
    "setupsocket": ("clienttcp", "setupSocket()"),
    "connectserver": ("clienttcp", "connectServer(host=None, port=None, maxretries=3)"),
    "bindsocket": ("serverudp", "bindSocket(port=None, maxretries=3)"),
    "senddata": ("servertcp", "sendData(conn, data, maxretries=3)"),
    "receivedata": ("servertcp", "receiveData(conn, buffersize=1024, maxretries=3)"),
    "closesocket": ("servertcp", "closeSocket(maxretries=3)"),
    "portfinder": ("common", "portFinder()"),
    "port_reserve": ("common", "port_reserve(sock, host, port)"),
}

def _printHeader(title: str):
    width = 72
    border = "=" * width
    print(f"\n{CYAN}{BOLD}+{border}+{RESET}")
    print(f"{CYAN}{BOLD}|  {title:<{width - 2}}|{RESET}")
    print(f"{CYAN}{BOLD}+{border}+{RESET}")

def _printSection(title: str, content: str = ""):
    print(f"\n{YELLOW}{BOLD}>> {title}:{RESET}")
    if content:
        print(f"  {content}")

def _printOverview():
    _printHeader("Computer Network Socket Library (v1) - Command Guide")
    print(f"  {GRAY}Interactive command helper for debugging sockets straight out of the terminal.{RESET}\n")

    print(f"{BOLD}AVAILABLE MODULES & CLASSES:{RESET}")
    items = [
        ("ServerTCP", "server.TCP", "TCP stream server with UDP LBA (255.255.255.255:9999) dynamic port broadcast."),
        ("ClientTCP", "client.TCP", "TCP stream client with UDP broadcast auto-discovery on port 9999."),
        ("ServerUDP", "server.UDP", "Fixed-port (8888) UDP server with configurable timeout_period detection."),
        ("ClientUDP", "client.UDP", "Fixed-port (8888) UDP client for datagram messaging."),
        ("UI", "UI", "Colorized status messaging helper (serverMsg, clientMsg, systemMsg, etc.)."),
        ("CNLogger", "cn_logging", "Instance-based session logger outputting to logs/ directory."),
        ("common_functions", "common_functions", "Utility functions: portFinder, port_reserve, and showHelp/help."),
    ]

    for name, mod, desc in items:
        print(f"  {GREEN}{BOLD}{name:<18}{RESET} {GRAY}({mod}){RESET}")
        print(f"    {desc}\n")

    print(f"{BOLD}QUICK DEBUG WORKFLOWS:{RESET}")
    print(f"  {CYAN}1. TCP Server & Client Discovery:{RESET}")
    print(f"     {GRAY}Terminal 1:{RESET} python -c \"from server.TCP import ServerTCP; s = ServerTCP(); s.setupSockets(); s.bindSockets(); s.announcePort(0); conn, _ = s.acceptConnection(); print(s.receiveData(conn)); s.closeSocket()\"")
    print(f"     {GRAY}Terminal 2:{RESET} python -c \"from client.TCP import ClientTCP; c = ClientTCP(); c.discoverServer(); c.setupSocket(); c.connectServer(); c.sendData('ping'); c.closeSocket()\"\n")

    print(f"  {CYAN}2. UDP Server & Client with Timeout:{RESET}")
    print(f"     {GRAY}Terminal 1:{RESET} python -c \"from server.UDP import ServerUDP; s = ServerUDP(timeout_period=5); s.setupSocket(); s.bindSocket(); print(s.receiveData()); s.closeSocket()\"")
    print(f"     {GRAY}Terminal 2:{RESET} python -c \"from client.UDP import ClientUDP; c = ClientUDP(); c.setupSocket(); c.sendData('ping'); c.closeSocket()\"\n")

    print(f"{BOLD}USAGE & HELP COMMANDS:{RESET}")
    print(f"  * In Python REPL / Script:   {GREEN}from common_functions import showHelp; showHelp('ServerTCP'){RESET}")
    print(f"  * Straight from Terminal:    {GREEN}python script/lib/v1/common_functions.py ServerTCP{RESET}")
    print(f"  * Specific method details:   {GREEN}showHelp('announcePort'){RESET} or {GREEN}showHelp('discoverServer'){RESET}\n")

def _printCommandHelp(key: str):
    info = COMMAND_REGISTRY[key]
    _printHeader(f"{info['title']} - Command Details")
    print(f"  {GRAY}Module: {info['module']} | Class: {info['class']}{RESET}")
    print(f"  {info['description']}")

    _printSection("Constructor", f"{BOLD}{info['constructor']}{RESET}")

    _printSection("Key Methods")
    for method, desc in info["methods"].items():
        print(f"  - {GREEN}{BOLD}{method}{RESET}")
        print(f"    {desc}")

    _printSection("Terminal Debugging Example")
    for line in info["example"].splitlines():
        print(f"  {CYAN}{line}{RESET}")
    print()

def _printMethodHelp(key: str, method_sig: str):
    info = COMMAND_REGISTRY[key]
    _printHeader(f"Method: {method_sig} ({info['title']})")
    print(f"  {GRAY}Module: {info['module']} | Class: {info['class']}{RESET}")
    desc = info["methods"].get(method_sig, "No specific method documentation found.")
    _printSection("Description", desc)

    _printSection("Example in Context")
    for line in info["example"].splitlines():
        print(f"  {CYAN}{line}{RESET}")
    print()

def showHelp(command: object = None):
    """
    Explains socket library commands, methods, and debugging workflows.
    Can be invoked from Python REPL or CLI terminal.

    Usage:
        showHelp()                    # Prints full library overview
        showHelp("ServerTCP")         # Explains ServerTCP methods & debugging snippet
        showHelp("announcePort")      # Explains specific method
        showHelp("ClientUDP")         # Explains UDP client usage
    """
    if command is None or str(command).strip() == "" or str(command).lower() in ("help", "--help", "-h", "all"):
        _printOverview()
        return

    # Extract target name if user passed class/function object directly
    if hasattr(command, "__name__"):
        query = command.__name__.lower().strip()
    else:
        query = str(command).lower().strip()

    # Normalize queries like "servertcp.announceport"
    if "." in query:
        cls_part, method_part = query.split(".", 1)
        if method_part in METHOD_LOOKUP:
            reg_key, sig = METHOD_LOOKUP[method_part]
            _printMethodHelp(reg_key, sig)
            return

    # Direct match in registry or aliases
    if query in COMMAND_REGISTRY:
        _printCommandHelp(query)
        return
    if query in COMMAND_ALIASES:
        _printCommandHelp(COMMAND_ALIASES[query])
        return

    # Direct match in method lookup
    clean_method = query.replace("()", "")
    if clean_method in METHOD_LOOKUP:
        reg_key, sig = METHOD_LOOKUP[clean_method]
        _printMethodHelp(reg_key, sig)
        return

    # Fuzzy match on registry keys or method names
    matched = [k for k in COMMAND_REGISTRY if query in k]
    if matched:
        _printCommandHelp(matched[0])
        return

    # Fallback to standard Python help
    print(f"{YELLOW}No custom library entry for '{command}'. Falling back to standard pydoc help:{RESET}\n")
    pydoc.help(command)

def help(command: object = None):
    """
    Convenience alias for showHelp().
    When called without arguments, displays library command reference.
    When given a non-string or unknown library object, delegates to Python built-in help.
    """
    if command is None:
        showHelp()
    elif isinstance(command, str) and (command.lower().strip() in COMMAND_REGISTRY or command.lower().strip() in COMMAND_ALIASES or command.lower().strip().replace("()", "") in METHOD_LOOKUP):
        showHelp(command)
    elif hasattr(command, "__name__") and command.__name__.lower() in COMMAND_ALIASES:
        showHelp(command.__name__)
    else:
        try:
            showHelp(command)
        except Exception:
            pydoc.help(command)

if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else None
    showHelp(target)
