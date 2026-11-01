"""Conservative single-mode ringdown fit; reject unsuitable/ambiguous records."""
from __future__ import annotations

import numpy as np
from scipy import optimize, signal

from .spec import EdgeError


def ringdown(samples, rate, settings, clock_ppm=0):
    y = np.asarray(samples, dtype=np.float64)
    if y.ndim != 1 or len(y) < 32 or not np.all(np.isfinite(y)):
        raise EdgeError("Ringdown needs at least 32 finite mono samples.")
    t = np.arange(len(y)) / rate
    duration = len(y)/rate
    y = y - np.mean(y)
    energy = float(np.dot(y, y))
    if energy < len(y) * 1e-12:
        return {"status": "rejected", "reasons": ["No usable signal above absolute floor."], "frequency_hz": None, "damping_ratio": None}
    f, power = signal.periodogram(y, rate, window="hann", nfft=max(4096, 2**int(np.ceil(np.log2(len(y))))))
    valid = (f >= settings["min_hz"]) & (f <= settings["max_hz"])
    if not np.any(valid) or np.max(power[valid]) < .1*np.max(power):
        return {"status": "rejected", "reasons": ["Dominant energy lies outside the declared band."], "frequency_hz": None, "damping_ratio": None}
    initial = float(f[np.flatnonzero(valid)[np.argmax(power[valid])]])

    def design(freq, decay):
        envelope = np.exp(-decay*t)
        return np.column_stack((envelope*np.sin(2*np.pi*freq*t), envelope*np.cos(2*np.pi*freq*t), np.ones(len(t))))

    # Variable projection: nonlinear frequency/decay, independent linear amplitudes.
    def residual(p):
        matrix = design(*p)
        beta = np.linalg.lstsq(matrix, y, rcond=None)[0]
        return matrix@beta-y

    fit = optimize.least_squares(residual, [initial, .2], bounds=([settings["min_hz"], 0], [settings["max_hz"], 20]),
                                  max_nfev=120, ftol=1e-10, xtol=1e-10, gtol=1e-10)
    frequency, decay = map(float, fit.x)
    explained = float(1 - np.dot(fit.fun, fit.fun)/energy)
    reasons = []
    if not fit.success or explained < .95:
        reasons.append("Single-mode decay fit explains less than 95% of signal energy or did not converge.")
    if frequency * duration < 15:
        reasons.append("Fewer than 15 cycles in the available record.")
    peaks, _ = signal.find_peaks(power)
    rivals = [float(f[i]) for i in peaks if settings["min_hz"] <= f[i] <= settings["max_hz"] and
              abs(f[i]-frequency) > max(2/duration, decay/np.pi) and power[i] > .15*np.max(power[valid])]
    if rivals:
        reasons.append("Competing modes make the single-mode interpretation ambiguous.")
    # Optimizer covariance would ignore shared clock/model error; report an envelope instead.
    frequency_envelope = max(1/duration, frequency*clock_ppm*1e-6)
    damping_reasons = list(reasons)
    if decay * duration < .7:
        damping_reasons.append("Less than 0.7 e-fold decay; damping is not identifiable.")
    if decay * duration > 8:
        damping_reasons.append("Decay reaches the floor too early for this record; shorten capture or supply noise characterization.")
    if explained < .98:
        damping_reasons.append("Damping requires at least 98% explained energy.")
    damping = decay / np.sqrt(decay**2 + (2*np.pi*frequency)**2)
    return {"status": "rejected" if reasons else "accepted_model_fit", "reasons": reasons,
            "frequency_hz": None if reasons else frequency,
            "fitted_frequency_hz": frequency, "decay_per_second": decay,
            "frequency_resolution_clock_envelope_hz": frequency_envelope,
            "envelope_label": "Resolution/declared clock envelope; not a validated coverage interval",
            "damping_ratio": None if damping_reasons else float(damping),
            "damping_rejection_reasons": damping_reasons, "explained_energy_fraction": explained,
            "competing_peaks_hz": rivals, "samples": len(y), "duration_seconds": duration,
            "model": "A exp(-alpha*t) sin(2*pi*f*t+phase) + offset; no stiffness/damage inference"}
