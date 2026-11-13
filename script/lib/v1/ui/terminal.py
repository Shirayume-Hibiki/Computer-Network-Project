'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Shirayume-Hibiki          ║
║  Creation date:            12/11/26                  ║
║  Edit dates / contributor:                           ║
║  13/11/26 Shirayume-Hibiki                           ║
╚══════════════════════════════════════════════════════╝
'''

import os
import sys
import threading
import time

try:
    import msvcrt
    HAS_MSVCRT = True
except ImportError:
    HAS_MSVCRT = False

try:
    import select
    import termios
    import tty
    HAS_TERMIOS = True
except ImportError:
    HAS_TERMIOS = False

# Enable ANSI escape processing in Windows console
if os.name == "nt":
    os.system("")

class TerminalUI:
    def __init__(self, prompt: str = "> ", ansi_enabled: bool = True):
        self.prompt = prompt
        self.ansi_enabled = ansi_enabled
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
            if self._is_interactive and self.ansi_enabled:
                current_input = "".join(self._input_buffer)
                # Clear current visual line
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
        if self._is_interactive and self.ansi_enabled:
            current_input = "".join(self._input_buffer)
            sys.stdout.write("\r\033[K")
            sys.stdout.write(f"{self.prompt}{current_input}")
            sys.stdout.flush()

    def readLine(self) -> str:
        """Read a line from user input interactively across Windows, Linux, and macOS."""
        if not self._is_interactive:
            try:
                sys.stdout.write(self.prompt)
                sys.stdout.flush()
                return sys.stdin.readline().strip()
            except (EOFError, KeyboardInterrupt):
                return "/quit"

        if HAS_MSVCRT:
            return self._readLineWindows()
        elif HAS_TERMIOS:
            return self._readLinePosix()
        else:
            try:
                sys.stdout.write(self.prompt)
                sys.stdout.flush()
                return sys.stdin.readline().strip()
            except (EOFError, KeyboardInterrupt):
                return "/quit"

    def _readLineWindows(self) -> str:
        with self._lock:
            self._input_buffer = []
            self._redrawPrompt()

        while True:
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

                elif ch in ("\x00", "\xe0"):  # Arrow / function key prefix
                    msvcrt.getwch()  # Consume scan code
                    continue

                else:
                    self._input_buffer.append(ch)
                    self._redrawPrompt()

    def _readLinePosix(self) -> str:
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setcbreak(fd)
            with self._lock:
                self._input_buffer = []
                self._redrawPrompt()

            while True:
                rlist, _, _ = select.select([sys.stdin], [], [], 0.02)
                if not rlist:
                    continue

                ch = sys.stdin.read(1)
                with self._lock:
                    if ch in ("\r", "\n"):
                        line = "".join(self._input_buffer)
                        self._input_buffer = []
                        sys.stdout.write("\n")
                        sys.stdout.flush()
                        return line.strip()

                    elif ch in ("\x08", "\x7f"):  # Backspace / DEL
                        if self._input_buffer:
                            self._input_buffer.pop()
                            self._redrawPrompt()

                    elif ch == "\x03":  # Ctrl+C
                        sys.stdout.write("\n")
                        sys.stdout.flush()
                        return "/quit"

                    elif ch == "\x04":  # Ctrl+D
                        return "/quit"

                    elif ch == "\x1b":  # Escape sequence prefix
                        if select.select([sys.stdin], [], [], 0.01)[0]:
                            sys.stdin.read(2)
                        continue

                    else:
                        self._input_buffer.append(ch)
                        self._redrawPrompt()
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
