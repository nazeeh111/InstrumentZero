"""Offline source integrity and cross-instrument SPL comparison, standard library only."""
from __future__ import annotations

import csv
import hashlib
import json
import statistics
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def matrix(path: Path) -> list[list[float]]:
    with path.open(newline="") as stream:
        rows = [[float(value) for value in row] for row in csv.reader(stream)]
    if len(rows) != 33 or any(len(row) != 33 for row in rows):
        raise ValueError(f"Unexpected source-map dimensions: {path}")
    return rows


def wav_info(path: Path) -> dict:
    data = path.read_bytes()
    if data[:4] != b"RIFF" or data[8:12] != b"WAVE":
        raise ValueError("Expected RIFF WAVE")
    pos, info = 12, {}
    while pos + 8 <= len(data):
        name, size = struct.unpack_from("<4sI", data, pos)
        start = pos + 8
        if name == b"fmt ":
            code, channels, rate, _, align, bits = struct.unpack_from("<HHIIHH", data, start)
            info.update(format_code=code, channels=channels, sample_rate_hz=rate, bits=bits, block_alignment=align)
        elif name == b"data":
            info["data_bytes"] = size
        pos = start + size + size % 2
    info["sample_count"] = info["data_bytes"] // info["block_alignment"]
    info["duration_s"] = info["sample_count"] / info["sample_rate_hz"]
    return info


def main() -> None:
    provenance = json.loads((ROOT / "hifuspex" / "provenance.json").read_text())
    for item in provenance["retained_source_files"]:
        path = ROOT / item["local_path"]
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != item["sha256"] or path.stat().st_size != item["bytes"]:
            raise ValueError(f"Source integrity failure: {path}")
    paths = provenance["comparison"]["matrix_paths"]
    hi = matrix(ROOT / paths["hifuspex"])
    ref = matrix(ROOT / paths["uspm"])
    differences = [a-b for ra, rb in zip(hi, ref) for a, b in zip(ra, rb)]
    mean = statistics.mean(differences)
    twice_sd = 2 * statistics.stdev(differences)
    if abs(mean - 0.71) >= 0.005 or abs(twice_sd - 5.95) >= 0.005:
        raise ValueError("Recorded comparison does not reproduce rounded publication values")
    output = {"source_files_verified": len(provenance["retained_source_files"]),
              "matched_positions": len(differences), "mean_difference_db": mean,
              "twice_spatial_sample_sd_db": twice_sd,
              "published_rounded_mean_db": 0.71, "published_rounded_twice_sd_db": 5.95,
              "reference_kind": "separate instrument on sequential same-day registered scans",
              "raw_to_pa_verified": False, "sample_clock_calibration_verified": False}
    for item in provenance["recordings"]:
        actual = wav_info(ROOT / item["path"])
        if actual != item["wave_format"]:
            raise ValueError(f"WAV header mismatch: {item['path']}")
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
