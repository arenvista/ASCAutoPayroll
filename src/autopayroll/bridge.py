"""JSON-lines bridge between the desktop GUI and the payroll pipeline.

The Tauri shell (``gui/``) spawns ``python -m autopayroll.bridge`` and talks to
it over stdin/stdout, one JSON object per line:

    GUI -> bridge   {"id": 1, "method": "run", "params": {...}}
    bridge -> GUI   {"id": 1, "result": ...}  or  {"id": 1, "error": {"message": ...}}
    bridge -> GUI   {"event": "stage", "data": {...}}     (unsolicited)

A run executes on a worker thread so the reader loop can keep delivering prompt
answers and cancellation while Selenium is busy. It drives the same building
blocks as the CLI (scraper login/save_html, AttendanceParser.parse,
build_timesheet, the automator's login_umbc/enter_rows/check_entries) but asks
its questions through the window instead of the terminal.

Events:
    log            {level, message, time}
    browser        {open}
    stage          {stage, status, detail}   stage: trac | parse | schedule |
                                             review | peoplesoft | verify
                                             status: active | waiting | done |
                                             skipped | error | cancelled
    prompt         {id, kind, message, ...}  kind: continue | confirm | text |
                                             password; "stage" marks prompts
                                             shown inside that step
    prompt_closed  {id}                      answered, or cancelled by the run
    entries        {rows, summary, csv_path}
    progress       {done, total}
    verification   {rows, all_ok}
    run_finished   {status, message}         status: ok | aborted | error

Every event except log and browser belongs to the current run and is kept, so
``init`` can hand a reloaded window the run's history to replay.
"""

import argparse
import json
import logging
import os
import sys
import threading
import uuid
from datetime import date
from typing import TextIO

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.support.ui import WebDriverWait

from autopayroll.automator import TimesheetAutomator
from autopayroll.browser import driver_alive, quit_quietly, start_firefox
from autopayroll.config import ConfigSettings
from autopayroll.errors import AutoPayrollError, UserAbort
from autopayroll.parser import AttendanceParser, pay_summary
from autopayroll.schedule import build_timesheet
from autopayroll.scraper import UMBCTimesheetScraper
from autopayroll.timeblocks import TimeBlockGenerator, read_periods

log = logging.getLogger(__name__)

# Steps a run never reaches when it stops after the review.
_LATE_STAGES = ("review", "peoplesoft", "verify")


class Channel:
    """Thread-safe writer for protocol messages."""

    def __init__(self, out: TextIO) -> None:
        self._out = out
        self._lock = threading.Lock()

    def send(self, message: dict) -> None:
        line = json.dumps(message, default=str)
        with self._lock:
            self._out.write(line + "\n")
            self._out.flush()

    def event(self, name: str, **data) -> None:
        self.send({"event": name, "data": data})


class GuiPrompter:
    """Asks the window a question and blocks the calling thread for the answer.

    Implements the Prompter interface ConfigSettings uses for credentials, plus
    ask() for the run's own pauses. close() answers every open question (and
    any asked later) with None, which the pipeline treats as a cancel.
    """

    def __init__(self, emit) -> None:
        self._emit = emit
        self._lock = threading.Lock()
        self._open: dict[str, tuple[threading.Event, list]] = {}
        self._closed = False

    def ask(self, kind: str, message: str, **extra):
        prompt_id = uuid.uuid4().hex
        answered = threading.Event()
        slot = [None]
        with self._lock:
            if self._closed:
                return None
            self._open[prompt_id] = (answered, slot)
        self._emit("prompt", id=prompt_id, kind=kind, message=message, **extra)
        answered.wait()
        return slot[0]

    def answer(self, prompt_id: str, value) -> bool:
        with self._lock:
            waiting = self._open.pop(prompt_id, None)
        if waiting is None:
            return False
        answered, slot = waiting
        slot[0] = value
        answered.set()
        self._emit("prompt_closed", id=prompt_id)
        return True

    def close(self) -> None:
        with self._lock:
            self._closed = True
            waiting, self._open = self._open, {}
        for prompt_id, (answered, _slot) in waiting.items():
            answered.set()
            self._emit("prompt_closed", id=prompt_id)

    def reopen(self) -> None:
        with self._lock:
            self._closed = False

    def text(self, message: str) -> str | None:
        return self.ask("text", message)

    def password(self, message: str) -> str | None:
        return self.ask("password", message)

    def confirm(self, message: str, default: bool = True) -> bool | None:
        return self.ask("confirm", message, default=default)


