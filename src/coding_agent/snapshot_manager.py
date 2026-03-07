import json
import os


class SnapshotManager:
    def __init__(self):
        self.snapshot_dir = os.path.join(os.getcwd(), ".snapshots")
        os.makedirs(self.snapshot_dir, exist_ok=True)

        self.index_path = os.path.join(self.snapshot_dir, "index.json")
        if not os.path.exists(self.index_path):
            with open(self.index_path, "w") as f:
                json.dump({"next_id": 0, "undo_stack": [], "redo_stack": []}, f)

        self._load_index()

        self.snapshot_id = self.index.get("next_id", 0)

    def save_snapshot(self, snapshot: dict):
        filepath = os.path.join(self.snapshot_dir, f"{self.snapshot_id}.json")
        with open(filepath, "w") as f:
            json.dump(snapshot, f)

        self.index["undo_stack"].append(self.snapshot_id)
        self.index["redo_stack"] = []  # Clear redo stack on new snapshot
        self.snapshot_id += 1
        self.index["next_id"] = self.snapshot_id

        self._save_index()

    def undo(self) -> dict | None:
        if not self.index["undo_stack"]:
            return None

        last_id = self.index["undo_stack"].pop()

        filepath = os.path.join(self.snapshot_dir, f"{last_id}.json")
        with open(filepath, "r") as f:
            snapshot = json.load(f)

        file_path = snapshot["file_path"]

        # Snapshot current state before restoring, push onto redo stack
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                current_content = f.read()
        else:
            current_content = None

        redo_filepath = os.path.join(self.snapshot_dir, f"{self.snapshot_id}.json")
        with open(redo_filepath, "w") as f:
            json.dump({"file_path": file_path, "original": current_content, "timestamp": snapshot["timestamp"]}, f)
        self.index["redo_stack"].append(self.snapshot_id)
        self.snapshot_id += 1
        self.index["next_id"] = self.snapshot_id

        # Restore the file
        if snapshot["original"] is None:
            if os.path.exists(file_path):
                os.remove(file_path)
        else:
            with open(file_path, "w") as f:
                f.write(snapshot["original"])

        self._save_index()
        return {"file_path": file_path, "action": "undo"}

    def redo(self) -> dict | None:
        if not self.index["redo_stack"]:
            return None

        last_id = self.index["redo_stack"].pop()

        filepath = os.path.join(self.snapshot_dir, f"{last_id}.json")
        with open(filepath, "r") as f:
            snapshot = json.load(f)

        file_path = snapshot["file_path"]

        # Snapshot current state before restoring, push onto undo stack
        if os.path.exists(file_path):
            with open(file_path, "r") as f:
                current_content = f.read()
        else:
            current_content = None

        undo_filepath = os.path.join(self.snapshot_dir, f"{self.snapshot_id}.json")
        with open(undo_filepath, "w") as f:
            json.dump({"file_path": file_path, "original": current_content, "timestamp": snapshot["timestamp"]}, f)
        self.index["undo_stack"].append(self.snapshot_id)
        self.snapshot_id += 1
        self.index["next_id"] = self.snapshot_id

        # Restore the file
        if snapshot["original"] is None:
            if os.path.exists(file_path):
                os.remove(file_path)
        else:
            with open(file_path, "w") as f:
                f.write(snapshot["original"])

        self._save_index()
        return {"file_path": file_path, "action": "redo"}

    def get_history(self) -> list[dict]:
        """Return snapshot details for each entry in the undo stack."""
        history = []
        for sid in self.index["undo_stack"]:
            filepath = os.path.join(self.snapshot_dir, f"{sid}.json")
            if os.path.exists(filepath):
                with open(filepath, "r") as f:
                    snapshot = json.load(f)
                action = "created" if snapshot.get("original") is None else "modified"
                history.append({
                    "id": sid,
                    "file_path": snapshot["file_path"],
                    "action": action,
                    "timestamp": snapshot.get("timestamp", 0),
                })
        return history

    def _load_index(self):
        if not os.path.exists(self.index_path):
            self.index = {"next_id": 0, "undo_stack": [], "redo_stack": []}
            with open(self.index_path, "w") as f:
                json.dump(self.index, f)
                return

        with open(self.index_path, "r") as f:
            self.index = json.load(f)

    def _save_index(self):
        with open(self.index_path, "w") as f:
            json.dump(self.index, f)
