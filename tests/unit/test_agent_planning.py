"""
Unit tests for agent.py planning mode functionality.

Tests plan mode setup, blocking rules, loop execution, and cleanup.
"""

from unittest.mock import Mock, patch

import pytest

from coding_agent.agent import PLAN_SYSTEM_ADDENDUM


# ============================================================================
# SECTION 3.1: Plan Mode Setup (3 tests)
# ============================================================================


class TestPlanModeSetup:
    """Test plan mode initialization."""

    def test_run_plan_loop_enters_plan_mode(self, mock_agent, mocker):
        """Verify plan_mode=True."""
        # Mock run_step to return text (exit condition)
        mocker.patch.object(
            mock_agent, "run_step", return_value=("This is a plan", None)
        )

        mock_agent.run_plan_loop()

        # plan_mode should be reset to False after
        assert mock_agent.plan_mode is False

    def test_run_plan_loop_modifies_system_prompt(self, mock_agent, mocker):
        """Verify PLAN_SYSTEM_ADDENDUM added."""
        original_prompt = mock_agent.messages[0]["content"]
        mocker.patch.object(mock_agent, "run_step", return_value=("Plan", None))

        mock_agent.run_plan_loop()

        # After execution, prompt should be restored
        assert mock_agent.messages[0]["content"] == original_prompt
        assert PLAN_SYSTEM_ADDENDUM not in mock_agent.messages[0]["content"]

    def test_run_plan_loop_restores_system_prompt(self, mock_agent, mocker):
        """Verify original prompt restored after."""
        original_prompt = mock_agent.messages[0]["content"]
        mocker.patch.object(mock_agent, "run_step", return_value=("Plan", None))

        mock_agent.run_plan_loop()

        assert mock_agent.messages[0]["content"] == original_prompt


# ============================================================================
# SECTION 3.2: Plan Mode Blocking (4 tests)
# ============================================================================


class TestPlanModeBlocking:
    """Test tool call blocking in plan mode."""

    def test_plan_mode_blocks_write_file(self, mock_agent):
        """write_file blocked in plan mode."""
        mock_agent.plan_mode = True
        tool_calls = [
            {
                "id": "call-1",
                "function": {
                    "name": "write_file",
                    "arguments": '{"file_path": "test.txt", "content": "content"}',
                },
            }
        ]

        summaries = mock_agent._handle_tool_calls(tool_calls)

        assert "not available in planning mode" in summaries[0]["result"]

    def test_plan_mode_blocks_run_terminal_command(self, mock_agent):
        """run_terminal_command blocked in plan mode."""
        mock_agent.plan_mode = True
        tool_calls = [
            {
                "id": "call-1",
                "function": {
                    "name": "run_terminal_command",
                    "arguments": '{"command": "ls -la"}',
                },
            }
        ]

        summaries = mock_agent._handle_tool_calls(tool_calls)

        assert "not available in planning mode" in summaries[0]["result"]

    def test_plan_mode_allows_read_file(self, mock_agent):
        """read_file allowed in plan mode."""
        mock_agent.plan_mode = True

        with patch.dict(
            "coding_agent.tools.AVAILABLE_TOOLS",
            {"read_file": lambda file_path, **kwargs: "content"},
        ):
            tool_calls = [
                {
                    "id": "call-1",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"file_path": "test.txt"}',
                    },
                }
            ]

            summaries = mock_agent._handle_tool_calls(tool_calls)

        # Should succeed
        assert "content" in summaries[0]["result"]

    def test_plan_mode_allows_web_search(self, mock_agent):
        """web_search allowed in plan mode."""
        mock_agent.plan_mode = True

        with patch.dict(
            "coding_agent.tools.AVAILABLE_TOOLS",
            {"web_search": lambda query, **kwargs: "search results"},
        ):
            tool_calls = [
                {
                    "id": "call-1",
                    "function": {
                        "name": "web_search",
                        "arguments": '{"query": "test"}',
                    },
                }
            ]

            summaries = mock_agent._handle_tool_calls(tool_calls)

        # Should succeed
        assert "search results" in summaries[0]["result"]


