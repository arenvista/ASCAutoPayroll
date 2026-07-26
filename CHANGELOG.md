Harden and restructure the payroll automation pipeline

Rework the tool end-to-end for reliability, security, and maintainability,
following PLAN.md. Behavior of the core pay logic is preserved: the parser
produces byte-identical output to the previously generated CSVs.

Correctness & reliability
- Auto-regenerate the pay-period list on startup so it never goes stale
  (previously the list expired on a hardcoded date and left the picker empty).
  Periods now derive from a fixed anchor and use stable absolute indices, and
  the current period is always included.
- Introduce typed exceptions (LoginError, PageStateError, UserAbort) raised by
  the scraper/automator and caught once in the interface, so a failure returns
  to the menu with the browser intact instead of charging into a broken page.
- Detect an existing browser session and skip the login form instead of timing
  out and crashing when the persistent Firefox profile is still valid.
- Verify entered values against the parsed data before submit, with a
  format-normalizing comparison (14:00 vs 2:00PM) and a per-row report.
- Drop non-billable visits whose rounded end is not after their start (e.g. a
  0-minute check-in that rounded to 13:00-12:30), which PeopleSoft would reject.
- Make the "add row" click robust to off-screen/intercepted elements by
  scrolling into view with a scripted-click fallback.

Security & configuration
- Store settings.env with 0600 permissions and stop echoing the password
  length to the terminal.
- Resolve the password from the settings file, then the system keyring, then an
  interactive prompt (with optional keyring save), keeping it out of plaintext.
- Centralize tunables and both portal URLs in ConfigSettings; drop the unused
  ENV_PATH/ROOT_DIR/CONFIG_DIR/CONFIG_PATH keys.
- Remove the vestigial pass.env and root-level timeblocks.csv.

Dependencies & packaging
- Prune unused deps (pynput, pyautogui, keyboard, evdev); fix bs4 ->
  beautifulsoup4 and dotenv -> python-dotenv.
- Move pyinstaller to a dev dependency group; add pytest and ruff.
- Add an `autopayroll` console-script entry point and a real project
  description; remove the checked-in egg-info.

Structure
- Remove the unused async layer (sync questionary API throughout).
- Flatten the three single-module subpackages into
  config/timeblocks/scraper/parser/automator/interface/errors.
- Give the CSV export path a single source of truth (parser returns the frame;
  the interface owns the path).
- Replace diagnostic prints with logging; add a --verbose flag.

UX
- Default the period picker to the period containing today.
- Preview parsed rows and confirm before touching PeopleSoft.
- Add a --dry-run flag and a dedicated dry-run menu action.
- Start the WebDriver lazily so Exit no longer launches Firefox.

Tests & docs
- Add pytest unit tests (rounding boundaries, duration math, date-filter edges,
  zero-duration drop, verification normalization, period generation) against a
  sanitized HTML fixture.
- Update README for the new layout, credential flow, dry-run, and a manual
  smoke-test checklist for the Selenium flows.
