"""Bounded runtime configuration. Generating bytes never opens hardware."""

from __future__ import annotations

import secrets
import struct
import time
import uuid
import zlib

import numpy as np

from .planner import measure_costs, plan
from .spec import EdgeError, compile_graph, integer, number

CONFIG = struct.Struct("<4sBBHIIHHHBB32sffI")
ACK = struct.Struct("<4sBBHII16s32sI")
MODES = ("raw_host", "calibrated_edge", "filtered_edge")
MAX_CONFIG_BYTES = 1092


def configuration(spec, placement="raw_host", request_id=None):
    compiled = compile_graph(spec)
    s = compiled["spec"]
    if s["source"]["adapter"] != "zephyr_adxl345" or placement not in MODES:
        raise EdgeError(
            "Runtime device configuration requires the provisional ADXL345 adapter and a reviewed placement."
        )
    scale, offset = np.float32(s["calibration"]["scale"][0]), np.float32(s["calibration"]["offset"][0])
    if not np.isfinite(scale) or scale == 0 or not np.isfinite(offset):
        raise EdgeError("Calibration is not representable by the device float32 core.")
    candidate = next(
        c for c in plan(compiled, measure_costs(compiled))["candidates"] if c["mode"] == placement
    )
    if not candidate["legal_under_declared_model"]:
        raise EdgeError("Runtime configuration violates resources: " + "; ".join(candidate["reasons"]))
    request_id = (
        secrets.randbits(32) if request_id is None else integer(request_id, 0, 0xFFFFFFFF, "request ID")
    )
    payload = CONFIG.pack(
        b"IZC1",
        1,
        1,
        int(s["resources"]["raw_validation"]),
        request_id,
        s["source"]["rate_hz"],
        s["resources"]["block_samples"],
        s["resources"]["queue_blocks"],
        s["dsp"]["taps"],
        s["dsp"]["decimation"],
        MODES.index(placement),
        bytes.fromhex(compiled["spec_sha256"]),
        scale,
        offset,
        0,
    )
    payload += np.asarray(compiled["coefficients"], dtype="<f4").tobytes()
    payload += struct.pack("<I", zlib.crc32(payload))
    assert len(payload) <= MAX_CONFIG_BYTES
    return b"C" + struct.pack("<H", len(payload)) + payload, compiled


def decode_ack(data):
    if len(data) != ACK.size:
        raise EdgeError("Truncated runtime configuration acknowledgement.")
    magic, version, status, flags, request_id, epoch, sid, digest, crc = ACK.unpack(data)
    mode, raw = flags & 255, flags >> 8
    if (
        magic != b"IZA1"
        or version != 1
        or status not in range(4)
        or mode > 2
        or raw > 1
        or zlib.crc32(data[:-4]) != crc
    ):
        raise EdgeError("Invalid runtime configuration acknowledgement.")
    return {
        "request_id": request_id,
        "epoch": epoch,
        "session": str(uuid.UUID(bytes=sid)),
        "spec_sha256": digest.hex(),
        "placement": MODES[mode],
        "raw_validation": bool(raw),
        "status": status,
    }


def write_all(port, data, deadline):
    sent = 0
    while sent < len(data):
        if time.monotonic() >= deadline:
            raise EdgeError("Serial control write timed out; acquisition stays stopped.")
        try:
            n = port.write(data[sent:])
        except BlockingIOError:
            port.read(0.005)
            continue
        if n is None or not 0 <= n <= len(data) - sent:
            raise EdgeError("Invalid serial control write count.")
        if n == 0:
            port.read(0.005)
        sent += n


