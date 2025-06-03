import ipaddress
import logging
from typing import Any, Callable, List, Literal, Optional, Type, Union, cast

import typer
from typing_extensions import Annotated

import logging
from collections.abc import Callable
from typing import Any, Generic, Iterable, Sequence

from fastmcp import Context, FastMCP, Image
from fastmcp.tools import Tool
from mcp.server.auth.provider import OAuthAuthorizationServerProvider
from mcp.server.streamable_http import EventStore
from mcp.types import AnyFunction, ToolAnnotations

from app.utils.wrappers import (
    apply_decorators,
    log_and_handle_errors,
)

from .modules import connect_to_plex, mcp

# Client module functions
from .modules.client import (
    client_control_playback,
    client_get_details,
    client_get_timelines,
    client_list,
    client_navigate,
    client_set_streams,
    client_start_playback,
    get_active_clients,
)

# Collection module functions
from .modules.collection import (
    collection_add_to,
    collection_create,
    collection_edit,
    collection_list,
    collection_remove_from,
)

# Import all tools to ensure they are registered with MCP
# Library module functions
from .modules.library import (
    library_get_contents,
    library_get_details,
    library_get_recently_added,
    library_get_stats,
    library_list,
    library_refresh,
    library_scan,
)

# Media module functions
from .modules.media import (
    media_delete,
    media_edit_metadata,
    media_get_artwork,
    media_get_details,
    media_list_available_artwork,
    media_search,
    media_set_artwork,
)

# Playlist module functions
from .modules.playlist import (
    playlist_add_to,
    playlist_copy_to_user,
    playlist_create,
    playlist_delete,
    playlist_edit,
    playlist_get_contents,
    playlist_list,
    playlist_remove_from,
    playlist_upload_poster,
)

# Server module functions
from .modules.server import (
    server_get_alerts,
    server_get_bandwidth,
    server_get_butler_tasks,
    server_get_current_resources,
    server_get_info,
    server_get_plex_logs,
    server_run_butler_task,
)

# Search module functions
from .modules.sessions import sessions_get_active, sessions_get_media_playback_history

# User module functions
from .modules.user import (
    user_get_info,
    user_get_on_deck,
    user_get_statistics,
    user_get_watch_history,
    user_search_users,
)

from .utils.wrappers import PendingMCPComponents

TransportType = Literal["stdio", "sse"]
LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]

import uvicorn  # type: ignore
from mcp.server import Server  # type: ignore
from mcp.server.sse import SseServerTransport  # type: ignore
from starlette.applications import Starlette  # type: ignore
from starlette.requests import Request  # type: ignore
from starlette.routing import Mount, Route  # type: ignore


def create_starlette_app(mcp_server: Server, *, debug: bool = False) -> Starlette:
    """Create a Starlette application that can serve the provided mcp server with SSE."""
    sse = SseServerTransport("/messages/")

    async def handle_sse(request: Request) -> None:
        async with sse.connect_sse(
            request.scope,
            request.receive,
            request._send,  # noqa: SLF001
        ) as (read_stream, write_stream):
            await mcp_server.run(
                read_stream,
                write_stream,
                mcp_server.create_initialization_options(),
            )

    return Starlette(
        debug=debug,
        routes=[
            Route("/sse", endpoint=handle_sse),
            Mount("/messages/", app=sse.handle_post_message),
        ],
    )



def validate_transport(transport: str) -> TransportType:
    if transport.lower() not in {"stdio", "sse"}:
        raise typer.BadParameter(f"Transport must be one of: STDIO, SSE")
    return cast(TransportType, transport)


def validate_ip(ip: str) -> str:
    try:
        ipaddress.IPv4Address(ip)
        return ip
    except ipaddress.AddressValueError:
        raise typer.BadParameter(f"{ip} is not a valid IPv4 address")


def validate_port(port: int | str) -> int:
    if isinstance(port, str):
        try:
            port = int(port)
        except ValueError:
            raise typer.BadParameter(f"{port} is not a valid port number")
    if not (1024 <= port <= 65535):
        raise typer.BadParameter(
            "Port must be between 1024 and 65535 (non-privileged range)"
        )
    return port


