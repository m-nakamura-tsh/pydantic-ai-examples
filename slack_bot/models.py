from datetime import datetime, UTC
from typing import Optional, List, Dict, Any
from contextlib import contextmanager
from sqlalchemy import create_engine, String, DateTime, Enum as SQLEnum, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from pydantic_core import to_jsonable_python
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelMessage
import enum


class Base(DeclarativeBase):
    pass


class TaskStatus(enum.Enum):
    PENDING = "pending"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    APPROVED = "approved"
    RETRY = "retry"
    COMPLETED = "completed"


class Task(Base):
    __tablename__ = "tasks"

    task_id: Mapped[str] = mapped_column(String, primary_key=True)
    channel_id: Mapped[str] = mapped_column(String, nullable=False)
    thread_ts: Mapped[str] = mapped_column(String, nullable=False)
    user_id: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[TaskStatus] = mapped_column(SQLEnum(TaskStatus), default=TaskStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, 
        default=lambda: datetime.now(UTC), 
        onupdate=lambda: datetime.now(UTC)
    )
    rejection_reason: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    model_messages: Mapped[Optional[List[Dict[str, Any]]]] = mapped_column(JSON, nullable=True)


def init_db(db_path: str = "slack_bot.db"):
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session


@contextmanager
def get_session(Session):
    """セッション管理用のコンテキストマネージャー"""
    session = Session()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


class TaskRepository:
    """タスクのデータベース操作を管理するリポジトリクラス"""
    
    def __init__(self, session_factory):
        self.Session = session_factory
    
    def create_task(
        self, 
        task_id: str, 
        channel_id: str, 
        thread_ts: str, 
        user_id: str,
        status: TaskStatus = TaskStatus.PENDING
    ) -> Task:
        """新規タスクを作成して保存"""
        session = self.Session()
        try:
            task = Task(
                task_id=task_id,
                channel_id=channel_id,
                thread_ts=thread_ts,
                user_id=user_id,
                status=status
            )
            session.add(task)
            session.commit()
            # 必要な属性を読み込んでから返す
            session.refresh(task)
            return task
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def get_task(self, task_id: str) -> Optional[Task]:
        """IDでタスクを取得"""
        session = self.Session()
        try:
            task = session.query(Task).filter_by(task_id=task_id).first()
            if task:
                # 必要な属性を読み込んでから返す
                session.refresh(task)
            return task
        finally:
            session.close()
    
    def update_status(
        self, 
        task_id: str, 
        status: TaskStatus, 
        rejection_reason: Optional[str] = None
    ) -> Optional[Task]:
        """タスクのステータスを更新"""
        session = self.Session()
        try:
            task = session.query(Task).filter_by(task_id=task_id).first()
            if task:
                task.status = status
                task.updated_at = datetime.now(UTC)
                if rejection_reason is not None:
                    task.rejection_reason = rejection_reason
                session.commit()
                # 必要な属性を読み込んでから返す
                session.refresh(task)
                return task
            return None
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def approve_task(self, task_id: str) -> Optional[Task]:
        """タスクを承認"""
        return self.update_status(task_id, TaskStatus.APPROVED)
    
    def retry_task(self, task_id: str, retry_reason: str) -> Optional[Task]:
        """タスクを拒否"""
        return self.update_status(task_id, TaskStatus.RETRY, retry_reason)
    
    def complete_task(self, task_id: str) -> Optional[Task]:
        """タスクを完了"""
        return self.update_status(task_id, TaskStatus.COMPLETED)
    
    def set_awaiting_confirmation(self, task_id: str) -> Optional[Task]:
        """タスクを確認待ち状態に設定"""
        return self.update_status(task_id, TaskStatus.AWAITING_CONFIRMATION)

    
    def update_model_messages(self, task_id: str, messages: List[ModelMessage]) -> Optional[Task]:
        """ModelMessageリストをJSON形式で保存"""
        session = self.Session()
        try:
            task = session.query(Task).filter_by(task_id=task_id).first()
            if task:
                # to_jsonable_pythonでJSON互換形式に変換
                task.model_messages = to_jsonable_python(messages)
                task.updated_at = datetime.now(UTC)
                session.commit()
                session.refresh(task)
                return task
            return None
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def append_model_message(self, task_id: str, message: ModelMessage) -> Optional[Task]:
        """既存のメッセージリストに新しいメッセージを追加"""
        session = self.Session()
        try:
            task = session.query(Task).filter_by(task_id=task_id).first()
            if task:
                # 既存のメッセージを取得
                existing_messages = []
                if task.model_messages:
                    existing_messages = ModelMessagesTypeAdapter.validate_python(task.model_messages)
                
                # 新しいメッセージを追加
                existing_messages.append(message)
                
                # JSON形式で保存
                task.model_messages = to_jsonable_python(existing_messages)
                task.updated_at = datetime.now(UTC)
                session.commit()
                session.refresh(task)
                return task
            return None
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def get_model_messages(self, task_id: str) -> List[ModelMessage]:
        """保存されたJSONからModelMessageリストを復元"""
        task = self.get_task(task_id)
        if task and task.model_messages:
            # ModelMessagesTypeAdapterで復元
            return ModelMessagesTypeAdapter.validate_python(task.model_messages)
        return []
