'''~~~~~~~~~~~~~~~
Creator: Shirayume_Hibiki
Date of creation: 18/10/2026
Edit dates:
~~~~~~~~~~~~~~~'''

import sys
import socket
import time

def portFinder():
    # Calling port 0 will let the OS find an available port for us
    return 0

def port_reserve(sock, host, port):
    # This function will switch the port if the current port is not available
    new_port = portFinder()
    print(f"Switching to new port: {new_port}")
    sock.close()
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((host, new_port))
    return sock
