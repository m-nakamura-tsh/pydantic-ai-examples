import os
import tempfile
import pytest
import pytest_asyncio
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, Mock
from slack_bot.models import Task, TaskStatus


@pytest.mark.asyncio
async def test_handle_run_task():
    from slack_bot.app import SlackBot
    
    with patch("slack_bot.app.AsyncApp") as mock_app:
        with patch("slack_bot.app.AsyncSocketModeHandler"):
            with patch("slack_bot.app.init_db") as mock_init_db:
                mock_session = MagicMock()
                mock_init_db.return_value = lambda: mock_session
                
                bot = SlackBot("xapp-test-token", "xoxb-test-token")
                bot.client = AsyncMock()
                
                with patch.object(bot.task_manager, "submit_task") as mock_submit:
                    mock_submit.return_value = MagicMock()
                    
                    with patch("asyncio.create_task"):
                        await bot._handle_run_task(
                            channel="C12345",
                            thread_ts="1234567890.123456",
                            user="U12345",
                            client=bot.client
                        )
                
                mock_session.add.assert_called_once()
                mock_session.commit.assert_called_once()
                bot.client.chat_postMessage.assert_called_once()


@pytest.mark.asyncio
async def test_monitor_task():
    from slack_bot.app import SlackBot
    
    with patch("slack_bot.app.AsyncApp"):
        with patch("slack_bot.app.AsyncSocketModeHandler"):
            with patch("slack_bot.app.init_db") as mock_init_db:
                mock_session = MagicMock()
                mock_task = MagicMock()
                mock_task.status = TaskStatus.PENDING
                mock_session.query.return_value.filter_by.return_value.first.return_value = mock_task
                mock_init_db.return_value = lambda: mock_session
                
                bot = SlackBot("xapp-test-token", "xoxb-test-token")
                bot.client = AsyncMock()
                
                with patch("asyncio.sleep"):
                    await bot._monitor_task(
                        task_id="test-task-id",
                        channel="C12345",
                        thread_ts="1234567890.123456",
                        client=bot.client
                    )
                
                assert mock_task.status == TaskStatus.AWAITING_CONFIRMATION
                mock_session.commit.assert_called_once()
                bot.client.chat_postMessage.assert_called_once()


@pytest.mark.asyncio
async def test_handle_approval_approved():
    from slack_bot.app import SlackBot
    
    mock_body = {
        "actions": [{"value": "test-task-id"}]
    }
    
    with patch("slack_bot.app.AsyncApp"):
        with patch("slack_bot.app.AsyncSocketModeHandler"):
            with patch("slack_bot.app.init_db") as mock_init_db:
                mock_session = MagicMock()
                mock_task = MagicMock()
                mock_task.task_id = "test-task-id"
                mock_task.channel_id = "C12345"
                mock_task.thread_ts = "1234567890.123456"
                mock_task.status = TaskStatus.AWAITING_CONFIRMATION
                mock_session.query.return_value.filter_by.return_value.first.return_value = mock_task
                mock_init_db.return_value = lambda: mock_session
                
                bot = SlackBot("xapp-test-token", "xoxb-test-token")
                bot.client = AsyncMock()
                
                with patch.object(bot.task_manager, "continue_task") as mock_continue:
                    mock_continue.return_value = MagicMock()
                    
                    with patch("asyncio.sleep"):
                        await bot._handle_approval(
                            body=mock_body,
                            client=bot.client,
                            approved=True
                        )
                
                # Task status will be COMPLETED after the full flow
                assert mock_task.status == TaskStatus.COMPLETED
                mock_session.commit.assert_called()
                bot.client.chat_postMessage.assert_called()


@pytest.mark.asyncio
async def test_handle_approval_rejected():
    from slack_bot.app import SlackBot
    
    mock_body = {
        "actions": [{"value": "test-task-id"}]
    }
    
    with patch("slack_bot.app.AsyncApp"):
        with patch("slack_bot.app.AsyncSocketModeHandler"):
            with patch("slack_bot.app.init_db") as mock_init_db:
                mock_session = MagicMock()
                mock_task = MagicMock()
                mock_task.task_id = "test-task-id"
                mock_task.channel_id = "C12345"
                mock_task.thread_ts = "1234567890.123456"
                mock_task.status = TaskStatus.AWAITING_CONFIRMATION
                mock_session.query.return_value.filter_by.return_value.first.return_value = mock_task
                mock_init_db.return_value = lambda: mock_session
                
                bot = SlackBot("xapp-test-token", "xoxb-test-token")
                bot.client = AsyncMock()
                
                with patch.object(bot.task_manager, "continue_task") as mock_continue:
                    mock_continue.return_value = MagicMock()
                    
                    with patch("asyncio.sleep"):
                        await bot._handle_approval(
                            body=mock_body,
                            client=bot.client,
                            approved=False,
                            rejection_reason="安全でないため"
                        )
                
                assert mock_task.status == TaskStatus.REJECTED
                assert mock_task.rejection_reason == "安全でないため"
                mock_session.commit.assert_called()
                bot.client.chat_postMessage.assert_called()