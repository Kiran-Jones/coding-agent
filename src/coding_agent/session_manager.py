# session_manager.py

import json
import os
from datetime import datetime


class SessionManager:
    def __init__(self, directory=".sessions"):
        self.directory = directory
        os.makedirs(self.directory, exist_ok=True)

    def _get_filepath(self, session_id: str) -> str:
        """Helper to get the full file path for a given session ID."""
        return os.path.join(self.directory, f"{session_id}.json")

    def _next_id(self) -> str:
        """Return the next integer session ID."""
        existing = []
        for filename in os.listdir(self.directory):
            if filename.endswith(".json"):
                name = filename[:-5]
                if name.isdigit():
                    existing.append(int(name))
        return str(max(existing, default=0) + 1)

    def create_session(self, messages: list, title: str) -> str:
        """Create a new session file with a unique ID and return that ID."""
        session_id = self._next_id()
        self.save_session(session_id, title, messages)
        return session_id

    def save_session(self, session_id: str, title: str, messages: list):
        """Save session data to a JSON file."""
        session_data = {
            "id": session_id,
            "title": title,
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "messages": messages,
        }
        with open(self._get_filepath(session_id), "w") as f:
            json.dump(session_data, f, indent=4)

    def load_session(self, session_id: str) -> dict | None:
        """Loads a specific session by ID. Returns None if it doesn't exist."""
        filepath = self._get_filepath(session_id)
        if not os.path.exists(filepath):
            return None
        with open(filepath, "r") as f:
            return json.load(f)

    def list_sessions(self) -> list:
        """Return a list of all saved sessions."""
        sessions = []
        for filename in os.listdir(self.directory):
            if filename.endswith(".json"):
                with open(os.path.join(self.directory, filename), "r") as f:
                    session_data = json.load(f)
                    sessions.append(
                        {
                            "id": session_data["id"],
                            "title": session_data["title"],
                            "updated_at": session_data["updated_at"],
                        }
                    )
        return sorted(sessions, key=lambda x: x["updated_at"], reverse=True)

    def delete_session(self, session_id: str) -> bool:
        """Delete a session by ID. Returns True if deleted, False if not found."""
        filepath = self._get_filepath(session_id)
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        return False
