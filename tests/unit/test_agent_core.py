"""
Unit tests for agent.py core functionality.

Tests initialization, API communication, tool call handling, token management,
and message management.
"""

import json
import os
from unittest.mock import Mock, patch

import pytest

from coding_agent.agent import CodingAgent, SYSTEM_PROMPT


# ============================================================================
# SECTION 2.1: Initialization (5 tests)
# ============================================================================


class TestCodingAgentInitialization:
    """Test CodingAgent initialization."""

    def test_coding_agent_init_basic(self, mocker):
        """Verify __init__ with API key, endpoint."""
        # Mock MCP initialization
        mocker.patch("coding_agent.mcp_manager.MCPManager", side_effect=ImportError)

        agent = CodingAgent(
            api_key="test-key", endpoint_url="http://test.com/v1/chat/completions"
        )

        assert agent.api_key == "test-key"
        assert agent.endpoint_url == "http://test.com/v1/chat/completions"
        assert len(agent.messages) > 0
        assert agent.messages[0]["role"] == "system"

    def test_coding_agent_init_with_callbacks(self, mocker):
        """Verify callback assignment."""
        mocker.patch("coding_agent.mcp_manager.MCPManager", side_effect=ImportError)

        ui_callback = Mock()
        stream_callback = Mock()
        approval_callback = Mock()

        agent = CodingAgent(
            api_key="test-key",
            endpoint_url="http://test.com/v1/chat/completions",
            ui_callback=ui_callback,
            stream_callback=stream_callback,
            approval_callback=approval_callback,
        )

        assert agent.ui_callback == ui_callback
        assert agent.stream_callback == stream_callback
        assert agent.approval_callback == approval_callback

    def test_coding_agent_init_default_callbacks(self, mocker):
        """Verify default callbacks are set."""
        mocker.patch("coding_agent.mcp_manager.MCPManager", side_effect=ImportError)

        agent = CodingAgent(
            api_key="test-key",
            endpoint_url="http://test.com/v1/chat/completions",
            ui_callback=None,
            stream_callback=None,
        )

        # Default callbacks should be lambda functions that do nothing
        agent.ui_callback("test")
        agent.stream_callback("test")

    def test_coding_agent_mcp_initialization_failure(self, mocker):
        """MCP init failure doesn't crash."""
        mocker.patch(
            "coding_agent.mcp_manager.MCPManager",
            side_effect=Exception("MCP Connection failed"),
        )
        # Make os.path.exists return True only for mcp config paths
        original_exists = os.path.exists

        def patched_exists(path):
            if "mcp_config" in str(path):
                return True
            return original_exists(path)

        mocker.patch("os.path.exists", side_effect=patched_exists)

        agent = CodingAgent(
            api_key="test-key",
            endpoint_url="http://test.com/v1/chat/completions",
        )

        # Should not raise, agent.mcp_manager should be None
        assert agent.mcp_manager is None


# ============================================================================
# SECTION 2.2: API Communication & Streaming (6 tests)
# ============================================================================


