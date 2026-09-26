"""
Data contracts for Asynchronous Deep Research Subsystem.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ResearchStatus(str, Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class ResearchJob(BaseModel):
    """Persistent research task model."""
    job_id: str
    user_id: Optional[str] = None
    chat_id: Optional[str] = None
    question: str
    scheme_id: str = "gobardhan"
    status: ResearchStatus = ResearchStatus.QUEUED
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    result: Optional[str] = None
    evidence: List[Dict[str, Any]] = Field(default_factory=list)
    error: Optional[str] = None
