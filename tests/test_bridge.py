import json
import os
import queue
import subprocess
import sys
import threading

import pytest

from autopayroll.bridge import Bridge, GuiPrompter

ENV_KEYS = ("UMBC_USR", "UMBC_PAS", "PROFILE_DIR", "PAY_RATE")
# Period 13 runs 2026-09-20 (Sun) .. 2026-10-03 (Sat): two of each weekday.
START, END = "2026-09-20", "2026-10-03"


class FakeChannel:
    def __init__(self):
        self.sent = []
        self._cond = threading.Condition()

    def send(self, message):
        with self._cond:
            self.sent.append(message)
            self._cond.notify_all()

    def event(self, name, **data):
        self.send({"event": name, "data": data})

    def wait_for(self, predicate, timeout=10):
        with self._cond:
            assert self._cond.wait_for(
                lambda: any(predicate(m) for m in self.sent), timeout
            ), f"timed out; sent so far: {self.sent}"
            return next(m for m in self.sent if predicate(m))

    def wait_event(self, name):
        return self.wait_for(lambda m: m.get("event") == name)["data"]

    def reply(self, msg_id):
        return self.wait_for(lambda m: m.get("id") == msg_id)

    def events(self, name):
        return [m["data"] for m in self.sent if m.get("event") == name]


@pytest.fixture
def home(tmp_path, monkeypatch):
    """A throwaway HOME (so ~/.config/autopayroll lands in tmp) and no keyring."""
    saved = dict(os.environ)
    for key in ENV_KEYS:
        os.environ.pop(key, None)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr("autopayroll.config._try_import_keyring", lambda: None)
    yield tmp_path
    os.environ.clear()
    os.environ.update(saved)


@pytest.fixture
def channel():
    return FakeChannel()


@pytest.fixture
def bridge(home, channel):
    b = Bridge(channel)
    yield b
    b.shutdown()


@pytest.fixture
def schedule(home):
    path = home / "schedule.csv"
    path.write_text("day,start,stop\nmon,11:00,13:00\nthu,16:00,18:30\n")
    return str(path)


def _run(bridge, schedule, dry_run, msg_id=1):
    bridge.handle(
        {
            "id": msg_id,
            "method": "run",
            "params": {
                "source": "schedule",
                "start": START,
                "end": END,
                "dry_run": dry_run,
                "schedule_path": schedule,
            },
        }
    )


class TestPrompter:
    def test_answer_unblocks_ask(self, channel):
        prompter = GuiPrompter(channel.event)
        result = []
        thread = threading.Thread(target=lambda: result.append(prompter.text("Name:")))
        thread.start()
        prompt = channel.wait_event("prompt")
        assert (prompt["kind"], prompt["message"]) == ("text", "Name:")
        assert prompter.answer(prompt["id"], "ab12")
        thread.join(5)
        assert result == ["ab12"]
        assert channel.events("prompt_closed") == [{"id": prompt["id"]}]

    def test_close_cancels_open_and_later_prompts(self, channel):
        prompter = GuiPrompter(channel.event)
        result = []
        thread = threading.Thread(target=lambda: result.append(prompter.confirm("Save?")))
        thread.start()
        prompt = channel.wait_event("prompt")
        prompter.close()
        thread.join(5)
        assert result == [None]
        assert prompter.password("Again?") is None  # closed: no new prompt sent
        assert len(channel.events("prompt")) == 1
        assert not prompter.answer(prompt["id"], True)  # already closed


class TestRequests:
    def test_unknown_method_is_an_error(self, bridge, channel):
        bridge.handle({"id": 7, "method": "nope"})
        assert channel.reply(7)["error"]["message"] == "Unknown method: nope"

    def test_init_lists_periods_with_today_selected(self, bridge, channel):
        bridge.handle({"id": 1, "method": "init"})
        result = channel.reply(1)["result"]
        assert result["run"] is None and result["browser_open"] is False
        current = [
            p for p in result["periods"] if p["period"] == result["current_period"]
        ]
        assert len(current) == 1

    def test_save_settings_round_trips(self, bridge, channel):
        bridge.handle(
            {
                "id": 1,
                "method": "save_settings",
                "params": {"username": "ab12", "profile_dir": "/p", "pay_rate": 18.25},
            }
        )
        assert channel.reply(1)["result"] == {
            "username": "ab12",
            "profile_dir": "/p",
            "pay_rate": 18.25,
            "password": None,
        }

    def test_preview_schedule(self, bridge, channel, schedule):
        bridge.handle(
            {
                "id": 1,
                "method": "preview_schedule",
                "params": {"path": schedule, "start": START, "end": END},
            }
        )
        result = channel.reply(1)["result"]
        assert [r["date"] for r in result["rows"]] == [
            "2026-09-21",
            "2026-09-24",
            "2026-09-28",
            "2026-10-01",
        ]
        assert result["summary"]["billed_hours"] == 9.0
        assert result["summary"]["gross"] == 9.0 * 17.5
        assert result["csv_path"] is None

    @pytest.mark.parametrize(
        "params,message",
        [
            ({"source": "schedule", "start": START, "end": END}, "Choose a schedule"),
            ({"source": "trac", "start": "2026-13-01", "end": END}, "Invalid pay period"),
            ({"source": "trac", "start": END, "end": START}, "Invalid pay period"),
            ({"source": "fax", "start": START, "end": END}, "Unknown source"),
        ],
    )
    def test_run_validates_params(self, bridge, channel, params, message):
        bridge.handle({"id": 1, "method": "run", "params": params})
        assert message in channel.reply(1)["error"]["message"]


