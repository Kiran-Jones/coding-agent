"""Tests for LiveMarkdownRenderer and render_markdown_with_syntax."""

from unittest.mock import Mock, patch

from rich.console import Group
from rich.markdown import Markdown
from rich.syntax import Syntax
from coding_agent.markdown_renderer import (
    LiveMarkdownRenderer,
    render_markdown_with_syntax,
)


class TestRenderMarkdownWithSyntax:
    """Test the render_markdown_with_syntax function."""

    def test_plain_text_returns_markdown(self):
        """Plain text without code blocks renders as Markdown."""
        result = render_markdown_with_syntax("Hello world")

        assert isinstance(result, Group)
        assert len(result.renderables) == 1
        assert isinstance(result.renderables[0], Markdown)

    def test_code_block_renders_as_syntax(self):
        """Fenced code block renders as Syntax."""
        content = '```python\nprint("hello")\n```'
        result = render_markdown_with_syntax(content)

        assert isinstance(result, Group)
        has_syntax = any(isinstance(r, Syntax) for r in result.renderables)
        assert has_syntax

    def test_code_block_without_language(self):
        """Code block without language tag defaults to text."""
        content = "```\nsome code\n```"
        result = render_markdown_with_syntax(content)

        assert isinstance(result, Group)
        has_syntax = any(isinstance(r, Syntax) for r in result.renderables)
        assert has_syntax

    def test_mixed_content(self):
        """Markdown text before and after code block both render."""
        content = "Here is code:\n\n```python\nx = 1\n```\n\nDone."
        result = render_markdown_with_syntax(content)

        assert isinstance(result, Group)
        assert len(result.renderables) >= 2

    def test_multiple_code_blocks(self):
        """Multiple code blocks each get their own Syntax element."""
        content = "```python\nx = 1\n```\n\n```javascript\nlet y = 2\n```"
        result = render_markdown_with_syntax(content)

        syntax_count = sum(1 for r in result.renderables if isinstance(r, Syntax))
        assert syntax_count == 2

    def test_empty_string(self):
        """Empty string still returns a Group with Markdown."""
        result = render_markdown_with_syntax("")

        assert isinstance(result, Group)
        assert len(result.renderables) == 1


class TestLiveMarkdownRendererLifecycle:
    """Test LiveMarkdownRenderer start/stop/update."""

    def test_init_state(self):
        """Renderer starts with empty buffer and no live instance."""
        console = Mock()
        renderer = LiveMarkdownRenderer(console)

        assert renderer.buffer == []
        assert renderer.live is None
        assert renderer.console is console

    @patch("coding_agent.markdown_renderer.Live")
    def test_start_creates_live(self, mock_live_cls):
        """start() creates and starts a Live instance."""
        console = Mock()
        renderer = LiveMarkdownRenderer(console)

        renderer.start()

        mock_live_cls.assert_called_once()
        mock_live_cls.return_value.start.assert_called_once()
        assert renderer.buffer == []

    @patch("coding_agent.markdown_renderer.Live")
    def test_start_clears_buffer(self, mock_live_cls):
        """start() resets the buffer."""
        console = Mock()
        renderer = LiveMarkdownRenderer(console)
        renderer.buffer = ["old", "data"]

        renderer.start()

        assert renderer.buffer == []

    @patch("coding_agent.markdown_renderer.Live")
    def test_update_appends_chunk(self, mock_live_cls):
        """update() adds chunk to buffer and updates live display."""
        console = Mock()
        renderer = LiveMarkdownRenderer(console)
        renderer.start()

        renderer.update("Hello")
        renderer.update(" world")

        assert renderer.buffer == ["Hello", " world"]
        assert mock_live_cls.return_value.update.call_count == 2

    @patch("coding_agent.markdown_renderer.Live")
    def test_update_empty_chunk_ignored(self, mock_live_cls):
        """update('') does not append to buffer."""
        console = Mock()
        renderer = LiveMarkdownRenderer(console)
        renderer.start()

        renderer.update("")

        assert renderer.buffer == []
        mock_live_cls.return_value.update.assert_not_called()

    @patch("coding_agent.markdown_renderer.Live")
    def test_update_none_chunk_ignored(self, mock_live_cls):
        """update(None) does not append to buffer."""
        console = Mock()
        renderer = LiveMarkdownRenderer(console)
        renderer.start()

        renderer.update(None)

        assert renderer.buffer == []

    @patch("coding_agent.markdown_renderer.Live")
    def test_stop_returns_content(self, mock_live_cls):
        """stop() returns accumulated content."""
        console = Mock()
        renderer = LiveMarkdownRenderer(console)
        renderer.start()
        renderer.update("Hello")
        renderer.update(" world")

        result = renderer.stop()

        assert result == "Hello world"
        mock_live_cls.return_value.stop.assert_called_once()
        assert renderer.live is None

    def test_stop_without_start(self):
        """stop() when not started returns empty string."""
        console = Mock()
        renderer = LiveMarkdownRenderer(console)

        result = renderer.stop()

        assert result == ""

    @patch("coding_agent.markdown_renderer.Live")
    def test_get_content(self, mock_live_cls):
        """get_content() returns buffer joined as string."""
        console = Mock()
        renderer = LiveMarkdownRenderer(console)
        renderer.start()
        renderer.update("abc")
        renderer.update("def")

        assert renderer.get_content() == "abcdef"
