from datetime import datetime, UTC
from sqlalchemy import create_engine, Column, String, DateTime, Enum as SQLEnum
from sqlalchemy.orm import declarative_base, sessionmaker
import enum

Base = declarative_base()


class TaskStatus(enum.Enum):
    PENDING = "pending"
    AWAITING_CONFIRMATION = "awaiting_confirmation"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"


class Task(Base):
    __tablename__ = "tasks"

    task_id = Column(String, primary_key=True)
    channel_id = Column(String, nullable=False)
    thread_ts = Column(String, nullable=False)
    user_id = Column(String, nullable=False)
    status = Column(SQLEnum(TaskStatus), default=TaskStatus.PENDING)
    created_at = Column(DateTime, default=lambda: datetime.now(UTC))
    updated_at = Column(DateTime, default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))
    rejection_reason = Column(String, nullable=True)


def init_db(db_path: str = "slack_bot.db"):
    engine = create_engine(f"sqlite:///{db_path}", echo=False)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session