import asyncio
import os
import sys
import logging
from typing import List, Optional
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from langchain_mcp_adapters.tools import load_mcp_tools

# Suppress Python-side MCP logging noise
logging.getLogger("mcp_remote").setLevel(logging.CRITICAL)
logging.getLogger("mcp.client").setLevel(logging.CRITICAL)

# Patterns emitted by mcp-remote Node.js process that are benign and should be hidden.
# The 409 Conflict occurs when mcp-remote tries to open an SSE notification channel
# after initialize() on a StreamableHTTP server that doesn't support push notifications.
# It's by design in mcp-remote 0.1.37+ and does not affect functionality.
_STDERR_SUPPRESS_PATTERNS = [
    "StreamableHTTPError",
    "Failed to open SSE stream: Conflict",
    "code: 409",
    "at StreamableHTTPClientTransport._startOrAuthSse",
    "at process.processTicksAndRejections",
]


async def _pipe_stderr_filtered(stream: asyncio.StreamReader, server_name: str):
    """Read stderr from the mcp-remote Node process and print lines that are not
    part of a known-benign 409 error block. Consecutive lines belonging to the
    same stack trace are swallowed together."""
    suppress_remaining = 0  # How many more lines to suppress from current block
    async for raw in stream:
        line = raw.decode("utf-8", errors="replace").rstrip()
        if suppress_remaining > 0:
            suppress_remaining -= 1
            continue
        if any(pat in line for pat in _STDERR_SUPPRESS_PATTERNS):
            # Suppress this line + the next ~4 (stack trace lines)
            suppress_remaining = 4
            continue
        # Print any other stderr through so real errors are still visible
        print(f"[{server_name}] {line}", file=sys.stderr)


