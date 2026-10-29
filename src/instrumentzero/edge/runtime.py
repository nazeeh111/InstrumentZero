"""Bounded acquisition/consumer separation and epoch-scoped execution."""
from __future__ import annotations

import time
import uuid
from collections import deque

import numpy as np
from scipy import signal

from .estimator import ringdown
from .native import Processor, core_identity
from .protocol import CRC, HEADER, Frame, Validator, encode
from .spec import EdgeError, compile_graph


class Session:
    def __init__(self, spec):
        self.session_id = str(uuid.uuid4())
        self.epoch = -1
        self.closed = False
        self.reconfigure(spec)

    def reconfigure(self, spec):
        if self.closed:
            raise EdgeError("Disconnected session cannot be reused; reconnect creates a new session.")
        compiled = compile_graph(spec)  # Validate before replacing a valid configuration.
        self.epoch += 1
        self.compiled = compiled
        self.queue = deque()
        self.result = None
        self.failure = None
        self.validator = Validator(compiled, self.session_id, self.epoch)

    def enqueue(self, packet):
        if self.closed or self.failure:
            raise EdgeError("Session is closed or invalid. Start a fresh epoch/session.")
        if len(self.queue) >= self.compiled["spec"]["resources"]["queue_blocks"]:
            self.failure = "Bounded acquisition queue overflow. Capture stopped; no silent drop."
            self.result = None
            self.queue.clear()
            raise EdgeError(self.failure)
        # No decoding/processing on producer path. Copy only bounded bytes.
        r = self.compiled["spec"]
        maximum = HEADER.size + CRC.size + r["resources"]["block_samples"] * (4+4*len(r["source"]["channels"]))
        if not isinstance(packet, bytes) or len(packet) > maximum:
            raise EdgeError("Producer packet exceeds bounded storage.")
        self.queue.append(packet)

    def consume(self):
        if self.closed or self.failure:
            raise EdgeError("Session is closed or invalid.")
        if not self.queue:
            return None
        try:
            return self.validator.accept(self.queue.popleft())
        except EdgeError as exc:
            self.failure = str(exc)
            self.result = None
            self.queue.clear()
            raise

    def disconnect(self):
        self.closed = True
        self.result = None
        self.queue.clear()

    close = disconnect

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()


def packets(samples, timestamps_us, compiled, session_id, epoch=0, chunks=None):
    n = len(samples)
    block = compiled["spec"]["resources"]["block_samples"]
    chunks = chunks or [block]
    pos = 0
    index = 0
    while pos < n:
        count = min(chunks[index % len(chunks)], n-pos)
        if not 1 <= count <= block:
            raise EdgeError("Transport chunks must fit the declared block_samples allocation.")
        yield encode(Frame(session_id, epoch, pos, compiled["spec"]["source"]["rate_hz"],
                           compiled["spec_sha256"], timestamps_us[pos:pos+count], samples[pos:pos+count]))
        pos += count
        index += 1


