"""Parse a saved TRAC attendance listing into a rounded, billable timesheet.

Start times round to the nearest hour and end times to the nearest 15 minutes,
matching how hours are entered on the PeopleSoft timesheet.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
from bs4 import BeautifulSoup

log = logging.getLogger(__name__)


class AttendanceParser:
    def __init__(self, html_file=None, timeblocks_file="timeblocks.csv", pay_rate=17.5):
        self.html_file = Path(html_file) if html_file else None
        self.timeblocks_file = timeblocks_file
        self.pay_rate = pay_rate

    @staticmethod
    def round_dt_to_nearest_hour(dt):
        rounded_dt = dt + timedelta(minutes=30)
        return rounded_dt.replace(minute=0, second=0, microsecond=0)

    @staticmethod
    def round_dt_to_nearest_15min(dt):
        half_interval = timedelta(minutes=7, seconds=30)
        rounded_dt = dt + half_interval
        new_minute = (rounded_dt.minute // 15) * 15
        return rounded_dt.replace(minute=new_minute, second=0, microsecond=0)

    def parse(self, start_filter, end_filter):
        if not self.html_file or not self.html_file.exists():
            raise FileNotFoundError(f"HTML Source missing: {self.html_file}")

        with open(self.html_file, encoding="utf-8") as fp:
            soup = BeautifulSoup(fp, "lxml")

        rows = soup.find_all("tr", class_="lrow rowOdd") + soup.find_all(
            "tr", class_="lrow rowEven"
        )
        rows = [
            row
            for row in rows
            if row.find("td", class_="lcell", attrs={"data-field": "Name"}).text == ""
        ]

        visit_data = []
        for row in rows:
            time_cell = row.find("td", attrs={"data-field": "Time"})
            duration_cell = row.find("td", attrs={"data-field": "Dur"})

            if time_cell and duration_cell:
                time_text = time_cell.get_text().replace("\xa0", " ").strip()
                parts = time_text.split(",")
                date_str = parts[0].strip()
                year_str = parts[1].strip()
                time_part_raw = parts[2].strip()

                duration_text = duration_cell.get_text().strip().split(" ")
                log.debug("duration text => %s", duration_text)

                h = next(
                    (cell.replace("h", "") for cell in duration_text if "h" in cell), ""
                ) or "0"
                m = next(
                    (cell.replace("m", "") for cell in duration_text if "m" in cell), ""
                ) or "0"

                total_minutes = (int(h) * 60) + int(m)
                billed_time_mins = round(total_minutes / 15) * 15
                billed_time_hours = billed_time_mins / 60.0

                time_to_parse = (
                    f"{time_part_raw[:-3]}:{time_part_raw[-3:-1]}"
                    f"{time_part_raw[-1].upper()}M"
                )
                start_dt_original = datetime.strptime(time_to_parse, "%I:%M%p")

                adjusted_start_dt = self.round_dt_to_nearest_hour(start_dt_original)
                original_end_dt = start_dt_original + timedelta(minutes=total_minutes)
                adjusted_end_dt = self.round_dt_to_nearest_15min(original_end_dt)

                # A very short visit can round to an end at/before its start
                # (e.g. a 0-minute check-in: start rounds up, end rounds down).
                # Such a row is not billable and PeopleSoft would reject it.
                if adjusted_end_dt <= adjusted_start_dt:
                    log.warning(
                        "Skipping non-billable visit on %s %s (%d min): rounds to "
                        "%s-%s.",
                        date_str,
                        time_part_raw,
                        total_minutes,
                        adjusted_start_dt.strftime("%H:%M"),
                        adjusted_end_dt.strftime("%H:%M"),
                    )
                    continue

                visit_data.append(
                    {
                        "date_str": date_str,
                        "year": year_str,
                        "start_time": adjusted_start_dt.strftime("%H:%M"),
                        "end_time": adjusted_end_dt.strftime("%H:%M"),
                        "original_end_time": original_end_dt.strftime("%H:%M"),
                        "duration_mins": total_minutes,
                        "billed_time_mins": billed_time_mins,
                        "billed_time_hours": billed_time_hours,
                        "net_difference_mins": (
                            adjusted_end_dt - original_end_dt
                        ).total_seconds()
                        / 60,
                    }
                )

        if not visit_data:
            raise ValueError(
                "No visit rows found in the attendance listing. Did the page "
                "finish loading before it was saved?"
            )

        df = pd.DataFrame(visit_data)
        full_date_str = df["date_str"] + " " + df["year"]
        df["date"] = pd.to_datetime(full_date_str, format="%b %d %Y")
        df = df.set_index("date").drop(columns=["date_str", "year"]).sort_index()

        filtered_df = df.loc[start_filter:end_filter].copy()
        filtered_df["formatted_date"] = filtered_df.index.strftime("%m/%d/%Y")
        filtered_df["day_of_week"] = filtered_df.index.day_name()

        return filtered_df

    def run(self, start_filter, end_filter, output_path: Path) -> pd.DataFrame:
        """Parse, print a pay summary, write to `output_path`, return the frame.

        The caller owns `output_path` so the export location has a single source
        of truth (previously the interface and parser each derived it).
        """
        log.info("Parsing date range: %s to %s", start_filter, end_filter)
        df = self.parse(start_filter, end_filter)

        billed_hours = df["billed_time_hours"].sum()
        raw_comp = billed_hours * self.pay_rate
        print(
            f"\nStats:\n\tTotal Billed Hours: {billed_hours}hrs\n"
            f"\tRaw Comp [${raw_comp:.2f}] | Estimate Net [${raw_comp * 0.7:.2f}]"
        )

        output_path = Path(output_path)
        df.to_csv(output_path)
        log.info("Saved export to %s", output_path)
        return df
