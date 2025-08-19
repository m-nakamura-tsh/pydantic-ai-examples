import asyncio
import time
import uuid
from concurrent.futures import ProcessPoolExecutor
from typing import Callable, Optional


def dummy_task(task_id: str, sleep_duration: int = 10):
    print(f"Task {task_id} started")
    time.sleep(sleep_duration / 2)
    
    print(f"Task {task_id} reached confirmation point")
    return {"task_id": task_id, "needs_confirmation": True}


def continue_task_after_confirmation(task_id: str, approved: bool, rejection_reason: Optional[str] = None):
    if approved:
        print(f"Task {task_id} approved, continuing...")
        time.sleep(5)
        print(f"Task {task_id} completed successfully")
        return {"task_id": task_id, "status": "completed"}
    else:
        print(f"Task {task_id} rejected. Reason: {rejection_reason}")
        return {"task_id": task_id, "status": "rejected", "reason": rejection_reason}


class TaskManager:
    def __init__(self):
        self.executor = ProcessPoolExecutor(max_workers=4)
        self.active_tasks = {}

    def submit_task(self, task_id: str) -> asyncio.Future:
        future = self.executor.submit(dummy_task, task_id)
        self.active_tasks[task_id] = future
        return future

    def continue_task(self, task_id: str, approved: bool, rejection_reason: Optional[str] = None) -> asyncio.Future:
        future = self.executor.submit(continue_task_after_confirmation, task_id, approved, rejection_reason)
        return future

    def shutdown(self):
        self.executor.shutdown(wait=True)