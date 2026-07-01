"""
libconserver - Python client library for connecting to a conserver daemon.

Implements the conserver text protocol: connection, SSL/TLS, GSSAPI/Kerberos
authentication, command dispatch with redirect following, and session setup.
"""

import os
import re
import socket
import ssl
import sys

try:
    import gssapi
    HAS_GSSAPI = True
except ImportError:
    HAS_GSSAPI = False

DEFAULT_PORT = 782
DEFAULT_MASTER = "console"
DEFATTN = 0x05  # Ctrl-E
DEFESC = ord('c')
OB_IAC = 0xFF
MAX_REDIRECT_DEPTH = 10


def parse_escape(text):
    def parse_char(s, pos):
        cvt = 0
        if pos + 1 < len(s) and s[pos] == 'M' and s[pos + 1] == '-':
            cvt = 0x80
            pos += 2
        if pos >= len(s):
            return None, pos
        if s[pos] == '^':
            pos += 1
            if pos >= len(s):
                return None, pos
            c = s[pos].upper()
            pos += 1
            if '@' <= c <= '_':
                return cvt | (ord(c) - ord('@')), pos
            elif c == '?':
                return cvt | 0x7f, pos
            return None, pos
        c = ord(s[pos])
        pos += 1
        return cvt | c, pos

    c1, pos = parse_char(text, 0)
    if c1 is None:
        raise ValueError(f"poorly formed escape sequence '{text}'")
    c2, pos = parse_char(text, pos)
    if c2 is None:
        raise ValueError(f"poorly formed escape sequence '{text}'")
    if pos != len(text):
        raise ValueError(f"too many characters in escape sequence '{text}'")
    return c1, c2


class ConserverError(Exception):
    pass


