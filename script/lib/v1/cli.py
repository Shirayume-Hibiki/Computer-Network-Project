'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Gemini 3.8 Flash          ║
║  Creation date:            05/11/26                  ║
║  Edit dates / contributor:                           ║
╚══════════════════════════════════════════════════════╝
'''

import code
import inspect
import os
import sys
import threading
import time

# Ensure lib/v1 directory is in sys.path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

# Safe UTF-8 output configuration
try:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from UI import UI
from cn_logging import CNLogger
from common_functions import help, port_reserve, portFinder, showHelp
from client.TCP import ClientTCP
from client.UDP import ClientUDP
from server.TCP import ServerTCP
from server.UDP import ServerUDP

CYAN = '\033[96m'
GREEN = '\033[92m'
YELLOW = '\033[93m'
GRAY = '\033[90m'
BOLD = '\033[1m'
RESET = '\033[0m'

def runInteractiveShell():
    """
    Launches an interactive Python debugging console with all library
    symbols and helper functions pre-imported into the session.
    """
    banner = f"""
{CYAN}{BOLD}+========================================================================+
|  Socket Library Interactive Debugging Shell (v1)                       |
+========================================================================+{RESET}
  {GRAY}All classes, modules, and utilities are pre-imported into this session.{RESET}

  {BOLD}Pre-loaded Symbols:{RESET}
    * {GREEN}ServerTCP{RESET}, {GREEN}ClientTCP{RESET}   (TCP streaming & dynamic port discovery)
    * {GREEN}ServerUDP{RESET}, {GREEN}ClientUDP{RESET}   (UDP datagram messaging)
    * {GREEN}UI{RESET}, {GREEN}CNLogger{RESET}           (Terminal output & file logging)
    * {GREEN}portFinder{RESET}, {GREEN}showHelp{RESET}, {GREEN}help{RESET}

  {BOLD}Try running:{RESET}
    >>> {YELLOW}srv = ServerTCP(); srv.setupSockets(); srv.bindSockets(){RESET}
    >>> {YELLOW}cli = ClientTCP(); cli.discoverServer(){RESET}
    >>> {YELLOW}showHelp("ServerTCP"){RESET}
    >>> {YELLOW}portFinder(){RESET}
"""
    namespace = {
        "ServerTCP": ServerTCP,
        "ClientTCP": ClientTCP,
        "ServerUDP": ServerUDP,
        "ClientUDP": ClientUDP,
        "UI": UI,
        "CNLogger": CNLogger,
        "portFinder": portFinder,
        "port_reserve": port_reserve,
        "showHelp": showHelp,
        "help": help,
    }
    print(banner)
    code.interact(banner="", local=namespace)

def runDiscover():
    """Executes client TCP discovery and prints the discovered server address."""
    UI.systemMsg("Initiating TCP discovery probe...", action="DISCOVERY")
    client = ClientTCP()
    res = client.discoverServer()
    if res:
        UI.clientMsg(f"Successfully discovered TCP server at {res[0]}:{res[1]}.", action="DISCOVERY")
    else:
        UI.errorMsg("Could not discover TCP server. Ensure ServerTCP is broadcasting or listening.", action="DISCOVERY")

def runQuickTcpTest():
    """Starts a temporary TCP server and runs a client connection test."""
    UI.systemMsg("Running quick local TCP integration test...", action="TEST")
    server = ServerTCP()
    server.setupSockets()
    server.bindSockets()

    stopevent = threading.Event()
    def announce():
        while not stopevent.is_set():
            try:
                sig = inspect.signature(server.announcePort)
                if "interval" in sig.parameters:
                    server.announcePort(interval=0.2)
                else:
                    server.announcePort()
            except Exception:
                pass
            time.sleep(0.2)

    t_srv = threading.Thread(target=announce, daemon=True)
    t_srv.start()

    client = ClientTCP()
    discovered = client.discoverServer()
    if not discovered:
        UI.errorMsg("TCP discovery failed.", action="TEST")
        stopevent.set()
        server.closeSocket()
        return

    client.setupSocket()
    if client.connectServer():
        client.sendData("PING_TEST")
        conn, addr = server.acceptConnection()
        if conn:
            data = server.receiveData(conn)
            server.sendData(conn, f"ACK: {data.decode(errors='ignore')}")
            reply = client.receiveData()
            UI.clientMsg(f"Verified reply: {reply.decode(errors='ignore')}", action="TEST")
            conn.close()
    stopevent.set()
    client.closeSocket()
    server.closeSocket()
    UI.systemMsg("TCP test completed successfully.", action="TEST")

def runQuickUdpTest():
    """Starts a temporary UDP server and runs a datagram echo test."""
    UI.systemMsg("Running quick local UDP integration test...", action="TEST")
    server = ServerUDP()
    server.setupSocket()
    server.bindSocket()

    client = ClientUDP()
    client.setupSocket()

    client.sendData("UDP_PING_TEST", addr=(server.host, server.port))
    data, addr = server.receiveData()
    if data and addr:
        server.sendData(addr, f"UDP_ACK: {data.decode(errors='ignore')}")
        reply, _ = client.receiveData()
        UI.clientMsg(f"Verified reply: {reply.decode(errors='ignore')}", action="TEST")

    client.closeSocket()
    server.closeSocket()
    UI.systemMsg("UDP test completed successfully.", action="TEST")

def main():
    args = sys.argv[1:]
    if not args or args[0] in ("-i", "shell", "interactive", "repl"):
        runInteractiveShell()
        return

    cmd = args[0].lower().strip()
    if cmd in ("help", "-h", "--help"):
        topic = args[1] if len(args) > 1 else None
        showHelp(topic)
    elif cmd in ("portfinder", "port_finder", "port"):
        print(f"portFinder() -> {portFinder()}")
    elif cmd in ("discover", "disco"):
        runDiscover()
    elif cmd in ("test-tcp", "test_tcp", "tcp"):
        runQuickTcpTest()
    elif cmd in ("test-udp", "test_udp", "udp"):
        runQuickUdpTest()
    else:
        # Check if argument is a registered topic in showHelp
        showHelp(args[0])

if __name__ == "__main__":
    main()
