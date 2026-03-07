# main.py

import os
import sys
import threading

from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel

from .agent import SYSTEM_PROMPT, CodingAgent
from .session_manager import SessionManager

load_dotenv()


API_KEY = os.getenv("API_KEY")
ENDPOINT_URL = os.getenv("ENDPOINT_URL")

if not API_KEY or not ENDPOINT_URL:
    print("Error: API_KEY and ENDPOINT_URL must be set in the .env file.")
    sys.exit(1)


console = Console()
verbose_mode = True

SLASH_COMMANDS = {
    "/sessions": "List all saved sessions",
    "/new": "Start a new session",
    "/delete": "Delete a session",
    "/load": "Load a saved session",
    "/model": "Show, list, or switch models",
    "/usage": "Show API token usage",
    "/verbose": "Toggle verbose/compact tool output",
    "/mcp": "Show MCP server status",
    "/quit": "Exit the program",
    "/help": "Show help message",
}


class SlashCommandCompleter(Completer):
    def __init__(self, agent=None):
        self.agent = agent
        self._cached_models = None

    def _get_models(self):
        return self._cached_models or []

    def fetch_models(self):
        if self.agent:
            try:
                self._cached_models = self.agent.list_models()
            except Exception:
                self._cached_models = []

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if not text.startswith("/"):
            return

        parts = text.split(None, 1)

        # Still typing the command name
        if len(parts) == 1 and not text.endswith(" "):
            for cmd, desc in SLASH_COMMANDS.items():
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text), display_meta=desc)
            return

        # Subcommand completions for /model
        if parts[0] == "/model":
            arg = parts[1] if len(parts) > 1 else ""
            if "list".startswith(arg):
                yield Completion(
                    "list",
                    start_position=-len(arg),
                    display_meta="Show available models",
                )
            for model_id in self._get_models():
                if model_id.startswith(arg):
                    active = (
                        "current" if self.agent and model_id == self.agent.model else ""
                    )
                    yield Completion(
                        model_id, start_position=-len(arg), display_meta=active
                    )


def print_session_table(sessions: list):
    """Helper to print a table of saved sessions."""
    from rich.table import Table

    table = Table(title="Saved Sessions", border_style="cyan")
    table.add_column("ID", style="dim")
    table.add_column("Title", style="bold")
    table.add_column("Last Updated", style="dim")

    for session in sessions:
        table.add_row(session["id"], session["title"], session["updated_at"])

    console.print(table)


