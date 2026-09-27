"""
GitHub Actions Workflow Dispatcher for Scheme-Intel Telegram Queries (Stage 3).
Triggers 04-telegram-query.yml via repository_dispatch with request context.
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional
import requests

from ..logger import get_logger

logger = get_logger(__name__)


class GitHubWorkflowDispatcher:
    """Dispatches complex Telegram queries to GitHub Actions 04-telegram-query.yml."""

    def __init__(
        self,
        repository: Optional[str] = None,
        token: Optional[str] = None,
    ):
        self.repository = (
            repository
            or os.getenv("GITHUB_REPOSITORY")
            or "botv99/scheme-intel"
        )
        self.token = (
            token
            or os.getenv("GITHUB_TOKEN")
            or os.getenv("GH_TOKEN")
            or os.getenv("GITHUB_PAT")
        )
        if not self.token:
            try:
                import shutil
                import subprocess
                if shutil.which("gh"):
                    res = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=5)
                    if res.returncode == 0 and res.stdout.strip():
                        self.token = res.stdout.strip()
            except Exception:
                pass

    def dispatch_query(
        self,
        request_id: str,
        chat_id: str,
        query: str,
        user_id: Optional[str] = None,
        normalized_query: str = "",
        intent: str = "COMPLEX_QUERY",
        scheme_id: Optional[str] = "gobardhan",
        symbol: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Trigger GitHub repository_dispatch for event_type 'telegram_query'.
        Payload contains all context needed by 04-telegram-query.yml.
        """
        if not self.token:
            logger.warning(
                "[WORKFLOW DISPATCH] GITHUB_TOKEN not configured. Cannot trigger 04-telegram-query.yml for request %s.",
                request_id,
            )
            return {
                "success": False,
                "error": "GITHUB_TOKEN not configured",
                "request_id": request_id,
            }

        url = f"https://api.github.com/repos/{self.repository}/dispatches"
        headers = {
            "Accept": "application/vnd.github.v3+json",
            "Authorization": f"Bearer {self.token}",
        }

        client_payload = {
            "request_id": request_id,
            "user_id": str(user_id) if user_id is not None else None,
            "chat_id": str(chat_id),
            "query": query,
            "normalized_query": normalized_query or query.lower().strip(),
            "intent": intent,
            "scheme_id": scheme_id or "gobardhan",
            "symbol": symbol,
        }

        body = {
            "event_type": "telegram_query",
            "client_payload": client_payload,
        }

        try:
            logger.info(
                "[WORKFLOW DISPATCH] Triggering 04-telegram-query for request %s (chat_id=%s, repo=%s)...",
                request_id,
                chat_id,
                self.repository,
            )
            resp = requests.post(url, json=body, headers=headers, timeout=15)

            if resp.status_code == 204:
                logger.info(
                    "[WORKFLOW DISPATCH] Successfully triggered repository_dispatch for request %s.",
                    request_id,
                )
                return {
                    "success": True,
                    "status_code": 204,
                    "request_id": request_id,
                }
            else:
                err_text = resp.text[:200]
                logger.error(
                    "[WORKFLOW DISPATCH] GitHub returned HTTP %d for request %s: %s",
                    resp.status_code,
                    request_id,
                    err_text,
                )
                return {
                    "success": False,
                    "status_code": resp.status_code,
                    "error": f"GitHub API HTTP {resp.status_code}: {err_text}",
                    "request_id": request_id,
                }
        except requests.RequestException as e:
            logger.error(
                "[WORKFLOW DISPATCH] Network error triggering workflow for request %s: %s",
                request_id,
                e,
            )
            return {
                "success": False,
                "error": str(e),
                "request_id": request_id,
            }
