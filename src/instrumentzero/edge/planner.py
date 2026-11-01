"""Deterministic legal prefix placement. Host costs are never relabeled MCU costs."""
from __future__ import annotations

import platform
import time

import numpy as np

from .native import Processor, core_identity, library
from .protocol import CRC, HEADER
from .spec import EdgeError, _keys, identity, number


def measure_costs(compiled):
    s = compiled["spec"]
    ch = len(s["source"]["channels"])
    n = s["resources"]["block_samples"]
    data = np.ones((n, ch), dtype=np.float32) * .01
    measurements = {}
    for name, coefficients, d in [("calibration", [1.0], 1),
                                  ("calibration_fir", compiled["coefficients"], s["dsp"]["decimation"])]:
        p = Processor(s["calibration"]["scale"], s["calibration"]["offset"], coefficients, d)
        costs = []
        for _ in range(7):
            start = time.perf_counter_ns()
            for _ in range(20):
                p.process(data)
            costs.append((time.perf_counter_ns() - start) / (20 * n))
        measurements[name] = {"ns_per_input_frame": float(np.median(costs)),
                              "observed_max_ns_per_input_frame": max(costs)}
    profile = {"schema": "instrumentzero.edge.costs/1", "basis": "measured_host_proxy",
               "platform": platform.platform(), "machine": platform.machine(),
               "core_sha256": core_identity(), "spec_sha256": compiled["spec_sha256"],
               "primitive_costs": measurements, "state_bytes": library().iz_state_bytes(),
               "limits": "Includes ctypes call/allocation overhead. No MCU timing, power or hard real-time guarantee."}
    return profile


def plan(compiled, profile):
    _keys(profile, ("schema", "basis", "platform", "machine", "core_sha256", "spec_sha256", "primitive_costs", "state_bytes", "limits"))
    if profile["schema"] != "instrumentzero.edge.costs/1" or profile["state_bytes"] != library().iz_state_bytes():
        raise EdgeError("Cost profile schema or native memory size does not match this executable core.")
    _keys(profile["primitive_costs"], ("calibration", "calibration_fir"))
    for cost in profile["primitive_costs"].values():
        _keys(cost, ("ns_per_input_frame", "observed_max_ns_per_input_frame"))
        average = number(cost["ns_per_input_frame"], .001, 1e12, "primitive cost")
        number(cost["observed_max_ns_per_input_frame"], average, 1e12, "observed maximum cost")
    if (profile.get("core_sha256") != core_identity() or
            profile.get("spec_sha256") != compiled["spec_sha256"] or profile.get("basis") != "measured_host_proxy"):
        raise EdgeError("Cost profile is stale, unbound, or unsupported; measure this specification again.")
    s = compiled["spec"]
    r, a = s["resources"], s["source"]
    ch, rate, block = len(a["channels"]), a["rate_hz"], r["block_samples"]
    # Explicit reserve is a planning bound, not linker-measured full firmware RAM.
    queue_bytes = r["queue_blocks"] * (HEADER.size + CRC.size + block * (12 + 4*ch))
    base_ram = queue_bytes + 3072 + r["fixed_runtime_memory_bytes"]
    candidates = []
    for mode in ("raw_host", "calibrated_edge", "filtered_edge"):
        edge_d = s["dsp"]["decimation"] if mode == "filtered_edge" else 1
        bps = rate / edge_d * (4 + 4*ch) + rate / block * (4 + HEADER.size + CRC.size)
        if r["raw_validation"] and mode != "raw_host":
            bps += rate * (4 + 4*ch) + rate / block * (4 + HEADER.size + CRC.size)
        ram = base_ram + (profile["state_bytes"] if mode != "raw_host" else 0)
        cost_key = "calibration_fir" if mode == "filtered_edge" else "calibration"
        cost = 0 if mode == "raw_host" else profile["primitive_costs"][cost_key]["observed_max_ns_per_input_frame"]
        utilization = cost * rate * 1e-9
        packet_bytes = 4 + HEADER.size + CRC.size + (block // edge_d + (block % edge_d != 0)) * (4 + 4*ch)
        if r["raw_validation"] and mode != "raw_host":
            packet_bytes += 4 + HEADER.size + CRC.size + block * (4+4*ch)
        latency_ms = 1000 * (block/rate + compiled["filter"]["group_delay_seconds"] +
                            packet_bytes / r["link_bytes_per_second"] + cost*block*1e-9)
        reasons = []
        if ram > r["edge_memory_bytes"]:
            reasons.append("declared edge RAM bound exceeded")
        if bps > r["link_bytes_per_second"]:
            reasons.append("declared link throughput exceeded")
        if latency_ms > r["max_latency_ms"]:
            reasons.append("modeled latency budget exceeded")
        if utilization >= .7:
            reasons.append("host-proxy processing utilization exceeds conservative 70% ceiling")
        candidates.append({"mode": mode, "legal_under_declared_model": not reasons, "reasons": reasons,
                           "estimated_transfer_bytes_per_second": bps, "reserved_edge_memory_bytes": ram,
                           "modeled_latency_ms": latency_ms, "host_proxy_processing_fraction": utilization,
                           "score": bps/r["link_bytes_per_second"] + utilization})
    legal = [c for c in candidates if c["legal_under_declared_model"]]
    if not legal:
        raise EdgeError("No placement meets declared resource bounds: " + str({c["mode"]: c["reasons"] for c in candidates}))
    winner = min(legal, key=lambda c: (c["score"], c["mode"]))
    return {"selected": winner["mode"], "candidates": candidates, "cost_profile_sha256": identity(profile),
            "rules_version": "prefix-v1", "raw_validation": r["raw_validation"],
            "edge_estimator": "Unavailable: ringdown optimization stays on host.",
            "status": "provisional placement using measured host costs; MCU costs unavailable",
            "error_contract": "FIR response checked at compilation; per-input frequency/damping disagreement checked at execution. No universal error guarantee.",
            "power": None}
