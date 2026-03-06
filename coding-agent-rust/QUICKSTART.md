# Quick Start Guide

Get up and running with the Coding Agent in minutes!

## Installation (5 minutes)

### 1. Install Rust
If you don't have Rust installed:
```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source $HOME/.cargo/env
```

### 2. Clone/Setup the Project
```bash
cd coding-agent-rust
```

### 3. Configure API Credentials
```bash
cp .env.example .env
# Edit .env with your API key and endpoint URL
nano .env
```

Example .env (using Anthropic Claude):
```env
API_KEY=sk-ant-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
ENDPOINT_URL=https://api.anthropic.com/v1/messages
```

Or for any OpenAI-compatible provider:
```env
API_KEY=your-api-key
ENDPOINT_URL=https://your-provider.com/v1/chat/completions
```

### 4. Build and Run
```bash
# First build (will take a minute or two)
cargo build --release

# Run the agent
cargo run --release
```

Or if you prefer shorter dev cycle:
```bash
cargo run  # Runs in debug mode
```

## First Steps

Once the agent is running, try these simple prompts:

### 1. Create a File
```
Agent> Create a file called test.txt with the content "Hello, World!"
```

The agent will:
- Call the `write_file` tool
- Show you the result
- Save the session automatically

### 2. List Files
```
Agent> List the current directory
```

The agent will:
- Call the `list_directory` tool
- Show you the contents

### 3. Run a Command
```
Agent> Show me the current date and time
```

The agent will:
- Call the `run_terminal_command` tool
- Execute `date` or similar
- Show the output

### 4. Search the Web
```
Agent> Search for the latest Rust release notes
```

The agent will:
- Call the `web_search` tool
- Return top 5 results

### 5. Create a Program
```
Agent> Create a Python script that calculates fibonacci numbers
```

The agent will:
- Write the Python file
- Run it to test it
- Show you the results

## Commands

In the interactive CLI, use these slash commands:

| Command | Example |
|---------|---------|
| `/new` | Start a fresh conversation |
| `/sessions` | List saved sessions |
| `/load ID` | Load a previous session (e.g., `/load 20240101_120000_abc123`) |
| `/help` | Show all commands |
| `/quit` | Exit the program |

## Tips & Tricks

### 1. Give Clear Instructions
Instead of:
```
Agent> write a script
```

Try:
```
Agent> Create a Python script that accepts a name and prints a greeting
```

### 2. Ask for Verification
The agent can verify its work:
```
Agent> Create a test.txt file with "Hello" and then read it back to confirm
```

### 3. Use Sessions
```
Agent> /sessions                          # See all sessions
Agent> /load 20240115_143022_abc456       # Resume a session
```

### 4. Check Previous Work
Sessions are saved in `.sessions/` directory as JSON files. You can review them to see what the agent did.

### 5. Multi-Step Tasks
The agent can do complex tasks with multiple steps:
```
Agent> 
1. Create a file called numbers.txt
2. Write the numbers 1-10 to it
3. Read it back and count how many lines are there
4. Tell me the result
```

## Troubleshooting

### Build Fails
```bash
# Clean and rebuild
cargo clean
cargo build --release
```

### API Key Error
```
Error: Failed to call API: Invalid API key
```
- Check `.env` file exists
- Verify API_KEY is not empty
- Test API key with curl:
```bash
curl -X POST "$ENDPOINT_URL" \
  -H "Authorization: Bearer $API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4", "messages":[{"role":"user","content":"hi"}]}'
```

### Sessions Not Loading
- Sessions are in `.sessions/` directory
- Use `/sessions` to list available ones
- Use exact ID from the list: `/load ID_HERE`

### Slow Build First Time
This is normal! Dependencies are being compiled. Subsequent builds are much faster.

## Understanding the Agent

### How It Works

1. **You**: Type a request
2. **Agent**: Calls OpenAI API to get response + tool calls
3. **Tools**: Executes tools (write files, run commands, etc.)
4. **Loop**: Uses tool results to make next decision
5. **Repeat**: Until agent decides it's done (or hits 35-step limit)
6. **Response**: Agent gives you final answer
7. **Save**: Session automatically saved

### Tool Descriptions

| Tool | What It Does | Example |
|------|------------|---------|
| `write_file` | Create/update files | Create hello.py with Python code |
| `read_file` | Read file contents | Read hello.py to show code |
| `run_terminal_command` | Execute shell commands | Run `python hello.py` |
| `replace_text_in_file` | Find and replace text | Change function name in file |
| `list_directory` | Show folder contents | List files in current directory |
| `web_search` | Search DuckDuckGo | Find Rust documentation |
| `read_webpage` | Read webpage content | Read article from URL |
| `run_git_command` | Execute git commands | Commit changes |

## Next Steps

- Explore the [README.md](README.md) for detailed documentation
- Check `.sessions/` to see saved conversations
- Try complex tasks and see how the agent handles them
- Customize the agent by modifying `src/agent.rs`

## Common Tasks

### Task: Generate Code
```
Agent> Create a Rust program that reads a file and counts how many lines it has
```

### Task: Process Data
```
Agent> 
1. Create a file with this CSV data: name,age,city
   Alice,30,NYC
   Bob,25,LA
2. Create a Python script to read it
3. Run the script to show the data
```

### Task: Web Research
```
Agent> Search the web for "Rust async patterns" and summarize the top 3 results
```

### Task: File Management
```
Agent> 
1. Create a backup directory
2. Copy all .txt files there
3. List what we copied
```

## Support

- Read the [README.md](README.md) for complete documentation
- Check [src/](src/) directory for source code
- Review saved sessions in `.sessions/` for examples

Happy coding! 🚀
