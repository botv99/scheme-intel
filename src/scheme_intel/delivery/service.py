"""
Unified Operational Runtime Service for Scheme-Intel (Stage 3).

Coordinates the Telegram conversational polling bot, asynchronous research worker,
and system health probes in a production-ready, non-blocking process.

Usage:
  python -m scheme_intel.delivery.service [--mode {all,bot,worker}] [--health] [--port PORT]
"""
from __future__ import annotations

import argparse
import http.server
import json
import os
import signal
import socketserver
import sys
import threading
import time
from typing import Any, Dict, Optional

from .telegram_conversation import TelegramConversationHandler
from ..research.worker import ResearchWorker
from ..research.queue import ResearchQueue
from ..intelligence_memory.retrieval import IntelligenceRetrieval
from ..intelligence_memory.models import SnapshotHealthStatus
from ..config import load_dotenv
from ..logger import get_logger

load_dotenv()
logger = get_logger(__name__)


_ACTIVE_SERVICE_INSTANCE: Optional["SchemeIntelService"] = None


def get_system_health(
    data_dir: Optional[str] = None,
    service_instance: Optional["SchemeIntelService"] = None,
) -> Dict[str, Any]:
    """
    Comprehensive, non-destructive health check of the Scheme-Intel runtime.
    Inspects credentials, memory snapshot integrity, queue depth, provider availability,
    and real runtime thread states if service is active.
    Does NOT trigger data ingestion, strategy pipeline, or snapshot rebuilding.
    """
    effective_service = service_instance or _ACTIVE_SERVICE_INSTANCE

    # 1. Telegram configuration
    has_bot_token = bool(os.getenv("TELEGRAM_BOT_TOKEN"))
    has_chat_id = bool(os.getenv("TELEGRAM_CHAT_ID"))

    # 2. Intelligence memory snapshot health
    retrieval = IntelligenceRetrieval(data_dir=data_dir, auto_build_if_missing=False)
    snapshot_status, snapshot, status_msg = retrieval.get_status()
    snapshot_meta = {
        "health_status": snapshot_status.value,
        "message": status_msg,
        "snapshot_id": snapshot.snapshot_id if snapshot else None,
        "age_seconds": snapshot.get_age_seconds() if snapshot else None,
        "age_display": snapshot.get_age_display() if snapshot else None,
        "total_setups": len(snapshot.qualified_setups) if snapshot else 0,
        "total_companies": len(snapshot.companies) if snapshot else 0,
        "schemes": snapshot.scheme_ids if snapshot else [],
    }

    # 3. Research queue status
    queue = ResearchQueue()
    queue_counts = queue.get_status_counts()

    # 4. Request store status
    from .request_store import RequestStore
    req_store = RequestStore()
    recent_requests = len(req_store.list_requests(limit=100))

    # 5. LLM provider keys
    llm_providers = {
        "gemini": bool(os.getenv("GEMINI_API_KEY")),
        "groq": bool(os.getenv("GROQ_API_KEY")),
        "openrouter": bool(os.getenv("OPENROUTER_API_KEY")),
    }

    # 5. Component runtime status
    component_status = (
        effective_service.get_component_status()
        if effective_service
        else {
            "telegram": "UNKNOWN",
            "research_worker": "UNKNOWN",
            "snapshot_syncer": "UNKNOWN",
        }
    )

    # Determine overall status
    is_healthy = True
    issues = []

    if not has_bot_token:
        issues.append("TELEGRAM_BOT_TOKEN is not configured")
    if snapshot_status == SnapshotHealthStatus.MISSING.value:
        issues.append("Intelligence snapshot is missing (run pipeline or refresh)")
    elif snapshot_status == SnapshotHealthStatus.INVALID.value:
        is_healthy = False
        issues.append("Intelligence snapshot is corrupted or invalid")
    elif snapshot_status == SnapshotHealthStatus.STALE.value:
        issues.append("Intelligence snapshot is stale (> freshness threshold)")

    # Check for crashed service threads
    for comp, st in component_status.items():
        if st == "FAILED":
            is_healthy = False
            issues.append(f"Component '{comp}' thread has failed/died")

    status_str = "healthy" if is_healthy and not issues else ("degraded" if is_healthy else "unhealthy")
    telemetry = effective_service.get_telemetry() if effective_service else None

    return {
        "status": status_str,
        "is_healthy": is_healthy,
        "issues": issues,
        "components": component_status,
        "telemetry": telemetry,
        "telegram": {
            "bot_token_configured": has_bot_token,
            "chat_id_configured": has_chat_id,
        },
        "intelligence_memory": snapshot_meta,
        "research_queue": queue_counts,
        "llm_providers": llm_providers,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


class HealthHTTPRequestHandler(http.server.BaseHTTPRequestHandler):
    """Minimal HTTP handler serving JSON health probes for container runtimes."""

    def do_GET(self):
        health = get_system_health()
        status_code = 200 if health["is_healthy"] else 503
        payload = json.dumps(health, indent=2).encode("utf-8")

        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format, *args):
        # Suppress noisy health probe access logs
        return


