"""
Client-related functions for Plex Media Server.
Provides tools to connect to clients and control media playback.
"""

import asyncio
import json
import time
from re import A
from typing import Annotated, Any, Dict, List, Literal, Optional, Union
from urllib.parse import urljoin

import httpx
from mcp.types import AnyFunction, ToolAnnotations
from plexapi.base import MediaContainer
from plexapi.exceptions import NotFound  # type: ignore
from plexapi.media import Session
from pydantic import Field

from app.modules import connect_to_plex, mcp
from app.utils.wrappers import tool_metadata


@tool_metadata(
    name="list_plex_clients",
    description="List all Plex clients currently connected to the server",
    annotations=ToolAnnotations(
        title="List Plex Clients",
        readOnlyHint=True,
    ),
)
async def client_list(
    include_details: Annotated[
        bool,
        Field(
            title="Include Client Details",
            description="Whether to include detailed information about each client.",
            default=False,
            examples=[True, False],
        ),
    ],
) -> str:
    """List all available Plex clients connected to the server.

    Args:
        include_details: Whether to include detailed information about each client

    Returns:
        List of client names or detailed info dictionaries
    """
    try:
        plex = connect_to_plex()
        clients = plex.clients()

        # Also get session clients which may not appear in clients()
        sessions: MediaContainer = plex.sessions()
        session_clients = []

        # Extract clients from sessions
        for session in sessions:
            if hasattr(session, "player") and session.player:
                session_clients.append(session.player)

        # Combine both client lists, avoiding duplicates
        all_clients = clients.copy()
        client_ids = {client.machineIdentifier for client in clients}

        for client in session_clients:
            if (
                hasattr(client, "machineIdentifier")
                and client.machineIdentifier not in client_ids
            ):
                all_clients.append(client)
                client_ids.add(client.machineIdentifier)

        if not all_clients:
            return json.dumps(
                {
                    "status": "success",
                    "message": "No clients currently connected to your Plex server.",
                    "count": 0,
                    "clients": [],
                }
            )

        result = []
        if include_details:
            for client in all_clients:
                result.append(
                    {
                        "name": client.title,
                        "device": getattr(client, "device", "Unknown"),
                        "model": getattr(client, "model", "Unknown"),
                        "product": getattr(client, "product", "Unknown"),
                        "version": getattr(client, "version", "Unknown"),
                        "platform": getattr(client, "platform", "Unknown"),
                        "state": getattr(client, "state", "Unknown"),
                        "machineIdentifier": getattr(
                            client, "machineIdentifier", "Unknown"
                        ),
                        "address": getattr(client, "_baseurl", "Unknown")
                        or getattr(client, "address", "Unknown"),
                        "protocolCapabilities": getattr(
                            client, "protocolCapabilities", []
                        ),
                    }
                )
        else:
            result = [client.title for client in all_clients]

        return json.dumps(
            {
                "status": "success",
                "message": f"Found {len(all_clients)} connected clients",
                "count": len(all_clients),
                "clients": result,
            },
            indent=2,
        )

    except Exception as e:
        return json.dumps(
            {"status": "error", "message": f"Error listing clients: {str(e)}"}
        )


