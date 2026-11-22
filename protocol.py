'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Shirayume_Hibiki          ║
║  Creation date:            21/11/26                  ║
║  Edit dates / contributor:                           ║
╚══════════════════════════════════════════════════════╝
'''

from __future__ import annotations

import socket
import struct
import uuid

# Maximum frame size allowed across network (16 MiB)
MAX_FRAME_SIZE: int = 16 * 1024 * 1024
HEADER_FORMAT: str = "!4sI"
HEADER_SIZE: int = struct.calcsize(HEADER_FORMAT)  # 8 bytes

# Frame tags (TCP)
TAG_HELO = b"HELO"
TAG_CHAT = b"CHAT"
TAG_FBEG = b"FBEG"
TAG_FDAT = b"FDAT"
TAG_FEND = b"FEND"
TAG_LEAV = b"LEAV"

# Frame tags (UDP)
TAG_PRES = b"PRES"
TAG_GBYE = b"GBYE"

# Subblock tags
TAG_USID = b"USID"
TAG_NAME = b"NAME"
TAG_PORT = b"PORT"
TAG_TEXT = b"TEXT"
TAG_FTID = b"FTID"
TAG_FNAM = b"FNAM"
TAG_SIZE = b"SIZE"
TAG_DATA = b"DATA"
TAG_STAT = b"STAT"


def pack_block(tag: bytes, data: bytes) -> bytes:
    """Packs a single TLV block: 4-byte tag, 4-byte unsigned length, payload."""
    tag_4 = tag[:4].ljust(4, b" ")
    return struct.pack(HEADER_FORMAT, tag_4, len(data)) + data


def pack_subblocks(tag: bytes, subblocks: list[tuple[bytes, bytes]]) -> bytes:
    """Concatenates packed subblocks and wraps them inside an outer TLV block."""
    body = b"".join(pack_block(subtag, subdata) for subtag, subdata in subblocks)
    return pack_block(tag, body)


def unpack_subblocks(data: bytes) -> list[tuple[bytes, bytes]]:
    """
    Parses a byte stream into a list of (tag, value) subblocks.
    Raises ValueError if length exceeds data or is >= MAX_FRAME_SIZE.
    """
    offset = 0
    total_len = len(data)
    blocks: list[tuple[bytes, bytes]] = []

    while offset < total_len:
        if offset + HEADER_SIZE > total_len:
            raise ValueError(f"Incomplete subblock header at offset {offset}")

        subtag, sublen = struct.unpack_from(HEADER_FORMAT, data, offset)
        offset += HEADER_SIZE

        if sublen >= MAX_FRAME_SIZE:
            raise ValueError(f"Subblock length too large ({sublen} bytes)")

        if offset + sublen > total_len:
            raise ValueError(f"Subblock spills over parent block boundaries ({offset + sublen} > {total_len})")

        subdata = data[offset:offset + sublen]
        offset += sublen
        blocks.append((subtag, subdata))

    return blocks


def parse_subblocks_dict(data: bytes) -> dict[bytes, bytes]:
    """Helper to convert unpacked subblocks into a dictionary."""
    blocks = unpack_subblocks(data)
    return {tag: val for tag, val in blocks}


def recv_exact(sock: socket.socket, length: int) -> bytes:
    """Reads exactly `length` bytes from a blocking socket."""
    buf = bytearray()
    while len(buf) < length:
        chunk = sock.recv(length - len(buf))
        if not chunk:
            if len(buf) == 0:
                return b""
            raise ConnectionResetError("Connection closed unexpectedly mid-frame.")
        buf.extend(chunk)
    return bytes(buf)


def read_frame(sock: socket.socket) -> tuple[bytes, bytes] | None:
    """
    Reads an outer TLV frame from a socket.
    Returns (tag, data) or None if socket closed cleanly.
    Raises ValueError if frame size >= 16 MiB.
    """
    header = recv_exact(sock, HEADER_SIZE)
    if not header:
        return None

    tag, length = struct.unpack(HEADER_FORMAT, header)
    if length >= MAX_FRAME_SIZE:
        raise ValueError(f"Frame length {length} exceeds maximum limit of {MAX_FRAME_SIZE} bytes")

    data = recv_exact(sock, length)
    return tag, data


# Specific frame builders

def pack_helo(usid: uuid.UUID, name: str, port: int) -> bytes:
    name_bytes = name.encode("utf-8")[:64]
    port_bytes = struct.pack("!H", port)
    return pack_subblocks(TAG_HELO, [
        (TAG_USID, usid.bytes),
        (TAG_NAME, name_bytes),
        (TAG_PORT, port_bytes),
    ])


def pack_chat(text: str) -> bytes:
    return pack_subblocks(TAG_CHAT, [
        (TAG_TEXT, text.encode("utf-8")),
    ])


def pack_fbeg(transfer_id: uuid.UUID, filename: str, file_size: int) -> bytes:
    fn_bytes = filename.encode("utf-8")
    size_bytes = struct.pack("!Q", file_size)
    return pack_subblocks(TAG_FBEG, [
        (TAG_FTID, transfer_id.bytes),
        (TAG_FNAM, fn_bytes),
        (TAG_SIZE, size_bytes),
    ])


def pack_fdat(transfer_id: uuid.UUID, chunk: bytes) -> bytes:
    return pack_subblocks(TAG_FDAT, [
        (TAG_FTID, transfer_id.bytes),
        (TAG_DATA, chunk),
    ])


def pack_fend(transfer_id: uuid.UUID) -> bytes:
    return pack_subblocks(TAG_FEND, [
        (TAG_FTID, transfer_id.bytes),
    ])


def pack_leav() -> bytes:
    return pack_block(TAG_LEAV, b"")


def pack_pres(usid: uuid.UUID, name: str, port: int, status: str) -> bytes:
    name_bytes = name.encode("utf-8")[:64]
    port_bytes = struct.pack("!H", port)
    stat_bytes = status.encode("utf-8")[:128]
    return pack_subblocks(TAG_PRES, [
        (TAG_USID, usid.bytes),
        (TAG_NAME, name_bytes),
        (TAG_PORT, port_bytes),
        (TAG_STAT, stat_bytes),
    ])


def pack_gbye(usid: uuid.UUID) -> bytes:
    return pack_subblocks(TAG_GBYE, [
        (TAG_USID, usid.bytes),
    ])
