import shutil
import sys
import time


class StatusBar:
    def __init__(self, agent):
        self.agent = agent
        self.active = False
        self.status = ""
        self.last_redraw = 0.0

    def enable(self):
        if self.active:
            return
        self.active = True
        self.status = ""
        size = shutil.get_terminal_size()
        # DEC save cursor, set scroll region (excludes bottom line, moves cursor
        # to home as a side-effect), DEC restore cursor to where it was.
        sys.stdout.write(f"\0337\033[1;{size.lines - 1}r\0338")
        sys.stdout.flush()
        self.draw()

    def disable(self):
        if not self.active:
            return
        self.active = False
        size = shutil.get_terminal_size()
        # DEC save cursor, clear status line, reset scroll region (moves cursor
        # to home as a side-effect), DEC restore cursor to where it was.
        sys.stdout.write(f"\0337\033[{size.lines};1H\033[K\033[r\0338")
        sys.stdout.flush()

    def set_status(self, text):
        self.status = text
        self.draw(throttle=True)

    def draw(self, throttle=False):
        if not self.active:
            return
        if throttle:
            now = time.monotonic()
            if now - self.last_redraw < 0.25:
                return
            self.last_redraw = now
        size = shutil.get_terminal_size()
        text = self._bar_text()
        bar = text.ljust(size.columns)[: size.columns]
        # Use CSI s/u (separate save slot from DEC SC/RC used by enable/disable)
        sys.stdout.write(f"\033[s\033[{size.lines};1H\033[7m{bar}\033[0m\033[u")
        sys.stdout.flush()

    def _bar_text(self):
        usage = self.agent.get_usage()
        text = f" {self.agent.model} │ {usage['total_prompt_tokens']:,} in / {usage['total_completion_tokens']:,} out"
        if self.status:
            text += f" │ {self.status}"
        return text