def handle_slash_commands(
    command: str, agent: CodingAgent, manager: SessionManager, session_id, session_title
) -> tuple[str | None, str]:
    """Router for local CLI commands. Returns (session_id, session_title)."""
    parts = command.split()
    cmd = parts[0].lower()

    if cmd == "/sessions":
        print_session_table(manager.list_sessions())

    elif cmd == "/load" and len(parts) > 1:
        target_id = parts[1]
        session_data = manager.load_session(target_id)
        if session_data:
            loaded_messages = session_data["messages"]
            # Reconcile system prompt: always use the current one
            if loaded_messages and loaded_messages[0].get("role") == "system":
                loaded_messages[0] = {"role": "system", "content": SYSTEM_PROMPT}
            agent.messages = loaded_messages
            agent.full_history = list(loaded_messages)
            session_id = session_data["id"]
            session_title = session_data["title"]
            console.print(
                f"[bold green]Session '{session_data['title']}' loaded successfully![/bold green]"
            )
        else:
            console.print(
                f"[bold red]No session found with ID '{target_id}'.[/bold red]"
            )

    elif cmd == "/new":
        agent.reset()
        session_id = None
        session_title = "New Chat"
        console.print("[bold green]Started a new session.[/bold green]")

    elif cmd == "/delete":
        if len(parts) > 1:
            target_id = parts[1]
            if manager.delete_session(target_id):
                console.print(
                    f"[bold green]Session '{target_id}' deleted successfully![/bold green]"
                )
            else:
                console.print(
                    f"[bold red]No session found with ID '{target_id}'.[/bold red]"
                )
        else:
            console.print("[bold red]Usage: /delete <session_id>[/bold red]")

    elif cmd == "/model":
        if len(parts) == 1:
            console.print(f"[bold]Current model:[/bold] {agent.model}")
        elif parts[1] == "list":
            try:
                models = agent.list_models()
                console.print("[bold]Available models:[/bold]")
                for m in models:
                    marker = " [green]◀[/green]" if m == agent.model else ""
                    console.print(f"  {m}{marker}")
            except Exception as e:
                console.print(f"[bold red]Failed to fetch models: {e}[/bold red]")
        else:
            agent.model = parts[1]
            console.print(f"[bold green]Model set to: {agent.model}[/bold green]")

    elif cmd == "/usage":
        usage = agent.get_usage()
        console.print(
            Panel.fit(
                f"Tokens used: {usage['total_tokens']} (Prompt: {usage['total_prompt_tokens']}, Completion: {usage['total_completion_tokens']})",
                title="API Usage",
                border_style="magenta",
            )
        )

    elif cmd == "/verbose":
        global verbose_mode
        verbose_mode = not verbose_mode
        label = "verbose" if verbose_mode else "compact"
        console.print(f"[bold green]Tool output: {label}[/bold green]")

    elif cmd == "/mcp":
        if not agent.mcp_manager:
            console.print("[dim]No MCP config found (mcp_config.json).[/dim]")
        elif len(parts) > 1 and parts[1] == "tools":
            try:
                tools = agent.mcp_manager.get_tools()
                if tools:
                    from rich.table import Table

                    table = Table(title="MCP Tools", border_style="cyan")
                    table.add_column("Name", style="bold")
                    table.add_column("Description", style="dim")
                    for t in tools:
                        fn = t["function"]
                        table.add_row(fn["name"], fn.get("description", ""))
                    console.print(table)
                else:
                    console.print("[dim]No MCP tools available.[/dim]")
            except Exception as e:
                console.print(f"[bold red]Failed to list MCP tools: {e}[/bold red]")
        else:
            from rich.table import Table

            status = agent.mcp_manager.get_server_status()
            table = Table(title="MCP Servers", border_style="cyan")
            table.add_column("Server", style="bold")
            table.add_column("Status")
            for name, st in status.items():
                style = "green" if st == "running" else "red"
                table.add_row(name, f"[{style}]{st}[/{style}]")
            console.print(table)

    elif cmd == "/quit" or cmd == "/exit":
        if session_id:
            manager.save_session(session_id, session_title, agent.full_history)
        if agent.mcp_manager:
            agent.mcp_manager.shutdown()
        console.print("[bold red]Exiting...[/bold red]")
        sys.exit(0)

    else:
        console.print(
            Panel.fit(
                "[bold cyan]/sessions[/] - List all saved sessions\n"
                "[bold cyan]/new[/] - Start a new session\n"
                "[bold cyan]/load <session_name>[/] - Load a saved session\n"
                "[bold cyan]/delete <session_name>[/] - Delete a session\n"
                "[bold cyan]/model[/] - Show current model\n"
                "[bold cyan]/model list[/] - List available models\n"
                "[bold cyan]/model <name>[/] - Switch model\n"
                "[bold cyan]/usage[/] - Show API token usage\n"
                "[bold cyan]/verbose[/] - Toggle verbose/compact tool output\n"
                "[bold cyan]/mcp[/] - Show MCP server status\n"
                "[bold cyan]/mcp tools[/] - List available MCP tools\n"
                "[bold cyan]/quit[/] - Exit the program\n"
                "[bold cyan]/help[/] - Show this help message",
                title="Available Commands",
                border_style="cyan",
            )
        )

    return session_id, session_title


def create_prompt_session(agent: CodingAgent) -> PromptSession:
    """Create a prompt_toolkit session. Enter submits."""
    return PromptSession(
        completer=SlashCommandCompleter(agent), complete_while_typing=True
    )


