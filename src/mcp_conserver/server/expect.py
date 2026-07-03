import asyncio
from typing import Any

from fastmcp import Context

from mcp_conserver.expect import ExpectEngine
from mcp_conserver.server import mcp


def _get_session(ctx: Any, session_id: str):
    store = ctx.request_context.lifespan_context.sessions
    session = store.get(session_id)
    if not session.is_connected:
        raise ValueError(
            f'Session {session_id} is disconnected.')
    return session


@mcp.tool()
async def console_expect(
    ctx: Context,
    session_id: str,
    steps: list[dict[str, Any]],
    timeout: int = 30,
) -> dict[str, Any]:
    """Run an expect script against a console session.

    Waits for patterns in the console output, sends text, and
    reports what matched. Useful for automating login sequences,
    detecting boot stages, or any interactive prompt handling.

    Args:
        session_id: Session ID from console_connect.
        steps: List of steps to execute sequentially. Each step is
            one of:
            - {"expect": "regex"} wait for a regex pattern
            - {"expect": "regex", "timeout": 10} with per-step
              timeout in seconds
            - {"expect": [{"pattern": "p1", "send": "text1"},
              {"pattern": "p2", "send": "text2"}]} multi-pattern:
              first match wins, optionally sends text on match
            - {"send": "text"} send text to the console
            - {"sleep": 1.5} wait N seconds
        timeout: Default timeout in seconds for expect steps.

    Returns:
        Result dict with status ('completed', 'timeout', 'eof',
        'error'), captured output, list of matches, and the
        failed step index if applicable.
    """
    session = _get_session(ctx, session_id)
    loop = asyncio.get_running_loop()

    def _run():
        initial_buffer = session.pause_reader()
        try:
            engine = ExpectEngine(
                session.conn.sock,
                initial_buffer=initial_buffer,
                default_timeout=timeout,
            )
            result = engine.run(steps)
            session.resume_reader(result.get('remaining_output', ''))
            return result
        except Exception as e:
            session.resume_reader(initial_buffer)
            raise

    return await loop.run_in_executor(None, _run)
