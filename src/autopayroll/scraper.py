"""Scrape the TRAC Cloud attendance listing and save its rendered HTML."""

import logging
from pathlib import Path

import questionary
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from autopayroll.errors import LoginError, UserAbort

log = logging.getLogger(__name__)


class UMBCTimesheetScraper:
    def __init__(self, driver, config) -> None:
        self.driver = driver
        self.config = config
        self.target_url: str = config.trac_listing_url
        self.output_file: Path = config.html_file

    def login(self) -> None:
        log.info("Navigating to TRAC listing...")
        self.driver.get(self.target_url)
        wait = WebDriverWait(self.driver, self.config.wait_time)
        short = WebDriverWait(self.driver, self.config.short_wait_time)

        # If the persistent Firefox profile still holds a valid session, TRAC
        # skips the login form entirely — don't wait the full timeout for a
        # field that will never appear.
        try:
            username_field = short.until(
                EC.element_to_be_clickable((By.XPATH, '//*[@id="username"]'))
            )
        except TimeoutException:
            log.info("Login form not shown; assuming existing session.")
        else:
            username_field.send_keys(self.config.get_username())
            password_field = wait.until(
                EC.element_to_be_clickable((By.XPATH, '//*[@id="password"]'))
            )
            password_field.send_keys(self.config.get_password())
            submit_button = wait.until(
                EC.element_to_be_clickable((By.XPATH, '//*[@id="submitButton"]'))
            )
            submit_button.click()

        try:
            wait.until(
                lambda d: d.execute_script("return document.readyState") == "complete"
            )
            # Dismiss the print dialog the listing (isPrint=true) pops open.
            body = wait.until(EC.presence_of_element_located((By.TAG_NAME, "body")))
            body.send_keys(Keys.ESCAPE)
        except TimeoutException as exc:
            raise LoginError("TRAC page did not finish loading after login.") from exc

    def fetch_and_save_html(self) -> None:
        choice = questionary.select(
            "Finished Loading Page?",
            choices=["Yes"],
            use_indicator=True,
        ).ask()
        if choice is None:
            raise UserAbort("Cancelled before saving attendance HTML.")

        html_source: str = self.driver.page_source
        self.config.data_dir.mkdir(parents=True, exist_ok=True)

        with open(self.output_file, "w", encoding="utf-8") as f:
            f.write(html_source)

        log.info("Saved attendance HTML to %s", self.output_file)

    def run(self) -> None:
        self.login()
        self.fetch_and_save_html()