def main():

    def print_agent_notification(message: str) -> None:
        console.print(message)

    spinner = None

    def stop_spinner():
        nonlocal spinner
        if spinner is not None:
            spinner.stop()
            spinner = None

    def start_spinner():
        nonlocal spinner
        spinner = console.status("Thinking…", spinner="dots")
        spinner.start()

    def print_stream_chunk(chunk: str) -> None:
        stop_spinner()
        sys.stdout.write(chunk)
        sys.stdout.flush()

    agent = CodingAgent(
        api_key=API_KEY,
        endpoint_url=ENDPOINT_URL,
        ui_callback=print_agent_notification,
        stream_callback=print_stream_chunk,
    )
    manager = SessionManager()
    session = create_prompt_session(agent)
    threading.Thread(target=session.completer.fetch_models, daemon=True).start()

    def get_toolbar():
        usage = agent.get_usage()
        return HTML(
            f" <b>{agent.model}</b> │ {usage['total_prompt_tokens']:,} in / {usage['total_completion_tokens']:,} out"
        )

    current_session_id = None
    current_session_title = "New Chat"

    console.print("[bold cyan]Welcome to the AI Coding Agent![/bold cyan]")
    console.print("[dim]Enter to submit. Ctrl+J for newline.[/dim]")

    while True:
        try:
            user_input = session.prompt("\n> ", bottom_toolbar=get_toolbar).strip()
        except (KeyboardInterrupt, EOFError):
            if current_session_id:
                manager.save_session(
                    current_session_id, current_session_title, agent.full_history
                )
            if agent.mcp_manager:
                agent.mcp_manager.shutdown()
            console.print("\n[bold red]Exiting...[/bold red]")
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            current_session_id, current_session_title = handle_slash_commands(
                user_input, agent, manager, current_session_id, current_session_title
            )
            continue

        agent.add_user_task(user_input)

        if current_session_id is None:
            current_session_title = agent.generate_title(user_input)
            current_session_id = manager.create_session(
                agent.messages, current_session_title
            )

        done = False
        step = 1
        max_steps = 35

        try:
            while not done:
                if step > max_steps:
                    console.print(
                        f"\n[bold yellow]Agent reached the maximum of {max_steps} steps.[/bold yellow]"
                    )
                    keep_going = (
                        session.prompt(
                            "Do you want to give it 10 more steps to finish? (y/n): ",
                            bottom_toolbar=get_toolbar,
                        )
                        .strip()
                        .lower()
                    )

                    if keep_going == "y":
                        max_steps += 10
                    else:
                        # Force the agent to summarize what it did instead of just cutting off
                        start_spinner()
                        result, msg = agent.run_step(force_text=True)
                        stop_spinner()
                        if result not in ("tool_used", "error"):
                            console.print("\n[bold green]Agent Summary:[/bold green]")
                            console.print(Panel(Markdown(result), border_style="green"))
                        break

                # On the last allowed step, force a text response so the agent wraps up
                force_text = step == max_steps
                start_spinner()
                result, msg = agent.run_step(force_text=force_text)
                stop_spinner()

                if result == "error":
                    break
                elif result == "tool_used":
                    for tc in msg:
                        is_error = tc["result"].startswith("Error")
                        if verbose_mode:
                            args_str = ", ".join(
                                f'{k}="{v}"' for k, v in tc["args"].items()
                            )
                            result_style = "red" if is_error else "green"
                            result_icon = "✗" if is_error else "✓"
                            console.print(
                                f" [bold]┃[/bold] [bold]{tc['name']}[/bold]([dim]{args_str}[/dim])"
                            )
                            console.print(
                                f" [bold]┃[/bold] [{result_style}]{result_icon} {tc['result']}[/{result_style}]"
                            )
                            console.print(" [bold]┃[/bold]")
                        else:
                            icon = "[red]✗[/red]" if is_error else "[green]✓[/green]"
                            console.print(f" {icon} [bold]{tc['name']}[/bold]")
                else:
                    sys.stdout.write("\n")
                    # console.print("\n[bold green]Agent Finished Task:[/bold green]")
                    # console.print(Panel(Markdown(result), border_style="green"))
                    done = True

                step += 1

        except KeyboardInterrupt:
            console.print("\n[bold yellow]Task cancelled.[/bold yellow]")

        finally:
            manager.save_session(
                current_session_id, current_session_title, agent.full_history
            )


if __name__ == "__main__":
    main()
