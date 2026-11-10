"""Минимальный RCON-клиент для сервера Minecraft без внешних зависимостей.

Протокол: пакет начинается с длины (int32 little-endian), дальше идут id запроса,
тип пакета, тело в UTF-8 и два нулевых байта. Тип 3 это авторизация, 2 команда,
0 ответ. При неверном пароле сервер отвечает пакетом с id -1.
"""

from __future__ import annotations

import socket
import struct

AUTH = 3
COMMAND = 2


class RconError(Exception):
    """Ошибка связи с RCON: сервер недоступен, обрыв, таймаут."""


class RconAuthError(RconError):
    """Сервер отверг пароль RCON."""


class Rcon:
    """Подключение к RCON. Используется как контекстный менеджер."""

    def __init__(self, host: str, port: int, password: str, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.password = password
        self.timeout = timeout
        self._sock: socket.socket | None = None
        self._next_id = 1

    def connect(self) -> None:
        """Открывает соединение и авторизуется. Бросает RconError или RconAuthError."""
        try:
            self._sock = socket.create_connection((self.host, self.port), timeout=self.timeout)
            self._sock.settimeout(self.timeout)
        except OSError as e:
            self._sock = None
            raise RconError(f"cannot connect to RCON {self.host}:{self.port}: {e}") from e
        req_id = self._send(AUTH, self.password)
        while True:
            resp_id, ptype, _ = self._recv()
            if resp_id == -1:
                self.close()
                raise RconAuthError("RCON rejected the password")
            # Некоторые серверы перед ответом на авторизацию шлют пустой пакет типа 0.
            if ptype == COMMAND and resp_id == req_id:
                return

    def command(self, cmd: str) -> str:
        """Выполняет команду сервера и возвращает текст ответа."""
        if self._sock is None:
            self.connect()
        req_id = self._send(COMMAND, cmd)
        resp_id, _, text = self._recv()
        if resp_id != req_id:
            raise RconError(f"unexpected RCON response id {resp_id}, expected {req_id}")
        return text

    def close(self) -> None:
        """Закрывает соединение, если оно открыто."""
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    def __enter__(self) -> "Rcon":
        self.connect()
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _send(self, ptype: int, text: str) -> int:
        req_id = self._next_id
        self._next_id += 1
        payload = struct.pack("<ii", req_id, ptype) + text.encode("utf-8") + b"\x00\x00"
        try:
            self._sock.sendall(struct.pack("<i", len(payload)) + payload)
        except OSError as e:
            raise RconError(f"RCON send failed: {e}") from e
        return req_id

    def _recv_exact(self, n: int) -> bytes:
        buf = b""
        while len(buf) < n:
            try:
                chunk = self._sock.recv(n - len(buf))
            except OSError as e:
                raise RconError(f"RCON receive failed: {e}") from e
            if not chunk:
                raise RconError("RCON connection closed by server")
            buf += chunk
        return buf

    def _recv(self) -> tuple[int, int, str]:
        (length,) = struct.unpack("<i", self._recv_exact(4))
        body = self._recv_exact(length)
        resp_id, ptype = struct.unpack("<ii", body[:8])
        return resp_id, ptype, body[8:-2].decode("utf-8", errors="replace")
