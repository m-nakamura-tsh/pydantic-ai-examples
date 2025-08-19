import os
import tempfile
import pytest
from datetime import datetime
from slack_bot.models import init_db, Task, TaskStatus


@pytest.fixture
def test_db():
    with tempfile.NamedTemporaryFile(delete=False, suffix=".db") as tmp:
        db_path = tmp.name
    
    Session = init_db(db_path)
    yield Session
    
    os.unlink(db_path)


def test_task_creation(test_db):
    session = test_db()
    
    task = Task(
        task_id="test-123",
        channel_id="C12345",
        thread_ts="1234567890.123456",
        user_id="U12345",
        status=TaskStatus.PENDING
    )
    
    session.add(task)
    session.commit()
    
    retrieved_task = session.query(Task).filter_by(task_id="test-123").first()
    
    assert retrieved_task is not None
    assert retrieved_task.task_id == "test-123"
    assert retrieved_task.channel_id == "C12345"
    assert retrieved_task.thread_ts == "1234567890.123456"
    assert retrieved_task.user_id == "U12345"
    assert retrieved_task.status == TaskStatus.PENDING
    assert retrieved_task.rejection_reason is None
    
    session.close()


def test_task_status_update(test_db):
    session = test_db()
    
    task = Task(
        task_id="test-456",
        channel_id="C12345",
        thread_ts="1234567890.123456",
        user_id="U12345",
        status=TaskStatus.PENDING
    )
    
    session.add(task)
    session.commit()
    
    task.status = TaskStatus.AWAITING_CONFIRMATION
    session.commit()
    
    retrieved_task = session.query(Task).filter_by(task_id="test-456").first()
    assert retrieved_task.status == TaskStatus.AWAITING_CONFIRMATION
    
    task.status = TaskStatus.REJECTED
    task.rejection_reason = "Not appropriate for production"
    session.commit()
    
    retrieved_task = session.query(Task).filter_by(task_id="test-456").first()
    assert retrieved_task.status == TaskStatus.REJECTED
    assert retrieved_task.rejection_reason == "Not appropriate for production"
    
    session.close()


def test_multiple_tasks(test_db):
    session = test_db()
    
    tasks = [
        Task(
            task_id=f"task-{i}",
            channel_id=f"C{i:05d}",
            thread_ts=f"123456789{i}.123456",
            user_id=f"U{i:05d}",
            status=TaskStatus.PENDING
        )
        for i in range(5)
    ]
    
    for task in tasks:
        session.add(task)
    session.commit()
    
    all_tasks = session.query(Task).all()
    assert len(all_tasks) == 5
    
    pending_tasks = session.query(Task).filter_by(status=TaskStatus.PENDING).all()
    assert len(pending_tasks) == 5
    
    session.close()