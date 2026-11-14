'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Shirayume-Hibiki          ║
║  Creation date:            12/11/26                  ║
║  Edit dates / contributor:                           ║
╚══════════════════════════════════════════════════════╝
'''

import argparse
import os
import sys

# Ensure script/lib/v1 is on python search path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, "..", ".."))
LIB_V1_DIR = os.path.join(PROJECT_ROOT, "script", "lib", "v1")

if LIB_V1_DIR not in sys.path:
    sys.path.insert(0, LIB_V1_DIR)

from peer.peer_node import PeerNode
from ui.cli_handler import CliHandler

def parseArguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LAN Chat & File Sharing - P2P Node")
    parser.add_argument("--name", "-n", type=str, default="", help="Your display name on the LAN")
    parser.add_argument("--port", "-p", type=int, default=0, help="TCP port to listen on for peer chat (0 for random)")
    parser.add_argument("--discovery-port", "-d", type=int, default=9999, help="UDP port used for peer discovery (default 9999)")
    parser.add_argument("--downloads", type=str, default=os.path.join(PROJECT_ROOT, "downloads"), help="Directory to save received files")
    parser.add_argument("--status", "-s", type=str, choices=["online", "away"], default="online", help="Initial status (default 'online')")
    return parser.parse_args()

def main() -> None:
    # Ensure stdout handles UTF-8 smoothly on Windows
    if sys.stdout.encoding and sys.stdout.encoding.lower() not in ("utf-8", "utf8"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    args = parseArguments()
    name = args.name.strip()
    while not name:
        try:
            name = input("Enter your username: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nExiting.")
            sys.exit(0)

    node = PeerNode(
        name=name,
        tcp_port=args.port,
        discovery_port=args.discovery_port,
        downloads_dir=args.downloads,
        status=args.status,
    )

    try:
        node.start()
        cli = CliHandler(node)
        cli.run()
    except KeyboardInterrupt:
        node.stop()
        print("\nLAN Chat stopped.")
    except Exception as e:
        print(f"\nFatal error: {e}")
        node.stop()
        sys.exit(1)

if __name__ == "__main__":
    main()