class ConserverConnection:
    def __init__(self, debug=False, sslcredentials=None):
        self.sock = None
        self.debug = debug
        self.sslcredentials = sslcredentials
        self.attn = DEFATTN
        self.esc = DEFESC
        self.sversion = 0
        self._recvbuf = b""

    def _debug(self, msg):
        if self.debug:
            print(f"DEBUG: {msg}", file=sys.stderr)

    def connect(self, host, port):
        self._debug(f"connecting to {host}:{port}")
        if self.sock:
            self.sock.close()
            self.sock = None
        self._recvbuf = b""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        s.connect((host, port))
        self.sock = s

    def close(self):
        if self.sock:
            self.sock.close()
            self.sock = None

    def send(self, data):
        if isinstance(data, str):
            data = data.encode()
        self.sock.sendall(data)

    def send_cmd(self, cmd):
        self._debug(f"send: {cmd.strip()}")
        self.send(cmd)

    def read_reply(self):
        while b"\n" not in self._recvbuf:
            chunk = self.sock.recv(4096)
            if not chunk:
                if self._recvbuf:
                    break
                raise ConserverError("lost connection")
            self._recvbuf += chunk
        idx = self._recvbuf.find(b"\n")
        if idx >= 0:
            line = self._recvbuf[:idx + 1]
            self._recvbuf = self._recvbuf[idx + 1:]
        else:
            line = self._recvbuf
            self._recvbuf = b""
        reply = line.decode(errors="replace")
        self._debug(f"recv: {reply.strip()}")
        return reply

    def negotiate_ssl(self):
        self.send_cmd("ssl\r\n")
        reply = self.read_reply()
        if reply.strip() != "ok":
            return False
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        if self.sslcredentials:
            try:
                ctx.load_cert_chain(self.sslcredentials)
            except (FileNotFoundError, ssl.SSLError) as e:
                raise ConserverError(
                    f"could not load SSL credentials "
                    f"'{self.sslcredentials}': {e}")
            ctx.set_ciphers(
                "ALL:!LOW:!EXP:!MD5:@STRENGTH:@SECLEVEL=0")
        else:
            ctx.set_ciphers(
                "ALL:aNULL:!LOW:!EXP:!MD5:@STRENGTH:@SECLEVEL=0")
        self.sock = ctx.wrap_socket(self.sock)
        self._debug("SSL negotiated")
        return True

    def negotiate_gssapi(self, server):
        if not HAS_GSSAPI:
            return False
        try:
            hostname = socket.getfqdn(server)
            self._debug(f"GSSAPI target: host@{hostname}")
            name = gssapi.Name(f"host@{hostname}",
                               gssapi.NameType.hostbased_service)
            ctx = gssapi.SecurityContext(
                name=name, usage="initiate",
                flags=[gssapi.RequirementFlag.mutual_authentication])
            token = ctx.step()
            if token is None or len(token) == 0:
                return False
        except gssapi.exceptions.GSSError:
            return False

        self.send_cmd(f"gssapi {len(token)}\r\n")
        reply = self.read_reply()
        if reply.strip() != "ok":
            return False

        self.sock.sendall(bytes(token))
        server_tok = self.sock.recv(65536)
        try:
            ctx.step(server_tok)
        except gssapi.exceptions.GSSError:
            return False

        if not ctx.complete:
            return False
        self._debug("GSSAPI authenticated")
        return True

    def login(self, username, password=None):
        self.send_cmd(f"login {username}\r\n")
        reply = self.read_reply()
        if reply.startswith("passwd?"):
            hostname = reply[7:].strip() or "server"
            if password is None:
                raise ConserverError(f"password required for "
                                     f"{username}@{hostname}")
            self.send_cmd(f"{password}\r\n")
            reply = self.read_reply()
            if reply.strip() != "ok":
                raise ConserverError(
                    f"login failed: {reply.strip()}")
        elif reply.strip() != "ok":
            raise ConserverError(f"login failed: {reply.strip()}")
        self._debug(f"logged in as {username}")

    def connect_and_auth(self, host, port, username, password=None,
                         password_callback=None):
        for attempt in range(3):
            self.connect(host, port)

            reply = self.read_reply()
            if reply.strip() != "ok":
                raise ConserverError(
                    f"server rejected: {reply.strip()}")

            self.negotiate_ssl()

            if self.negotiate_gssapi(host):
                return

            try:
                self.login(username, password)
                return
            except ConserverError:
                if password_callback and attempt < 2:
                    password = password_callback(username, host)
                    self.close()
                    continue
                raise

    def call_console(self, master, port, console, username, mode,
                     replay=False, password=None,
                     password_callback=None):
        depth = 0
        host = master
        ports_str = f"@{master}"

        while depth < MAX_REDIRECT_DEPTH:
            server, cport = self._parse_port_spec(
                ports_str, host, port)
            self.connect_and_auth(server, cport, username, password,
                                  password_callback)

            self.send_cmd(f"call {console}\r\n")
            reply = self.read_reply()

            if (reply[0] == '@' or
                    (reply[0].isdigit()
                     and not reply.startswith('['))):
                self.send_cmd("exit\r\n")
                try:
                    self.read_reply()
                except ConserverError:
                    pass
                self.close()

                ports_str = reply.strip()
                host = server
                depth += 1
                continue

            if not reply.startswith('['):
                raise ConserverError(
                    f"{server}: {reply.strip()}")

            self._debug(
                f"attachment response: {reply.strip()}")
            motd = self._session_setup()

            result = reply.strip()
            got = 'a' if result == "[attached]" else 's'
            if mode != got and result not in (
                    "[console is read-only]",
                    "[line to console is down]"):
                self._debug(f"switching to mode '{mode}'")
                self.send(bytes([self.attn, self.esc,
                                 ord(mode)]))

            if replay:
                self._debug("requesting replay")
                self.send(bytes([self.attn, self.esc,
                                 ord('r')]))

            return result, motd

        raise ConserverError("too many redirects")

    def run_command(self, master, port, username, cmds,
                    cmdarg=None, password=None,
                    password_callback=None, callback=None):
        results = []
        self._do_cmds(master, f"@{master}", port, username,
                      cmds, len(cmds) - 1, cmdarg, password,
                      password_callback, results, callback)
        return results

    def _do_cmds(self, master, ports_str, default_port, username,
                 cmds, cmdi, cmdarg, password, password_callback,
                 results, callback=None):
        for server, cport in self._parse_ports(
                ports_str, master, default_port):
            try:
                self.connect_and_auth(server, cport, username,
                                      password, password_callback)
            except (ConserverError, EOFError, OSError) as e:
                self._debug(f"connect failed: {e}")
                continue

            cmd = cmds[cmdi]
            if cmd == "call" and cmdarg:
                self.send_cmd(f"call {cmdarg}\r\n")
                reply = self.read_reply().strip()

                if (reply.startswith('@') or
                        (reply[0].isdigit()
                         and not reply.startswith('['))):
                    self.send_cmd("exit\r\n")
                    try:
                        self.read_reply()
                    except ConserverError:
                        pass
                    self.close()
                    self._do_cmds(
                        server, reply, default_port, username,
                        cmds, cmdi, cmdarg, password,
                        password_callback, results, callback)
                elif reply.startswith('[') and cmdi > 0:
                    self.send(bytes([DEFATTN, DEFESC,
                                     ord('.')]))
                    try:
                        self._read_to_close()
                    except (OSError, ssl.SSLError):
                        pass
                    self.close()
                    port_spec = f"{cport}@{server}"
                    self._do_cmds(
                        server, port_spec, default_port,
                        username, cmds, cmdi - 1, cmdarg,
                        password, password_callback, results,
                        callback)
                else:
                    self.close()
                    results.append((server, reply))
                    if callback:
                        callback(server, reply)
                return

            if cmdi != 0:
                self.send_cmd(f"{cmd}\r\n")

            if cmdi == 0:
                if cmdarg:
                    both = f"{cmd} {cmdarg}\r\nexit\r\n"
                else:
                    both = f"{cmd}\r\nexit\r\n"
                self._debug(f"send: {cmd} (+ exit)")
                self.send(both)
                reply = self._read_to_close()
                reply = reply.rstrip('\r\n')
                if reply.endswith("goodbye"):
                    reply = reply[:-len("goodbye")].rstrip(
                        '\r\n')
                self.close()
                results.append((server, reply))
                if callback:
                    callback(server, reply)
            else:
                reply = self.read_reply()
                self.send_cmd("exit\r\n")
                try:
                    self.read_reply()
                except ConserverError:
                    pass
                self.close()
                self._do_cmds(
                    server, reply, default_port, username,
                    cmds, cmdi - 1, cmdarg, password,
                    password_callback, results, callback)

    def _read_to_close(self):
        buf = self._recvbuf
        self._recvbuf = b""
        while True:
            try:
                chunk = self.sock.recv(4096)
            except (OSError, ssl.SSLError):
                break
            if not chunk:
                break
            buf += chunk
        return buf.decode(errors="replace")

    def _parse_ports(self, ports_str, default_host, default_port):
        ports_str = ports_str.strip().rstrip('\r\n')
        entries = []
        for entry in ports_str.split(':'):
            if not entry:
                continue
            if '@' in entry:
                p, s = entry.split('@', 1)
                server = s if s else default_host
            else:
                p = entry
                server = default_host
            if not p:
                cport = default_port
            else:
                cport = int(p)
            entries.append((server, cport))
        return entries if entries else [(default_host, default_port)]

    def _parse_port_spec(self, ports_str, default_host,
                         default_port):
        entries = self._parse_ports(ports_str, default_host,
                                    default_port)
        return entries[0] if entries else (default_host,
                                           default_port)

    def _session_setup(self):
        attn = self.attn
        esc = self.esc

        self.send(bytes([attn, esc, ord('=')]))
        reply = self.read_reply()
        self._debug(f"state: {reply.strip()}")

        self.send(bytes([attn, esc, 0xD6]))
        reply = self.read_reply()
        if not reply.startswith("[unknown"):
            try:
                self.sversion = int(
                    reply.strip().strip('[]'))
            except ValueError:
                pass
        self._debug(f"server version: {self.sversion}")

        self.send(bytes([attn, esc, ord('m')]))
        reply = self.read_reply()
        motd = None
        if (not reply.startswith("[unknown") and
                not reply.startswith("[-- MOTD --]\r\n")):
            motd = reply.rstrip('\r\n')

        self.send(bytes([attn, esc, ord(';')]))
        reply = self.read_reply()

        return motd

    @staticmethod
    def strip_iac(data):
        out = bytearray()
        i = 0
        while i < len(data):
            if data[i] == OB_IAC:
                i += 1
                if i >= len(data):
                    break
                if data[i] == OB_IAC:
                    out.append(OB_IAC)
                i += 1
            else:
                out.append(data[i])
                i += 1
        return bytes(out)
