"""A deliberately bounded scientific compiler and calibrated inference engine."""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

import numpy as np
from scipy import stats

from .spec import MeasurementError, MeasurementSpec, finite


def digest(data: Any) -> str:
    return hashlib.sha256(json.dumps(data, sort_keys=True, allow_nan=False,
                                     separators=(",", ":")).encode()).hexdigest()


def reference_comparison(spec: MeasurementSpec, value: float | None) -> dict | None:
    if spec.reference is None:
        return None
    return {**spec.reference, "relative_error": abs(value / spec.reference["value"] - 1) if value else None,
            "verification": "Reference supplied with specification; independence and traceability not attested"}


def compile_experiment(spec: MeasurementSpec | dict) -> dict:
    """Compile supported questions into reviewable procedures; never actuate hardware."""
    s = MeasurementSpec.parse(spec)
    c = s.calibration
    if s.domain == "stiffness":
        steps = [
            ("Set up a low-force experiment", f"Secure the spring or cantilever. Use known loads "
             f"between 0 and {s.max_force_n:g} N. A human must check attachment, elastic range and clearance."),
            ("Calibrate position and force", "Measure a known length in the same image plane; record "
             "metres per pixel and its uncertainty. Use measured force in N, or mass × local gravity. "
             "Document uncertainty in the shared force scale. Do not equate pixels with metres."),
            ("Measure distinct loads", "Capture at least four settled observations at two or more "
             "distinct forces, including a low-force reference. Keep the camera fixed and track "
             "the same fiducial. Include unloading to check hysteresis."),
            ("Fit and challenge the model", "Fit position = intercept + compliance × force. Inspect "
             "residuals, test curvature and propagate shared calibration uncertainty. Invert a "
             "strictly positive compliance interval to obtain stiffness."),
            ("Choose the next observation", "Compare feasible loads by expected compliance-variance "
             "reduction per second. Recommendations are proposals, not executed measurements."),
            ("Verify and export", "Compare with a separately measured reference; export source "
             "observations, calibration, assumptions, executable analysis and limitations.")]
        identifiable = c.meters_per_pixel is not None and c.pixel_noise_sd is not None
        warnings = [] if identifiable else ["Absolute length/noise calibration is absent. SI displacement "
            "rows with explicit sigma_m are an alternative; their units and force span are checked at analysis."]
        required = ["Absolute length scale and its relative standard uncertainty",
                    "Known forces in N and shared force-scale uncertainty",
                    "Per-observation position standard uncertainty"]
        assumptions = ["Small deflections in a linear elastic regime", "Fixed camera and in-plane motion",
                       "Independent position errors conditional on shared calibration",
                       "Unknown position offset fitted jointly with compliance"]
    else:
        steps = [
            ("Choose the frequency band", f"Inspect a single dominant resonance in "
             f"{s.min_frequency_hz:g}–{s.max_frequency_hz:g} Hz; a harmonic is not automatically the fundamental."),
            ("Calibrate the sample clock", "Use the recorded sample rate and a documented relative "
             "clock uncertainty. A nominal sample rate alone is not traceable calibration."),
            ("Record or import audio", "Record a steady, unclipped signal in a quiet space for at "
             "least 0.25 seconds. Microphone access requires a deliberate user action. Imported "
             "recordings retain their source identity."),
            ("Estimate resonance", "Initialize from a Hann-window spectrum; refine a sinusoidal "
             "frequency fit. Compare independent time windows and inspect competing peaks."),
            ("Challenge and repeat", "Report resolution, window instability and clock uncertainty. "
             "A longer recording can improve resolution, but cannot remove clock error."),
            ("Verify and export", "Compare against an independently characterized source. An "
             "author's nominal tuning-fork label is a limited agreement check, not calibration.")]
        identifiable = c.sample_clock_relative_sd is not None
        warnings = [] if identifiable else ["Supply sample_clock_relative_sd; zero explicitly assumes a perfect clock."]
        required = ["Sample rate in Hz", "Sample-clock relative standard uncertainty", "Source recording provenance"]
        assumptions = ["One dominant approximately stationary sinusoidal component within the selected band",
                       "Sample times are uniformly spaced", "Frequency scale follows the sample clock",
                       "A resonance peak need not be the fundamental"]
    return {"title": s.question, "domain": s.domain, "identifiable": identifiable,
            "identifiability_scope": "Calibration readiness only. Actual observation rank, force span or "
            "sampling must still be checked before a parameter is identified.",
            "steps": [{"title": title, "detail": detail} for title, detail in steps],
            "required_calibration": required, "assumptions": assumptions, "warnings": warnings,
            "compiler": "Bounded model-based compiler; no general-language or paid model service",
            "execution": "human-supervised; no physical actuation"}


