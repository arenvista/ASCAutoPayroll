"""Start, check, and close the Selenium-driven Firefox."""

import logging

from selenium import webdriver
from selenium.common.exceptions import WebDriverException
from selenium.webdriver.firefox.options import Options

from autopayroll.errors import AutoPayrollError

log = logging.getLogger(__name__)


def start_firefox(config) -> webdriver.Firefox:
    """Launch Firefox, reusing the configured profile for its saved session."""
    log.info("Setting up Firefox profile at: %s", config.profile_dir)
    options = Options()
    if config.profile_dir:
        options.add_argument("-profile")
        options.add_argument(str(config.profile_dir))

    log.info("Initializing WebDriver...")
    try:
        return webdriver.Firefox(options=options)
    except WebDriverException as exc:
        raise AutoPayrollError(f"Could not start Firefox: {exc.msg or exc}") from exc


def driver_alive(driver) -> bool:
    """True if the session still has a window to drive.

    The user can close the automated window (or all of Firefox) between runs.
    If only the current window is gone, switch to one that survived.
    """
    try:
        handles = driver.window_handles
        if not handles:
            return False
        try:
            _ = driver.current_window_handle
        except WebDriverException:
            driver.switch_to.window(handles[0])
        return True
    except Exception:  # dead session, or geckodriver already stopped
        return False


def quit_quietly(driver) -> None:
    """Quit the driver, ignoring errors from a session that is already gone."""
    try:
        driver.quit()
    except Exception as exc:
        log.debug("Ignoring error while closing the browser: %s", exc)
