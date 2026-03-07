"""
Integration tests for Memory and Session management.

Tests message compaction with session persistence.
"""



from coding_agent.session_manager import SessionManager
from coding_agent.memory_utils import smart_compact


class TestMemorySessionIntegration:
    """Test memory and session interaction."""

    def test_compacted_messages_can_be_saved(self, tmp_path, mocker):
        """Save compacted messages to session."""
        # Create many messages
        messages = [{"role": "system", "content": "System"}]
        for i in range(50):
            messages.append({
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"Message {i}"
            })
        
        mock_response = mocker.Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Compaction summary"}}]
        }
        mocker.patch("requests.post", return_value=mock_response)
        
        # Compact
        compacted, was_compacted = smart_compact(
            messages, "key", "http://api.test", "model"
        )
        
        # Save to session
        manager = SessionManager(directory=str(tmp_path / "sessions"))
        session_id = manager.create_session(compacted, "Test", messages)
        
        # Load and verify
        loaded = manager.load_session(session_id)
        assert len(loaded["messages"]) < len(loaded["full_history"])

    def test_full_history_preserved_after_compaction(self, tmp_path, mocker):
        """full_history unchanged, only messages compacted."""
        messages = [{"role": "system", "content": "System"}]
        full_history = [{"role": "system", "content": "System"}]
        
        for i in range(50):
            msg = {
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"Message {i}"
            }
            messages.append(msg)
            full_history.append(msg)
        
        mock_response = mocker.Mock()
        mock_response.json.return_value = {
            "choices": [{"message": {"content": "Summary"}}]
        }
        mocker.patch("requests.post", return_value=mock_response)
        
        # Compact
        compacted, was_compacted = smart_compact(
            messages, "key", "http://api.test", "model"
        )
        
        # Save
        manager = SessionManager(directory=str(tmp_path / "sessions"))
        manager.save_session("1", "Test", compacted, full_history)
        
        # Load and verify
        loaded = manager.load_session("1")
        assert len(loaded["full_history"]) == len(full_history)
        assert len(loaded["messages"]) < len(messages)

    def test_session_recovery_after_crash(self, tmp_path, mocker):
        """Load compacted session, continue operation."""
        # Create session with compacted messages
        messages = [{"role": "system", "content": "System"}]
        for i in range(10):
            messages.append({
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"Message {i}"
            })
        
        manager = SessionManager(directory=str(tmp_path / "sessions"))
        session_id = manager.create_session(messages, "Recovery Test", messages)
        
        # Load it back
        loaded = manager.load_session(session_id)
        
        # Verify we can work with it
        assert len(loaded["messages"]) == len(messages)
        assert loaded["messages"][0]["role"] == "system"

    def test_multiple_sessions_separate_histories(self, tmp_path, mocker):
        """Each session has independent history."""
        manager = SessionManager(directory=str(tmp_path / "sessions"))
        
        # Session 1
        messages1 = [{"role": "system", "content": "System"}]
        for i in range(5):
            messages1.append({
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"Session 1 - Message {i}"
            })
        
        # Session 2
        messages2 = [{"role": "system", "content": "System"}]
        for i in range(10):
            messages2.append({
                "role": "user" if i % 2 == 0 else "assistant",
                "content": f"Session 2 - Message {i}"
            })
        
        id1 = manager.create_session(messages1, "Session 1", messages1)
        id2 = manager.create_session(messages2, "Session 2", messages2)
        
        # Load and verify
        loaded1 = manager.load_session(id1)
        loaded2 = manager.load_session(id2)
        
        assert len(loaded1["messages"]) != len(loaded2["messages"])
        assert "Session 1" in loaded1["messages"][1]["content"]
        assert "Session 2" in loaded2["messages"][1]["content"]
