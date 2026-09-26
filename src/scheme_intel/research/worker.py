"""
Asynchronous Research Worker.
Pulls queued research jobs from SQLite, executes them, persists results,
and dispatches Markdown findings to the requesting Telegram chat.
"""
from __future__ import annotations

import argparse
import time
from typing import Optional

from .models import ResearchJob, ResearchStatus
from .queue import ResearchQueue
from .executor import ResearchExecutor
from .formatter import format_research_failure
from ..notifier import send_telegram
from ..logger import get_logger

logger = get_logger(__name__)


class ResearchWorker:
    """Processes background research requests independently of Telegram polling loops."""

    def __init__(
        self,
        queue: Optional[ResearchQueue] = None,
        executor: Optional[ResearchExecutor] = None,
    ):
        self.queue = queue or ResearchQueue()
        self.executor = executor or ResearchExecutor()

    def process_next_job(self, send_telegram_alert: bool = True) -> Optional[ResearchJob]:
        """Claim and process a single queued job."""
        job = self.queue.claim_next_job()
        if not job:
            return None

        logger.info("Worker starting research job %s: '%s'", job.job_id, job.question)
        try:
            result_text, evidence = self.executor.execute(job)
            self.queue.complete_job(job.job_id, result_text, evidence)

            # Asynchronously send completed result to user's Telegram chat
            if send_telegram_alert and job.chat_id:
                try:
                    send_telegram(result_text, chat_ids=[job.chat_id], parse_mode="Markdown")
                except Exception as e:
                    logger.warning("Failed dispatching research result to Telegram chat %s: %s", job.chat_id, e)

            return self.queue.get_job(job.job_id)
        except Exception as e:
            logger.error("Research job %s failed: %s", job.job_id, e)
            self.queue.fail_job(job.job_id, str(e))
            if send_telegram_alert and job.chat_id:
                try:
                    fail_msg = format_research_failure(job.job_id, job.question, str(e))
                    send_telegram(fail_msg, chat_ids=[job.chat_id], parse_mode="Markdown")
                except Exception:
                    pass
            return self.queue.get_job(job.job_id)

    def process_all(self, max_jobs: int = 10, send_telegram_alert: bool = True) -> int:
        """Process all queued research jobs up to max_jobs."""
        count = 0
        for _ in range(max_jobs):
            job = self.process_next_job(send_telegram_alert=send_telegram_alert)
            if not job:
                break
            count += 1
        logger.info("Processed %d research jobs from queue.", count)
        return count


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Scheme-Intel Research Queue Worker")
    parser.add_argument("--max-jobs", type=int, default=10, help="Maximum jobs to process")
    parser.add_argument("--send", action="store_true", help="Send results via Telegram if chat_id configured")
    args = parser.parse_args()

    worker = ResearchWorker()
    processed = worker.process_all(max_jobs=args.max_jobs, send_telegram_alert=args.send)
    print(f"Processed {processed} research jobs.")
