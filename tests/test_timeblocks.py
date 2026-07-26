import itertools
from datetime import date, timedelta

from autopayroll.timeblocks import ANCHOR_START, PERIOD_DAYS, TimeBlockGenerator


class TestPeriodMath:
    def test_anchor_is_period_zero(self):
        assert TimeBlockGenerator.period_index_for(ANCHOR_START) == 0

    def test_period_index_increments_every_two_weeks(self):
        assert TimeBlockGenerator.period_index_for(ANCHOR_START + timedelta(days=13)) == 0
        assert TimeBlockGenerator.period_index_for(ANCHOR_START + timedelta(days=14)) == 1
        assert TimeBlockGenerator.period_index_for(ANCHOR_START + timedelta(days=28)) == 2

    def test_period_bounds_are_14_day_inclusive_blocks(self):
        start, end = TimeBlockGenerator.period_bounds(0)
        assert start == ANCHOR_START
        assert (end - start).days == PERIOD_DAYS - 1

    def test_bounds_contain_their_index(self):
        for k in range(-3, 20):
            start, end = TimeBlockGenerator.period_bounds(k)
            assert TimeBlockGenerator.period_index_for(start) == k
            assert TimeBlockGenerator.period_index_for(end) == k


class TestGenerateWindow:
    def test_window_count_and_contiguity(self):
        gen = TimeBlockGenerator("unused.csv")
        today = ANCHOR_START + timedelta(days=100)
        periods = gen.generate_window(today, past=2, future=8)
        assert len(periods) == 2 + 8 + 1
        # Consecutive periods are contiguous and 2 weeks apart.
        for a, b in itertools.pairwise(periods):
            a_end = date.fromisoformat(a["end"])
            b_start = date.fromisoformat(b["start"])
            assert b_start == a_end + timedelta(days=1)

    def test_window_includes_current_period(self):
        gen = TimeBlockGenerator("unused.csv")
        today = ANCHOR_START + timedelta(days=100)
        periods = gen.generate_window(today)
        assert any(p["start"] <= today.isoformat() <= p["end"] for p in periods)


class TestLegacyGetNextN:
    def test_includes_seed_period(self):
        gen = TimeBlockGenerator("unused.csv")
        periods = gen.get_next_n_periods("2026-03-22", "2026-04-04", 3)
        assert len(periods) == 3
        assert periods[0]["start"] == "2026-03-22"  # seed is present now


class TestEnsureFresh:
    def test_writes_when_missing(self, tmp_path):
        path = tmp_path / "timeblock.env"
        gen = TimeBlockGenerator(str(path))
        gen.ensure_fresh(today=date(2026, 7, 26))
        assert path.exists()
        assert path.read_text().startswith("period,start,end")

    def test_regenerates_when_stale(self, tmp_path):
        path = tmp_path / "timeblock.env"
        # Seed a file that only covers early-2026 periods.
        TimeBlockGenerator(str(path)).ensure_fresh(today=date(2026, 3, 22))
        first = path.read_text()
        # A much later "today" is not covered, so the file must be rewritten.
        TimeBlockGenerator(str(path)).ensure_fresh(today=date(2027, 6, 1))
        assert path.read_text() != first

    def test_idempotent_when_current(self, tmp_path):
        path = tmp_path / "timeblock.env"
        gen = TimeBlockGenerator(str(path))
        gen.ensure_fresh(today=date(2026, 7, 26))
        before = path.read_text()
        gen.ensure_fresh(today=date(2026, 7, 26))
        assert path.read_text() == before
