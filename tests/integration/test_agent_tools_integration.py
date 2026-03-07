"""
Integration tests for Agent and Tools interaction.

Tests agent calling tools, handling results, and state management.
"""

import json
from unittest.mock import patch


class TestAgentToolsIntegration:
    """Test agent-tools integration."""

    def test_agent_calls_read_file_tool(self, mock_agent, tmp_path):
        """Agent can call read_file tool."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        tool_calls = [
            {
                "id": "call-1",
                "function": {
                    "name": "read_file",
                    "arguments": json.dumps({"file_path": str(test_file)}),
                },
            }
        ]

        summaries = mock_agent._handle_tool_calls(tool_calls)

        assert "Test content" in summaries[0]["result"]

    def test_agent_calls_write_file_tool(self, mock_agent, tmp_path):
        """Agent can call write_file tool."""
        test_file = tmp_path / "output.txt"

        tool_calls = [
            {
                "id": "call-1",
                "function": {
                    "name": "write_file",
                    "arguments": json.dumps(
                        {"file_path": str(test_file), "content": "New content"}
                    ),
                },
            }
        ]

        summaries = mock_agent._handle_tool_calls(tool_calls)

        assert "Success" in summaries[0]["result"]
        assert test_file.read_text() == "New content"

    def test_agent_chained_read_write(self, mock_agent, tmp_path):
        """Agent can read file, then write modified version."""
        source_file = tmp_path / "source.txt"
        source_file.write_text("Original")

        dest_file = tmp_path / "dest.txt"

        # Read tool call
        tool_calls = [
            {
                "id": "call-1",
                "function": {
                    "name": "read_file",
                    "arguments": json.dumps({"file_path": str(source_file)}),
                },
            }
        ]
        mock_agent._handle_tool_calls(tool_calls)

        # Write tool call
        tool_calls = [
            {
                "id": "call-2",
                "function": {
                    "name": "write_file",
                    "arguments": json.dumps(
                        {"file_path": str(dest_file), "content": "Modified"}
                    ),
                },
            }
        ]
        mock_agent._handle_tool_calls(tool_calls)

        assert dest_file.exists()
        assert dest_file.read_text() == "Modified"

    def test_agent_tool_messages_appended_correctly(self, mock_agent):
        """Tool results added to message history."""
        initial_len = len(mock_agent.messages)

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

            mock_agent._handle_tool_calls(tool_calls)

        # Should add tool message
        assert len(mock_agent.messages) == initial_len + 1
        assert mock_agent.messages[-1]["role"] == "tool"

    def test_agent_snapshot_integration(self, mock_agent, tmp_path):
        """Tool execution triggers snapshot."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("original")

        tool_calls = [
            {
                "id": "call-1",
                "function": {
                    "name": "write_file",
                    "arguments": json.dumps(
                        {"file_path": str(test_file), "content": "modified"}
                    ),
                },
            }
        ]

        mock_agent._handle_tool_calls(tool_calls)

        # Verify snapshot was called
        assert mock_agent.snapshot_manager.save_snapshot.called

    def test_multiple_tools_in_single_call(self, mock_agent):
        """Handle multiple tool calls at once."""
        with patch.dict(
            "coding_agent.tools.AVAILABLE_TOOLS",
            {"read_file": lambda file_path, **kwargs: "content"},
        ):
            tool_calls = [
                {
                    "id": "call-1",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"file_path": "file1.txt"}',
                    },
                },
                {
                    "id": "call-2",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"file_path": "file2.txt"}',
                    },
                },
            ]

            summaries = mock_agent._handle_tool_calls(tool_calls)

        assert len(summaries) == 2
        assert all("content" in s["result"] for s in summaries)


class TestAgentToolErrorHandling:
    """Test error handling in tool execution."""

    def test_agent_handles_tool_timeout(self, mock_agent, mocker):
        """Handle timeout in terminal command."""
        mocker.patch.dict(
            "coding_agent.tools.AVAILABLE_TOOLS",
            {
                "run_terminal_command": lambda command, **kwargs: (
                    "Error: The command timed out"
                )
            },
        )

        tool_calls = [
            {
                "id": "call-1",
                "function": {
                    "name": "run_terminal_command",
                    "arguments": '{"command": "sleep 1000"}',
                },
            }
        ]

        summaries = mock_agent._handle_tool_calls(tool_calls)

        assert "timed out" in summaries[0]["result"].lower()

    def test_agent_handles_file_not_found(self, mock_agent):
        """Handle missing file gracefully."""
        tool_calls = [
            {
                "id": "call-1",
                "function": {
                    "name": "read_file",
                    "arguments": '{"file_path": "/nonexistent/path/file.txt"}',
                },
            }
        ]

        summaries = mock_agent._handle_tool_calls(tool_calls)

        assert "Error" in summaries[0]["result"]
        assert "not found" in summaries[0]["result"].lower()
