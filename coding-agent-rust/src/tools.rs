use serde_json::{json, Value};
use std::fs;
use std::path::Path;
use std::process::Command;
use std::time::Duration;
use tokio::time::timeout;
use scraper::Html;

const DANGEROUS_KEYWORDS: &[&str] = &["rm", "sudo", "dd", "mkfs", "format", "shutdown", "reboot", "poweroff"];

/// Get the OpenAI-format tool schemas
pub fn get_tools_schema() -> Value {
    json!([
        {
            "type": "function",
            "function": {
                "name": "run_terminal_command",
                "description": "Run a shell command with 15s timeout. Checks for dangerous keywords and prompts for confirmation if found.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The shell command to execute"
                        }
                    },
                    "required": ["command"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "write_file",
                "description": "Create parent directories if needed and write content to a file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "The path where to write the file"
                        },
                        "content": {
                            "type": "string",
                            "description": "The content to write to the file"
                        }
                    },
                    "required": ["file_path", "content"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read a file and return its contents with line numbers",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "The path to the file to read"
                        }
                    },
                    "required": ["file_path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "replace_text_in_file",
                "description": "Replace all occurrences of old_text with new_text in a file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "The path to the file"
                        },
                        "old_text": {
                            "type": "string",
                            "description": "The text to find and replace"
                        },
                        "new_text": {
                            "type": "string",
                            "description": "The replacement text"
                        }
                    },
                    "required": ["file_path", "old_text", "new_text"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_directory",
                "description": "List directory contents, filtering out dotfiles and __pycache__",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "The directory path (default: '.')"
                        }
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "web_search",
                "description": "Search DuckDuckGo for the given query and return top 5 results",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "The search query"
                        }
                    },
                    "required": ["query"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "read_webpage",
                "description": "Fetch a webpage, parse HTML, and return clean text (up to 15000 chars)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "url": {
                            "type": "string",
                            "description": "The URL to fetch"
                        }
                    },
                    "required": ["url"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "run_git_command",
                "description": "Run a git command with validation and 15s timeout",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The git command (with or without 'git ' prefix)"
                        }
                    },
                    "required": ["command"]
                }
            }
        }
    ])
}

/// Execute a tool with the given name and arguments
pub async fn execute_tool(name: &str, args: &Value) -> String {
    match name {
        "run_terminal_command" => run_terminal_command(args).await,
        "write_file" => write_file(args),
        "read_file" => read_file(args),
        "replace_text_in_file" => replace_text_in_file(args),
        "list_directory" => list_directory(args),
        "web_search" => web_search(args).await,
        "read_webpage" => read_webpage(args).await,
        "run_git_command" => run_git_command(args).await,
        _ => format!("Unknown tool: {}", name),
    }
}

async fn run_terminal_command(args: &Value) -> String {
    let command = match args.get("command").and_then(|v| v.as_str()) {
        Some(cmd) => cmd,
        None => return "Error: 'command' parameter is required".to_string(),
    };

    // Check for dangerous keywords
    for keyword in DANGEROUS_KEYWORDS {
        if command.contains(keyword) {
            println!("\n⚠️  Warning: Command contains '{}' which is potentially dangerous.", keyword);
            println!("Command: {}", command);
            print!("Proceed? (y/N): ");
            std::io::Write::flush(&mut std::io::stdout()).ok();

            let mut input = String::new();
            if std::io::stdin().read_line(&mut input).is_err() {
                return "Command cancelled by user".to_string();
            }

            if !input.trim().eq_ignore_ascii_case("y") {
                return "Command cancelled by user".to_string();
            }
        }
    }

    // Execute with timeout
    let output = tokio::task::spawn_blocking({
        let command = command.to_string();
        move || {
            Command::new("sh")
                .arg("-c")
                .arg(&command)
                .output()
        }
    });

    match timeout(Duration::from_secs(15), output).await {
        Ok(Ok(output)) => {
            if output.status.success() {
                String::from_utf8_lossy(&output.stdout).to_string()
            } else {
                String::from_utf8_lossy(&output.stderr).to_string()
            }
        }
        Ok(Err(e)) => format!("Error spawning command: {}", e),
        Err(_) => "Command timed out after 15 seconds".to_string(),
    }
}

