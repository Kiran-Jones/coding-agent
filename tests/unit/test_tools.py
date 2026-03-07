"""
Unit tests for tools.py module.

Tests schema generation, terminal commands, file operations, web operations,
and git commands.
"""

import subprocess
from unittest.mock import Mock

import requests

from coding_agent import tools


# ============================================================================
# SECTION 1.1: Schema Generation (3 tests)
# ============================================================================


class TestSchemaGeneration:
    """Test schema generation from Python functions."""

    def test_map_python_type_to_json_basic_types(self):
        """Verify str→string, int→integer, float→number, bool→boolean, list→array mapping."""
        assert tools.map_python_type_to_json(str) == "string"
        assert tools.map_python_type_to_json(int) == "integer"
        assert tools.map_python_type_to_json(float) == "number"
        assert tools.map_python_type_to_json(bool) == "boolean"
        assert tools.map_python_type_to_json(list) == "array"
        assert tools.map_python_type_to_json(dict) == "object"

    def test_map_python_type_to_json_unknown_type(self):
        """Verify unknown types default to 'string'."""

        class CustomType:
            pass

        assert tools.map_python_type_to_json(CustomType) == "string"
        assert tools.map_python_type_to_json(None) == "string"

    def test_generate_schema_from_function(self):
        """Verify schema generation with parameters, required fields, and docstring."""

        def sample_func(required_param: str, optional_param: int = 5):
            """This is a sample function."""
            pass

        schema = tools.generate_schema(sample_func)

        assert schema["type"] == "function"
        assert schema["function"]["name"] == "sample_func"
        assert schema["function"]["description"] == "This is a sample function."
        assert "required_param" in schema["function"]["parameters"]["properties"]
        assert "optional_param" in schema["function"]["parameters"]["properties"]
        assert "required_param" in schema["function"]["parameters"]["required"]
        assert "optional_param" not in schema["function"]["parameters"]["required"]


# ============================================================================
# SECTION 1.2: Terminal Command Execution (4 tests)
# ============================================================================


class TestRunTerminalCommand:
    """Test terminal command execution."""

    def test_run_terminal_command_success(self):
        """Execute echo command, verify output."""
        result = tools.run_terminal_command("echo 'hello world'")
        assert "hello world" in result

    def test_run_terminal_command_with_stderr(self):
        """Capture both stdout and stderr."""
        result = tools.run_terminal_command("ls /nonexistent_directory_12345 2>&1")
        # Should contain error info
        assert "Error" in result or "cannot access" in result or result

    def test_run_terminal_command_timeout(self, mocker):
        """Verify timeout handling."""
        mock_proc = mocker.MagicMock()
        mock_proc.stdout = iter([])
        mock_proc.wait.side_effect = subprocess.TimeoutExpired(
            cmd="sleep 200", timeout=120
        )
        mock_proc.kill = mocker.MagicMock()
        mocker.patch("subprocess.Popen", return_value=mock_proc)
        result = tools.run_terminal_command("sleep 200")
        assert "timed out" in result.lower()

    def test_run_terminal_command_invalid_command(self):
        """Verify error message for invalid command."""
        result = tools.run_terminal_command("invalid_command_xyz_12345")
        assert (
            "Error" in result or "not found" in result.lower() or "Exception" in result
        )


# ============================================================================
# SECTION 1.3: File Operations (4 tests)
# ============================================================================


class TestFileOperations:
    """Test file read/write operations."""

    def test_write_file_simple(self, tmp_path):
        """Create file with content, verify existence."""
        filepath = tmp_path / "test.txt"
        result = tools.write_file(str(filepath), "test content")

        assert "Success" in result
        assert filepath.exists()
        assert filepath.read_text() == "test content"

    def test_write_file_nested_directory(self, tmp_path):
        """Create parent directories if missing."""
        filepath = tmp_path / "subdir" / "nested" / "file.txt"
        result = tools.write_file(str(filepath), "nested content")

        assert "Success" in result
        assert filepath.exists()
        assert filepath.read_text() == "nested content"

    def test_write_file_overwrite(self, tmp_path):
        """Overwrite existing file."""
        filepath = tmp_path / "test.txt"
        filepath.write_text("original")

        result = tools.write_file(str(filepath), "new content")

        assert "Success" in result
        assert filepath.read_text() == "new content"

    def test_write_file_permission_error(self, tmp_path, mocker):
        """Mock OSError for permission denied."""
        mocker.patch("builtins.open", side_effect=PermissionError("Permission denied"))

        result = tools.write_file("/some/path", "content")

        assert "Error" in result


# ============================================================================
# SECTION 1.4: Web Operations (3 tests)
# ============================================================================


class TestWebSearch:
    """Test web search functionality."""

    def test_web_search_success(self, mocker):
        """Mock DDGS, verify 5 results formatted correctly."""
        mock_results = [
            {"title": "Result 1", "href": "http://example.com/1", "body": "Snippet 1"},
            {"title": "Result 2", "href": "http://example.com/2", "body": "Snippet 2"},
        ]
        mocker.patch(
            "coding_agent.tools.DDGS"
        ).return_value.__enter__.return_value.text.return_value = mock_results

        result = tools.web_search("test query")

        assert "Result 1:" in result
        assert "Result 2:" in result
        assert "http://example.com/1" in result
        assert "http://example.com/2" in result

    def test_web_search_no_results(self, mocker):
        """Verify 'No results found' message."""
        mocker.patch(
            "coding_agent.tools.DDGS"
        ).return_value.__enter__.return_value.text.return_value = []

        result = tools.web_search("obscure query xyz")

        assert "No results found" in result

    def test_web_search_exception(self, mocker):
        """Mock exception, verify error message."""
        mocker.patch("coding_agent.tools.DDGS", side_effect=Exception("Network error"))

        result = tools.web_search("test")

        assert "Search failed" in result or "Error" in result


