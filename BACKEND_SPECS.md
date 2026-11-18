# Specifications for the backend

Refer to the assignment brief for the core requirements needed.

## Structure

Backend code must be placed within the `backend/` directory. Don't do `v1` stuff because guess what git is for?

Don't overcomplicate stuff with "security measures."

## Configuration

All backend configuration must be passed in via configuration dataclasses. Loading configurations from `.toml` files is banned, because config is Mochi-tan's responsibility (⸝⸝> ᴗ•⸝⸝)

Look at [backend/data_types.py](./backend/data_types.py) for the exact specs.

## Logging

Logging shall only ever be done through the log function provided by the `BackendConfig` class. If the function is not provided, logging must be a no-op.

## Public interfaces

A class implementing the backend must have these:

- `__init__(config: BackendConfig, on_event: Callable[[BackendEvent], None])`: Stores config and event callback. Must not block.
- `start() -> None`: Binds TCP socket, starts UDP discovery and TCP acceptor. Calling `start()` twice should raise a `BackendError`. Do not try to make the backend restartable after calling `stop()`. Should not block for a long time.
- `tcp_port : int | None`: A read-only property, returning what the user's current TCP port is. Must not block.
- `stop() -> None`: Sends a goodbye signal to UDP discovery, closes all open TCP sockets, aborts and deletes any partial downloads, and stops threads. The method is idempotent (look it up (๑ > ᴗ < ๑) ehehe). Allowed to block for short time.
- `get_peers() -> list[PeerInfo]`: Returns an **unordered** list of the current discovered peers. Must not block.
- `set_status(status: str) -> None`: Set the user's status and immediately broadcasts it. Must not block.
- `connect(addr: PeerAddress) -> None`: Opens TCP connection to the address, and exchanges a hello if not already connected. Is a no-op if already connected. Raise a `BackendError` if not reachable. May block up to `config.connect_timeout`.
- `disconnect(addr: PeerAddress) -> None`: Sends a leave (best-effort) and close only the address's socket. Abort any active file transfers on the socket. Is a no-op if socket is already closed.
- `send_message(addr: PeerAddress, message: str) -> None`: Sends a chat message to the address. Raise `BackendError` if not connected or if the socket broke.
- `send_file(addr: PeerAddress, filepath: str | Path) -> str`: Sends a file to the address. Raise `BackendError` if not connected, if file doesn't exist. Return the `transfer_id`. Must not block.

## TCP (maybe other stuff if you want to) protocol

We are here to get clout for forwards-compatibility.

[Type–length–value](https://en.wikipedia.org/wiki/Type%E2%80%93length%E2%80%93value)

All stuff sent via TCP sockets shall follow this format:
- First 4 bytes: A label saying what type the data is (e.g "HELO", "GBYE", "CHAT", ...)
- Next 4 bytes: An unsigned 4-byte integer, storing the byte size of the data in network-order.
- The data: ... the data. "( – ⌓ – )

Examples:
```text
48 45 4C 4F    HELO
00 00 00 00    ....

48 45 4C 4F    HELO
00 00 00 04    ....
67 69 42 00    giB.
```

Some types may need you to recursively parse a TLV block inside a TLV block.

But remember the most important rule when dealing with data of this kind. **DO NOT ERROR WHEN YOU ENCOUNTER AN UNKNOWN TYPE. SKIP IT. IGNORE IT.** ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧

## A little bit of implementation details

The backend should generate an `instance_id` on a `start()` call, to be used for identifying unique users in UDP discovery. Use `uuid.uuid4()` because... I heard it's good? (⸝⸝⸝╸w╺⸝⸝⸝)

When broadcasting to the addresses given, check for errors in **each address** and **ignore** them.

(WIP)
