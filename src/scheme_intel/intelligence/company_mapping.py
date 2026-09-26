"""
Company Mapping and Entity Resolution Module.
Resolves news and policy text to scheme watchlist stocks.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional
from ..schemes.registry import SchemeRegistry
from ..schemes.models import SchemeStock


class CompanyMapper:
    """Resolves raw text mentions to scheme watchlist stocks."""

    def __init__(self, scheme_id: Optional[str] = None):
        self.scheme = SchemeRegistry.get(scheme_id) if scheme_id else SchemeRegistry.get_active()

    def find_matching_companies(self, text: str) -> List[SchemeStock]:
        """Find all stocks from the active scheme mentioned in the text."""
        if not text or not self.scheme:
            return []

        text_lower = text.lower()
        matched: List[SchemeStock] = []

        for stock in self.scheme.watchlist:
            # Check company name
            if re.search(r"\b" + re.escape(stock.name.lower()) + r"\b", text_lower):
                matched.append(stock)
                continue

            # Check aliases
            found_alias = False
            for alias in stock.aliases:
                if len(alias) >= 3 and re.search(r"\b" + re.escape(alias.lower()) + r"\b", text_lower):
                    matched.append(stock)
                    found_alias = True
                    break
            if found_alias:
                continue

            # Check mapping keywords
            custom_terms = self.scheme.company_mappings.get(stock.name, [])
            for term in custom_terms:
                if re.search(r"\b" + re.escape(term.lower()) + r"\b", text_lower):
                    matched.append(stock)
                    break

        return matched
