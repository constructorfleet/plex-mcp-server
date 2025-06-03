import asyncio
import inspect
import logging
from datetime import datetime
from functools import wraps
from typing import (
    Any,
    Awaitable,
    Callable,
    List,
    Literal,
    Optional,
    TypeVar,
    Union,
    cast,
)

import httpx
from fastmcp import FastMCP
from mcp.types import ToolAnnotations

T = TypeVar("T")
FuncType = Union[Callable[..., T], Callable[..., Awaitable[T]]]


class PendingMCPComponents:
    """
    A class to manage pending MCP components that need to be registered later.
    This is useful for components that are not immediately available at startup.
    """

    _instance: Optional["PendingMCPComponents"] = None

    @staticmethod
    def instance() -> "PendingMCPComponents":
        """
        Get the singleton instance of PendingMCPComponents.
        """
        if PendingMCPComponents._instance is None:
            PendingMCPComponents._instance = PendingMCPComponents()
        return PendingMCPComponents._instance

    def __init__(self):
        self.components: List[FuncType] = []
        self._mcpApp: FastMCP | None = None

    def process(self, app: FastMCP) -> None:
        """
        Process the pending components and register them with the given FastMCP app.

        Args:
            app: The FastMCP application instance to register components with.
        """
        self._mcpApp = app
        components = self.components.copy()
        self.components.clear()
        for component in components:
            self._process_component(component)

    def _process_component(self, component: FuncType) -> FuncType | None:
        if self._mcpApp is None:
            return component
        if hasattr(component, "_tool_metadata"):
            apply_decorators(
                self._mcpApp.tool(
                    name=component._tool_metadata.name,
                    description=component._tool_metadata.description,
                    annotations=component._tool_metadata.annotations,
                ),
                log_and_handle_errors,
            )(component)
        elif hasattr(component, "_resource_metadata"):
            apply_decorators(
                self._mcpApp.resource(
                    uri=component._resource_metadata.uri,
                    name=component._resource_metadata.name,
                    description=component._resource_metadata.description,
                    mime_type=component._resource_metadata.mime_type,
                ),
                log_and_handle_errors,
            )(component)
        elif hasattr(component, "_prompt_metadata"):
            apply_decorators(
                self._mcpApp.prompt(
                    name=component._prompt_metadata.name,
                    description=component._prompt_metadata.description,
                    tags=component._prompt_metadata.tags,
                ),
                log_and_handle_errors,
            )(component)
        return None

    def add(self, func: FuncType) -> FuncType:
        """
        Add a function to the pending list.

        Args:
            func: The function to add to the pending list
        """
        processed = self._process_component(func)
        if processed is None:
            return func

        self.components.append(func)
        return func

    def get_pending(self) -> List[FuncType]:
        """Get the list of pending components."""
        return self.components


def apply_decorators(
    *decorators: Callable[[FuncType], FuncType]
) -> Callable[[FuncType], FuncType]:
    def decorator(func: FuncType) -> FuncType:
        for deco in reversed(decorators):
            func = deco(func)
        return func

    return decorator


def log_function_call(func: FuncType) -> FuncType:
    if asyncio.iscoroutinefunction(func):

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            logger = logging.getLogger(f"{func.__module__}:{func.__name__}")
            logger.debug(
                f"Calling async function {func.__name__} with args: {args}, kwargs: {kwargs}"
            )
            start = datetime.now()
            try:
                return await func(*args, **kwargs)
            finally:
                duration = (datetime.now() - start).total_seconds()
                logger.debug(
                    f"Async function {func.__name__} took {duration:.4f}s to complete"
                )

        return cast(FuncType, async_wrapper)
    else:

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            logger = logging.getLogger(f"{func.__module__}:{func.__name__}")
            logger.debug(
                f"Calling sync function {func.__name__} with args: {args}, kwargs: {kwargs}"
            )
            start = datetime.now()
            try:
                return func(*args, **kwargs)
            finally:
                duration = (datetime.now() - start).total_seconds()
                logger.debug(
                    f"Sync function {func.__name__} took {duration:.4f}s to complete"
                )

        return cast(FuncType, sync_wrapper)