@tool_metadata(
    name="get_plex_client_details",
    description="Get detailed information about a specific Plex client",
    annotations=ToolAnnotations(
        title="Get Plex Client Details",
        readOnlyHint=True,
    ),
)
async def client_get_details(
    client_machine_identifier: Annotated[
        str,
        Field(
            title="Client Machine Identifier",
            description="Machine identifier of the client to get details for",
            examples=["1234567890abcdef1234567890abcdef12345678"],
        ),
    ],
) -> str:
    """Get detailed information about a specific Plex client.

    Args:
        client_machine_identifier: Name of the client to get details for

    Returns:
        Dictionary containing client details
    """
    try:
        plex = connect_to_plex()

        # Get regular clients
        regular_clients = plex.clients()

        # Also get clients from sessions
        sessions = plex.sessions()
        session_clients = []

        # Extract clients from sessions
        for session in sessions:
            if hasattr(session, "player") and session.player:  # type: ignore
                session_clients.append(session.player)  # type: ignore

        # Try to find the client first in regular clients
        client = None
        try:
            client = plex.client(client_machine_identifier)
        except NotFound:
            # Try to find a client with a matching name in regular clients
            matching_clients = [
                c
                for c in regular_clients
                if client_machine_identifier in c.machineIdentifier
            ]
            if matching_clients:
                client = matching_clients[0]
            else:
                # Try to find in session clients
                matching_session_clients = [
                    c
                    for c in session_clients
                    if hasattr(c, "title")
                    and client_machine_identifier in c.machineIdentifier
                ]
                if matching_session_clients:
                    client = matching_session_clients[0]
                else:
                    return json.dumps(
                        {
                            "status": "error",
                            "message": f"No client found matching '{client_machine_identifier}'",
                        }
                    )

        client_details = {
            "name": client.title,
            "device": getattr(client, "device", "Unknown"),
            "deviceClass": getattr(client, "deviceClass", "Unknown"),
            "model": getattr(client, "model", "Unknown"),
            "product": getattr(client, "product", "Unknown"),
            "version": getattr(client, "version", "Unknown"),
            "platform": getattr(client, "platform", "Unknown"),
            "platformVersion": getattr(client, "platformVersion", "Unknown"),
            "state": getattr(client, "state", "Unknown"),
            "machineIdentifier": getattr(client, "machineIdentifier", "Unknown"),
            "protocolCapabilities": getattr(client, "protocolCapabilities", []),
            "address": getattr(client, "_baseurl", "Unknown")
            or getattr(client, "address", "Unknown"),
            "local": getattr(client, "local", "Unknown"),
            "protocol": getattr(client, "protocol", "plex"),
            "protocolVersion": getattr(client, "protocolVersion", "Unknown"),
            "vendor": getattr(client, "vendor", "Unknown"),
        }

        return json.dumps({"status": "success", "client": client_details}, indent=2)

    except Exception as e:
        return json.dumps(
            {"status": "error", "message": f"Error getting client details: {str(e)}"}
        )