def execute(compiled, samples, timestamps_us, mode="raw_host", chunks=None, session_id=None):
    started = time.perf_counter()
    if mode not in ("raw_host", "calibrated_edge", "filtered_edge"):
        raise EdgeError("Unknown placement.")
    s = compiled["spec"]
    a, c, d = s["source"], s["calibration"], s["dsp"]
    y = np.asarray(samples, np.float32)
    if y.ndim == 1:
        y = y[:, None]
    if not 32 <= len(y) <= 200000 or y.shape[1:] != (len(a["channels"]),):
        raise EdgeError("Capture must contain 32–200000 frames with declared channel count.")
    t = np.asarray(timestamps_us, dtype=np.int64)
    if t.shape != (len(y),):
        raise EdgeError("Each input sample needs its own timestamp.")
    session = Session(s)
    if session_id:
        session.session_id = session_id
        session.validator = Validator(compiled, session_id)
    outputs = []
    native_ns = []
    wire_bytes = 0
    calibration = Processor(c["scale"], c["offset"], [1.0], 1) if mode == "calibrated_edge" else None
    processor = Processor([1.0]*len(c["scale"]) if calibration else c["scale"],
                          [0.0]*len(c["scale"]) if calibration else c["offset"],
                          compiled["coefficients"], d["decimation"])
    init_seconds = time.perf_counter()-started
    frame_count = 0
    transferred_count = 0
    kind = {"raw_host": 1, "calibrated_edge": 2, "filtered_edge": 3}[mode]
    transport = Validator(compiled, session.session_id, kind=kind)
    try:
        for packet in packets(y, t, compiled, session.session_id, chunks=chunks):
            session.enqueue(packet)
            frame = session.consume()
            frame_count += 1
            start = time.perf_counter_ns()
            raw = frame.samples
            values = calibration.process(raw) if calibration else raw
            # The chosen cut passes actual encoded/decoded packets, not just a byte model.
            processed = processor.process(values) if mode == "filtered_edge" else None
            edge_values = processed if mode == "filtered_edge" else values
            before_count = session.validator.count-len(raw)
            if mode == "filtered_edge":
                local_ids = np.arange(len(raw)) + before_count
                wire_ticks = frame.timestamps_us[(local_ids + 1) % d["decimation"] == 0]
            else:
                wire_ticks = frame.timestamps_us
            if len(edge_values):
                wire_packet = encode(Frame(session.session_id, 0, transferred_count, int(compiled["output_rate_hz"] if kind == 3 else a["rate_hz"]),
                                           compiled["spec_sha256"], wire_ticks, edge_values, kind=kind))
                received = transport.accept(wire_packet).samples
                transferred_count += len(edge_values)
                if mode != "filtered_edge":
                    processed = processor.process(received)
                else:
                    processed = received
                wire_bytes += 4 + len(wire_packet)
            elif processed is None:
                processed = np.empty((0, len(c["scale"])), np.float32)
            native_ns.append(time.perf_counter_ns()-start)
            outputs.append(processed)
            # Account for actual framed float32 values + timestamp offsets, even when
            # the virtual cut is inside this process. Frames preserve raw provenance separately.
            if s["resources"]["raw_validation"] and mode != "raw_host":
                wire_bytes += 4 + len(packet)
        timing = session.validator.timing()
        if abs(timing["mean_clock_disagreement_ppm"]) > max(250, 5*a["clock_uncertainty_ppm"]):
            raise EdgeError("Measured sample rate disagrees with nominal/declared clock budget.")
        if timing["max_period_error_us"] > max(2., 1e4/a["rate_hz"]):
            raise EdgeError("Timestamp jitter exceeds the uniform-sample estimator's 1% period tolerance.")
        result_y = np.concatenate(outputs)
        input_indices = np.arange(d["decimation"]-1, len(y), d["decimation"])
        valid = input_indices >= d["taps"]-1
        valid_y = result_y[valid]
        measured_rate = timing["measured_rate_hz"] / d["decimation"]
        channel = a["channels"].index(s["estimator"]["channel"])
        result = ringdown(valid_y[:, channel], measured_rate, s["estimator"], a["clock_uncertainty_ppm"])
        elapsed = time.perf_counter()-started
        return {"session": session.session_id, "epoch": 0, "mode": mode, "spec_sha256": compiled["spec_sha256"],
                "core_sha256": core_identity(), "result": result, "timing": timing,
                "samples_out": result_y, "analysis_samples": valid_y,
                "metrics": {"processing_wall_seconds": elapsed, "initialization_seconds": init_seconds,
                            "processor_chunk_max_observed_ms": max(native_ns)*1e-6,
                            "processor_chunk_mean_ms": float(np.mean(native_ns))*1e-6,
                            "wire_bytes_including_headers": wire_bytes, "transport_frames": frame_count,
                            "native_state_bytes": processor.state_bytes + (calibration.state_bytes if calibration else 0),
                            "input_samples": len(y), "valid_output_samples": len(valid_y),
                            "declared_capture_seconds": (t[-1]-t[0])*1e-6,
                            "drops": 0, "acquisition_to_result_latency_seconds": None,
                            "latency_scope": "Software replay processing measured. No physical acquisition/transport latency or MCU utilization measured.",
                            "power_watts": None}, "acquisition_verified": False}
    finally:
        session.close()


def reference_samples(compiled, samples):
    s = compiled["spec"]
    calibrated = (np.asarray(samples, dtype=np.float64)-s["calibration"]["offset"])*s["calibration"]["scale"]
    return signal.lfilter(np.asarray(compiled["coefficients"], float), [1.], calibrated, axis=0)[s["dsp"]["decimation"]-1::s["dsp"]["decimation"]]
