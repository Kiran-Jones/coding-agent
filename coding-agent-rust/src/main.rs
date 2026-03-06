use colored::*;
use dotenv::dotenv;
use rustyline::DefaultEditor;
use std::env;

mod agent;
mod memory;
mod session;
mod tools;

use agent::CodingAgent;
use session::{SessionManager, SessionInfo};

#[tokio::main]
async fn main() -> Result<(), Box<dyn std::error::Error>> {
    dotenv().ok();

    let api_key = env::var("API_KEY").expect("API_KEY not found in .env");
    let endpoint_url = env::var("ENDPOINT_URL").expect("ENDPOINT_URL not found in .env");

    println!("{}", "═".repeat(60).cyan());
    println!(
        "{}",
        "  Welcome to the Coding Agent CLI".cyan().bold()
    );
    println!("{}", "═".repeat(60).cyan());
    println!(
        "{}",
        "Type /help to see available commands, or start typing your request.".italic()
    );
    println!();

    let session_manager = SessionManager::new()?;
    let mut agent = CodingAgent::new(api_key, endpoint_url);
    let mut rl = DefaultEditor::new()?;
    
    let mut session_id: Option<String> = None;
    let mut session_title = "Untitled".to_string();

    loop {
        let prompt = if session_id.is_some() {
            format!("{}> ", "Agent".cyan())
        } else {
            format!("{}> ", "Agent".yellow())
        };

        match rl.readline(&prompt) {
            Ok(line) => {
                let input = line.trim();

                if input.is_empty() {
                    continue;
                }

                if input.starts_with('/') {
                    match handle_slash_command(input, &session_manager, &mut agent, &mut session_id, &mut session_title) {
                        Ok((new_session_id, new_title)) => {
                            session_id = new_session_id;
                            if let Some(ref id) = session_id {
                                session_title = new_title;
                                println!("{} Session: {}", "✓".green(), id.bright_black());
                            }
                        }
                        Err(e) => println!("{} {}", "✗".red(), e),
                    }
                } else {
                    // User input
                    if session_id.is_none() {
                        // Create a new session
                        session_id = Some(session_manager.create_session(
                            agent.full_history.clone(),
                            "Untitled".to_string(),
                        ));
                    }

                    agent.add_user_message(input);

                    // Run agent loop
                    run_agent_loop(&mut agent, &session_manager, &session_id, &session_title)
                        .await;

                    // Save session
                    if let Some(ref id) = session_id {
                        let _ = session_manager.save_session(
                            id,
                            &session_title,
                            agent.full_history.clone(),
                        );
                    }
                }
            }
            Err(rustyline::error::ReadlineError::Interrupted) => {
                // Ctrl+C
                if session_id.is_some() {
                    println!("\n{} Session saved.", "✓".green());
                }
                break;
            }
            Err(rustyline::error::ReadlineError::Eof) => {
                // Ctrl+D
                if session_id.is_some() {
                    println!("\n{} Session saved.", "✓".green());
                }
                break;
            }
            Err(e) => {
                println!("Error: {}", e);
                break;
            }
        }
    }

    Ok(())
}

fn handle_slash_command(
    input: &str,
    session_manager: &SessionManager,
    agent: &mut CodingAgent,
    current_session_id: &mut Option<String>,
    current_session_title: &mut String,
) -> Result<(Option<String>, String), String> {
    let parts: Vec<&str> = input.split_whitespace().collect();
    let command = parts.get(0).map(|s| *s).unwrap_or("");

    match command {
        "/sessions" => {
            let sessions = session_manager
                .list_sessions()
                .map_err(|e| e.to_string())?;

            if sessions.is_empty() {
                println!("No sessions found.");
            } else {
                println!("{}", "ID | Title | Updated At".cyan().bold());
                println!("{}", "─".repeat(80).cyan());
                for session in sessions {
                    println!(
                        "{} | {} | {}",
                        session.id.bright_black(),
                        session.title,
                        session.updated_at.bright_black()
                    );
                }
            }
            Ok((current_session_id.clone(), current_session_title.clone()))
        }
        "/load" => {
            let session_id = parts.get(1).ok_or("Usage: /load <session_id>")?;
            let session = session_manager
                .load_session(session_id)
                .map_err(|e| format!("Failed to load session: {}", e))?;

            // Reconcile system prompt
            let mut messages = session.messages.clone();
            if !messages.is_empty() {
                messages[0] = serde_json::json!({
                    "role": "system",
                    "content": "You are a coding agent. You have tools to write files and run terminal commands. Do NOT output raw code blocks for me to run. Use your 'write_file' tool to create the python scripts, and use your 'run_terminal_command' tool to execute and test them. When you have successfully completed the task and verified it works, just reply with a friendly message explaining what you did."
                });
            }

            agent.messages = messages.clone();
            agent.full_history = messages;

            Ok((
                Some(session_id.to_string()),
                session.title.clone(),
            ))
        }
        "/new" => {
            agent.reset();
            Ok((None, "Untitled".to_string()))
        }
        "/quit" | "/exit" => {
            std::process::exit(0);
        }
        "/help" => {
            println!("{}", "Available Commands:".cyan().bold());
            println!("  {} — List all saved sessions", "/sessions".yellow());
            println!("  {} — Load a previous session", "/load <session_id>".yellow());
            println!("  {} — Start a new session", "/new".yellow());
            println!("  {} — Exit the agent", "/quit".yellow());
            println!("  {} — Show this help", "/help".yellow());
            Ok((current_session_id.clone(), current_session_title.clone()))
        }
        _ => Err(format!("Unknown command: {}. Type /help for available commands.", command)),
    }
}

async fn run_agent_loop(
    agent: &mut CodingAgent,
    session_manager: &SessionManager,
    session_id: &Option<String>,
    session_title: &str,
) {
    let max_steps = 35;
    let mut step = 0;

    loop {
        step += 1;

        match agent.run_step().await {
            Ok((response_text, tool_used)) => {
                if tool_used {
                    // Continue looping for more steps
                    if step >= max_steps {
                        println!("\n{}", "─".repeat(60).bright_black());
                        println!(
                            "{}",
                            "Max steps reached. Continue for 10 more? (y/N)".yellow()
                        );
                        print!("{}> ", "Agent".cyan());
                        std::io::Write::flush(&mut std::io::stdout()).ok();

                        let mut input = String::new();
                        if std::io::stdin().read_line(&mut input).is_err() {
                            break;
                        }

                        if input.trim().eq_ignore_ascii_case("y") {
                            step = 0; // Reset step counter
                        } else {
                            break;
                        }
                    }
                } else {
                    // Got text response
                    println!("\n{}", "─".repeat(60).bright_black());
                    print_panel(&response_text);
                    println!();
                    break;
                }
            }
            Err(e) => {
                println!("{} Error: {}", "✗".red(), e);
                break;
            }
        }
    }

    // Save session
    if let Some(id) = session_id {
        let _ = session_manager.save_session(id, session_title, agent.full_history.clone());
    }
}

fn print_panel(text: &str) {
    let border = "█".repeat(60);
    println!("{}", border.green());
    for line in text.lines() {
        println!("█ {:<58}█", line);
    }
    println!("{}", border.green());
}
