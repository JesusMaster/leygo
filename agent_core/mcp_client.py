import asyncio
import io
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

# Lines emitted by mcp-remote (Node.js) belonging to the benign 409 Conflict block.
# mcp-remote tries to open an SSE notification push channel after initialize() on a
# StreamableHTTP server. The server rejects it with 409 because the session is already
# active. This is by design — mcp-remote falls back to polling automatically.
_SUPPRESS = [
    b"StreamableHTTPError",
    b"Failed to open SSE stream: Conflict",
    b"code: 409",
    b"_startOrAuthSse",
    b"processTicksAndRejections",
    b"chunk-65X3S4HB",
    b"chunk-FBGYN3F2",
]


async def _filtered_stderr_reader(read_fd: int):
    """Read from a pipe fd and print lines that are not part of a 409 block."""
    loop = asyncio.get_event_loop()
    suppress_remaining = 0
    buf = b""
    try:
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        transport, _ = await loop.connect_read_pipe(lambda: protocol, os.fdopen(read_fd, "rb", 0))
        async for raw in reader:
            buf += raw
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if suppress_remaining > 0:
                    suppress_remaining -= 1
                    continue
                if any(pat in line for pat in _SUPPRESS):
                    suppress_remaining = 5
                    continue
                text = line.decode("utf-8", errors="replace").rstrip()
                if text:
                    print(text, file=sys.stderr)
    except Exception:
        pass
    finally:
        try:
            transport.close()
        except Exception:
            pass


import mcp.client.stdio as _mcp_stdio
_original_create_process = _mcp_stdio._create_platform_compatible_process


async def _patched_create_process(command, args, env=None, errlog=sys.stderr, cwd=None):
    """Replacement for _create_platform_compatible_process that intercepts stderr
    via an OS-level pipe so we can filter out benign 409 messages from mcp-remote."""
    # Only intercept when errlog is our filtered writer — for other callers behave normally
    if not isinstance(errlog, _FilteredStderrWriter):
        return await _original_create_process(command, args, env=env, errlog=errlog, cwd=cwd)

    import anyio
    read_fd, write_fd = os.pipe()

    process = await anyio.open_process(
        [command, *args],
        env=env,
        stderr=write_fd,   # child writes to write end of pipe
        cwd=cwd,
        start_new_session=True,
    )
    # Close write end in parent — child holds it open
    os.close(write_fd)

    # Start background reader that filters the pipe output
    asyncio.create_task(_filtered_stderr_reader(read_fd))

    return process


_mcp_stdio._create_platform_compatible_process = _patched_create_process


class _FilteredStderrWriter:
    """Sentinel class — presence is checked by _patched_create_process to
    decide whether to activate pipe-based stderr filtering."""
    pass


class MCPClientManager:
    """Manages connections to multiple MCP servers."""
    def __init__(self, config: dict):
        self.config = config
        self.sessions: List[ClientSession] = []
        self._tasks: List[asyncio.Task] = []
        self._stop_events: List[asyncio.Event] = []
        self._tools_cache: dict = {}

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

        server_params = StdioServerParameters(command=command, args=args, env=merged_env)

        # Pass the sentinel so _patched_create_process activates pipe-based filtering
        filtered_stderr = _FilteredStderrWriter()

        session_ref = None
        try:
            async with stdio_client(server_params, errlog=filtered_stderr) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    session_ref = session
                    await session.initialize()
                    self.sessions.append(session)
                    print(f"=> Servidor '{name}' inicializado correctamente.")
                    ready_event.set()

                    # Pre-load tools into cache to avoid a second wire call
                    # (which would trigger another 409 attempt from mcp-remote)
                    try:
                        tools = await load_mcp_tools(session)
                        self._tools_cache[id(session)] = tools
                    except Exception as e:
                        if "409" not in str(e) and "Conflict" not in str(e):
                            print(f"Advertencia: No se pudo pre-cargar tools de '{name}': {e}")
                        self._tools_cache[id(session)] = []

                    await stop_event.wait()

        except Exception as e:
            print(f"Error en servidor stdio '{name}': {e}")
            ready_event.set()
        finally:
            if session_ref in self.sessions:
                self.sessions.remove(session_ref)
            self._tools_cache.pop(id(session_ref), None)

    async def get_all_tools(self) -> list:
        """Return tools from all connected MCP sessions using cache."""
        all_tools = []
        for session in self.sessions:
            session_id = id(session)
            if session_id in self._tools_cache:
                tools = self._tools_cache[session_id]
            else:
                try:
                    tools = await load_mcp_tools(session)
                    self._tools_cache[session_id] = tools
                except Exception as e:
                    print(f"Error obteniendo herramientas de una sesión: {e}")
                    tools = []

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
