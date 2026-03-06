# Development Guide

This guide is for developers who want to contribute to the Coding Agent project or customize it for their needs.

## Project Structure

```
coding-agent-rust/
├── Cargo.toml              # Project manifest and dependencies
├── .env.example            # Example environment configuration
├── .gitignore              # Git ignore rules
├── README.md               # User guide
├── QUICKSTART.md           # Quick start guide
├── DEVELOPMENT.md          # This file
├── src/
│   ├── main.rs            # CLI entry point and command handling
│   ├── lib.rs             # Module exports
│   ├── agent.rs           # CodingAgent struct and agentic loop
│   ├── tools.rs           # Tool implementations and schemas
│   ├── session.rs         # Session persistence logic
│   └── memory.rs          # Context compaction and summarization
└── target/                # Build output (ignored)
```

## Architecture Overview

### Agent Loop Flow

```
User Input
    ↓
Add to messages
    ↓
Check if compact needed → Call API to summarize
    ↓
Call API for response
    ↓
Extract tools from response
    ↓
Execute tools (one at a time)
    ↓
Add tool results back
    ↓
Repeat until no more tools
    ↓
Return text response
    ↓
Save session
```

### Module Responsibilities

#### main.rs
- **CLI Loop**: Interactive readline-based input
- **Command Routing**: Handles `/` commands
- **Session Management**: Create/load/list sessions
- **Output Formatting**: Colored output and panels
- **Agent Invocation**: Runs agent loop when user submits text

#### agent.rs
- **CodingAgent Struct**: Holds messages and API credentials
- **Message Management**: Add user/assistant messages
- **Agent Step**: Single execution step with tool handling
- **API Communication**: Calls the OpenAI-compatible endpoint
- **Tool Execution**: Dispatches to tool executor and processes results

#### tools.rs
- **Tool Schemas**: OpenAI function definitions for all 8 tools
- **Tool Router**: `execute_tool()` dispatcher function
- **Tool Implementations**: 
  - `run_terminal_command`: Shell execution with safety checks
  - `write_file`: File creation with directory auto-creation
  - `read_file`: File reading with line numbers
  - `replace_text_in_file`: Text substitution
  - `list_directory`: Directory listing (filtered)
  - `web_search`: DuckDuckGo search with parsing
  - `read_webpage`: Webpage fetching and HTML parsing
  - `run_git_command`: Git execution with validation

#### session.rs
- **SessionManager**: Handles session I/O
- **Session Format**: JSON files in `.sessions/` directory
- **SessionData**: Struct holding full session information
- **SessionInfo**: Minimal info for listing
- **ID Generation**: `YYYYMMDD_HHMMSS_{random}` format

#### memory.rs
- **smart_compact()**: Main compaction entry point
- **generate_summary()**: API call to create summary
- **Compaction Logic**: Keeps system + last 15 messages, summarizes the rest
- **Token Management**: Reduces token usage for long conversations

## Development Setup

### Build Commands

```bash
# Debug build
cargo build

# Release build (optimized)
cargo build --release

# Run with debug build
cargo run

# Run with release build
cargo run --release

# Run tests
cargo test

# Watch for changes (requires cargo-watch)
cargo watch -x run
```

### Code Quality

```bash
# Format code
cargo fmt

# Check formatting
cargo fmt -- --check

# Lint code
cargo clippy

# Check dependencies
cargo tree

# Audit dependencies for vulnerabilities
cargo audit
```

## Key Data Structures

### Message Format (serde_json::Value)

User message:
```json
{
  "role": "user",
  "content": "Hello, create a Python script..."
}
```

Assistant message with tools:
```json
{
  "role": "assistant",
  "content": "I'll create that script for you.",
  "tool_calls": [
    {
      "id": "call_123",
      "function": {
        "name": "write_file",
        "arguments": "{\"file_path\": \"script.py\", \"content\": \"...\"}"
      }
    }
  ]
}
```

