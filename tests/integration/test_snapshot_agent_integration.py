"""
Integration tests for Snapshot and Agent interaction.

Tests snapshot creation during tool execution, undo/redo workflows.
"""

import json


from coding_agent.snapshot_manager import SnapshotManager


class TestSnapshotAgentIntegration:
    """Test snapshot and agent interaction."""

    def test_agent_tool_triggers_snapshot(self, mock_agent, tmp_path, mocker):
        """Agent tool execution creates snapshot."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("original")

        # Mock snapshot manager
        mock_snapshot_mgr = mocker.Mock(spec=SnapshotManager)
        mock_agent.snapshot_manager = mock_snapshot_mgr

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

        # Verify snapshot was saved
        mock_snapshot_mgr.save_snapshot.assert_called_once()
        call_args = mock_snapshot_mgr.save_snapshot.call_args[0][0]
        assert call_args["file_path"] == str(test_file)
        assert call_args["original"] == "original"

    def test_snapshot_preserves_original_before_modification(self, tmp_path, mocker):
        """Snapshot captures original before write."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("original content")

        mocker.patch("os.getcwd", return_value=str(tmp_path))
        snapshot_mgr = SnapshotManager()

        snapshot = {
            "file_path": str(test_file),
            "original": "original content",
            "timestamp": 1.0,
        }

        snapshot_mgr.save_snapshot(snapshot)

        # Modify file
        test_file.write_text("new content")

        # Verify original preserved in snapshot
        history = snapshot_mgr.get_history()
        assert history[0]["file_path"] == str(test_file)

    def test_undo_after_multiple_file_edits(self, tmp_path, mocker):
        """Undo restores state across multiple edits."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("state 1")

        mocker.patch("os.getcwd", return_value=str(tmp_path))
        snapshot_mgr = SnapshotManager()

        # Edit 1
        snapshot_mgr.save_snapshot(
            {"file_path": str(test_file), "original": "state 1", "timestamp": 1.0}
        )
        test_file.write_text("state 2")

        # Edit 2
        snapshot_mgr.save_snapshot(
            {"file_path": str(test_file), "original": "state 2", "timestamp": 2.0}
        )
        test_file.write_text("state 3")

        # Undo once
        snapshot_mgr.undo()
        assert test_file.read_text() == "state 2"

        # Undo again
        snapshot_mgr.undo()
        assert test_file.read_text() == "state 1"

    def test_multiple_files_snapshot_tracking(self, tmp_path, mocker):
        """Track snapshots for multiple files."""
        file1 = tmp_path / "file1.txt"
        file2 = tmp_path / "file2.txt"
        file1.write_text("file1 original")
        file2.write_text("file2 original")

        mocker.patch("os.getcwd", return_value=str(tmp_path))
        snapshot_mgr = SnapshotManager()

        # Edit file 1
        snapshot_mgr.save_snapshot(
            {"file_path": str(file1), "original": "file1 original", "timestamp": 1.0}
        )

        # Edit file 2
        snapshot_mgr.save_snapshot(
            {"file_path": str(file2), "original": "file2 original", "timestamp": 2.0}
        )

        # Verify both tracked
        history = snapshot_mgr.get_history()
        assert len(history) == 2
        paths = [h["file_path"] for h in history]
        assert str(file1) in paths
        assert str(file2) in paths

    def test_snapshot_with_readonly_tools(self, mock_agent, mocker):
        """Readonly tools don't trigger snapshots."""
        mock_agent.snapshot_manager = mocker.Mock()

        mocker.patch.dict(
            "coding_agent.tools.AVAILABLE_TOOLS",
            {"read_file": lambda file_path, **kwargs: "content"},
        )
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

        # Snapshot should not be called
        mock_agent.snapshot_manager.save_snapshot.assert_not_called()

    def test_new_file_creation_snapshot(self, tmp_path, mocker):
        """New file creation creates snapshot with original=None."""
        new_file = tmp_path / "new.txt"

        mocker.patch("os.getcwd", return_value=str(tmp_path))
        snapshot_mgr = SnapshotManager()

        snapshot_mgr.save_snapshot(
            {"file_path": str(new_file), "original": None, "timestamp": 1.0}
        )

        history = snapshot_mgr.get_history()
        assert history[0]["file_path"] == str(new_file)

        # Check the actual snapshot file
        snapshot_file = tmp_path / ".snapshots" / "0.json"
        import json

        with open(snapshot_file) as f:
            data = json.load(f)
        assert data["original"] is None
