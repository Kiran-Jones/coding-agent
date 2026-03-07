"""Tests for StatusBar terminal status display."""

import time
from unittest.mock import Mock, patch

from coding_agent.status_bar import StatusBar


class TestStatusBarInitialization:
    """Test StatusBar initialization."""

    def test_init_defaults(self):
        """StatusBar starts inactive with empty status."""
        agent = Mock()
        bar = StatusBar(agent)

        assert bar.active is False
        assert bar.status == ""
        assert bar.last_redraw == 0.0
        assert bar.agent is agent


class TestStatusBarEnableDisable:
    """Test enable/disable lifecycle."""

    @patch("sys.stdout")
    def test_enable_sets_active(self, mock_stdout):
        """enable() sets active=True and writes escape sequences."""
        agent = Mock()
        agent.get_usage.return_value = {
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
        }
        agent.model = "test-model"
        bar = StatusBar(agent)

        bar.enable()

        assert bar.active is True
        assert mock_stdout.write.called
        assert mock_stdout.flush.called

    @patch("sys.stdout")
    def test_enable_idempotent(self, mock_stdout):
        """Calling enable() twice does not double-initialize."""
        agent = Mock()
        agent.get_usage.return_value = {
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
        }
        agent.model = "test-model"
        bar = StatusBar(agent)

        bar.enable()
        call_count = mock_stdout.write.call_count
        bar.enable()

        assert mock_stdout.write.call_count == call_count

    @patch("sys.stdout")
    def test_disable_sets_inactive(self, mock_stdout):
        """disable() sets active=False."""
        agent = Mock()
        agent.get_usage.return_value = {
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
        }
        agent.model = "test-model"
        bar = StatusBar(agent)

        bar.enable()
        bar.disable()

        assert bar.active is False

    @patch("sys.stdout")
    def test_disable_idempotent(self, mock_stdout):
        """Calling disable() when already inactive is a no-op."""
        agent = Mock()
        bar = StatusBar(agent)

        bar.disable()

        assert bar.active is False


class TestStatusBarSetStatus:
    """Test set_status method."""

    def test_set_status_updates_text(self):
        """set_status() stores the status string."""
        agent = Mock()
        bar = StatusBar(agent)

        bar.set_status("Thinking…")

        assert bar.status == "Thinking…"

    def test_set_status_empty_string(self):
        """set_status('') clears the status."""
        agent = Mock()
        bar = StatusBar(agent)
        bar.status = "Thinking…"

        bar.set_status("")

        assert bar.status == ""


class TestStatusBarDraw:
    """Test draw method."""

    def test_draw_inactive_noop(self):
        """draw() does nothing when inactive."""
        agent = Mock()
        bar = StatusBar(agent)

        with patch("sys.stdout") as mock_stdout:
            bar.draw()

        mock_stdout.write.assert_not_called()

    @patch("sys.stdout")
    def test_draw_active_writes_output(self, mock_stdout):
        """draw() writes to stdout when active."""
        agent = Mock()
        agent.get_usage.return_value = {
            "total_prompt_tokens": 100,
            "total_completion_tokens": 50,
        }
        agent.model = "test-model"
        bar = StatusBar(agent)
        bar.active = True

        bar.draw()

        assert mock_stdout.write.called
        assert mock_stdout.flush.called

    @patch("sys.stdout")
    def test_draw_throttle_skips_rapid_calls(self, mock_stdout):
        """draw(throttle=True) skips if called within 0.25s."""
        agent = Mock()
        agent.get_usage.return_value = {
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
        }
        agent.model = "test-model"
        bar = StatusBar(agent)
        bar.active = True
        bar.last_redraw = time.monotonic()

        bar.draw(throttle=True)

        mock_stdout.write.assert_not_called()

    @patch("sys.stdout")
    def test_draw_throttle_allows_after_interval(self, mock_stdout):
        """draw(throttle=True) draws if enough time has passed."""
        agent = Mock()
        agent.get_usage.return_value = {
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
        }
        agent.model = "test-model"
        bar = StatusBar(agent)
        bar.active = True
        bar.last_redraw = time.monotonic() - 1.0

        bar.draw(throttle=True)

        assert mock_stdout.write.called


class TestStatusBarText:
    """Test _bar_text generation."""

    def test_bar_text_includes_model(self):
        """Bar text includes the model name."""
        agent = Mock()
        agent.model = "gpt-4"
        agent.get_usage.return_value = {
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
        }
        bar = StatusBar(agent)

        text = bar._bar_text()

        assert "gpt-4" in text

    def test_bar_text_includes_token_counts(self):
        """Bar text includes formatted token counts."""
        agent = Mock()
        agent.model = "test"
        agent.get_usage.return_value = {
            "total_prompt_tokens": 1234,
            "total_completion_tokens": 567,
        }
        bar = StatusBar(agent)

        text = bar._bar_text()

        assert "1,234 in" in text
        assert "567 out" in text

    def test_bar_text_includes_status(self):
        """Bar text includes status when set."""
        agent = Mock()
        agent.model = "test"
        agent.get_usage.return_value = {
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
        }
        bar = StatusBar(agent)
        bar.status = "Thinking…"

        text = bar._bar_text()

        assert "Thinking…" in text

    def test_bar_text_omits_status_when_empty(self):
        """Bar text has no trailing separator when status is empty."""
        agent = Mock()
        agent.model = "test"
        agent.get_usage.return_value = {
            "total_prompt_tokens": 0,
            "total_completion_tokens": 0,
        }
        bar = StatusBar(agent)
        bar.status = ""

        text = bar._bar_text()

        # Should end with token info, no trailing "│"
        assert text.rstrip().endswith("out")
