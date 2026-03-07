"""Custom Markdown renderer with syntax-highlighted code blocks using rich.syntax."""

import re
from rich.console import Console, Group
from rich.live import Live
from rich.markdown import Markdown
from rich.syntax import Syntax
from rich.text import Text


class LiveMarkdownRenderer:
    """Manages live rendering of markdown with syntax highlighting during streaming."""

    def __init__(self, console: Console):
        self.console = console
        self.buffer = []
        self.live = None

    def start(self):
        """Start live rendering."""
        self.buffer = []
        self.live = Live(
            "",
            console=self.console,
            auto_refresh=True,
            refresh_per_second=10,
            transient=False,  # Keep content after stopping
        )
        self.live.start()

    def update(self, chunk: str):
        """Add a chunk and update the live display."""
        if chunk:
            self.buffer.append(chunk)
            content = "".join(self.buffer)
            rendered = render_markdown_with_syntax(content)
            if self.live:
                self.live.update(rendered)

    def stop(self):
        """Stop live rendering and return final content."""
        if self.live:
            self.live.stop()
            self.live = None
        return "".join(self.buffer)

    def get_content(self) -> str:
        """Get the accumulated content."""
        return "".join(self.buffer)


def render_markdown_with_syntax(content: str) -> Group:
    """
    Render markdown content with syntax-highlighted code blocks.

    This function parses markdown to extract code blocks and renders them
    using rich.syntax.Syntax for proper syntax highlighting, while rendering
    other content using rich.markdown.Markdown.

    Args:
        content: The markdown content to render

    Returns:
        A Rich Group containing all rendered elements
    """
    # Pattern to match code blocks: ```language\ncode\n```
    code_block_pattern = re.compile(
        r'```(\w+)?\n(.*?)```',
        re.DOTALL
    )

    elements = []
    last_end = 0

    for match in code_block_pattern.finditer(content):
        # Add any markdown content before this code block
        if match.start() > last_end:
            markdown_text = content[last_end:match.start()].strip()
            if markdown_text:
                elements.append(Markdown(markdown_text))

        # Extract language and code
        language = match.group(1) or "text"
        code = match.group(2).rstrip('\n')

        # Create syntax-highlighted code block
        try:
            syntax = Syntax(
                code,
                language,
                theme="monokai",
                line_numbers=True,
                word_wrap=False,
                background_color="default"
            )
            elements.append(syntax)
        except Exception:
            # Fallback to plain text if syntax highlighting fails
            elements.append(Text(code, style="dim"))

        last_end = match.end()

    # Add any remaining markdown content after the last code block
    if last_end < len(content):
        markdown_text = content[last_end:].strip()
        if markdown_text:
            elements.append(Markdown(markdown_text))

    # If no code blocks were found, just return the whole thing as markdown
    if not elements:
        elements.append(Markdown(content))

    return Group(*elements)
