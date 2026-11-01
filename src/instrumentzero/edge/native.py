"""Build the packaged reviewed C core with a local free C compiler; no network."""
from __future__ import annotations

import ctypes as ct
import functools
import hashlib
import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

import numpy as np

from .spec import EdgeError

CORE = Path(__file__).with_name("core")


def core_identity():
    return hashlib.sha256((CORE / "iz_core.h").read_bytes() + (CORE / "iz_core.c").read_bytes()).hexdigest()


@functools.lru_cache(maxsize=1)
def library():
    compiler = shutil.which("clang") or shutil.which("cc")
    if not compiler:
        raise EdgeError("Install a free C99 compiler (Clang or GCC) to execute the Edge core.")
    folder = Path(tempfile.mkdtemp(prefix="instrumentzero-edge-core-"))
    target = folder / ("core.dylib" if platform.system() == "Darwin" else "core.so")
    command = [compiler, "-std=c99", "-O2", "-fPIC", "-shared", str(CORE / "iz_core.c"), "-o", str(target)]
    run = subprocess.run(command, capture_output=True, text=True)
    if run.returncode:
        raise EdgeError(f"C core compilation failed: {run.stderr[:2000]}")
    lib = ct.CDLL(str(target))
    lib.iz_state_bytes.restype = ct.c_size_t
    fp = ct.POINTER(ct.c_float)
    lib.iz_init.argtypes = [ct.c_void_p, ct.c_uint32, fp, fp, fp, ct.c_uint32, ct.c_uint32]
    lib.iz_process.argtypes = [ct.c_void_p, fp, ct.c_size_t, fp, ct.c_size_t, ct.POINTER(ct.c_size_t)]
    return lib


def _pointer(a):
    return a.ctypes.data_as(ct.POINTER(ct.c_float))


class Processor:
    """One isolated stream with state continuous across arbitrary chunk boundaries."""
    def __init__(self, scale, offset, coefficients, decimation):
        arrays = [np.ascontiguousarray(a, dtype=np.float32) for a in (scale, offset, coefficients)]
        if (any(a.ndim != 1 for a in arrays) or not 1 <= len(arrays[0]) <= 3 or
                len(arrays[1]) != len(arrays[0]) or not 1 <= len(arrays[2]) <= 255 or
                isinstance(decimation, bool) or not isinstance(decimation, int) or not 1 <= decimation <= 8):
            raise EdgeError("Native configuration needs matching 1-D calibration vectors, 1–255 taps and integer decimation 1–8.")
        self.lib = library()
        self.state = ct.create_string_buffer(self.lib.iz_state_bytes())
        self.channels = len(scale)
        self.decimation = decimation
        self._config = tuple(tuple(float(v) for v in a) for a in arrays) + (decimation,)
        rc = self.lib.iz_init(self.state, self.channels, *[_pointer(a) for a in arrays], len(coefficients), decimation)
        if rc:
            raise EdgeError(f"Native processor rejected configuration ({rc}).")

    @property
    def state_bytes(self):
        return self.lib.iz_state_bytes()

    def reset(self):
        self.__init__(*self._config)

    def process(self, samples):
        data = np.ascontiguousarray(samples, dtype=np.float32)
        if data.ndim == 1:
            data = data[:, None]
        if data.ndim != 2 or data.shape[1] != self.channels:
            raise EdgeError("Native input shape does not match declared channels.")
        capacity = len(data) // self.decimation + 1
        output = np.empty((capacity, self.channels), np.float32)
        written = ct.c_size_t()
        rc = self.lib.iz_process(self.state, _pointer(data), len(data), _pointer(output), capacity, ct.byref(written))
        if rc:
            raise EdgeError(f"Native processor rejected samples ({rc}).")
        return output[:written.value].copy()