@tool_metadata(
    name="get_plex_client_timelines",
    description="Get the current timeline information for a specific Plex client",
    annotations=ToolAnnotations(
        title="Get Plex Client Timelines",
        readOnlyHint=True,
    ),
)
async def client_get_timelines(
    client_machine_identifier: Annotated[
        str,
        Field(
            title="Client Machine Identifier",
            description="Machine identifier of the client to get timeline for",
            examples=["1234567890abcdef1234567890abcdef12345678"],
        ),
    ],
) -> str:
    """Get the current timeline information for a specific Plex client.

    Args:
        client_machine_identifier: Name of the client to get timeline for

    Returns:
        Timeline information for the client
    """
    try:
        plex = connect_to_plex()

        # Get regular clients
        regular_clients = plex.clients()

        # Also get clients from sessions
        sessions = plex.sessions()
        session_clients = []

        # Extract clients from sessions
        for session in sessions:
            if hasattr(session, "player") and session.player:  # type: ignore
                session_clients.append(session.player)  # type: ignore

        # Try to find the client first in regular clients
        client = None
        try:
            client = plex.client(client_machine_identifier)
        except NotFound:
            # Try to find a client with a matching name in regular clients
            matching_clients = [
                c
                for c in regular_clients
                if client_machine_identifier in c.machineIdentifier
            ]
            if matching_clients:
                client = matching_clients[0]
            else:
                # Try to find in session clients
                matching_session_clients = [
                    c
                    for c in session_clients
                    if hasattr(c, "title")
                    and client_machine_identifier in c.clientIdentifier
                ]
                if matching_session_clients:
                    client = matching_session_clients[0]
                else:
                    return json.dumps(
                        {
                            "status": "error",
                            "message": f"No client found matching '{client_machine_identifier}'",
                        }
                    )

        # Some clients may not always respond to timeline requests
        try:
            timeline = client.timeline

            # If timeline is None, the client might not be actively playing anything
            if timeline is None:
                # Check if this client has an active session
                for session in [s for s in sessions if s is not None]:
                    if (
                        hasattr(session, "player")
                        and session.player
                        and hasattr(session.player, "machineIdentifier")
                        and hasattr(client, "machineIdentifier")
                        and session.player.machineIdentifier == client.machineIdentifier
                    ):
                        # Use session information instead
                        session_data = {
                            "state": (
                                session.player.state
                                if hasattr(session.player, "state")
                                else "Unknown"
                            ),
                            "time": (
                                session.viewOffset
                                if hasattr(session, "viewOffset")
                                else 0
                            ),
                            "duration": (
                                session.duration if hasattr(session, "duration") else 0
                            ),
                            "progress": round(
                                (
                                    (session.viewOffset / session.duration * 100)
                                    if hasattr(session, "viewOffset")
                                    and hasattr(session, "duration")
                                    and session.duration
                                    else 0
                                ),
                                2,
                            ),
                            "title": (
                                session.title
                                if hasattr(session, "title")
                                else "Unknown"
                            ),
                            "type": (
                                session.type if hasattr(session, "type") else "Unknown"
                            ),
                        }

                        return json.dumps(
                            {
                                "status": "success",
                                "client_machine_identifier": client_machine_identifier,
                                "client_name": client.title,
                                "source": "session",
                                "timeline": session_data,
                            },
                            indent=2,
                        )

                return json.dumps(
                    {
                        "status": "info",
                        "message": f"Client '{client.title}' is not currently playing any media.",
                        "client_machine_identifier": client_machine_identifier,
                        "client_name": client.title,
                    }
                )

            # Process timeline data
            timeline_data = {
                "type": timeline.type,
                "state": timeline.state,
                "time": timeline.time,
                "duration": timeline.duration,
                "progress": round(
                    (
                        (timeline.time / timeline.duration * 100)
                        if timeline.duration
                        else 0
                    ),
                    2,
                ),
                "key": getattr(timeline, "key", None),
                "ratingKey": getattr(timeline, "ratingKey", None),
                "playQueueItemID": getattr(timeline, "playQueueItemID", None),
                "playbackRate": getattr(timeline, "playbackRate", 1),
                "shuffled": getattr(timeline, "shuffled", False),
                "repeated": getattr(timeline, "repeated", 0),
                "muted": getattr(timeline, "muted", False),
                "volume": getattr(timeline, "volume", None),
                "title": getattr(timeline, "title", None),
                "guid": getattr(timeline, "guid", None),
            }

            return json.dumps(
                {
                    "status": "success",
                    "client_machine_identifier": client_machine_identifier,
                    "client_name": client.title,
                    "source": "timeline",
                    "timeline": timeline_data,
                },
                indent=2,
            )
        except:
            # Check if there's an active session for this client
            for session in [s for s in sessions if s is not None]:
                if (
                    hasattr(session, "player")
                    and session.player
                    and hasattr(session.player, "machineIdentifier")
                    and hasattr(client, "machineIdentifier")
                    and session.player.machineIdentifier == client.machineIdentifier
                ):
                    # Use session information instead
                    session_data = {
                        "state": (
                            session.player.state
                            if hasattr(session.player, "state")
                            else "Unknown"
                        ),
                        "time": (
                            session.viewOffset if hasattr(session, "viewOffset") else 0
                        ),
                        "duration": (
                            session.duration if hasattr(session, "duration") else 0
                        ),
                        "progress": round(
                            (
                                (session.viewOffset / session.duration * 100)
                                if hasattr(session, "viewOffset")
                                and hasattr(session, "duration")
                                and session.duration
                                else 0
                            ),
                            2,
                        ),
                        "title": (
                            session.title if hasattr(session, "title") else "Unknown"
                        ),
                        "type": session.type if hasattr(session, "type") else "Unknown",
                    }

                    return json.dumps(
                        {
                            "status": "success",
                            "client_machine_identifier": client_machine_identifier,
                            "client_name": client.title,
                            "source": "session",
                            "timeline": session_data,
                        },
                        indent=2,
                    )

            return json.dumps(
                {
                    "status": "warning",
                    "message": f"Unable to get timeline information for client '{client.title}'. The client may not be responding to timeline requests.",
                    "client_machine_identifier": client_machine_identifier,
                    "client_name": client.title,
                }
            )

    except Exception as e:
        return json.dumps(
            {"status": "error", "message": f"Error getting client timeline: {str(e)}"}
        )