class TestScheduleRun:
    def test_dry_run_saves_csv_and_skips_peoplesoft(self, bridge, channel, schedule):
        _run(bridge, schedule, dry_run=True)
        assert channel.reply(1)["result"] is None
        finished = channel.wait_event("run_finished")
        assert finished["status"] == "ok"
        assert [(s["stage"], s["status"]) for s in channel.events("stage")] == [
            ("schedule", "active"),
            ("schedule", "done"),
            ("review", "skipped"),
            ("peoplesoft", "skipped"),
            ("verify", "skipped"),
        ]
        (entries,) = channel.events("entries")
        assert len(entries["rows"]) == 4
        assert os.path.exists(entries["csv_path"])
        assert entries["csv_path"].endswith(f"{START}_{END}.csv")
        assert bridge.driver is None  # never needed Firefox

    def test_declining_review_stops_before_firefox(self, bridge, channel, schedule):
        _run(bridge, schedule, dry_run=False)
        prompt = channel.wait_event("prompt")
        assert (prompt["kind"], prompt["stage"]) == ("confirm", "review")
        assert prompt["confirm_label"] == "Enter 4 rows"
        bridge.handle(
            {
                "id": 2,
                "method": "respond",
                "params": {"prompt_id": prompt["id"], "value": False},
            }
        )
        finished = channel.wait_event("run_finished")
        assert finished == {"status": "aborted", "message": "Timesheet entry cancelled."}
        assert ("review", "cancelled") in [
            (s["stage"], s["status"]) for s in channel.events("stage")
        ]
        assert bridge.driver is None

    def test_cancel_releases_open_prompt(self, bridge, channel, schedule):
        _run(bridge, schedule, dry_run=False)
        prompt = channel.wait_event("prompt")
        bridge.handle({"id": 2, "method": "cancel"})
        assert channel.wait_event("run_finished")["status"] == "aborted"
        assert {"id": prompt["id"]} in channel.events("prompt_closed")

    def test_busy_bridge_rejects_changes_and_replays_run(self, bridge, channel, schedule):
        _run(bridge, schedule, dry_run=False)
        prompt = channel.wait_event("prompt")

        _run(bridge, schedule, dry_run=True, msg_id=2)
        assert "Finish or cancel" in channel.reply(2)["error"]["message"]
        bridge.handle({"id": 3, "method": "close_browser"})
        assert "Finish or cancel" in channel.reply(3)["error"]["message"]

        # A reloaded window gets the run's history, open prompt included.
        bridge.handle({"id": 4, "method": "init"})
        run = channel.reply(4)["result"]["run"]
        assert run["params"]["source"] == "schedule"
        replayed = [e["event"] for e in run["events"]]
        assert replayed == ["stage", "stage", "entries", "stage", "prompt"]
        assert run["events"][-1]["data"]["id"] == prompt["id"]

        bridge.handle({"id": 5, "method": "cancel"})
        channel.wait_event("run_finished")


class TestCredentialPrompts:
    def test_cancelling_a_sign_in_prompt_aborts_the_run(
        self, bridge, channel, monkeypatch
    ):
        # Sign-in prompts come from ConfigSettings deep inside a login flow. The
        # window cancels the run when the user declines, which must read as a
        # cancel rather than a missing-password error.
        monkeypatch.setattr(
            Bridge, "_pipeline", lambda self, *args: self.config.get_password()
        )
        bridge.config.update(username="ab12")
        bridge.handle(
            {
                "id": 1,
                "method": "run",
                "params": {"source": "trac", "start": START, "end": END},
            }
        )
        prompt = channel.wait_event("prompt")
        assert prompt["kind"] == "password" and "stage" not in prompt
        bridge.handle({"id": 2, "method": "cancel"})
        assert channel.wait_event("run_finished") == {
            "status": "aborted",
            "message": "Run cancelled.",
        }


def test_bridge_process_speaks_json_lines(home, schedule):
    """Drive a real bridge process over its pipes, like the Tauri shell does."""
    proc = subprocess.Popen(
        [sys.executable, "-m", "autopayroll.bridge"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        env=os.environ.copy(),
    )
    lines = queue.Queue()
    threading.Thread(
        target=lambda: [lines.put(x) for x in proc.stdout], daemon=True
    ).start()

    def send(message):
        proc.stdin.write(json.dumps(message) + "\n")
        proc.stdin.flush()

    def read_until(predicate):
        while True:
            message = json.loads(lines.get(timeout=30))  # every line must be JSON
            if predicate(message):
                return message

    try:
        send({"id": 1, "method": "init"})
        assert "periods" in read_until(lambda m: m.get("id") == 1)["result"]
        send(
            {
                "id": 2,
                "method": "run",
                "params": {
                    "source": "schedule",
                    "start": START,
                    "end": END,
                    "dry_run": True,
                    "schedule_path": schedule,
                },
            }
        )
        finished = read_until(lambda m: m.get("event") == "run_finished")
        assert finished["data"]["status"] == "ok"
        send({"id": 3, "method": "shutdown"})
        assert read_until(lambda m: m.get("id") == 3)["result"] is None
        assert proc.wait(timeout=10) == 0
    finally:
        proc.kill()