def validate_log_level(level: str) -> str:
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if level.upper() not in valid_levels:
        raise typer.BadParameter(f"Log level must be one of: {', '.join(valid_levels)}")
    return level.upper()


def run(
    transport: Annotated[
        TransportType,
        typer.Argument(
            show_default=True,
            show_choices=True,
            help="Run the MCP server in stdio mode or sse mode.",
            default="STDIO",
            envvar="TRANSPORT",
            parser=validate_transport,
        ),
    ],
    host: Annotated[
        str,
        typer.Argument(
            show_default=True,
            help="Host to bind to (for SSE).",
            default="0.0.0.0",
            envvar="HOST",
            parser=validate_ip,
        ),
    ],
    port: Annotated[
        int,
        typer.Argument(
            show_default=True,
            help="Port to listen on (for SSE).",
            default=3000,
            envvar="PORT",
            parser=validate_port,
        ),
    ],
    log_level: Annotated[
        LogLevel,
        typer.Argument(
            show_default=True,
            help="The level of logging to use.",
            default="INFO",
            envvar="LOG_LEVEL",
            parser=validate_log_level,
        ),
    ],
) -> None:
    """
    Start the Plex MCP server with the given arguments.
    """
    logging.basicConfig(
        level=log_level, format="%(asctime)s - %(levelname)s - %(message)s"
    )
    logger = logging.getLogger(__name__)

    logger.info(
        f"Starting MCP server with transport={transport}, host={host}, port={port}, log_level={log_level}"
    )
    app = PlexMCP(transport=transport, host=host, port=port, log_level=log_level)
    PendingMCPComponents.instance().process(app)

    if transport == "stdio":
        # Run with stdio transport (original method)
        mcp.run(transport="stdio")
    else:
        # Run with SSE transport
        starlette_app = create_starlette_app(app._mcp_server, debug=log_level=="DEBUG")
        print(f"Starting SSE server on http://{host}:{port}")
        print("Access the SSE endpoint at /sse")
        uvicorn.run(starlette_app, host=host, port=port)



class PlexMCP(FastMCP):
    """MCP Server for Plex."""

    _logger = logging.getLogger("PlexMCP")

    def __init__(
        self,
        name: str | None = None,
        instructions: str | None = None,
        auth_server_provider: (
            OAuthAuthorizationServerProvider[Any, Any, Any] | None
        ) = None,
        event_store: EventStore | None = None,
        *,
        tools: list[Tool | Callable[..., Any]] | None = None,
        **settings: Any,
    ) -> None:
        super().__init__(
            name=name,
            instructions=instructions,
            auth_server_provider=auth_server_provider,
            event_store=event_store,
            tools=tools,
            **settings,
        )
        self.logger = logging.getLogger(__name__)
        self.logger.info("server initialize")

    def tool(
        self,
        name: str,
        description: str,
        annotations: ToolAnnotations | None = None,
    ) -> Callable[[AnyFunction], AnyFunction]:
        """Register a tool with the server."""
        return apply_decorators(
            super().tool(
                name=name,
                description=description,
                annotations=annotations or ToolAnnotations(),
            ),
            log_and_handle_errors,
        )

    def resource(
        self,
        uri: str,
        *,
        name: str | None = None,
        description: str | None = None,
        mime_type: str | None = None,
    ) -> Callable[[AnyFunction], AnyFunction]:
        """Register a resource with the server."""
        return apply_decorators(
            super().resource(
                uri,
                name=name,
                description=description,
                mime_type=mime_type,
            ),
            log_and_handle_errors,
        )

    def prompt(
        self, name: str | None = None, description: str | None = None
    ) -> Callable[[AnyFunction], AnyFunction]:
        """Register a prompt with the server."""
        return apply_decorators(
            super().prompt(name=name, description=description),
            log_and_handle_errors,
        )

    def custom_route(
        self,
        path: str,
        methods: list[str],
        name: str | None = None,
        include_in_schema: bool = True,
    ) -> Callable[[AnyFunction], AnyFunction]:
        """Register a route with the server."""
        return apply_decorators(
            super().custom_route(
                path,
                methods=methods,
                name=name,
                include_in_schema=include_in_schema,
            ),
            log_and_handle_errors,
        )


if __name__ == "__main__":
    typer.run(run)
