"""Build timesheet rows from a weekly schedule CSV instead of scraping TRAC.

The CSV lists a recurring week, one shift per row (a day may have several):

    day,start,stop
    mon,11:00,13:00
    tue,11:00,14:00
    tue,16:00,18:00

Each row is applied to every matching weekday in the selected pay period, and
the times are entered exactly as written (no rounding).

To give the two weeks of a pay period different hours, add a ``week`` column
(1 = first week of the period, 2 = second):

    day,start,stop,week
    mon,11:00,13:00,1
    mon,14:00,16:00,2
    fri,09:00,10:00,

A blank week means the row applies to both weeks. If only one week number is
used (or the column is absent), that week is repeated for both weeks.
"""

import logging
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

from autopayroll.timeblocks import ANCHOR_START, PERIOD_DAYS

log = logging.getLogger(__name__)

_DAYS = {
    name: i
    for i, names in enumerate(
        [
            ("mon", "monday"),
            ("tue", "tues", "tuesday"),
            ("wed", "weds", "wednesday"),
            ("thu", "thur", "thurs", "thursday"),
            ("fri", "friday"),
            ("sat", "saturday"),
            ("sun", "sunday"),
        ]
    )
    for name in names
}


def _parse_time(text: str, line: int) -> datetime:
    text = str(text).strip()
    for fmt in ("%H:%M", "%I:%M%p", "%I:%M %p"):
        try:
            return datetime.strptime(text.upper(), fmt)
        except ValueError:
            continue
    raise ValueError(f"Line {line}: unrecognized time {text!r} (use HH:MM, e.g. 14:00).")


def _parse_week(value, line: int) -> int | None:
    if pd.isna(value) or not str(value).strip():
        return None
    text = str(value).strip()
    if text not in ("1", "2"):
        raise ValueError(f"Line {line}: unknown week {value!r} (use 1, 2, or blank).")
    return int(text)


def week_of_period(day: date) -> int:
    """Return 1 or 2: which week of its two-week pay period `day` falls in."""
    return (day - ANCHOR_START).days % PERIOD_DAYS // 7 + 1


def read_schedule(csv_path) -> list[tuple[int | None, int, str, str]]:
    """Read and validate the schedule; return (week, weekday, start, stop) tuples.

    Week is 1 or 2, or None when the shift applies to both weeks; it is None for
    every shift unless both weeks are defined. Weekday is 0=Monday. Times are
    normalized to 24-hour HH:MM.
    """
    csv_path = Path(csv_path).expanduser()
    if not csv_path.exists():
        raise FileNotFoundError(f"Schedule CSV not found: {csv_path}")

    raw = pd.read_csv(csv_path, dtype=str, skipinitialspace=True)
    raw.columns = [c.strip().lower() for c in raw.columns]
    missing = {"day", "start", "stop"} - set(raw.columns)
    if missing:
        raise ValueError(
            f"Schedule CSV is missing column(s): {', '.join(sorted(missing))}. "
            "Expected a header of: day,start,stop"
        )

    shifts = []
    for i, row in raw.dropna(how="all").iterrows():
        line = int(i) + 2  # 1-based, after the header
        week = _parse_week(row.get("week"), line)
        day = str(row["day"]).strip().lower()
        if day not in _DAYS:
            raise ValueError(f"Line {line}: unknown day {row['day']!r} (use mon..sun).")
        start = _parse_time(row["start"], line)
        stop = _parse_time(row["stop"], line)
        if stop <= start:
            raise ValueError(
                f"Line {line}: stop {row['stop']} is not after start {row['start']}."
            )
        shifts.append(
            (week, _DAYS[day], start.strftime("%H:%M"), stop.strftime("%H:%M"))
        )

    if not shifts:
        raise ValueError(f"Schedule CSV has no shifts: {csv_path}")

    weeks = {week for week, *_ in shifts if week is not None}
    if len(weeks) < 2:
        if weeks:
            log.info("Only week %d defined; repeating it for both weeks.", *weeks)
        shifts = [(None, *rest) for _, *rest in shifts]
    return shifts


def build_timesheet(csv_path, start_filter: str, end_filter: str) -> pd.DataFrame:
    """Expand the weekly schedule across [start_filter, end_filter] (inclusive).

    Returns a frame with the same columns the automator and summary expect
    from AttendanceParser.parse, indexed by date.
    """
    shifts = read_schedule(csv_path)
    first = date.fromisoformat(start_filter)
    last = date.fromisoformat(end_filter)

    entries = []
    day = first
    while day <= last:
        week = week_of_period(day)
        for shift_week, weekday, start, stop in shifts:
            if weekday != day.weekday() or shift_week not in (None, week):
                continue
            minutes = (
                datetime.strptime(stop, "%H:%M") - datetime.strptime(start, "%H:%M")
            ).seconds // 60
            entries.append(
                {
                    "date": pd.Timestamp(day),
                    "start_time": start,
                    "end_time": stop,
                    "duration_mins": minutes,
                    "billed_time_mins": minutes,
                    "billed_time_hours": minutes / 60.0,
                }
            )
        day += timedelta(days=1)

    df = pd.DataFrame(
        entries,
        columns=[
            "date",
            "start_time",
            "end_time",
            "duration_mins",
            "billed_time_mins",
            "billed_time_hours",
        ],
    )
    df = df.set_index("date").sort_values(["date", "start_time"])
    df["formatted_date"] = df.index.strftime("%m/%d/%Y")
    df["day_of_week"] = df.index.day_name()
    log.info("Built %d entries from schedule %s.", len(df), csv_path)
    return df
