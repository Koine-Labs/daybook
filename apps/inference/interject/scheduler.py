"""APScheduler wrapper for Daybook scheduled triggers.

Runs as a persistent process (BlockingScheduler). Registers daily cron jobs
or one-shot date jobs; wraps each job in an error-swallowing shim so a
trigger crash never takes the scheduler down.
"""
from __future__ import annotations

import logging
import traceback
from datetime import datetime
from typing import Any, Callable

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)


class DaybookScheduler:
    """Thin wrapper around APScheduler for Daybook trigger jobs."""

    def __init__(self, *, blocking: bool = True) -> None:
        self.scheduler = (
            BlockingScheduler() if blocking else BackgroundScheduler()
        )
        self._registered: list[str] = []

    def register_daily(
        self,
        *,
        hour: int,
        minute: int,
        func: Callable[..., Any],
        name: str,
        **kwargs: Any,
    ) -> None:
        """Register a job to run every day at hour:minute (local time)."""
        wrapped = _wrap_safe(func, name=name)
        self.scheduler.add_job(
            wrapped,
            CronTrigger(hour=hour, minute=minute),
            id=name,
            name=name,
            kwargs=kwargs,
            replace_existing=True,
        )
        self._registered.append(f"{name} @ {hour:02d}:{minute:02d} daily")

    def register_once(
        self,
        *,
        run_at: datetime,
        func: Callable[..., Any],
        name: str,
        **kwargs: Any,
    ) -> None:
        """Register a one-shot job at the given datetime (used by smoke test)."""
        wrapped = _wrap_safe(func, name=name)
        self.scheduler.add_job(
            wrapped,
            DateTrigger(run_date=run_at),
            id=name,
            name=name,
            kwargs=kwargs,
            replace_existing=True,
        )
        self._registered.append(f"{name} @ {run_at.isoformat()} once")

    def register_interval(
        self,
        *,
        minutes: int,
        func: Callable[..., Any],
        name: str,
        **kwargs: Any,
    ) -> None:
        """Register a job that fires every N minutes around the clock."""
        wrapped = _wrap_safe(func, name=name)
        self.scheduler.add_job(
            wrapped,
            IntervalTrigger(minutes=minutes),
            id=name,
            name=name,
            kwargs=kwargs,
            replace_existing=True,
        )
        self._registered.append(f"{name} every {minutes} min")

    def start(self) -> None:
        """Print registry then start the scheduler. Blocks if blocking=True."""
        for line in self._registered:
            print(f"[scheduler] {line}")
        if not self._registered:
            print("[scheduler] (no jobs registered)")
        self.scheduler.start()

    def shutdown(self, *, wait: bool = False) -> None:
        try:
            self.scheduler.shutdown(wait=wait)
        except Exception as e:  # pragma: no cover
            logger.warning("scheduler shutdown failed: %s", e)


def _wrap_safe(func: Callable[..., Any], *, name: str) -> Callable[..., Any]:
    """Wrap a trigger so exceptions are logged but never crash the scheduler."""

    def runner(**kwargs: Any) -> Any:
        try:
            print(f"[scheduler] firing '{name}' at {datetime.now().isoformat(timespec='seconds')}")
            return func(**kwargs)
        except Exception as e:
            print(f"[scheduler] '{name}' raised: {e}")
            traceback.print_exc()
            return None

    runner.__name__ = f"safe_{name}"
    return runner


__all__ = ["DaybookScheduler"]
