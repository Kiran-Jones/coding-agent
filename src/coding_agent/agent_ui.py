import sys

from prompt_toolkit import PromptSession

from .markdown_renderer import LiveMarkdownRenderer


class AgentUI:
    def __init__(self, console, agent, status_bar):
        self.console = console
        self.live_renderer = LiveMarkdownRenderer(console)
        self.status_bar = status_bar
        self.renderer_active = False

    def stream_chunk(self, chunk):
        if self.status_bar.status == "Thinking…":
            self.status_bar.set_status("")
            # Disable status bar and start live renderer
            self.status_bar.disable()
            self.live_renderer.start()
            self.renderer_active = True

        if self.renderer_active:
            self.live_renderer.update(chunk)
        else:
            # Fallback to plain streaming if renderer not active
            sys.stdout.write(chunk)
            sys.stdout.flush()
            self.status_bar.draw(throttle=True)

    def approve_tool(self, func_name, args):
        # Stop live renderer if active before showing approval prompt
        if self.renderer_active:
            self.live_renderer.stop()
            self.renderer_active = False
        self.status_bar.set_status("")

        arg_summary = ", ".join(f"{k}={str(v)[:80]}" for k, v in args.items())
        self.console.print(f"\n [bold yellow]{func_name}[/bold yellow]({arg_summary})")
        try:
            answer = PromptSession().prompt("   Allow? (y/n) > ").strip().lower()
            return answer in ("y", "yes", "")
        except (KeyboardInterrupt, EOFError):
            return False

    def start_thinking(self):
        self.status_bar.set_status("Thinking…")

    def stop_thinking(self):
        if self.renderer_active:
            self.live_renderer.stop()
            self.renderer_active = False
        self.status_bar.set_status("")
