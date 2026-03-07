import asyncio
import json
import os
import re

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


GLOBAL_CONFIG = os.path.join(
    os.path.expanduser("~/.coding-agent"),
    "mcp_config.json",
)
PROJECT_CONFIG = os.path.join(os.getcwd(), "mcp_config.json")


class MCPManager:
    def __init__(self, config_paths: list[str]) -> None:
        self._config_paths = config_paths
        self._config: dict = {}
        self._loop = asyncio.new_event_loop()
        self._sessions: dict[str, ClientSession] = {}
        self._stdio_contexts: dict[str, object] = {}
        self._session_contexts: dict[str, object] = {}
        self._initialized = False

    def initialize(self) -> None:
        """Load config and start all MCP servers. Blocks until ready."""
        self._config = self._load_config()
        self._loop.run_until_complete(self._start_servers())
        self._initialized = True

    def shutdown(self) -> None:
        """Stop all servers and close the event loop."""
        if self._initialized:
            self._loop.run_until_complete(self._stop_servers())
            self._initialized = False
        self._loop.close()

    def get_tools(self) -> list[dict]:
        """Return all MCP tools in OpenAI function calling format."""
        return self._loop.run_until_complete(self._list_tools())

    def call_tool(self, prefixed_name: str, arguments: dict) -> str:
        """Route a prefixed tool call (server__tool) to the correct MCP server."""
        server_name, tool_name = prefixed_name.split("__", 1)
        return self._loop.run_until_complete(
            self._call_tool(server_name, tool_name, arguments)
        )

    def get_server_status(self) -> dict[str, str]:
        """Return {server_name: 'running' | 'stopped'} for each configured server."""
        status = {}
        for name in self._config.get("mcpServers", {}):
            status[name] = "running" if name in self._sessions else "stopped"
        return status

    async def _start_servers(self) -> None:
        """Connect to each configured MCP server via stdio."""
        for name, cfg in self._config.get("mcpServers", {}).items():
            try:
                env = {**os.environ, **cfg.get("env", {})}
                params = StdioServerParameters(
                    command=cfg["command"],
                    args=cfg.get("args", []),
                    env=env,
                )
                stdio_ctx = stdio_client(params)
                read, write = await stdio_ctx.__aenter__()
                self._stdio_contexts[name] = stdio_ctx

                session_ctx = ClientSession(read, write)
                session = await session_ctx.__aenter__()
                self._session_contexts[name] = session_ctx

                await session.initialize()
                self._sessions[name] = session
            except Exception as e:
                # Skip servers that fail to start; don't crash the agent
                print(f"Warning: MCP server '{name}' failed to start: {e}")

    async def _stop_servers(self) -> None:
        """Close all sessions and stdio connections."""
        for name in list(self._sessions):
            try:
                session_ctx = self._session_contexts.pop(name, None)
                if session_ctx:
                    await session_ctx.__aexit__(None, None, None)
            except Exception:
                pass
            try:
                stdio_ctx = self._stdio_contexts.pop(name, None)
                if stdio_ctx:
                    await stdio_ctx.__aexit__(None, None, None)
            except Exception:
                pass
            self._sessions.pop(name, None)

    async def _list_tools(self) -> list[dict]:
        """Query all connected servers for tools, return in OpenAI format."""
        tools = []
        for name, session in self._sessions.items():
            try:
                result = await session.list_tools()
                for tool in result.tools:
                    tools.append(self._convert_to_openai_schema(name, tool))
            except Exception:
                pass
        return tools

    async def _call_tool(
        self, server_name: str, tool_name: str, arguments: dict
    ) -> str:
        """Call a specific tool on a specific server, return result as string."""
        if server_name not in self._sessions:
            return f"Error: MCP server '{server_name}' not found"
        session = self._sessions[server_name]
        result = await session.call_tool(tool_name, arguments)
        if result.content:
            parts = []
            for block in result.content:
                if hasattr(block, "text"):
                    parts.append(block.text)
                else:
                    parts.append(str(block))
            return "\n".join(parts)
        return ""

    def _load_config(self) -> dict:
        """Load and merge configs: global first, project overrides on top."""
        merged: dict = {"mcpServers": {}}
        for path in self._config_paths:
            if not os.path.exists(path):
                continue
            with open(path) as f:
                config = json.load(f)
            for name, server_cfg in config.get("mcpServers", {}).items():
                env = server_cfg.get("env", {})
                for key, value in env.items():
                    if isinstance(value, str):
                        env[key] = re.sub(
                            r"\$\{(\w+)\}",
                            lambda m: os.environ.get(m.group(1), m.group(0)),
                            value,
                        )
                merged["mcpServers"][name] = server_cfg
        return merged

    @staticmethod
    def _convert_to_openai_schema(server_name: str, mcp_tool) -> dict:
        """Convert an MCP tool to OpenAI function calling format."""
        return {
            "type": "function",
            "function": {
                "name": f"{server_name}__{mcp_tool.name}",
                "description": mcp_tool.description or "",
                "parameters": mcp_tool.inputSchema,
            },
        }
