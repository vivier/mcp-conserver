import asyncio
from typing import Any

from fastmcp import Context

from mcp_conserver.libconserver import ConserverConnection
from mcp_conserver.session import RC_MASTER, RC_PORT, RC_USERNAME
from mcp_conserver.server import mcp


@mcp.tool()
async def console_who(
    ctx: Context,
    master: str = RC_MASTER,
    port: int = RC_PORT,
    username: str = RC_USERNAME,
    console: str = '',
) -> str:
    """Show who is connected to consoles.

    Args:
        master: Conserver master server hostname.
        port: Conserver port.
        username: Username for authentication.
        console: Optional console name to filter. If empty,
                 shows all connected users across all consoles.

    Returns:
        List of connected users and their consoles.
    """
    conn = ConserverConnection()
    loop = asyncio.get_running_loop()

    lines = []

    def _collect(server, reply):
        if reply:
            lines.append(reply)

    def _run():
        if console:
            cmds = ["group", "call"]
            cmdarg = console
        else:
            cmds = ["group", "groups", "master"]
            cmdarg = None
        conn.run_command(
            master, port, username, cmds,
            cmdarg=cmdarg, callback=_collect)

    await loop.run_in_executor(None, _run)
    conn.close()

    return '\n'.join(lines) if lines else '(no users connected)'