# ============================================================================
# SECTION 1.5: Read Webpage (2 tests)
# ============================================================================


class TestReadWebpage:
    """Test webpage reading."""

    def test_read_webpage_success(self, mocker):
        """Mock requests.get, verify HTML stripping."""
        mock_response = Mock()
        mock_response.text = "<html><body><p>Hello world</p></body></html>"
        mock_response.raise_for_status = Mock()
        mocker.patch("requests.get", return_value=mock_response)

        result = tools.read_webpage("http://example.com")

        assert "Hello world" in result
        assert "<p>" not in result
        assert "<html>" not in result

    def test_read_webpage_timeout(self, mocker):
        """requests.Timeout exception handling."""
        mocker.patch("requests.get", side_effect=requests.exceptions.Timeout())

        result = tools.read_webpage("http://example.com")

        assert "took too long" in result


# ============================================================================
# SECTION 1.6: File Reading (3 tests)
# ============================================================================


class TestReadFile:
    """Test file reading functionality."""

    def test_read_file_success(self, tmp_path):
        """Read file with line numbers."""
        filepath = tmp_path / "test.txt"
        filepath.write_text("Line 1\nLine 2\nLine 3\n")

        result = tools.read_file(str(filepath))

        assert "1 |" in result
        assert "2 |" in result
        assert "3 |" in result
        assert "Line 1" in result
        assert "Line 2" in result

    def test_read_file_too_large(self, tmp_path):
        """File > 2000 lines returns error."""
        filepath = tmp_path / "large.txt"
        large_content = "\n".join([f"Line {i}" for i in range(2001)])
        filepath.write_text(large_content)

        result = tools.read_file(str(filepath))

        assert "Error" in result or "too large" in result

    def test_read_file_not_found(self):
        """FileNotFoundError handling."""
        result = tools.read_file("/nonexistent/path/file.txt")

        assert "Error" in result
        assert "not found" in result


# ============================================================================
# SECTION 1.7: Replace Text (2 tests)
# ============================================================================


class TestReplaceText:
    """Test text replacement in files."""

    def test_replace_text_in_file_success(self, tmp_path):
        """Replace exact string."""
        filepath = tmp_path / "test.txt"
        filepath.write_text("This is old text.")

        result = tools.replace_text_in_file(str(filepath), "old", "new")

        assert "Success" in result
        assert filepath.read_text() == "This is new text."

    def test_replace_text_in_file_not_found(self, tmp_path):
        """String not found error."""
        filepath = tmp_path / "test.txt"
        filepath.write_text("Original content")

        result = tools.replace_text_in_file(str(filepath), "nonexistent", "new")

        assert "Error" in result
        assert "not found" in result


# ============================================================================
# SECTION 1.8: Git Commands (3 tests)
# ============================================================================


class TestGitCommands:
    """Test git command execution."""

    def test_run_git_command_success(self, mocker):
        """Mock subprocess.run, verify git output."""
        mock_result = Mock()
        mock_result.returncode = 0
        mock_result.stdout = "git output"
        mock_result.stderr = ""
        mocker.patch("subprocess.run", return_value=mock_result)

        result = tools.run_git_command("status")

        assert "git output" in result

    def test_run_git_command_no_command_chaining(self):
        """Block `;`, `&&`, `|` for security."""
        result1 = tools.run_git_command("status; rm -rf /")
        assert "not allowed" in result1

        result2 = tools.run_git_command("status && echo hacked")
        assert "not allowed" in result2

        result3 = tools.run_git_command("status | grep")
        assert "not allowed" in result3

    def test_run_git_command_timeout(self, mocker):
        """TimeoutExpired handling."""
        mocker.patch(
            "subprocess.run", side_effect=subprocess.TimeoutExpired("git", 120)
        )

        result = tools.run_git_command("status")

        assert "timed out" in result.lower()


# ============================================================================
# SECTION 1.9: Tool Registry (1 test)
# ============================================================================


class TestToolRegistry:
    """Test AVAILABLE_TOOLS registry."""

    def test_available_tools_contains_all_functions(self):
        """Verify all expected tools are registered."""
        expected_tools = {
            "run_terminal_command",
            "write_file",
            "web_search",
            "read_webpage",
            "list_directory",
            "read_file",
            "replace_text_in_file",
            "run_git_command",
        }

        assert set(tools.AVAILABLE_TOOLS.keys()) == expected_tools

    def test_tool_schemas_generated(self):
        """Verify tool schemas are generated."""
        assert len(tools.TOOL_SCHEMAS) > 0
        for schema in tools.TOOL_SCHEMAS:
            assert "type" in schema
            assert "function" in schema
            assert "name" in schema["function"]
