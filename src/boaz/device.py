"""Explicit-device, bounded ADB operations. Input requires a fresh matching frame."""

from pathlib import Path
import re
from threading import Lock
import time


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

        def push(self, local, remote):
            # Upstream treats the extensionless minitouch binary as a directory.
            return self.cmd(['push',str(local),remote])

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

        for _ in range(3):
            png = connection.cmd(["exec-out", "screencap", "-p"], ensure_unicode=False, timeout=8)
            frame = string_2_img(png)
            if frame is not None and frame.size and frame.any():
                return frame
        raise RuntimeError("Emulator returned only black frames; restore the game window and reconnect")

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

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 300, *, allowed=None):
        with self._lock:
            if allowed is not None and not allowed.is_set():
                raise InterruptedError("Camera input cancelled before dispatch")
            self._point(x1, y1)
            self._point(x2, y2)
            if type(duration_ms) is not int or not 50 <= duration_ms <= 2000:
                raise ValueError("Swipe duration must be 50–2000 ms")
            self._connection.cmd(["shell", "input", "swipe", str(x1), str(y1), str(x2), str(y2), str(duration_ms)], timeout=8)

    def disconnect(self):
        with self._lock:
            self._clear()
            self.error = ""

    def zoom_out(self, *, allowed=None):
        from airtest.core.android.touch_methods.minitouch import Minitouch
        with self._lock:
            if allowed is not None and not allowed.is_set():
                raise InterruptedError('Camera normalization cancelled')
            self._point(640,320)
            if self.dimensions != (1280,720):
                raise ValueError('Camera normalization supports English 1280×720 only')
            touch=Minitouch(self._connection,size_info={'width':1280,'height':720})
            send=None
            try:
                touch.install_and_setup()
                send=touch.handle
                def guarded(command):
                    if allowed is not None and not allowed.is_set():
                        raise InterruptedError('Camera normalization cancelled')
                    send(command)
                def contacts(verb,points):
                    commands=[]
                    for contact,(x,y) in enumerate(points):
                        nx,ny=touch.transform_xy(x,y)
                        commands.append(f'{verb} {contact} {nx} {ny} {touch.default_pressure}')
                    guarded('\n'.join(commands)+'\nc\n')
                # Commit both contacts together so a pinch cannot become a pan.
                contacts('d',[(256,104),(1024,536)])
                for step in range(1,6):
                    time.sleep(.1)
                    contacts('m',[(256+(620-256)*step/5,104+(310-104)*step/5),
                                  (1024+(660-1024)*step/5,536+(330-536)*step/5)])
            finally:
                if send is not None:
                    send('u 0\nu 1\nc\n')
                touch.teardown()
