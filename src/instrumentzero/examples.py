"""Reproducible examples. Synthetic and recorded evidence never share a label."""
import csv
from pathlib import Path

import numpy as np

from .acoustic import analyze_audio, load_wav
from .engine import analyze_stiffness, compile_experiment
from .spec import MeasurementError


def stiffness_example() -> dict:
    spec = {"domain": "stiffness", "question": "How stiff is this spring?",
            "equipment": ["calibrated webcam", "known loads", "CSV"],
            "target_relative_uncertainty": .05, "budget_seconds": 120, "max_force_n": 2,
            "calibration": {"meters_per_pixel": .0001, "pixel_noise_sd": .7,
                            "scale_relative_sd": .01, "force_relative_sd": .005},
            "source_kind": "synthetic", "source_name": "Seeded synthetic linear spring, k = 80 N/m",
            "reference": {"value": 80, "unit": "N/m", "kind": "synthetic ground truth"}}
    rng = np.random.default_rng(42)
    forces = np.array([0, .2, .4, .6, .8, 1])
    rows = [{"force_n": float(f), "position_px": float(20 + f / 80 / .0001 + rng.normal(0, .7))}
            for f in forces]
    result = analyze_stiffness(spec, rows)
    return {"spec": spec, "rows": rows, "plan": compile_experiment(spec), "result": result}


def acoustic_example(data_dir: Path) -> dict:
    wavs = list(data_dir.glob("*440*.wav"))
    if not wavs:
        raise MeasurementError("Recorded acoustic fixture is absent. Import your own WAV recording.")
    spec = {"domain": "acoustic", "question": "What is the tuning fork's dominant resonance?",
            "equipment": ["recorded measurement-microphone WAV"], "budget_seconds": 30,
            "target_relative_uncertainty": .001, "min_frequency_hz": 200, "max_frequency_hz": 1500,
            "calibration": {"sample_clock_relative_sd": .0001}, "source_kind": "recorded",
            "source_name": "jmuehlhans: Tuning Fork 440 Hz, Resonance Box (CC0)",
            "reference": {"value": 440, "unit": "Hz", "kind": "creator-stated nominal frequency; not traceably calibrated"},
            "calibration_basis": "The 100 ppm sample-clock uncertainty is a declared example assumption, "
                "not a calibration certificate from the recording creator.",
            "source_limitations": ["The 100 ppm clock uncertainty is an example assumption, not a "
                "calibration certificate. The nominal 440 Hz label does not establish physical truth."],
            "source_attribution": [{"title": "Tuning Fork 440 Hz, Resonance Box", "creators": ["jmuehlhans"],
                "source_url": "https://commons.wikimedia.org/wiki/File:Tuning-fork-440Hz.ogg",
                "license": "CC0-1.0", "license_url": "https://creativecommons.org/publicdomain/zero/1.0/",
                "modifications": "Commons OGG derivative decoded to mono PCM WAV; no resampling, "
                "normalization or frequency correction. Original Freesound recording ID220747."}]}
    samples, rate = load_wav(wavs[0])
    result = analyze_audio(spec, samples, rate)
    return {"spec": spec, "plan": compile_experiment(spec), "result": result}


def recorded_stiffness_example(data_dir: Path) -> dict:
    path = data_dir / "nickel-sensor/force_displacement.csv"
    if not path.exists():
        raise MeasurementError("The recorded force-sensor fixture is absent.")
    with path.open(newline="") as stream:
        source_rows = list(csv.DictReader(stream))
    # Predeclared low-load subset, below the paper's reported >3 N buckling region.
    # The noise and scale values are sensitivity assumptions, not invented certificates.
    rows = [{"force_n": float(r["force_N"]), "displacement_m": float(r["displacement_mm"]) / 1000,
             "sigma_m": 1e-6} for r in source_rows if float(r["force_N"]) <= 2.5]
    spec = {"domain": "stiffness", "question": "What is the low-load stiffness of this nickel force sensor?",
            "equipment": ["recorded calibrated reference transducer", "actuator displacement", "SI CSV"],
            "source_kind": "recorded", "source_name": "Dera et al. nickel force sensor, CC BY 4.0; low-load subset",
            "max_force_n": 2.5, "target_relative_uncertainty": .05, "budget_seconds": 60,
            "calibration": {"scale_relative_sd": .01, "force_relative_sd": .005},
            "calibration_basis": "Source reports a calibrated KM1403 force transducer and Z825B actuator. "
                "No total uncertainty certificate is supplied. 1 µm position SD, 1% length scale and 0.5% "
                "force scale are declared sensitivity assumptions, not measured calibration uncertainties.",
            "source_limitations": ["Only recorded observations at ≤2.5 N are analyzed; the paper reports "
                "rib buckling above about 3 N. Do not transfer this specimen's load limit to another device.",
                "Declared uncertainty values are sensitivity assumptions. This interval does not certify "
                "physical stiffness accuracy. Inspect the loading/unloading branches for hysteresis."],
            "source_attribution": [{"title": "Development of a novel nickel-based metal force microsensor using bottom-up approach",
                "creators": ["Wojciech J. Dera", "Hanna Konopacka", "Dariusz M. Jarząbek"],
                "source_url": "https://doi.org/10.17632/syjkdyzmxj.1", "license": "CC-BY-4.0",
                "license_url": "https://creativecommons.org/licenses/by/4.0/",
                "modifications": "Subset force_N <= 2.5 from both branches of the source15point CSV. "
                "Displacement converted mm to m; force unchanged. sigma_m=1e-6, length1% and force0.5% "
                "are sensitivity assumptions, not source-certified measurement uncertainties."}]}
    result = analyze_stiffness(spec, rows)
    result["provenance"].update(source_doi="10.17632/syjkdyzmxj.1", source_rows=len(source_rows),
                                 selected_rows=len(rows), selection_rule="force_N <= 2.5, both branches")
    return {"spec": spec, "rows": rows, "plan": compile_experiment(spec), "result": result}
