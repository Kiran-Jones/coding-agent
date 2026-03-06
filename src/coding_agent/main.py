# main.py

import os
import sys

from dotenv import load_dotenv
from prompt_toolkit import PromptSession
from prompt_toolkit.key_binding import KeyBindings
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
    
    elif cmd == "/quit" or cmd == "/exit":
        if session_id:
            manager.save_session(session_id, session_title, agent.full_history)
        console.print("[bold red]Exiting...[/bold red]")
        sys.exit(0)
    else:
        console.print(
            Panel.fit(
                "[bold cyan]/sessions[/] - List all saved sessions\n"
                "[bold cyan]/load <session_name>[/] - Load a saved session\n"
                "[bold cyan]/quit[/] - Exit the program\n"
                "[bold cyan]/help[/] - Show this help message",
                title="Available Commands",
                border_style="cyan",
            )
        )
    
    return session_id, session_title


def create_prompt_session() -> PromptSession:
    """Create a prompt_toolkit session where Enter submits and Ctrl+J inserts a newline."""
    kb = KeyBindings()
    
    @kb.add("enter")
    def handle_enter(event):
        event.current_buffer.validate_and_handle()
    
    @kb.add("c-j")
    def handle_newline(event):
        event.current_buffer.insert_text("\n")
    
    return PromptSession(key_bindings=kb, multiline=True)


def main():
    
    def print_agent_notification(message: str):
        console.print(message)
    
    agent = CodingAgent(
        api_key=API_KEY,
        endpoint_url=ENDPOINT_URL,
        ui_callback=print_agent_notification,
    )
    manager = SessionManager()
    session = create_prompt_session()
    
    current_session_id = None
    current_session_title = "New Chat"
    
    console.print("[bold cyan]Welcome to the AI Coding Agent![/bold cyan]")
    console.print("[dim]Enter to submit. Ctrl+J for newline.[/dim]")
    
    while True:
        try:
            user_input = session.prompt("\nYou: ").strip()
        except (KeyboardInterrupt, EOFError):
            if current_session_id:
                manager.save_session(
                    current_session_id, current_session_title, agent.full_history
                )
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
        
        while not done:
            if step > max_steps:
                console.print(
                    f"\n[bold yellow]Agent reached the maximum of {max_steps} steps.[/bold yellow]"
                )
                keep_going = (
                    session.prompt(
                        "Do you want to give it 10 more steps to finish? (y/n): "
                    )
                    .strip()
                    .lower()
                )
                
                if keep_going == "y":
                    max_steps += 10
                else:
                    # Force the agent to summarize what it did instead of just cutting off
                    result = agent.run_step(force_text=True)
                    if result not in ("tool_used", "error"):
                        console.print("\n[bold green]Agent Summary:[/bold green]")
                        console.print(Panel(Markdown(result), border_style="green"))
                    break
            
            # On the last allowed step, force a text response so the agent wraps up
            force_text = step == max_steps
            result = agent.run_step(force_text=force_text)
            
            if result == "error":
                break
            elif result == "tool_used":
                console.print(
                    "[italic dim yellow]Agent used a tool. Looping to let it read the results...[/italic dim yellow]"
                )
            else:
                console.print("\n[bold green]Agent Finished Task:[/bold green]")
                console.print(Panel(Markdown(result), border_style="green"))
                done = True
            
            step += 1
        
        manager.save_session(
            current_session_id, current_session_title, agent.full_history
        )

if __name__ == "__main__":
    main()