class Bridge:
    """Request handlers and the state that outlives a single run."""

    def __init__(self, channel: Channel) -> None:
        self.channel = channel
        # Guards request handling and run-event emission, so a snapshot taken
        # by init can't miss an event that's sent while it is being built.
        self._lock = threading.RLock()
        self._run_params: dict | None = None
        self._run_events: list[dict] = []
        self._worker: threading.Thread | None = None
        self._cancel = threading.Event()
        self._stage: str | None = None
        self.driver = None
        self.prompter = GuiPrompter(self._emit)
        self.config = ConfigSettings(prompter=self.prompter)
        self._methods = {
            "init": self.init,
            "periods": self.periods,
            "settings": self.settings,
            "save_settings": self.save_settings,
            "set_password": self.set_password,
            "forget_password": self.forget_password,
            "preview_schedule": self.preview_schedule,
            "run": self.run,
            "respond": self.respond,
            "cancel": self.cancel,
            "close_browser": self.close_browser,
        }

    # -- protocol -----------------------------------------------------------

    def handle(self, message: dict) -> bool:
        """Dispatch one request; return False once the GUI asked us to exit."""
        msg_id = message.get("id")
        method = message.get("method")
        if method == "shutdown":
            self.channel.send({"id": msg_id, "result": None})
            return False
        handler = self._methods.get(method)
        with self._lock:
            if handler is None:
                self.channel.send(
                    {"id": msg_id, "error": {"message": f"Unknown method: {method}"}}
                )
                return True
            try:
                result = handler(**(message.get("params") or {}))
            except Exception as exc:
                log.debug("%s failed", method, exc_info=True)
                self.channel.send({"id": msg_id, "error": {"message": _describe(exc)}})
            else:
                self.channel.send({"id": msg_id, "result": result})
        return True

    def _emit(self, name: str, **data) -> None:
        """Send a run event and keep it for replay."""
        with self._lock:
            self._run_events.append({"event": name, "data": data})
            self.channel.event(name, **data)

    @property
    def busy(self) -> bool:
        return self._worker is not None and self._worker.is_alive()

    def _require_idle(self) -> None:
        if self.busy:
            raise AutoPayrollError("Finish or cancel the current run first.")

    # -- requests -----------------------------------------------------------

    def init(self) -> dict:
        """Everything the window needs at startup (or after a reload)."""
        run = None
        if self.busy:
            run = {"params": self._run_params, "events": list(self._run_events)}
        return {
            "config_dir": str(self.config.config_dir),
            "data_dir": str(self.config.data_dir),
            "settings": self._settings(),
            "browser_open": self.driver is not None,
            "run": run,
            **self.periods(),
        }

    def periods(self) -> dict:
        """The selectable pay periods and the one containing today."""
        TimeBlockGenerator(str(self.config.timeblock_path)).ensure_fresh()
        periods = read_periods(self.config.timeblock_path)
        today = date.today().isoformat()
        current = next(
            (p["period"] for p in periods if p["start"] <= today <= p["end"]), None
        )
        return {"periods": periods, "current_period": current}

    def settings(self) -> dict:
        """Settings plus where the password is stored. Looking in the keyring
        can pop an unlock dialog, so only the Settings view asks for this."""
        return {**self._settings(), "password": self.config.password_source()}

    def _settings(self) -> dict:
        return {
            "username": self.config.umbc_usr or "",
            "profile_dir": self.config.profile_dir or "",
            "pay_rate": self.config.pay_rate,
        }

    def save_settings(self, username: str, profile_dir: str, pay_rate: float) -> dict:
        self._require_idle()
        self.config.update(username=username, profile_dir=profile_dir, pay_rate=pay_rate)
        return self.settings()

    def set_password(self, password: str) -> dict:
        self._require_idle()
        if not password:
            raise AutoPayrollError("Enter a password to save.")
        self.config.store_password(password)
        return self.settings()

    def forget_password(self) -> dict:
        self._require_idle()
        self.config.forget_password()
        return self.settings()

    def preview_schedule(self, path: str, start: str, end: str) -> dict:
        """The rows a schedule CSV expands to, without saving anything."""
        _check_period(start, end)
        return self._entries_payload(_schedule_frame(path, start, end), None)

    def run(
        self,
        source: str,
        start: str,
        end: str,
        dry_run: bool = False,
        schedule_path: str | None = None,
    ) -> None:
        """Start a run in the background; its progress arrives as events."""
        self._require_idle()
        if source not in ("trac", "schedule"):
            raise ValueError(f"Unknown source: {source}")
        if source == "schedule" and not schedule_path:
            raise AutoPayrollError("Choose a schedule CSV first.")
        _check_period(start, end)

        self._run_params = {
            "source": source,
            "start": start,
            "end": end,
            "dry_run": bool(dry_run),
            "schedule_path": schedule_path,
        }
        self._run_events = []
        self._cancel.clear()
        self.prompter.reopen()
        self._worker = threading.Thread(
            target=self._run, kwargs=self._run_params, name="run", daemon=True
        )
        self._worker.start()

    def respond(self, prompt_id: str, value=None) -> bool:
        return self.prompter.answer(prompt_id, value)

    def cancel(self) -> None:
        if not self.busy:
            return
        log.info("Cancelling the run...")
        self._cancel.set()
        self.prompter.close()

    def close_browser(self) -> None:
        self._require_idle()
        self._quit_driver()

    def shutdown(self) -> None:
        """Stop any run and close Firefox before the process exits."""
        self._cancel.set()
        self.prompter.close()
        if self._worker is not None:
            self._worker.join(timeout=5)
        self._quit_driver()

    # -- the run ------------------------------------------------------------

    def _run(self, source, start, end, dry_run, schedule_path) -> None:
        status, message = "error", "The run stopped unexpectedly."
        try:
            message = self._pipeline(source, start, end, dry_run, schedule_path)
            status = "ok"
        except Exception as exc:
            if isinstance(exc, UserAbort) or self._cancel.is_set():
                status = "aborted"
                message = str(exc) if isinstance(exc, UserAbort) else "Run cancelled."
                log.info("Aborted: %s", message)
            else:
                message = _describe(exc)
                log.error("%s", message, exc_info=not isinstance(exc, AutoPayrollError))
            if self._stage is not None:
                failed = "error" if status == "error" else "cancelled"
                self._emit("stage", stage=self._stage, status=failed, detail=None)
        finally:
            self._stage = None
            self._emit("run_finished", status=status, message=message)

    def _pipeline(self, source, start, end, dry_run, schedule_path) -> str:
        csv_path = self.config.data_dir / f"{start}_{end}.csv"
        if source == "trac":
            df = self._fetch_trac(start, end)
        else:
            self._set_stage("schedule", "active")
            df = _schedule_frame(schedule_path, start, end)
            self._set_stage("schedule", "done")
        df.to_csv(csv_path)
        log.info("Saved export to %s", csv_path)
        self._emit("entries", **self._entries_payload(df, csv_path))

        if dry_run or df.empty:
            for stage in _LATE_STAGES:
                self._set_stage(stage, "skipped")
            if df.empty:
                return "No rows to enter for this pay period."
            return (
                f"{len(df)} rows saved to {csv_path.name}. Nothing was entered into "
                "PeopleSoft."
            )

        self._set_stage("review", "waiting")
        rows = f"{len(df)} row{'s' if len(df) != 1 else ''}"
        proceed = self.prompter.ask(
            "confirm",
            f"Enter these {rows} into your PeopleSoft timesheet?",
            stage="review",
            confirm_label=f"Enter {rows}",
            cancel_label="Cancel",
        )
        if not proceed:
            raise UserAbort("Timesheet entry cancelled.")
        self._set_stage("review", "done")

        if self._fill_timesheet(csv_path):
            return "Review the timesheet in Firefox, then submit it."
        return "Check the flagged rows in Firefox and correct them before submitting."

    def _fetch_trac(self, start, end):
        self._set_stage("trac", "active", "Starting Firefox…")
        scraper = UMBCTimesheetScraper(self._ensure_driver(), self.config)
        self._set_stage("trac", "active", "Opening TRAC…")
        scraper.login()
        self._pause(
            "trac",
            "Finish any sign-in steps (like Duo) in Firefox and wait for your "
            "attendance listing to load completely, then continue.",
            "Cancelled before saving attendance HTML.",
        )
        scraper.save_html()
        self._set_stage("trac", "done")

        self._set_stage("parse", "active")
        parser = AttendanceParser(
            html_file=self.config.html_file,
            timeblocks_file=self.config.timeblock_path,
            pay_rate=self.config.pay_rate,
        )
        df = parser.parse(start, end)
        self._set_stage("parse", "done")
        return df

    def _fill_timesheet(self, csv_path) -> bool:
        """Enter the saved rows into PeopleSoft; True if every field verified."""
        self._set_stage("peoplesoft", "active", "Starting Firefox…")
        driver = self._ensure_driver()
        automator = TimesheetAutomator(
            driver, WebDriverWait(driver, self.config.wait_time), self.config
        )
        df = automator.load_rows(csv_path)
        self._set_stage("peoplesoft", "active", "Opening the timesheet…")
        automator.login_umbc(self.config.timesheet_url)
        self._pause(
            "peoplesoft",
            "Finish any sign-in steps in Firefox and wait for the timesheet page "
            "to load completely, then continue.",
            "Cancelled before entering timesheet data.",
        )
        self._set_stage("peoplesoft", "active", "Entering rows…")
        automator.enter_rows(df, on_row=self._row_entered)
        self._set_stage("peoplesoft", "done")

        self._set_stage("verify", "active")
        checks = automator.check_entries(df)
        all_ok = not any(
            issue["match"] is False for check in checks for issue in check["issues"]
        )
        self._emit("verification", rows=checks, all_ok=all_ok)
        self._set_stage("verify", "done")
        return all_ok

    def _row_entered(self, done: int, total: int) -> None:
        self._emit("progress", done=done, total=total)
        if self._cancel.is_set():
            raise UserAbort(f"Stopped after entering {done} of {total} rows.")

    def _set_stage(self, stage: str, status: str, detail: str | None = None) -> None:
        if status in ("active", "waiting") and self._cancel.is_set():
            raise UserAbort("Run cancelled.")
        self._stage = stage if status in ("active", "waiting") else None
        self._emit("stage", stage=stage, status=status, detail=detail)

    def _pause(self, stage: str, message: str, abort_message: str) -> None:
        """Wait for the user to say the page in Firefox is ready."""
        self._set_stage(stage, "waiting")
        if not self.prompter.ask("continue", message, stage=stage):
            raise UserAbort(abort_message)
        self._set_stage(stage, "active")

    def _ensure_driver(self):
        if self.driver is not None:
            if driver_alive(self.driver):
                return self.driver
            log.info("Firefox was closed; starting a new window.")
            self._quit_driver()
        self.driver = start_firefox(self.config)
        self._browser_changed()
        return self.driver

    def _quit_driver(self) -> None:
        if self.driver is None:
            return
        quit_quietly(self.driver)
        self.driver = None
        log.info("Browser closed.")
        self._browser_changed()

    def _browser_changed(self) -> None:
        # Under the lock, so it can't overtake an init reading self.driver.
        with self._lock:
            self.channel.event("browser", open=self.driver is not None)

    def _entries_payload(self, df, csv_path) -> dict:
        rows = [
            {
                "date": when.strftime("%Y-%m-%d"),
                "formatted_date": row["formatted_date"],
                "day_of_week": row["day_of_week"],
                "start_time": row["start_time"],
                "end_time": row["end_time"],
                "duration_mins": int(row["duration_mins"]),
                "billed_hours": float(row["billed_time_hours"]),
            }
            for when, row in df.iterrows()
        ]
        return {
            "rows": rows,
            "summary": {
                **pay_summary(df, self.config.pay_rate),
                "pay_rate": self.config.pay_rate,
            },
            "csv_path": str(csv_path) if csv_path else None,
        }


