import socket
import struct
import threading
import time

import pytest

from stand.rcon import Rcon, RconAuthError, RconError


def _read_packet(conn):
    raw = b""
    while len(raw) < 4:
        raw += conn.recv(4 - len(raw))
    (length,) = struct.unpack("<i", raw)
    body = b""
    while len(body) < length:
        body += conn.recv(length - len(body))
    req_id, ptype = struct.unpack("<ii", body[:8])
    return req_id, ptype, body[8:-2].decode("utf-8")


def _send_packet(conn, req_id, ptype, text):
    payload = struct.pack("<ii", req_id, ptype) + text.encode("utf-8") + b"\x00\x00"
    conn.sendall(struct.pack("<i", len(payload)) + payload)


def _fake_server(password, replies):
    """Поднимает фейковый RCON-сервер на одно подключение и возвращает его порт."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]

    def serve():
        conn, _ = srv.accept()
        with conn:
            req_id, ptype, text = _read_packet(conn)
            assert ptype == 3
            _send_packet(conn, req_id if text == password else -1, 2, "")
            if text != password:
                return
            while True:
                try:
                    req_id, ptype, text = _read_packet(conn)
                except (ConnectionError, struct.error, OSError):
                    return
                _send_packet(conn, req_id, 0, replies.get(text, ""))
        srv.close()

    threading.Thread(target=serve, daemon=True).start()
    return port


def test_auth_and_command():
    port = _fake_server("pw", {"list": "There are 0/20 players online:"})
    with Rcon("127.0.0.1", port, "pw") as rcon:
        assert rcon.command("list") == "There are 0/20 players online:"


def test_wrong_password_raises_auth_error():
    port = _fake_server("pw", {})
    with pytest.raises(RconAuthError):
        Rcon("127.0.0.1", port, "bad").connect()


def test_no_server_times_out():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    port = srv.getsockname()[1]
    srv.close()
    start = time.monotonic()
    with pytest.raises(RconError):
        Rcon("127.0.0.1", port, "pw", timeout=1.0).connect()
    assert time.monotonic() - start < 2.0