class MCPClientManager:
    """Manages connections to multiple MCP servers."""
    def __init__(self, config: dict):
        self.config = config
        self.sessions: List[ClientSession] = []
        self._tasks: List[asyncio.Task] = []
        self._stop_events: List[asyncio.Event] = []
        self._tools_cache: dict = {}  # Cache tools per session to avoid redundant list calls

    async def connect_all(self):
        """Connects to all configured servers by spinning up background tasks."""
        servers = self.config.get("mcp_servers", [])
        if not servers:
            print("=> No MCP servers found in config.")
            return

        ready_events = []

        for server_config in servers:
            name = server_config.get("name", "unknown")
            transport = server_config.get("transport", "stdio")
            print(f"=> Conectando a servidor MCP '{name}' via {transport}...")

            stop_event = asyncio.Event()
            ready_event = asyncio.Event()
            self._stop_events.append(stop_event)
            ready_events.append(ready_event)

            if transport == "sse":
                task = asyncio.create_task(self._run_sse_server(name, server_config, stop_event, ready_event))
                self._tasks.append(task)
            elif transport == "stdio":
                task = asyncio.create_task(self._run_stdio_server(name, server_config, stop_event, ready_event))
                self._tasks.append(task)
            else:
                print(f"Transporte desconocido '{transport}' para el servidor '{name}'")
                ready_event.set()

        # Wait for all tasks to initialize sessions (or fail)
        if ready_events:
            await asyncio.gather(*(event.wait() for event in ready_events))

    async def _run_sse_server(self, name: str, server_config: dict, stop_event: asyncio.Event, ready_event: asyncio.Event):
        url = server_config.get("url")
        if not url:
            print(f"Error: URL missing for SSE server '{name}'")
            ready_event.set()
            return

        env = server_config.get("env", {})
        kwargs = {}
        if env:
            kwargs["headers"] = env

        session_ref = None
        try:
            async with sse_client(url, **kwargs) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    session_ref = session
                    await session.initialize()
                    self.sessions.append(session)
                    print(f"=> Servidor '{name}' inicializado correctamente.")
                    ready_event.set()

                    # Wait until signaled to stop
                    await stop_event.wait()

        except Exception as e:
            print(f"Error en servidor SSE '{name}': {e}")
            ready_event.set()
        finally:
            if session_ref in self.sessions:
                self.sessions.remove(session_ref)

    async def _run_stdio_server(self, name: str, server_config: dict, stop_event: asyncio.Event, ready_event: asyncio.Event):
        command = server_config.get("command")
        args = server_config.get("args", [])
        env = server_config.get("env", {})
        if not command:
            print(f"Error: Command missing for stdio server '{name}'")
            ready_event.set()
            return

        merged_env = os.environ.copy()
        merged_env.update(env)

        # Launch the Node subprocess directly so we can intercept its stderr
        # and suppress benign 409 messages from mcp-remote.
        full_cmd = [command] + args
        process = await asyncio.create_subprocess_exec(
            *full_cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=merged_env,
        )

        # Start stderr filter task immediately
        stderr_task = asyncio.create_task(
            _pipe_stderr_filtered(process.stderr, name)
        )

        session_ref = None
        try:
            # Build MCP streams manually from the process pipes
            # mcp's stdio_client expects an anyio-compatible interface;
            # we replicate what StdioServerParameters does internally.
            server_params = StdioServerParameters(command=command, args=args, env=merged_env)
            async with stdio_client(server_params) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    session_ref = session
                    await session.initialize()
                    self.sessions.append(session)
                    print(f"=> Servidor '{name}' inicializado correctamente.")
                    ready_event.set()

                    # Pre-load tools into cache right after initialization to avoid
                    # a second wire call that would trigger another 409 attempt.
                    try:
                        tools = await load_mcp_tools(session)
                        self._tools_cache[id(session)] = tools
                    except Exception as e:
                        if "409" not in str(e) and "Conflict" not in str(e):
                            print(f"Advertencia: No se pudo pre-cargar tools de '{name}': {e}")
                        self._tools_cache[id(session)] = []

                    # Wait until signaled to stop
                    await stop_event.wait()

        except Exception as e:
            print(f"Error en servidor stdio '{name}': {e}")
            ready_event.set()
        finally:
            stderr_task.cancel()
            try:
                await stderr_task
            except asyncio.CancelledError:
                pass
            if session_ref in self.sessions:
                self.sessions.remove(session_ref)
            self._tools_cache.pop(id(session_ref), None)

    async def get_all_tools(self) -> list:
        """Return tools from all connected MCP sessions using cache.

        Tools are pre-loaded during initialization to avoid triggering a second
        SSE stream open (which causes 409 Conflict on StreamableHTTP servers).
        For sessions not yet cached (e.g. SSE transport), falls back to live fetch.
        """
        all_tools = []
        for session in self.sessions:
            session_id = id(session)
            if session_id in self._tools_cache:
                # Use cached tools - no extra wire call needed
                tools = self._tools_cache[session_id]
            else:
                # Fallback: live fetch for sessions initialized via SSE transport
                try:
                    tools = await load_mcp_tools(session)
                    self._tools_cache[session_id] = tools
                except Exception as e:
                    print(f"Error obteniendo herramientas de una sesión: {e}")
                    tools = []

            # Wrap each tool to prevent unhandled exceptions from crashing the graph loop
            for tool in tools:
                original_arun = getattr(tool, "_arun", None)
                original_run = getattr(tool, "_run", None)

                if original_arun:
                    async def safe_arun(*args, config: dict = None, _original_arun=original_arun, _tool=tool, **kwargs):
                        try:
                            return await _original_arun(*args, config=config, **kwargs)
                        except Exception as e:
                            err_msg = f"Error executing MCP tool '{_tool.name}': {type(e).__name__}: {str(e)}. Tip: Verify your parameters or use a different tool."
                            print(f"\033[91m[MCP Error Interno] {err_msg}\033[0m")
                            if getattr(_tool, "response_format", None) == "content_and_artifact":
                                return err_msg, None
                            return err_msg
                    tool._arun = safe_arun

                if original_run:
                    def safe_run(*args, config: dict = None, _original_run=original_run, _tool=tool, **kwargs):
                        try:
                            return _original_run(*args, config=config, **kwargs)
                        except Exception as e:
                            err_msg = f"Error executing MCP tool '{_tool.name}': {type(e).__name__}: {str(e)}. Tip: Verify your parameters or use a different tool."
                            if getattr(_tool, "response_format", None) == "content_and_artifact":
                                return err_msg, None
                            return err_msg
                    tool._run = safe_run

            all_tools.extend(tools)
        return all_tools

    async def close(self):
        """Signals all server tasks to stop and waits for them."""
        for event in self._stop_events:
            event.set()

        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)

        self.sessions.clear()
        self._tasks.clear()
        self._stop_events.clear()
        self._tools_cache.clear()
