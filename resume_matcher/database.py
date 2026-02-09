"""Database layer: SQLAlchemy models and session management.

Uses SQLite locally. Swap the DATABASE_URL to PostgreSQL for production.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    String,
    Text,
    create_engine,
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

# ── Configuration ───────────────────────────────────────────────

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data")
os.makedirs(DATA_DIR, exist_ok=True)

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{os.path.join(DATA_DIR, 'resume_matcher.db')}",
)

engine = create_engine(
    DATABASE_URL,
    # SQLite needs check_same_thread=False for FastAPI
    connect_args={"check_same_thread": False} if "sqlite" in DATABASE_URL else {},
    echo=False,
)

SessionLocal = sessionmaker(bind=engine)


# ── Base ────────────────────────────────────────────────────────


class Base(DeclarativeBase):
    pass


# ── Helpers ─────────────────────────────────────────────────────


def _new_id() -> str:
    return uuid4().hex[:12]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ── Models ──────────────────────────────────────────────────────


class ResumeRecord(Base):
    """A parsed resume stored for later use."""

    __tablename__ = "resumes"

    id = Column(String(12), primary_key=True, default=_new_id)
    filename = Column(String(255), nullable=False)
    parsed_json = Column(Text, nullable=False)  # JSON string
    raw_text = Column(Text, default="")
    file_path = Column(String(500), default="")  # path to stored .docx
    created_at = Column(DateTime, default=_utcnow)

    analyses = relationship("AnalysisRecord", back_populates="resume")

    def get_parsed(self) -> dict:
        return json.loads(self.parsed_json)

    def to_summary(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class JobRecord(Base):
    """A parsed job description stored for later use."""

    __tablename__ = "jobs"

    id = Column(String(12), primary_key=True, default=_new_id)
    title = Column(String(500), default="")
    source_url = Column(String(2000), default="")
    parsed_json = Column(Text, nullable=False)  # JSON string
    created_at = Column(DateTime, default=_utcnow)

    analyses = relationship("AnalysisRecord", back_populates="job")

    def get_parsed(self) -> dict:
        return json.loads(self.parsed_json)

    def to_summary(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "source_url": self.source_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


class AnalysisRecord(Base):
    """A match analysis linking a resume to a job description."""

    __tablename__ = "analyses"

    id = Column(String(12), primary_key=True, default=_new_id)
    resume_id = Column(String(12), ForeignKey("resumes.id"), nullable=False)
    job_id = Column(String(12), ForeignKey("jobs.id"), nullable=False)
    match_report = Column(Text, default="{}")  # JSON string
    ats_report = Column(Text, default="{}")  # JSON string
    updated_resume_json = Column(Text, default="{}")  # JSON string
    output_file_path = Column(String(500), default="")
    created_at = Column(DateTime, default=_utcnow)

    resume = relationship("ResumeRecord", back_populates="analyses")
    job = relationship("JobRecord", back_populates="analyses")

    def to_summary(self) -> dict:
        match_data = json.loads(self.match_report) if self.match_report else {}
        return {
            "id": self.id,
            "resume_id": self.resume_id,
            "job_id": self.job_id,
            "overall_score": match_data.get("overall_score", 0),
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── Database initialization ─────────────────────────────────────


def init_db() -> None:
    """Create all tables if they don't exist."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Session:
    """Get a database session. Use as a FastAPI dependency."""
    db = SessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise
