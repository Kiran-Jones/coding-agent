use crate::memory::smart_compact;
use crate::tools::{execute_tool, get_tools_schema};
use serde_json::{json, Value};

pub struct CodingAgent {
    pub messages: Vec<Value>,
    pub full_history: Vec<Value>,
    api_key: String,
    endpoint_url: String,
}

const SYSTEM_PROMPT: &str = "You are a coding agent. You have tools to write files and run terminal commands. Do NOT output raw code blocks for me to run. Use your 'write_file' tool to create the python scripts, and use your 'run_terminal_command' tool to execute and test them. When you have successfully completed the task and verified it works, just reply with a friendly message explaining what you did.";

impl CodingAgent {
    pub fn new(api_key: String, endpoint_url: String) -> Self {
        let system_msg = json!({
            "role": "system",
            "content": SYSTEM_PROMPT
        });

        CodingAgent {
            messages: vec![system_msg.clone()],
            full_history: vec![system_msg],
            api_key,
            endpoint_url,
        }
    }

    /// Reset agent to initial state
    pub fn reset(&mut self) {
        let system_msg = json!({
            "role": "system",
            "content": SYSTEM_PROMPT
        });
        self.messages = vec![system_msg.clone()];
        self.full_history = vec![system_msg];
    }

    /// Add a user message
    pub fn add_user_message(&mut self, content: &str) {
        let msg = json!({
            "role": "user",
            "content": content
        });
        self.messages.push(msg.clone());
        self.full_history.push(msg);
    }

    /// Run one agent step
    /// Returns: (response_text, tool_used)
    pub async fn run_step(&mut self) -> Result<(String, bool), String> {
        // Compact messages if needed
        let (compacted_messages, did_compact) = smart_compact(&self.messages, &self.api_key, &self.endpoint_url).await;
        if did_compact {
            println!("\n💾 Context window compacted to manage token usage\n");
            self.messages = compacted_messages;
        }

        // Call API
        let request_body = json!({
            "model": "anthropic.claude-haiku-4-5-20251001",
            "messages": self.messages,
            "tools": get_tools_schema(),
            "tool_choice": "auto",
            "max_tokens": 4096
        });

        let response = self.call_api(&request_body).await?;

        // Extract assistant message
        let assistant_message = response
            .get("choices")
            .and_then(|c| c.get(0))
            .and_then(|c| c.get("message"))
            .ok_or("Invalid response format")?
            .clone();

        // Append assistant message to both vectors
        self.messages.push(assistant_message.clone());
        self.full_history.push(assistant_message.clone());

        // Check for tool calls
        if let Some(tool_calls) = assistant_message.get("tool_calls").and_then(|t| t.as_array()) {
            if !tool_calls.is_empty() {
                // Execute each tool
                for tool_call in tool_calls {
                    let tool_use_id = tool_call
                        .get("id")
                        .and_then(|id| id.as_str())
                        .unwrap_or("unknown");

                    let tool_name = tool_call
                        .get("function")
                        .and_then(|f| f.get("name"))
                        .and_then(|n| n.as_str())
                        .unwrap_or("unknown");

                    let tool_input = tool_call
                        .get("function")
                        .and_then(|f| f.get("arguments"))
                        .cloned()
                        .unwrap_or(json!({}));

                    // Parse arguments if they're a string (JSON)
                    let tool_input = if let Value::String(s) = &tool_input {
                        serde_json::from_str(s).unwrap_or(json!({}))
                    } else {
                        tool_input
                    };

                    println!("\n🔧 Calling tool: {}", tool_name);

                    // Execute tool
                    let result = execute_tool(tool_name, &tool_input).await;

                    // Append tool result to both vectors
                    let tool_result_msg = json!({
                        "role": "user",
                        "content": result
                    });

                    self.messages.push(tool_result_msg.clone());
                    self.full_history.push(tool_result_msg);
                }

                return Ok(("".to_string(), true));
            }
        }

        // Extract text content
        let content = assistant_message
            .get("content")
            .and_then(|c| c.as_str())
            .unwrap_or("")
            .to_string();

        Ok((content, false))
    }

    async fn call_api(&self, request_body: &Value) -> Result<Value, String> {
        let client = reqwest::Client::new();

        let response = client
            .post(&self.endpoint_url)
            .header("Authorization", format!("Bearer {}", self.api_key))
            .header("Content-Type", "application/json")
            .json(request_body)
            .send()
            .await
            .map_err(|e| format!("Request failed: {}", e))?;

        if !response.status().is_success() {
            let status = response.status();
            let text = response
                .text()
                .await
                .unwrap_or_else(|_| "Unknown error".to_string());
            return Err(format!("API error {}: {}", status, text));
        }

        response
            .json::<Value>()
            .await
            .map_err(|e| format!("Failed to parse response: {}", e))
    }
}
