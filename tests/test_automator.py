from autopayroll.automator import TimesheetAutomator

match = TimesheetAutomator._values_match


class TestValuesMatch:
    def test_exact_string_match(self):
        assert match("start", "14:00", "14:00") is True

    def test_time_reformatted_by_peoplesoft(self):
        # PeopleSoft echoes "14:00" back as "2:00PM"; still a match.
        assert match("end", "16:00", "4:00PM") is True
        assert match("start", "09:00", "9:00AM") is True

    def test_time_mismatch(self):
        assert match("start", "14:00", "3:00PM") is False

    def test_date_reformatted(self):
        assert match("date", "07/09/2026", "07/09/2026") is True
        assert match("date", "07/09/2026", "2026-07-09") is True

    def test_date_mismatch(self):
        assert match("date", "07/09/2026", "07/10/2026") is False

    def test_empty_field_is_failure(self):
        assert match("start", "14:00", "") is False
        assert match("start", "14:00", None) is False

    def test_unparseable_is_unconfirmed(self):
        assert match("start", "14:00", "garbage") is None
