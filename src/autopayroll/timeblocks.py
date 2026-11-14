"""Pay-period (time block) generation and selection.

Pay periods are fixed two-week blocks anchored at a known reference date, so any
date maps deterministically to a period index. This lets the generator keep the
on-disk list fresh forever without a hardcoded expiry, and lets the picker
default to the period containing today.
"""

import csv
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import questionary

from autopayroll.errors import UserAbort

log = logging.getLogger(__name__)

# Reference period 0 runs 2026-03-22 .. 2026-04-04 (14 days inclusive of both
# ends). Every period is PERIOD_DAYS long; period k starts ANCHOR + 14*k.
ANCHOR_START = date(2026, 3, 22)
PERIOD_DAYS = 14


class TimeBlockGenerator:
    """Generates consecutive two-week pay periods and saves them to a CSV."""

    def __init__(self, timeblock_path: str = "timeblocks.csv"):
        self.timeblock_path = Path(timeblock_path)

    @staticmethod
    def period_index_for(d: date) -> int:
        """Return the period index k whose two-week window contains date d."""
        return (d - ANCHOR_START).days // PERIOD_DAYS

    @staticmethod
    def period_bounds(k: int) -> tuple[date, date]:
        """Return (start, end) dates for period index k (end is inclusive)."""
        start = ANCHOR_START + timedelta(days=PERIOD_DAYS * k)
        end = start + timedelta(days=PERIOD_DAYS - 1)
        return start, end

    def get_next_n_periods(
        self, start_filter: str, end_filter: str, n: int
    ) -> list[dict]:
        """Legacy API: the given period plus the next n-1 consecutive periods.

        Kept for backwards compatibility. Unlike the old version this includes
        the seed period itself (index 0) rather than starting one period ahead.
        """
        start_dt = datetime.strptime(start_filter, "%Y-%m-%d").date()
        periods = []
        for i in range(n):
            p_start = start_dt + timedelta(days=PERIOD_DAYS * i)
            p_end = p_start + timedelta(days=PERIOD_DAYS - 1)
            periods.append(
                {
                    "period": i,
                    "start": p_start.strftime("%Y-%m-%d"),
                    "end": p_end.strftime("%Y-%m-%d"),
                }
            )
        return periods

    def generate_window(self, today: date, past: int = 2, future: int = 8) -> list[dict]:
        """Build periods from `past` before to `future` after today's period.

        Period numbers are the absolute index k (stable across regenerations),
        so a given pay period always carries the same label.
        """
        current = self.period_index_for(today)
        periods = []
        for k in range(current - past, current + future + 1):
            p_start, p_end = self.period_bounds(k)
            periods.append(
                {
                    "period": k,
                    "start": p_start.strftime("%Y-%m-%d"),
                    "end": p_end.strftime("%Y-%m-%d"),
                }
            )
        return periods

    def export_to_csv(self, periods: list[dict]) -> None:
        with open(self.timeblock_path, "w", newline="") as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=["period", "start", "end"])
            writer.writeheader()
            writer.writerows(periods)
        log.info("Saved %d periods to '%s'.", len(periods), self.timeblock_path)

    def _covers_needed_range(self, today: date, future: int) -> bool:
        """True if the existing file already spans today's period + `future`."""
        if not self.timeblock_path.exists():
            return False
        try:
            with open(self.timeblock_path, newline="") as fp:
                rows = list(csv.DictReader(fp))
            if not rows:
                return False
            starts = [datetime.strptime(r["start"], "%Y-%m-%d").date() for r in rows]
        except (KeyError, ValueError, OSError):
            return False
        current_start, _ = self.period_bounds(self.period_index_for(today))
        needed_last_start, _ = self.period_bounds(
            self.period_index_for(today) + future
        )
        return min(starts) <= current_start and max(starts) >= needed_last_start

    def ensure_fresh(self, today: date | None = None, future: int = 8) -> None:
        """Regenerate the time block file if it's missing or doesn't reach far
        enough ahead of today. Idempotent when the file is already current."""
        today = today or date.today()
        if self._covers_needed_range(today, future):
            return
        log.info("Time blocks stale or missing; regenerating around %s.", today)
        self.export_to_csv(self.generate_window(today, future=future))

    def run(self, start_filter: str, end_filter: str, n: int) -> list[dict]:
        """Convenience: generate consecutive periods from a seed and save."""
        periods = self.get_next_n_periods(start_filter, end_filter, n)
        self.export_to_csv(periods)
        return periods


def read_periods(timeblocks_path) -> list[dict]:
    """Load the saved pay periods as [{"period": k, "start": ..., "end": ...}]."""
    with open(timeblocks_path, newline="") as fp:
        return [
            {"period": int(row["period"]), "start": row["start"], "end": row["end"]}
            for row in csv.DictReader(fp)
        ]


def prompt_for_timeblock(
    timeblocks_path, today: date | None = None
) -> tuple[str, str]:
    """Fuzzy-search prompt for a pay period. Defaults the cursor to the period
    containing today. Returns (start, end); raises UserAbort if cancelled."""
    today = today or date.today()
    try:
        periods = read_periods(timeblocks_path)
    except FileNotFoundError:
        log.error("Could not find %s. Make sure the file exists.", timeblocks_path)
        sys.exit(1)

    choices_dict = {
        f"Period {p['period']:>2}: {p['start']} to {p['end']}": (p["start"], p["end"])
        for p in periods
    }

    # Default the highlighted choice to the period that contains today.
    default_display = None
    today_str = today.strftime("%Y-%m-%d")
    for display, (start, end) in choices_dict.items():
        if start <= today_str <= end:
            default_display = display
            break

    selected_display = questionary.select(
        "Fuzzy find and select a timeblock (type to filter/search):",
        choices=list(choices_dict.keys()),
        default=default_display,
        use_indicator=True,
    ).ask()

    if selected_display is None:
        raise UserAbort("Timeblock selection cancelled.")

    return choices_dict[selected_display]
