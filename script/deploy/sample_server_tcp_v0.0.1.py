'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Shirayume_Hibiki          ║
║  Creation date:            24/10/26                  ║
║  Edit dates / contributor:                           ║
╚══════════════════════════════════════════════════════╝
'''

import os
import sys
import threading
import time

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib", "v1"))

from server.TCP import ServerTCP
from UI import UI as ui

def handleClient(server: ServerTCP, conn, addr: tuple[str, int]):
    ui.serverMsg(f"Client thread started for {addr}", action = "SESSION")
    try:
        while True:
            data = server.receiveData(conn)
            if not data:
                break
            message = data.decode("utf-8", errors="ignore").strip()
            ui.serverMsg(f"Received from {addr}: '{message}'", action = "RECEIVE")

            reply = f"ACK: {message}"
            server.sendData(conn, reply)

            if message.lower() == "quit":
                break
    except Exception as err:
        ui.errorMsg(f"Client {addr} handler exception: {err}")
    finally:
        conn.close()
        ui.serverMsg(f"Closed connection with {addr}", action = "DISCONNECT")

def runDiscovery(server: ServerTCP, stopevent: threading.Event):
    if server.discovery is not None:
        server.discovery.settimeout(1.0)
    while not stopevent.is_set():
        server.announcePort()

def main():
    ui.systemMsg("Initializing TCP test server...", action = "START")
    server = ServerTCP()
    server.setupSockets()
    server.bindSockets()

    stopevent = threading.Event()
    discthread = threading.Thread(target=runDiscovery, args=(server, stopevent), daemon=True)
    discthread.start()
    ui.systemMsg("Discovery listener active on UDP port 9999.", action = "DISCOVERY")
    ui.systemMsg(f"Server listening on TCP port {server.port}. Press Ctrl+C to stop.", action = "READY")

    try:
        while True:
            conn, addr = server.acceptConnection()
            if conn is not None and addr is not None:
                clientthread = threading.Thread(target=handleClient, args=(server, conn, addr), daemon=True)
                clientthread.start()
    except KeyboardInterrupt:
        ui.systemMsg("Interrupt received. Stopping TCP server...", action = "STOP")
    finally:
        stopevent.set()
        server.closeSocket()
        ui.systemMsg("TCP server stopped.", action = "STOP")

if __name__ == "__main__":
    main()