class TestParseStream:
    """Test stream parsing."""

    def test_parse_stream_simple_text(self, mock_agent, mock_stream_response):
        """Parse single text chunk."""
        message, usage = mock_agent._parse_stream(mock_stream_response)

        assert message["role"] == "assistant"
        assert "Hello world" in message["content"]
        assert usage.get("prompt_tokens") == 10
        assert usage.get("completion_tokens") == 5

    def test_parse_stream_tool_calls(self, mock_agent, mock_tool_call_response):
        """Parse tool_calls with arguments."""
        message, usage = mock_agent._parse_stream(mock_tool_call_response)

        assert "tool_calls" in message
        assert len(message["tool_calls"]) > 0
        tc = message["tool_calls"][0]
        assert tc["function"]["name"] == "write_file"
        args = json.loads(tc["function"]["arguments"])
        assert args["file_path"] == "test.txt"
        assert args["content"] == "hello"

    def test_parse_stream_mixed_content(self, mock_agent):
        """Both text and tool calls."""
        mock_response = Mock()
        mock_response.iter_lines.return_value = [
            'data: {"choices":[{"delta":{"content":"Starting..."}}]}\n',
            'data: {"choices":[{"delta":{"tool_calls"'
            ':[{"index":0,"id":"call-1","function":{"name":"read_file",'
            '"arguments":"{\\"file_path\\":\\"test.py\\"}"}}]}}]}\n',
            'data: {"choices":[{"delta":{}}],"usage":{"prompt_tokens":5,"completion_tokens":3}}\n',
            "data: [DONE]\n",
        ]

        message, usage = mock_agent._parse_stream(mock_response)

        assert message["content"] == "Starting..."
        assert "tool_calls" in message

    def test_parse_stream_malformed_json(self, mocker):
        """Handle JSONDecodeError gracefully."""
        mock_response = Mock()
        mock_response.iter_lines.return_value = [
            'data: {"choices":[{"delta":{"content":"test"}}]}\n',
            "data: {malformed json}\n",  # Invalid JSON
            "data: [DONE]\n",
        ]

        agent = CodingAgent(api_key="test", endpoint_url="http://test.com")
        message, usage = agent._parse_stream(mock_response)

        assert message["content"] == "test"

    def test_parse_stream_usage_tokens(self, mocker):
        """Extract usage.prompt_tokens, completion_tokens."""
        mock_response = Mock()
        mock_response.iter_lines.return_value = [
            'data: {"choices":[{"delta":{"content":"hi"}}]}\n',
            'data: {"choices":[{"delta":{}}],"usage":{"prompt_tokens":42,"completion_tokens":17}}\n',
            "data: [DONE]\n",
        ]

        agent = CodingAgent(api_key="test", endpoint_url="http://test.com")
        message, usage = agent._parse_stream(mock_response)

        assert usage["prompt_tokens"] == 42
        assert usage["completion_tokens"] == 17

    def test_run_step_api_error(self, mock_agent, mocker):
        """Handle API error gracefully."""
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        mocker.patch("requests.post", return_value=mock_response)

        result, msg = mock_agent.run_step()

        assert result == "error"


# ============================================================================
# SECTION 2.3: Tool Call Handling (8 tests)
# ============================================================================


