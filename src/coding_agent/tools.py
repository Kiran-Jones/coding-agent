import inspect
import os
import shlex
import subprocess

import requests
from bs4 import BeautifulSoup
from ddgs import DDGS


def map_python_type_to_json(py_type):
    """Converts Python type hints to JSON schema types."""
    mapping = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }
    # Default to string if no type hint is provided
    return mapping.get(py_type, "string")


def generate_schema(func):
    """Automatically generates an OpenAI/Claude tool JSON schema from a Python function."""
    sig = inspect.signature(func)
    
    properties = {}
    required = []
    
    # Loop through the function's arguments
    for name, param in sig.parameters.items():
        # Map the Python type hint (e.g., str) to JSON type (e.g., "string")
        param_type = map_python_type_to_json(param.annotation)
        
        properties[name] = {"type": param_type, "description": f"The {name} parameter."}
        
        # If the argument doesn't have a default value, it's required
        if param.default == inspect.Parameter.empty:
            required.append(name)
    
    return {
        "type": "function",
        "function": {
            "name": func.__name__,
            # Uses the function's docstring as the description for the LLM
            "description": inspect.getdoc(func) or f"Execute {func.__name__}",
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required,
            },
        },
    }


def run_terminal_command(command: str) -> str:
    """Run a terminal command and return its output. Only accepts a single 'command' argument (the shell command string)."""
    
    import re
    
    DANGEROUS_PATTERNS = [
        r"\brm\b",
        r"\bsudo\b",
        r"\bdd\b",
        r"\bmkfs\b",
        r"\bshutdown\b",
        r"\breboot\b",
        r"\bpoweroff\b",
    ]
    
    if any(re.search(p, command) for p in DANGEROUS_PATTERNS):
        confirmation = input(
            f"The command '{command}' contains potentially dangerous keywords. Are you sure you want to run it? (Y/n): "
        )
        if confirmation.lower() != "y":
            return "Command execution cancelled by user."
    
    try:
        result = subprocess.run(
            command, shell=True, capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0:
            return (
                result.stdout.strip()
                or "Command executed successfully with no output."
            )
        else:
            return f"Error: {result.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return "Error: The command timed out after 15 seconds. Do not run interactive commands."
    except Exception as e:
        return f"Execution Exception: {str(e)}"


def write_file(file_path: str, content: str) -> str:
    """Write content to a file. Only accepts 'file_path' (the path to write to) and 'content' (the full file content). Returns success message or error."""
    try:
        parent = os.path.dirname(file_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(file_path, "w") as f:
            f.write(content)
        return f"Success! File saved to {file_path}."
    except Exception as e:
        return f"Error writing file: {str(e)}"


def web_search(query: str) -> str:
    """Perform a web search using DuckDuckGo and return the top 5 results.
    Returns the Title, URL, and a short snippet for each result.
    Use the 'read_webpage' tool on the provided URLs to read the full content."""
    
    try:
        with DDGS() as ddgs:
            # We limit to 5 results to keep the context window clean and focused
            results = list(ddgs.text(query, max_results=5))
            
        if not results:
            return "No results found. Try modifying your search query."
            
        formatted_results = []
        for i, res in enumerate(results, 1):
            formatted_results.append(
                f"Result {i}:\n"
                f"Title: {res.get('title')}\n"
                f"URL: {res.get('href')}\n"
                f"Snippet: {res.get('body')}\n"
            )
            
        return "\n".join(formatted_results)
    except Exception as e:
        return f"Search failed: {str(e)}"


def read_webpage(url: str) -> str:
    """Fetches a URL, strips away all HTML/CSS/JS, and returns clean text for the agent to read."""
    
    try:
        # 1. Fetch the raw HTML (Timeout is crucial so the agent doesn't hang!)
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        # 2. Parse it and strip out the junk
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Destroy script and style elements completely
        for script in soup(["script", "style", "nav", "footer", "header"]):
            script.extract()
        
        # 3. Get the clean text
        text = soup.get_text(separator=" ", strip=True)
        
        # Limit the text length just in case it's a massive terms of service page
        # ~15,000 characters is a safe chunk for an LLM to read quickly
        return text[:15000]
    except requests.exceptions.Timeout:
        return "Error: The webpage took too long to load."
    except Exception as e:
        return f"Error reading webpage: {str(e)}"


def list_directory(path: str = ".") -> str:
    """Lists the contents of a directory. Only accepts 'path' (directory path, defaults to '.'). Useful for exploring the file system."""
    
    try:
        items = os.listdir(path)
        # Filter out noisy directories that confuse the LLM
        clean_items = [
            item for item in items if not item.startswith(".") and item != "__pycache__"
        ]
        
        if not clean_items:
            return f"Directory '{path}' is empty."
        
        return f"Contents of {path}:\n" + "\n".join(f"- {item}" for item in clean_items)
    except FileNotFoundError:
        return f"Error: Directory '{path}' not found."
    except Exception as e:
        return f"Error reading directory: {str(e)}"


def read_file(file_path: str) -> str:
    """Reads a file and returns its contents with line numbers. Only accepts 'file_path' (the path to read). Use this to inspect code."""
    
    try:
        with open(file_path, "r") as f:
            lines = f.readlines()
        
        # Context Window Protection: Prevent reading massive files
        if len(lines) > 2000:
            return f"Error: File is too large ({len(lines)} lines). I can only read up to 2000 lines to protect memory."
        
        # Add line numbers to the output (e.g., "1 | import os")
        numbered_content = ""
        for i, line in enumerate(lines, 1):
            numbered_content += f"{i:4d} | {line}"
        
        return numbered_content
    except FileNotFoundError:
        return f"Error: File '{file_path}' not found. Try using list_directory to see what files exist."
    except UnicodeDecodeError:
        return "Error: This looks like a binary file (like an image or PDF). I can only read text files."
    except Exception as e:
        return f"Error reading file: {str(e)}"


def replace_text_in_file(file_path: str, old_text: str, new_text: str) -> str:
    """Replaces old_text with new_text in the specified file. Only accepts 'file_path', 'old_text' (exact string to find), and 'new_text' (replacement string). Returns success message or error."""
    
    try:
        with open(file_path, "r") as f:
            content = f.read()
        
        if old_text not in content:
            return (
                f"Error: The exact string '{old_text}' was not found in the file. "
                "Check your spelling, whitespace, and indentation, and try again."
            )
        
        updated_content = content.replace(old_text, new_text)
        
        with open(file_path, "w") as f:
            f.write(updated_content)
        
        return f"Success! Replaced text in {file_path}."
    except FileNotFoundError:
        return f"Error: File '{file_path}' not found."
    except Exception as e:
        return f"Error replacing text in file: {str(e)}"


def run_git_command(command: str) -> str:
    """Run a git command and return its output. Useful for version control tasks."""
    
    if ";" in command or "&&" in command or "|" in command:
        return "Error: Command chaining is not allowed for security reasons. Run one git command at a time."
    
    command = command.strip()
    if command.startswith("git "):
        command = command[4:]
    
    try:
        args = ["git"] + shlex.split(command)
        
        result = subprocess.run(args, capture_output=True, text=True, timeout=15)
        if result.returncode == 0:
            return (
                result.stdout.strip()
                or "Git command executed successfully with no output."
            )
        else:
            return f"Error: {result.stderr.strip()}"
    except subprocess.TimeoutExpired:
        return "Error: The git command timed out after 15 seconds."
    except Exception as e:
        return f"Execution Exception: {str(e)}"

# A router dictionary so the Agent can easily trigger the right function
AVAILABLE_TOOLS = {
    "run_terminal_command": run_terminal_command,
    "write_file": write_file,
    "web_search": web_search,
    "read_webpage": read_webpage,
    "list_directory": list_directory,
    "read_file": read_file,
    "replace_text_in_file": replace_text_in_file,
    "run_git_command": run_git_command,
}

TOOL_SCHEMAS = [generate_schema(func) for func in AVAILABLE_TOOLS.values()]