@tool_metadata(
    name="get_active_plex_clients",
    description="Get all clients that are currently playing media",
    annotations=ToolAnnotations(
        title="Get Active Plex Clients",
        readOnlyHint=True,
    ),
)
async def get_active_clients() -> str:
    """Get all clients that are currently playing media.

    Returns:
        List of active clients with their playback status
    """
    try:
        plex = connect_to_plex()

        # Get all sessions
        sessions = plex.sessions()

        if not sessions:
            return json.dumps(
                {
                    "status": "success",
                    "message": "No active playback sessions found.",
                    "count": 0,
                    "active_clients": [],
                }
            )

        active_clients = []

        for session in [s for s in sessions if s is not None]:
            if hasattr(session, "player") and session.player:
                player = session.player

                # Get media information
                media_info = {
                    "title": session.title if hasattr(session, "title") else "Unknown",
                    "type": session.type if hasattr(session, "type") else "Unknown",
                }

                # Add additional info based on media type
                if hasattr(session, "type"):
                    if session.type == "episode":
                        media_info["show"] = getattr(
                            session, "grandparentTitle", "Unknown Show"
                        )
                        media_info["season"] = getattr(
                            session, "parentTitle", "Unknown Season"
                        )
                        media_info["seasonEpisode"] = (
                            f"S{getattr(session, 'parentIndex', '?')}E{getattr(session, 'index', '?')}"
                        )
                    elif session.type == "movie":
                        media_info["year"] = getattr(session, "year", "Unknown")

                # Calculate progress if possible
                progress = None
                if (
                    hasattr(session, "viewOffset")
                    and hasattr(session, "duration")
                    and session.duration
                ):
                    progress = round((session.viewOffset / session.duration) * 100, 1)

                # Get user info
                username = "Unknown User"
                if hasattr(session, "usernames") and session.usernames:
                    username = session.usernames[0]

                # Get transcoding status
                transcoding = False
                if hasattr(session, "transcodeSessions") and session.transcodeSessions:
                    transcoding = True

                client_info = {
                    "name": player.title,
                    "device": getattr(player, "device", "Unknown"),
                    "product": getattr(player, "product", "Unknown"),
                    "platform": getattr(player, "platform", "Unknown"),
                    "state": getattr(player, "state", "Unknown"),
                    "user": username,
                    "media": media_info,
                    "progress": progress,
                    "transcoding": transcoding,
                }

                active_clients.append(client_info)

        return json.dumps(
            {
                "status": "success",
                "message": f"Found {len(active_clients)} active clients",
                "count": len(active_clients),
                "active_clients": active_clients,
            },
            indent=2,
        )

    except Exception as e:
        return json.dumps(
            {"status": "error", "message": f"Error getting active clients: {str(e)}"}
        )