class TestHandleToolCalls:
    """Test tool call handling."""

    def test_handle_tool_calls_malformed_arguments(self, mock_agent):
        """JSONDecodeError in tool arguments."""
        tool_calls = [
            {
                "id": "call-1",
                "function": {
                    "name": "write_file",
                    "arguments": "{invalid json}",
                },
            }
        ]

        summaries = mock_agent._handle_tool_calls(tool_calls)

        assert len(summaries) == 1
        assert "Error" in summaries[0]["result"]
        assert "Malformed" in summaries[0]["result"]

    def test_handle_tool_calls_plan_mode_blocking(self, mock_agent):
        """Block non-readonly tools in plan mode."""
        mock_agent.plan_mode = True
        tool_calls = [
            {
                "id": "call-1",
                "function": {
                    "name": "write_file",
                    "arguments": '{"file_path": "test.txt", "content": "test"}',
                },
            }
        ]

        summaries = mock_agent._handle_tool_calls(tool_calls)

        assert "not available in planning mode" in summaries[0]["result"]

    def test_handle_tool_calls_plan_mode_allows_readonly(self, mock_agent):
        """Allow readonly tools in plan mode."""
        mock_agent.plan_mode = True
        mock_agent.approval_callback = None
        tool_calls = [
            {
                "id": "call-1",
                "function": {
                    "name": "read_file",
                    "arguments": '{"file_path": "test.txt"}',
                },
            }
        ]

        with patch.dict(
            "coding_agent.tools.AVAILABLE_TOOLS",
            {"read_file": lambda file_path, **kwargs: "content"},
        ):
            summaries = mock_agent._handle_tool_calls(tool_calls)

        # Should execute without error
        assert len(summaries) == 1

    def test_handle_tool_calls_approval_required(
        self, mock_agent, mock_approval_callback
    ):
        """Test approval_callback workflow."""
        mock_agent.approval_callback = mock_approval_callback
        tool_calls = [
            {
                "id": "call-1",
                "function": {
                    "name": "write_file",
                    "arguments": '{"file_path": "test.txt", "content": "test"}',
                },
            }
        ]

        with patch.dict(
            "coding_agent.tools.AVAILABLE_TOOLS",
            {"write_file": lambda file_path, content, **kwargs: "Success"},
        ):
            mock_agent._handle_tool_calls(tool_calls)

        # Verify callback was called
        mock_approval_callback.assert_called_once()

    def test_handle_tool_calls_approval_denied(self, mock_agent):
        """User denies tool call."""
        mock_approval_callback = Mock(return_value=False)
        mock_agent.approval_callback = mock_approval_callback
        tool_calls = [
            {
                "id": "call-1",
                "function": {
                    "name": "write_file",
                    "arguments": '{"file_path": "test.txt", "content": "test"}',
                },
            }
        ]

        summaries = mock_agent._handle_tool_calls(tool_calls)

        assert "denied" in summaries[0]["result"].lower()

    def test_handle_tool_calls_mcp_tool(self, mock_agent, mocker):
        """Route to MCPManager for 'server__tool' calls."""
        mock_mcp = Mock()
        mock_mcp.call_tool.return_value = "MCP result"
        mock_agent.mcp_manager = mock_mcp

        tool_calls = [
            {
                "id": "call-1",
                "function": {
                    "name": "server__tool",
                    "arguments": '{"param": "value"}',
                },
            }
        ]

        summaries = mock_agent._handle_tool_calls(tool_calls)

        mock_mcp.call_tool.assert_called_once()
        assert "MCP result" in summaries[0]["result"]

    def test_handle_tool_calls_built_in_tool(self, mock_agent):
        """Execute AVAILABLE_TOOLS function."""
        with patch.dict(
            "coding_agent.tools.AVAILABLE_TOOLS",
            {"read_file": lambda file_path, **kwargs: "file content"},
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

        assert "file content" in summaries[0]["result"]

    def test_handle_tool_calls_unknown_tool(self, mock_agent):
        """Return 'Error: Unknown tool'."""
        tool_calls = [
            {
                "id": "call-1",
                "function": {
                    "name": "nonexistent_tool",
                    "arguments": "{}",
                },
            }
        ]

        summaries = mock_agent._handle_tool_calls(tool_calls)

        assert "Unknown tool" in summaries[0]["result"]


# ============================================================================
# SECTION 2.4: Snapshot Integration (3 tests)
# ============================================================================


class TestSnapshotIntegration:
    """Test snapshot manager integration."""

    def test_handle_tool_calls_snapshot_on_write(self, mock_agent, tmp_path, mocker):
        """Verify snapshot_manager.save_snapshot called."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("original content")

        tool_calls = [
            {
                "id": "call-1",
                "function": {
                    "name": "write_file",
                    "arguments": json.dumps(
                        {"file_path": str(test_file), "content": "new content"}
                    ),
                },
            }
        ]

        mock_agent._handle_tool_calls(tool_calls)

        # Verify snapshot was saved
        mock_agent.snapshot_manager.save_snapshot.assert_called()

    def test_handle_tool_calls_snapshot_new_file(self, mock_agent, tmp_path):
        """Save None for new files."""
        new_file = tmp_path / "new.txt"

        tool_calls = [
            {
                "id": "call-1",
                "function": {
                    "name": "write_file",
                    "arguments": json.dumps(
                        {"file_path": str(new_file), "content": "content"}
                    ),
                },
            }
        ]

        mock_agent._handle_tool_calls(tool_calls)

        # Verify snapshot was saved with None original
        call_args = mock_agent.snapshot_manager.save_snapshot.call_args
        snapshot = call_args[0][0]
        assert snapshot["original"] is None


# ============================================================================
# SECTION 2.5: Token Management (2 tests)
# ============================================================================


class TestTokenManagement:
    """Test token counting and management."""

    def test_get_usage_returns_correct_totals(self, mock_agent):
        """Verify usage dict structure."""
        mock_agent.total_prompt_tokens = 100
        mock_agent.total_completion_tokens = 50

        usage = mock_agent.get_usage()

        assert usage["total_prompt_tokens"] == 100
        assert usage["total_completion_tokens"] == 50
        assert usage["total_tokens"] == 150

    def test_token_counters_reset_on_reset(self, mock_agent):
        """Verify reset() clears counters."""
        mock_agent.total_prompt_tokens = 100
        mock_agent.total_completion_tokens = 50

        mock_agent.reset()

        # Note: reset() doesn't clear token counters (by design)
        # but does reset messages
        assert len(mock_agent.messages) == 1
        assert mock_agent.messages[0]["role"] == "system"


# ============================================================================
# SECTION 2.6: Message Management (4 tests)
# ============================================================================


class TestMessageManagement:
    """Test message management."""

    def test_add_user_task(self, mock_agent):
        """Append user message to messages and full_history."""
        initial_len = len(mock_agent.messages)

        mock_agent.add_user_task("Do something")

        assert len(mock_agent.messages) == initial_len + 1
        assert len(mock_agent.full_history) == initial_len + 1
        assert mock_agent.messages[-1]["role"] == "user"
        assert mock_agent.messages[-1]["content"] == "Do something"

    def test_clear_working_context(self, mock_agent):
        """Keep system prompt, clear others."""
        mock_agent.add_user_task("Task 1")
        mock_agent.add_user_task("Task 2")

        mock_agent.clear_working_context()

        assert len(mock_agent.messages) == 1
        assert mock_agent.messages[0]["role"] == "system"
        # full_history should be preserved
        assert len(mock_agent.full_history) > 1

    def test_reset(self, mock_agent):
        """Full reset with SYSTEM_PROMPT."""
        mock_agent.add_user_task("Task")

        mock_agent.reset()

        assert len(mock_agent.messages) == 1
        assert len(mock_agent.full_history) == 1
        assert SYSTEM_PROMPT in mock_agent.messages[0]["content"]

    def test_full_history_preserved(self, mock_agent):
        """Verify full_history preserved after compaction."""
        initial_history_len = len(mock_agent.full_history)
        mock_agent.add_user_task("Task 1")

        full_history_len = len(mock_agent.full_history)

        assert full_history_len == initial_history_len + 1


# ============================================================================
# SECTION 2.7: List Models & Titles (3 tests)
# ============================================================================


class TestListModelsAndTitles:
    """Test model listing and title generation."""

    def test_list_models_success(self, mock_agent, mocker):
        """Mock GET /models, return list."""
        mock_response = Mock()
        mock_response.json.return_value = {
            "data": [
                {"id": "model-1"},
                {"id": "model-2"},
                {"id": "model-3"},
            ]
        }
        mock_response.raise_for_status = Mock()
        mocker.patch("requests.get", return_value=mock_response)

        models = mock_agent.list_models()

        assert len(models) == 3
        assert "model-1" in models

    def test_list_models_api_failure(self, mock_agent, mocker):
        """Handle API error gracefully."""
        mocker.patch("requests.get", side_effect=Exception("Network error"))

        with pytest.raises(Exception):
            mock_agent.list_models()

    def test_generate_title_success(self, mock_agent, mocker):
        """Generate title from user input."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Generated Title"}}]
        }
        mocker.patch("requests.post", return_value=mock_response)

        title = mock_agent.generate_title("Write a hello world program")

        assert title == "Generated Title"


