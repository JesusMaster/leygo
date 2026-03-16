import asyncio
import os
import sys
import logging
from typing import List
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
from langchain_mcp_adapters.tools import load_mcp_tools

logging.getLogger("mcp_remote").setLevel(logging.CRITICAL)
logging.getLogger("mcp.client").setLevel(logging.CRITICAL)


class MCPClientManager:
    """Manages connections to multiple MCP servers."""

    def __init__(self, config: dict):
        self.config = config
        self.sessions: List[ClientSession] = []
        self._tasks: List[asyncio.Task] = []
        self._stop_events: List[asyncio.Event] = []
        self._tools_cache: dict = {}

    async def connect_all(self):
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
            elif transport == "stdio":
                task = asyncio.create_task(self._run_stdio_server(name, server_config, stop_event, ready_event))
            else:
                print(f"Transporte desconocido '{transport}' para el servidor '{name}'")
                ready_event.set()
                continue
            self._tasks.append(task)

        if ready_events:
            await asyncio.gather(*(e.wait() for e in ready_events))

    async def _run_sse_server(self, name, server_config, stop_event, ready_event):
        url = server_config.get("url")
        if not url:
            print(f"Error: URL missing for SSE server '{name}'")
            ready_event.set()
            return
        env = server_config.get("env", {})
        kwargs = {"headers": env} if env else {}
        session_ref = None
        try:
            async with sse_client(url, **kwargs) as (r, w):
                async with ClientSession(r, w) as session:
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

    async def _run_stdio_server(self, name, server_config, stop_event, ready_event):
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

        # Route the child process stderr to /dev/null to silence benign 409 messages
        # from mcp-remote. These occur when mcp-remote tries to open an SSE notification
        # push channel on a StreamableHTTP server after initialize() — the server rejects
        # it with 409 because the session is already active. This is by design in
        # mcp-remote and the session works correctly regardless.
        # NOTE: real errors (e.g. authentication failures) will also be suppressed.
        # If you need to debug mcp-remote, change devnull to sys.stderr temporarily.
        devnull = open(os.devnull, "w")

        session_ref = None
        try:
            async with stdio_client(server_params, errlog=devnull) as (r, w):
                async with ClientSession(r, w) as session:
                    session_ref = session
                    await session.initialize()
                    self.sessions.append(session)
                    print(f"=> Servidor '{name}' inicializado correctamente.")
                    ready_event.set()

                    # Pre-load tools once right after initialization.
                    # Avoids a second tools/list call later which triggers another 409.
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
            devnull.close()
            if session_ref in self.sessions:
                self.sessions.remove(session_ref)
            self._tools_cache.pop(id(session_ref), None)

    async def get_all_tools(self) -> list:
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
        for event in self._stop_events:
            event.set()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self.sessions.clear()
        self._tasks.clear()
        self._stop_events.clear()
        self._tools_cache.clear()