Tool result message:
```json
{
  "role": "user",
  "content": "File written successfully to script.py"
}
```

## Adding a New Tool

### Step 1: Add Tool Schema (tools.rs)

```rust
pub fn get_tools_schema() -> Value {
    json!([
        // ... existing tools ...
        {
            "type": "function",
            "function": {
                "name": "my_tool_name",
                "description": "What this tool does",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "param1": {
                            "type": "string",
                            "description": "Description of param1"
                        }
                    },
                    "required": ["param1"]
                }
            }
        }
    ])
}
```

### Step 2: Implement Tool Function (tools.rs)

```rust
async fn my_tool_name(args: &Value) -> String {
    let param1 = match args.get("param1").and_then(|v| v.as_str()) {
        Some(p) => p,
        None => return "Error: 'param1' parameter is required".to_string(),
    };

    // Implementation here
    format!("Result: {}", param1)
}
```

### Step 3: Add to Router (tools.rs)

```rust
pub async fn execute_tool(name: &str, args: &Value) -> String {
    match name {
        // ... existing tools ...
        "my_tool_name" => my_tool_name(args).await,
        _ => format!("Unknown tool: {}", name),
    }
}
```

## Modifying the System Prompt

The system prompt is defined in `agent.rs`:

```rust
const SYSTEM_PROMPT: &str = "You are a coding agent...";
```

Change it to customize agent behavior. Remember to also update the prompt reconciliation in `main.rs` when loading sessions:

```rust
// In main.rs, handle_slash_command function
messages[0] = serde_json::json!({
    "role": "system",
    "content": "Your new system prompt here"
});
```

## Customizing API Behavior

### Change Model

In `agent.rs`, modify the API call:

```rust
let request_body = json!({
    "model": "gpt-4-turbo",  // Change this
    "messages": self.messages,
    "tools": get_tools_schema(),
    "tool_choice": "auto",
    "max_tokens": 4096
});
```

### Adjust Token Limits

In `agent.rs`:
```rust
"max_tokens": 8192  // Increase for longer responses
```

### Change Temperature

In `memory.rs` (for summarization):
```rust
"temperature": 0.1,  // More deterministic (0.0-1.0)
```

## Session Format

Sessions are stored as JSON in `.sessions/{id}.json`:

```json
{
  "id": "20240115_143022_a1b2c3",
  "title": "Project Setup",
  "created_at": "2024-01-15T14:30:22.123456789Z",
  "updated_at": "2024-01-15T14:35:45.987654321Z",
  "messages": [
    {
      "role": "system",
      "content": "You are a coding agent..."
    },
    {
      "role": "user",
      "content": "Create a Python script..."
    },
    // ... more messages ...
  ]
}
```

## Error Handling

All async functions return `Result<String, _>` or `String`. Tools return `String` directly.

### Best Practices

1. Always validate parameters before use
2. Return user-friendly error messages
3. Use `match` for Option/Result handling
4. Log errors to stderr when appropriate

Example:
```rust
let file_path = match args.get("file_path").and_then(|v| v.as_str()) {
    Some(path) => path,
    None => return "Error: 'file_path' parameter is required".to_string(),
};

match fs::write(file_path, content) {
    Ok(_) => format!("File written successfully to {}", file_path),
    Err(e) => format!("Error writing file: {}", e),
}
```

## Testing

### Unit Tests

Add tests in the same file:

```rust
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_my_function() {
        let result = some_function("input");
        assert_eq!(result, "expected output");
    }

    #[tokio::test]
    async fn test_async_function() {
        let result = async_function().await;
        assert!(result.is_ok());
    }
}
```

Run with:
```bash
cargo test
```

### Integration Testing

Test the full agent with:
```bash
cargo run --release
# Then use it interactively
```

## Performance Optimization

### Message Compaction

The agent automatically compacts history when it exceeds 40 messages. To adjust:

