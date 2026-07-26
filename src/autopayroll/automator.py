"""Fill the UMBC PeopleSoft timesheet from a parsed billing CSV."""

import logging
from datetime import datetime
from time import sleep

import pandas as pd
import questionary
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC

from autopayroll.errors import LoginError, PageStateError, UserAbort

log = logging.getLogger(__name__)


def _try_parse(text: str, formats: tuple[str, ...]) -> datetime | None:
    for fmt in formats:
        try:
            return datetime.strptime(text.strip().upper().replace(" ", ""), fmt)
        except ValueError:
            continue
    return None


class TimesheetAutomator:
    """Automates UMBC timesheet entry using Selenium and Pandas."""

    def __init__(self, driver, wait, config) -> None:
        self.config = config
        self.driver = driver
        self.wait = wait
        self._validate_setup()

    def _validate_setup(self) -> None:
        if self.driver is None or self.wait is None:
            raise ValueError("Driver / Wait did not start properly from interface.")

    def login_umbc(self, login_url: str) -> None:
        """Navigate to the timesheet page, logging in if prompted."""
        username = self.config.get_username()
        password = self.config.get_password()

        log.info("Navigating to timesheet page: %s", login_url)
        self.driver.get(login_url)

        # If the session carried over, the login form won't appear; that's fine.
        from selenium.webdriver.support.ui import WebDriverWait

        short = WebDriverWait(self.driver, self.config.short_wait_time)
        try:
            uname_input = short.until(
                EC.element_to_be_clickable((By.XPATH, '//*[@id="username"]'))
            )
        except TimeoutException:
            log.info("Login form not shown; assuming existing session.")
            return

        try:
            uname_input.send_keys(username)
            pass_input = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, '//*[@id="password"]'))
            )
            pass_input.send_keys(password)
            self.driver.find_element(By.XPATH, '//*[@id="submitButton"]').click()
        except (TimeoutException, NoSuchElementException) as exc:
            raise LoginError("Timesheet login fields not found in time.") from exc

    def _switch_to_peoplesoft_iframe(self) -> None:
        """Switch to the PeopleSoft content iframe or raise PageStateError."""
        log.info("Switching to PeopleSoft iframe...")
        try:
            self.wait.until(
                EC.frame_to_be_available_and_switch_to_it((By.ID, "ptModFrame_0"))
            )
            log.info("Switched to modal iframe (ptModFrame_0).")
            return
        except TimeoutException:
            log.info("Modal iframe not found; trying main content iframe...")
        try:
            self.wait.until(
                EC.frame_to_be_available_and_switch_to_it((By.ID, "ptifrmtgtframe"))
            )
            log.info("Switched to main iframe (ptifrmtgtframe).")
        except TimeoutException as exc:
            raise PageStateError(
                "Could not find the PeopleSoft timesheet iframe."
            ) from exc

    @staticmethod
    def _row_xpaths(index: int) -> dict:
        return {
            "date": f"//*[@id='UM_WORK_DATE${index}']",
            "start": f"//*[@id='UM_TIME_IN${index}']",
            "end": f"//*[@id='UM_TIME_OUT${index}']",
            "break": f"//*[@id='UM_BREAK${index}']",
            "add_btn": f"//*[@id='COMPANY$new${index}$$0']",
        }

    def _enter_row_data(
        self, index: int, row: pd.Series, is_last_row: bool, timer: float = 0.5
    ) -> None:
        """Inputs a single row of data from the DataFrame into the timesheet."""
        log.debug("Entering row index %d", index)
        xpaths = self._row_xpaths(index)

        for field, value in (
            ("date", str(row["formatted_date"])),
            ("start", str(row["start_time"])),
            ("end", str(row["end_time"])),
            ("break", "0"),
        ):
            element = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, xpaths[field]))
            )
            element.clear()
            element.send_keys(value)
            element.send_keys(Keys.TAB)
            sleep(timer)

        if not is_last_row:
            add_row_btn = self.wait.until(
                EC.element_to_be_clickable((By.XPATH, xpaths["add_btn"]))
            )
            self._safe_click(add_row_btn)
            sleep(timer)
            next_date_xpath = f"//*[@id='UM_WORK_DATE${index + 1}']"
            self.wait.until(EC.presence_of_element_located((By.XPATH, next_date_xpath)))
            sleep(0.5)

    def _safe_click(self, element) -> None:
        """Click an element that may be off-screen or transiently covered.

        The PeopleSoft "add row" link often sits below the fold, so a raw click
        reports the page body as intercepting it. Scroll it into view first and
        fall back to a scripted click if the native one is still intercepted.
        """
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", element
        )
        sleep(0.2)
        try:
            element.click()
        except ElementClickInterceptedException:
            log.debug("Native click intercepted; falling back to JS click.")
            self.driver.execute_script("arguments[0].click();", element)

    @staticmethod
    def _values_match(field: str, want: str, got: str | None) -> bool | None:
        """Compare an expected value to what the field holds.

        PeopleSoft reformats date/time fields on blur (e.g. "14:00" -> "2:00PM"),
        so compare on parsed value rather than raw text. Returns None when the
        field value can't be parsed, meaning "could not confirm".
        """
        got = (got or "").strip()
        want = want.strip()
        if not got:
            return False
        if got == want:
            return True
        if field == "date":
            got_dt = _try_parse(got, ("%m/%d/%Y", "%m/%d/%y", "%Y-%m-%d"))
            want_dt = _try_parse(want, ("%m/%d/%Y",))
            if got_dt is None or want_dt is None:
                return None
            return got_dt.date() == want_dt.date()
        # start / end times ("2:00PM" and "14:00" normalize to the same time)
        got_t = _try_parse(got, ("%H:%M", "%I:%M%p"))
        want_t = _try_parse(want, ("%H:%M",))
        if got_t is None or want_t is None:
            return None
        return got_t.time() == want_t.time()

    def _verify_entries(self, df: pd.DataFrame) -> bool:
        """Read each field back and compare against the DataFrame before submit.

        Best-effort: the comparison normalizes formats, but the exact way
        PeopleSoft echoes values has not been validated against the live portal.
        """
        print("\nVerifying entered values (heuristic — confirm visually too):")
        all_ok = True
        for index, row in df.iterrows():
            xpaths = self._row_xpaths(int(index))
            expected = {
                "date": str(row["formatted_date"]),
                "start": str(row["start_time"]),
                "end": str(row["end_time"]),
            }
            marks = []
            details = []
            for field, want in expected.items():
                try:
                    got = self.driver.find_element(
                        By.XPATH, xpaths[field]
                    ).get_attribute("value")
                except NoSuchElementException:
                    got = None
                result = self._values_match(field, want, got)
                if result is False:
                    marks.append("✗")
                    details.append(f"{field}: expected {want!r}, got {got!r}")
                    all_ok = False
                elif result is None:
                    marks.append("?")
                    details.append(f"{field}: could not confirm (got {got!r})")
            mark = "✓" if not marks else "".join(marks)
            print(f"  {mark} row {index} ({row['formatted_date']})")
            for d in details:
                print(f"      - {d}")
        return all_ok

    def run(self, csv_file: str, timesheet_url: str) -> None:
        """Read the billing CSV and enter each row into the timesheet."""
        try:
            df = pd.read_csv(csv_file)
        except Exception as exc:
            raise PageStateError(f"Failed to read CSV {csv_file}: {exc}") from exc

        if df.empty:
            print("No rows to enter for this pay period.")
            return

        self.login_umbc(timesheet_url)

        choice = questionary.select(
            "Finished Loading Page?",
            choices=["Yes"],
            use_indicator=True,
        ).ask()
        if choice is None:
            raise UserAbort("Cancelled before entering timesheet data.")

        log.info("Entering timesheet data...")
        self._switch_to_peoplesoft_iframe()

        total_rows = len(df)
        for index, row in df.iterrows():
            is_last_row = index + 1 == total_rows
            self._enter_row_data(index=int(index), row=row, is_last_row=is_last_row)
            sleep(1)

        if self._verify_entries(df):
            print("\nAll rows match the parsed data. Review and submit in the browser.")
        else:
            print(
                "\nWarning: some fields did not match. Check the flagged rows in "
                "the browser before submitting."
            )
        input("Press Enter to quit...")
        self.quit_driver()

    def quit_driver(self) -> None:
        if self.driver:
            self.driver.quit()
            log.info("Browser closed.")
