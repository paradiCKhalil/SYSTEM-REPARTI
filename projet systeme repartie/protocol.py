import json
from datetime import datetime, timezone


class ProtocolError(ValueError):
    pass


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat()


def encode_message(payload):
    try:
        return (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ProtocolError(f"Message JSON invalide: {exc}") from exc


def send_message(sock, payload, send_lock=None):
    message = encode_message(payload)
    if send_lock is None:
        sock.sendall(message)
        return

    with send_lock:
        sock.sendall(message)


def read_messages(sock_file):
    for raw_line in sock_file:
        line = raw_line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ProtocolError(f"JSON recu invalide: {exc}") from exc

        if not isinstance(message, dict):
            raise ProtocolError("Le message recu doit etre un objet JSON")

        message_type = message.get("type")
        if not isinstance(message_type, str) or not message_type:
            raise ProtocolError("Chaque message doit contenir un champ 'type'")

        yield message