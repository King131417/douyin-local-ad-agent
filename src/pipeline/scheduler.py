"""
Task Scheduler

Uses APScheduler for periodic data sync.
Runs inside the main process as a background thread.
"""

import logging
import threading
from datetime import date, datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

import pytz

from config.settings import SCHEDULE_CRON_HOUR, SCHEDULE_CRON_MINUTE, SCHEDULE_TIMEZONE
from .etl import ETLPipeline

logger = logging.getLogger(__name__)


class SyncStatus:
    """Thread-safe sync status tracker."""

    def __init__(self):
        self._lock = threading.Lock()
        self.is_syncing = False
        self.last_sync_time: datetime | None = None
        self.last_sync_result: str = "尚未同步"
        self.last_sync_rows: int = 0

    def begin(self):
        with self._lock:
            self.is_syncing = True

    def done(self, rows: int):
        with self._lock:
            self.is_syncing = False
            self.last_sync_time = datetime.now()
            self.last_sync_rows = rows
            self.last_sync_result = "success"

    def failed(self, err: str):
        with self._lock:
            self.is_syncing = False
            self.last_sync_time = datetime.now()
            self.last_sync_result = f"error: {err}"

    def to_dict(self) -> dict:
        with self._lock:
            return {
                "is_syncing": self.is_syncing,
                "last_sync_time": (
                    self.last_sync_time.strftime("%Y-%m-%d %H:%M:%S")
                    if self.last_sync_time
                    else None
                ),
                "last_sync_result": self.last_sync_result,
                "last_sync_rows": self.last_sync_rows,
            }


# Global singleton status — shared between scheduler and Flask routes
sync_status = SyncStatus()


class AdDataScheduler:
    """Background scheduler for periodic ad data sync."""

    def __init__(self, pipeline: ETLPipeline | None = None):
        self.pipeline = pipeline or ETLPipeline()
        self._scheduler = BackgroundScheduler()

    def start(self):
        """Start the background scheduler."""
        self._scheduler.add_job(
            self._sync_job,
            trigger=CronTrigger(
                hour=SCHEDULE_CRON_HOUR,
                minute=SCHEDULE_CRON_MINUTE,
                timezone=pytz.timezone(SCHEDULE_TIMEZONE)
            ),
            id="ad_data_sync",
            name=f"Ad data sync (daily {SCHEDULE_CRON_HOUR:02d}:{SCHEDULE_CRON_MINUTE:02d} {SCHEDULE_TIMEZONE})",
            replace_existing=True,
        )
        self._scheduler.start()
        logger.info(
            "Scheduler started: syncing daily at %02d:%02d (%s)",
            SCHEDULE_CRON_HOUR,
            SCHEDULE_CRON_MINUTE,
            SCHEDULE_TIMEZONE,
        )

    def stop(self):
        """Stop the scheduler."""
        self._scheduler.shutdown(wait=False)
        logger.info("Scheduler stopped")

    def trigger_now(self, target_date: date | None = None):
        """Manually trigger a sync in a background thread (non-blocking)."""
        t = threading.Thread(
            target=self._sync_job,
            kwargs={"target_date": target_date},
            daemon=True,
        )
        t.start()

    def trigger_backfill(self, days: int = 30):
        """Trigger a historical backfill in a background thread."""
        t = threading.Thread(
            target=self._backfill_job,
            kwargs={"days": days},
            daemon=True,
        )
        t.start()

    def _backfill_job(self, days: int = 30):
        """Full backfill job."""
        sync_status.begin()
        try:
            logger.info("=== Starting %d-day backfill ===", days)
            result = self.pipeline.run_backfill(days=days)
            total = sum(result.values())
            sync_status.done(total)
            logger.info("Backfill complete: %d rows", total)
        except Exception as e:
            logger.error("Backfill failed: %s", e, exc_info=True)
            sync_status.failed(str(e))

    def _sync_job(self, target_date: date | None = None):
        """The scheduled sync job."""
        sync_status.begin()
        try:
            logger.info("Starting scheduled data sync...")
            result = self.pipeline.run_daily_sync(target_date)
            # result may be dict {account_id: rows} or int
            total = (
                sum(result.values())
                if isinstance(result, dict)
                else int(result or 0)
            )
            sync_status.done(total)
            logger.info("Scheduled sync done: %d rows", total)
            # Auto-backup after successful sync
            try:
                self.pipeline.storage.backup_database(keep=7)
            except Exception:
                pass  # backup failure is non-critical
        except Exception as e:
            logger.error("Scheduled sync failed: %s", e, exc_info=True)
            sync_status.failed(str(e))

    def run_now(self, target_date: date | None = None):
        """Manually trigger a sync (useful for testing, blocking)."""
        return self.pipeline.run_daily_sync(target_date)
