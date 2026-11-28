'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  diamboy                   ║
║  Creation date:            28/11/26                  ║
║  Edit dates / contributor:                           ║
╚══════════════════════════════════════════════════════╝
'''

import dataclasses
from dataclasses import dataclass
import queue
import threading
import typing
from typing import Callable

from textual import events, on, markup, work
from textual.app import App, ComposeResult
from textual.containers import (
    Horizontal,
    HorizontalGroup,
    HorizontalScroll,
    Vertical,
    VerticalGroup,
    VerticalScroll,
    Center,
)
from textual.message import Message
from textual.timer import Timer
from textual.widgets import (
    Header,
    Footer,
    Static,
    Button,
    OptionList,
    ContentSwitcher,
    RichLog,
    ListView,
    ListItem,
    TabbedContent,
    TabPane,
    TextArea,
)

from backend.data_types import (
    PeerAddress,
    BackendConfig,
    LogLevel,
    PeerInfo,
    PeerOnline,
    PeerChanged,
    PeerOffline,
    PeerConnected,
    PeerDisconnected,
    MessageReceived,
    TransferProgress,
    TransferFinished,
    TransferFailed,
    BackendEvent,
    BackendError,
)

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
    border_title: str
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

class ChatSendReq(Message):
    pass

class ChatSend(Message):
    text: str
    addr: PeerAddress | None
    def __init__(self, text: str, addr: PeerAddress | None = None):
        super().__init__()
        self.text = text
        self.addr = addr

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
    def __init__(self, addr: PeerAddress | None, name: str, mute: bool = False):
        super().__init__()
        self._chat_log = VerticalScroll(id="chat-log")
        self._chat_log.anchor()
        self._chat = ChatTextArea(id="chat-box")
        self._send = Button("⏎", id="chat-send")
        self._name = name
        self._addr = addr
        self._mute = mute
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
        text = self._chat.text.strip()
        if len(text) == 0:
            return
        self._chat.clear()
        if not self._mute:
            self._chat_log.mount(ChatMessage(self._name, markup.escape(text), True))
        self.post_message(ChatSend(text, self._addr))
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

SYSTEM_NAME = "[bold]SYSTEM[/bold]"

class ChatApplication(App):
    TITLE = "Chateaubriand"
    CSS_PATH = "app.tcss"
    event_queue: queue.SimpleQueue[BackendEvent | LogEvent | FailConnectEvent]
    _disc_list_disp: list[PeerInfo]
    _disc_list_curr: list[PeerInfo]
    _disc_high: DiscoveryEntry | None
    _connected: dict[PeerAddress, tuple[ChatTab, str]]
    def __init__(self, backend_class, config: BackendConfig):
        super().__init__()
        self.event_queue = queue.SimpleQueue()
        self.config = dataclasses.replace(config, log=self._log_put)
        self.backend = backend_class(self.config, self._event_put)
        self._disc_list_disp = []
        self._disc_list_curr = []
        self._disc_high = None
        self._connected = {};

    def _log_put(self, level: LogLevel, text: str) -> None:
        self.event_queue.put(LogEvent(level, text))

    def _event_put(self, event: BackendEvent) -> None:
        self.event_queue.put(event)

    def on_mount(self) -> None:
        self.query_one("#system > ChatTab", ChatTab).append_system_message(
                SYSTEM_NAME,
                "Choose a peer from the list!")
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
                    with TabbedContent(id="active-chats"):
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
        if addr in self._connected.keys():
            return
        ct = ChatTab(addr, self.config.name)
        tp = TabPane(f"{addr.ip}:{addr.port}" if name is None else name, ct)
        await self.query_one("#active-chats", TabbedContent).add_pane(tp)
        ct.append_system_message(SYSTEM_NAME, f"Connecting to {name} ({addr.ip}:{addr.port})...")
        tid = typing.cast(str, tp.id)
        self.query_one("#active-chats", TabbedContent).active = tid
        self._connected[addr] = (ct, tid)
        self._connect1(addr, name, tid)

    @work(thread=True)
    def _connect1(self, addr: PeerAddress, name: str | None, tid: str) -> None:
        try:
            self.backend.connect(addr)
        except BackendError as err:
            del self._connected[addr]
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
            self._connected[ev.addr][0].append_system_message(
                    SYSTEM_NAME,
                    f"Failed to send message to {ev.addr.ip}:{ev.addr.port}: {str(err)}")

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
                case PeerOnline(peer=peer):
                    needs_disc_update = True
                case PeerChanged(peer=peer):
                    needs_disc_update = True
                case PeerOffline(peer=peer):
                    needs_disc_update = True
                case PeerConnected(addr=addr, name=name):
                    if addr not in self._connected:
                        ct = ChatTab(addr, self.config.name)
                        tp = TabPane(f"{markup.escape(name)}", ct)
                        await self.query_one("#active-chats", TabbedContent).add_pane(tp)
                        tid = typing.cast(str, tp.id)
                        self._connected[addr] = (ct, tid)
                    self._connected[addr][0].append_system_message(
                            SYSTEM_NAME,
                            f"Connected to {name} ({addr.ip}:{addr.port})")
                    tc = self.query_one("#active-chats", TabbedContent)
                    tab = tc.get_tab(self._connected[addr][1])
                case PeerDisconnected(addr=addr, name=name, reason=reason):
                    pass
                case MessageReceived(addr=addr, name=name, text=text, timestamp=timestamp):
                    self._connected[addr][0].append_peer_message(ev)
                case _:
                    pass

        if needs_disc_update:
            await self._disc_update()
