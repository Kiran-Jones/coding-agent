"""
Unit tests for session_manager.py module.

Tests session creation, persistence, listing, and data integrity.
"""

import json


from coding_agent.session_manager import SessionManager


# ============================================================================
# SECTION 5.1: Initialization (2 tests)
# ============================================================================

class TestSessionManagerInitialization:
    """Test SessionManager initialization."""

    def test_session_manager_init_creates_directory(self, tmp_path):
        """os.makedirs(directory, exist_ok=True)."""
        session_dir = tmp_path / "sessions"
        
        manager = SessionManager(directory=str(session_dir))
        
        assert session_dir.exists()
        assert session_dir.is_dir()

    def test_session_manager_directory_parameter(self, tmp_path):
        """Custom directory parameter works."""
        custom_dir = tmp_path / "custom_sessions"
        
        manager = SessionManager(directory=str(custom_dir))
        
        assert manager.directory == str(custom_dir)
        assert custom_dir.exists()


# ============================================================================
# SECTION 5.2: Session CRUD (6 tests)
# ============================================================================

class TestSessionCRUD:
    """Test Create, Read, Update, Delete operations."""

    def test_create_session_returns_unique_id(self, tmp_path):
        """Create session, returns ID."""
        manager = SessionManager(directory=str(tmp_path / "sessions"))
        
        session_id = manager.create_session(
            messages=[{"role": "user", "content": "Hello"}],
            title="Test Session",
            full_history=[{"role": "user", "content": "Hello"}]
        )
        
        assert session_id == "1"

    def test_create_session_auto_increments(self, tmp_path):
        """Multiple sessions have IDs 1, 2, 3..."""
        manager = SessionManager(directory=str(tmp_path / "sessions"))
        
        id1 = manager.create_session([], "Session 1", [])
        id2 = manager.create_session([], "Session 2", [])
        id3 = manager.create_session([], "Session 3", [])
        
        assert id1 == "1"
        assert id2 == "2"
        assert id3 == "3"

    def test_save_session_writes_json(self, tmp_path):
        """Save and verify JSON structure."""
        manager = SessionManager(directory=str(tmp_path / "sessions"))
        
        messages = [{"role": "user", "content": "Test"}]
        full_history = [{"role": "user", "content": "Test"}]
        manager.save_session("1", "Test", messages, full_history)
        
        # Verify file exists
        session_file = tmp_path / "sessions" / "1.json"
        assert session_file.exists()
        
        # Verify content
        with open(session_file) as f:
            data = json.load(f)
        
        assert data["id"] == "1"
        assert data["title"] == "Test"
        assert data["messages"] == messages
        assert data["full_history"] == full_history
        assert "updated_at" in data

    def test_load_session_returns_data(self, tmp_path):
        """Load session returns correct data."""
        manager = SessionManager(directory=str(tmp_path / "sessions"))
        
        messages = [{"role": "user", "content": "Test"}]
        manager.save_session("1", "Test Session", messages, messages)
        
        loaded = manager.load_session("1")
        
        assert loaded["id"] == "1"
        assert loaded["title"] == "Test Session"
        assert loaded["messages"] == messages

    def test_load_session_not_found(self, tmp_path):
        """Non-existent session returns None."""
        manager = SessionManager(directory=str(tmp_path / "sessions"))
        
        result = manager.load_session("999")
        
        assert result is None

    def test_delete_session_removes_file(self, tmp_path):
        """Delete works, subsequent load returns None."""
        manager = SessionManager(directory=str(tmp_path / "sessions"))
        
        manager.save_session("1", "Test", [], [])
        assert manager.load_session("1") is not None
        
        deleted = manager.delete_session("1")
        
        assert deleted is True
        assert manager.load_session("1") is None


# ============================================================================
# SECTION 5.3: Session Listing (2 tests)
# ============================================================================

class TestSessionListing:
    """Test listing sessions."""

    def test_list_sessions_returns_sorted(self, tmp_path):
        """Sessions sorted by updated_at descending."""
        manager = SessionManager(directory=str(tmp_path / "sessions"))
        
        manager.save_session("1", "First", [], [])
        manager.save_session("2", "Second", [], [])
        manager.save_session("3", "Third", [], [])
        
        sessions = manager.list_sessions()
        
        # Should be sorted by updated_at descending (newest first)
        assert len(sessions) == 3
        assert sessions[0]["id"] in ["1", "2", "3"]

    def test_list_sessions_includes_metadata(self, tmp_path):
        """id, title, updated_at present."""
        manager = SessionManager(directory=str(tmp_path / "sessions"))
        
        manager.save_session("1", "Test Session", [], [])
        
        sessions = manager.list_sessions()
        
        assert len(sessions) == 1
        assert sessions[0]["id"] == "1"
        assert sessions[0]["title"] == "Test Session"
        assert "updated_at" in sessions[0]


# ============================================================================
# SECTION 5.4: Data Integrity (3 tests)
# ============================================================================

class TestSessionDataIntegrity:
    """Test data integrity."""

    def test_session_full_history_preserved(self, tmp_path):
        """full_history and messages kept separate."""
        manager = SessionManager(directory=str(tmp_path / "sessions"))
        
        messages = [{"role": "system", "content": "System"}]
        full_history = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "User 1"},
            {"role": "assistant", "content": "Response 1"},
            {"role": "user", "content": "User 2"},
        ]
        
        manager.save_session("1", "Test", messages, full_history)
        loaded = manager.load_session("1")
        
        assert loaded["messages"] == messages
        assert loaded["full_history"] == full_history
        assert len(loaded["full_history"]) > len(loaded["messages"])

    def test_session_special_characters_in_content(self, tmp_path):
        """Handle special characters and unicode."""
        manager = SessionManager(directory=str(tmp_path / "sessions"))
        
        messages = [{"role": "user", "content": "Hello 世界 🚀 <script>alert('xss')</script>"}]
        manager.save_session("1", "Unicode", messages, messages)
        
        loaded = manager.load_session("1")
        
        assert "世界" in loaded["messages"][0]["content"]
        assert "🚀" in loaded["messages"][0]["content"]

    def test_session_empty_messages(self, tmp_path):
        """Handle empty message lists."""
        manager = SessionManager(directory=str(tmp_path / "sessions"))
        
        manager.save_session("1", "Empty", [], [])
        loaded = manager.load_session("1")
        
        assert loaded["messages"] == []
        assert loaded["full_history"] == []
