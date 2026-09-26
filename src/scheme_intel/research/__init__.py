"""
Asynchronous Deep Research Subsystem.
Provides persistent job queuing, evidence gathering, LLM synthesis, and worker execution.
"""
from .models import ResearchJob, ResearchStatus
from .queue import ResearchQueue
from .executor import ResearchExecutor
from .worker import ResearchWorker
from .formatter import (
    format_research_acknowledgement,
    format_research_result,
    format_research_failure,
)

__all__ = [
    "ResearchJob",
    "ResearchStatus",
    "ResearchQueue",
    "ResearchExecutor",
    "ResearchWorker",
    "format_research_acknowledgement",
    "format_research_result",
    "format_research_failure",
]
