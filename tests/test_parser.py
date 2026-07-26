from datetime import datetime
from pathlib import Path

import pytest

from autopayroll.parser import AttendanceParser

FIXTURE = Path(__file__).parent / "fixtures" / "attendance_sample.html"


def _dt(s: str) -> datetime:
    return datetime.strptime(s, "%H:%M")


class TestRounding:
    @pytest.mark.parametrize(
        "start,expected",
        [
            ("11:00", "11:00"),
            ("11:29", "11:00"),
            ("11:30", "12:00"),  # exactly half rounds up
            ("11:31", "12:00"),
        ],
    )
    def test_round_to_nearest_hour(self, start, expected):
        got = AttendanceParser.round_dt_to_nearest_hour(_dt(start))
        assert got.strftime("%H:%M") == expected

    @pytest.mark.parametrize(
        "end,expected",
        [
            ("15:00", "15:00"),
            ("15:07", "15:00"),
            ("15:08", "15:15"),  # 7:30 boundary rounds up
            ("15:11", "15:15"),
            ("15:22", "15:15"),
            ("15:23", "15:30"),
        ],
    )
    def test_round_to_nearest_15min(self, end, expected):
        got = AttendanceParser.round_dt_to_nearest_15min(_dt(end))
        assert got.strftime("%H:%M") == expected

    def test_nearest_hour_midnight_wraparound(self):
        # 23:45 + 30min rounds into the next day's 00:00.
        got = AttendanceParser.round_dt_to_nearest_hour(_dt("23:45"))
        assert got.strftime("%H:%M") == "00:00"


class TestParse:
    def _parse(self, start="2026-07-06", end="2026-07-11"):
        parser = AttendanceParser(html_file=FIXTURE)
        return parser.parse(start, end)

    def test_named_rows_are_filtered_out(self):
        # 4 billable rows total in the fixture; the named student row is dropped.
        parser = AttendanceParser(html_file=FIXTURE)
        df = parser.parse("2026-01-01", "2026-12-31")
        assert len(df) == 4

    def test_date_range_filter_is_inclusive(self):
        df = self._parse("2026-07-06", "2026-07-11")
        # Jul 6, 9, 11 kept; Jul 20 excluded.
        assert len(df) == 3
        assert df["formatted_date"].tolist() == ["07/06/2026", "07/09/2026", "07/11/2026"]

    def test_start_rounds_to_hour_end_to_quarter(self):
        df = self._parse()
        jul9 = df.loc["2026-07-09"]
        # 1:42pm start -> 14:00; 71-min duration -> 14:53 end -> 15:00.
        assert jul9["start_time"] == "14:00"
        assert jul9["end_time"] == "15:00"

    def test_duration_math_hours_and_minutes(self):
        df = self._parse()
        jul9 = df.loc["2026-07-09"]
        assert jul9["duration_mins"] == 71  # 1h 11m
        assert jul9["billed_time_mins"] == 75  # nearest 15
        assert jul9["billed_time_hours"] == 1.25

    def test_duration_hours_only(self):
        df = self._parse()
        jul6 = df.loc["2026-07-06"]
        assert jul6["duration_mins"] == 120  # "2h"
        assert jul6["start_time"] == "12:00"
        assert jul6["end_time"] == "14:00"

    def test_empty_result_raises(self, tmp_path):
        empty = tmp_path / "empty.html"
        empty.write_text("<html><body><table></table></body></html>")
        parser = AttendanceParser(html_file=empty)
        with pytest.raises(ValueError):
            parser.parse("2026-07-06", "2026-07-11")

    def test_missing_file_raises(self, tmp_path):
        parser = AttendanceParser(html_file=tmp_path / "nope.html")
        with pytest.raises(FileNotFoundError):
            parser.parse("2026-07-06", "2026-07-11")

    def test_zero_duration_visit_is_dropped(self, tmp_path):
        # A 0-minute check-in at 12:37p rounds to start 13:00, end 12:30 —
        # end <= start, so the row must be dropped rather than emitted.
        html = tmp_path / "zero.html"
        html.write_text(
            "<html><body><table><tbody>"
            '<tr class="lrow rowOdd">'
            '<td class="lcell" data-field="Name"></td>'
            '<td class="lcell" data-field="Time">Jul 13, 2026,&nbsp; 12<small>37p</small></td>'
            '<td class="lcell" data-field="Dur">0<small>m</small></td>'
            "</tr>"
            '<tr class="lrow rowEven">'
            '<td class="lcell" data-field="Name"></td>'
            '<td class="lcell" data-field="Time">Jul 13, 2026,&nbsp; 2<small>00p</small></td>'
            '<td class="lcell" data-field="Dur">1<small>h</small></td>'
            "</tr>"
            "</tbody></table></body></html>"
        )
        df = AttendanceParser(html_file=html).parse("2026-07-13", "2026-07-13")
        # Only the valid 2:00pm visit survives.
        assert len(df) == 1
        assert df.iloc[0]["start_time"] == "14:00"
