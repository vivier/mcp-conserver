from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator

from fastmcp import FastMCP

from mcp_conserver.session import SessionStore


@dataclass
class LifespanContext:
    sessions: SessionStore


@asynccontextmanager
async def lifespan(app: FastMCP) -> AsyncIterator[LifespanContext]:
    ctx = LifespanContext(sessions=SessionStore())
    try:
        yield ctx
    finally:
        for info in ctx.sessions.list_all():
            sid = info['session_id']
            session = ctx.sessions.get(sid)
            session.close()
