'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Shirayume-Hibiki          ║
║  Creation date:            12/11/26                  ║
║  Edit dates / contributor:                           ║
╚══════════════════════════════════════════════════════╝
'''

import os
import sys
import time

from peer.peer_node import PeerNode
from ui.terminal import TerminalUI

def formatProgressBar(percentage: float, width: int = 20) -> str:
    filled = int(width * (percentage / 100.0))
    filled = max(0, min(width, filled))
    bar = "=" * filled + (">" if filled < width else "")
    return f"[{bar.ljust(width)}]"

class CliHandler:
    def __init__(self, node: PeerNode):
        self.node = node
        self.ui = TerminalUI(prompt=f"[{node.name}] > ")
        self._wireCallbacks()

    def _wireCallbacks(self) -> None:
        self.node.on_message = self._handleIncomingMessage
        self.node.on_file_progress = self._handleFileProgress
        self.node.on_file_complete = self._handleFileComplete
        self.node.on_file_error = self._handleFileError
        self.node.on_notice = self._handleNotice

    def _handleIncomingMessage(self, sender: str, text: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        self.ui.printLine(f"[{timestamp}] <{sender}>: {text}")

    def _handleFileProgress(self, filename: str, done: int, total: int, pct: float, is_upload: bool) -> None:
        direction = "Upload" if is_upload else "Download"
        bar = formatProgressBar(pct, width=20)
        line = f"[{direction}] {filename} {bar} {pct:5.1f}% ({done}/{total} bytes)"
        self.ui.printLine(line)

    def _handleFileComplete(self, filename: str, path: str, is_upload: bool) -> None:
        if is_upload:
            self.ui.printLine(f"[Transfer] File '{filename}' successfully sent!")
        else:
            self.ui.printLine(f"[Transfer] File '{filename}' successfully received and saved to: {path}")

    def _handleFileError(self, filename: str, err: str) -> None:
        self.ui.printLine(f"[Transfer Error] {filename}: {err}")

    def _handleNotice(self, msg: str) -> None:
        self.ui.printLine(f"[*] {msg}")

    def displayHelp(self) -> None:
        help_text = (
            "\n"
            "+-------------------------------------------------------------------------+\n"
            "|                          AVAILABLE LAN CHAT COMMANDS                    |\n"
            "+-------------------------------------------------------------------------+\n"
            "| /list                   : Show all active peers on the LAN              |\n"
            "| /chat <username|index>  : Connect and start a 1-to-1 chat session       |\n"
            "| <message text>          : Send text message to the currently active peer|\n"
            "| /send <filepath>        : Send a file to the currently active peer      |\n"
            "| /leave                  : Disconnect from the current chat session      |\n"
            "| /status <online|away>   : Change your presence status                   |\n"
            "| /help                   : Display this command reference                |\n"
            "| /quit                   : Disconnect, broadcast goodbye, and exit       |\n"
            "+-------------------------------------------------------------------------+"
        )
        self.ui.printLine(help_text)

    def displayPeerList(self) -> None:
        peers = self.node.peer_table.getActivePeers()
        if not peers:
            self.ui.printLine("[*] No active peers found on LAN yet. Waiting for beacons...")
            return

        now = time.time()
        lines = [
            "\n+-----+----------------------+----------------------+---------+------------+",
            "| #   | Username             | IP Address : Port    | Status  | Last Seen  |",
            "+-----+----------------------+----------------------+---------+------------+",
        ]
        for idx, peer in enumerate(peers, start=1):
            elapsed = int(now - peer.last_seen)
            last_seen_str = f"{elapsed}s ago"
            addr_str = f"{peer.ip}:{peer.port}"
            lines.append(f"| {idx:<3} | {peer.name:<20} | {addr_str:<20} | {peer.status:<7} | {last_seen_str:<10} |")
        lines.append("+-----+----------------------+----------------------+---------+------------+")
        self.ui.printLine("\n".join(lines))

    def run(self) -> None:
        self.ui.printLine(f"\n=======================================================")
        self.ui.printLine(f"  LAN Chat P2P Node Started")
        self.ui.printLine(f"  User: {self.node.name} | TCP Port: {self.node.tcp_port} | Status: {self.node.status}")
        self.ui.printLine(f"  Type /help for available commands or /list to see peers.")
        self.ui.printLine(f"=======================================================\n")

        while self.node.running:
            try:
                # Update prompt dynamically
                if self.node.active_peer_name:
                    self.ui.setPrompt(f"[{self.node.name} -> {self.node.active_peer_name}] > ")
                else:
                    self.ui.setPrompt(f"[{self.node.name}] > ")

                cmd_line = self.ui.readLine()
                if not cmd_line:
                    continue

                if cmd_line.startswith("/"):
                    parts = cmd_line.split(maxsplit=1)
                    cmd = parts[0].lower()
                    arg = parts[1].strip() if len(parts) > 1 else ""

                    if cmd == "/quit":
                        self.ui.printLine("[*] Exiting LAN Chat...")
                        break
                    elif cmd == "/help":
                        self.displayHelp()
                    elif cmd == "/list":
                        self.displayPeerList()
                    elif cmd == "/chat":
                        if not arg:
                            self.ui.printLine("Usage: /chat <username|index>")
                        else:
                            self.node.connectToPeer(arg)
                    elif cmd == "/leave":
                        self.node.leaveChat()
                    elif cmd == "/send":
                        if not arg:
                            self.ui.printLine("Usage: /send <filepath>")
                        else:
                            self.node.sendFile(arg)
                    elif cmd == "/status":
                        if arg in ("online", "away"):
                            self.node.setStatus(arg)
                            self.ui.printLine(f"[*] Status set to {arg}.")
                        else:
                            self.ui.printLine("Usage: /status <online|away>")
                    else:
                        self.ui.printLine(f"Unknown command '{cmd}'. Type /help for assistance.")
                else:
                    # Regular chat message
                    if self.node.active_sock:
                        self.node.sendMessage(cmd_line)
                    else:
                        self.ui.printLine("[!] Not in a chat session. Use /chat <username|index> to connect, or /list to find peers.")

            except (KeyboardInterrupt, EOFError):
                break
            except Exception as e:
                self.ui.printLine(f"[!] Error: {e}")

        # Shutdown node
        self.node.stop()
        self.ui.printLine("[*] Goodbye!")