def _schedule_frame(path, start, end):
    try:
        return build_timesheet(path, start, end)
    except (OSError, ValueError) as exc:
        raise AutoPayrollError(f"Could not use schedule: {exc}") from exc


def _check_period(start: str, end: str) -> None:
    # Also keeps the dates safe to use in the CSV file name.
    try:
        first, last = date.fromisoformat(start), date.fromisoformat(end)
    except (TypeError, ValueError) as exc:
        raise AutoPayrollError(f"Invalid pay period: {start} to {end}") from exc
    if first > last:
        raise AutoPayrollError(f"Invalid pay period: {start} to {end}")


def _describe(exc: BaseException) -> str:
    """One line for the window about why a request or run failed."""
    if isinstance(exc, TimeoutException):
        return "Timed out waiting for the page. Check the Firefox window and try again."
    if isinstance(exc, WebDriverException):
        lines = (exc.msg or "").strip().splitlines()
        return f"Browser error: {lines[0] if lines else type(exc).__name__}"
    if isinstance(exc, (AutoPayrollError, OSError, ValueError)):
        return str(exc) or type(exc).__name__
    return f"Unexpected error ({type(exc).__name__}): {exc}"


class _GuiLogHandler(logging.Handler):
    def __init__(self, channel: Channel) -> None:
        super().__init__()
        self.channel = channel

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.channel.event(
                "log",
                level=record.levelname.lower(),
                message=self.format(record),
                time=record.created,
            )
        except Exception:
            self.handleError(record)


