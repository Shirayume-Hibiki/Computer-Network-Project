'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Shirayume_Hibiki          ║
║  Creation date:            24/10/26                  ║
║  Edit dates / contributor:                           ║
╚══════════════════════════════════════════════════════╝
'''

import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib", "v1"))

from server.UDP import ServerUDP
from UI import UI as ui

def main():
    ui.systemMsg("Initializing UDP test server...", action = "START")
    server = ServerUDP()
    server.setupSocket()
    bound = server.bindSocket()
    if bound is None:
        ui.errorMsg("Failed to bind UDP server socket.")
        return

    ui.systemMsg(f"UDP server listening on fixed port {server.port}. Press Ctrl+C to stop.", action = "READY")

    try:
        while True:
            data, clientaddr = server.receiveData()
            if data and clientaddr is not None:
                message = data.decode("utf-8", errors="ignore").strip()
                ui.serverMsg(f"Received datagram from {clientaddr}: '{message}'", action = "RECEIVE")

                reply = f"UDP_ACK: {message}"
                server.sendData(clientaddr, reply)
    except KeyboardInterrupt:
        ui.systemMsg("Interrupt received. Stopping UDP server...", action = "STOP")
    finally:
        server.closeSocket()
        ui.systemMsg("UDP server stopped.", action = "STOP")

if __name__ == "__main__":
    main()
