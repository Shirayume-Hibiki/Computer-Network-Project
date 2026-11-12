'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Shirayume-Hibiki          ║
║  Creation date:            12/11/26                  ║
║  Edit dates / contributor:                           ║
╚══════════════════════════════════════════════════════╝
'''

import json
import time

PROTOCOL_MAGIC: str = "LANCHAT"
MSG_BEACON: str = "BEACON"
MSG_STATUS_UPDATE: str = "STATUS_UPDATE"
MSG_GOODBYE: str = "GOODBYE"

VALID_STATUSES: set[str] = {"online", "away", "offline"}

def createBeacon(name: str, port: int, status: str = "online") -> bytes:
    payload = {
        "magic": PROTOCOL_MAGIC,
        "type": MSG_BEACON,
        "name": name,
        "port": port,
        "status": status if status in VALID_STATUSES else "online",
        "ts": time.time()
    }
    return json.dumps(payload).encode("utf-8")

def createStatusUpdate(name: str, port: int, status: str) -> bytes:
    payload = {
        "magic": PROTOCOL_MAGIC,
        "type": MSG_STATUS_UPDATE,
        "name": name,
        "port": port,
        "status": status if status in VALID_STATUSES else "online",
        "ts": time.time()
    }
    return json.dumps(payload).encode("utf-8")

def createGoodbye(name: str, port: int) -> bytes:
    payload = {
        "magic": PROTOCOL_MAGIC,
        "type": MSG_GOODBYE,
        "name": name,
        "port": port,
        "status": "offline",
        "ts": time.time()
    }
    return json.dumps(payload).encode("utf-8")

def parseDatagram(data: bytes) -> dict | None:
    try:
        raw_text = data.decode("utf-8", errors="replace")
        payload = json.loads(raw_text)
        if not isinstance(payload, dict):
            return None
        if payload.get("magic") != PROTOCOL_MAGIC:
            return None
        if "type" not in payload or "name" not in payload or "port" not in payload:
            return None
        return payload
    except Exception:
        return None
