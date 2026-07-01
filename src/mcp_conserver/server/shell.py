import asyncio
from typing import Any

from fastmcp import Context

from mcp_conserver.server import mcp


def _get_session(ctx: Any, session_id: str):
    store = ctx.request_context.lifespan_context.sessions
    session = store.get(session_id)
    if not session.is_connected:
        raise ValueError(
            f'Session {session_id} is disconnected.')
    return session


@mcp.tool()
async def console_send(
    ctx: Context,
    session_id: str,
    data: str,
    press_enter: bool = True,
    wait: float = 1.0,
    read_lines: int = 100,
) -> str:
    """Send text to a console and return the output.

    Args:
        session_id: Session ID from console_connect.
        data: Text to send to the console.
        press_enter: Whether to append a newline (press Enter).
        wait: Seconds to wait for output after sending.
        read_lines: Number of tail lines to return from the
                    output buffer.

    Returns:
        Latest console output (last N lines from buffer).
    """
    session = _get_session(ctx, session_id)

    payload = data + '\n' if press_enter else data
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None, lambda: session.send(payload))

    if wait > 0:
        await asyncio.sleep(wait)

    output = await loop.run_in_executor(
        None, lambda: session.read_buffer(lines=read_lines))
    return output


@mcp.tool()
async def console_read(
    ctx: Context,
    session_id: str,
    lines: int = 100,
) -> str:
    """Read the latest output from a console session.

    Args:
        session_id: Session ID from console_connect.
        lines: Number of tail lines to return.

    Returns:
        Latest console output.
    """
    session = _get_session(ctx, session_id)

    loop = asyncio.get_running_loop()
    output = await loop.run_in_executor(
        None, lambda: session.read_buffer(lines=lines))
    return output if output.strip() else '(no output)'


@mcp.tool()
async def console_send_control(
    ctx: Context,
    session_id: str,
    key: str,
    wait: float = 1.0,
    read_lines: int = 100,
) -> str:
    """Send a control character to the console.

    Args:
        session_id: Session ID from console_connect.
        key: Control key name: 'ctrl-c', 'ctrl-d', 'ctrl-z',
             'ctrl-\\', 'enter', 'escape', or a single letter
             like 'c' for Ctrl+C.
        wait: Seconds to wait for output after sending.
        read_lines: Number of tail lines to return.

    Returns:
        Latest console output.
    """
    key_map = {
        'ctrl-c': '\x03',
        'ctrl-d': '\x04',
        'ctrl-z': '\x1a',
        'ctrl-\\': '\x1c',
        'ctrl-l': '\x0c',
        'enter': '\n',
        'escape': '\x1b',
    }

    char = key_map.get(key.lower())
    if char is None and len(key) == 1:
        char = chr(ord(key.upper()) - 64)
    if char is None:
        raise ValueError(
            f"Unknown control key '{key}'. "
            f"Use: {', '.join(key_map.keys())}")

    session = _get_session(ctx, session_id)

    loop = asyncio.get_running_loop()
    await loop.run_in_executor(
        None, lambda: session.send(char))

    if wait > 0:
        await asyncio.sleep(wait)

    output = await loop.run_in_executor(
        None, lambda: session.read_buffer(lines=read_lines))
    return output
