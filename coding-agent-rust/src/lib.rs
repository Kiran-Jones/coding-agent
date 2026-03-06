pub mod agent;
pub mod tools;
pub mod session;
pub mod memory;

pub use agent::CodingAgent;
pub use session::SessionManager;
pub use tools::{execute_tool, get_tools_schema};
pub use memory::smart_compact;
