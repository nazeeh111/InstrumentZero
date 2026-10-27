"""Recorded and deliberate live-capture audio, without device access from Python."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import numpy as np
from scipy import optimize, signal
from scipy.io import wavfile

from .engine import compile_experiment, digest, reference_comparison
from .spec import MeasurementError, MeasurementSpec, finite


def load_wav(path: str | Path) -> tuple[np.ndarray, float]:
    try:
        rate, raw = wavfile.read(path)
    except (ValueError, OSError) as exc:
        raise MeasurementError("Use an uncompressed PCM or float WAV recording.") from exc
    if raw.ndim > 1:
        raw = np.mean(raw.astype(float), axis=1)
    if np.issubdtype(raw.dtype, np.integer):
        info = np.iinfo(raw.dtype)
        samples = raw.astype(float)
        if info.min == 0:
            samples -= (info.max + 1) / 2
        samples /= max(abs(info.min), (info.max + 1) / 2 if info.min == 0 else info.max)
    else:
        samples = raw.astype(float)
        # Stereo integer averaging has changed dtype; detect original scale from a reread if needed.
        _, original = wavfile.read(path)
        if np.issubdtype(original.dtype, np.integer):
            info = np.iinfo(original.dtype)
            if info.min == 0:
                samples -= (info.max + 1) / 2
            samples /= max(abs(info.min), (info.max + 1) / 2 if info.min == 0 else info.max)
    return samples, float(rate)


def _estimate(y: np.ndarray, rate: float, low: float, high: float) -> tuple[float, np.ndarray, np.ndarray]:
    frequencies, power = signal.periodogram(y, rate, window="hann", detrend="constant")
    valid = (frequencies >= low) & (frequencies <= high)
    if np.count_nonzero(valid) < 3:
        raise MeasurementError("Recording is too short to resolve the selected frequency band.")
    indices = np.where(valid)[0]
    peak = indices[np.argmax(power[valid])]
    if peak in {indices[0], indices[-1]}:
        raise MeasurementError("The strongest in-band peak is at the search boundary. Expand the frequency "
                               "band or record a source with a resolvable in-band resonance.")
    initial = frequencies[peak]
    width = rate / len(y)
    t = np.arange(len(y)) / rate
    # Variable projection: linear sine/cosine/offset coefficients at each candidate frequency.
    def loss(f: float) -> float:
        basis = np.column_stack((np.cos(2 * np.pi * f * t), np.sin(2 * np.pi * f * t), np.ones(len(t))))
        beta = np.linalg.lstsq(basis, y, rcond=None)[0]
        return float(np.sum((y - basis @ beta) ** 2))
    fit = optimize.minimize_scalar(loss, bounds=(max(low, initial - width), min(high, initial + width)),
                                   method="bounded", options={"xatol": 1e-8})
    if not fit.success:
        raise MeasurementError("Frequency refinement did not converge.")
    return float(fit.x), frequencies, power


def analyze_audio(spec: MeasurementSpec | dict, samples: list[float] | np.ndarray,
                  sample_rate_hz: float) -> dict:
    s = MeasurementSpec.parse(spec)
    if s.domain != "acoustic":
        raise MeasurementError("Audio requires an acoustic specification.")
    rate = finite(sample_rate_hz, "sample_rate_hz", 100, 384000)
    if s.max_frequency_hz >= rate / 2:
        raise MeasurementError("The frequency band must remain strictly below half the sample rate (Nyquist).")
    clock = s.calibration.sample_clock_relative_sd
    if clock is None:
        raise MeasurementError("Supply sample_clock_relative_sd; a nominal rate is not a clock calibration.")
    try:
        y = np.asarray(samples, dtype=float)
    except (ValueError, TypeError) as exc:
        raise MeasurementError("Audio samples must be a flat array of finite amplitudes.") from exc
    if y.ndim != 1 or len(y) < rate * .25 or len(y) > 2_000_000 or not np.isfinite(y).all():
        raise MeasurementError("Provide 0.25 seconds or more of finite mono audio, at most 2 million samples.")
    if np.max(np.abs(y)) > 1.0001:
        raise MeasurementError("Normalize audio amplitudes to [-1, 1] before analysis.")
    if np.std(y) < 1e-7:
        raise MeasurementError("No usable signal: the recording is silent or constant.")
    # Analyze at most ten seconds from the strongest half-second neighborhood, preserving source indices.
    duration = len(y) / rate
    window = min(len(y), int(rate * 10))
    blocks = max(1, len(y) // max(1, int(rate * .5)))
    energy = [np.mean(part ** 2) for part in np.array_split(y, blocks)]
    anchor = int((np.argmax(energy) + .5) * len(y) / blocks)
    start = min(max(0, anchor - window // 2), len(y) - window)
    segment = y[start:start + window] - np.mean(y[start:start + window])
    # Downsample with an anti-aliasing filter only if it preserves the entire requested band.
    decimation = max(1, int(rate // max(8000, s.max_frequency_hz * 3)))
    effective_rate = rate
    if decimation > 1:
        segment = signal.resample_poly(segment, 1, decimation)
        effective_rate /= decimation
    frequency, freqs, power = _estimate(segment, effective_rate, s.min_frequency_hz, s.max_frequency_hz)
    resolution = effective_rate / len(segment)
    times = np.arange(len(segment)) / effective_rate
    basis = np.column_stack((np.cos(2 * np.pi * frequency * times),
                             np.sin(2 * np.pi * frequency * times), np.ones(len(times))))
    coefficients = np.linalg.lstsq(basis, segment, rcond=None)[0]
    model_residual = segment - basis @ coefficients
    explained = float(1 - np.sum(model_residual ** 2) / np.sum(segment ** 2))
    estimates = []
    for part in np.array_split(segment, 4):
        if len(part) >= .25 * effective_rate and np.std(part) > 1e-7:
            estimates.append(_estimate(part, effective_rate, s.min_frequency_hz, s.max_frequency_hz)[0])
    spread = float(np.std(estimates, ddof=1)) if len(estimates) > 1 else resolution
    # A conservative resolution floor is not a statistically calibrated confidence claim.
    half_width = float(np.sqrt(resolution ** 2 + (1.96 * spread) ** 2 + (1.96 * frequency * clock) ** 2))
    valid = (freqs >= s.min_frequency_hz) & (freqs <= s.max_frequency_hz)
    band_power = power[valid]
    snr = float(np.max(band_power) / max(np.median(band_power), np.finfo(float).tiny))
    peaks, _ = signal.find_peaks(power)
    competing = [int(i) for i in peaks if s.min_frequency_hz <= freqs[i] <= s.max_frequency_hz
                 and abs(freqs[i] - frequency) > 1.5 * resolution
                 and power[i] > np.max(band_power) * .25]
    warnings = list(s.source_limitations)
    reliable = True
    clipped = float(np.mean(np.abs(y) >= .999))
    if clipped > .001:
        warnings.append("Audio clipping is present; lower input gain and repeat the recording.")
        reliable = False
    if snr < 25:
        warnings.append("The spectral peak is weak relative to the noise floor.")
        reliable = False
    if explained < .7:
        warnings.append("A stationary sinusoid explains less than 70% of the analyzed signal energy. "
                        "Inspect multiple tones, transients or background noise before using this estimate.")
        reliable = False
    if competing:
        warnings.append("Other strong peaks are present. The reported component may be a harmonic or another source.")
        reliable = False
    if spread > max(2 * resolution, frequency * .001):
        warnings.append("Frequency changes across windows; the stationary sinusoid model is unreliable.")
        reliable = False
    if clock == 0:
        warnings.append("Sample-clock uncertainty is zero; frequency scaling assumes an exact clock.")
    warnings.append("The displayed interval is a conservative resolution/repeatability envelope, not a "
                    "validated 95% confidence interval for arbitrary audio.")
    relative = half_width / frequency
    if relative > s.target_relative_uncertainty:
        warnings.append("The requested relative uncertainty has not been reached.")
    # Retain the strongest samples per spectrum bucket, not an aliasing-prone stride.
    ids = np.where(valid)[0]
    if len(ids) > 1600:
        ids = np.array([chunk[np.argmax(power[chunk])] for chunk in np.array_split(ids, 1600)])
    wave_ids = np.linspace(0, len(y) - 1, min(1600, len(y)), dtype=int)
    return {"domain": "acoustic", "status": "reliable" if reliable else "unreliable",
            "reference": reference_comparison(s, frequency),
            "source_kind": s.source_kind, "source_name": s.source_name,
            "quantity": {"name": "Dominant resonance", "value": frequency, "unit": "Hz",
                         "interval_95": [frequency - half_width, frequency + half_width],
                         "interval_label": "Resolution + repeatability + clock envelope (not validated 95% coverage)",
                         "relative_uncertainty": relative,
                         "target_reached": reliable and relative <= s.target_relative_uncertainty},
            "fit": {"x": list(range(len(estimates))), "observed": estimates,
                    "predicted": [frequency] * len(estimates), "residuals": [v - frequency for v in estimates],
                    "x_label": "Non-overlapping window", "y_label": "Frequency / Hz"},
            "spectrum": {"frequency_hz": freqs[ids].tolist(), "power": power[ids].tolist()},
            "waveform": {"time_s": (wave_ids / rate).tolist(), "amplitude": y[wave_ids].tolist()},
            "calibration": asdict(s.calibration), "warnings": warnings,
            "assumptions": compile_experiment(s)["assumptions"],
            "next_experiment": {"title": "Record an independent sample", "reason":
                "A separate recording tests repeatability. Longer duration reduces frequency resolution "
                "error; it does not remove shared clock error or identify a fundamental automatically.",
                "feasible": True, "status": "proposed",
                "settings": {"duration_seconds": min(s.budget_seconds, 20, max(2, duration * 2)),
                             "sample_rate_hz": rate, "mode": "proposed; not recorded"}, "candidates": []},
            "model_comparison": [{"model": "dominant stationary component", "window_estimates_hz": estimates,
                                  "sinusoid_explained_energy_fraction": explained,
                                  "window_sd_hz": spread, "competing_peaks_hz": freqs[competing].tolist(),
                                  "peak_to_median_power": snr}],
            "provenance": {"observation_sha256": digest(y.tolist()), "specification_sha256": digest(s.to_dict()),
                           "calibration_basis": s.calibration_basis,
                           "source_attribution": s.source_attribution,
                           "samples": len(y), "sample_rate_hz": rate, "duration_seconds": duration,
                           "analysis_sample_range": [start, start + window], "fft_resolution_hz": resolution,
                           "validation": "No independently calibrated physical reference supplied"},
            "uncertainty_method": "Conservative quadrature of full FFT-bin width, window scatter and "
            "1.96 × shared sample-clock standard uncertainty; coverage not validated on arbitrary audio."}
