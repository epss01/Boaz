from io import BytesIO
from urllib.error import URLError

import pytest

from boaz import __main__ as launcher


def test_reuses_existing_dashboard(monkeypatch):
    opened = []
    monkeypatch.setattr(launcher, "urlopen", lambda *a, **k: BytesIO(b"<html><title>Boaz workspace</title></html>"))
    monkeypatch.setattr(launcher.webbrowser, "open", opened.append)
    assert launcher.open_existing()
    assert opened == ["http://127.0.0.1:8080"]


def test_no_server_requires_startup(monkeypatch):
    def offline(*args, **kwargs):
        raise URLError("Connection refused")
    monkeypatch.setattr(launcher, "urlopen", offline)
    monkeypatch.setattr(launcher.webbrowser, "open", lambda *a: pytest.fail("Opened before startup"))
    assert not launcher.open_existing()


def test_other_application_is_not_reused(monkeypatch):
    monkeypatch.setattr(launcher, "urlopen", lambda *a, **k: BytesIO(b"<title>Another app</title>"))
    monkeypatch.setattr(launcher.webbrowser, "open", lambda *a: pytest.fail("Opened another application"))
    with pytest.raises(RuntimeError, match="8080"):
        launcher.open_existing()
