"""Typed exceptions for the autopayroll pipeline.

Low-level layers (scraper, automator) raise these so the interface can catch a
failure in one place, tell the user what went wrong, and return to the menu with
the browser still alive instead of charging ahead into a broken page state.
"""


class AutoPayrollError(Exception):
    """Base class for all expected, user-facing autopayroll failures."""


class LoginError(AutoPayrollError):
    """Login could not be completed (missing credentials, form never loaded)."""


class PageStateError(AutoPayrollError):
    """The page was not in the expected state (iframe/field missing)."""


class UserAbort(AutoPayrollError):
    """The user cancelled a prompt (Ctrl-C / Esc) and the run should stop."""
