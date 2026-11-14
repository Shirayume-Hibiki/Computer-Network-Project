'''
╔══════════════════════════════════════════════════════╗
║  Creator:                  Shirayume-Hibiki          ║
║  Creation date:            12/11/26                  ║
║  Edit dates / contributor:                           ║
║  13/11/26 Shirayume-Hibiki                           ║
║  14/11/26 Shirayume-Hibiki                           ║
╚══════════════════════════════════════════════════════╝
'''

import json
import time

PROTOCOL_MAGIC: str = "LANCHAT"
MSG_BEACON: str = "BEACON"
MSG_STATUS_UPDATE: str = "STATUS_UPDATE"
MSG_GOODBYE: str = "GOODBYE"

VALID_STATUSES: set[str] = {"online", "away", "offline"}

def createBeacon(name: str, port: int, status: str = "online", node_id: str = "") -> bytes:
    payload = {
        "magic": PROTOCOL_MAGIC,
        "type": MSG_BEACON,
        "node_id": node_id,
        "name": name,
        "port": port,
        "status": status if status in VALID_STATUSES else "online",
        "ts": time.time()
    }
    return json.dumps(payload).encode("utf-8")

def createStatusUpdate(name: str, port: int, status: str, node_id: str = "") -> bytes:
    payload = {
        "magic": PROTOCOL_MAGIC,
        "type": MSG_STATUS_UPDATE,
        "node_id": node_id,
        "name": name,
        "port": port,
        "status": status if status in VALID_STATUSES else "online",
        "ts": time.time()
    }
    return json.dumps(payload).encode("utf-8")

def createGoodbye(name: str, port: int, node_id: str = "") -> bytes:
    payload = {
        "magic": PROTOCOL_MAGIC,
        "type": MSG_GOODBYE,
        "node_id": node_id,
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

        # Validate message type
        msg_type = payload.get("type")
        if msg_type not in (MSG_BEACON, MSG_STATUS_UPDATE, MSG_GOODBYE):
            return None

        # Validate username length and type
        name = payload.get("name")
        if not isinstance(name, str) or not (1 <= len(name.strip()) <= 32):
            return None
        payload["name"] = name.strip()

        # Validate TCP port strictly within 1..65535
        raw_port = payload.get("port")
        try:
            port = int(raw_port)
            if not (1 <= port <= 65535):
                return None
            payload["port"] = port
        except (ValueError, TypeError):
            return None

        # Enforce strict validation on status field
        status = payload.get("status")
        if not isinstance(status, str) or status not in VALID_STATUSES:
            payload["status"] = "online"
            
        return payload
    except Exception:
        return None