def analyze_stiffness(spec: MeasurementSpec | dict, rows: list[dict], *, _history: bool = True) -> dict:
    s = MeasurementSpec.parse(spec)
    if s.domain != "stiffness":
        raise MeasurementError("Force-deflection observations require a stiffness specification.")
    if not isinstance(rows, list) or not 4 <= len(rows) <= 10000:
        raise MeasurementError("Provide 4–10000 observations at two or more distinct forces.")
    c = s.calibration
    pixel_data = all(isinstance(r, dict) and "position_px" in r for r in rows)
    si_data = all(isinstance(r, dict) and "displacement_m" in r for r in rows)
    if pixel_data == si_data:
        raise MeasurementError("Use either position_px or displacement_m consistently, never both.")
    if pixel_data and (c.meters_per_pixel is None or c.pixel_noise_sd is None):
        raise MeasurementError("Pixel observations require meters_per_pixel and pixel_noise_sd calibration.")
    forces, positions, noise = [], [], []
    for i, row in enumerate(rows):
        forces.append(finite(row.get("force_n"), f"row {i + 1} force_n", 0, s.max_force_n))
        if pixel_data:
            positions.append(finite(row["position_px"], f"row {i + 1} position_px") * c.meters_per_pixel)
            noise.append(c.pixel_noise_sd * c.meters_per_pixel)
        else:
            positions.append(finite(row["displacement_m"], f"row {i + 1} displacement_m"))
            sd = finite(row.get("sigma_m"), f"row {i + 1} sigma_m", 0)
            if sd == 0:
                raise MeasurementError("sigma_m must be positive; exact observations are unsupported.")
            noise.append(sd)
    x, y, sd = map(np.asarray, (forces, positions, noise))
    span = float(np.ptp(x))
    if span <= max(1e-12, float(np.max(np.abs(x))) * 1e-8):
        raise MeasurementError("Compliance and offset are not identifiable from one force. Add distinct loads.")
    # Center and scale force for a well-conditioned weighted fit, then transform covariance back.
    center = float(np.mean(x))
    z = (x - center) / span
    design = np.column_stack((np.ones(len(x)), z))
    weighted = design / sd[:, None]
    beta_z, _, rank, _ = np.linalg.lstsq(weighted, y / sd, rcond=None)
    if rank != 2:
        raise MeasurementError("The measurement design is rank deficient.")
    transform = np.array([[1, -center / span], [0, 1 / span]])
    beta = transform @ beta_z
    predicted = np.column_stack((np.ones(len(x)), x)) @ beta
    residuals = y - predicted
    chi2 = float(np.sum((residuals / sd) ** 2))
    dof = len(x) - 2
    inflation = max(1, chi2 / dof)
    cov = transform @ np.linalg.inv(weighted.T @ weighted) @ transform.T * inflation
    slope = float(beta[1])
    slope_sd = float(np.sqrt(cov[1, 1]))
    # Shared multiplicative calibration is sampled once per fit, not once per row.
    rng = np.random.default_rng(1729)
    compliance_draws = rng.normal(slope, slope_sd, 50000)
    for rel, inverse in ((c.scale_relative_sd, False), (c.force_relative_sd, True)):
        log_sd = np.sqrt(np.log1p(rel * rel))
        factor = rng.lognormal(-.5 * log_sd * log_sd, log_sd, len(compliance_draws))
        compliance_draws = compliance_draws / factor if inverse else compliance_draws * factor
    lo_c, hi_c = np.quantile(compliance_draws, [.025, .975])
    warnings = list(s.source_limitations)
    valid = bool(lo_c > 0 and slope > 0)
    value, interval, relative = None, [None, None], None
    if valid:
        value = 1 / slope
        interval = [float(1 / hi_c), float(1 / lo_c)]
        relative = (interval[1] - interval[0]) / (2 * value)
    else:
        warnings.append("The compliance interval includes zero or is negative; positive stiffness is unbounded.")
    p_value = float(stats.chi2.sf(chi2, dof))
    comparison = [{"model": "linear elastic", "parameters": 2, "chi_squared": chi2,
                   "degrees_of_freedom": dof, "lack_of_fit_p": p_value}]
    if len(np.unique(x)) >= 3 and len(x) >= 6:
        quadratic = np.column_stack((np.ones(len(x)), z, z * z))
        bq = np.linalg.lstsq(quadratic / sd[:, None], y / sd, rcond=None)[0]
        qchi = float(np.sum(((y - quadratic @ bq) / sd) ** 2))
        delta = chi2 - qchi
        # Known-noise nested-model likelihood ratio, used only as a diagnostic.
        curve_p = float(stats.chi2.sf(max(0, delta), 1))
        comparison.append({"model": "quadratic diagnostic", "parameters": 3, "chi_squared": qchi,
                           "improvement_p": curve_p})
        if curve_p < .01:
            warnings.append("Curvature is detectable against the declared noise; a linear stiffness may be invalid.")
            valid = False
    if p_value < .01:
        warnings.append("Residuals exceed the declared noise. Inspect drift, hysteresis, tracking or model error.")
        valid = False
    if c.scale_relative_sd == 0:
        warnings.append("Length scale uncertainty is set to zero; intervals assume an exact length scale.")
    if c.force_relative_sd == 0:
        warnings.append("Force scale uncertainty is set to zero; intervals assume exact applied forces.")
    if relative is not None and relative > s.target_relative_uncertainty:
        warnings.append("The requested relative uncertainty has not been reached.")
    from .design import recommend
    next_action = recommend(forces, cov.tolist(), float(np.median(sd)), s.max_force_n, s.budget_seconds)
    next_action.update(title="Measure another distinct load" if next_action.get("feasible") else "Budget exhausted",
                       settings={"force_n": next_action.get("force_n"),
                                 "cost_seconds": next_action.get("cost_seconds"),
                                 "mode": "proposed; human setup required"})
    floor = np.hypot(c.scale_relative_sd, c.force_relative_sd) * 1.96
    if floor >= s.target_relative_uncertainty:
        next_action["reason"] += (" Shared calibration uncertainty already exceeds the target; "
                                   "improve calibration before expecting more rows to meet it.")
    if not valid:
        next_action = {"title": "Check the model before adding load", "feasible": False,
                       "status": "diagnostic required", "reason": "The current observations do not support "
                       "a reliable positive linear stiffness. Inspect calibration, repeat low-load "
                       "loading/unloading controls, and test drift or curvature before using a linear "
                       "variance-reduction recommendation. No additional physical load is selected.",
                       "settings": {"mode": "diagnostic review; no physical action selected"}, "candidates": []}
    order = np.argsort(x)
    history = []
    if _history:
        checkpoints = np.unique(np.linspace(4, len(rows), min(10, len(rows) - 3), dtype=int))
        for count in checkpoints:
            try:
                earlier = analyze_stiffness(s, rows[:int(count)], _history=False)
                q = earlier["quantity"]
                history.append({"samples": int(count), "value": q["value"], "lower": q["interval_95"][0],
                                "upper": q["interval_95"][1], "relative_uncertainty": q["relative_uncertainty"],
                                "status": earlier["status"]})
            except MeasurementError:
                continue
    return {"domain": "stiffness", "status": "reliable" if valid else "unreliable",
            "reference": reference_comparison(s, value),
            "uncertainty_history": history,
            "source_kind": s.source_kind, "source_name": s.source_name,
            "quantity": {"name": "Stiffness", "value": value, "unit": "N/m", "interval_95": interval,
                         "relative_uncertainty": relative, "target_reached": valid and relative is not None
                         and relative <= s.target_relative_uncertainty},
            "compliance": {"value": slope, "unit": "m/N", "interval_95": [float(lo_c), float(hi_c)]},
            "fit": {"x": x[order].tolist(), "observed": y[order].tolist(),
                    "predicted": predicted[order].tolist(), "residuals": residuals[order].tolist(),
                    "x_label": "Applied force / N", "y_label": "Position / m",
                    "offset_m": float(beta[0]), "conditional_covariance": cov.tolist(),
                    "reduced_chi_squared": chi2 / dof},
            "calibration": asdict(c), "warnings": warnings,
            "assumptions": compile_experiment(s)["assumptions"], "next_experiment": next_action,
            "model_comparison": comparison,
            "provenance": {"observation_sha256": digest(rows), "specification_sha256": digest(s.to_dict()),
                           "calibration_basis": s.calibration_basis,
                           "source_attribution": s.source_attribution,
                           "samples": len(rows), "calibration_draw_seed": 1729,
                           "calibration_draws": 50000, "validation": "No independent physical reference supplied"},
            "uncertainty_method": "Weighted Gaussian linear fit; residual variance never deflates declared "
            "noise; Monte Carlo propagates shared length and force scales; reciprocal compliance quantiles."}
