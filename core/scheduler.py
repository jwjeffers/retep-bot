from __future__ import annotations
"""Bell-curve daily message scheduler for Retep bot."""

import random
import logging
from datetime import datetime
from core.config import Config

logger = logging.getLogger(__name__)


class DailySchedule:
    """
    Generates and manages a daily schedule of message times using a
    bell-curve (normal) distribution centered on the midpoint of active hours.

    The schedule ensures:
    - Times fall within the configured active hours window
    - Minimum 1-hour spacing between messages
    - Natural, human-like clustering around mid-afternoon/evening
    """

    def __init__(self):
        self._scheduled_times: list[datetime] = []
        self._sent_times: set[int] = set()  # indices of already-sent times
        self._schedule_date: datetime | None = None

    @property
    def remaining_count(self) -> int:
        """How many messages are left to send today."""
        return len(self._scheduled_times) - len(self._sent_times)

    def generate(self, now: datetime | None = None, active_hours: list[int] | None = None) -> list[datetime]:
        """
        Generate today's message schedule using a bell-curve distribution.

        Args:
            now: Current datetime (defaults to now). Used for testing.
            active_hours: Optional list of hours (0-23) when the server is active.
                         If provided, messages will only be scheduled during these hours.

        Returns:
            Sorted list of scheduled datetime objects for today.
        """
        if now is None:
            now = datetime.now()

        self._schedule_date = now.date()
        self._sent_times.clear()

        n_messages = Config.MESSAGES_PER_DAY

        if active_hours and len(active_hours) >= 2:
            start_hour = min(active_hours)
            end_hour = max(active_hours) + 1  # +1 so we can schedule up to :59 of the last hour
        else:
            start_hour = Config.ACTIVE_HOURS_START
            end_hour = Config.ACTIVE_HOURS_END

        # Center of the active window
        center_hour = (start_hour + end_hour) / 2.0
        # Standard deviation — ~2.5 hours gives nice spread
        std_dev = (end_hour - start_hour) / 5.0

        times: list[datetime] = []
        max_attempts = n_messages * 20  # Safety valve
        attempts = 0

        while len(times) < n_messages and attempts < max_attempts:
            attempts += 1

            # Draw from normal distribution
            hour = random.gauss(center_hour, std_dev)

            # Clamp to active window
            hour = max(start_hour, min(end_hour - 0.1, hour))

            # Convert to datetime
            hours_int = int(hour)
            minutes = int((hour - hours_int) * 60)
            # Add some random seconds for naturalness
            seconds = random.randint(0, 59)

            candidate = now.replace(
                hour=hours_int,
                minute=minutes,
                second=seconds,
                microsecond=0,
            )

            # Skip times that have already passed
            if candidate <= now:
                continue

            # Enforce minimum 1-hour spacing
            too_close = any(
                abs((candidate - existing).total_seconds()) < 3600
                for existing in times
            )
            if too_close:
                continue

            times.append(candidate)

        # Sort chronologically
        times.sort()
        self._scheduled_times = times

        logger.info(
            "Generated daily schedule with %d messages: %s",
            len(times),
            [t.strftime("%H:%M:%S") for t in times],
        )
        return times

    def mark_sent(self, index: int) -> None:
        """Mark a scheduled time as sent."""
        self._sent_times.add(index)

    def check_due(self, now: datetime | None = None) -> int | None:
        """
        Check if any scheduled message is due.

        Returns:
            The index of the due message, or None if nothing is due.
        """
        if now is None:
            now = datetime.now()

        # If we're on a new day, the schedule is stale
        if self._schedule_date and now.date() != self._schedule_date:
            return None

        for i, scheduled_time in enumerate(self._scheduled_times):
            if i in self._sent_times:
                continue
            # Message is due if its scheduled time has passed
            if now >= scheduled_time:
                return i

        return None

    def is_stale(self, now: datetime | None = None) -> bool:
        """Check if the schedule needs regeneration (new day or empty)."""
        if now is None:
            now = datetime.now()
        if self._schedule_date is None:
            return True
        return now.date() != self._schedule_date

    def status_summary(self) -> str:
        """Human-readable status string."""
        if not self._scheduled_times:
            return "No schedule generated yet."

        lines = []
        for i, t in enumerate(self._scheduled_times):
            status = "✅ sent" if i in self._sent_times else "⏳ pending"
            lines.append(f"  {t.strftime('%I:%M %p')} — {status}")

        remaining = self.remaining_count
        return (
            f"Today's schedule ({len(self._scheduled_times)} messages, "
            f"{remaining} remaining):\n" + "\n".join(lines)
        )