def handle_api_errors(func: FuncType) -> FuncType:
    """
    Decorator to handle common error cases for API calls

    Args:
        func: The async function to decorate

    Returns:
        Wrapped function that handles errors
    """

    def format_error(return_type: Any, msg: str) -> Any:
        if "Dict" in return_type:
            return {"error": msg}
        elif "List" in return_type:
            return [{"error": msg}]
        else:
            return msg

    if asyncio.iscoroutinefunction(func):

        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            # Determine return type from function annotation
            return_type = inspect.signature(func).return_annotation

            try:
                return await func(*args, **kwargs)
            except httpx.ConnectError as e:
                return format_error(
                    return_type,
                    f"Connection error: Cannot connect to resource at {e.request.url}",
                )
            except httpx.TimeoutException as e:
                return format_error(
                    return_type,
                    f"Timeout error: Resource at {e.request.url} did not respond in time",
                )
            except httpx.HTTPStatusError as e:
                return format_error(
                    return_type,
                    f"HTTP error: Server responded with {e.response.status_code} - {e.response.reason_phrase}",
                )
            except httpx.RequestError as e:
                return format_error(return_type, f"Request error: {str(e)}")
            except Exception as e:
                return format_error(return_type, f"Unexpected error: {str(e)}")

        return cast(FuncType, async_wrapper)
    else:

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            # Determine return type from function annotation
            return_type = inspect.signature(func).return_annotation

            try:
                return func(*args, **kwargs)
            except httpx.ConnectError as e:
                return format_error(
                    return_type,
                    f"Connection error: Cannot connect to resource at {e.request.url}",
                )
            except httpx.TimeoutException as e:
                return format_error(
                    return_type,
                    f"Timeout error: Resource at {e.request.url} did not respond in time",
                )
            except httpx.HTTPStatusError as e:
                return format_error(
                    return_type,
                    f"HTTP error: Server responded with {e.response.status_code} - {e.response.reason_phrase}",
                )
            except httpx.RequestError as e:
                return format_error(return_type, f"Request error: {str(e)}")
            except Exception as e:
                return format_error(return_type, f"Unexpected error: {str(e)}")

        return cast(FuncType, sync_wrapper())


def log_and_handle_errors(func: FuncType) -> FuncType:
    """
    Decorator to log errors and handle them gracefully

    Args:
        func: The function to decorate

    Returns:
        Wrapped function that logs errors
    """
    return apply_decorators(handle_api_errors, log_function_call)(func)


def add_pending(fn: FuncType) -> FuncType:
    """
    Add a function to the pending list.

    Args:
        func: The function to add to the pending list
    """
    PendingMCPComponents.instance().add(fn)
    return fn


def tool_metadata(
    name: str,
    description: str,
    annotations: ToolAnnotations | None = None,
) -> Callable[[FuncType], FuncType]:
    """
    Decorator to add metadata to a tool function

    Args:
        name: The name of the tool
        description: A brief description of what the tool does
        annotations: Optional annotations for the tool parameters

    Returns:
        Decorated function with metadata
    """

    def decorator(func: FuncType) -> FuncType:
        func._tool_metadata = {
            "name": name,
            "description": description,
            "annotations": annotations or {},
        }
        return add_pending(func)

    return decorator


def resource_metadata(
    uri: str,
    name: str | None = None,
    description: str | None = None,
    mime_type: str | None = None,
) -> Callable[[FuncType], FuncType]:
    """
    Decorator to add metadata to a resource function

    Args:
        uri: The URI of the resource
        name: Optional name for the resource
        description: Optional description of the resource
        mime_type: Optional MIME type of the resource

    Returns:
        Decorated function with metadata
    """

    def decorator(func: FuncType) -> FuncType:
        func._resource_metadata = {
            "uri": uri,
            "name": name,
            "description": description,
            "mime_type": mime_type,
        }
        return add_pending(func)

    return decorator


def prompt_metadata(
    name: str | None = None, description: str | None = None
) -> Callable[[FuncType], FuncType]:
    """
    Decorator to add metadata to a prompt function

    Args:
        name: Optional name for the prompt
        description: Optional description of the prompt

    Returns:
        Decorated function with metadata
    """

    def decorator(func: FuncType) -> FuncType:
        func._prompt_metadata = {"name": name, "description": description}
        return add_pending(func)

    return decorator


def custom_route_metadata(
    path: str,
    methods: list[str],
    name: str | None = None,
    include_in_schema: bool = True,
) -> Callable[[FuncType], FuncType]:
    """
    Decorator to add metadata to a custom route function

    Args:
        path: The path for the custom route
        methods: List of HTTP methods for the route
        name: Optional name for the route
        include_in_schema: Whether to include this route in the OpenAPI schema
    Returns:
        Decorated function with metadata
    """

    def decorator(func: FuncType) -> FuncType:
        func._custom_route_metadata = {
            "path": path,
            "methods": methods,
            "name": name,
            "include_in_schema": include_in_schema,
        }
        return add_pending(func)

    return decorator
