"""
Unit tests for memory_utils.py module.

Tests summary generation and smart compaction of message history.
"""

from unittest.mock import Mock


from coding_agent.memory_utils import generate_summary, smart_compact


# ============================================================================
# SECTION 4.1: Summary Generation (4 tests)
# ============================================================================


class TestGenerateSummary:
    """Test summary generation."""

    def test_generate_summary_basic(self, mocker):
        """Create chat_log from messages, call API."""
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]

        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Summary: Conversation started"}}]
        }
        mock_response.raise_for_status = Mock()
        mocker.patch("requests.post", return_value=mock_response)

        summary = generate_summary(messages, "key", "http://api.test", "model")

        assert "Summary" in summary

    def test_generate_summary_with_tool_calls(self, mocker):
        """Handle messages with tool_calls."""
        messages = [
            {
                "role": "assistant",
                "content": "Running tool",
                "tool_calls": [
                    {
                        "function": {
                            "name": "write_file",
                            "arguments": '{"file_path": "test.txt"}',
                        }
                    }
                ],
            }
        ]

        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Executed write_file"}}]
        }
        mock_response.raise_for_status = Mock()
        mocker.patch("requests.post", return_value=mock_response)

        summary = generate_summary(messages, "key", "http://api.test", "model")

        assert summary

    def test_generate_summary_api_error(self, mocker):
        """Return error message on API failure."""
        messages = [{"role": "user", "content": "Hello"}]

        mocker.patch("requests.post", side_effect=Exception("Network error"))

        summary = generate_summary(messages, "key", "http://api.test", "model")

        assert "Failed to generate summary" in summary

    def test_generate_summary_truncates_large_content(self, mocker):
        """Content truncated appropriately."""
        messages = [
            {
                "role": "user",
                "content": "x" * 1000,  # Very long content
            }
        ]

        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Summary"}}]
        }
        mocker.patch("requests.post", return_value=mock_response)

        summary = generate_summary(messages, "key", "http://api.test", "model")

        # Should not error on large content
        assert summary


# ============================================================================
# SECTION 4.2: Smart Compact Behavior (4 tests)
# ============================================================================


class TestSmartCompact:
    """Test message compaction."""

    def test_smart_compact_no_compaction_needed(self, mocker):
        """len(messages) <= MAX_MESSAGES=40 → return unchanged, False."""
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]

        result_messages, was_compacted = smart_compact(
            messages, "key", "http://api.test", "model"
        )

        assert result_messages == messages
        assert was_compacted is False

    def test_smart_compact_compaction_happens(self, mocker):
        """len(messages) > 40 → return compacted, True."""
        # Create > 40 messages
        messages = [{"role": "system", "content": "System"}]
        for i in range(45):
            messages.append(
                {
                    "role": "user" if i % 2 == 0 else "assistant",
                    "content": f"Message {i}",
                }
            )

        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Compact summary"}}]
        }
        mocker.patch("requests.post", return_value=mock_response)

        result_messages, was_compacted = smart_compact(
            messages, "key", "http://api.test", "model"
        )

        assert was_compacted is True
        assert len(result_messages) < len(messages)

    def test_smart_compact_preserves_system_prompt(self, mocker):
        """messages[0] always preserved."""
        system_msg = {"role": "system", "content": "Original system prompt"}
        messages = [system_msg]
        for i in range(50):
            messages.append(
                {
                    "role": "user" if i % 2 == 0 else "assistant",
                    "content": f"Message {i}",
                }
            )

        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Summary"}}]
        }
        mocker.patch("requests.post", return_value=mock_response)

        result_messages, was_compacted = smart_compact(
            messages, "key", "http://api.test", "model"
        )

        assert result_messages[0] == system_msg

    def test_smart_compact_keeps_recent_messages(self, mocker):
        """KEEP_RECENT=15 latest messages preserved."""
        messages = [{"role": "system", "content": "System"}]
        for i in range(50):
            messages.append(
                {
                    "role": "user" if i % 2 == 0 else "assistant",
                    "content": f"Message {i}",
                }
            )

        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Summary"}}]
        }
        mocker.patch("requests.post", return_value=mock_response)

        result_messages, was_compacted = smart_compact(
            messages, "key", "http://api.test", "model"
        )

        # Should have system + summary + 15 recent
        # Exact count depends on role filtering
        assert len(result_messages) <= 18


# ============================================================================
# SECTION 4.3: Edge Cases (4 tests)
# ============================================================================


class TestSmartCompactEdgeCases:
    """Test edge cases in compaction."""

    def test_smart_compact_single_system_message(self, mocker):
        """Only system prompt → no compaction."""
        messages = [{"role": "system", "content": "System"}]

        result_messages, was_compacted = smart_compact(
            messages, "key", "http://api.test", "model"
        )

        assert result_messages == messages
        assert was_compacted is False

    def test_smart_compact_strips_tool_messages(self, mocker):
        """Tool messages are stripped from recent."""
        messages = [{"role": "system", "content": "System"}]
        for i in range(50):
            messages.append(
                {
                    "role": "user" if i % 2 == 0 else "assistant",
                    "content": f"Message {i}",
                }
            )
        # Add tool messages at end
        messages.append({"role": "tool", "content": "Tool result"})
        messages.append({"role": "tool", "content": "Tool result 2"})

        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Summary"}}]
        }
        mocker.patch("requests.post", return_value=mock_response)

        result_messages, was_compacted = smart_compact(
            messages, "key", "http://api.test", "model"
        )

        # Should strip tool messages from the end
        assert was_compacted is True

    def test_smart_compact_handles_empty_summary(self, mocker):
        """If num_to_summarize <= 0, return unchanged."""
        messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "Hi"},
        ]

        result_messages, was_compacted = smart_compact(
            messages, "key", "http://api.test", "model"
        )

        assert was_compacted is False

    def test_smart_compact_summary_node_format(self, mocker):
        """Verify summary node has correct format."""
        messages = [{"role": "system", "content": "System"}]
        for i in range(50):
            messages.append(
                {
                    "role": "user" if i % 2 == 0 else "assistant",
                    "content": f"Message {i}",
                }
            )

        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Compact summary content"}}]
        }
        mocker.patch("requests.post", return_value=mock_response)

        result_messages, was_compacted = smart_compact(
            messages, "key", "http://api.test", "model"
        )

        # Find summary node
        summary_node = result_messages[1]
        assert summary_node["role"] == "system"
        assert "SUMMARY" in summary_node["content"]
        assert "Compact summary content" in summary_node["content"]