@tool_metadata(
    name="plex_client_start_playback",
    description="Start playback of media on a specified Plex client",
    annotations=ToolAnnotations(
        title="Start Playback on Plex Client",
        readOnlyHint=False,
        destructiveHint=True,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
async def client_start_playback(
    media_title: Annotated[
        str,
        Field(
            title="Media Title",
            description="Title of the media to play",
            examples=["Inception", "Game of Thrones S01E01", "The Matrix"],
            min_length=1,
            max_length=100,
        ),
    ],
    client_machine_identifier: Annotated[
        str,
        Field(
            title="Client Machine Identifier",
            description="Machine identifier of the client to play on.",
            examples=["1234567890abcdef1234567890abcdef12345678"],
        ),
    ],
    offset: Annotated[
        int,
        Field(
            title="Playback Offset (ms)",
            description="Time offset in milliseconds to start playback from",
            default=0,
            ge=0,
            examples=[0, 30000, 60000],  # 0ms, 30s, 60s
        ),
    ] = 0,
    library_name: Annotated[
        str | None,
        Field(
            title="Library Name",
            description="Name of the library to search in. If not provided, searches all libraries.",
            default=None,
            examples=["Movies", "TV Shows"],
        ),
    ] = None,
) -> str:
    """Start playback of media on a specified client.

    Args:
        media_title: Title of the media to play
        client_machine_identifier: Optional machine identifier of the client to play on (will prompt if not provided)
        offset: Optional time offset in milliseconds to start from
        library_name: Optional name of the library to search in
        use_external_player: Whether to use the client's external player
    """
    try:
        plex = connect_to_plex()

        # First, find the media item
        results = []
        if library_name:
            try:
                library = plex.library.section(library_name)
                results = library.search(title=media_title)
            except Exception:
                return json.dumps(
                    {
                        "status": "error",
                        "message": f"Library '{library_name}' not found",
                    }
                )
        else:
            results = plex.search(media_title)

        if not results:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"No media found matching '{media_title}'",
                }
            )

        if len(results) > 1:
            # If multiple results, provide information about them
            media_list = []
            for i, media in enumerate(
                results[:10], 1
            ):  # Limit to first 10 to avoid overwhelming
                media_type = getattr(media, "type", "unknown")
                title = getattr(media, "title", "Unknown")
                year = getattr(media, "year", "")

                media_info = {
                    "index": i,
                    "title": title,
                    "type": media_type,
                }

                if year:
                    media_info["year"] = year

                if media_type == "episode":
                    show = getattr(media, "grandparentTitle", "Unknown Show")
                    season = getattr(media, "parentIndex", "?")
                    episode = getattr(media, "index", "?")
                    media_info["show"] = show
                    media_info["season"] = season
                    media_info["episode"] = episode

                media_list.append(media_info)

            return json.dumps(
                {
                    "status": "multiple_results",
                    "message": f"Multiple items found matching '{media_title}'. Please specify a library or use a more specific title.",
                    "count": len(results),
                    "results": media_list,
                },
                indent=2,
            )

        media = results[0]

        # Try to find the client
        try:
            client = plex.client(client_machine_identifier)
        except NotFound:
            # Try to find a client with a matching name
            matching_clients = [
                c
                for c in plex.clients()
                if client_machine_identifier in c.client_machine_identifier
            ]
            if matching_clients:
                client = matching_clients[0]
            else:
                return json.dumps(
                    {
                        "status": "error",
                        "message": f"No client found matching '{client_machine_identifier}'",
                    }
                )

        # Start playback
        media_type = getattr(media, "type", "unknown")
        title = getattr(media, "title", "Unknown")

        formatted_title = title
        if media_type == "episode":
            show = getattr(media, "grandparentTitle", "Unknown Show")
            season = getattr(media, "parentIndex", "?")
            episode = getattr(media, "index", "?")
            formatted_title = f"{show} - S{season}E{episode} - {title}"
        elif hasattr(media, "year") and media.year:
            formatted_title = f"{title} ({media.year})"

        try:
            client.playMedia(media, offset=offset)

            return json.dumps(
                {
                    "status": "success",
                    "message": f"Started playback of '{formatted_title}' on {client.title}",
                    "media": {
                        "title": title,
                        "type": media_type,
                        "formatted_title": formatted_title,
                        "rating_key": getattr(media, "ratingKey", None),
                    },
                    "client": client.title,
                    "offset": offset,
                },
                indent=2,
            )
        except Exception as e:
            return json.dumps(
                {"status": "error", "message": f"Error starting playback: {str(e)}"}
            )

    except Exception as e:
        return json.dumps(
            {"status": "error", "message": f"Error setting up playback: {str(e)}"}
        )


PlaybackAction = Literal[
    "play",
    "pause",
    "stop",
    "skipNext",
    "skipPrevious",
    "stepForward",
    "stepBack",
    "seekTo",
    "seekForward",
    "seekBack",
    "mute",
    "unmute",
    "setVolume",
]

MediaType = Literal["video", "music", "photo"]


