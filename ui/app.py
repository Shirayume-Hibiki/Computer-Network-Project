from textual.app import App, ComposeResult
from textual.widgets import Static

class ChatApplication(App):
    def compose(self) -> ComposeResult:
        yield Static("⸜(｡˃ ᵕ ˂ )⸝♡")

