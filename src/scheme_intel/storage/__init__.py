"""
Storage Subsystem.
Manages SQLite database connections, repositories, and migrations.
"""
from .database import Stage2Database, DEFAULT_STAGE2_DB_PATH
from .migrations import apply_migrations

__all__ = [
    "Stage2Database",
    "DEFAULT_STAGE2_DB_PATH",
    "apply_migrations",
]
