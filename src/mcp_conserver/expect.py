import re
import socket
import ssl
import time
from typing import Any

from mcp_conserver.libconserver import ConserverConnection


class ExpectEngine:
    def __init__(self, sock, initial_buffer: str = '',
                 default_timeout: float = 30):
        self.sock = sock
        self.buffer = initial_buffer
        self.default_timeout = default_timeout
        self.output = initial_buffer
        self.matches: list[dict[str, Any]] = []

    def run(self, steps: list[dict[str, Any]]) -> dict[str, Any]:
        for i, step in enumerate(steps):
            if 'expect' in step:
                result = self._do_expect(i, step)
                if result['status'] != 'matched':
                    return {
                        'status': result['status'],
                        'output': self.output,
                        'matches': self.matches,
                        'failed_step': i,
                        'remaining_output': self.buffer,
                    }
            elif 'send' in step:
                self._do_send(step['send'])
            elif 'sleep' in step:
                time.sleep(step['sleep'])
            else:
                return {
                    'status': 'error',
                    'output': self.output,
                    'matches': self.matches,
                    'failed_step': i,
                    'remaining_output': self.buffer,
                    'error': f'unknown step type: {step}',
                }

        return {
            'status': 'completed',
            'output': self.output,
            'matches': self.matches,
            'failed_step': None,
            'remaining_output': self.buffer,
        }

    def _do_expect(self, step_index: int,
                   step: dict[str, Any]) -> dict[str, str]:
        timeout = step.get('timeout', self.default_timeout)
        raw = step['expect']

        if isinstance(raw, str):
            branches = [{'pattern': raw}]
        else:
            branches = raw

        compiled = []
        for b in branches:
            try:
                compiled.append((re.compile(b['pattern']), b))
            except re.error as e:
                return {'status': 'error',
                        'error': f"bad regex '{b['pattern']}': {e}"}

        deadline = time.monotonic() + timeout
        orig_timeout = self.sock.gettimeout()
        self.sock.settimeout(0.1)

        try:
            while True:
                for regex, spec in compiled:
                    m = regex.search(self.buffer)
                    if m:
                        before = self.buffer[:m.start()]
                        matched = m.group()
                        self.buffer = self.buffer[m.end():]

                        match_info = {
                            'step': step_index,
                            'pattern': spec['pattern'],
                            'matched': matched,
                            'before': before,
                        }
                        self.matches.append(match_info)

                        if 'send' in spec:
                            self._do_send(spec['send'])

                        return {'status': 'matched'}

                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return {'status': 'timeout'}

                try:
                    data = self.sock.recv(4096)
                except (socket.timeout, TimeoutError):
                    continue
                except (OSError, ssl.SSLError):
                    return {'status': 'eof'}

                if not data:
                    return {'status': 'eof'}

                text = ConserverConnection.strip_iac(
                    data).decode(errors='replace')
                self.buffer += text
                self.output += text
        finally:
            self.sock.settimeout(orig_timeout)

    def _do_send(self, text: str) -> None:
        self.sock.sendall(text.encode())
