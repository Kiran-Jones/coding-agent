use serde_json::{json, Value};

/// Compacts message history by summarizing old messages
/// Returns (new_messages, did_compact)
pub async fn smart_compact(
    messages: &[Value],
    api_key: &str,
    endpoint_url: &str,
) -> (Vec<Value>, bool) {
    if messages.len() <= 40 {
        return (messages.to_vec(), false);
    }

    // Keep system prompt (first message) and last 15 messages
    let system_prompt = messages[0].clone();
    let recent_start = if messages.len() > 15 {
        messages.len() - 15
    } else {
        1
    };

    let mut recent = messages[recent_start..].to_vec();

    // Trim front of recent until it starts with user or assistant message
    while !recent.is_empty() {
        if let Some(role) = recent[0].get("role").and_then(|r| r.as_str()) {
            if role == "user" || role == "assistant" {
                break;
            }
        }
        recent.remove(0);
    }

    // Summarize messages between system prompt and recent
    let to_summarize = &messages[1..recent_start];
    
    let summary_text = generate_summary(to_summarize, api_key, endpoint_url).await;

    let summary_message = json!({
        "role": "assistant",
        "content": format!("[Previous conversation summarized]\n{}", summary_text)
    });

    let mut new_messages = vec![system_prompt];
    new_messages.push(summary_message);
    new_messages.extend(recent);

    (new_messages, true)
}

/// Generates a summary of messages using the API
async fn generate_summary(messages: &[Value], api_key: &str, endpoint_url: &str) -> String {
    // Format messages into a chat log
    let chat_log = format_messages_for_summary(messages);

    let summary_prompt = format!(
        "Below is a conversation between a user and an AI coding agent. \
         Summarize the key points, decisions made, and tools used in 2-3 sentences:\n\n{}",
        chat_log
    );

    let request_body = json!({
        "model": "anthropic.claude-haiku-4-5-20251001",
        "messages": [
            {
                "role": "user",
                "content": summary_prompt
            }
        ],
        "temperature": 0.3,
        "max_tokens": 300
    });

    match make_api_call(api_key, endpoint_url, &request_body).await {
        Ok(response) => {
            if let Some(content) = response
                .get("choices")
                .and_then(|c| c.get(0))
                .and_then(|c| c.get("message"))
                .and_then(|m| m.get("content"))
                .and_then(|c| c.as_str())
            {
                content.to_string()
            } else {
                "Summary generation failed".to_string()
            }
        }
        Err(e) => format!("Error generating summary: {}", e),
    }
}

fn format_messages_for_summary(messages: &[Value]) -> String {
    let mut result = String::new();

    for msg in messages {
        if let Some(role) = msg.get("role").and_then(|r| r.as_str()) {
            result.push_str(&format!("{}: ", role.to_uppercase()));

            if let Some(content) = msg.get("content").and_then(|c| c.as_str()) {
                // Truncate content
                let truncated = if content.len() > 300 {
                    &content[..300]
                } else {
                    content
                };
                result.push_str(truncated);
            }

            // Check for tool_calls
            if let Some(tool_calls) = msg.get("tool_calls").and_then(|t| t.as_array()) {
                for tool_call in tool_calls {
                    if let Some(tool_name) = tool_call.get("function").and_then(|f| f.get("name")).and_then(|n| n.as_str()) {
                        result.push_str(&format!(" [Called {}]", tool_name));
                    }
                }
            }

            result.push_str("\n");
        }
    }

    result
}

/// Make an API call to the endpoint
async fn make_api_call(
    api_key: &str,
    endpoint_url: &str,
    request_body: &Value,
) -> Result<Value, String> {
    let client = reqwest::Client::new();

    match client
        .post(endpoint_url)
        .header("Authorization", format!("Bearer {}", api_key))
        .header("Content-Type", "application/json")
        .json(request_body)
        .send()
        .await
    {
        Ok(response) => match response.status().is_success() {
            true => match response.json::<Value>().await {
                Ok(json) => Ok(json),
                Err(e) => Err(format!("Failed to parse JSON: {}", e)),
            },
            false => {
                let status = response.status();
                let text = response.text().await.unwrap_or_default();
                Err(format!("API error {}: {}", status, text))
            }
        },
        Err(e) => Err(format!("Request failed: {}", e)),
    }
}
