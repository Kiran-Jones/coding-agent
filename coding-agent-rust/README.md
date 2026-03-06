# Coding Agent - Rust CLI

A powerful Rust-based CLI application that implements an autonomous coding agent with tool-calling capabilities. The agent can execute shell commands, manipulate files, search the web, and more.

## Features

- **Agentic Loop**: Autonomous agent that can call tools and take actions
- **8 Built-in Tools**:
  - `run_terminal_command` - Execute shell commands with safety checks
  - `write_file` - Create/write files with automatic directory creation
  - `read_file` - Read files with line numbering and size limits
  - `replace_text_in_file` - Find and replace text in files
  - `list_directory` - List directory contents (filtered)
  - `web_search` - DuckDuckGo search with 5 results
  - `read_webpage` - Fetch and parse webpages
  - `run_git_command` - Execute git commands safely
- **Session Management**: Save and load conversation sessions
- **Smart Context Compaction**: Automatic message history summarization for token efficiency
- **OpenAI-Compatible API**: Uses OpenAI chat completions format
- **Colored Output**: Terminal colors for better UX
- **Interactive CLI**: Line-by-line input with history using rustyline

## Architecture

### Module Structure

- **main.rs** - CLI loop, slash command routing, colored output
- **agent.rs** - CodingAgent struct, agentic loop, API calls
- **tools.rs** - Tool implementations and OpenAI schema definitions
- **session.rs** - Session save/load/list to .sessions/ directory
- **memory.rs** - Context compaction and summarization

## Setup

### Prerequisites

- Rust 1.70+ (install from https://rustup.rs/)

### Installation

1. Clone the repository:
```bash
git clone <repo-url>
cd coding-agent-rust
```

2. Copy the environment template:
```bash
cp .env.example .env
```

3. Configure your API credentials in `.env`:
```env
API_KEY=your-api-key
ENDPOINT_URL=https://your-api-endpoint/v1/chat/completions
```

The default model is `anthropic.claude-haiku-4-5-20251001` which is Claude 3.5 Haiku via Anthropic's API with OpenAI-compatible chat completions format.

### Building

```bash
# Build the project
cargo build --release

# Run directly
cargo run
```

## Usage

### Starting the Agent

```bash
cargo run
```

Or after building:
```bash
./target/release/coding-agent
```

### Commands

Once the agent is running, you have access to these slash commands:

| Command | Description |
|---------|-------------|
| `/sessions` | List all saved sessions |
| `/load <id>` | Load a previous session |
| `/new` | Start a new session |
| `/quit`, `/exit` | Exit the agent |
| `/help` | Show available commands |

### Regular Input

Simply type your request and press Enter. The agent will:
1. Create a new session if one doesn't exist
2. Process your request through the agentic loop
3. Call tools as needed (up to 35 steps by default)
4. Provide a final response
5. Auto-save the session

### Examples

```
Agent> Create a Python script that prints "Hello, World!"
🔧 Calling tool: write_file
File written successfully to hello.py

🔧 Calling tool: run_terminal_command
Hello, World!

█ I've successfully created a Python script that prints "Hello, World!" 
█ and executed it. The script was saved to hello.py and the output 
█ confirms it works correctly.
█
```

## Sessions

Sessions are automatically saved to the `.sessions/` directory as JSON files. Session IDs follow the format:
```
YYYYMMDD_HHMMSS_{6-char-random-hex}
```

Sessions include:
- Full conversation history
- Tool calls and results
- Metadata (creation time, last update)
- Session title

## Safety Features

### Dangerous Command Detection

Commands containing dangerous keywords are flagged:
- `rm`, `sudo`, `dd`, `mkfs`, `format`, `shutdown`, `reboot`, `poweroff`

The agent will prompt for confirmation before executing.

### Git Command Safety

- Rejects shell metacharacters (`;`, `&&`, `|`)
- Only allows proper git subcommands
- 15-second timeout protection

### File Operations

- Parent directories created automatically
- Line count limits (max 2000 lines per file)
- Text file validation

## Performance & Optimization

### Context Window Management

The agent implements smart context compaction:
- Keeps system prompt and last 15 messages in active memory
- Summarizes older messages when history exceeds 40 messages
- Uses temperature 0.3 for consistent summarization
- Preserves full history for session persistence

### Timeout Protection

All operations have timeouts:
- Terminal commands: 15 seconds
- Webpage requests: 10 seconds
- Git operations: 15 seconds

## Configuration

### API Endpoint

The endpoint should support OpenAI-compatible chat completions:
```
POST /v1/chat/completions
Header: Authorization: Bearer {API_KEY}
Content-Type: application/json
```

### Request Format

```json
{
  "model": "anthropic.claude-haiku-4-5-20251001",
  "messages": [...],
  "tools": [...],
  "tool_choice": "auto",
  "max_tokens": 4096
}
```

## Project Structure

```
coding-agent-rust/
├── Cargo.toml
├── .env.example
├── src/
│   ├── main.rs          # CLI loop
│   ├── lib.rs           # Module exports
│   ├── agent.rs         # Agent logic
│   ├── tools.rs         # Tool implementations
│   ├── session.rs       # Session management
│   └── memory.rs        # Compaction/summarization
├── .sessions/           # Session storage (auto-created)
└── README.md
```

## Dependencies

Key dependencies:
- **reqwest** - HTTP client for API calls
- **serde/serde_json** - JSON serialization
- **tokio** - Async runtime
- **scraper** - HTML parsing for web scraping
- **colored** - Terminal colors
- **rustyline** - Interactive line editing
- **uuid** - Session ID generation
- **dotenv** - Environment variable loading
- **chrono** - Timestamp handling
- **shell-words** - Shell command parsing

## Development

### Building from source

```bash
# Debug build
cargo build

# Release build (optimized)
cargo build --release

# Run tests
cargo test

# Check code
cargo check

# Format code
cargo fmt

# Lint
cargo clippy
```

## Troubleshooting

### API Key/Endpoint errors
- Verify `.env` file exists
- Check `API_KEY` and `ENDPOINT_URL` are set correctly
- Test with `curl`:
```bash
curl -X POST $ENDPOINT_URL \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model": "anthropic.claude-haiku-4-5-20251001", "messages": [{"role": "user", "content": "Hi"}]}'
```

### Timeout issues
- Check network connectivity
- Verify API endpoint is responsive
- Increase timeout values in code if needed

### Session loading issues
- Check `.sessions/` directory exists
- Verify session JSON files are valid
- Use `/sessions` to list available sessions

## Limitations

- Maximum file size for `read_file`: 2000 lines
- Webpage parsing: 15000 characters max
- Search results: Top 5 from DuckDuckGo
- Default agent loop: 35 steps (ask for 10 more)
- Tool execution: Sequential (no parallelization)

## Future Enhancements

- [ ] Parallel tool execution
- [ ] Streaming responses
- [ ] Custom tool plugins
- [ ] Multi-model support
- [ ] Advanced session filtering
- [ ] Conversation export (Markdown, PDF)
- [ ] Web UI dashboard
- [ ] Multi-turn planning mode

## License

MIT

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## Support

For issues or questions:
1. Check existing issues
2. Review the troubleshooting section
3. Check API endpoint documentation
4. Verify environment configuration