class DeviceController:
    """Control an already-owned port; no implicit open, flash or sensor start.

    Call configure before every start. Capture data only after a matching ACK.
    Reconfiguration stops first; buffered prior-session bytes are discarded during
    the ACK search and never returned as new-epoch samples.
    """

    def __init__(self, port):
        self.port = port
        self.accepted = None
        self.compiled = None
        self.last_epoch = None
        self.accepted_at = None

    def stop(self):
        self.accepted = None
        write_all(self.port, b"S", time.monotonic() + 1)
        self.port.started = False
        self.port.control_pending = False

    def configure(self, spec, placement="raw_host", timeout=2.0):
        number(timeout, 0.1, 5.0, "configuration timeout")
        request, compiled = configuration(spec, placement)
        self.stop()
        self.compiled = None
        deadline = time.monotonic() + timeout
        try:
            self.port.control_pending = True
            write_all(self.port, request, deadline)
            request_id = struct.unpack_from("<I", request, 11)[0]
            buffer = bytearray()
            discarded = 0
            while time.monotonic() < deadline:
                chunk = self.port.read(min(0.05, max(0.0, deadline - time.monotonic())))
                if chunk == b"":
                    raise EdgeError("Device disconnected during configuration.")
                if chunk:
                    buffer.extend(chunk)
                while len(buffer) >= ACK.size:
                    start = buffer.find(b"IZA1")
                    if start < 0:
                        discarded += len(buffer) - 3
                        del buffer[:-3]
                        break
                    discarded += start
                    del buffer[:start]
                    if len(buffer) < ACK.size:
                        break
                    raw = bytes(buffer[: ACK.size])
                    try:
                        accepted = decode_ack(raw)
                    except EdgeError:
                        discarded += 1
                        del buffer[:1]
                        continue
                    del buffer[: ACK.size]
                    if accepted["request_id"] != request_id:
                        discarded += ACK.size
                        continue
                    if accepted["status"]:
                        raise EdgeError(
                            "Device rejected configuration (status " + str(accepted["status"]) + ")."
                        )
                    if (
                        accepted["spec_sha256"] != compiled["spec_sha256"]
                        or accepted["placement"] != placement
                        or accepted["raw_validation"] != compiled["spec"]["resources"]["raw_validation"]
                        or (self.last_epoch is not None and accepted["epoch"] <= self.last_epoch)
                    ):
                        raise EdgeError(
                            "Acknowledgement does not bind the requested configuration or a fresh epoch."
                        )
                    if buffer:
                        raise EdgeError("Device emitted unexpected bytes after ACK before explicit start.")
                    self.accepted = accepted
                    self.compiled = compiled
                    self.last_epoch = accepted["epoch"]
                    self.accepted_at = time.monotonic()
                    return {
                        "accepted": accepted,
                        "configuration_hex": request.hex(),
                        "acknowledgement_hex": raw.hex(),
                        "discarded_prior_bytes": discarded,
                        "hardware_operation_verified": False,
                    }
                if discarded + len(buffer) > 16 * 1024 * 1024:
                    raise EdgeError("Configuration response exceeds the bounded receive window.")
            raise EdgeError("No matching configuration acknowledgement; no start command sent.")
        except BaseException:
            self.accepted = None
            # A partially transmitted control frame may consume this S as payload.
            # Firmware remains disarmed and its bounded transaction timeout stops it.
            try:
                self.stop()
            except (OSError, EdgeError):
                pass
            raise

    def start(self):
        if self.accepted is None:
            raise EdgeError("A matching accepted configuration is required before start.")
        if time.monotonic() - self.accepted_at > 1.8:
            self.stop()
            raise EdgeError("Accepted configuration expired before start; configure again.")
        write_all(self.port, b"G", time.monotonic() + 1)
        self.port.started = True
        # Every G requires a new configuration, including after stop/reconnect.
        self.accepted = None