@tool_metadata(
    name="control_plex_client_playback",
    description="Control playback on a specified Plex client",
    annotations=ToolAnnotations(
        title="Control Plex Client Playback",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
async def client_control_playback(
    client_machine_identifier: Annotated[
        str,
        Field(
            title="Client Machine Identifier",
            description="Machine identifier of the client to control",
            examples=["1234567890abcdef1234567890abcdef12345678"],
        ),
    ],
    action: Annotated[
        PlaybackAction,
        Field(
            title="Playback Action",
            description="Action to perform on the client",
            examples=[
                "play",
                "pause",
                "stop",
                "skipNext",
                "skipPrevious",
                "stepForward",
                "stepBack",
                "seekTo",
                "seekForward",
                "seekBack",
                "mute",
                "unmute",
                "setVolume",
            ],
        ),
    ],
    parameter: Annotated[
        int | None,
        Field(
            title="Action Parameter",
            description="Parameter for actions that require it (like setVolume or seekTo). "
            "For setVolume, this should be between 0 and 100. "
            "For seekTo, this should be in milliseconds.",
            default=None,
            examples=[30, 60, 1000, None],
        ),
    ] = None,
    media_type: Annotated[
        MediaType,
        Field(
            title="Media Type",
            description="Type of media being controlled (video, music, or photo). "
            "This is used to determine the appropriate client capabilities.",
            default="video",
            examples=["video", "music", "photo"],
        ),
    ] = "video",
) -> str:
    """Control playback on a specified client.

    Args:
        client_machine_identifier: Machine identifier of the client to control
        action: Action to perform (play, pause, stop, skipNext, skipPrevious,
                stepForward, stepBack, seekTo, seekForward, seekBack, mute, unmute, setVolume)
        parameter: Parameter for actions that require it (like setVolume or seekTo)
        media_type: Type of media being controlled ('video', 'music', or 'photo')
    """
    try:
        plex = connect_to_plex()

        # Validate action
        valid_actions = [
            "play",
            "pause",
            "stop",
            "skipNext",
            "skipPrevious",
            "stepForward",
            "stepBack",
            "seekTo",
            "seekForward",
            "seekBack",
            "mute",
            "unmute",
            "setVolume",
        ]

        if action not in valid_actions:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Invalid action '{action}'. Valid actions are: {', '.join(valid_actions)}",
                }
            )

        # Check if parameter is needed but not provided
        actions_needing_parameter = ["seekTo", "setVolume"]
        if action in actions_needing_parameter and parameter is None:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Action '{action}' requires a parameter value.",
                }
            )

        # Validate media type
        valid_media_types = ["video", "music", "photo"]
        if media_type not in valid_media_types:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Invalid media type '{media_type}'. Valid types are: {', '.join(valid_media_types)}",
                }
            )

        # Try to find the client
        try:
            client = plex.client(client_machine_identifier)
        except NotFound:
            # Try to find a client with a matching name
            matching_clients = [
                c
                for c in plex.clients()
                if client_machine_identifier in c.client_machine_identifier
            ]
            if matching_clients:
                client = matching_clients[0]
            else:
                return json.dumps(
                    {
                        "status": "error",
                        "message": f"No client found matching '{client_machine_identifier}'",
                    }
                )

        # Check if the client has playback control capability
        if "playback" not in client.protocolCapabilities:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Client '{client.title}' does not support playback control.",
                }
            )

        # Perform the requested action
        try:
            # Transport controls
            if action == "play":
                client.play()
            elif action == "pause":
                client.pause()
            elif action == "stop":
                client.stop()
            elif action == "skipNext":
                client.skipNext()
            elif action == "skipPrevious":
                client.skipPrevious()
            elif action == "stepForward":
                client.stepForward()
            elif action == "stepBack":
                client.stepBack()

            # Seeking
            elif action == "seekTo":
                # Parameter should be milliseconds
                client.seekTo(parameter)
            elif action == "seekForward":
                # Default to 30 seconds if no parameter
                seconds = parameter if parameter is not None else 30
                client.seekTo(client.timeline.time + (seconds * 1000))
            elif action == "seekBack":
                # Default to 30 seconds if no parameter
                seconds = parameter if parameter is not None else 30
                seek_time = max(0, client.timeline.time - (seconds * 1000))
                client.seekTo(seek_time)

            # Volume controls
            elif action == "mute":
                client.mute()
            elif action == "unmute":
                client.unmute()
            elif action == "setVolume":
                if parameter is None:
                    return json.dumps(
                        {
                            "status": "error",
                            "message": "setVolume action requires a parameter value.",
                        }
                    )
                # Parameter should be 0-100
                if parameter < 0 or parameter > 100:
                    return json.dumps(
                        {
                            "status": "error",
                            "message": "Volume must be between 0 and 100",
                        }
                    )
                client.setVolume(parameter)

            # Check timeline to confirm the action (may take a moment to update)
            time.sleep(0.5)  # Give a short delay for state to update

            # Get updated timeline info
            timeline = None
            try:
                timeline = client.timeline
                if timeline:
                    timeline_data = {
                        "state": timeline.state,
                        "time": timeline.time,
                        "duration": timeline.duration,
                        "volume": getattr(timeline, "volume", None),
                        "muted": getattr(timeline, "muted", None),
                    }
                else:
                    timeline_data = None
            except:
                timeline_data = None

            return json.dumps(
                {
                    "status": "success",
                    "message": f"Successfully performed action '{action}' on client '{client.title}'",
                    "action": action,
                    "client": client.title,
                    "parameter": parameter,
                    "timeline": timeline_data,
                },
                indent=2,
            )

        except Exception as e:
            return json.dumps(
                {"status": "error", "message": f"Error controlling playback: {str(e)}"}
            )

    except Exception as e:
        return json.dumps(
            {
                "status": "error",
                "message": f"Error setting up playback control: {str(e)}",
            }
        )


