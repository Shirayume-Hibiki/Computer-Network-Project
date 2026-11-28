'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  diamboy                   ║
║  Creation date:            28/11/26                  ║
║  Edit dates / contributor:                           ║
╚══════════════════════════════════════════════════════╝
'''

from backend.data_types import (
    LogLevel,
    PeerAddress,
    BackendConfig,
    PeerInfo,
    TransferInfo,
    BackendError,
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
)
import threading
from collections.abc import Callable
from pathlib import Path
import random
import time
from typing import Literal
from uuid import UUID, uuid4

_PEER_SIM: list[tuple[str, str, int, list[tuple[str, float]]]] = [
        ("diamboy", "192.168.1.10", 1000,
         [("online", 10), ("", 5)]),
        ("Mochi-tan もちもち～", "192.168.1.10", 1001,
         [("🍡🍡mgmg", 7), ("🍬🍬prpr～", 7), ("", 5)]),
        ("Gemini 3.8 Flash", "23.143.42.33", 9931,
         [("", 5), ("Ruminating...", 12)]),
        ("Hibiki", "23.143.42.33", 1000,
         [("online", 20), ("", 5)]),
]

def _get_name(addr: PeerAddress) -> str:
    for p in _PEER_SIM:
        if PeerAddress(p[1], p[2]) == addr:
            return p[0]
    return ""

class MockPeerBackend:
    _name: str
    _status: str
    _on_event: Callable[[BackendEvent], None]
    _conf_tcp_port: int
    _connect_timeout: float
    _disc_thr: threading.Thread
    _lifetime: Literal["init", "running", "finished"]
    _lifetime_lock: threading.Lock
    _log: Callable[[LogLevel, str], None]
    _start_time: float
    _peer_list: dict[PeerAddress, PeerInfo]
    _peer_list_lock: threading.Lock
    _peer_thrs: dict[PeerAddress, threading.Thread]
    _peer_dis_cv: threading.Condition
    _peer_connected: set[PeerAddress]
    _peer_thrs_lock: threading.Lock
    _tcp_port: int | None = None
    @staticmethod
    def log_silent(level: LogLevel, text: str) -> None:
        pass
    def __init__(self,
                 config: BackendConfig,
                 on_event: Callable[[BackendEvent], None]):
        self._name = config.name
        self._status = config.status
        self._on_event = on_event
        self._conf_tcp_port = config.tcp_port
        self._connect_timeout = config.connect_timeout
        self._lifetime = "init"
        self._lifetime_lock = threading.Lock()
        if config.log is not None:
            self._log = config.log
        else:
            self._log = self.log_silent
        self._peer_list = {PeerAddress("?", 12): PeerInfo(name="fail", addr=PeerAddress("?", 12), status="fail", last_seen=0)}
        self._peer_list_lock = threading.Lock()
        self._peer_thrs = {}
        self._peer_connected = set()
        self._peer_thrs_lock = threading.Lock()
        self._peer_dis_cv = threading.Condition(self._peer_thrs_lock)
        self._disc_thr = threading.Thread(target=self._disc)
        self._start_time = time.time()
        self._log(LogLevel.DEBUG, "backend init")
    def start(self) -> None:
        with self._lifetime_lock:
            if self._lifetime != "init":
                raise BackendError(f"cannot call start() when {self._lifetime}")
            self._lifetime = "running"
        if self._conf_tcp_port == 0:
            self._tcp_port = 1337
        else:
            self._tcp_port = self._conf_tcp_port
        self._disc_thr.start()
        self._log(LogLevel.DEBUG, f"backend started on port {self._tcp_port}")
    @property
    def tcp_port(self) -> int | None:
        return self._tcp_port
    def stop(self) -> None:
        with self._lifetime_lock:
            if self._lifetime == "finished":
                return
            if self._lifetime == "init":
                self._lifetime = "finished"
                return
            self._lifetime = "finished"
        with self._peer_dis_cv:
            self._peer_connected.clear()
            self._peer_dis_cv.notify_all()
        for thr in self._peer_thrs.values():
            thr.join()
        self._peer_thrs.clear()
        self._disc_thr.join()
        self._tcp_port = None
        self._log(LogLevel.DEBUG, "backend stopped")
    def _update_peers(self) -> None:
        t = time.time() - self._start_time
        for peer_sim in _PEER_SIM:
            tm = sum([sch[1] for sch in peer_sim[3]])
            tt = t % tm
            ti = 0
            ts = 0.0
            while tt > ts + peer_sim[3][ti][1]:
                ts += peer_sim[3][ti][1]
                ti += 1
            tl = self._start_time + t - tt + ts
            addr = PeerAddress(peer_sim[1], peer_sim[2])
            ev: BackendEvent | None = None
            with self._peer_list_lock:
                if addr in self._peer_list:
                    if peer_sim[3][ti][0] == self._peer_list[addr].status:
                        pass
                    elif peer_sim[3][ti][0] == "":
                        ev = PeerOffline(self._peer_list[addr], "timeout")
                        del self._peer_list[addr]
                    else:
                        self._peer_list[addr] = PeerInfo(
                                name=self._peer_list[addr].name,
                                status=peer_sim[3][ti][0],
                                addr=self._peer_list[addr].addr,
                                last_seen=tl)
                        ev = PeerChanged(self._peer_list[addr])
                elif peer_sim[3][ti][0] == "":
                    pass
                else:
                        self._peer_list[addr] = PeerInfo(
                                name=peer_sim[0],
                                status=peer_sim[3][ti][0],
                                addr=PeerAddress(peer_sim[1], peer_sim[2]),
                                last_seen=tl)
                        ev = PeerOnline(self._peer_list[addr])
            if ev is not None:
                self._on_event(ev)
    def _disc(self) -> None:
        while True:
            with self._lifetime_lock:
                if self._lifetime != "running":
                    return
            self._update_peers()
            time.sleep(0.2)
    def get_peers(self) -> list[PeerInfo]:
        with self._lifetime_lock:
            if self._lifetime != "running":
                raise BackendError("cannot call get_peers() when not running")
        with self._peer_list_lock:
            return list(self._peer_list.values())
    def set_status(self, status: str) -> None:
        with self._lifetime_lock:
            if self._lifetime != "running":
                raise BackendError("cannot call set_status() when not running")
        self._status = status
    def _connected_sim(self, addr: PeerAddress, name: str) -> None:
        MESSAGES = (["i love komamochi's art",
                     "🎨🎨🎨🎨🎨🎨🎨🎨🎨🎨",
                     "🖌️🖌️🖌️🖌️🖌️🖌️🖌️🖌️🖌️🖌️🖌️",
                     "i wanna commission you!!～"] * 4
                    + [0, 0, 0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 2])
        sending_total = 0
        sending_left = -1
        tr_id: UUID
        self._on_event(PeerConnected(addr, name))
        self._peer_dis_cv.acquire()
        while True:
            self._peer_dis_cv.wait(0.03125)
            if addr not in self._peer_connected:
                break
            ev: BackendEvent | None = None
            if random.random() < 1 / 16:
                msg = random.choice(MESSAGES)
                if isinstance(msg, str):
                    ev = MessageReceived(addr=addr,
                                         name=name,
                                         text=msg,
                                         timestamp=time.time())
                elif sending_left == -1 and msg == 0:
                    tr_id = uuid4()
                    sending_total = sending_left = random.randrange(8, 16)
                    ev = TransferProgress(TransferInfo(
                            transfer_id=tr_id,
                            addr=addr,
                            name=name,
                            filename="komamochi_fanart.psd",
                            direction="download",
                            bytes_transferred=0,
                            bytes_total=sending_total * 512,
                            saved_path=None,
                            error=None))
                elif sending_left >= 0 and msg == 2:
                    ev = TransferFailed(TransferInfo(
                            transfer_id=tr_id,
                            addr=addr,
                            name=name,
                            filename="komamochi_fanart.psd",
                            direction="download",
                            bytes_transferred=(sending_total
                                               - sending_left) * 512,
                            bytes_total=sending_total * 512,
                            saved_path=None,
                            error="bc i wanna"))
                    sending_left = -1
                elif sending_left > 0:
                    sending_left -= 1
                    ev = TransferProgress(TransferInfo(
                            transfer_id=tr_id,
                            addr=addr,
                            name=name,
                            filename="komamochi_fanart.psd",
                            direction="download",
                            bytes_transferred=(sending_total
                                               - sending_left) * 512,
                            bytes_total=sending_total * 512,
                            saved_path=None,
                            error=None))
                elif sending_left == 0:
                    sending_left -= 1
                    ev = TransferFinished(TransferInfo(
                            transfer_id=tr_id,
                            addr=addr,
                            name=name,
                            filename="komamochi_fanart.psd",
                            direction="download",
                            bytes_transferred=sending_total * 512,
                            bytes_total=sending_total * 512,
                            saved_path=Path("nyan"),
                            error=None))
            if ev is not None:
                self._peer_dis_cv.release()
                self._on_event(ev)
                self._peer_dis_cv.acquire()
        self._peer_dis_cv.release()
        if sending_left >= 0:
            self._on_event(TransferFailed(TransferInfo(
                    transfer_id=tr_id,
                    addr=addr,
                    name=name,
                    filename="komamochi_fanart.psd",
                    direction="download",
                    bytes_transferred=(sending_total
                                       - sending_left) * 512,
                    bytes_total=sending_total * 512,
                    saved_path=None,
                    error="disconnect")))
        self._on_event(PeerDisconnected(addr, name, "disconnect"))
    def connect(self, addr: PeerAddress) -> None:
        with self._lifetime_lock:
            if self._lifetime != "running":
                raise BackendError("cannot call connect() when not running")
        with self._peer_thrs_lock:
            if addr in self._peer_connected:
                return
        time.sleep(random.uniform(self._connect_timeout / 2,
                                  self._connect_timeout))
        if addr not in [PeerAddress(i[1], i[2]) for i in _PEER_SIM]:
            raise BackendError(f"{addr} is not reachable")
        name = _get_name(addr)
        with self._peer_thrs_lock:
            if addr in self._peer_connected:
                return
            self._peer_connected.add(addr)
            self._peer_thrs[addr] = threading.Thread(
                    target=self._connected_sim,
                    args=(addr, name))
            self._peer_thrs[addr].start()
    def disconnect(self, addr: PeerAddress) -> None:
        with self._lifetime_lock:
            if self._lifetime != "running":
                raise BackendError("cannot call disconnect() when not running")
        with self._peer_thrs_lock:
            if addr not in self._peer_connected:
                return
        with self._peer_thrs_lock:
            if addr not in self._peer_connected:
                return
            self._peer_connected.remove(addr)
            self._peer_dis_cv.notify_all()
        self._peer_thrs[addr].join()
        del self._peer_thrs[addr]
    def send_message(self, addr: PeerAddress, message: str) -> None:
        with self._lifetime_lock:
            if self._lifetime != "running":
                raise BackendError("cannot call send_message() when not running")
        pass
    def _send_file_sim(self, addr: PeerAddress, file: Path) -> None:
        pass
    def send_file(self, addr: PeerAddress, filepath: str | Path) -> UUID:
        with self._lifetime_lock:
            if self._lifetime != "running":
                raise BackendError("cannot call send_file() when not running")
        return uuid4()
