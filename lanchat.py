'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  diamboy                   ║
║  Creation date:            28/11/26                  ║
║  Edit dates / contributor:                           ║
╚══════════════════════════════════════════════════════╝
'''

import argparse
import random

from backend.data_types import BackendConfig
from backend import PeerBackend
from mock_backend import MockPeerBackend
from ui import ChatApplication

desc = "Chateaubriand: LAN chat application built using Textual."

def anon_name():
    LENGTH = 6
    return f"Anon #{str(random.randrange(0, 10**LENGTH)).rjust(LENGTH, '0')}"

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument("-n", "--name")
    parser.add_argument("-p", "--port", default="0")
    parser.add_argument("-s", "--status", default="online")
    parser.add_argument("-m", "--mock", action="store_true")

    args = parser.parse_args()
    name: str = args.name if args.name else anon_name()
    port: int = 0
    mock: bool = args.mock
    try:
        port = int(args.port)
    except ValueError:
        pass
    if not 0 <= port < 65536:
        port = 0
    config: BackendConfig = BackendConfig(
            name=name,
            tcp_port=port)
    app = ChatApplication(MockPeerBackend if mock else PeerBackend, config)
    app.run()
