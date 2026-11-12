import pandas as pd
import pytest

from autopayroll.schedule import build_timesheet, read_schedule
from autopayroll.timeblocks import TimeBlockGenerator


def _write(tmp_path, text):
    path = tmp_path / "schedule.csv"
    path.write_text(text)
    return path


EXAMPLE = """day,start,stop
mon,11:00,13:00
tue,11:00,14:00
tue,16:00,18:00
wed,11:00,13:00
thu,11:00,14:00
"""


class TestBuildTimesheet:
    def test_expands_week_across_period(self, tmp_path):
        # 2026-09-27 (Sun) .. 2026-10-10 (Sat): two of each weekday.
        df = build_timesheet(_write(tmp_path, EXAMPLE), "2026-09-27", "2026-10-10")
        assert len(df) == 10
        assert df["billed_time_hours"].sum() == 24.0
        first = df.iloc[0]
        assert (first["formatted_date"], first["start_time"], first["end_time"]) == (
            "09/28/2026",
            "11:00",
            "13:00",
        )
        # Tuesday's two shifts stay in time order.
        tue = df[df["day_of_week"] == "Tuesday"]
        assert list(tue["start_time"])[:2] == ["11:00", "16:00"]

    def test_round_trips_through_csv_for_automator(self, tmp_path):
        df = build_timesheet(_write(tmp_path, EXAMPLE), "2026-09-27", "2026-10-10")
        out = tmp_path / "out.csv"
        df.to_csv(out)
        back = pd.read_csv(out)
        assert list(back.index) == list(range(10))
        assert back.loc[0, "formatted_date"] == "09/28/2026"

    def test_times_entered_as_written(self, tmp_path):
        path = _write(tmp_path, "day,start,stop\nFriday, 9:07 , 1:52PM\n")
        df = build_timesheet(path, "2026-10-02", "2026-10-02")
        assert list(df["start_time"]) == ["09:07"]
        assert list(df["end_time"]) == ["13:52"]


class TestTwoWeek:
    # Period 13 runs 2026-09-20 (Sun) .. 2026-10-03 (Sat).
    START, END = (d.isoformat() for d in TimeBlockGenerator.period_bounds(13))

    def test_each_week_uses_its_own_shifts(self, tmp_path):
        text = (
            "day,start,stop,week\n"
            "mon,11:00,13:00,1\n"
            "mon,14:00,16:00,2\n"
            "fri,09:00,10:00,\n"
        )
        df = build_timesheet(_write(tmp_path, text), self.START, self.END)
        rows = list(zip(df["formatted_date"], df["start_time"]))
        assert rows == [
            ("09/21/2026", "11:00"),
            ("09/25/2026", "09:00"),
            ("09/28/2026", "14:00"),
            ("10/02/2026", "09:00"),
        ]

    def test_single_week_repeats_for_both(self, tmp_path):
        weekly = EXAMPLE.replace("day,start,stop\n", "day,start,stop,week\n")
        weekly = weekly.replace("\n", ",1\n").replace("week,1\n", "week\n")
        with_week = build_timesheet(_write(tmp_path, weekly), self.START, self.END)
        without = build_timesheet(_write(tmp_path, EXAMPLE), self.START, self.END)
        assert len(with_week) == len(without) == 10
        assert list(with_week.index) == list(without.index)

    def test_week_two_only_repeats_for_both(self, tmp_path):
        text = "day,start,stop,week\nmon,11:00,13:00,2\n"
        df = build_timesheet(_write(tmp_path, text), self.START, self.END)
        assert list(df["formatted_date"]) == ["09/21/2026", "09/28/2026"]


class TestValidation:
    @pytest.mark.parametrize(
        "text,match",
        [
            ("day,start\nmon,11:00\n", "missing column"),
            ("day,start,stop\nfunday,11:00,13:00\n", "unknown day"),
            ("day,start,stop\nmon,eleven,13:00\n", "unrecognized time"),
            ("day,start,stop\nmon,13:00,11:00\n", "not after start"),
            ("day,start,stop\n", "no shifts"),
            ("day,start,stop,week\nmon,11:00,13:00,3\n", "unknown week"),
        ],
    )
    def test_rejects_bad_input(self, tmp_path, text, match):
        with pytest.raises(ValueError, match=match):
            read_schedule(_write(tmp_path, text))

    def test_missing_file(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            read_schedule(tmp_path / "nope.csv")
