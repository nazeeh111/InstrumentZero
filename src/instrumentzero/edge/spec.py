"""Bounded typed graph compiler. Only reviewed linear operators are executable."""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any

import numpy as np
from scipy import signal


class EdgeError(ValueError):
    """A specification, acquisition, or measurement contract was violated."""


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def identity(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def _keys(value, required, optional=()):
    if not isinstance(value, dict) or set(value) - set(required) - set(optional) or set(required) - set(value):
        raise EdgeError(f"Expected fields {list(required)}; optional {list(optional)}.")


def number(value, low, high, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value) or not low <= value <= high:
        raise EdgeError(f"{name} must be finite within [{low}, {high}].")
    return float(value)


def integer(value, low, high, name):
    number(value, low, high, name)
    if type(value) is not int:
        raise EdgeError(f"{name} must be a JSON integer, not a floating-point value.")
    return int(value)


@dataclass(frozen=True)
class EdgeSpec:
    """Owns a canonical immutable snapshot. No mutable caller aliases."""
    encoded: bytes

    @classmethod
    def parse(cls, value: dict | EdgeSpec) -> EdgeSpec:
        if isinstance(value, cls):
            # The public frozen dataclass can also be constructed directly.
            # Always validate at the compiler boundary, even for typed inputs.
            snapshot = value.to_dict()
            _validate(snapshot)
            if canonical(snapshot) != value.encoded:
                raise EdgeError("Typed specification bytes must be canonical JSON.")
            return value
        try:
            snapshot = json.loads(canonical(value))
            _validate(snapshot)
        except (TypeError, KeyError, OverflowError) as exc:
            raise EdgeError(f"Invalid Edge specification: {exc}") from exc
        return cls(canonical(snapshot))

    def to_dict(self):
        return json.loads(self.encoded)

    @property
    def sha256(self):
        return hashlib.sha256(self.encoded).hexdigest()


def _validate(s):
    _keys(s, ("schema", "source", "calibration", "dsp", "estimator", "resources", "graph"))
    if s["schema"] != "instrumentzero.edge/1":
        raise EdgeError("Unsupported Edge specification version.")
    a = s["source"]
    _keys(a, ("adapter", "channels", "unit", "rate_hz", "representation", "full_scale", "clock_uncertainty_ppm"))
    integer(a["rate_hz"], 1, 48000, "nominal rate")
    rates = {"simulated": (100, 200, 400, 800, 1600, 8000, 16000, 48000),
             "wav": (8000, 16000, 48000), "zephyr_adxl345": (100, 200, 400)}
    if a["adapter"] not in rates or a["rate_hz"] not in rates[a["adapter"]]:
        raise EdgeError("Unsupported adapter or nominal rate.")
    if (not isinstance(a["channels"], list) or not 1 <= len(a["channels"]) <= 3 or
            any(not isinstance(c, str) or not c or len(c) > 24 for c in a["channels"]) or
            len(set(a["channels"])) != len(a["channels"])):
        raise EdgeError("Declare 1–3 distinct named channels.")
    if a["representation"] != "float32_le" or a["unit"] not in ("m/s^2", "FS"):
        raise EdgeError("Supported representation: float32_le; units: m/s^2 or FS (audio full scale).")
    if a["adapter"] == "wav" and a["unit"] != "FS":
        raise EdgeError("WAV input is full scale; Pa requires a separately calibrated adapter.")
    if a["adapter"] == "zephyr_adxl345" and a["unit"] != "m/s^2":
        raise EdgeError("The Zephyr driver returns acceleration in m/s^2.")
    if a["adapter"] == "zephyr_adxl345" and (a["channels"] != ["z"] or a["full_scale"] != 19.6133):
        raise EdgeError("The provisional ADXL345 binding exposes z only with a conservative ±2g software range (19.6133 m/s^2).")
    number(a["full_scale"], .01, 10000, "full_scale")
    if a["unit"] == "FS" and a["full_scale"] != 1:
        raise EdgeError("Normalized audio full scale must equal 1 FS.")
    number(a["clock_uncertainty_ppm"], 0, 10000, "clock uncertainty")
    c = s["calibration"]
    _keys(c, ("id", "unit_in", "unit_out", "scale", "offset", "relative_standard_uncertainty", "basis"))
    if not isinstance(c["id"], str) or not 1 <= len(c["id"]) <= 128 or not isinstance(c["basis"], str):
        raise EdgeError("Calibration needs an identity and a stated basis.")
    if c["unit_in"] != a["unit"] or c["unit_out"] != a["unit"]:
        raise EdgeError("Calibration units must match source units; no implicit unit conversion.")
    for key in ("scale", "offset"):
        if not isinstance(c[key], list) or len(c[key]) != len(a["channels"]):
            raise EdgeError("Calibration vectors must match declared channel count.")
        for v in c[key]:
            number(v, -1000, 1000, key)
            if key == "scale" and v == 0:
                raise EdgeError("Calibration gains must be nonzero; sign declares orientation.")
    number(c["relative_standard_uncertainty"], 0, 1, "calibration uncertainty")
    d = s["dsp"]
    _keys(d, ("operator", "decimation", "taps", "passband_hz", "stopband_hz", "max_passband_error", "min_stopband_db", "max_numeric_relative_error"))
    if d["operator"] != "fir_lowpass":
        raise EdgeError("Only the reviewed fir_lowpass operator is supported.")
    decimation = integer(d["decimation"], 1, 8, "decimation")
    if decimation not in (1, 2, 4, 8) or a["rate_hz"] % decimation:
        raise EdgeError("Supported decimation: 1, 2, 4 or 8, dividing the input rate exactly.")
    taps = integer(d["taps"], 3, 255, "taps")
    if taps % 2 == 0:
        raise EdgeError("Use odd tap counts for explicit integer group delay.")
    number(d["passband_hz"], .1, a["rate_hz"] / (2 * decimation), "passband")
    number(d["stopband_hz"], d["passband_hz"] + .01, a["rate_hz"] / (2 * decimation), "stopband")
    number(d["max_passband_error"], 1e-5, .2, "passband error budget")
    number(d["min_stopband_db"], 20, 120, "stopband attenuation")
    number(d["max_numeric_relative_error"], 1e-7, .01, "numeric waveform error budget")
    e = s["estimator"]
    _keys(e, ("operator", "channel", "min_hz", "max_hz", "max_frequency_error_hz", "max_damping_relative_error"))
    if e["operator"] != "ringdown" or e["channel"] not in a["channels"]:
        raise EdgeError("Use the ringdown estimator on a declared channel.")
    number(e["min_hz"], .1, d["passband_hz"] - .01, "minimum frequency")
    number(e["max_hz"], e["min_hz"] + .01, d["passband_hz"], "maximum frequency")
    number(e["max_frequency_error_hz"], 1e-5, 100, "frequency budget")
    number(e["max_damping_relative_error"], .001, 1, "damping budget")
    r = s["resources"]
    _keys(r, ("edge_memory_bytes", "fixed_runtime_memory_bytes", "link_bytes_per_second", "max_latency_ms", "block_samples", "queue_blocks", "raw_validation"))
    integer(r["edge_memory_bytes"], 0, 1000000, "edge memory")
    integer(r["fixed_runtime_memory_bytes"], 0, 1000000, "fixed runtime memory reserve")
    if a["adapter"] == "zephyr_adxl345" and r["fixed_runtime_memory_bytes"] < 16384:
        raise EdgeError("The provisional board binding needs a conservative 16384-byte fixed RTOS/driver/stack reserve.")
    number(r["link_bytes_per_second"], 1, 1e9, "link bandwidth")
    number(r["max_latency_ms"], .1, 10000, "latency")
    integer(r["block_samples"], 1, 256, "block size")
    integer(r["queue_blocks"], 1, 64, "queue blocks")
    minimum_ram = r["fixed_runtime_memory_bytes"] + r["queue_blocks"] * (84 + r["block_samples"] * (12+4*len(a["channels"]))) + 3072
    if r["edge_memory_bytes"] < minimum_ram:
        raise EdgeError("Impossible minimum bounded acquisition allocation for the declared block/channel/queue sizes.")
    if a["adapter"] == "zephyr_adxl345" and r["block_samples"] > 64:
        raise EdgeError("The provisional board binding supports at most 64 samples per block with its declared stack allocation.")
    if not isinstance(r["raw_validation"], bool):
        raise EdgeError("raw_validation must be boolean.")
    graph = s["graph"]
    expected = ["source", "timestamp", "calibration", "dsp", "estimator", "recorder"]
    if not isinstance(graph, list) or len(graph) != len(expected):
        raise EdgeError("The supported bounded graph has exactly six reviewed nodes.")
    for i, node in enumerate(graph):
        _keys(node, ("id", "operator", "inputs"))
        if node != {"id": expected[i], "operator": expected[i], "inputs": [] if i == 0 else [expected[i-1]]}:
            raise EdgeError("Cycle, fanout, reorder, or unsupported binding in graph; use source → timestamp → calibration → dsp → estimator → recorder.")


def default_spec(rate=400):
    names = ["source", "timestamp", "calibration", "dsp", "estimator", "recorder"]
    return {"schema": "instrumentzero.edge/1",
            "source": {"adapter": "simulated", "channels": ["z"], "unit": "m/s^2", "rate_hz": rate,
                       "representation": "float32_le", "full_scale": 19.6133, "clock_uncertainty_ppm": 50},
            "calibration": {"id": "simulation-identity-v1", "unit_in": "m/s^2", "unit_out": "m/s^2",
                            "scale": [1.0], "offset": [0.0], "relative_standard_uncertainty": .01,
                            "basis": "Synthetic identity. No physical calibration."},
            "dsp": {"operator": "fir_lowpass", "decimation": 4, "taps": 127, "passband_hz": 30.,
                    "stopband_hz": 50., "max_passband_error": .003, "min_stopband_db": 55, "max_numeric_relative_error": 1e-5},
            "estimator": {"operator": "ringdown", "channel": "z", "min_hz": 5., "max_hz": 28.,
                          "max_frequency_error_hz": .05, "max_damping_relative_error": .1},
            "resources": {"edge_memory_bytes": 32768, "fixed_runtime_memory_bytes": 16384, "link_bytes_per_second": 4000,
                          "max_latency_ms": 1200, "block_samples": 64, "queue_blocks": 4, "raw_validation": False},
            "graph": [{"id": n, "operator": n, "inputs": [] if i == 0 else [names[i-1]]} for i, n in enumerate(names)]}


def compile_graph(value: dict | EdgeSpec):
    s = EdgeSpec.parse(value)
    v = s.to_dict()
    d, a = v["dsp"], v["source"]
    coefficients = signal.firwin(d["taps"], (d["passband_hz"] + d["stopband_hz"]) / 2,
                                 fs=a["rate_hz"], window=("kaiser", 7.0)).astype(np.float32)
    f, h = signal.freqz(coefficients.astype(float), worN=65536, fs=a["rate_hz"])
    pass_error = float(np.max(np.abs(np.abs(h[f <= d["passband_hz"]]) - 1)))
    attenuation = float(-20 * np.log10(max(float(np.max(np.abs(h[f >= d["stopband_hz"]]))), 1e-15)))
    if pass_error > d["max_passband_error"] or attenuation < d["min_stopband_db"]:
        raise EdgeError(f"FIR misses declared budget: passband error {pass_error:.5g}; stopband {attenuation:.2f} dB. Increase taps or widen transition.")
    return {"schema": "instrumentzero.edge.compiled/1", "spec": v, "spec_sha256": s.sha256,
            "calibration_sha256": identity(v["calibration"]), "coefficients": coefficients.tolist(),
            "output_rate_hz": a["rate_hz"] / d["decimation"],
            "filter": {"passband_max_error": pass_error, "stopband_min_db": attenuation,
                       "group_delay_seconds": (d["taps"] - 1) / (2 * a["rate_hz"]),
                       "startup_invalid_input_samples": d["taps"] - 1,
                       "analysis": "65536-point response grid of float32 coefficients; not an analog alias bound"},
            "limits": {"max_session_samples": 200000, "max_taps": 255, "max_channels": 3},
            "hardware_verified": False}
