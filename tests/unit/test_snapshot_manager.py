"""
Unit tests for snapshot_manager.py module.

Tests snapshot creation, undo/redo functionality, and history tracking.
"""

import json
import os


from coding_agent.snapshot_manager import SnapshotManager


# ============================================================================
# SECTION 6.1: Initialization (2 tests)
# ============================================================================

class TestSnapshotManagerInitialization:
    """Test SnapshotManager initialization."""

    def test_snapshot_manager_init_creates_directory(self, tmp_path, mocker):
        """Create .snapshots directory and index."""
        mocker.patch("os.getcwd", return_value=str(tmp_path))
        
        manager = SnapshotManager()
        
        assert os.path.exists(manager.snapshot_dir)
        assert os.path.exists(manager.index_path)

    def test_snapshot_manager_loads_existing_index(self, tmp_path, mocker):
        """Load existing index on init."""
        snapshot_dir = tmp_path / ".snapshots"
        snapshot_dir.mkdir()
        
        index_data = {"next_id": 5, "undo_stack": [0, 1], "redo_stack": [2]}
        with open(snapshot_dir / "index.json", "w") as f:
            json.dump(index_data, f)
        
        mocker.patch("os.getcwd", return_value=str(tmp_path))
        manager = SnapshotManager()
        
        assert manager.index["next_id"] == 5
        assert manager.index["undo_stack"] == [0, 1]


# ============================================================================
# SECTION 6.2: Snapshot Operations (5 tests)
# ============================================================================

class TestSnapshotOperations:
    """Test snapshot save and retrieval."""

    def test_save_snapshot_creates_file(self, tmp_path, mocker):
        """Save snapshot creates JSON file."""
        mocker.patch("os.getcwd", return_value=str(tmp_path))
        manager = SnapshotManager()
        
        snapshot = {
            "file_path": "/path/to/file.txt",
            "original": "original content",
            "timestamp": 1234567890.0,
        }
        
        manager.save_snapshot(snapshot)
        
        snapshot_file = tmp_path / ".snapshots" / "0.json"
        assert snapshot_file.exists()
        
        with open(snapshot_file) as f:
            saved = json.load(f)
        
        assert saved["file_path"] == "/path/to/file.txt"
        assert saved["original"] == "original content"

    def test_save_snapshot_increments_id(self, tmp_path, mocker):
        """Each snapshot gets unique ID."""
        mocker.patch("os.getcwd", return_value=str(tmp_path))
        manager = SnapshotManager()
        
        snapshot = {"file_path": "file.txt", "original": "content", "timestamp": 0}
        
        manager.save_snapshot(snapshot)
        id1 = manager.snapshot_id - 1
        
        manager.save_snapshot(snapshot)
        id2 = manager.snapshot_id - 1
        
        assert id2 == id1 + 1

    def test_save_snapshot_updates_undo_stack(self, tmp_path, mocker):
        """Snapshot added to undo_stack."""
        mocker.patch("os.getcwd", return_value=str(tmp_path))
        manager = SnapshotManager()
        
        snapshot = {"file_path": "file.txt", "original": "content", "timestamp": 0}
        
        manager.save_snapshot(snapshot)
        
        assert 0 in manager.index["undo_stack"]
        assert len(manager.index["redo_stack"]) == 0

    def test_save_snapshot_clears_redo_stack(self, tmp_path, mocker):
        """redo_stack cleared on new snapshot."""
        mocker.patch("os.getcwd", return_value=str(tmp_path))
        manager = SnapshotManager()
        
        # Manually set redo stack
        manager.index["redo_stack"] = [1, 2]
        snapshot = {"file_path": "file.txt", "original": "content", "timestamp": 0}
        
        manager.save_snapshot(snapshot)
        
        assert len(manager.index["redo_stack"]) == 0


# ============================================================================
# SECTION 6.3: Undo/Redo Functionality (4 tests)
# ============================================================================

