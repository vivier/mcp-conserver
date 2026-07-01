from fastmcp import FastMCP

from mcp_conserver.lifespan import lifespan

mcp = FastMCP('mcp-conserver', lifespan=lifespan)

from mcp_conserver.server import connection, shell, query  # noqa: E402, F401