fn write_file(args: &Value) -> String {
    let file_path = match args.get("file_path").and_then(|v| v.as_str()) {
        Some(path) => path,
        None => return "Error: 'file_path' parameter is required".to_string(),
    };

    let content = match args.get("content").and_then(|v| v.as_str()) {
        Some(content) => content,
        None => return "Error: 'content' parameter is required".to_string(),
    };

    // Create parent directories
    if let Some(parent) = Path::new(file_path).parent() {
        if !parent.as_os_str().is_empty() {
            if let Err(e) = fs::create_dir_all(parent) {
                return format!("Error creating directories: {}", e);
            }
        }
    }

    // Write file
    match fs::write(file_path, content) {
        Ok(_) => format!("File written successfully to {}", file_path),
        Err(e) => format!("Error writing file: {}", e),
    }
}

fn read_file(args: &Value) -> String {
    let file_path = match args.get("file_path").and_then(|v| v.as_str()) {
        Some(path) => path,
        None => return "Error: 'file_path' parameter is required".to_string(),
    };

    let content = match fs::read_to_string(file_path) {
        Ok(content) => content,
        Err(e) => return format!("Error reading file: {}", e),
    };

    let lines: Vec<&str> = content.lines().collect();
    if lines.len() > 2000 {
        return format!(
            "Error: File has {} lines, exceeds 2000 line limit",
            lines.len()
        );
    }

    let formatted: Vec<String> = lines
        .iter()
        .enumerate()
        .map(|(i, line)| format!("{:4} | {}", i + 1, line))
        .collect();

    formatted.join("\n")
}

fn replace_text_in_file(args: &Value) -> String {
    let file_path = match args.get("file_path").and_then(|v| v.as_str()) {
        Some(path) => path,
        None => return "Error: 'file_path' parameter is required".to_string(),
    };

    let old_text = match args.get("old_text").and_then(|v| v.as_str()) {
        Some(text) => text,
        None => return "Error: 'old_text' parameter is required".to_string(),
    };

    let new_text = match args.get("new_text").and_then(|v| v.as_str()) {
        Some(text) => text,
        None => return "Error: 'new_text' parameter is required".to_string(),
    };

    let mut content = match fs::read_to_string(file_path) {
        Ok(content) => content,
        Err(e) => return format!("Error reading file: {}", e),
    };

    if !content.contains(old_text) {
        return "Error: old_text not found in file".to_string();
    }

    content = content.replace(old_text, new_text);

    match fs::write(file_path, content) {
        Ok(_) => "File updated successfully".to_string(),
        Err(e) => format!("Error writing file: {}", e),
    }
}

fn list_directory(args: &Value) -> String {
    let path = args
        .get("path")
        .and_then(|v| v.as_str())
        .unwrap_or(".");

    match fs::read_dir(path) {
        Ok(entries) => {
            let mut items: Vec<String> = entries
                .filter_map(|entry| {
                    entry.ok().and_then(|e| {
                        let name = e.file_name();
                        let name_str = name.to_string_lossy();

                        // Filter out dotfiles and __pycache__
                        if name_str.starts_with('.') || name_str == "__pycache__" {
                            return None;
                        }

                        Some(name_str.to_string())
                    })
                })
                .collect();

            items.sort();
            items.join("\n")
        }
        Err(e) => format!("Error reading directory: {}", e),
    }
}

async fn web_search(args: &Value) -> String {
    let query = match args.get("query").and_then(|v| v.as_str()) {
        Some(q) => q,
        None => return "Error: 'query' parameter is required".to_string(),
    };

    let encoded_query = urlencoding::encode(query);
    let url = format!("https://html.duckduckgo.com/html/?q={}", encoded_query);

    let client = reqwest::Client::new();
    match client.get(&url).send().await {
        Ok(response) => match response.text().await {
            Ok(html) => parse_duckduckgo_results(&html),
            Err(e) => format!("Error reading response: {}", e),
        },
        Err(e) => format!("Error making request: {}", e),
    }
}

