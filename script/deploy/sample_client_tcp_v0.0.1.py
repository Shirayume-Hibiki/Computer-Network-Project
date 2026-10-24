'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Shirayume_Hibiki          ║
║  Creation date:            24/10/26                  ║
║  Edit dates / contributor:                           ║
╚══════════════════════════════════════════════════════╝
'''

import os
import sys
import time

sys.path.append(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib", "v1"))

from client.TCP import ClientTCP
from UI import UI as ui

def main():
    ui.systemMsg("Initializing TCP test client...", action = "START")
    client = ClientTCP()

    # 1. Discover TCP server dynamic port via discovery UDP port 9999
    ui.clientMsg("Discovering server TCP port...", action = "DISCOVERY")
    result = client.discoverServer()
    if result is None:
        ui.errorMsg("Could not discover server. Ensure sample_server_tcp is running.")
        return

    host, port = result
    ui.clientMsg(f"Discovered server at {host}:{port}.", action = "DISCOVERY")

    # 2. Setup socket and connect to server
    client.setupSocket()
    connected = client.connectServer()
    if not connected:
        ui.errorMsg(f"Failed to connect to TCP server at {host}:{port}.")
        client.closeSocket()
        return

    # 3. Send test payload messages and receive replies
    testmessages = [
        "Hello Server! Connection verified.",
        "Ping test from ClientTCP.",
        "Testing multiple data transfers.",
        "quit"
    ]

    for msg in testmessages:
        ui.clientMsg(f"Sending: '{msg}'", action = "SEND")
        sent = client.sendData(msg)
        if not sent:
            ui.errorMsg("Failed to send message.")
            break

        reply = client.receiveData()
        if reply:
            decoded = reply.decode("utf-8", errors="ignore").strip()
            ui.clientMsg(f"Server response: '{decoded}'", action = "RESPONSE")
        else:
            ui.warningMsg("No reply received from server.")
            break

        time.sleep(0.5)

    # 4. Clean shutdown
    client.closeSocket()
    ui.systemMsg("TCP client finished test successfully.", action = "FINISH")

if __name__ == "__main__":
    main()
