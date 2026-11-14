import json
import sys
import threading
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[2] / "billbot"))
import homekeeper_billers as hb  # noqa: E402


def test_parse_valid_and_invalid():
    good = json.dumps({"version": 1, "billers": {" Duke-Energy.com ": " Duke Energy ", "x": 3, "": "n"}})
    assert hb.parse(good) == {"duke-energy.com": "Duke Energy"}
    assert hb.parse(good.encode()) == {"duke-energy.com": "Duke Energy"}
    for bad in ("nope", "[]", '{"billers": []}', '{"x": 1}', None, b""):
        assert hb.parse(bad) is None


def test_merge_remote_wins_and_lowercases():
    assert hb.merge({"A.com": "Old", "b.com": "B"}, {"a.com": "New"}) == {"a.com": "New", "b.com": "B"}
    assert hb.merge({"a.com": "A"}, None) == {"a.com": "A"}


def test_cache_round_trip(tmp_path):
    path = tmp_path / "sub" / "cache.json"
    assert hb.read_cache(path) is None
    hb.write_cache({"a.com": "A"}, path)
    assert hb.read_cache(path) == {"a.com": "A"}
    path.write_text("garbage")
    assert hb.read_cache(path) is None


class FakeClient:
    """Mimics paho: delivers one retained message after connect."""

    def __init__(self, payload=None, fail=False):
        self.payload, self.fail = payload, fail
        self.subscribed, self.stopped = [], False

    def username_pw_set(self, *a):
        pass

    def connect_async(self, *a, **k):
        if self.fail:
            raise OSError("no broker")

    def loop_start(self):
        def go():
            self.on_connect(self, None, None, 0)
            if self.payload is not None:
                msg = type("M", (), {"payload": self.payload})()
                self.on_message(self, None, msg)

        threading.Thread(target=go).start()

    def subscribe(self, topic, qos=0):
        self.subscribed.append(topic)

    def disconnect(self):
        pass

    def loop_stop(self):
        self.stopped = True


def test_fetch_reads_retained_list():
    payload = json.dumps({"version": 1, "billers": {"a.com": "A"}}).encode()
    fake = FakeClient(payload)
    assert hb.fetch("broker", wait=2, client_factory=lambda: fake) == {"a.com": "A"}
    assert fake.subscribed == [hb.TOPIC] and fake.stopped


def test_fetch_failure_modes_return_none():
    assert hb.fetch("", client_factory=FakeClient) is None
    assert hb.fetch("broker", wait=0.2, client_factory=lambda: FakeClient(None)) is None
    assert hb.fetch("broker", wait=0.2, client_factory=lambda: FakeClient(fail=True)) is None
    assert hb.fetch("broker", wait=0.5, client_factory=lambda: FakeClient(b"junk")) is None


@pytest.fixture
def clean(tmp_path, monkeypatch):
    monkeypatch.setattr(hb, "CACHE_FILE", tmp_path / "cache.json")
    hb._memo.update(at=0.0, value=None)
    yield
    hb._memo.update(at=0.0, value=None)


def test_remote_billers_falls_back_to_cache_when_broker_is_down(clean, monkeypatch):
    hb.write_cache({"cached.com": "Cached"}, hb.CACHE_FILE)
    monkeypatch.setattr(hb, "fetch", lambda *a, **k: None)
    assert hb.remote_billers("broker") == {"cached.com": "Cached"}


def test_remote_billers_caches_in_memory_and_on_disk(clean, monkeypatch):
    calls = []
    monkeypatch.setattr(hb, "fetch", lambda *a, **k: calls.append(1) or {"a.com": "A"})
    assert hb.remote_billers("broker") == {"a.com": "A"}
    assert hb.remote_billers("broker") == {"a.com": "A"}
    assert len(calls) == 1  # second call used the in-memory copy
    assert hb.read_cache(hb.CACHE_FILE) == {"a.com": "A"}


def test_from_env_without_mqtt_returns_local_only(clean, monkeypatch):
    monkeypatch.delenv("BILLBOT_MQTT_HOST", raising=False)
    assert hb.from_env({"A.com": "A"}) == {"a.com": "A"}
    monkeypatch.setenv("BILLBOT_MQTT_HOST", "broker")
    monkeypatch.setattr(hb, "fetch", lambda *a, **k: {"b.com": "B"})
    assert hb.from_env({"a.com": "A"}) == {"a.com": "A", "b.com": "B"}
