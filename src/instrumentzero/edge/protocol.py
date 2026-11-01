"""IZP1 binary frames: bounded, little endian, CRC32 and exact configuration binding."""
from __future__ import annotations

import struct
import uuid
import zlib
from dataclasses import dataclass

import numpy as np

from .spec import EdgeError

HEADER = struct.Struct("<4sBBH16sIIQIHH32s")
CRC = struct.Struct("<I")
MAX_FRAME = HEADER.size + 256 * (4 + 3 * 4) + CRC.size
MAGIC = b"IZP1"


@dataclass
class Frame:
    session: str
    epoch: int
    sequence: int
    rate_hz: int
    spec_sha256: str
    timestamps_us: np.ndarray
    samples: np.ndarray
    flags: int = 0
    kind: int = 1


def encode(frame: Frame) -> bytes:
    y = np.asarray(frame.samples, dtype="<f4")
    t = np.asarray(frame.timestamps_us)
    if (y.ndim != 2 or not 1 <= len(y) <= 256 or not 1 <= y.shape[1] <= 3 or
            t.shape != (len(y),) or not np.issubdtype(t.dtype, np.integer) or
            np.any(t < 0) or np.any(t[1:] <= t[:-1]) or
            not np.all(np.isfinite(y)) or np.any(np.abs(y) > 1e6) or
            int(t[-1]) - int(t[0]) > 0xffffffff):
        raise EdgeError("Invalid frame dimensions, timestamps, or sample representation.")
    try:
        digest = bytes.fromhex(frame.spec_sha256)
        if len(digest) != 32:
            raise ValueError("SHA-256 needs 32 bytes")
        head = HEADER.pack(MAGIC, 1, frame.kind, frame.flags, uuid.UUID(frame.session).bytes, frame.epoch,
                           frame.sequence, int(t[0]), frame.rate_hz, len(y), y.shape[1], digest)
    except (ValueError, struct.error, OverflowError) as exc:
        raise EdgeError(f"Invalid frame header: {exc}") from exc
    offsets = (t - t[0]).astype("<u4")
    body = head + offsets.tobytes() + y.tobytes()
    return body + CRC.pack(zlib.crc32(body))


def decode(data: bytes) -> Frame:
    if not HEADER.size + CRC.size < len(data) <= MAX_FRAME:
        raise EdgeError("Truncated or oversized frame.")
    magic, version, kind, flags, session, epoch, seq, tick, rate, n, ch, digest = HEADER.unpack_from(data)
    if magic != MAGIC or version != 1 or kind not in (1, 2, 3) or flags & ~3:
        raise EdgeError("Unsupported protocol, frame kind, or flags.")
    if not 1 <= n <= 256 or not 1 <= ch <= 3 or not 1 <= rate <= 48000:
        raise EdgeError("Frame rate or allocation is outside protocol bounds.")
    if len(data) != HEADER.size + n * (4 + ch * 4) + CRC.size:
        raise EdgeError("Payload length does not match header.")
    if zlib.crc32(data[:-4]) != CRC.unpack_from(data, len(data) - 4)[0]:
        raise EdgeError("Frame integrity CRC mismatch.")
    offsets = np.frombuffer(data, "<u4", n, HEADER.size).astype(np.uint64)
    if offsets[0] != 0 or np.any(offsets[1:] <= offsets[:-1]) or tick > 0xffffffffffffffff - int(offsets[-1]):
        raise EdgeError("Invalid or overflowing timestamp offsets.")
    y = np.frombuffer(data, "<f4", n * ch, HEADER.size + n * 4).reshape(n, ch).copy()
    if not np.all(np.isfinite(y)) or np.any(np.abs(y) > 1e6):
        raise EdgeError("Nonfinite or out-of-contract samples.")
    return Frame(str(uuid.UUID(bytes=session)), epoch, seq, rate, digest.hex(), offsets + tick, y, flags, kind)


