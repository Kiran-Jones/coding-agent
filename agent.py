import inspect
import json
import os

import requests

from memory_utils import smart_compact
from tools import AVAILABLE_TOOLS, TOOL_SCHEMAS

SYSTEM_PROMPT = "You are a coding agent. You have tools to write files and run terminal commands. Do NOT output raw code blocks for me to run. Use your 'write_file' tool to create the python scripts, and use your 'run_terminal_command' tool to execute and test them. When you have successfully completed the task and verified it works, just reply with a friendly message explaining what you did."


class CodingAgent:
    def __init__(self, api_key, endpoint_url, ui_callback=None):
        self.api_key = api_key
        self.endpoint_url = endpoint_url

        self.ui_callback = ui_callback if ui_callback else lambda msg: None

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

    def add_user_task(self, prompt: str):
        msg = {"role": "user", "content": prompt}
        self.messages.append(msg)
        self.full_history.append(msg)

    def run_step(self, force_text=False):
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
            "tools": TOOL_SCHEMAS,
            "tool_choice": "none" if force_text else "auto",
        }

        response = requests.post(
            self.endpoint_url,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            json=payload,
        )

        if response.status_code != 200:
            error_msg = f"API request failed with status {response.status_code}: {response.text}"
            self.ui_callback(f"[bold red]{error_msg}[/bold red]")
            return "error"

        message = response.json()["choices"][0]["message"]
        self.messages.append(message)
        self.full_history.append(message)

        if message.get("tool_calls"):
            self._handle_tool_calls(message["tool_calls"])
            return "tool_used"

        return message.get("content", "")

    def _handle_tool_calls(self, tool_calls):
        for tool_call in tool_calls:
            func_name = tool_call["function"]["name"]
            arguments = json.loads(tool_call["function"]["arguments"])

            if func_name in AVAILABLE_TOOLS:
                func_to_call = AVAILABLE_TOOLS[func_name]
                # Filter out any arguments the LLM hallucinated
                valid_params = inspect.signature(func_to_call).parameters
                filtered_args = {
                    k: v for k, v in arguments.items() if k in valid_params
                }
                result = func_to_call(**filtered_args)

                # Report the result back to the LLM's memory
                tool_msg = {
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": str(result),
                }
                self.messages.append(tool_msg)
                self.full_history.append(tool_msg)

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
