#!/usr/bin/env python3
"""Controlled acoustic acceptance: empirical envelopes and explicit negative cases.

All signals here are generated. This validates software under declared models,
not a microphone, recording clock, pressure calibration, or new physical experiment.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
from pathlib import Path
from time import perf_counter

import numpy as np
import scipy
from scipy.stats import norm

from instrumentzero.acoustic import analyze_audio
from instrumentzero.spec import MeasurementError

REGIMES = ("nominal_clock", "unmodeled_clock_drift", "nearby_tones", "chirp", "clipped", "noise_only")


def wilson(successes: int, count: int) -> list[float] | None:
    if not count:
        return None
    z = norm.ppf(.975)
    p = successes / count
    center = (p + z*z / (2*count)) / (1 + z*z/count)
    half = z * np.sqrt(p*(1-p)/count + z*z/(4*count*count)) / (1 + z*z/count)
    return [float(max(0, center-half)), float(min(1, center+half))]


def signal_case(regime: str, trial: int, seed: int = 20261026) -> tuple[dict, np.ndarray, float | None]:
    """Sample one ADC clock error per recording; never per independent audio sample."""
    if regime not in REGIMES:
        raise ValueError("Unknown acoustic validation regime")
    rng = np.random.default_rng(np.random.SeedSequence([seed, trial, REGIMES.index(regime)]))
    rate, duration, declared_clock_sd = 8000, 2, .001
    physical_frequency = float(rng.uniform(250, 1400))
    clock_error = float(rng.normal(0, declared_clock_sd * (4 if regime == "unmodeled_clock_drift" else 1)))
    physical_times = np.arange(rate*duration) / (rate * (1 + clock_error))
    phase = float(rng.uniform(-np.pi, np.pi))
    signal = .4 * np.sin(2*np.pi*physical_frequency*physical_times + phase)
    reference = physical_frequency
    if regime == "nearby_tones":
        signal = .27 * np.sin(2*np.pi*physical_frequency*physical_times + phase)
        signal += .27 * np.sin(2*np.pi*(physical_frequency+1)*physical_times + phase)
        reference = None
    elif regime == "chirp":
        signal = .4 * np.sin(2*np.pi*(physical_frequency*physical_times + 2*physical_times**2) + phase)
        reference = None
    elif regime == "clipped":
        signal = np.clip(2*signal/.4, -1, 1)
        reference = None
    elif regime == "noise_only":
        signal = rng.normal(0, .15, len(physical_times))
        reference = None
    if regime not in {"clipped", "noise_only"}:
        signal += rng.normal(0, .005, len(signal))
    spec = {"domain": "acoustic", "question": "What is the dominant resonance frequency?",
            "equipment": ["generated acceptance signal"], "source_kind": "synthetic",
            "source_name": f"Controlled acoustic acceptance / {regime} / seed {seed} / trial {trial}",
            "min_frequency_hz": 100, "max_frequency_hz": 1800,
            "calibration": {"sample_clock_relative_sd": declared_clock_sd},
            "calibration_basis": "Simulation assumption: one Gaussian relative clock error per recording; "
            "the drift regime deliberately violates its stated standard deviation by fourfold.",
            "target_relative_uncertainty": .01}
    return spec, signal, reference


def evaluate_case(regime: str, trial: int, seed: int) -> dict:
    spec, samples, reference = signal_case(regime, trial, seed)
    start = perf_counter()
    try:
        result = analyze_audio(spec, samples, 8000)
    except MeasurementError as exc:
        return {"regime": regime, "trial": trial, "reported": False, "reliable": False,
                "reference_frequency_hz": reference, "estimated_frequency_hz": None, "error_hz": None,
                "envelope_covers_reference": None, "half_width_hz": None,
                "seconds": perf_counter()-start, "reason": str(exc)}
    q = result["quantity"]
    low, high = q["interval_95"]
    return {"regime": regime, "trial": trial, "reported": True,
            "reliable": result["status"] == "reliable", "reference_frequency_hz": reference,
            "estimated_frequency_hz": q["value"], "error_hz": q["value"]-reference if reference else None,
            "envelope_covers_reference": low <= reference <= high if reference else None,
            "half_width_hz": (high-low)/2, "seconds": perf_counter()-start,
            "reason": "; ".join(result["warnings"])}


def summarize(rows: list[dict]) -> list[dict]:
    summaries = []
    for regime in REGIMES:
        selected = [r for r in rows if r["regime"] == regime]
        count = len(selected)
        evaluated = [r for r in selected if r["envelope_covers_reference"] is not None]
        covers = sum(r["envelope_covers_reference"] for r in evaluated)
        accepted = sum(r["reliable"] for r in selected)
        expected_reject = regime not in {"nominal_clock", "unmodeled_clock_drift"}
        errors = [r["error_hz"] for r in evaluated]
        summaries.append({"regime": regime, "trials": count, "accepted_as_reliable": accepted,
                          "reliable_fraction": accepted/count, "expected_reject": expected_reject,
                          "model_rejection_fraction": (count-accepted)/count,
                          "rejection_wilson_95": wilson(count-accepted, count),
                          "scalar_reference_trials": len(evaluated),
                          "envelope_coverage": covers/len(evaluated) if evaluated else None,
                          "coverage_wilson_95": wilson(covers, len(evaluated)),
                          "frequency_rmse_hz": float(np.sqrt(np.mean(np.square(errors)))) if errors else None,
                          "mean_half_width_hz": float(np.mean([r["half_width_hz"] for r in evaluated])) if evaluated else None,
                          "mean_analysis_seconds": float(np.mean([r["seconds"] for r in selected]))})
    return summaries


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=100)
    parser.add_argument("--seed", type=int, default=20261026)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 1 <= args.trials <= 10000:
        parser.error("Use 1–10000 trials per regime")
    if args.output.exists():
        parser.error("Use a new output directory; previous valid results are preserved")
    rows = [evaluate_case(regime, trial, args.seed) for regime in REGIMES for trial in range(args.trials)]
    source = Path(__file__).resolve().parents[1]
    paths = [Path(__file__).resolve(), source/'src/instrumentzero/acoustic.py', source/'src/instrumentzero/spec.py']
    result = {"evidence_kind": "controlled_synthetic_acoustic_software_acceptance", "live_hardware_run": False,
              "config": {"trials_per_regime": args.trials, "seed": args.seed, "sample_rate_hz": 8000,
                         "duration_seconds": 2, "declared_clock_relative_sd": .001,
                         "drift_clock_sd_multiplier": 4},
              "source_sha256": {str(p.relative_to(source)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
              "environment": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
              "summaries": summarize(rows), "limitations": [
                  "Every signal is numerically generated, not a physical microphone recording.",
                  "Wilson intervals describe repeated-trial proportions, not measurement-parameter confidence intervals.",
                  "Empirical coverage applies only to the declared distributions and finite trials.",
                  "A wrong sample clock is not identifiable from a stationary tone alone; the drift negative result is expected.",
                  "A chirp or two-tone signal has no single scalar resonance truth in this test; only model rejection is evaluated.",
                  "These tests do not establish actual permissions, operating-system/device behavior or total physical accuracy."]}
    args.output.mkdir(parents=True)
    (args.output/'results.json').write_text(json.dumps(result, indent=2, allow_nan=False)+'\n')
    with (args.output/'trials.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(json.dumps(result['summaries'], indent=2))


if __name__ == '__main__':
    main()
