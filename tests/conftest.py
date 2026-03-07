"""
Shared pytest fixtures and configuration for the AI Coding Agent test suite.

This module provides:
- Mock API responses and fixtures
- Mock agent instances with callbacks
- Mock MCPManager for testing
- Mock filesystem fixtures
- Mock streaming responses
"""

import json
from unittest.mock import Mock

import pytest

from coding_agent.agent import CodingAgent
from coding_agent.session_manager import SessionManager
from coding_agent.snapshot_manager import SnapshotManager

# ============================================================================
# MOCK API RESPONSES
# ============================================================================


class MockAPIResponses:
    """Collection of mock API responses for different scenarios."""

    @staticmethod
    def streaming_text_response():
        """Mock streaming response with text content."""
        return [
            'data: {"choices":[{"delta":{"content":"Hello"}}]}\n',
            'data: {"choices":[{"delta":{"content":" "}}]}\n',
            'data: {"choices":[{"delta":{"content":"world"}}]}\n',
            'data: {"choices":[{"delta":{}}],"usage":{"prompt_tokens":10,"completion_tokens":5}}\n',
            "data: [DONE]\n",
        ]

    @staticmethod
    def tool_call_response():
        """Mock streaming response with tool calls."""
        return [
            'data: {"choices":[{"delta":{"tool_calls"'
            ':[{"index":0,"id":"call-123","function":{"name":"write_file",'
            '"arguments":"{\\"file_path\\":\\"test.txt\\",\\"content\\":\\"hello\\"}"}}]}}]}\n',
            'data: {"choices":[{"delta":{}}],"usage":{"prompt_tokens":20,"completion_tokens":10}}\n',
            "data: [DONE]\n",
        ]

    @staticmethod
    def mcp_tool_response():
        """Mock streaming response with MCP tool calls."""
        return [
            'data: {"choices":[{"delta":{"tool_calls"'
            ':[{"index":0,"id":"call-456","function":{"name":"test__my_tool",'
            '"arguments":"{\\"param\\":\\"value\\"}"}}]}}]}\n',
            'data: {"choices":[{"delta":{}}],"usage":{"prompt_tokens":15,"completion_tokens":8}}\n',
            "data: [DONE]\n",
        ]

    @staticmethod
    def error_response(status_code=500):
        """Mock error API response."""
        return {
            "error": {
                "message": "Internal Server Error",
                "type": "server_error",
                "param": None,
                "code": "internal_error",
            }
        }

    @staticmethod
    def models_list_response():
        """Mock /models endpoint response."""
        return {
            "object": "list",
            "data": [
                {"id": "model-1", "object": "model", "owned_by": "test"},
                {"id": "model-2", "object": "model", "owned_by": "test"},
                {"id": "model-3", "object": "model", "owned_by": "test"},
            ],
        }


# ============================================================================
# FIXTURES: Mock Objects & Agents
# ============================================================================


@pytest.fixture
def mock_api_responses():
    """Provide access to mock API responses."""
    return MockAPIResponses()


@pytest.fixture
def mock_callback():
    """Create a mock callback function."""
    return Mock(return_value=None)


@pytest.fixture
def mock_stream_callback():
    """Create a mock stream callback."""
    return Mock(return_value=None)


@pytest.fixture
def mock_approval_callback():
    """Create a mock approval callback (default: approve all)."""
    return Mock(return_value=True)


@pytest.fixture
def mock_approval_callback_deny():
    """Create a mock approval callback that denies all."""
    return Mock(return_value=False)


@pytest.fixture
def mock_agent(mocker, mock_callback, mock_stream_callback, mock_approval_callback):
    """
    Create a CodingAgent instance with mocked external dependencies.

    This agent has:
    - Mocked API endpoint
    - Mocked snapshot_manager
    - All callbacks configured
    - No real API calls made
    """
    # Create agent
    agent = CodingAgent(
        api_key="test-api-key-12345",
        endpoint_url="http://test-api.local/v1/chat/completions",
        ui_callback=mock_callback,
        stream_callback=mock_stream_callback,
        approval_callback=mock_approval_callback,
    )

    # Mock snapshot_manager to avoid filesystem operations
    agent.snapshot_manager = Mock(spec=SnapshotManager)
    agent.snapshot_manager.save_snapshot = Mock()
    agent.snapshot_manager.undo = Mock(
        return_value={"file_path": "test.txt", "action": "undo"}
    )
    agent.snapshot_manager.redo = Mock(
        return_value={"file_path": "test.txt", "action": "redo"}
    )
    agent.snapshot_manager.get_history = Mock(return_value=[])

    # Mock MCP manager if present
    agent.mcp_manager = None

    return agent


@pytest.fixture
def mock_agent_no_approval(mocker, mock_callback, mock_stream_callback):
    """Create a CodingAgent with no approval callback (auto-approve mode)."""
    agent = CodingAgent(
        api_key="test-api-key-12345",
        endpoint_url="http://test-api.local/v1/chat/completions",
        ui_callback=mock_callback,
        stream_callback=mock_stream_callback,
        approval_callback=None,  # No approval needed
    )
    agent.snapshot_manager = Mock(spec=SnapshotManager)
    agent.mcp_manager = None
    return agent


@pytest.fixture
def mock_mcp_manager(mocker):
    """
    Create a mock MCPManager for integration testing.

    Provides:
    - get_tools() returns list of MCP tools
    - call_tool() returns mock results
    - get_server_status() returns status dict
    """
    mock = Mock()
    mock.get_tools.return_value = [
        {
            "type": "function",
            "function": {
                "name": "test_server__list_files",
                "description": "List files in directory",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "Directory path"}
                    },
                    "required": ["path"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "test_server__run_custom_tool",
                "description": "Run custom tool",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string", "description": "Command to run"}
                    },
                    "required": ["command"],
                },
            },
        },
    ]
    mock.call_tool.return_value = "Tool executed successfully"
    mock.get_server_status.return_value = {
        "test_server": "running",
        "other_server": "stopped",
    }
    mock.initialize = Mock()
    mock.shutdown = Mock()
    return mock


