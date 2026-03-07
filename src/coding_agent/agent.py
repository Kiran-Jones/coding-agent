import inspect
import json
import os

import requests

from .memory_utils import smart_compact
from .tools import AVAILABLE_TOOLS, TOOL_SCHEMAS

SYSTEM_PROMPT = "You are a coding agent. You have tools to write files and run terminal commands. Do NOT output raw code blocks for me to run. Use your 'write_file' tool to create the python scripts, and use your 'run_terminal_command' tool to execute and test them. When you have successfully completed the task and verified it works, just reply with a friendly message explaining what you did."


class CodingAgent:
    def __init__(self, api_key, endpoint_url, ui_callback=None, stream_callback=None):
        self.api_key = api_key
        self.endpoint_url = endpoint_url

        self.ui_callback = ui_callback if ui_callback else lambda msg: None
        self.stream_callback = stream_callback if stream_callback else lambda msg: None

        self.model = os.getenv("MODEL_NAME", "qwen.qwen3-vl-32b-instruct-fp8")
        self.title_model = os.getenv("TITLE_MODEL", self.model)
        self.summary_model = os.getenv("SUMMARY_MODEL", self.model)
        self.messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ]
        self.full_history = list(self.messages)

        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0

        self.mcp_manager = None
        try:
            from .mcp_manager import MCPManager, GLOBAL_CONFIG, PROJECT_CONFIG

            config_paths = [GLOBAL_CONFIG, PROJECT_CONFIG]
            if any(os.path.exists(p) for p in config_paths):
                self.mcp_manager = MCPManager(config_paths)
                self.mcp_manager.initialize()
        except Exception as e:
            self.ui_callback(f"[bold red]Failed to initialize MCP: {e}[/bold red]")


    def run_step(self, force_text=False) -> tuple[str, dict | None]:
        self.messages, did_compact = smart_compact(
            self.messages, self.api_key, self.endpoint_url, self.summary_model
        )

        if did_compact:
            self.ui_callback(
                "[italic dim yellow]Auto compacted message history[/italic dim yellow]"
            )

        payload = {
            "model": self.model,
            "messages": self.messages,
            "tools": self._get_all_tools(),
            "tool_choice": "none" if force_text else "auto",
            "stream": True,
            "stream_options": {"include_usage": True},
        }

        response = requests.post(
            self.endpoint_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
            stream=True,
        )

        if response.status_code != 200:
            error_msg = f"API request failed with status {response.status_code}: {response.text}"
            self.ui_callback(f"[bold red]{error_msg}[/bold red]")
            return "error", None

        message, usage = self._parse_stream(response)

        prompt_tokens = usage.get("prompt_tokens", 0)
        completion_tokens = usage.get("completion_tokens", 0)
        self.total_prompt_tokens += prompt_tokens
        self.total_completion_tokens += completion_tokens

        self.messages.append(message)
        self.full_history.append(message)

        if message.get("tool_calls"):
            summaries = self._handle_tool_calls(message["tool_calls"])
            return "tool_used", summaries

        return message.get("content", ""), None

    def _parse_stream(self, response: requests.Response) -> tuple[dict, dict]:
        content_parts = []
        tool_calls_by_index = {}
        role = "assistant"
        usage = {}

        for line in response.iter_lines(decode_unicode=True):
            if not line or not line.startswith("data: "):
                continue

            data_str = line[6:]

            if data_str.strip() == "[DONE]":
                break
            try:
                chunk = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            if "usage" in chunk:
                usage = chunk["usage"]

            choice = chunk["choices"][0] if chunk.get("choices") else None
            if not choice:
                continue

            delta = choice.get("delta", {})

            if "content" in delta and delta["content"]:
                content_parts.append(delta["content"])
                self.stream_callback(delta["content"])

            if "tool_calls" in delta:
                for tc_delta in delta["tool_calls"]:
                    index = tc_delta.get("index", 0)
                    if index not in tool_calls_by_index:
                        tool_calls_by_index[index] = {
                            "id": tc_delta.get("id", ""),
                            "type": "function",
                            "function": {
                                "name": tc_delta.get("function", {}).get("name", ""),
                                "arguments": "",
                            },
                        }

                    arg_chunk = tc_delta.get("function", {}).get("arguments", "")
                    if arg_chunk:
                        tool_calls_by_index[index]["function"]["arguments"] += arg_chunk
        message = {"role": role, "content": "".join(content_parts) or None}
        if tool_calls_by_index:
            message["tool_calls"] = [
                tool_calls_by_index[i] for i in sorted(tool_calls_by_index)
            ]

        return message, usage

    def _handle_tool_calls(self, tool_calls: list) -> list[dict]:
        summaries = []
        for tool_call in tool_calls:
            func_name = tool_call["function"]["name"]
            arguments = json.loads(tool_call["function"]["arguments"])

            if "__" in func_name and self.mcp_manager:
                try:
                    result = self.mcp_manager.call_tool(func_name, arguments)
                except Exception as e:
                    result = f"Error: MCP tool failed: {e}"
                display_args = arguments
            elif func_name in AVAILABLE_TOOLS:
                func_to_call = AVAILABLE_TOOLS[func_name]
                valid_params = inspect.signature(func_to_call).parameters
                filtered_args = {
                    k: v for k, v in arguments.items() if k in valid_params
                }
                result = str(func_to_call(**filtered_args))
                display_args = filtered_args
            else:
                result = f"Error: Unknown tool '{func_name}'"
                display_args = arguments

            tool_msg = {
                "role": "tool",
                "tool_call_id": tool_call["id"],
                "content": result,
            }
            self.messages.append(tool_msg)
            self.full_history.append(tool_msg)

            truncated_args = {
                k: (str(v)[:100] + "…" if len(str(v)) > 100 else v)
                for k, v in display_args.items()
            }
            truncated_result = result[:200] + "…" if len(result) > 200 else result
            summaries.append(
                {
                    "name": func_name,
                    "args": truncated_args,
                    "result": truncated_result,
                }
            )
        return summaries

    def add_user_task(self, user_input: str) -> None:
        """Add a user message to the conversation."""
        msg = {"role": "user", "content": user_input}
        self.messages.append(msg)
        self.full_history.append(msg)

    def _get_all_tools(self) -> list[dict]:
        """Return built-in tools plus any MCP tools."""
        tools = list(TOOL_SCHEMAS)
        if self.mcp_manager:
            try:
                tools.extend(self.mcp_manager.get_tools())
            except Exception:
                pass
        return tools

    def list_models(self) -> list[str]:
        """Fetch available model IDs from the API."""
        # Derive models URL from the completions endpoint
        base_url = self.endpoint_url.rsplit("/chat/completions", 1)[0]
        models_url = f"{base_url}/models"
        response = requests.get(
            models_url,
            headers={"Authorization": f"Bearer {self.api_key}"},
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()
        return sorted(m["id"] for m in data.get("data", []))

    def generate_title(self, user_input: str) -> str:
        """Generate a short session title from the first user message."""
        try:
            response = requests.post(
                self.endpoint_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.title_model,
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Generate a short title (max 6 words, no quotes) for a coding session that starts with this request:\n\n{user_input[:500]}",
                        }
                    ],
                    "temperature": 0.3,
                },
                timeout=10,
            )
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"].strip()
        except Exception:
            pass
        return "New Chat"

    def reset(self):
        self.messages = [
            {
                "role": "system",
                "content": SYSTEM_PROMPT,
            }
        ]
        self.full_history = list(self.messages)

    def get_usage(self) -> dict:
        return {
            "total_prompt_tokens": self.total_prompt_tokens,
            "total_completion_tokens": self.total_completion_tokens,
            "total_tokens": self.total_prompt_tokens + self.total_completion_tokens,
        }
