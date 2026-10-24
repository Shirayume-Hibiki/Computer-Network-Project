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

from client.UDP import ClientUDP
from UI import UI as ui

def main():
    ui.systemMsg("Initializing UDP test client...", action = "START")
    client = ClientUDP()
    client.setupSocket()
    ui.clientMsg(f"Configured to communicate with UDP server at {client.host}:{client.port}.", action = "CONFIG")

    testmessages = [
        "Hello UDP Server! Datagram 1.",
        "Testing packet transmission.",
        "Final test datagram."
    ]

    for msg in testmessages:
        ui.clientMsg(f"Sending datagram: '{msg}'", action = "SEND")
        sent = client.sendData(msg)
        if not sent:
            ui.errorMsg("Failed to send datagram.")
            break

        data, serveraddr = client.receiveData()
        if data:
            decoded = data.decode("utf-8", errors="ignore").strip()
            ui.clientMsg(f"Reply from {serveraddr}: '{decoded}'", action = "RESPONSE")
        else:
            ui.warningMsg("No reply received from server.")

        time.sleep(0.5)

    client.closeSocket()
    ui.systemMsg("UDP client finished test successfully.", action = "FINISH")

if __name__ == "__main__":
    main()