# ============================================================================
# FIXTURES: Filesystem & Sessions
# ============================================================================


@pytest.fixture
def tmp_session_dir(tmp_path):
    """Create a temporary session directory for testing."""
    session_dir = tmp_path / ".sessions"
    session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


@pytest.fixture
def tmp_snapshot_dir(tmp_path):
    """Create a temporary snapshot directory with initialized index."""
    snapshot_dir = tmp_path / ".snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    # Create index.json
    index_path = snapshot_dir / "index.json"
    index_data = {
        "next_id": 0,
        "undo_stack": [],
        "redo_stack": [],
    }
    with open(index_path, "w") as f:
        json.dump(index_data, f)

    return snapshot_dir


@pytest.fixture
def session_manager(tmp_session_dir):
    """Create a SessionManager using temporary directory."""
    return SessionManager(directory=str(tmp_session_dir))


@pytest.fixture
def snapshot_manager_instance(tmp_snapshot_dir, mocker):
    """
    Create a SnapshotManager instance using temporary directory.

    Note: Mocks os.getcwd() to return the tmp_path directory.
    """
    # Create snapshot manager with custom directory
    manager = SnapshotManager()
    # Override the directory to use our tmp_snapshot_dir
    manager.snapshot_dir = str(tmp_snapshot_dir)
    manager.index_path = str(tmp_snapshot_dir / "index.json")
    manager._load_index()
    return manager


@pytest.fixture
def sample_file(tmp_path):
    """Create a sample file for testing file operations."""
    file_path = tmp_path / "sample.txt"
    file_path.write_text("Original content\nLine 2\nLine 3\n")
    return file_path


@pytest.fixture
def sample_code_file(tmp_path):
    """Create a sample Python file for testing."""
    file_path = tmp_path / "sample.py"
    file_path.write_text(
        'def hello():\n    """Say hello."""\n    print("Hello, world!")\n'
    )
    return file_path


# ============================================================================
# FIXTURES: Mock Streaming Responses
# ============================================================================


@pytest.fixture
def mock_stream_response(mocker, mock_api_responses):
    """Mock a streaming API response."""
    response = Mock()
    response.status_code = 200
    response.iter_lines.return_value = mock_api_responses.streaming_text_response()
    return response


@pytest.fixture
def mock_tool_call_response(mocker, mock_api_responses):
    """Mock a streaming API response with tool calls."""
    response = Mock()
    response.status_code = 200
    response.iter_lines.return_value = mock_api_responses.tool_call_response()
    return response


@pytest.fixture
def mock_mcp_call_response(mocker, mock_api_responses):
    """Mock a streaming API response with MCP tool calls."""
    response = Mock()
    response.status_code = 200
    response.iter_lines.return_value = mock_api_responses.mcp_tool_response()
    return response


@pytest.fixture
def mock_error_response(mocker, mock_api_responses):
    """Mock a failed API response."""
    response = Mock()
    response.status_code = 500
    response.text = json.dumps(mock_api_responses.error_response())
    return response


# ============================================================================
# FIXTURES: Data Fixtures
# ============================================================================


@pytest.fixture
def sample_messages():
    """Create a sample message history."""
    return [
        {
            "role": "system",
            "content": "You are a helpful assistant.",
        },
        {
            "role": "user",
            "content": "Write a hello world program.",
        },
        {
            "role": "assistant",
            "content": "Here's a hello world program:",
            "tool_calls": [
                {
                    "id": "call-123",
                    "type": "function",
                    "function": {
                        "name": "write_file",
                        "arguments": '{"file_path": "hello.py", "content": "print(\'hello\')"}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "tool_call_id": "call-123",
            "content": "Success! File saved to hello.py.",
        },
    ]


@pytest.fixture
def sample_session_data():
    """Create sample session data."""
    return {
        "id": "1",
        "title": "My Coding Session",
        "updated_at": "2024-01-15 10:30:00",
        "messages": [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Hello"},
        ],
        "full_history": [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ],
    }


@pytest.fixture
def sample_snapshot():
    """Create sample snapshot data."""
    return {
        "file_path": "/path/to/file.txt",
        "original": "Original content",
        "timestamp": 1705329000.0,
    }


@pytest.fixture
def sample_snapshot_new_file():
    """Create snapshot data for a new file."""
    return {
        "file_path": "/path/to/new_file.txt",
        "original": None,
        "timestamp": 1705329000.0,
    }


# ============================================================================
# FIXTURES: Rich Console Mock
# ============================================================================


@pytest.fixture
def mock_console(mocker):
    """Create a mock Rich Console."""
    from rich.console import Console

    mock = Mock(spec=Console)
    mock.print = Mock()
    return mock


# ============================================================================
# PYTEST MARKERS
# ============================================================================


def pytest_configure(config):
    """Register custom pytest markers."""
    config.addinivalue_line("markers", "unit: Unit test for a single module")
    config.addinivalue_line(
        "markers", "integration: Integration test for multiple modules"
    )
    config.addinivalue_line("markers", "system: System/E2E test")
    config.addinivalue_line("markers", "critical: Critical test that must pass")
    config.addinivalue_line("markers", "slow: Slow test (>5s)")
    config.addinivalue_line("markers", "requires_api: Test requires external API")