class TestUndoRedo:
    """Test undo and redo operations."""

    def test_undo_restores_file(self, tmp_path, mocker):
        """Undo restores original file content."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("original")
        
        mocker.patch("os.getcwd", return_value=str(tmp_path))
        manager = SnapshotManager()
        
        # Save snapshot of original
        manager.save_snapshot({
            "file_path": str(test_file),
            "original": "original",
            "timestamp": 1.0
        })
        
        # Modify file
        test_file.write_text("modified")
        
        # Undo
        result = manager.undo()
        
        assert result["action"] == "undo"
        assert test_file.read_text() == "original"

    def test_undo_empty_stack(self, tmp_path, mocker):
        """Undo with empty stack returns None."""
        mocker.patch("os.getcwd", return_value=str(tmp_path))
        manager = SnapshotManager()
        
        result = manager.undo()
        
        assert result is None

    def test_redo_restores_modified(self, tmp_path, mocker):
        """Redo restores modified state."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("original")
        
        mocker.patch("os.getcwd", return_value=str(tmp_path))
        manager = SnapshotManager()
        
        # Save original
        manager.save_snapshot({
            "file_path": str(test_file),
            "original": "original",
            "timestamp": 1.0
        })
        
        # Modify and save undo stack entry
        test_file.write_text("modified")
        result = manager.undo()
        
        # Now redo
        result = manager.redo()
        
        assert result["action"] == "redo"

    def test_redo_empty_stack(self, tmp_path, mocker):
        """Redo with empty stack returns None."""
        mocker.patch("os.getcwd", return_value=str(tmp_path))
        manager = SnapshotManager()
        
        result = manager.redo()
        
        assert result is None


# ============================================================================
# SECTION 6.4: History Tracking (2 tests)
# ============================================================================

class TestHistoryTracking:
    """Test snapshot history retrieval."""

    def test_get_history_returns_all_snapshots(self, tmp_path, mocker):
        """get_history returns list of snapshots."""
        mocker.patch("os.getcwd", return_value=str(tmp_path))
        manager = SnapshotManager()
        
        for i in range(3):
            manager.save_snapshot({
                "file_path": f"file{i}.txt",
                "original": f"content{i}",
                "timestamp": float(i)
            })
        
        history = manager.get_history()
        
        assert len(history) == 3

    def test_get_history_includes_metadata(self, tmp_path, mocker):
        """History includes file_path, action, timestamp."""
        mocker.patch("os.getcwd", return_value=str(tmp_path))
        manager = SnapshotManager()
        
        manager.save_snapshot({
            "file_path": "test.txt",
            "original": "original content",
            "timestamp": 123.456
        })
        
        history = manager.get_history()
        
        assert len(history) == 1
        assert history[0]["file_path"] == "test.txt"
        assert history[0]["action"] in ["created", "modified"]
        assert history[0]["timestamp"] == 123.456


# ============================================================================
# SECTION 6.5: New File Handling (2 tests)
# ============================================================================

class TestNewFileHandling:
    """Test handling of new file creation."""

    def test_snapshot_new_file_original_is_none(self, tmp_path, mocker):
        """New file snapshot has original=None."""
        mocker.patch("os.getcwd", return_value=str(tmp_path))
        manager = SnapshotManager()
        
        manager.save_snapshot({
            "file_path": "/new/file.txt",
            "original": None,
            "timestamp": 1.0
        })
        
        snapshot_file = tmp_path / ".snapshots" / "0.json"
        with open(snapshot_file) as f:
            saved = json.load(f)
        
        assert saved["original"] is None

    def test_undo_new_file_deletes_it(self, tmp_path, mocker):
        """Undo on new file deletes it."""
        new_file = tmp_path / "newfile.txt"
        new_file.write_text("created")
        
        mocker.patch("os.getcwd", return_value=str(tmp_path))
        manager = SnapshotManager()
        
        # Save snapshot with original=None
        manager.save_snapshot({
            "file_path": str(new_file),
            "original": None,
            "timestamp": 1.0
        })
        
        # Undo
        result = manager.undo()
        
        assert not new_file.exists()


# ============================================================================
# SECTION 6.6: Index Persistence (1 test)
# ============================================================================

class TestIndexPersistence:
    """Test index file persistence."""

    def test_index_persists_across_instances(self, tmp_path, mocker):
        """Index changes persist across manager instances."""
        mocker.patch("os.getcwd", return_value=str(tmp_path))
        
        # First instance
        manager1 = SnapshotManager()
        manager1.save_snapshot({
            "file_path": "file.txt",
            "original": "content",
            "timestamp": 1.0
        })
        
        # Second instance
        manager2 = SnapshotManager()
        
        assert len(manager2.index["undo_stack"]) == 1
        assert manager2.snapshot_id == 1
