import asyncio
from typing import Any

from fastmcp import Context

from mcp_conserver.libconserver import ConserverConnection, ConserverError
from mcp_conserver.session import (
    ConserverSession, RC_MASTER, RC_PORT, RC_USERNAME,
)
from mcp_conserver.server import mcp


def _get_store(ctx: Any):
    return ctx.request_context.lifespan_context.sessions


@mcp.tool()
async def console_connect(
    ctx: Context,
    console: str,
    master: str = RC_MASTER,
    port: int = RC_PORT,
    username: str = RC_USERNAME,
    mode: str = 'attach',
) -> dict[str, Any]:
    """Connect to a serial console via conserver.

    Args:
        console: Console name (e.g. 'myhost.example.com').
        master: Conserver master server hostname.
        port: Conserver port.
        username: Username for authentication.
        mode: Connection mode - 'attach' (read-write), 'spy' (read-only),
              or 'force' (take over read-write from other users).

    Returns:
        Session info with session_id to use in subsequent calls.
    """
    mode_map = {'attach': 'a', 'spy': 's', 'force': 'f'}
    m = mode_map.get(mode, mode)
    if m not in ('a', 's', 'f'):
        raise ValueError(
            f"Invalid mode '{mode}'. "
            f"Use 'attach', 'spy', or 'force'.")

    conn = ConserverConnection()
    session = ConserverSession(
        console=console, master=master, conn=conn, mode=m)

    loop = asyncio.get_running_loop()

    def _connect():
        result, motd = conn.call_console(
            master, port, console, username, m)
        session.motd = motd or ''
        conn.sock.settimeout(0.5)
        session.start_reader()
        return result

    result = await loop.run_in_executor(None, _connect)

    store = _get_store(ctx)
    await store.add(session)

    await asyncio.sleep(0.5)

    info = session.summary()
    info['result'] = result
    if session.motd:
        info['motd'] = session.motd
    initial = await loop.run_in_executor(
        None, lambda: session.read_buffer(lines=20))
    if initial.strip():
        info['initial_output'] = initial
    return info


@mcp.tool()
async def console_list_sessions(
    ctx: Context,
) -> list[dict[str, Any]]:
    """List all active console sessions.

    Returns:
        List of session summaries with session_id, console name,
        and connection status.
    """
    store = _get_store(ctx)
    return store.list_all()


@mcp.tool()
async def console_close(
    ctx: Context,
    session_id: str,
) -> str:
    """Close a console session and disconnect.

    Args:
        session_id: Session ID returned by console_connect.

    Returns:
        Confirmation message.
    """
    store = _get_store(ctx)
    session = store.get(session_id)
    console = session.console
    session.close()
    await store.remove(session_id)
    return f'Session {session_id} ({console}) closed.'
