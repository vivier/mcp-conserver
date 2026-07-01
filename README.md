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
- **Query** who is connected to consoles
- **Disconnect** users from consoles
- **SSL/TLS** and **GSSAPI/Kerberos** authentication

## Installation

```bash
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

Activate the virtual environment before starting Claude Code:

```bash
source /path/to/mcp-conserver/venv/bin/activate
claude
```

Then add to `.mcp.json` in your project directory (see
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

## Tools

| Tool | Description |
|------|-------------|
| `console_connect` | Connect to a console (attach/spy/force) |
| `console_close` | Disconnect and close a session |
| `console_list_sessions` | List active sessions |
| `console_send` | Send text and return output |
| `console_read` | Read latest console output |
| `console_send_control` | Send control characters |
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