def decode_configuration(request):
    if (
        len(request) < 3 + CONFIG.size + 4
        or request[:1] != b"C"
        or struct.unpack_from("<H", request, 1)[0] != len(request) - 3
        or len(request) > 3 + MAX_CONFIG_BYTES
    ):
        raise EdgeError("Invalid configuration envelope.")
    payload = request[3:]
    (
        magic,
        version,
        opcode,
        flags,
        request_id,
        rate,
        block,
        queue,
        taps,
        decimation,
        mode,
        digest,
        scale,
        offset,
        reserved,
    ) = CONFIG.unpack_from(payload)
    coefficients = (
        np.frombuffer(payload[CONFIG.size : -4], dtype="<f4")
        if (len(payload) - CONFIG.size - 4) % 4 == 0
        else np.array([])
    )
    if (
        magic != b"IZC1"
        or version != 1
        or opcode != 1
        or flags > 1
        or reserved
        or rate not in (100, 200, 400)
        or not 1 <= block <= 64
        or not 1 <= queue <= 64
        or taps < 3
        or taps > 255
        or taps % 2 == 0
        or decimation not in (1, 2, 4, 8)
        or rate % decimation
        or mode > 2
        or len(coefficients) != taps
        or not np.isfinite(scale)
        or scale == 0
        or abs(scale) > 1000
        or not np.isfinite(offset)
        or abs(offset) > 1000
        or not np.all(np.isfinite(coefficients))
        or np.abs(coefficients).sum(dtype=np.float32) > 8
        or zlib.crc32(payload[:-4]) != struct.unpack_from("<I", payload, len(payload) - 4)[0]
    ):
        raise EdgeError("Invalid runtime configuration payload.")
    return {
        "request_id": request_id,
        "rate_hz": rate,
        "block_samples": block,
        "queue_blocks": queue,
        "taps": taps,
        "decimation": decimation,
        "placement": MODES[mode],
        "raw_validation": bool(flags),
        "spec_sha256": digest.hex(),
        "scale": scale,
        "offset": offset,
        "coefficients": coefficients.copy(),
    }


def validate_receipt(receipt, compiled, session, epoch, kinds):
    if (
        not isinstance(receipt, dict)
        or not isinstance(receipt.get("accepted"), dict)
        or not isinstance(receipt.get("configuration_hex"), str)
        or not isinstance(receipt.get("acknowledgement_hex"), str)
    ):
        raise EdgeError("Invalid retained runtime control receipt fields.")
    try:
        request = decode_configuration(bytes.fromhex(receipt["configuration_hex"]))
        accepted = decode_ack(bytes.fromhex(receipt["acknowledgement_hex"]))
    except (ValueError, KeyError, TypeError, struct.error) as exc:
        raise EdgeError("Invalid retained runtime control receipt.") from exc
    s = compiled["spec"]
    if (
        accepted["status"]
        or accepted != receipt["accepted"]
        or accepted["request_id"] != request["request_id"]
        or accepted["spec_sha256"] != compiled["spec_sha256"]
        or request["spec_sha256"] != compiled["spec_sha256"]
        or accepted["session"] != session
        or accepted["epoch"] != epoch
        or accepted["placement"] != request["placement"]
        or accepted["raw_validation"] != request["raw_validation"]
        or request["rate_hz"] != s["source"]["rate_hz"]
        or request["block_samples"] != s["resources"]["block_samples"]
        or request["queue_blocks"] != s["resources"]["queue_blocks"]
        or request["taps"] != s["dsp"]["taps"]
        or request["decimation"] != s["dsp"]["decimation"]
        or request["raw_validation"] != s["resources"]["raw_validation"]
        or request["scale"] != np.float32(s["calibration"]["scale"][0])
        or request["offset"] != np.float32(s["calibration"]["offset"][0])
        or not np.array_equal(request["coefficients"], np.asarray(compiled["coefficients"], np.float32))
    ):
        raise EdgeError("Control receipt does not match the samples, epoch or compiled specification.")
    expected = {1} if accepted["placement"] == "raw_host" else {1, MODES.index(accepted["placement"]) + 1}
    if set(kinds) != expected:
        raise EdgeError("Recording is missing the acknowledged stream kind or includes an unexpected stream.")
    return receipt
