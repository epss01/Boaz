"""Explicit-device, bounded ADB operations. Input requires a fresh matching frame."""

from pathlib import Path
import re
from threading import Lock


def make_adb(adb_path: str, address: str):
    from airtest.core.android.adb import ADB

    class BoundedADB(ADB):
        # Airtest's constructor also issues commands; bound those as well as captures.
        def cmd(self, *args, **kwargs):
            kwargs.setdefault("timeout", 8)
            return super().cmd(*args, **kwargs)

        def connect(self, force=False):
            # The upstream connect probes get_status() without a timeout.
            return self.cmd(["connect", self.serialno], device=False)

    return BoundedADB(serialno=address, adb_path=adb_path)


class Device:
    def __init__(self):
        self._lock = Lock()
        self._connection = None
        self.address = ""
        self.error = ""
        self.frame = None
        self.dimensions = None

    @property
    def connected(self) -> bool:
        return self._connection is not None

    def connect(self, adb_path: str, address: str) -> None:
        with self._lock:
            self._clear()
            try:
                executable = Path(adb_path).expanduser()
                if not adb_path or not executable.is_absolute() or not executable.is_file():
                    raise ValueError("Choose the full path to adb.exe or HD-Adb.exe")
                match = re.fullmatch(r"127\.0\.0\.1:(\d{1,5})", address)
                if not match or not 1 <= int(match[1]) <= 65535:
                    raise ValueError("Use the emulator's local ADB address, for example 127.0.0.1:5555")
                # Explicitly target the supplied instance; never use Airtest's first-device fallback.
                connection = make_adb(str(executable), address)
                result = connection.cmd(["get-state"])
                if result.strip() != "device":
                    raise RuntimeError("Device is offline or unauthorized; enable ADB in BlueStacks")
                frame = self._screenshot(connection)
                self._accept_frame(frame)
                self._connection = connection
                self.address = address
                self.error = ""
            except Exception as exc:
                self.error = f"Connection failed: {exc}"
                raise RuntimeError(self.error) from exc

    @staticmethod
    def _screenshot(connection):
        from airtest.aircv.utils import string_2_img

        png = connection.cmd(["exec-out", "screencap", "-p"], ensure_unicode=False, timeout=8)
        return string_2_img(png)

    def _accept_frame(self, frame) -> None:
        if frame is None or getattr(frame, "size", 0) == 0 or len(frame.shape) != 3:
            raise RuntimeError("Emulator returned an empty or invalid screenshot")
        self.frame = frame
        self.dimensions = (frame.shape[1], frame.shape[0])

    def capture(self):
        with self._lock:
            if self._connection is None:
                raise RuntimeError("Connect the emulator before requesting a screenshot")
            try:
                frame = self._screenshot(self._connection)
                self._accept_frame(frame)
                return frame
            except Exception as exc:
                self._clear()
                self.error = f"Capture failed: {exc}. Check BlueStacks and reconnect."
                raise RuntimeError(self.error) from exc

    def _clear(self):
        self._connection = None
        self.address = ""
        self.frame = None
        self.dimensions = None

    def _point(self, x, y):
        if not self.connected or self.dimensions is None:
            raise RuntimeError("Connect and capture before sending input")
        if type(x) is not int or type(y) is not int or not (0 <= x < self.dimensions[0] and 0 <= y < self.dimensions[1]):
            raise ValueError("Input coordinates must be integer pixels inside the captured screen")

    def tap(self, x: int, y: int, *, allowed=None):
        with self._lock:
            if allowed is not None and not allowed.is_set():
                raise InterruptedError("Input cancelled before dispatch")
            self._point(x, y)
            self._connection.cmd(["shell", "input", "tap", str(x), str(y)], timeout=8)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300):
        with self._lock:
            self._point(x1, y1)
            self._point(x2, y2)
            if type(duration_ms) is not int or not 50 <= duration_ms <= 2000:
                raise ValueError("Swipe duration must be 50–2000 ms")
            self._connection.cmd(["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms)], timeout=8)

    def disconnect(self):
        with self._lock:
            self._clear()
            self.error = ""
