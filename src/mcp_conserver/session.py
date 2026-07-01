import asyncio
import os
import re
import ssl
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from mcp_conserver.libconserver import (
    ConserverConnection, ConserverError, DEFATTN, DEFESC,
    DEFAULT_PORT, DEFAULT_MASTER,
)


def read_consolerc():
    config = {}
    rc = os.path.expanduser("~/.consolerc")
    if not os.path.exists(rc):
        return config
    with open(rc) as f:
        text = f.read()
    m = re.search(r'master\s+([^;\s]+)', text)
    if m:
        config['master'] = m.group(1)
    m = re.search(r'username\s+([^;\s]+)', text)
    if m:
        config['username'] = m.group(1)
    m = re.search(r'port\s+([^;\s]+)', text)
    if m:
        config['port'] = m.group(1)
    return config


_rc = read_consolerc()
RC_MASTER = _rc.get('master', DEFAULT_MASTER)
RC_PORT = int(_rc.get('port', DEFAULT_PORT))
RC_USERNAME = _rc.get('username', '')
if not RC_USERNAME:
    try:
        RC_USERNAME = os.getlogin()
    except OSError:
        RC_USERNAME = 'unknown'


@dataclass
class ConserverSession:
    session_id: str = field(
        default_factory=lambda: uuid.uuid4().hex[:8])
    console: str = ''
    master: str = ''
    mode: str = 'a'
    connected_at: float = field(default_factory=time.time)
    conn: ConserverConnection = field(
        default_factory=ConserverConnection, repr=False)
    motd: str = field(default='', repr=False)

    _buffer: str = field(default='', repr=False)
    _lock: threading.Lock = field(
        default_factory=threading.Lock, repr=False)
    _reader_thread: threading.Thread | None = field(
        default=None, repr=False)
    _stop_event: threading.Event = field(
        default_factory=threading.Event, repr=False)

    @property
    def is_connected(self) -> bool:
        return (self.conn.sock is not None
                and not self._stop_event.is_set())

    def start_reader(self) -> None:
        self._stop_event.clear()
        self._reader_thread = threading.Thread(
            target=self._reader_loop, daemon=True)
        self._reader_thread.start()

    def _reader_loop(self) -> None:
        sock = self.conn.sock
        while not self._stop_event.is_set():
            try:
                data = sock.recv(4096)
            except socket.timeout:
                continue
            except (OSError, ssl.SSLError):
                break
            if not data:
                break
            text = ConserverConnection.strip_iac(data).decode(
                errors='replace')
            with self._lock:
                self._buffer += text
                if len(self._buffer) > 500_000:
                    self._buffer = self._buffer[-500_000:]

    def send(self, data: str) -> None:
        if not self.is_connected:
            raise ConserverError('session not connected')
        if isinstance(data, str):
            data = data.encode()
        self.conn.sock.sendall(data)

    def read_buffer(self, lines: int = 100) -> str:
        with self._lock:
            all_lines = self._buffer.splitlines()
            tail = (all_lines[-lines:]
                    if len(all_lines) > lines else all_lines)
            return '\n'.join(tail)

    def read_new(self) -> str:
        with self._lock:
            data = self._buffer
            self._buffer = ''
            return data

    def close(self) -> None:
        self._stop_event.set()
        if self.conn.sock:
            try:
                self.conn.send(
                    bytes([DEFATTN, DEFESC, ord('.')]))
            except (OSError, ssl.SSLError):
                pass
        self.conn.close()
        if self._reader_thread and self._reader_thread.is_alive():
            self._reader_thread.join(timeout=2)

    def summary(self) -> dict[str, Any]:
        return {
            'session_id': self.session_id,
            'console': self.console,
            'master': self.master,
            'mode': self.mode,
            'connected': self.is_connected,
        }


class SessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, ConserverSession] = {}
        self._lock = asyncio.Lock()

    async def add(self, session: ConserverSession) -> None:
        async with self._lock:
            self._sessions[session.session_id] = session

    def get(self, session_id: str) -> ConserverSession:
        session = self._sessions.get(session_id)
        if session is None:
            available = (', '.join(self._sessions.keys())
                         or 'none')
            raise ValueError(
                f'Session not found: {session_id}. '
                f'Active: {available}.')
        return session

    async def remove(
            self, session_id: str) -> ConserverSession | None:
        async with self._lock:
            return self._sessions.pop(session_id, None)

    def list_all(self) -> list[dict[str, Any]]:
        return [s.summary() for s in self._sessions.values()]