**In memory.rs:**
```rust
pub async fn smart_compact(messages: &[Value], ...) -> (Vec<Value>, bool) {
    if messages.len() <= 50 {  // Change this threshold
        return (messages.to_vec(), false);
    }
```

### Timeout Values

Adjust timeouts in `tools.rs`:

```rust
// Terminal command timeout
timeout(Duration::from_secs(30), output).await  // Increase from 15

// Webpage fetch timeout
timeout(Duration::from_secs(20), client.get(url).send()).await  // From 10
```

## Dependencies

Key dependencies in `Cargo.toml`:

| Crate | Purpose |
|-------|---------|
| `reqwest` | HTTP client for API calls |
| `serde_json` | JSON serialization |
| `tokio` | Async runtime |
| `scraper` | HTML parsing |
| `colored` | Terminal colors |
| `rustyline` | Interactive CLI |
| `uuid` | Session ID generation |
| `dotenv` | Environment variables |
| `chrono` | Timestamps |
| `shell-words` | Shell command parsing |
| `urlencoding` | URL encoding |

To add a new dependency:
```bash
cargo add new-crate-name
# or
cargo add new-crate-name@version
```

## Common Issues & Solutions

### Build Failures

1. **Missing dependencies**: Run `cargo update && cargo build`
2. **Rust version**: Ensure `rustc --version` is recent (1.70+)
3. **Platform issues**: Some tools may behave differently on Windows

### Runtime Errors

1. **API authentication**: Check `.env` file and API key validity
2. **Network timeouts**: Increase timeout values or check connectivity
3. **Tool execution errors**: Check tool implementation and parameters

### Performance Issues

1. **Slow message processing**: Implement smarter compaction
2. **High memory usage**: Sessions are fully loaded into memory; consider pagination
3. **API rate limits**: Implement request throttling if needed

## Debugging

### Enable Debug Output

Add debug prints:
```rust
eprintln!("DEBUG: {:?}", variable);
```

Run with:
```bash
cargo run 2>&1 | grep DEBUG
```

### Check API Requests/Responses

Add logging in `agent.rs`:
```rust
eprintln!("Request: {}", serde_json::to_string_pretty(&request_body)?);
let response = self.call_api(&request_body).await?;
eprintln!("Response: {}", serde_json::to_string_pretty(&response)?);
```

### Test Tool Execution

Create a test script:
```bash
#!/bin/bash
cargo run --example test_tools
```

## Contributing Guidelines

1. **Code Style**: Run `cargo fmt` before committing
2. **Linting**: Run `cargo clippy` and fix warnings
3. **Testing**: Add tests for new functionality
4. **Documentation**: Update README and relevant docs
5. **Commits**: Use clear, descriptive commit messages

## Future Enhancement Ideas

1. **Streaming Responses**: Use SSE or WebSockets for real-time output
2. **Parallel Tool Execution**: Execute multiple tools simultaneously
3. **Custom Tool Plugins**: Allow loading external tool libraries
4. **Multi-Model Support**: Switch between different AI models
5. **Advanced Memory**: Use vector embeddings for semantic search
6. **Web UI**: Create a web dashboard
7. **Session Export**: Save sessions as Markdown or PDF
8. **Multi-User Support**: Session sharing and collaboration
9. **Tool Scheduling**: Schedule recurring tool executions
10. **Feedback Loop**: Learn from user feedback to improve responses

## Resources

- [Rust Book](https://doc.rust-lang.org/book/)
- [Tokio Documentation](https://tokio.rs/)
- [OpenAI API Docs](https://platform.openai.com/docs/api-reference)
- [Serde Documentation](https://serde.rs/)
- [Reqwest Documentation](https://docs.rs/reqwest/)

## Support & Contact

For issues, questions, or suggestions:
1. Check existing documentation
2. Review code comments
3. Open an issue on GitHub
4. Create a discussion for feature requests
