"""Interactive CLI: menu loop and pipeline orchestration."""

import argparse
import logging
import sys
from enum import Enum

import questionary
from selenium import webdriver
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.support.ui import WebDriverWait

from autopayroll.automator import TimesheetAutomator
from autopayroll.config import ConfigSettings
from autopayroll.errors import AutoPayrollError, UserAbort
from autopayroll.parser import AttendanceParser, print_pay_summary
from autopayroll.schedule import build_timesheet
from autopayroll.scraper import UMBCTimesheetScraper
from autopayroll.timeblocks import prompt_for_timeblock

log = logging.getLogger(__name__)


class ControlFlow(Enum):
    EXIT = 0
    PROCESS = 1
    DRY_RUN = 2
    SCHEDULE = 3


class Interface:
    def __init__(self, dry_run: bool = False, schedule: str | None = None) -> None:
        self.config = ConfigSettings()
        self.dry_run = dry_run
        # Last schedule CSV used; pre-fills the path prompt.
        self.schedule = schedule
        # The WebDriver is started lazily so choosing "Exit" (or a dry run that
        # never needs the browser) doesn't pay Firefox's startup cost.
        self.driver = None
        self.wait: WebDriverWait | None = None
        self.timesheet_mgr: TimesheetAutomator | None = None

    def _ensure_driver(self) -> None:
        if self.driver is not None:
            return
        log.info("Setting up Firefox profile at: %s", self.config.profile_dir)
        options = Options()
        if self.config.profile_dir:
            options.add_argument("-profile")
            options.add_argument(str(self.config.profile_dir))

        log.info("Initializing WebDriver...")
        self.driver = webdriver.Firefox(options=options)
        self.wait = WebDriverWait(self.driver, self.config.wait_time)
        self.timesheet_mgr = TimesheetAutomator(self.driver, self.wait, self.config)

    def _process_timesheet(self, dry_run: bool) -> None:
        start, end = prompt_for_timeblock(self.config.timeblock_path)
        csv_filepath = self.config.data_dir / f"{start}_{end}.csv"

        self._ensure_driver()

        print("[GETTING LATEST TIMESHEET]")
        scraper = UMBCTimesheetScraper(self.driver, self.config)
        scraper.run()

        print(f"[PARSING NEW TIMEBLOCK] => {start} to {end}...")
        parser = AttendanceParser(
            html_file=self.config.html_file,
            timeblocks_file=self.config.timeblock_path,
            pay_rate=self.config.pay_rate,
        )
        df = parser.run(start, end, csv_filepath)
        self._enter_rows(df, csv_filepath, dry_run)

    def _process_schedule(self, dry_run: bool) -> None:
        """Enter the times from a weekly schedule CSV, skipping TRAC entirely."""
        path = questionary.path(
            "Schedule CSV (columns: day,start,stop):",
            default=self.schedule or "",
        ).ask()
        if not path:
            raise UserAbort("No schedule CSV chosen.")
        self.schedule = path

        start, end = prompt_for_timeblock(self.config.timeblock_path)
        csv_filepath = self.config.data_dir / f"{start}_{end}.csv"

        print(f"[BUILDING FROM SCHEDULE] => {start} to {end}...")
        try:
            df = build_timesheet(path, start, end)
        except (OSError, ValueError) as exc:
            raise AutoPayrollError(f"Could not use schedule: {exc}") from exc
        print_pay_summary(df, self.config.pay_rate)
        df.to_csv(csv_filepath)
        log.info("Saved export to %s", csv_filepath)
        self._enter_rows(df, csv_filepath, dry_run)

    def _enter_rows(self, df, csv_filepath, dry_run: bool) -> None:
        if dry_run:
            print(f"\n[DRY RUN] Prepared {len(df)} rows; CSV saved to {csv_filepath}.")
            print("[DRY RUN] Skipping PeopleSoft entry.")
            return

        # Show the rows and confirm before touching PeopleSoft.
        print("\nEntries:")
        print(df[["formatted_date", "day_of_week", "start_time", "end_time"]].to_string())
        proceed = questionary.confirm(
            "Enter these rows into the PeopleSoft timesheet?", default=True
        ).ask()
        if not proceed:
            raise UserAbort("Timesheet entry cancelled by user.")

        self._ensure_driver()
        self.timesheet_mgr.run(str(csv_filepath), self.config.timesheet_url)

    def _process_exit(self) -> None:
        print("\nExiting. Goodbye!")
        if self.driver:
            self.driver.quit()
        sys.exit(0)

    def _process_request(self, request: ControlFlow) -> None:
        try:
            match request:
                case ControlFlow.PROCESS:
                    # --dry-run makes even "Process" parse-only.
                    self._process_timesheet(dry_run=self.dry_run)
                case ControlFlow.DRY_RUN:
                    self._process_timesheet(dry_run=True)
                case ControlFlow.SCHEDULE:
                    self._process_schedule(dry_run=self.dry_run)
                case ControlFlow.EXIT:
                    self._process_exit()
                case _:
                    raise RuntimeError(f"Unknown request: {request}")
        except UserAbort as exc:
            log.info("Aborted: %s", exc)
            print(f"\n{exc} Returning to menu.")
        except AutoPayrollError as exc:
            log.error("%s", exc)
            print(f"\nError: {exc}\nReturning to menu (browser left open).")

    def main(self) -> None:
        """Main menu loop."""
        scripts = {
            "1.  Process a Timesheet": ControlFlow.PROCESS,
            "2.  Process from a schedule CSV (no TRAC)": ControlFlow.SCHEDULE,
            "3.  Dry run (parse only, no PeopleSoft entry)": ControlFlow.DRY_RUN,
            "4. 󰈆 Exit": ControlFlow.EXIT,
        }
        while True:
            choice = questionary.select(
                "What would you like to do?",
                choices=list(scripts.keys()),
                use_indicator=True,
            ).ask()
            if choice is None:  # Ctrl-C / Esc at the menu
                self._process_exit()
            self._process_request(scripts[choice])


def _configure_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )


def main() -> None:
    parser = argparse.ArgumentParser(prog="autopayroll", description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Default the menu to parse-only (no PeopleSoft entry).",
    )
    parser.add_argument(
        "--schedule",
        metavar="CSV",
        help="Default path for the schedule-CSV menu option (day,start,stop).",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging."
    )
    args = parser.parse_args()

    _configure_logging(args.verbose)
    Interface(dry_run=args.dry_run, schedule=args.schedule).main()


if __name__ == "__main__":
    main()