NavigationAction = Literal[
    "moveUp",
    "moveDown",
    "moveLeft",
    "moveRight",
    "select",
    "back",
    "home",
    "contextMenu",
]


@tool_metadata(
    name="plex_client_navigate",
    description="Navigate a Plex client interface",
    annotations=ToolAnnotations(
        title="Navigate Plex Client",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
async def client_navigate(
    client_machine_identifier: Annotated[
        str,
        Field(
            title="Client Machine Identifier",
            description="Machine identifier of the client to navigate",
            examples=["1234567890abcdef1234567890abcdef12345678"],
        ),
    ],
    action: Annotated[
        NavigationAction,
        Field(
            title="Navigation Action",
            description="Navigation action to perform",
            examples=[
                "moveUp",
                "moveDown",
                "moveLeft",
                "moveRight",
                "select",
                "back",
                "home",
                "contextMenu",
            ],
        ),
    ],
) -> str:
    """Navigate a Plex client interface.

    Args:
        client_machine_identifier: Name of the client to navigate
        action: Navigation action to perform (moveUp, moveDown, moveLeft, moveRight,
                select, back, home, contextMenu)
    """
    try:
        plex = connect_to_plex()

        # Validate action
        valid_actions = [
            "moveUp",
            "moveDown",
            "moveLeft",
            "moveRight",
            "select",
            "back",
            "home",
            "contextMenu",
        ]

        if action not in valid_actions:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Invalid navigation action '{action}'. Valid actions are: {', '.join(valid_actions)}",
                }
            )

        # Try to find the client
        try:
            client = plex.client(client_machine_identifier)
        except NotFound:
            # Try to find a client with a matching name
            matching_clients = [
                c
                for c in plex.clients()
                if client_machine_identifier in c.client_machine_identifier
            ]
            if matching_clients:
                client = matching_clients[0]
            else:
                return json.dumps(
                    {
                        "status": "error",
                        "message": f"No client found matching '{client_machine_identifier}'",
                    }
                )

        # Check if the client has navigation capability
        if "navigation" not in client.protocolCapabilities:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Client '{client.title}' does not support navigation control.",
                }
            )

        # Perform the requested action
        try:
            if action == "moveUp":
                client.moveUp()
            elif action == "moveDown":
                client.moveDown()
            elif action == "moveLeft":
                client.moveLeft()
            elif action == "moveRight":
                client.moveRight()
            elif action == "select":
                client.select()
            elif action == "back":
                client.goBack()
            elif action == "home":
                client.goToHome()
            elif action == "contextMenu":
                client.contextMenu()

            return json.dumps(
                {
                    "status": "success",
                    "message": f"Successfully performed navigation action '{action}' on client '{client.title}'",
                    "action": action,
                    "client": client.title,
                },
                indent=2,
            )

        except Exception as e:
            return json.dumps(
                {"status": "error", "message": f"Error navigating client: {str(e)}"}
            )

    except Exception as e:
        return json.dumps(
            {
                "status": "error",
                "message": f"Error setting up client navigation: {str(e)}",
            }
        )


