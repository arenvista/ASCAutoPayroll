"""Prompts that can fire inside shared pipeline code.

Credentials are resolved lazily, deep inside the TRAC and PeopleSoft login
flows that both front-ends share, so ConfigSettings asks through a prompter
instead of calling questionary itself. The CLI uses ConsolePrompter; the
desktop bridge passes one that asks through the window.

questionary is called only by interface.py, timeblocks.prompt_for_timeblock,
scraper.fetch_and_save_html, automator.run, and ConsolePrompter. The bridge
never calls any of those.
"""

from typing import Protocol

import questionary


class Prompter(Protocol):
    """Each method returns None if the user cancels."""

    def text(self, message: str) -> str | None: ...

    def password(self, message: str) -> str | None: ...

    def confirm(self, message: str, default: bool = True) -> bool | None: ...


class ConsolePrompter:
    """Terminal prompts via questionary."""

    def text(self, message: str) -> str | None:
        return questionary.text(message).ask()

    def password(self, message: str) -> str | None:
        return questionary.password(message).ask()

    def confirm(self, message: str, default: bool = True) -> bool | None:
        return questionary.confirm(message, default=default).ask()
