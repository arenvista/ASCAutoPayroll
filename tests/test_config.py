import os
import stat

import pytest

from autopayroll.config import DEFAULT_PAY_RATE, ConfigSettings
from autopayroll.errors import LoginError

ENV_KEYS = ("UMBC_USR", "UMBC_PAS", "PROFILE_DIR", "PAY_RATE")


@pytest.fixture
def home(tmp_path, monkeypatch):
    saved = dict(os.environ)
    for key in ENV_KEYS:
        os.environ.pop(key, None)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("autopayroll.config._try_import_keyring", lambda: None)
    yield tmp_path
    os.environ.clear()
    os.environ.update(saved)


def _fresh_config():
    """A new ConfigSettings that reads only the settings file, as on next launch."""
    for key in ENV_KEYS:
        os.environ.pop(key, None)
    return ConfigSettings()


class Declines:
    def text(self, message):
        return None

    def password(self, message):
        return None

    def confirm(self, message, default=True):
        return None


class TestUpdate:
    def test_writes_settings_and_applies_them(self, home):
        config = ConfigSettings()
        config.update(username=" ab12 ", profile_dir="/tmp/profile", pay_rate=18.25)
        assert (config.umbc_usr, config.profile_dir, config.pay_rate) == (
            "ab12",
            "/tmp/profile",
            18.25,
        )
        assert stat.S_IMODE(config.config_path.stat().st_mode) == 0o600

        again = _fresh_config()
        assert (again.umbc_usr, again.profile_dir, again.pay_rate) == (
            "ab12",
            "/tmp/profile",
            18.25,
        )

    def test_blank_values_clear_settings(self, home):
        config = ConfigSettings()
        config.update(username="ab12", profile_dir="/tmp/profile")
        config.update(username="", profile_dir="")
        assert config.umbc_usr is None and config.profile_dir is None
        assert _fresh_config().umbc_usr is None

    def test_rejects_non_positive_pay_rate(self, home):
        with pytest.raises(ValueError):
            ConfigSettings().update(pay_rate=0)


class TestPayRate:
    def test_defaults_when_unset(self, home):
        assert ConfigSettings().pay_rate == DEFAULT_PAY_RATE

    def test_invalid_value_falls_back_to_default(self, home):
        ConfigSettings()  # creates the settings file
        settings = home / ".config" / "autopayroll" / "settings.env"
        settings.write_text(
            settings.read_text().replace('PAY_RATE=""', 'PAY_RATE="lots"')
        )
        assert _fresh_config().pay_rate == DEFAULT_PAY_RATE


class TestCredentials:
    def test_cancelled_username_prompt_is_a_login_error(self, home):
        with pytest.raises(LoginError):
            ConfigSettings(prompter=Declines()).get_username()

    def test_cancelled_password_prompt_is_a_login_error(self, home):
        config = ConfigSettings(prompter=Declines())
        config.update(username="ab12")
        with pytest.raises(LoginError):
            config.get_password()

    def test_password_source(self, home):
        config = ConfigSettings()
        assert config.password_source() is None
        config._env_password = "hunter2"
        assert config.password_source() == "file"
