from concurrent.futures import ThreadPoolExecutor
import time

import numpy as np
import pytest

from boaz import device as module
from boaz.device import Device


class FakeADB:
    def __init__(self):
        self.calls = []
        self.fail = False
        self.active = 0
        self.max_active = 0

    def cmd(self, args, **kwargs):
        self.calls.append((args, kwargs))
        if args == ["get-state"]:
            return "device\n"
        assert args == ["exec-out", "screencap", "-p"]
        assert kwargs["timeout"] == 8
        if self.fail:
            raise TimeoutError("capture timed out")
        self.active += 1
        self.max_active = max(self.active, self.max_active)
        time.sleep(0.005)
        from airtest.aircv.utils import img_2_string
        result = img_2_string(np.zeros((720, 1280, 3), dtype=np.uint8))
        self.active -= 1
        return result


@pytest.fixture
def connected(tmp_path, monkeypatch):
    executable = tmp_path / "adb.exe"
    executable.touch()
    fake = FakeADB()
    targets = []
    def factory(path, address):
        targets.append((path, address))
        return fake
    monkeypatch.setattr(module, "make_adb", factory)
    device = Device()
    device.connect(str(executable), "127.0.0.1:5557")
    assert targets == [(str(executable), "127.0.0.1:5557")]
    return device, fake


def test_explicit_connection_and_capture(connected):
    device, fake = connected
    assert device.connected
    assert device.dimensions == (1280, 720)
    assert device.capture().shape == (720, 1280, 3)
    assert all(args in (["get-state"], ["exec-out", "screencap", "-p"]) for args, _ in fake.calls)
    assert not hasattr(device, "tap")
    device.disconnect()
    assert not device.connected
    assert device.frame is None


def test_connection_validation(tmp_path):
    device = Device()
    with pytest.raises(RuntimeError, match="full path"):
        device.connect("", "127.0.0.1:5555")
    executable = tmp_path / "adb.exe"
    executable.touch()
    for address in ["", "other-host:5555", "127.0.0.1:99999", "127.0.0.1:0"]:
        with pytest.raises(RuntimeError, match="local ADB"):
            device.connect(str(executable), address)
    assert not device.connected


def test_offline_device(tmp_path, monkeypatch):
    executable = tmp_path / "adb.exe"
    executable.touch()
    fake = FakeADB()
    monkeypatch.setattr(fake, "cmd", lambda *a, **k: "offline")
    monkeypatch.setattr(module, "make_adb", lambda *a: fake)
    device = Device()
    with pytest.raises(RuntimeError, match="offline"):
        device.connect(str(executable), "127.0.0.1:5555")
    assert not device.connected


def test_capture_failure_clears_stale_frame(connected):
    device, fake = connected
    fake.fail = True
    with pytest.raises(RuntimeError, match="reconnect"):
        device.capture()
    assert not device.connected
    assert device.frame is None
    assert device.dimensions is None


def test_captures_are_serialized(connected):
    device, fake = connected
    with ThreadPoolExecutor(max_workers=3) as pool:
        frames = list(pool.map(lambda _: device.capture(), range(3)))
    assert len(frames) == 3
    assert fake.max_active == 1


def test_airtest_constructor_and_commands_are_bounded(tmp_path, monkeypatch):
    from airtest.core.android.adb import ADB
    calls = []
    def command(self, args, **kwargs):
        calls.append((args, kwargs))
        return "device"
    monkeypatch.setattr(ADB, "cmd", command)
    def unbounded_status(*args):
        raise AssertionError("Must not call Airtest's unbounded status probe")
    monkeypatch.setattr(ADB, "get_status", unbounded_status)
    adb = module.make_adb(str(tmp_path / "adb.exe"), "127.0.0.1:5555")
    adb.cmd(["get-state"])
    assert calls == [
        (["connect", "127.0.0.1:5555"], {"device": False, "timeout": 8}),
        (["get-state"], {"timeout": 8}),
    ]
