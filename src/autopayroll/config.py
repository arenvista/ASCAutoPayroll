"""Runtime configuration: paths, credentials, tunables, and target URLs.

Everything a run needs — where files live, how long to wait, the pay rate, and
the two portal URLs — is centralized here so operational changes don't require
editing code. Credentials come from the settings file, then the system keyring,
then an interactive prompt, in that order.
"""

import logging
import os
import stat
from pathlib import Path

from dotenv import load_dotenv

from autopayroll.timeblocks import TimeBlockGenerator

log = logging.getLogger(__name__)

# Where the tool scrapes attendance from and where it enters the timesheet.
TRAC_LISTING_URL = (
    "https://traccloud.go-redrock.com/umbc/trac/listing.php?navSrch=all&form=list"
    "&tbl=Visits&rsrc=&searchForm=true&previousSearch=Previous+Search%3A+month"
    "&previousSearch_Visits=Previous+Search%3A+month&isPrint=true"
)
PEOPLESOFT_TIMESHEET_URL = (
    "https://hrprd-web.pshr.umbc.edu/psp/ps/EMPLOYEE/HRMS/c/UM_ETS_EMP."
    "UM_ETS_EMP_SUMMARY.GBL?PORTALPARAM_PTCNAV=UM_ETS_EMP_SUMMARY_GBL&"
    "EOPP.SCNode=HRMS&EOPP.SCPortal=EMPLOYEE&EOPP.SCName=UMBC_TIME_ENTRY_LEAVE_PROCESS&"
    "EOPP.SCLabel=UMBC%20Time%20and%20Leave%20Processing&"
    "EOPP.SCPTfname=UMBC_TIME_ENTRY_LEAVE_PROCESS&"
    "FolderPath=PORTAL_ROOT_OBJECT.UMBC_TIME_ENTRY_LEAVE_PROCESS.UM_ETS_TIMESHEET."
    "UM_ETS_EMP_SUMMARY_GBL&IsFolder=false"
)

_KEYRING_SERVICE = "autopayroll"

# Only the keys the app actually reads.
_DEFAULT_CONFIG = """\
PROFILE_DIR=""
UMBC_USR=""
UMBC_PAS=""
"""


class ConfigSettings:
    def __init__(self) -> None:
        self.config_dir: Path = Path(os.path.expanduser("~/.config/autopayroll"))
        self.config_path: Path = self.config_dir / "settings.env"
        self.data_dir: Path = self.config_dir / "data"
        self.timeblock_path: Path = self.config_dir / "timeblock.env"
        self.html_file: Path = self.data_dir / "Attendance Listing.html"

        # Tunables (were scattered magic numbers before).
        self.wait_time: int = 15
        self.short_wait_time: int = 4
        self.pay_rate: float = 17.5

        self.trac_listing_url: str = TRAC_LISTING_URL
        self.timesheet_url: str = PEOPLESOFT_TIMESHEET_URL

        self._password_cache: str | None = None

        self._check_config()
        self._read_config()
        self._check_missing()

    def _check_config(self):
        if not self.config_dir.exists():
            log.info("Creating config dir: %s", self.config_dir)
            self.config_dir.mkdir(parents=True, exist_ok=True)

        if not self.data_dir.exists():
            self.data_dir.mkdir(parents=True, exist_ok=True)

        if not self.config_path.exists():
            log.info("Creating default settings file: %s", self.config_path)
            with open(self.config_path, "w") as config_file:
                config_file.write(_DEFAULT_CONFIG)

        # Credentials live here; keep the file owner-only readable.
        self._tighten_permissions(self.config_path)

        # Keep the pay-period list current so the picker is never empty.
        TimeBlockGenerator(str(self.timeblock_path)).ensure_fresh()

    @staticmethod
    def _tighten_permissions(path: Path) -> None:
        try:
            current = stat.S_IMODE(path.stat().st_mode)
            if current & 0o077:
                path.chmod(0o600)
                log.debug("Restricted permissions on %s to 0600.", path)
        except OSError as exc:  # e.g. unusual filesystem; not worth failing over
            log.debug("Could not adjust permissions on %s: %s", path, exc)

    def _read_config(self):
        load_dotenv(dotenv_path=self.config_path)
        self.umbc_usr: str | None = os.getenv("UMBC_USR") or None
        self.profile_dir: str | None = os.getenv("PROFILE_DIR") or None
        # Password is resolved lazily (env -> keyring -> prompt) via get_password.
        self._env_password: str | None = os.getenv("UMBC_PAS") or None

    def _check_missing(self):
        # Password is intentionally excluded: it can be supplied interactively.
        missing = [
            name
            for name, val in [
                ("PROFILE_DIR", self.profile_dir),
                ("UMBC_USR", self.umbc_usr),
            ]
            if not val
        ]
        if missing:
            log.warning("Environment variable(s) not set: %s", ", ".join(missing))

    def get_username(self) -> str:
        """Return the username, prompting once if it isn't configured."""
        if not self.umbc_usr:
            import questionary

            self.umbc_usr = questionary.text("UMBC username:").ask()
            if not self.umbc_usr:
                raise ValueError("A UMBC username is required.")
        return self.umbc_usr

    def get_password(self) -> str:
        """Resolve the password: settings file, then keyring, then a prompt.

        A prompted password can optionally be stored in the system keyring so it
        isn't asked for again, keeping it out of the plaintext settings file.
        """
        if self._password_cache:
            return self._password_cache

        if self._env_password:
            self._password_cache = self._env_password
            return self._password_cache

        username = self.get_username()
        keyring = _try_import_keyring()
        if keyring is not None:
            try:
                stored = keyring.get_password(_KEYRING_SERVICE, username)
            except Exception as exc:  # no usable backend on this box
                log.debug("Keyring lookup failed: %s", exc)
                stored = None
            if stored:
                self._password_cache = stored
                return stored

        import questionary

        password = questionary.password("UMBC password:").ask()
        if not password:
            raise ValueError("A UMBC password is required.")
        self._password_cache = password

        if keyring is not None:
            save = questionary.confirm(
                "Save this password to your system keyring for next time?",
                default=True,
            ).ask()
            if save:
                try:
                    keyring.set_password(_KEYRING_SERVICE, username, password)
                    log.info("Password saved to system keyring.")
                except Exception as exc:  # keyring backends vary; never fatal
                    log.warning("Could not store password in keyring: %s", exc)
        return password


def _try_import_keyring():
    try:
        import keyring

        return keyring
    except Exception:
        return None
