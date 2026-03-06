use chrono::Local;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::fs;
use std::path::PathBuf;
use uuid::Uuid;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionData {
    pub id: String,
    pub title: String,
    pub created_at: String,
    pub updated_at: String,
    pub messages: Vec<Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SessionInfo {
    pub id: String,
    pub title: String,
    pub updated_at: String,
}

pub struct SessionManager {
    session_dir: PathBuf,
}

impl SessionManager {
    pub fn new() -> std::io::Result<Self> {
        let session_dir = PathBuf::from(".sessions");
        fs::create_dir_all(&session_dir)?;
        Ok(SessionManager { session_dir })
    }

    /// Generate a new session ID in format: YYYYMMDD_HHMMSS_{6 random hex chars}
    pub fn generate_session_id() -> String {
        let now = Local::now();
        let timestamp = now.format("%Y%m%d_%H%M%S");
        let random = Uuid::new_v4().to_string()[0..6].to_string();
        format!("{}_{}", timestamp, random)
    }

    /// Create a new session
    pub fn create_session(&self, messages: Vec<Value>, title: String) -> String {
        let session_id = Self::generate_session_id();
        let _ = self.save_session(&session_id, &title, messages);
        session_id
    }

    /// Save session to .sessions/{id}.json
    pub fn save_session(&self, session_id: &str, title: &str, messages: Vec<Value>) -> std::io::Result<()> {
        let now = Local::now().to_rfc3339();
        let created_at = now.clone();

        // Check if session exists to preserve created_at
        let created_at = if let Ok(existing) = self.load_session(session_id) {
            existing.created_at
        } else {
            created_at
        };

        let session_data = SessionData {
            id: session_id.to_string(),
            title: title.to_string(),
            created_at,
            updated_at: now,
            messages,
        };

        let file_path = self.session_dir.join(format!("{}.json", session_id));
        let json = serde_json::to_string_pretty(&session_data)?;
        fs::write(file_path, json)?;

        Ok(())
    }

    /// Load a session
    pub fn load_session(&self, session_id: &str) -> std::io::Result<SessionData> {
        let file_path = self.session_dir.join(format!("{}.json", session_id));
        let json = fs::read_to_string(file_path)?;
        let session: SessionData = serde_json::from_str(&json)?;
        Ok(session)
    }

    /// List all sessions, sorted by updated_at descending
    pub fn list_sessions(&self) -> std::io::Result<Vec<SessionInfo>> {
        let mut sessions = Vec::new();

        for entry in fs::read_dir(&self.session_dir)? {
            let entry = entry?;
            let path = entry.path();

            if path.extension().and_then(|s| s.to_str()) == Some("json") {
                if let Ok(json) = fs::read_to_string(&path) {
                    if let Ok(session) = serde_json::from_str::<SessionData>(&json) {
                        sessions.push(SessionInfo {
                            id: session.id,
                            title: session.title,
                            updated_at: session.updated_at,
                        });
                    }
                }
            }
        }

        // Sort by updated_at descending
        sessions.sort_by(|a, b| b.updated_at.cmp(&a.updated_at));

        Ok(sessions)
    }
}
