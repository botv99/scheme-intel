"""
Intelligence Subsystem.
Covers news categorization, catalyst extraction, impact evaluation, and company mapping.
"""
from .news import NewsEngine
from .impact import evaluate_stock_catalysts
from .catalysts import extract_catalysts, score_catalyst
from .company_mapping import CompanyMapper

__all__ = [
    "NewsEngine",
    "evaluate_stock_catalysts",
    "extract_catalysts",
    "score_catalyst",
    "CompanyMapper",
]
