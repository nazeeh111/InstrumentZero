"""Offline adapters consume exported sensor responses. They never discover devices."""
from __future__ import annotations

from typing import Any

import numpy as np

from .spec import MeasurementError


def phyphox_buffers(response: dict[str, Any], time_buffer: str, value_buffer: str) -> dict:
    """Validate an explicitly obtained Phyphox /get JSON response.

    Buffer names come from the configured phone experiment, not universal guesses.
    This function neither connects to a phone nor calls control/set endpoints.
    """
    try:
        buffers = response["buffer"]
        times = np.asarray(buffers[time_buffer]["buffer"], dtype=float)
        values = np.asarray(buffers[value_buffer]["buffer"], dtype=float)
        session = response["status"]["session"]
    except (KeyError, TypeError, ValueError) as exc:
        raise MeasurementError("Phyphox response is missing a requested buffer or session identity.") from exc
    if times.ndim != 1 or values.shape != times.shape or len(times) < 3:
        raise MeasurementError("Phyphox buffers must be aligned one-dimensional arrays with at least 3 samples.")
    if not np.isfinite(times).all() or not np.isfinite(values).all() or np.any(np.diff(times) <= 0):
        raise MeasurementError("Reject missing/nonfinite Phyphox values and non-increasing timestamps.")
    spacing = np.diff(times)
    uniform = bool(np.max(np.abs(spacing / np.median(spacing) - 1)) <= .01)
    return {"time_s": times.tolist(), "values": values.tolist(), "session": str(session),
            "uniform_sampling_within_one_percent": uniform,
            "sample_rate_hz": float(1 / np.median(spacing)) if uniform else None,
            "value_unit": "Must be supplied from the actual Phyphox experiment configuration",
            "source_kind": "imported", "adapter": "offline Phyphox remote-response validator"}