def _claim_stdio() -> tuple[TextIO, TextIO]:
    """Take fds 0/1 for the protocol and point the originals elsewhere.

    A stray print (or a child process writing to fd 1) then lands on stderr
    instead of corrupting the JSON stream, and anything that tries to read the
    terminal (questionary, input()) gets EOF instead of swallowing protocol
    lines. prompt_toolkit resolves stdin/stdout when a prompt is created, not
    at import, so this only has to run before the first request is handled.
    """
    proto_in = os.fdopen(os.dup(0), "r", encoding="utf-8")
    proto_out = os.fdopen(os.dup(1), "w", encoding="utf-8", newline="\n")
    devnull = os.open(os.devnull, os.O_RDONLY)
    os.dup2(devnull, 0)
    os.close(devnull)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    return proto_in, proto_out


def serve(proto_in: TextIO, proto_out: TextIO, verbose: bool = False) -> None:
    channel = Channel(proto_out)
    handler = _GuiLogHandler(channel)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[handler], force=True)
    logging.captureWarnings(True)
    if verbose:
        logging.getLogger("autopayroll").setLevel(logging.DEBUG)

    bridge = Bridge(channel)
    try:
        for line in proto_in:
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                log.warning("Ignoring malformed message from the GUI.")
                continue
            if not bridge.handle(message):
                break
    finally:
        bridge.shutdown()


def main() -> None:
    parser = argparse.ArgumentParser(prog="autopayroll-bridge", description=__doc__)
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable debug logging."
    )
    args = parser.parse_args()
    proto_in, proto_out = _claim_stdio()
    serve(proto_in, proto_out, verbose=args.verbose)


if __name__ == "__main__":
    main()