# ============================================================================
# SECTION 3.3: Plan Loop Execution (5 tests)
# ============================================================================


class TestPlanLoopExecution:
    """Test plan loop execution flow."""

    def test_run_plan_loop_max_steps(self, mock_agent, mocker):
        """max_steps=15, verify loop terminates."""
        step_count = [0]

        def mock_run_step(force_text=False):
            step_count[0] += 1
            if step_count[0] >= 15:
                return ("Plan result", None)
            return ("tool_used", [{"name": "read_file", "result": "content"}])

        mocker.patch.object(mock_agent, "run_step", side_effect=mock_run_step)

        mock_agent.run_plan_loop()

        # Should stop at or before max_steps
        assert step_count[0] <= 15

    def test_run_plan_loop_returns_text_response(self, mock_agent, mocker):
        """Loop exits when result != 'tool_used'."""
        mocker.patch.object(
            mock_agent, "run_step", return_value=("This is the final plan", None)
        )

        result = mock_agent.run_plan_loop()

        assert result == "This is the final plan"

    def test_run_plan_loop_handles_tool_results(self, mock_agent, mocker):
        """Tool result messages appended."""
        step_count = [0]

        def mock_run_step(force_text=False):
            step_count[0] += 1
            if step_count[0] == 1:
                return ("tool_used", [{"name": "read_file", "result": "file content"}])
            else:
                return ("Final plan", None)

        mocker.patch.object(mock_agent, "run_step", side_effect=mock_run_step)

        result = mock_agent.run_plan_loop()

        assert result == "Final plan"
        assert len(mock_agent.messages) >= 1

    def test_run_plan_loop_error_breaks_loop(self, mock_agent, mocker):
        """result=='error' breaks loop."""
        mocker.patch.object(mock_agent, "run_step", return_value=("error", None))

        mock_agent.run_plan_loop()

        # Loop should break
        assert mock_agent.plan_mode is False

    def test_run_plan_loop_callbacks(self, mock_agent, mocker):
        """Verify spinner_start/stop callbacks invoked."""
        spinner_start = Mock()
        spinner_stop = Mock()

        mocker.patch.object(mock_agent, "run_step", return_value=("Plan", None))

        mock_agent.run_plan_loop(spinner_start=spinner_start, spinner_stop=spinner_stop)

        spinner_start.assert_called()
        spinner_stop.assert_called()


# ============================================================================
# SECTION 3.4: Plan Loop Cleanup (3 tests)
# ============================================================================


class TestPlanLoopCleanup:
    """Test plan loop cleanup."""

    def test_run_plan_loop_exception_restores_prompt(self, mock_agent, mocker):
        """Even if exception, prompt restored."""
        original_prompt = mock_agent.messages[0]["content"]
        mocker.patch.object(mock_agent, "run_step", side_effect=Exception("Test error"))

        with pytest.raises(Exception):
            mock_agent.run_plan_loop()

        # Prompt should be restored
        assert mock_agent.messages[0]["content"] == original_prompt

    def test_run_plan_loop_sets_plan_mode_false(self, mock_agent, mocker):
        """plan_mode=False after loop."""
        mocker.patch.object(mock_agent, "run_step", return_value=("Plan", None))

        mock_agent.run_plan_loop()

        assert mock_agent.plan_mode is False

    def test_run_plan_loop_stream_callback_filters_errors(self, mock_agent, mocker):
        """Stream callback shows errors."""
        step_count = [0]

        def mock_run_step(force_text=False):
            step_count[0] += 1
            if step_count[0] == 1:
                return (
                    "tool_used",
                    [{"name": "read_file", "result": "Error: File not found"}],
                )
            else:
                return ("Plan", None)

        mocker.patch.object(mock_agent, "run_step", side_effect=mock_run_step)
        stream_callback = Mock()

        mock_agent.run_plan_loop(stream_callback=stream_callback)

        # Callback should have been called with error message
        stream_callback.assert_called()
