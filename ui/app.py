'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  diamboy                   ║
║  Creation date:            28/11/26                  ║
║  Edit dates / contributor:                           ║
╚══════════════════════════════════════════════════════╝
'''

import dataclasses
import queue
import textwrap
import typing
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from textual import events, markup, on, work
from textual.app import App, ComposeResult
from textual.containers import (
    Horizontal,
    HorizontalGroup,
    HorizontalScroll,
    Vertical,
    VerticalGroup,
    VerticalScroll,
)
from textual.message import Message
from textual.timer import Timer
from textual.widgets import (
    Button,
    ContentSwitcher,
    Footer,
    Header,
    ListItem,
    ListView,
    ProgressBar,
    RichLog,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
)

from backend.data_types import (
    BackendConfig,
    BackendError,
    BackendEvent,
    LogLevel,
    MessageReceived,
    PeerAddress,
    PeerChanged,
    PeerConnected,
    PeerDisconnected,
    PeerInfo,
    PeerOffline,
    PeerOnline,
    TransferFailed,
    TransferFinished,
    TransferProgress,
)

SYSTEM_NAME = "[bold]SYSTEM[/bold]"

class DiscoveryEntry(ListItem):
    _text: Static
    _scroll: HorizontalScroll
    _scroll_stop: bool
    _curr_timer: Timer | None
    peer: PeerInfo

    def __init__(self, peer: PeerInfo):
        super().__init__()
        self._text = Static()
        self._scroll = HorizontalScroll(self._text)
        self._scroll_stop = False
        self._curr_timer = None
        self.peer = peer;
        self.set_text(peer)

    def set_text(self, peer: PeerInfo):
        self._text.update(f"{markup.escape(peer.name)} | {markup.escape(peer.status)}")
    def compose(self) -> ComposeResult:
        yield self._scroll

    def _delay_helper(self, sec: float, cb) -> Callable[[], None]:
        def a():
            self._curr_timer = self.set_timer(sec, cb)
        return a

    def _scroll1(self) -> None:
        if self._scroll_stop:
            return
        self._scroll.scroll_to(x=self._scroll.max_scroll_x,
                               speed=10,
                               easing="linear",
                               force=True,
                               on_complete=self._delay_helper(2, self._scroll2))
    def _scroll2(self) -> None:
        if self._scroll_stop:
            return
        self._scroll.scroll_to(x=0,
                               speed=10,
                               easing="linear",
                               force=True,
                               on_complete=self._delay_helper(2, self._scroll1))
    def scroll_start(self) -> None:
        self._scroll_stop = False
        self._scroll1()
    def scroll_stop(self) -> None:
        self._scroll_stop = True
        if isinstance(self._curr_timer, Timer):
            self._curr_timer.stop()
        self._scroll.scroll_to(x=0,
                               animate=False,
                               force=True,
                               immediate=True)

class ChatMessage(HorizontalGroup):
    author: str
    text: str
    is_ours: bool
    static: Static
    def __init__(self, author: str, text: str, is_ours: bool):
        super().__init__()
        self.author = author
        self.border_title = author
        self.text = text
        self.is_ours = is_ours
        if self.is_ours:
            self.add_class("ours")
        else:
            self.add_class("not-ours")
        self.static = Static(self.text)
        self.static.border_title = self.author
    def compose(self) -> ComposeResult:
        yield self.static

class FileMessage(HorizontalGroup):
    _static: Static
    _progress: ProgressBar
    _vert: VerticalGroup
    def __init__(self, name: str, transfer: TransferProgress | TransferFinished | TransferFailed):
        super().__init__()
        self._static = Static()
        self._progress = ProgressBar()
        self._vert = VerticalGroup(self._static, self._progress)
        self.update(name, transfer)

    def update(self, name: str, transfer: TransferProgress | TransferFinished | TransferFailed) -> None:
        tr = transfer.transfer
        self.set_class(tr.direction == "upload", "ours")
        self.set_class(tr.direction == "download", "not-ours")
        self._vert.border_title = tr.name if tr.direction == "download" else name
        match transfer:
            case TransferProgress(_):
                self._static.update(f"[bold]{markup.escape(tr.filename)}[/bold]\n{tr.bytes_transferred}/{tr.bytes_total}")
                self._progress.progress = tr.bytes_transferred
                self._progress.total = tr.bytes_total
            case TransferFinished(_):
                if tr.direction == "download":
                    path: Path = typing.cast(Path, tr.saved_path)
                    self._static.update(f"[bold]{markup.escape(tr.filename)}\nSaved at: [/bold]{markup.escape(str(path))}\n{tr.bytes_total}")
                else:
                    self._static.update(f"[bold]{markup.escape(tr.filename)}[/bold]\n{tr.bytes_total}")
            case TransferFailed(_):
                self._static.update(f"[bold]{markup.escape(tr.filename)}\nFAILED[/bold]")
                self._progress.total = None

    def compose(self) -> ComposeResult:
        yield self._vert

class ChatSendReq(Message):
    pass

class ChatSend(Message):
    text: str
    addr: PeerAddress | None
    def __init__(self, text: str, addr: PeerAddress | None = None):
        super().__init__()
        self.text = text
        self.addr = addr

class DisconnectReq(Message):
    addr: PeerAddress
    def __init__(self, addr: PeerAddress):
        super().__init__()
        self.addr = addr

class CloseReq(Message):
    addr: PeerAddress
    def __init__(self, addr: PeerAddress):
        super().__init__()
        self.addr = addr

class FileSendReq(Message):
    addr: PeerAddress
    path: str | Path
    def __init__(self, addr: PeerAddress, path: str | Path):
        super().__init__()
        self.addr = addr
        self.path = path

class ChatTextArea(TextArea):
    def on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            self.post_message(ChatSendReq())
            event.prevent_default()
        if event.key == "shift+enter":
            self.insert('\n')
            event.prevent_default()

class ChatTab(Vertical):
    _chat_log: VerticalScroll
    _chat: ChatTextArea
    _name: str
    _addr: PeerAddress | None
    _mute: bool
    _transfers: dict[UUID, FileMessage]
    def __init__(self, addr: PeerAddress | None, name: str, mute: bool = False):
        super().__init__()
        self._chat_log = VerticalScroll(id="chat-log")
        self._chat_log.anchor()
        self._chat = ChatTextArea(id="chat-box")
        self._send = Button("⏎", id="chat-send")
        self._name = name
        self._addr = addr
        self._mute = mute
        self._transfers = {}
    def append_peer_message(self, ev: MessageReceived) -> None:
        self._chat_log.mount(ChatMessage(markup.escape(ev.name),
                                         markup.escape(ev.text), False))
    def append_system_message(self, title: str, text: str) -> None:
        self._chat_log.mount(ChatMessage(title, text, False))

    @on(ChatSendReq)
    def _send_message1(self) -> None:
        self.send_message()

    @on(Button.Pressed, "#chat-send")
    def _send_message2(self) -> None:
        self.send_message()

    def send_message(self) -> None:
        text = self._chat.text
        if text.startswith('/'):
            self._chat.clear()
            if text == "/disconnect":
                if self._addr is not None:
                    self.post_message(DisconnectReq(self._addr))
            elif text == "/close":
                if self._addr is not None:
                    self.post_message(CloseReq(self._addr))
            elif text.startswith("/sendfile "):
                if self._addr is not None:
                    self.post_message(FileSendReq(self._addr, text.removeprefix("/sendfile").strip()))
            else:
                help_text = """\
                        [bold]/help[/bold]: Displays this help message.
                        [bold]/disconnect[/bold]: Disconnects the current peer.
                        [bold]/close[/bold]: Closes the tab if peer is disconnected.
                        [bold]/sendfile[/bold] <file>: Sends a file to the current peer."""
                if text != "/help":
                    self.append_system_message(
                            SYSTEM_NAME,
                            f"Unrecognized command '{markup.escape(text)}'\n\n{textwrap.dedent(help_text)}")
                else:
                    self.append_system_message(SYSTEM_NAME, textwrap.dedent(help_text))
            return
        text = text.strip()
        if len(text) == 0:
            return
        self._chat.clear()
        if not self._mute:
            self._chat_log.mount(ChatMessage(self._name, markup.escape(text), True))
        self.post_message(ChatSend(text, self._addr))

    def update_file_message(self, transfer: TransferProgress | TransferFinished | TransferFailed):
        tr = transfer.transfer
        if tr.transfer_id not in self._transfers:
            fm = FileMessage(self._name, transfer)
            self._transfers[tr.transfer_id] = fm
            self._chat_log.mount(fm)
        else:
            self._transfers[tr.transfer_id].update(self._name, transfer)

    def compose(self) -> ComposeResult:
        yield self._chat_log
        with HorizontalGroup():
            yield self._chat
            yield self._send

@dataclass(frozen=True)
class LogEvent:
    level: LogLevel
    text: str

@dataclass(frozen=True)
class FailConnectEvent:
    addr: PeerAddress
    name: str | None
    tid: str

@dataclass(frozen=True)
class CloseFailedEvent:
    addr: PeerAddress

@dataclass(frozen=True)
class CloseChatEvent:
    addr: PeerAddress

@dataclass(frozen=True)
class FileSendFailEvent:
    addr: PeerAddress
    path: str | Path
    reason: str

AllEvents = (BackendEvent | LogEvent | FailConnectEvent | CloseFailedEvent
             | CloseChatEvent | FileSendFailEvent)
class ChatApplication(App):
    TITLE = "Chateaubriand"
    CSS_PATH = "app.tcss"
    event_queue: queue.SimpleQueue[AllEvents]
    _disc_list_disp: list[PeerInfo]
    _disc_list_curr: list[PeerInfo]
    _disc_high: DiscoveryEntry | None
    _connected: dict[PeerAddress, str]
    _tab_open: dict[PeerAddress, tuple[ChatTab, str]]
    def __init__(self, backend_class, config: BackendConfig):
        super().__init__()
        self.event_queue = queue.SimpleQueue()
        self.config = dataclasses.replace(config, log=self._log_put)
        self.backend = backend_class(self.config, self._event_put)
        self._disc_list_disp = []
        self._disc_list_curr = []
        self._disc_high = None
        self._connected = {};
        self._tab_open = {};

    def _log_put(self, level: LogLevel, text: str) -> None:
        self.event_queue.put(LogEvent(level, text))

    def _event_put(self, event: BackendEvent) -> None:
        self.event_queue.put(event)

    def on_mount(self) -> None:
        self.query_one("#system > ChatTab", ChatTab).append_system_message(
                SYSTEM_NAME,
                "Choose a peer from the list to chat!\nType '[bold]/help[/bold]' for more info.")
        self.backend.start()
        self.set_interval(0.05, self._event_drainer)

    def on_unmount(self) -> None:
        self.backend.stop()

    def compose(self) -> ComposeResult:
        yield Header(icon="💬", show_clock=True)
        with Horizontal(id="app"):
            with Vertical(id="app_tabs"):
                yield Button("💬", id="tab-main", name="main", classes="tab_button")
                yield Button("🔧", id="tab-settings", name="settings", classes="tab_button")
                yield Button("📜", id="tab-logs", name="logs", classes="tab_button")
            with ContentSwitcher(initial="main"):
                with Horizontal(id="main"):
                    with ListView(id="discovery"):
                        for peer in self._disc_list_curr:
                            yield DiscoveryEntry(peer)
                    with TabbedContent(id="active-chats"): # noqa: SIM117
                        with TabPane("System", id="system"):
                            yield ChatTab(None, "", True)
                with Vertical(id="settings"):
                    yield Static("asd")
                yield RichLog(id="logs", markup=True)
        yield Footer()

    @on(Button.Pressed, "#app_tabs > Button")
    def _switch_app_tabs(self, event: Button.Pressed) -> None:
        self.query_one("#app > ContentSwitcher", ContentSwitcher).current = event.button.name

    @on(ListView.Highlighted, "#discovery")
    def _disc_marquee_on(self, event: ListView.Highlighted) -> None:
        if isinstance(event.item, DiscoveryEntry):
            if isinstance(self._disc_high, DiscoveryEntry):
                self._disc_high.scroll_stop()
            event.item.scroll_start()
            self._disc_high = event.item

    @on(ListView.Selected, "#discovery")
    async def _connect_discovery(self, event: ListView.Selected) -> None:
        if isinstance(event.item, DiscoveryEntry):
            peer = event.item.peer
            addr = peer.addr
            await self._connect(addr, peer.name)

    async def _connect(self, addr: PeerAddress, name: str | None) -> None:
        if addr in self._connected:
            return
        if addr in self._tab_open:
            ct = self._tab_open[addr][0]
            tid = self._tab_open[addr][1]
        else:
            ct = ChatTab(addr, self.config.name)
            tp = TabPane(f"{addr.ip}:{addr.port}" if name is None else name, ct)
            await self.query_one("#active-chats", TabbedContent).add_pane(tp)
            tid = typing.cast(str, tp.id)
        ct.append_system_message(SYSTEM_NAME, f"Connecting to {name} ({addr.ip}:{addr.port})...")
        self.query_one("#active-chats", TabbedContent).active = tid
        self._tab_open[addr] = (ct, tid)
        self._connect1(addr, name, tid)

    @work(thread=True)
    def _connect1(self, addr: PeerAddress, name: str | None, tid: str) -> None:
        try:
            self.backend.connect(addr)
        except BackendError:
            del self._tab_open[addr]
            self.event_queue.put(FailConnectEvent(addr, name, tid))

    def _search_peers(self, sel: str) -> list[PeerInfo]:
        peers: list[PeerInfo] = self._disc_list_disp
        cand: list[tuple[PeerInfo, int]] = []
        for peer in peers:
            find_idx = peer.name.find(sel)
            if find_idx != -1:
                cand.append((peer, find_idx))
        cand.sort(key=lambda e: e[1])
        return [p[0] for p in cand]

    async def _disc_update(self) -> None:
        self._disc_list_curr = self.backend.get_peers()
        key: Callable[[PeerInfo], tuple] = lambda p: (p.name.casefold(), p.addr.ip, p.addr.port)
        self._disc_list_curr.sort(key=key)
        with self.batch_update():
            disc_list_el = self.query_one("#discovery", ListView)
            i_disp = 0
            i = 0
            while i_disp < len(self._disc_list_disp) and i < len(self._disc_list_curr):
                key_disp = key(self._disc_list_disp[i_disp])
                key_curr = key(self._disc_list_curr[i])
                if key_disp < key_curr:
                    await disc_list_el.pop(i)
                    i_disp += 1
                elif key_disp > key_curr:
                    await disc_list_el.insert(i, [DiscoveryEntry(self._disc_list_curr[i])])
                    i += 1
                else:
                    typing.cast(DiscoveryEntry, disc_list_el.children[i]).set_text(self._disc_list_curr[i])
                    i_disp += 1
                    i += 1
            if i_disp < len(self._disc_list_disp):
                await disc_list_el.remove_items(range(
                        len(self._disc_list_curr),
                        len(self._disc_list_curr) + len(self._disc_list_disp) - i_disp))
            elif i < len(self._disc_list_curr):
                await disc_list_el.extend([DiscoveryEntry(p) for p in self._disc_list_curr[i:]])
        self._disc_list_disp = self._disc_list_curr

    @on(ChatSend)
    def _chat_send(self, ev: ChatSend) -> None:
        if not isinstance(ev.addr, PeerAddress):
            return
        try:
            self.backend.send_message(ev.addr, ev.text)
        except BackendError as err:
            self._tab_open[ev.addr][0].append_system_message(
                    SYSTEM_NAME,
                    f"Failed to send message to {ev.addr.ip}:{ev.addr.port}: {err!s}")

    @on(DisconnectReq)
    def _disconnect_req(self, ev: DisconnectReq) -> None:
        self.backend.disconnect(ev.addr)

    @on(CloseReq)
    def _close_req(self, ev: CloseReq) -> None:
        if ev.addr not in self._tab_open:
            return
        if ev.addr in self._connected:
            self.event_queue.put(CloseFailedEvent(ev.addr))
            return
        self.event_queue.put(CloseChatEvent(ev.addr))

    @on(FileSendReq)
    def _file_send_req(self, ev: FileSendReq):
        try:
            self.backend.send_file(ev.addr, ev.path)
        except BackendError as err:
            self.event_queue.put(FileSendFailEvent(ev.addr, ev.path, str(err)))

    async def _event_drainer(self) -> None:
        needs_disc_update: bool = False
        while True:
            try:
                ev = self.event_queue.get_nowait()
            except queue.Empty:
                break
            match ev:
                case LogEvent(level=level, text=text):
                    self.query_one("#logs", RichLog).write(f"[{level.name}] {markup.escape(text)}")
                case FailConnectEvent(addr=addr, name=name, tid=tid):
                    self.query_one("#active-chats", TabbedContent).active = "system"
                    self.query_one("#active-chats", TabbedContent).remove_pane(tid)
                    self.query_one("#system > ChatTab", ChatTab).append_system_message(
                            SYSTEM_NAME,
                            f"Failed to connect to {markup.escape(name) + ' ' if name is not None else ''}({addr.ip}:{addr.port}).")
                case PeerOnline(_):
                    needs_disc_update = True
                case PeerChanged(_):
                    needs_disc_update = True
                case PeerOffline(_):
                    needs_disc_update = True
                case PeerConnected(addr=addr, name=name):
                    self._connected[addr] = name
                    if addr not in self._tab_open:
                        ct = ChatTab(addr, self.config.name)
                        tp = TabPane(f"{markup.escape(name)}", ct)
                        await self.query_one("#active-chats", TabbedContent).add_pane(tp)
                        tid = typing.cast(str, tp.id)
                        self._tab_open[addr] = (ct, tid)
                    self._tab_open[addr][0].append_system_message(
                            SYSTEM_NAME,
                            f"Connected to {markup.escape(name)} ({addr.ip}:{addr.port})")
                    tc = self.query_one("#active-chats", TabbedContent)
                    tab = tc.get_tab(self._tab_open[addr][1])
                    tab.label = name
                case PeerDisconnected(addr=addr, name=name, reason=reason):
                    del self._connected[addr]
                    self._tab_open[addr][0].append_system_message(
                            SYSTEM_NAME,
                            f"Peer disconnected. Reason: {markup.escape(reason)}")
                case MessageReceived(addr=addr, name=name, text=text, timestamp=_):
                    self._tab_open[addr][0].append_peer_message(ev)
                case CloseFailedEvent(addr=addr):
                    self._tab_open[addr][0].append_system_message(
                            SYSTEM_NAME,
                            "Disconnect the peer before running [bold]'/close'[/bold]")
                case CloseChatEvent(addr=addr):
                    self.query_one("#active-chats", TabbedContent).active = "system"
                    self.query_one("#active-chats", TabbedContent).remove_pane(self._tab_open[addr][1])
                    del self._tab_open[addr]
                case FileSendFailEvent(addr=addr, path=path, reason=reason):
                    self._tab_open[addr][0].append_system_message(
                            SYSTEM_NAME,
                            f"Failed to send {path!s}. Reason: {markup.escape(reason)}")
                case TransferProgress(transfer=transfer):
                    self._tab_open[transfer.addr][0].update_file_message(ev)
                case TransferFinished(transfer=transfer):
                    self._tab_open[transfer.addr][0].update_file_message(ev)
                case TransferFailed(transfer=transfer):
                    self._tab_open[transfer.addr][0].update_file_message(ev)
                case _:
                    pass

        if needs_disc_update:
            await self._disc_update()
