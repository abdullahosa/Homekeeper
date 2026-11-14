"""Optional BillBot add-on: take the biller list from Homekeeper.

Homekeeper publishes a retained message on `homekeeper/billers`:
    {"version": 1, "billers": {"duke-energy.com": "Duke Energy", ...}}
Drop this file next to billbot.py and change load_billers() as described in
BILLBOT-PATCH.md. BillBot then merges that list over billers.json, so adding or
removing a biller in Home Assistant needs no file edit and no restart.

Safe by design: if MQTT or the message is missing it falls back to the last good
copy on disk, then to billers.json alone. It never raises into BillBot.
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

TOPIC = "homekeeper/billers"
CACHE_FILE = Path(os.environ.get("BILLBOT_HK_CACHE", "/var/lib/billbot/homekeeper-billers.json"))
TTL_SECONDS = 60  # how long one fetch is reused (load_billers() is called often)

_memo: dict[str, Any] = {"at": 0.0, "value": None}


def parse(payload: bytes | str) -> dict[str, str] | None:
    """The domain -> name mapping from a message, or None if it isn't valid."""
    try:
        data = json.loads(payload)
        billers = data["billers"]
    except (TypeError, ValueError, KeyError):
        return None
    if not isinstance(billers, dict):
        return None
    out = {}
    for key, name in billers.items():
        if isinstance(key, str) and isinstance(name, str) and key.strip() and name.strip():
            out[key.strip().lower()] = name.strip()
    return out


def merge(local: dict[str, str], remote: dict[str, str] | None) -> dict[str, str]:
    """billers.json first, Homekeeper's list on top (Homekeeper is the source of truth)."""
    merged = {k.lower(): v for k, v in local.items()}
    merged.update(remote or {})
    return merged


def read_cache(path: Path | None = None) -> dict[str, str] | None:
    path = path or CACHE_FILE
    try:
        return parse(path.read_text(encoding="utf-8"))
    except OSError:
        return None


def write_cache(billers: dict[str, str], path: Path | None = None) -> None:
    path = path or CACHE_FILE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps({"version": 1, "billers": billers}), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass  # a cache that can't be written is not worth failing over


def fetch(
    host: str,
    port: int = 1883,
    user: str = "",
    password: str = "",
    wait: float = 3.0,
    client_factory: Callable[[], Any] | None = None,
) -> dict[str, str] | None:
    """Connect, read the retained biller list, disconnect. None if nothing arrived."""
    if not host:
        return None
    got: dict[str, Any] = {}
    done = threading.Event()

    def on_connect(client, *_args):
        client.subscribe(TOPIC, qos=1)

    def on_message(_client, _userdata, msg):
        parsed = parse(msg.payload)
        if parsed is not None:
            got["billers"] = parsed
            done.set()

    try:
        if client_factory is not None:
            client = client_factory()
        else:
            import paho.mqtt.client as mqtt

            try:  # paho-mqtt 2.x
                client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="billbot-hk-billers")
            except AttributeError:  # paho-mqtt 1.x
                client = mqtt.Client(client_id="billbot-hk-billers")
        if user:
            client.username_pw_set(user, password)
        client.on_connect = on_connect
        client.on_message = on_message
        client.connect_async(host, port, keepalive=30)
        client.loop_start()
        try:
            done.wait(wait)
        finally:
            client.disconnect()
            client.loop_stop()
    except Exception:  # noqa: BLE001 - never break BillBot over an optional feed
        return None
    return got.get("billers")


def remote_billers(
    host: str, port: int = 1883, user: str = "", password: str = "", **kw: Any
) -> dict[str, str]:
    """Homekeeper's list: fresh if reachable, else the last good copy, else empty."""
    now = time.monotonic()
    if _memo["value"] is not None and now - _memo["at"] < TTL_SECONDS:
        return _memo["value"]
    fetched = fetch(host, port, user, password, **kw)
    if fetched is not None:
        write_cache(fetched)
        value = fetched
    else:
        value = read_cache() or {}
    _memo.update(at=now, value=value)
    return value


def from_env(local: dict[str, str]) -> dict[str, str]:
    """What BillBot's load_billers() calls: local file merged with Homekeeper's list."""
    host = os.environ.get("BILLBOT_MQTT_HOST", "")
    if not host:
        return merge(local, None)
    remote = remote_billers(
        host,
        int(os.environ.get("BILLBOT_MQTT_PORT", "1883")),
        os.environ.get("BILLBOT_MQTT_USER", ""),
        os.environ.get("BILLBOT_MQTT_PASSWORD", ""),
    )
    return merge(local, remote)
