"""Tests for AgentUI callbacks and rendering coordination."""

from unittest.mock import Mock, patch

from coding_agent.agent_ui import AgentUI


def make_ui():
    """Create an AgentUI with mocked dependencies."""
    console = Mock()
    agent = Mock()
    status_bar = Mock()
    status_bar.status = ""
    ui = AgentUI(console, agent, status_bar)
    return ui, console, status_bar


class TestAgentUIInitialization:
    """Test AgentUI initialization."""

    def test_init_state(self):
        """AgentUI starts with renderer inactive."""
        ui, console, status_bar = make_ui()

        assert ui.console is console
        assert ui.status_bar is status_bar
        assert ui.renderer_active is False
        assert ui.live_renderer is not None


class TestStreamChunk:
    """Test stream_chunk callback."""

    def test_first_chunk_starts_renderer(self):
        """First chunk while 'Thinking…' starts the live renderer."""
        ui, _, status_bar = make_ui()
        status_bar.status = "Thinking…"
        ui.live_renderer = Mock()

        ui.stream_chunk("Hello")

        status_bar.set_status.assert_called_with("")
        status_bar.disable.assert_called_once()
        ui.live_renderer.start.assert_called_once()
        ui.live_renderer.update.assert_called_with("Hello")
        assert ui.renderer_active is True

    def test_subsequent_chunks_update_renderer(self):
        """After renderer is active, chunks go to update()."""
        ui, _, status_bar = make_ui()
        ui.renderer_active = True
        ui.live_renderer = Mock()

        ui.stream_chunk("world")

        ui.live_renderer.update.assert_called_with("world")
        status_bar.disable.assert_not_called()

    def test_fallback_to_stdout_when_renderer_inactive(self):
        """Without active renderer, chunks write to stdout."""
        ui, _, status_bar = make_ui()
        status_bar.status = ""
        ui.renderer_active = False

        with patch("sys.stdout") as mock_stdout:
            ui.stream_chunk("test")

        mock_stdout.write.assert_called_with("test")
        mock_stdout.flush.assert_called()
        status_bar.draw.assert_called_with(throttle=True)


class TestStopThinking:
    """Test stop_thinking method."""

    def test_stop_thinking_stops_renderer(self):
        """stop_thinking() stops live renderer if active."""
        ui, _, status_bar = make_ui()
        ui.renderer_active = True
        ui.live_renderer = Mock()

        ui.stop_thinking()

        ui.live_renderer.stop.assert_called_once()
        assert ui.renderer_active is False
        status_bar.set_status.assert_called_with("")

    def test_stop_thinking_clears_status(self):
        """stop_thinking() clears status bar even if renderer inactive."""
        ui, _, status_bar = make_ui()
        ui.renderer_active = False

        ui.stop_thinking()

        status_bar.set_status.assert_called_with("")


class TestStartThinking:
    """Test start_thinking method."""

    def test_start_thinking_sets_status(self):
        """start_thinking() sets status to 'Thinking…'."""
        ui, _, status_bar = make_ui()

        ui.start_thinking()

        status_bar.set_status.assert_called_with("Thinking…")


class TestApproveTool:
    """Test approve_tool method."""

    def test_approve_tool_stops_renderer(self):
        """approve_tool() stops live renderer before prompting."""
        ui, console, status_bar = make_ui()
        ui.renderer_active = True
        ui.live_renderer = Mock()

        with patch("coding_agent.agent_ui.PromptSession") as mock_ps:
            mock_ps.return_value.prompt.return_value = "y"
            ui.approve_tool("write_file", {"file_path": "test.txt"})

        ui.live_renderer.stop.assert_called_once()
        assert ui.renderer_active is False

    def test_approve_tool_yes(self):
        """'y' returns True."""
        ui, _, _ = make_ui()

        with patch("coding_agent.agent_ui.PromptSession") as mock_ps:
            mock_ps.return_value.prompt.return_value = "y"
            result = ui.approve_tool("write_file", {"file_path": "test.txt"})

        assert result is True

    def test_approve_tool_empty_string_approves(self):
        """Empty string (just Enter) returns True."""
        ui, _, _ = make_ui()

        with patch("coding_agent.agent_ui.PromptSession") as mock_ps:
            mock_ps.return_value.prompt.return_value = ""
            result = ui.approve_tool("write_file", {})

        assert result is True

    def test_approve_tool_no(self):
        """'n' returns False."""
        ui, _, _ = make_ui()

        with patch("coding_agent.agent_ui.PromptSession") as mock_ps:
            mock_ps.return_value.prompt.return_value = "n"
            result = ui.approve_tool("write_file", {})

        assert result is False

    def test_approve_tool_keyboard_interrupt(self):
        """KeyboardInterrupt returns False."""
        ui, _, _ = make_ui()

        with patch("coding_agent.agent_ui.PromptSession") as mock_ps:
            mock_ps.return_value.prompt.side_effect = KeyboardInterrupt
            result = ui.approve_tool("write_file", {})

        assert result is False

    def test_approve_tool_eof(self):
        """EOFError returns False."""
        ui, _, _ = make_ui()

        with patch("coding_agent.agent_ui.PromptSession") as mock_ps:
            mock_ps.return_value.prompt.side_effect = EOFError
            result = ui.approve_tool("write_file", {})

        assert result is False

    def test_approve_tool_prints_summary(self):
        """approve_tool() prints the function name and args."""
        ui, console, _ = make_ui()

        with patch("coding_agent.agent_ui.PromptSession") as mock_ps:
            mock_ps.return_value.prompt.return_value = "y"
            ui.approve_tool("run_terminal_command", {"command": "ls"})

        printed = console.print.call_args[0][0]
        assert "run_terminal_command" in printed
        assert "command=ls" in printed
