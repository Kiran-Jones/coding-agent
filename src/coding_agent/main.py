# main.py

import os
import re
import shutil
import sys
import threading
import time

from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table

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
    # Sessions
    "/new": "Start a new session",
    "/sessions": "List all saved sessions",
    "/load": "Load a saved session",
    "/delete": "Delete a session",
    # Workflow
    "/plan": "Plan before executing",
    "/history": "Show agent file change history",
    "/undo": "Undo last file change",
    "/redo": "Redo last undone change",
    # Settings
    "/model": "Show, list, or switch models",
    "/usage": "Show API token usage",
    "/verbose": "Toggle verbose/compact tool output",
    "/mcp": "Show MCP server status",
    # Meta
    "/help": "Show help message",
    "/quit": "Exit the program",
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

    def _complete_file_path(self, partial: str):
        """Yield file path completions for a partial path after '@'."""
        # Split into directory part and name prefix
        if "/" in partial:
            dir_part, prefix = partial.rsplit("/", 1)
            search_dir = os.path.abspath(dir_part)
        else:
            dir_part, prefix = "", partial
            search_dir = os.getcwd()

        if not os.path.isdir(search_dir):
            return

        try:
            entries = os.listdir(search_dir)
        except OSError:
            return

        # Fuzzy-ish: match entries that contain the prefix (case-insensitive)
        prefix_lower = prefix.lower()
        for entry in sorted(entries):
            if entry.startswith("."):
                continue
            if prefix_lower and prefix_lower not in entry.lower():
                continue

            full_path = os.path.join(search_dir, entry)
            rel = f"{dir_part}/{entry}" if dir_part else entry
            is_dir = os.path.isdir(full_path)

            if is_dir:
                yield Completion(
                    rel + "/",
                    start_position=-len(partial),
                    display_meta="dir",
                )
            else:
                yield Completion(
                    rel,
                    start_position=-len(partial),
                    display_meta="file",
                )

    def get_completions(self, document, complete_event):
        text = document.text_before_cursor

        # --- @file mention completions ---
        # Find the last '@' that could be a file mention
        at_idx = text.rfind("@")
        if at_idx >= 0:
            # '@' must be at start or preceded by whitespace
            if at_idx == 0 or text[at_idx - 1] in (" ", "\t"):
                partial = text[at_idx + 1 :]
                # Only complete if partial looks like a path (no spaces)
                if " " not in partial:
                    for completion in self._complete_file_path(partial):
                        yield completion
                    return

        # --- Slash command completions ---
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
            loaded_full_history = session_data["full_history"]
            # Reconcile system prompt: always use the current one
            if loaded_messages and loaded_messages[0].get("role") == "system":
                loaded_messages[0] = {"role": "system", "content": SYSTEM_PROMPT}
            if loaded_full_history and loaded_full_history[0].get("role") == "system":
                loaded_full_history[0] = {"role": "system", "content": SYSTEM_PROMPT}
            agent.messages = loaded_messages
            agent.full_history = loaded_full_history
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

    elif cmd == "/history":
        history = agent.snapshot_manager.get_history()
        if not history:
            console.print("[dim]No file changes yet.[/dim]")
        else:
            table = Table(title="File Change History", border_style="cyan")
            table.add_column("#", style="dim")
            table.add_column("File", style="bold")
            table.add_column("Action")
            table.add_column("Time", style="dim")
            for entry in history:
                ago = int(time.time() - entry["timestamp"])
                if ago < 60:
                    time_str = f"{ago}s ago"
                else:
                    time_str = f"{ago // 60}m ago"
                table.add_row(
                    str(entry["id"]),
                    entry["file_path"],
                    entry["action"],
                    time_str,
                )
            console.print(table)

    elif cmd == "/undo":
        result = agent.snapshot_manager.undo()
        if result:
            console.print(
                f"[bold green]Undid change to {result['file_path']}[/bold green]"
            )
        else:
            console.print("[dim]Nothing to undo.[/dim]")

    elif cmd == "/redo":
        result = agent.snapshot_manager.redo()
        if result:
            console.print(
                f"[bold green]Redid change to {result['file_path']}[/bold green]"
            )
        else:
            console.print("[dim]Nothing to redo.[/dim]")

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
            manager.save_session(
                session_id, session_title, agent.messages, agent.full_history
            )
        if agent.mcp_manager:
            agent.mcp_manager.shutdown()
        console.print("[bold red]Exiting...[/bold red]")
        sys.exit(0)

    else:
        console.print(
            Panel.fit(
                "[bold dim]Sessions[/bold dim]\n"
                "[bold cyan]/new[/] - Start a new session\n"
                "[bold cyan]/sessions[/] - List all saved sessions\n"
                "[bold cyan]/load <id>[/] - Load a saved session\n"
                "[bold cyan]/delete <id>[/] - Delete a session\n"
                "\n[bold dim]Workflow[/bold dim]\n"
                "[bold cyan]/plan <task>[/] - Plan before executing\n"
                "[bold cyan]/history[/] - Show agent file change history\n"
                "[bold cyan]/undo[/] - Undo last file change\n"
                "[bold cyan]/redo[/] - Redo last undone change\n"
                "\n[bold dim]Settings[/bold dim]\n"
                "[bold cyan]/model[/] - Show, list, or switch models\n"
                "[bold cyan]/usage[/] - Show API token usage\n"
                "[bold cyan]/verbose[/] - Toggle verbose/compact tool output\n"
                "[bold cyan]/mcp[/] - Show MCP server status\n"
                "\n[bold dim]Meta[/bold dim]\n"
                "[bold cyan]/help[/] - Show this help message\n"
                "[bold cyan]/quit[/] - Exit the program",
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


def parse_file_mentions(text: str) -> str:
    """Replace @file mentions with the file's content injected into the message."""
    mentions = re.findall(r"@([\w/.-]+(?::\d+-\d+)?)", text)
    if not mentions:
        return text

    # Remove @mentions from the text, keeping just the filename
    clean_text = re.sub(r"@([\w/.-]+(?::\d+-\d+)?)", r"`\1`", text)

    file_blocks = []
    for mention in mentions:
        # Parse optional line range: file.py:10-20
        if ":" in mention and mention.rsplit(":", 1)[1].replace("-", "").isdigit():
            filepath, line_range = mention.rsplit(":", 1)
        else:
            filepath, line_range = mention, None

        # Resolve relative to cwd
        resolved = os.path.abspath(filepath)
        if not os.path.isfile(resolved):
            file_blocks.append(f"[File not found: {filepath}]")
            continue

        try:
            with open(resolved) as f:
                lines = f.readlines()
        except Exception as e:
            file_blocks.append(f"[Error reading {filepath}: {e}]")
            continue

        if line_range:
            parts = line_range.split("-")
            start = max(int(parts[0]) - 1, 0)
            end = int(parts[1]) if len(parts) > 1 else start + 1
            selected = lines[start:end]
            header = f"{filepath}:{line_range}"
        else:
            selected = lines
            header = filepath

        # Truncate very large files
        if len(selected) > 500:
            selected = selected[:500]
            header += " (truncated to 500 lines)"

        content = "".join(selected)
        file_blocks.append(f"--- {header} ---\n{content}")

    attached = "\n\n".join(file_blocks)
    return f"{clean_text}\n\n<attached-files>\n{attached}\n</attached-files>"


def main():

    def print_agent_notification(message: str) -> None:
        console.print(message)

    # ── Persistent status bar ──────────────────────────────────────────
    _bar_active = False
    _bar_status = ""
    _bar_last_redraw = 0.0

    def _bar_text(extra: str = "") -> str:
        usage = agent.get_usage()
        text = f" {agent.model} │ {usage['total_prompt_tokens']:,} in / {usage['total_completion_tokens']:,} out"
        if extra:
            text += f" │ {extra}"
        return text

    def _draw_bar(extra: str = "", throttle: bool = False):
        nonlocal _bar_last_redraw
        if not _bar_active:
            return
        if throttle:
            now = time.monotonic()
            if now - _bar_last_redraw < 0.25:
                return
            _bar_last_redraw = now
        size = shutil.get_terminal_size()
        text = _bar_text(extra or _bar_status)
        bar = text.ljust(size.columns)[: size.columns]
        # Use CSI s/u (separate save slot from DEC SC/RC used by enable/disable)
        sys.stdout.write(f"\033[s\033[{size.lines};1H\033[7m{bar}\033[0m\033[u")
        sys.stdout.flush()

    def enable_status_bar():
        nonlocal _bar_active, _bar_status
        if _bar_active:
            return
        _bar_active = True
        _bar_status = ""
        size = shutil.get_terminal_size()
        # DEC save cursor, set scroll region (excludes bottom line, moves cursor
        # to home as a side-effect), DEC restore cursor to where it was.
        sys.stdout.write(f"\0337\033[1;{size.lines - 1}r\0338")
        sys.stdout.flush()
        _draw_bar()

    def disable_status_bar():
        nonlocal _bar_active
        if not _bar_active:
            return
        _bar_active = False
        size = shutil.get_terminal_size()
        # DEC save cursor, clear status line, reset scroll region (moves cursor
        # to home as a side-effect), DEC restore cursor to where it was.
        sys.stdout.write(f"\0337\033[{size.lines};1H\033[K\033[r\0338")
        sys.stdout.flush()

    # ── Spinner replacements (now just status bar text) ────────────────
    def stop_spinner():
        nonlocal _bar_status
        _bar_status = ""
        _draw_bar()

    def start_spinner():
        nonlocal _bar_status
        _bar_status = "Thinking…"
        _draw_bar()

    def print_stream_chunk(chunk: str) -> None:
        nonlocal _bar_status
        if _bar_status == "Thinking…":
            _bar_status = ""
        sys.stdout.write(chunk)
        sys.stdout.flush()
        _draw_bar(throttle=True)

    def approve_tool(func_name: str, arguments: dict) -> bool:
        nonlocal _bar_status
        _bar_status = ""
        _draw_bar()
        arg_summary = ", ".join(f"{k}={str(v)[:80]}" for k, v in arguments.items())
        console.print(f"\n [bold yellow]{func_name}[/bold yellow]({arg_summary})")
        try:
            answer = PromptSession().prompt("   Allow? (y/n) > ").strip().lower()
            return answer in ("y", "yes", "")
        except (KeyboardInterrupt, EOFError):
            return False

    agent = CodingAgent(
        api_key=API_KEY,
        endpoint_url=ENDPOINT_URL,
        ui_callback=print_agent_notification,
        stream_callback=print_stream_chunk,
        approval_callback=approve_tool,
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
                    current_session_id,
                    current_session_title,
                    agent.messages,
                    agent.full_history,
                )
            if agent.mcp_manager:
                agent.mcp_manager.shutdown()
            console.print("\n[bold red]Exiting...[/bold red]")
            break

        if not user_input:
            continue

        if user_input.startswith("/plan"):
            plan_task = user_input[5:].strip()
            if not plan_task:
                console.print("[bold red]Usage: /plan <task description>[/bold red]")
                continue

            console.print(
                Panel(
                    "[bold]Planning mode[/bold] — exploring before executing",
                    border_style="cyan",
                )
            )
            agent.add_user_task(parse_file_mentions(plan_task))

            if current_session_id is None:
                current_session_title = agent.generate_title(plan_task)
                current_session_id = manager.create_session(
                    agent.messages, current_session_title, agent.full_history
                )

            enable_status_bar()
            plan_text = agent.run_plan_loop(
                stream_callback=print_stream_chunk,
                spinner_start=start_spinner,
                spinner_stop=stop_spinner,
            )
            stop_spinner()
            disable_status_bar()

            if not plan_text:
                console.print(
                    "[bold red]Planning failed — no plan produced.[/bold red]"
                )
                continue

            console.print(
                Panel(Markdown(plan_text), title="Proposed Plan", border_style="cyan")
            )
            answer = (
                session.prompt(
                    "  Approve plan? (y/n/edit) > ", bottom_toolbar=get_toolbar
                )
                .strip()
                .lower()
            )

            if answer in ("e", "edit"):
                feedback = session.prompt(
                    "  Your feedback > ", bottom_toolbar=get_toolbar
                ).strip()
                agent.add_user_task(
                    f"Revise your plan based on this feedback: {feedback}"
                )
                enable_status_bar()
                plan_text = agent.run_plan_loop(
                    stream_callback=print_stream_chunk,
                    spinner_start=start_spinner,
                    spinner_stop=stop_spinner,
                )
                stop_spinner()
                disable_status_bar()
                if plan_text:
                    console.print(
                        Panel(
                            Markdown(plan_text),
                            title="Revised Plan",
                            border_style="cyan",
                        )
                    )
                    answer = (
                        session.prompt(
                            "  Approve plan? (y/n) > ", bottom_toolbar=get_toolbar
                        )
                        .strip()
                        .lower()
                    )
                else:
                    console.print("[bold red]Revised planning failed.[/bold red]")
                    continue

            if answer not in ("y", "yes", ""):
                console.print("[dim]Plan rejected.[/dim]")
                continue

            # Clear planning exploration from working context, keep only system prompt
            agent.clear_working_context()
            console.print(
                "[italic dim yellow]Cleared planning context[/italic dim yellow]"
            )
            # Inject approved plan as context for execution
            agent.add_user_task(f"Execute the following plan:\n\n{plan_text}")
            user_input = plan_task  # for session title / fall-through

        elif user_input.startswith("/"):
            current_session_id, current_session_title = handle_slash_commands(
                user_input, agent, manager, current_session_id, current_session_title
            )
            continue
        else:
            agent.add_user_task(parse_file_mentions(user_input))

        if current_session_id is None:
            current_session_title = agent.generate_title(user_input)
            current_session_id = manager.create_session(
                agent.messages, current_session_title, agent.full_history
            )

        done = False
        step = 1
        max_steps = 35
        enable_status_bar()

        try:
            while not done:
                if step > max_steps:
                    disable_status_bar()
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
                        enable_status_bar()
                    else:
                        enable_status_bar()
                        # Force the agent to summarize what it did instead of just cutting off
                        start_spinner()
                        result, msg = agent.run_step(force_text=True)
                        stop_spinner()
                        disable_status_bar()
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
                            console.print(
                                f" [bold]┃[/bold] [bold]{tc['name']}[/bold]([dim]{args_str}[/dim])"
                            )
                            console.print(
                                f" [bold]┃[/bold] [{result_style}]{tc['result']}[/{result_style}]"
                            )
                            console.print(" [bold]┃[/bold]")
                        else:
                            result_style = "red" if is_error else "green"
                            console.print(f" [bold]{tc['name']}[/bold] [{result_style}]{tc['result']}[/{result_style}]")
                else:
                    sys.stdout.write("\n")
                    # console.print("\n[bold green]Agent Finished Task:[/bold green]")
                    # console.print(Panel(Markdown(result), border_style="green"))
                    done = True

                step += 1

        except KeyboardInterrupt:
            console.print("\n[bold yellow]Task cancelled.[/bold yellow]")

        finally:
            disable_status_bar()
            manager.save_session(
                current_session_id,
                current_session_title,
                agent.messages,
                agent.full_history,
            )


if __name__ == "__main__":
    main()
