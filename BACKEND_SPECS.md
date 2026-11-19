# Specifications for the backend

Refer to the assignment brief for the core requirements.

## Structure

Backend code must be placed within the `backend/` directory. Don't do `v1` stuff because guess what git is for?

All backend code must import only from standard Python libraries.

Importing any module must never cause any side-effects.

Don't overcomplicate stuff with "security measures."

## Configuration

All backend configuration must be passed in via configuration dataclasses. Loading configurations from `.toml` files is banned, because config is Mochi-tan's responsibility (⸝⸝> ᴗ•⸝⸝)

Look at [backend/data_types.py](./backend/data_types.py) for the exact specs.

## Logging

Logging shall only ever be done through the log function provided by the `BackendConfig` class. If the function is not provided, logging must be a no-op.

Mochi-tan has lamented many times, don't do it yourself! Don't spill it out to stdout or to a file! Only the log function! ｡°(°¯᷄◠¯᷅°)°｡

User-facing messages should go through the event system instead of the log function.

## Public interfaces

`backend/__init__.py` must expose a class named `PeerBackend` that has these methods:

- `__init__(config: BackendConfig, on_event: Callable[[BackendEvent], None])`: Stores config and event callback. Must not block.
- `start() -> None`: Binds TCP socket, starts UDP discovery and TCP acceptor. Calling `start()` twice should raise a `BackendError`. Raise a `BackendError` if it's called after calling `stop()`. Should not block for a long time.
- `tcp_port: int | None`: A read-only property, returning what the user's current TCP port is. Must not block.
- `stop() -> None`: Sends a goodbye signal to UDP discovery, closes all open TCP sockets, aborts and deletes any partial downloads, and stops threads. The method is idempotent (look it up (๑ > ᴗ < ๑) ehehe). Allowed to block for a short time.
- `get_peers() -> list[PeerInfo]`: Returns an **unordered** list of the current discovered peers. Must not block.
- `set_status(status: str) -> None`: Sets the user's status and immediately broadcasts it. Must preserve custom statuses like `🍡🍡mgmg`. Must not block.
- `connect(addr: PeerAddress) -> None`: Opens TCP connection to the address, and exchanges a hello if not already connected. Emit a `PeerConnected` event once done. Is a no-op if the socket is already connected. Raise a `BackendError` if not reachable. May block up to `config.connect_timeout` seconds (this is the total budget of the function).
- `disconnect(addr: PeerAddress) -> None`: Sends a leave (but don't block waiting on a dead peer) and shuts-down + closes only the address's socket. Abort any active file transfers on the socket. Emit a `PeerDisconnected` event once done. Is a no-op if the socket is already closed. Must not block.
- `send_message(addr: PeerAddress, message: str) -> None`: Sends a chat message to the address. Raise `BackendError` if not connected. If the socket broke before or during the sending, tear down the socket cleanly before raising `BackendError`. Must not block.
- `send_file(addr: PeerAddress, filepath: str | Path) -> UUID`: Sends a file to the address. Raise `BackendError` if not connected or if the path points to something that's not a file. Return the `transfer_id`. Must not block.

`get_peers`, `set_status`, `connect`, `disconnect`, `send_message`, and `send_file` should raise a `BackendError` if the backend hasn't started, or has stopped.

## TCP (maybe UDP too if you want) protocol

We are doing this to get clout for backwards-and-forwards-compatibility.

[Type–length–value](https://en.wikipedia.org/wiki/Type%E2%80%93length%E2%80%93value)

All stuff sent via TCP sockets shall follow this format:
- First 4 bytes: A label saying what type the data is (e.g., "HELO", "LEAV", "CHAT", ...)
- Next 4 bytes: An unsigned 4-byte integer, storing the byte size of the data in network-order.
- The data: ... the data. "( – ⌓ – )

Examples:
```text
41 42 43 44    ABCD
00 00 00 00    ....

41 42 43 44    ABCD
00 00 00 03    ....
67 69 42       giB

4E 45 53 54    NEST
00 00 00 18    ....
53 55 42 31    SUB1
00 00 00 03    ....
67 69 42 53    giBS
55 42 32 00    UB2.
00 00 05 69    ...i
42 01 33 70    B.3p

(chunked)
4E 45 53 54    NEST
00 00 00 18    ....
│   53 55 42 31    SUB1
│   00 00 00 03    ....
│   67 69 42       giB
│
│   53 55 42 32    SUB2
│   00 00 00 05    ....
│   69 42 01 33 70 iB.3p
```

Some types may need you to recursively parse a TLV block inside a TLV block.

We shall call the block at the outermost layer a "frame," inner layers as "subblocks," and the general term for both as... "blocks."

But remember the most important rule when dealing with data of this kind. **DO NOT ERROR WHEN YOU ENCOUNTER AN UNKNOWN TYPE. SKIP IT. IGNORE IT.** ദ്ദി(˵ •̀ ᴗ - ˵ ) ✧

When you encounter a block with an unknown tag, read the data size, read exactly that many bytes from the socket, and discard them.

When you encounter a block with a size that's too big (size ≥ 16 MiB) or when a subblock's end spills over the parent block's end, everything is corrupted! There's no hope left! Emit a `BackendNotice` (and a `TransferFailed` if any file transfers are currently happening) and disconnect the socket. Remember to check the sizes before doing any reads.

## A little bit of implementation details

The backend should generate an `instance_id` on a `start()` call, to be used for identifying unique users in UDP discovery. Use `uuid.uuid4()` because... I heard it's good? (⸝⸝⸝╸w╺⸝⸝⸝)

`start()` must bind to `("", config.tcp_port)`. If binding TCP or UDP fails, close all sockets cleanly before raising a `BackendError`.

When broadcasting to the addresses given, check for errors in **each address** and **ignore** them. If you do exception-handling around the whole loop, you will not send your presence message to all available addresses, and you will stop early at the first error. So, ignore errors per address. (Mochi-tan learned that stopping at "what you should do" is better than "what you shouldn't do!" Words are cool, aren't they? ⋆˚☆˖°⋆｡° ✮˖ ࣪ ⊹⋆.˚)

Remember to enable `SO_BROADCAST` on broadcast sockets.

Methods involving TCP sockets may be run on many threads, so each socket should hold a mutex (`threading.Lock`) when sending data. The mutex should only be acquired when sending one complete TLV frame.

STOP RETRYING SHIT

A TCP connection either delivers bytes in order, or the stream is dead. On such errors, immediately tear down the socket cleanly.

## Minimum frame types (TCP)

All serialized integers are in network-order.

- `HELO`: Sent immediately on connect/accept. It must have the following subblocks:
    - `USID`: The `instance_id` as the raw 16-byte representation.
    - `NAME`: The peer's name in UTF-8.
    - `PORT`: The peer's listening port as a `u16`. Store this port instead of the port returned from `accept()`.
- `CHAT`: Sent when a chat message is... sent. It must have the following subblocks:
    - `TEXT`: The message content in UTF-8.
    - (Ehhhhh, only one subblock??? Don't worry, Mochi-tan has a plan ( • ᴗ - ) ✧)
- `FBEG`: Sent when starting a file transfer. It must have the following subblocks:
    - `FTID`: The transfer ID as the raw 16-byte representation.
    - `FNAM`: The UTF-8 filename. Remember to sanitize it before use. Don't let a stray ../../../../../ ruin everyone's day!
    - `SIZE`: The expected file size as a u64.
- `FDAT`: The raw file chunks that are sent. It must have the following subblocks:
    - `FTID`: The transfer ID as the raw 16-byte representation.
    - `DATA`: The data lol.
- `FEND`: Sent when the file transfer is complete. It must have the following subblocks:
    - `FTID`: The transfer ID as the raw 16-byte representation.
    - (Ehhhhh, only one subblock??? Don't worry, Mochi-tan also has a plan ( • ᴗ - ) ✧)
- `LEAV`: Sent on a graceful disconnect.

When you encounter a known block that doesn't have the required subblocks, treat the whole connection as corrupted and clean up the connection like above.

## Minimum frame types (UDP)

Resist the temptation to use JSON. Use TLV too. You have to write a TLV parser already, reuse it.

- `PRES`: Sent as the presence message. It must have the following subblocks:
    - `USID`: The `instance_id` as the raw 16-byte representation.
    - `NAME`: The peer's name in UTF-8.
    - `PORT`: The peer's listening port as a `u16`.
    - `STAT`: The peer's status in UTF-8.
- `GBYE`: Sent on a graceful stop. It must have the following subblocks:
    - `USID`: The `instance_id` as the raw 16-byte representation.

When you encounter a known block that doesn't have the required subblocks... cope lol. Log a warning.

## UDP discovery

Bind the UDP listener to `("", config.discovery_port)` using `SO_BROADCAST`, `SO_REUSEADDR` **AND** `SO_REUSEPORT` if present, for cross-platform compatibility.

Use `instance_id` to filter our own presence message, as a key to an internal peer table, and to silently (without emitting `PeerOffline`) remove an older entry that has the exact same address when a peer restarts on the same port.

Emit a `PeerOnline` event when a peer with a new `instance_id` goes online.

Emit a `PeerChanged` event when a peer's address, name or status changes.

Emit a `PeerOffline` event when a peer is removed from the internal active peers list. The reason "goodbye" is used when the peer has broadcasted a goodbye. The reason "timeout" is used when there has been no presence messages from the peer after `config.broadcast_timeout` seconds.

When updating an existing `instance_id`, prefer upgrading to non-loopback IPs (obtained via `recvfrom()`) over loopback IPs. Conversely, don't overwrite an existing non-loopback IP with a loopback IP.

Broadcast a presence message every `config.broadcast_interval` seconds and immediately on `set_status()`.

Broadcast a goodbye message on `stop()`.

Remove a peer off of the active list after `config.broadcast_timeout` seconds of no presence messages. But do not close a perfectly good TCP connection to them.

The backend should *at least* trim any status received from other connections to `MAX_STATUS_BYTES` before storing it into `PeerInfo`s. Be careful when handling UTF-8 multibyte sequences.

## TCP

Accept multiple peers. Why do I have to say this? Look at the assignment? Look at `refactor/all_that_mattered script/lib/v1/peer/peer_node.py:375`? Well Mochi-tan thinks you just didn't tell your Gemini 3.8 Flash-san to follow the requirements more carefully!! (╥ ᴗ ╥)

If two peers connect at the same time, resolve the duplication cleanly by a tiebreaking rule (Mochi-tan proposes... we compare `instance_id`, and the peer with the lower `instance_id` will keep its outgoing connection! Conversely, the peer with the higher `instance_id` will keep its incoming connection! ദ്ദി ˉ͈̀꒳ˉ͈́ ) Don't emit a `PeerDisconnected` for the closed duplicate connection. And since this is within "expected behavior," don't raise any errors.

After the hello exchange, sockets should all be set to blocking mode with no timeouts in the receiver threads.

Release all internal locks before calling `on_event`.

Each socket's write mutex should only be held when sending one complete TLV frame.

When a chat message is received, emit a `MessageReceived` event with the timestamp being `time.time()`.

The backend should *at least* trim any name received from other connections to `MAX_NAME_BYTES` before storing it into `PeerInfo`s or event dataclasses. Be careful when handling UTF-8 multibyte sequences.

### TCP file transfer

Stream files, starting with an `FBEG` frame, then many `FDAT` frames in order, and ending with an `FEND` frame. Acquire and release the write mutex when sending each frame. 0-byte files must be supported.

Throttle `TransferProgress` events to something reasonable. You must send one at 0% and 100%, and send mid-transfer progress updates at a throttled frequency (Mochi-tan proposes... for every increment of 5% OR every 0.2 seconds! ( ◡̀  ̫ ◡́) ✧)

Emit a `TransferFinished` event when the transfer... finishes... (๑ > ᴗ < ๑)

Don't emit a `TransferProgress` event after a `TransferFinished` event of the same `transfer_id`.

Save downloads in the directory `downloads_dir` with sanitized filenames, and without overwriting existing files by implementing a collision suffix. Verify total size on `FEND`. If the directory doesn't exist, make one.

On any failure, disconnect or stop() before transfer completion, close the file handle, delete the partially-downloaded file, and emit a `TransferFailed` event.
