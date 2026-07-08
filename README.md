# mcp-conserver

MCP server for interacting with serial consoles managed by a
[conserver](https://www.conserver.com/) daemon.

Allows AI agents (e.g. Claude) to connect to serial consoles, send
commands, read output, and manage console sessions through the
[Model Context Protocol](https://modelcontextprotocol.io/).

## Features

- **Connect** to a console in attach, spy (read-only), or force mode
- **Send** commands and read output interactively
- **Send control characters** (Ctrl-C, Ctrl-D, etc.)
- **Expect scripting** for automated interaction (wait for patterns, branch on output)
- **Query** who is connected to consoles
- **Disconnect** users from consoles
- **SSL/TLS** and **GSSAPI/Kerberos** authentication
- **Multiple transports**: stdio, SSE, and streamable-http

## Installation

```bash
pip install mcp-conserver
```

Or install from source:

```bash
git clone https://github.com/vivier/mcp-conserver.git
cd mcp-conserver
python -m venv venv
source venv/bin/activate
pip install -e .
```

## Configuration

The server reads `~/.consolerc` for default master server, port,
and username:

```
config * {
  master conserver.example.com;
  port 782;
  username myuser;
}
```

All defaults can be overridden per tool call.

## Usage with Claude Code

Add to `.mcp.json` in your project directory (see
`mcp.json.example`):

```json
{
  "mcpServers": {
    "conserver": {
      "command": "mcp-conserver"
    }
  }
}
```

To use SSE or streamable-http transport instead of stdio:

```bash
mcp-conserver --transport sse --host 0.0.0.0 --port 9820
```

## Tools

| Tool | Description |
|------|-------------|
| `console_connect` | Connect to a console (attach/spy/force) |
| `console_close` | Disconnect and close a session |
| `console_list_sessions` | List active sessions |
| `console_send` | Send text and return output |
| `console_read` | Read latest console output |
| `console_send_control` | Send control characters (Ctrl-C, Ctrl-D, etc.) |
| `console_expect` | Run expect-like scripts (wait for patterns, send on match) |
| `console_who` | Show who is connected |

## Architecture

Uses `libconserver.py`, a pure Python implementation of the conserver
client protocol, supporting SSL/TLS (anonymous DH), GSSAPI/Kerberos
authentication, and multi-hop server redirects.

Each console session runs a background reader thread that continuously
drains the socket into a buffer, ensuring no data is lost between
tool calls.

## License

GPLv2 - see [LICENSE](LICENSE).
