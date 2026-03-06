# memory_utils.py
import requests


def generate_summary(
    messages_to_summarize: list, api_key: str, endpoint_url: str, model: str
) -> str:
    """Helper utility to compress a chunk of messages."""
    chat_log = ""
    for msg in messages_to_summarize:
        role = msg.get("role", "unknown")

        # Handle assistant messages with tool calls
        if role == "assistant" and msg.get("tool_calls"):
            parts = []
            if msg.get("content"):
                parts.append(str(msg["content"])[:300])
            for tc in msg["tool_calls"]:
                func = tc.get("function", {})
                name = func.get("name", "unknown")
                args = func.get("arguments", "")[:200]
                parts.append(f"[Called {name}({args})]")
            content = " ".join(parts)
        else:
            content = str(msg.get("content", ""))[:500]

        chat_log += f"{role.upper()}: {content}\n\n"

    prompt = (
        "You are a technical summarizer. Compress the following chat log into a dense, "
        "bulleted summary of what has been done and the current state.\n\n"
        f"CHAT LOG:\n{chat_log}"
    )

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
    }

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        response = requests.post(
            endpoint_url, headers=headers, json=payload, timeout=30
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        return f"(Failed to generate summary: {str(e)})"


def smart_compact(messages: list, api_key: str, endpoint_url: str, model: str) -> tuple[list, bool]:
    """Safely compacts an array of LLM messages. Returns (new_messages, was_compacted)."""
    MAX_MESSAGES = 40
    KEEP_RECENT = 15

    if len(messages) <= MAX_MESSAGES:
        # Return the original messages, and False (no compaction happened)
        return messages, False

    system_prompt = messages[0]
    recent = messages[-KEEP_RECENT:]

    while recent and recent[0].get("role") not in ["user", "assistant"]:
        recent.pop(0)

    num_to_summarize = len(messages) - 1 - len(recent)
    if num_to_summarize <= 0:
        return messages, False

    to_summarize = messages[1 : 1 + num_to_summarize]
    summary_text = generate_summary(to_summarize, api_key, endpoint_url, model)

    summary_node = {
        "role": "system",
        "content": f"--- SUMMARY OF PREVIOUS ACTIONS ---\n{summary_text}\n-----------------------------------",
    }

    # Return the new messages, and True (compaction successful!)
    return [system_prompt, summary_node] + recent, True
