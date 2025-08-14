"""
Unit tests for isms_securitycheck_tool.py using pytest and pydantic_ai TestModel
Tests sheet_agent and filter_agent without making actual LLM calls
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from typing import List, Dict, Any
import json

from pydantic import BaseModel
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.test import TestModel

# Import the modules to test
from isms_securitycheck_tool import (
    UpdateTask,
    UpdateTasksList,
    sheet_agent,
    filter_agent,
    get_sheet_data,
    filter_update_tasks,
    _convert_to_dict
)

# Disable actual model requests
from pydantic_ai import models
models.ALLOW_MODEL_REQUESTS = False

# ==================== Fixtures ====================

@pytest.fixture
def sample_sheet_raw_data() -> List[List[str]]:
    """Mock raw data from Google Sheets"""
    return [
        # Header row
        ["アップデート対応日", "端末機№", "部署名", "コンピューター名", 
         "最終ログオンユーザ", "最終ログオンユーザ\n 表示名", "OS", 
         "IEまたはOSビルドのバージョン", "Windows Update\n／WithSecure",
         "Google Chrome", "Mozilla Firefox", "Mozilla Thunderbird", 
         "Adobe Reader", "SKYSEA"],
        # Row 1: Incomplete task (empty date)
        ["", "977", "CH", "HOPC127", "jinji", "人事PC", "Windows 10",
         "22H2(19045.4651)", "×", "127.0.6533.089", "", "",
         "24.002.20895", "19.300.09h"],
        # Row 2: Complete task (has date)
        ["2025-08-13", "978", "IT", "HOPC128", "admin", "管理者PC", "Windows 11",
         "23H2(22631.4169)", "○", "128.0.6613.113", "130.0", "",
         "24.002.21000", "19.300.10a"],
        # Row 3: Incomplete task (None date)
        ["", "979", "FIN", "HOPC129", "keiri", "経理PC", "Windows 10",
         "22H2(19045.4651)", "×", "126.0.6478.127", "129.0.2", "115.15.0",
         "", ""],
    ]


@pytest.fixture
def sample_sheet_dict_data(sample_sheet_raw_data) -> List[Dict[str, str]]:
    """Convert raw sheet data to dictionary format"""
    return _convert_to_dict(sample_sheet_raw_data)


@pytest.fixture
def sample_update_tasks_all() -> UpdateTasksList:
    """Sample UpdateTasksList with both complete and incomplete tasks"""
    return UpdateTasksList(
        tasks=[
            UpdateTask(
                date_of_update="",
                computer_name="HOPC127",
                last_logon_user="jinji",
                software_to_be_updated={"Google Chrome", "Adobe Reader", "SKYSEA"}
            ),
            UpdateTask(
                date_of_update="2025-08-13",
                computer_name="HOPC128",
                last_logon_user="admin",
                software_to_be_updated={"Firefox", "Adobe Reader", "SKYSEA"}
            ),
            UpdateTask(
                date_of_update=None,
                computer_name="HOPC129",
                last_logon_user="keiri",
                software_to_be_updated={"Google Chrome", "Firefox", "Thunderbird"}
            ),
        ],
        total_count=3
    )


@pytest.fixture
def sample_update_tasks_filtered() -> UpdateTasksList:
    """Sample UpdateTasksList with only incomplete tasks"""
    return UpdateTasksList(
        tasks=[
            UpdateTask(
                date_of_update="",
                computer_name="HOPC127",
                last_logon_user="jinji",
                software_to_be_updated={"Google Chrome", "Adobe Reader", "SKYSEA"}
            ),
            UpdateTask(
                date_of_update=None,
                computer_name="HOPC129",
                last_logon_user="keiri",
                software_to_be_updated={"Google Chrome", "Firefox", "Thunderbird"}
            ),
        ],
        total_count=2
    )


@pytest.fixture
def mock_google_sheets_service():
    """Mock Google Sheets API service"""
    with patch('isms_securitycheck_tool.get_google_sheets_service') as mock_service:
        mock_api = MagicMock()
        mock_service.return_value = mock_api
        yield mock_api


# ==================== Helper Functions Tests ====================

def test_convert_to_dict_with_valid_data(sample_sheet_raw_data):
    """Test _convert_to_dict with valid sheet data"""
    result = _convert_to_dict(sample_sheet_raw_data)
    
    assert len(result) == 3  # 3 data rows
    assert result[0]["コンピューター名"] == "HOPC127"
    assert result[1]["アップデート対応日"] == "2025-08-13"
    assert result[2]["最終ログオンユーザ"] == "keiri"


def test_convert_to_dict_with_empty_data():
    """Test _convert_to_dict with empty or insufficient data"""
    assert _convert_to_dict([]) == []
    assert _convert_to_dict([["header1", "header2"]]) == []  # Only header, no data


# ==================== sheet_agent Tests ====================

@pytest.mark.asyncio
async def test_sheet_agent_with_testmodel(mock_google_sheets_service, sample_sheet_raw_data):
    """Test sheet_agent with TestModel to avoid actual LLM calls"""
    
    # Mock the Google Sheets API response
    mock_google_sheets_service.spreadsheets().values().batchGet.return_value.execute.return_value = {
        'valueRanges': [{'values': sample_sheet_raw_data}]
    }
    
    # Use TestModel - it will automatically generate valid UpdateTasksList
    test_model = TestModel()
    
    # Override the agent with TestModel
    with sheet_agent.override(model=test_model):
        result = await sheet_agent.run(
            "Get all security update tasks from spreadsheet",
            deps="test_spreadsheet_id"
        )
    
    # Verify the result structure is correct
    assert isinstance(result.output, UpdateTasksList)
    assert hasattr(result.output, 'tasks')
    assert hasattr(result.output, 'total_count')
    assert isinstance(result.output.tasks, list)
    
    # TestModel generates valid data automatically
    for task in result.output.tasks:
        assert isinstance(task, UpdateTask)
        assert hasattr(task, 'computer_name')
        assert hasattr(task, 'last_logon_user')
        assert hasattr(task, 'software_to_be_updated')


@pytest.mark.asyncio
async def test_sheet_agent_with_custom_output(mock_google_sheets_service):
    """Test sheet_agent with TestModel using custom output"""
    
    # Mock the Google Sheets API
    mock_google_sheets_service.spreadsheets().values().batchGet.return_value.execute.return_value = {
        'valueRanges': [{'values': [["header"], ["data"]]}]
    }
    
    # Create TestModel with custom output
    test_model = TestModel(
        custom_output_args={
            'tasks': [
                {
                    'date_of_update': '',
                    'computer_name': 'TEST-PC',
                    'last_logon_user': 'test_user',
                    'software_to_be_updated': ['Google Chrome', 'SKYSEA']
                }
            ],
            'total_count': 1
        }
    )
    
    with sheet_agent.override(model=test_model):
        result = await sheet_agent.run(
            "Get tasks from spreadsheet",
            deps="test_dep"
        )
    
    assert result.output.total_count == 1
    assert result.output.tasks[0].computer_name == 'TEST-PC'


@pytest.mark.asyncio
async def test_sheet_agent_runs_with_testmodel(mock_google_sheets_service):
    """Test sheet_agent runs successfully with TestModel"""
    
    mock_google_sheets_service.spreadsheets().values().batchGet.return_value.execute.return_value = {
        'valueRanges': [{'values': [["header"], ["data"]]}]
    }
    
    test_model = TestModel()
    
    # Override agent and run
    with sheet_agent.override(model=test_model):
        result = await sheet_agent.run(
            "Get tasks from sheet",
            deps="test_dep"
        )
    
    # Verify the result has proper structure
    assert result is not None
    assert hasattr(result, 'output')
    assert isinstance(result.output, UpdateTasksList)
    
    # TestModel generates data automatically
    assert result.output.total_count >= 0
    assert isinstance(result.output.tasks, list)


# ==================== filter_agent Tests ====================

@pytest.mark.asyncio
async def test_filter_agent_with_testmodel(sample_update_tasks_all):
    """Test filter_agent with TestModel"""
    
    # TestModel will automatically generate valid UpdateTasksList
    test_model = TestModel()
    
    with filter_agent.override(model=test_model):
        result = await filter_agent.run(
            "Filter tasks without update date",
            deps=sample_update_tasks_all
        )
    
    # Verify result structure
    assert isinstance(result.output, UpdateTasksList)
    assert hasattr(result.output, 'tasks')
    assert hasattr(result.output, 'total_count')
    assert isinstance(result.output.tasks, list)


@pytest.mark.asyncio
async def test_filter_agent_with_custom_output():
    """Test filter_agent with custom output"""
    
    input_tasks = UpdateTasksList(
        tasks=[
            UpdateTask(
                date_of_update="2025-08-13",
                computer_name="PC1",
                last_logon_user="user1",
                software_to_be_updated={"Google Chrome"}
            ),
            UpdateTask(
                date_of_update="",
                computer_name="PC2",
                last_logon_user="user2",
                software_to_be_updated={"Firefox"}
            ),
        ],
        total_count=2
    )
    
    # Custom output with only incomplete tasks
    test_model = TestModel(
        custom_output_args={
            'tasks': [
                {
                    'date_of_update': '',
                    'computer_name': 'PC2',
                    'last_logon_user': 'user2',
                    'software_to_be_updated': ['Firefox']
                }
            ],
            'total_count': 1
        }
    )
    
    with filter_agent.override(model=test_model):
        result = await filter_agent.run(
            "Filter incomplete tasks",
            deps=input_tasks
        )
    
    assert result.output.total_count == 1
    assert result.output.tasks[0].computer_name == 'PC2'


@pytest.mark.asyncio
async def test_filter_agent_tool_behavior():
    """Test the actual filter_update_tasks tool logic directly"""
    
    # Create mock context with test data
    mock_context = MagicMock(spec=RunContext)
    mock_context.deps = UpdateTasksList(
        tasks=[
            UpdateTask(
                date_of_update="",
                computer_name="PC1",
                last_logon_user="user1",
                software_to_be_updated={"Google Chrome"}
            ),
            UpdateTask(
                date_of_update="2025-08-13",
                computer_name="PC2",
                last_logon_user="user2",
                software_to_be_updated={"Firefox"}
            ),
            UpdateTask(
                date_of_update=None,
                computer_name="PC3",
                last_logon_user="user3",
                software_to_be_updated={"Thunderbird"}
            ),
        ],
        total_count=3
    )
    
    # Call the tool directly
    result = filter_update_tasks(mock_context)
    
    # Verify filtering logic
    assert result.total_count == 2
    assert len(result.tasks) == 2
    assert result.tasks[0].computer_name == "PC1"
    assert result.tasks[1].computer_name == "PC3"


# ==================== Integration Tests ====================

@pytest.mark.asyncio
async def test_end_to_end_flow(mock_google_sheets_service, sample_sheet_raw_data):
    """Test complete flow from sheet_agent to filter_agent"""
    
    # Mock Google Sheets API
    mock_google_sheets_service.spreadsheets().values().batchGet.return_value.execute.return_value = {
        'valueRanges': [{'values': sample_sheet_raw_data}]
    }
    
    # Use TestModel for both agents
    sheet_model = TestModel(
        custom_output_args={
            'tasks': [
                {'date_of_update': '', 'computer_name': 'PC1', 'last_logon_user': 'user1', 
                 'software_to_be_updated': ['Google Chrome']},
                {'date_of_update': '2025-08-13', 'computer_name': 'PC2', 'last_logon_user': 'user2',
                 'software_to_be_updated': ['Firefox']},
                {'date_of_update': None, 'computer_name': 'PC3', 'last_logon_user': 'user3',
                 'software_to_be_updated': ['Thunderbird']},
            ],
            'total_count': 3
        }
    )
    
    filter_model = TestModel(
        custom_output_args={
            'tasks': [
                {'date_of_update': '', 'computer_name': 'PC1', 'last_logon_user': 'user1',
                 'software_to_be_updated': ['Google Chrome']},
                {'date_of_update': None, 'computer_name': 'PC3', 'last_logon_user': 'user3',
                 'software_to_be_updated': ['Thunderbird']},
            ],
            'total_count': 2
        }
    )
    
    # Run the pipeline
    with sheet_agent.override(model=sheet_model):
        sheet_result = await sheet_agent.run(
            "Get all tasks from sheet",
            deps="spreadsheet_id"
        )
    
    with filter_agent.override(model=filter_model):
        filter_result = await filter_agent.run(
            "Filter incomplete tasks",
            deps=sheet_result.output
        )
    
    # Verify the flow
    assert sheet_result.output.total_count == 3
    assert filter_result.output.total_count == 2
    # Verify filtered tasks have no date
    for task in filter_result.output.tasks:
        assert task.date_of_update == "" or task.date_of_update is None


# ==================== Edge Cases & Error Handling ====================

@pytest.mark.asyncio
async def test_sheet_agent_with_empty_data(mock_google_sheets_service):
    """Test sheet_agent handles empty sheet data"""
    
    # Mock empty sheet response
    mock_google_sheets_service.spreadsheets().values().batchGet.return_value.execute.return_value = {
        'valueRanges': [{'values': []}]
    }
    
    test_model = TestModel(
        custom_output_args={
            'tasks': [],
            'total_count': 0
        }
    )
    
    with sheet_agent.override(model=test_model):
        result = await sheet_agent.run(
            "Process empty data",
            deps="test_dep"
        )
    
    assert result.output.total_count == 0
    assert len(result.output.tasks) == 0


@patch('isms_securitycheck_tool.get_google_sheets_service')
@pytest.mark.asyncio
async def test_google_sheets_api_error(mock_service):
    """Test handling of Google Sheets API errors"""
    
    from googleapiclient.errors import HttpError
    
    # Mock API error
    mock_service.side_effect = HttpError(
        resp=MagicMock(status=403),
        content=b"Access denied"
    )
    
    # The tool should raise the error
    mock_context = MagicMock(spec=RunContext)
    mock_context.deps = "test_deps"
    
    with pytest.raises(HttpError):
        get_sheet_data(
            mock_context,
            spreadsheet_id="test_id",
            ranges=["Sheet1!A1:Z100"]
        )


@pytest.mark.asyncio
async def test_filter_agent_preserves_task_integrity():
    """Test that filter_agent preserves all task fields correctly"""
    
    original_task = UpdateTask(
        date_of_update="",
        computer_name="COMPLEX-PC-名前",
        last_logon_user="ユーザー",
        software_to_be_updated={"windows update", "Google Chrome", "Firefox", "Thunderbird", "Adobe Reader", "SKYSEA"}
    )
    
    input_tasks = UpdateTasksList(
        tasks=[original_task],
        total_count=1
    )
    
    mock_context = MagicMock(spec=RunContext)
    mock_context.deps = input_tasks
    
    result = filter_update_tasks(mock_context)
    
    # Verify task is preserved exactly
    assert len(result.tasks) == 1
    filtered_task = result.tasks[0]
    assert filtered_task.computer_name == original_task.computer_name
    assert filtered_task.last_logon_user == original_task.last_logon_user
    assert filtered_task.software_to_be_updated == original_task.software_to_be_updated


# ==================== Additional Tests ====================

@pytest.mark.asyncio
async def test_complete_workflow_with_testmodel(mock_google_sheets_service):
    """Test a complete workflow with TestModel"""
    
    # Mock the Google Sheets API
    mock_google_sheets_service.spreadsheets().values().batchGet.return_value.execute.return_value = {
        'valueRanges': [{
            'values': [
                ["アップデート対応日", "コンピューター名", "最終ログオンユーザ"],
                ["", "PC1", "user1"],
                ["2025-08-13", "PC2", "user2"],
                ["", "PC3", "user3"]
            ]
        }]
    }
    
    # Run with TestModel - it will generate valid output automatically
    with sheet_agent.override(model=TestModel()):
        sheet_result = await sheet_agent.run(
            "Get all tasks",
            deps="test_spreadsheet"
        )
    
    with filter_agent.override(model=TestModel()):
        filter_result = await filter_agent.run(
            "Filter incomplete tasks",
            deps=sheet_result.output
        )
    
    # Just verify the structure is correct
    assert isinstance(sheet_result.output, UpdateTasksList)
    assert isinstance(filter_result.output, UpdateTasksList)