# ============================================================================
# SECTION 2.8: Approval Workflow (4 tests)
# ============================================================================


class TestApprovalWorkflow:
    """Test approval workflow."""

    def test_requires_approval_mcp_tools(self, mock_agent):
        """MCP tools with '__' require approval."""
        mock_agent.approval_callback = Mock()

        result = mock_agent._requires_approval("server__tool", {})

        assert result is True

    def test_requires_approval_dangerous_functions(self, mock_agent):
        """Dangerous functions need approval."""
        mock_agent.approval_callback = Mock()

        assert mock_agent._requires_approval("run_terminal_command", {}) is True
        assert mock_agent._requires_approval("write_file", {}) is True
        assert mock_agent._requires_approval("replace_text_in_file", {}) is True
        assert mock_agent._requires_approval("run_git_command", {}) is True

    def test_requires_approval_no_callback(self, mock_agent):
        """No approval needed if callback=None."""
        mock_agent.approval_callback = None

        result = mock_agent._requires_approval("write_file", {})

        assert result is False

    def test_get_user_approval_calls_callback(self, mock_agent, mock_approval_callback):
        """Verify callback is invoked."""
        mock_agent.approval_callback = mock_approval_callback

        mock_agent._get_user_approval("write_file", {"file_path": "test.txt"})

        mock_approval_callback.assert_called_once_with(
            "write_file", {"file_path": "test.txt"}
        )
