"""Self-process RSS sampling without process-list permissions or third-party modules."""

import ctypes
import json
from pathlib import Path
import platform
import threading
import time


def rss_reader():
    if platform.system() == "Linux":
        def read():
            text = Path("/proc/self/status").read_text()
            line = next(line for line in text.splitlines() if line.startswith("VmRSS:"))
            return int(line.split()[1]) * 1024
        return read, "/proc/self/status"
    if platform.system() != "Darwin":
        raise RuntimeError("RSS sampling currently supports macOS and Linux")

    # Apple's public MACH_TASK_BASIC_INFO layout:
    # https://github.com/apple-oss-distributions/xnu/blob/main/osfmk/mach/task_info.h
    class Info(ctypes.Structure):
        _fields_ = [
            ("virtual_size", ctypes.c_uint64), ("resident_size", ctypes.c_uint64),
            ("resident_size_max", ctypes.c_uint64), ("user_time", ctypes.c_int32 * 2),
            ("system_time", ctypes.c_int32 * 2), ("policy", ctypes.c_int32),
            ("suspend_count", ctypes.c_int32),
        ]

    library = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
    task = ctypes.c_uint.in_dll(library, "mach_task_self_").value
    library.task_info.argtypes = [
        ctypes.c_uint, ctypes.c_uint, ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint),
    ]
    library.task_info.restype = ctypes.c_int

    def read():
        info = Info()
        count = ctypes.c_uint(ctypes.sizeof(info) // ctypes.sizeof(ctypes.c_uint32))
        code = library.task_info(task, 20, ctypes.byref(info), ctypes.byref(count))
        if code:
            raise OSError(f"MACH_TASK_BASIC_INFO failed: {code}")
        return info.resident_size

    return read, "self MACH_TASK_BASIC_INFO.resident_size"


class RSSSampler:
    def __init__(self, path, interval):
        self.path = path
        self.interval = interval
        self.read, self.method = rss_reader()
        self.stop = threading.Event()
        self.phase = ("ready", None)
        self.count = 0
        self.peak = 0
        self.error = None
        self.thread = threading.Thread(target=self.sample, name="benchmark-rss", daemon=True)

    def sample(self):
        start = time.perf_counter()
        try:
            with self.path.open("w") as target:
                while True:
                    stamp = time.perf_counter()
                    phase, native_start = self.phase
                    rss = self.read()
                    self.peak = max(self.peak, rss)
                    self.count += 1
                    point = {"since_sampler_start_seconds": stamp - start,
                             "rss_bytes": rss, "phase": phase,
                             "native_elapsed_seconds": stamp - native_start
                             if native_start is not None else None}
                    target.write(json.dumps(point) + "\n")
                    target.flush()
                    if self.stop.is_set():
                        break
                    self.stop.wait(self.interval)
        except Exception as error:
            self.error = error

    def __enter__(self):
        if self.read() <= 0:
            raise RuntimeError("Self RSS reading is unavailable")
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, traceback):
        self.phase = ("finished" if exc_type is None else "failed", None)
        self.stop.set()
        self.thread.join()
        if exc_type is None and self.error is not None:
            raise RuntimeError("RSS snapshots failed") from self.error