fn parse_duckduckgo_results(html: &str) -> String {
    let document = Html::parse_document(html);
    let mut results = Vec::new();

    // DuckDuckGo results are in divs with class "result__body"
    let selector = match scraper::Selector::parse("div.result") {
        Ok(sel) => sel,
        Err(_) => {
            return "Error parsing search results".to_string();
        }
    };

    for (idx, element) in document.select(&selector).enumerate() {
        if idx >= 5 {
            break;
        }

        let title_selector = match scraper::Selector::parse("h2 > a") {
            Ok(sel) => sel,
            Err(_) => continue,
        };

        let snippet_selector = match scraper::Selector::parse(".result__snippet") {
            Ok(sel) => sel,
            Err(_) => continue,
        };

        let title = element
            .select(&title_selector)
            .next()
            .and_then(|el| el.value().attr("title"))
            .unwrap_or("");

        let url = element
            .select(&title_selector)
            .next()
            .and_then(|el| el.value().attr("href"))
            .unwrap_or("");

        let snippet = element
            .select(&snippet_selector)
            .next()
            .map(|el| el.inner_html())
            .unwrap_or_default();

        // Remove HTML tags from snippet
        let snippet_text = Html::parse_document(&snippet)
            .root_element()
            .text()
            .collect::<Vec<_>>()
            .join(" ");

        results.push(format!(
            "Title: {}\nURL: {}\nSnippet: {}\n",
            title, url, snippet_text
        ));
    }

    if results.is_empty() {
        "No search results found".to_string()
    } else {
        results.join("\n---\n")
    }
}

async fn read_webpage(args: &Value) -> String {
    let url = match args.get("url").and_then(|v| v.as_str()) {
        Some(u) => u,
        None => return "Error: 'url' parameter is required".to_string(),
    };

    let client = reqwest::Client::new();
    match timeout(
        Duration::from_secs(10),
        client.get(url).send(),
    )
    .await
    {
        Ok(Ok(response)) => match response.text().await {
            Ok(html) => {
                let document = Html::parse_document(&html);
                
                // Remove script, style, nav, footer, header elements
                let mut text_parts: Vec<String> = Vec::new();
                
                for element in document.root_element().descendants() {
                    if let scraper::node::Node::Element(e) = element.value() {
                        let name = e.name();
                        if name == "script" || name == "style" || name == "nav" 
                            || name == "footer" || name == "header" {
                            continue;
                        }
                    }
                }

                // Extract text
                let text = document
                    .root_element()
                    .text()
                    .collect::<Vec<_>>()
                    .join(" ");

                // Clean up whitespace
                let cleaned = text
                    .split_whitespace()
                    .collect::<Vec<_>>()
                    .join(" ");

                // Truncate to 15000 chars
                if cleaned.len() > 15000 {
                    cleaned[..15000].to_string()
                } else {
                    cleaned
                }
            }
            Err(e) => format!("Error reading response: {}", e),
        },
        Ok(Err(e)) => format!("Error making request: {}", e),
        Err(_) => "Request timed out after 10 seconds".to_string(),
    }
}

async fn run_git_command(args: &Value) -> String {
    let command = match args.get("command").and_then(|v| v.as_str()) {
        Some(cmd) => cmd,
        None => return "Error: 'command' parameter is required".to_string(),
    };

    // Check for shell metacharacters
    if command.contains(';') || command.contains("&&") || command.contains('|') {
        return "Error: Shell metacharacters (;, &&, |) are not allowed".to_string();
    }

    // Strip leading "git " if present
    let cmd_clean = if command.starts_with("git ") {
        &command[4..]
    } else {
        command
    };

    // Parse arguments
    let args_vec = match shell_words::split(cmd_clean) {
        Ok(args) => args,
        Err(e) => return format!("Error parsing command: {}", e),
    };

    if args_vec.is_empty() {
        return "Error: No git command provided".to_string();
    }

    // Execute git command
    let output = tokio::task::spawn_blocking({
        let args = args_vec.clone();
        move || {
            Command::new("git")
                .args(&args)
                .output()
        }
    });

    match timeout(Duration::from_secs(15), output).await {
        Ok(Ok(output)) => {
            if output.status.success() {
                String::from_utf8_lossy(&output.stdout).to_string()
            } else {
                String::from_utf8_lossy(&output.stderr).to_string()
            }
        }
        Ok(Err(e)) => format!("Error spawning command: {}", e),
        Err(_) => "Command timed out after 15 seconds".to_string(),
    }
}