class SchemeIntelService:
    """Production runtime service managing Bot, Worker, and Syncer lifecycle."""

    def __init__(
        self,
        mode: str = "all",
        poll_interval: float = 2.0,
        worker_poll_interval: float = 3.0,
        stale_recovery_interval: float = 60.0,
        http_port: Optional[int] = None,
        sync_snapshot: bool = True,
        sync_interval: float = 300.0,
    ):
        global _ACTIVE_SERVICE_INSTANCE
        self.mode = mode
        self.poll_interval = poll_interval
        self.worker_poll_interval = worker_poll_interval
        self.stale_recovery_interval = stale_recovery_interval
        self.http_port = http_port
        self.sync_snapshot = sync_snapshot

        from ..intelligence_memory.syncer import SnapshotSyncer

        self.bot_handler = TelegramConversationHandler()
        self.worker = ResearchWorker()
        self.syncer = SnapshotSyncer(
            store=self.bot_handler.router.retriever.store,
            interval_seconds=sync_interval,
            enabled=sync_snapshot,
        )

        self.is_running = False
        self.bot_thread: Optional[threading.Thread] = None
        self.worker_thread: Optional[threading.Thread] = None
        self.syncer_thread: Optional[threading.Thread] = None
        self.http_server: Optional[socketserver.TCPServer] = None
        _ACTIVE_SERVICE_INSTANCE = self

    def get_component_status(self) -> Dict[str, str]:
        """Return live health state of managed runtime threads."""
        status = {}

        if self.mode in ("all", "bot"):
            if self.bot_thread and self.bot_thread.is_alive() and self.bot_handler.is_running:
                status["telegram"] = "RUNNING"
            elif self.bot_handler.is_running and (not self.bot_thread or not self.bot_thread.is_alive()):
                status["telegram"] = "FAILED"
            else:
                status["telegram"] = "STOPPED"
        else:
            status["telegram"] = "DISABLED"

        if self.mode in ("all", "worker"):
            if self.worker_thread and self.worker_thread.is_alive() and self.worker.is_running:
                status["research_worker"] = "RUNNING"
            elif self.worker.is_running and (not self.worker_thread or not self.worker_thread.is_alive()):
                status["research_worker"] = "FAILED"
            else:
                status["research_worker"] = "STOPPED"
        else:
            status["research_worker"] = "DISABLED"

        if self.sync_snapshot and self.syncer.enabled:
            if self.syncer_thread and self.syncer_thread.is_alive() and self.syncer.is_running:
                status["snapshot_syncer"] = "RUNNING"
            else:
                status["snapshot_syncer"] = "STOPPED"
        else:
            status["snapshot_syncer"] = "DISABLED"

        return status

    def get_telemetry(self) -> Dict[str, Any]:
        """Return runtime telemetry including polling state and counters."""
        return {
            "telegram": self.bot_handler.get_metrics(),
            "research_worker": {
                "is_running": self.worker.is_running,
            },
            "snapshot_syncer": {
                "is_running": self.syncer.is_running,
                "enabled": self.syncer.enabled,
                "last_sync_time": (
                    time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self.syncer.last_sync_time))
                    if self.syncer.last_sync_time
                    else None
                ),
            },
        }

    def start(self) -> None:
        """Start components according to configured mode and block until interrupted."""
        self.is_running = True
        logger.info("Initializing Scheme-Intel Service in mode: '%s'", self.mode)

        # Explicit Required Startup Logs
        logger.info("[TELEGRAM] Gateway started")
        if self.mode in ("all", "bot"):
            logger.info("[TELEGRAM] Polling active")
        if self.mode in ("all", "worker"):
            logger.info("[TELEGRAM] Worker active")

        retr = IntelligenceRetrieval(auto_build_if_missing=False)
        _, snap, _ = retr.get_status()
        if snap:
            logger.info("[TELEGRAM] Snapshot available")

        # 1. Optional HTTP probe server (e.g. for Render/Railway/CloudRun)
        port_env = os.getenv("PORT")
        effective_port = self.http_port or (int(port_env) if port_env and port_env.isdigit() else None)
        if effective_port:
            self._start_http_server(effective_port)

        # 2. Snapshot syncer thread (Option A: Pull latest snapshot from GitHub repository)
        if self.sync_snapshot and self.syncer.enabled:
            self.syncer_thread = threading.Thread(
                target=self.syncer.run_forever,
                name="SnapshotSyncerThread",
                daemon=True,
            )
            self.syncer_thread.start()
            logger.info("Snapshot Syncer thread launched.")

        # 3. Worker thread
        if self.mode in ("all", "worker"):
            self.worker_thread = threading.Thread(
                target=self.worker.run_forever,
                kwargs={
                    "poll_interval": self.worker_poll_interval,
                    "stale_recovery_interval": self.stale_recovery_interval,
                    "send_telegram_alert": True,
                },
                name="ResearchWorkerThread",
                daemon=True,
            )
            self.worker_thread.start()
            logger.info("Research Worker thread launched.")

        # 4. Bot handler thread / loop
        if self.mode in ("all", "bot"):
            if self.mode == "bot":
                logger.info("Running Telegram Bot poller directly...")
                self.bot_handler.run_polling(interval_seconds=int(self.poll_interval))
            else:
                self.bot_thread = threading.Thread(
                    target=self.bot_handler.run_polling,
                    kwargs={"interval_seconds": int(self.poll_interval)},
                    name="TelegramBotThread",
                    daemon=True,
                )
                self.bot_thread.start()
                logger.info("Telegram Bot poller thread launched.")

                # Keep main thread alive and supervise running threads
                try:
                    while self.is_running:
                        time.sleep(1.0)
                        if self.is_running and self.bot_thread and not self.bot_thread.is_alive():
                            token = os.getenv("TELEGRAM_BOT_TOKEN")
                            if token:
                                logger.warning("[TELEGRAM] Bot thread terminated unexpectedly. Restarting poller...")
                                self.bot_thread = threading.Thread(
                                    target=self.bot_handler.run_polling,
                                    kwargs={"interval_seconds": int(self.poll_interval)},
                                    name="TelegramBotThread",
                                    daemon=True,
                                )
                                self.bot_thread.start()
                except KeyboardInterrupt:
                    self.stop()
        elif self.mode == "worker":
            try:
                while self.is_running:
                    time.sleep(1.0)
            except KeyboardInterrupt:
                self.stop()

    def stop(self) -> None:
        """Gracefully terminate all running threads and servers."""
        if not self.is_running:
            return
        logger.info("Initiating graceful shutdown of Scheme-Intel Service...")
        self.is_running = False

        self.syncer.stop()
        self.bot_handler.stop()
        self.worker.stop()

        if self.http_server:
            try:
                self.http_server.shutdown()
                self.http_server.server_close()
            except Exception as e:
                logger.debug("Error shutting down HTTP server: %s", e)

        for th in (self.bot_thread, self.worker_thread, self.syncer_thread):
            if th and th.is_alive():
                th.join(timeout=2.0)
        logger.info("Scheme-Intel Service stopped cleanly.")

    def _start_http_server(self, port: int) -> None:
        try:
            class ReusableTCPServer(socketserver.TCPServer):
                allow_reuse_address = True

            self.http_server = ReusableTCPServer(("", port), HealthHTTPRequestHandler)
            http_thread = threading.Thread(target=self.http_server.serve_forever, daemon=True, name="HealthHTTPThread")
            http_thread.start()
            logger.info("HTTP Health Probe listening on port %d", port)
        except Exception as e:
            logger.warning("Could not bind HTTP health probe on port %d: %s", port, e)


def main():
    parser = argparse.ArgumentParser(description="Scheme-Intel Operational Service Runtime")
    parser.add_argument(
        "--mode",
        choices=["all", "bot", "worker"],
        default="all",
        help="Service operational mode (default: all)",
    )
    parser.add_argument(
        "--health",
        action="store_true",
        help="Execute one-shot system health check and exit",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="Optional HTTP port for health probes",
    )
    args = parser.parse_args()

    if args.health:
        health = get_system_health()
        print(json.dumps(health, indent=2))
        sys.exit(0 if health["is_healthy"] else 1)

    service = SchemeIntelService(mode=args.mode, http_port=args.port)

    def _sig_handler(signum, frame):
        logger.info("Termination signal (%s) received.", signum)
        service.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)

    service.start()


if __name__ == "__main__":
    main()