class TickUnwrapper:
    """Unwrap a 32-bit microsecond counter; half-range ambiguity fails closed."""
    def __init__(self):
        self.previous = None
        self.extended = 0

    def update(self, tick):
        if not isinstance(tick, int) or not 0 <= tick <= 0xffffffff:
            raise EdgeError("Expected a uint32 clock tick.")
        if self.previous is None:
            self.extended = tick
        else:
            delta = (tick - self.previous) & 0xffffffff
            if not 0 < delta < 0x80000000:
                raise EdgeError("Repeated or ambiguous/backward device clock.")
            self.extended += delta
        self.previous = tick
        return self.extended


class Validator:
    """One epoch only. Any data fault poisons the epoch until explicit reconfiguration."""
    def __init__(self, compiled, session, epoch=0, kind=1):
        self.compiled = compiled
        self.session = session
        self.epoch = epoch
        self.kind = kind
        self.expected = 0
        self.last_tick = None
        self.first_tick = None
        self.count = 0
        self.failed = None
        self.deltas = []

    def accept(self, data: bytes):
        if self.failed:
            raise EdgeError(f"Epoch already invalid: {self.failed}")
        try:
            f = decode(data)
            s = self.compiled["spec"]["source"]
            if (f.session != self.session or f.epoch != self.epoch or
                    f.spec_sha256 != self.compiled["spec_sha256"]):
                raise EdgeError("Session/epoch/configuration mismatch; never splice streams.")
            expected_rate = self.compiled["output_rate_hz"] if self.kind == 3 else s["rate_hz"]
            block = self.compiled["spec"]["resources"]["block_samples"]
            d = self.compiled["spec"]["dsp"]["decimation"] if self.kind == 3 else 1
            if len(f.samples) > (block+d-1)//d:
                raise EdgeError("Frame exceeds the configured block allocation for this stream kind.")
            if f.kind != self.kind or f.rate_hz != expected_rate or f.samples.shape[1] != len(s["channels"]):
                raise EdgeError("Frame rate/channel binding mismatch.")
            if f.sequence != self.expected:
                raise EdgeError("Dropped, repeated, or reordered samples (sequence mismatch).")
            if f.flags:
                raise EdgeError("Device reports clipping or acquisition overrun.")
            if self.kind == 1 and np.any(np.abs(f.samples) >= s["full_scale"] * .999):
                raise EdgeError("Samples clip the declared input range.")
            ticks = f.timestamps_us.astype(np.int64)
            if np.any(f.timestamps_us > np.iinfo(np.int64).max):
                raise EdgeError("Timestamp exceeds signed host analysis range.")
            if self.last_tick is not None:
                ticks = np.r_[self.last_tick, ticks]
            deltas = np.diff(ticks)
            nominal = 1e6 / f.rate_hz
            if np.any(np.abs(deltas - nominal) > max(2, nominal * .25)):
                raise EdgeError("Clock jump, repeated timestamp, or excessive sample jitter.")
            if self.count + len(f.samples) > 200000:
                raise EdgeError("Session exceeds 200000 sample allocation.")
            self.deltas.extend(deltas.tolist())
            self.last_tick = int(f.timestamps_us[-1])
            if self.first_tick is None:
                self.first_tick = int(f.timestamps_us[0])
            self.expected = (self.expected + len(f.samples)) & 0xffffffff
            self.count += len(f.samples)
            return f
        except EdgeError as exc:
            self.failed = str(exc)
            raise

    def timing(self):
        observed = (self.count - 1) * 1e6 / (self.last_tick - self.first_tick) if self.count > 1 else None
        nominal = self.compiled["output_rate_hz"] if self.kind == 3 else self.compiled["spec"]["source"]["rate_hz"]
        return {"nominal_rate_hz": nominal, "measured_rate_hz": observed,
                "mean_clock_disagreement_ppm": (observed / nominal - 1) * 1e6 if observed else None,
                "period_jitter_std_us": float(np.std(self.deltas)) if self.deltas else None,
                "max_period_error_us": float(np.max(np.abs(np.asarray(self.deltas) - 1e6/nominal))) if self.deltas else None,
                "timestamp_location": "per-sample adapter timestamps; hardware semantics in manifest",
                "host_device_mapping": "No shared epoch or independent clock calibration; device-relative duration only."}