@tool_metadata(
    name="plex_client_set_streams",
    description="Set audio, subtitle, or video streams for current playback on a client",
    annotations=ToolAnnotations(
        title="Set Plex Client Streams",
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    ),
)
async def client_set_streams(
    client_machine_identifier: Annotated[
        str,
        Field(
            title="Client Machine Identifier",
            description="Machine identifier of the client to set streams for",
            examples=["1234567890abcdef1234567890abcdef12345678"],
        ),
    ],
    audio_stream_id: Annotated[
        str | None,
        Field(
            title="Audio Stream ID",
            description="ID of the audio stream to switch to. Use '0' to disable audio.",
            default=None,
            examples=["1", "2", "0"],
        ),
    ] = None,
    subtitle_stream_id: Annotated[
        str | None,
        Field(
            title="Subtitle Stream ID",
            description="ID of the subtitle stream to switch to. Use '0' to disable subtitles.",
            default=None,
            examples=["1", "2", "0"],
        ),
    ] = None,
    video_stream_id: Annotated[
        str | None,
        Field(
            title="Video Stream ID",
            description="ID of the video stream to switch to. Use '0' to disable video.",
            default=None,
            examples=["1", "2", "0"],
        ),
    ] = None,
) -> str:
    """Set audio, subtitle, or video streams for current playback on a client.

    Args:
        client_machine_identifier: Client machine identifier of the client to set streams for
        audio_stream_id: ID of the audio stream to switch to
        subtitle_stream_id: ID of the subtitle stream to switch to, use '0' to disable
        video_stream_id: ID of the video stream to switch to
    """
    try:
        plex = connect_to_plex()

        # Check if at least one stream ID is provided
        if (
            audio_stream_id is None
            and subtitle_stream_id is None
            and video_stream_id is None
        ):
            return json.dumps(
                {
                    "status": "error",
                    "message": "At least one stream ID (audio, subtitle, or video) must be provided.",
                }
            )

        # Try to find the client
        try:
            client = plex.client(client_machine_identifier)
        except NotFound:
            # Try to find a client with a matching name
            matching_clients = [
                c
                for c in plex.clients()
                if client_machine_identifier in client_machine_identifier
            ]
            if matching_clients:
                client = matching_clients[0]
            else:
                return json.dumps(
                    {
                        "status": "error",
                        "message": f"No client found matching '{client_machine_identifier}'",
                    }
                )

        # Check if client is currently playing
        timeline = None
        try:
            timeline = client.timeline
            if (
                timeline is None
                or not hasattr(timeline, "state")
                or timeline.state != "playing"
            ):
                # Check active sessions to see if this client has a session
                sessions = plex.sessions()
                client_session = None

                for session in [s for s in sessions if s is not None]:
                    if (
                        hasattr(session, "player")
                        and session.player
                        and hasattr(session.player, "machineIdentifier")
                        and hasattr(client, "machineIdentifier")
                        and session.player.machineIdentifier == client.machineIdentifier
                    ):
                        client_session = session
                        break

                if not client_session:
                    return json.dumps(
                        {
                            "status": "error",
                            "message": f"Client '{client.title}' is not currently playing any media.",
                        }
                    )
        except:
            return json.dumps(
                {
                    "status": "error",
                    "message": f"Unable to get playback status for client '{client.title}'.",
                }
            )

        # Set streams
        changed_streams = []
        try:
            if audio_stream_id is not None:
                client.setAudioStream(audio_stream_id)
                changed_streams.append(f"audio to {audio_stream_id}")

            if subtitle_stream_id is not None:
                client.setSubtitleStream(subtitle_stream_id)
                changed_streams.append(f"subtitle to {subtitle_stream_id}")

            if video_stream_id is not None:
                client.setVideoStream(video_stream_id)
                changed_streams.append(f"video to {video_stream_id}")

            return json.dumps(
                {
                    "status": "success",
                    "message": f"Successfully set streams for '{client.title}': {', '.join(changed_streams)}",
                    "client": client.title,
                    "changes": {
                        "audio_stream": (
                            audio_stream_id if audio_stream_id is not None else None
                        ),
                        "subtitle_stream": (
                            subtitle_stream_id
                            if subtitle_stream_id is not None
                            else None
                        ),
                        "video_stream": (
                            video_stream_id if video_stream_id is not None else None
                        ),
                    },
                },
                indent=2,
            )
        except Exception as e:
            return json.dumps(
                {"status": "error", "message": f"Error setting streams: {str(e)}"}
            )

    except Exception as e:
        return json.dumps(
            {
                "status": "error",
                "message": f"Error setting up stream selection: {str(e)}",
            }
        )
