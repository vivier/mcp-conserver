import asyncio
import sys

import click


if sys.platform == 'win32':
    asyncio.set_event_loop_policy(
        asyncio.WindowsSelectorEventLoopPolicy())


@click.command()
@click.option(
    '--transport',
    type=click.Choice(['stdio', 'sse', 'streamable-http']),
    default='stdio')
@click.option('--host', default='0.0.0.0')
@click.option('--port', default=9820)
def main(transport: str, host: str, port: int) -> None:
    from mcp_conserver.server import mcp

    if transport == 'stdio':
        asyncio.run(mcp.run_async(transport=transport))
    else:
        asyncio.run(mcp.run_async(
            transport=transport, host=host, port=port))


if __name__ == '__main__':
    main()
