import asyncio
import pytest
from unittest.mock import patch, MagicMock
from slack_bot.background_task import dummy_task, continue_task_after_confirmation, TaskManager


def test_dummy_task():
    with patch("time.sleep"):
        result = dummy_task("test-task-1", sleep_duration=10)
        
        assert result["task_id"] == "test-task-1"
        assert result["needs_confirmation"] is True


def test_continue_task_approved():
    with patch("time.sleep"):
        result = continue_task_after_confirmation("test-task-2", approved=True)
        
        assert result["task_id"] == "test-task-2"
        assert result["status"] == "completed"


def test_continue_task_rejected():
    with patch("time.sleep"):
        result = continue_task_after_confirmation(
            "test-task-3", 
            approved=False, 
            rejection_reason="Not safe to proceed"
        )
        
        assert result["task_id"] == "test-task-3"
        assert result["status"] == "rejected"
        assert result["reason"] == "Not safe to proceed"


def test_task_manager_submit():
    manager = TaskManager()
    
    with patch("slack_bot.background_task.dummy_task") as mock_task:
        mock_task.return_value = {"task_id": "test-task-4", "needs_confirmation": True}
        
        future = manager.submit_task("test-task-4")
        
        assert "test-task-4" in manager.active_tasks
        assert future is not None
    
    manager.shutdown()


def test_task_manager_continue():
    manager = TaskManager()
    
    with patch("slack_bot.background_task.continue_task_after_confirmation") as mock_continue:
        mock_continue.return_value = {"task_id": "test-task-5", "status": "completed"}
        
        future = manager.continue_task("test-task-5", approved=True)
        
        assert future is not None
    
    manager.shutdown()


def test_task_manager_shutdown():
    manager = TaskManager()
    
    with patch.object(manager.executor, "shutdown") as mock_shutdown:
        manager.shutdown()
        mock_shutdown.assert_called_once_with(wait=True)