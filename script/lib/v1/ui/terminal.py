'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Shirayume-Hibiki          ║
║  Creation date:            12/11/26                  ║
║  Edit dates / contributor:                           ║
╚══════════════════════════════════════════════════════╝
'''

import os
import sys
import threading
import time

# Enable ANSI escape processing in Windows console
if os.name == "nt":
    os.system("")

try:
    import msvcrt
    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False

class TerminalUI:
    def __init__(self, prompt: str = "> "):
        self.prompt = prompt
        self._lock = threading.Lock()
        self._input_buffer: list[str] = []
        self._is_interactive = sys.stdin.isatty() and sys.stdout.isatty()

    def setPrompt(self, prompt: str) -> None:
        with self._lock:
            self.prompt = prompt
            self._redrawPrompt()

    def printLine(self, text: str) -> None:
        """Print a line while preserving currently typed user input."""
        with self._lock:
            if self._is_interactive:
                current_input = "".join(self._input_buffer)
                # Clear current line
                sys.stdout.write("\r\033[K")
                # Print message
                sys.stdout.write(f"{text}\n")
                # Redraw prompt and buffered input
                sys.stdout.write(f"{self.prompt}{current_input}")
                sys.stdout.flush()
            else:
                sys.stdout.write(f"{text}\n")
                sys.stdout.flush()

    def _redrawPrompt(self) -> None:
        if self._is_interactive:
            current_input = "".join(self._input_buffer)
            sys.stdout.write("\r\033[K")
            sys.stdout.write(f"{self.prompt}{current_input}")
            sys.stdout.flush()

    def readLine(self) -> str:
        """Read a line from user input interactively without breaking output."""
        if not self._is_interactive or not HAS_MSVCRT:
            try:
                sys.stdout.write(self.prompt)
                sys.stdout.flush()
                return sys.stdin.readline().strip()
            except (EOFError, KeyboardInterrupt):
                return "/quit"

        with self._lock:
            self._input_buffer = []
            self._redrawPrompt()

        while True:
            # Polling kbhit with small sleep to yield CPU
            while not msvcrt.kbhit():
                time.sleep(0.02)

            ch = msvcrt.getwch()

            with self._lock:
                if ch in ("\r", "\n"):
                    line = "".join(self._input_buffer)
                    self._input_buffer = []
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    return line.strip()

                elif ch in ("\x08", "\x7f"):  # Backspace
                    if self._input_buffer:
                        self._input_buffer.pop()
                        self._redrawPrompt()

                elif ch == "\x03":  # Ctrl+C
                    sys.stdout.write("\n")
                    sys.stdout.flush()
                    return "/quit"

                elif ch == "\x04":  # Ctrl+D
                    return "/quit"

                elif ch in ("\x00", "\xe0"):  # Special arrow / function keys
                    msvcrt.getwch()  # Consume the scan code byte
                    continue

                else:
                    self._input_buffer.append(ch)
                    self._redrawPrompt()
