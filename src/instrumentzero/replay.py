"""Sequential revelation of authentic recorded observations, never counterfactual data.

The actuator displacement is a known setting. Reference force is the hidden
response, so selection cannot inspect future measured forces or validation data.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import platform
import zipfile
from pathlib import Path
from typing import Any

import numpy as np
import scipy
from scipy import stats

from .spec import MeasurementError

INITIAL_POINTS = (1, 2, 3)
MAX_RECORDED_DISPLACEMENT_M = .0001
POLICIES = ("information_gain", "fixed_uniform", "endpoint", "random")


def _apply_scale_corrections(stiffness: np.ndarray, length_correction: np.ndarray,
                             force_correction: np.ndarray) -> np.ndarray:
    """If F_true=F_recorded*f and d_true=d_recorded*l, k_true=k_fit*f/l."""
    return stiffness * force_correction / length_correction


def _load_records(data_dir: Path) -> tuple[list[dict], bytes]:
    path = Path(data_dir) / "nickel-sensor/force_displacement.csv"
    if not path.is_file():
        raise MeasurementError("The attributed nickel-sensor recorded CSV is absent.")
    raw = path.read_bytes()
    try:
        source = list(csv.DictReader(io.StringIO(raw.decode("utf-8-sig"))))
        records = [{"point": int(r["point"]), "branch": r["branch"],
                    "displacement_m": float(r["displacement_mm"]) / 1000,
                    "stage_position_mm": float(r["stage_position_mm"]),
                    "reference_force_n": float(r["force_N"])} for r in source]
    except (KeyError, ValueError, UnicodeDecodeError) as exc:
        raise MeasurementError("Recorded CSV fields or values are invalid.") from exc
    if (len(records) != 15 or len({r["point"] for r in records}) != 15
            or any(r["branch"] not in {"loading", "unloading"} for r in records)
            or not np.isfinite([[r["displacement_m"], r["stage_position_mm"], r["reference_force_n"]]
                                  for r in records]).all()):
        raise MeasurementError("Expected 15 unique finite source observations with loading/unloading labels.")
    return records, raw


def _infer(records: list[dict], noise_sd_n: float, noise_dof: int,
           length_relative_sd: float, force_relative_sd: float) -> dict:
    x = np.asarray([r["displacement_m"] for r in records])
    y = np.asarray([r["reference_force_n"] for r in records])
    h = np.column_stack([np.ones(len(x)), x])
    beta = np.linalg.lstsq(h, y, rcond=None)[0]
    covariance = np.linalg.inv(h.T @ h) * noise_sd_n**2
    residuals = y - h @ beta
    initial_sse = noise_sd_n**2 * noise_dof
    full_sse = float(residuals @ residuals)
    increment_dof = len(y) - 3
    # The old residual vector remains in the full design's null space. The new
    # orthogonal SSE increment and initial SSE are independent under iid Gaussian
    # linear errors. This is an F(n-3,1) check, not a known-noise chi-square test.
    f_stat = max(0., full_sse-initial_sse) / increment_dof / noise_sd_n**2 if increment_dof else None
    check_p = float(stats.f.sf(f_stat, increment_dof, noise_dof)) if increment_dof else None
    rng = np.random.default_rng(73913)
    slope_draws = beta[1] + np.sqrt(covariance[1, 1]) * rng.standard_t(noise_dof, 50000)
    corrections = []
    for relative_sd in (length_relative_sd, force_relative_sd):
        log_sd = np.sqrt(np.log1p(relative_sd**2))
        corrections.append(rng.lognormal(-.5*log_sd**2, log_sd, len(slope_draws)))
    slope_draws = _apply_scale_corrections(slope_draws, corrections[0], corrections[1])
    low, high = np.quantile(slope_draws, [.025, .975])
    adequate = bool(beta[1] > 0 and low > 0 and (check_p is None or check_p >= .01))
    return {"status": "conditional_recorded_estimate" if adequate else "unreliable",
            "physical_accuracy_verified": False,
            "quantity": {"name": "Force-on-actuator-displacement stiffness", "value": float(beta[1]),
                         "unit": "N/m", "interval_95": [float(low), float(high)],
                         "target_reached": False},
            "intercept_n": float(beta[0]), "gaussian_design_covariance_proxy": covariance.tolist(),
            "slope_t_scale_n_per_m": float(np.sqrt(covariance[1, 1])),
            "assumed_shared_scale_floor_n_per_m": float(abs(beta[1])*np.hypot(length_relative_sd, force_relative_sd)),
            "model_check": {"initial_residual_sse_n2": initial_sse, "full_residual_sse_n2": full_sse,
                            "incremental_f_statistic": f_stat, "numerator_degrees_of_freedom": increment_dof,
                            "denominator_degrees_of_freedom": noise_dof, "incremental_f_check_p": check_p,
                            "screen_passed": check_p >= .01 if check_p is not None else None,
                            "interpretation": "Orthogonal residual-increment F(n-3,1) check under iid Gaussian linear errors; unassessed for initial3, very low power with one denominator degree of freedom; no physical model validation"},
            "fit": {"x": x.tolist(), "observed": y.tolist(), "predicted": (h@beta).tolist(),
                    "residuals": residuals.tolist(), "x_label": "Actuator-derived displacement / m",
                    "y_label": "Recorded reference force / N"},
            "samples": len(records), "observed_point_ids": [r["point"] for r in records],
            "design_proxy_method": "The finite covariance/gain fields are plug-in known-noise Gaussian design proxies. "
            "They are not the variance or mutual information of the Student-t(df=1) inference distribution, whose variance is infinite.",
            "uncertainty_method": "Student-t slope draws using frozen initial noise estimate (one residual degree of freedom), plus shared declared length/force scale sensitivity; not total physical accuracy"}


def _candidate_scores(covariance: list[list[float]], settings: list[dict], floor_sd: float) -> list[dict]:
    cov = np.asarray(covariance)
    result = []
    for setting in settings:
        h = np.array([1., setting["displacement_m"]])
        predicted_var = float(h@cov@h)
        cross = float(cov[1]@h)
        # hCh and C both include the same initial residual-noise scale.
        independent_var = setting["noise_sd_n"]**2
        reduction = cross**2 / (independent_var+predicted_var)
        result.append({"point": setting["point"], "displacement_m": setting["displacement_m"],
                       "cost_observations": 1, "gaussian_stiffness_variance_reduction_proxy": reduction,
                       "gaussian_fractional_reduction_proxy_including_assumed_floor": reduction / (cov[1, 1]+floor_sd**2),
                       "gaussian_joint_information_proxy_nats": float(.5*np.log1p(predicted_var/independent_var)),
                       "gaussian_stiffness_information_proxy_nats": float(.5*np.log(cov[1, 1]/(cov[1, 1]-reduction)))})
    return result


def _reference_check(result: dict, heldout: list[dict]) -> dict:
    slope, intercept = result["quantity"]["value"], result["intercept_n"]
    predictions = [{"point": r["point"], "displacement_m": r["displacement_m"],
                    "reference_force_n": r["reference_force_n"],
                    "predicted_force_n": intercept+slope*r["displacement_m"]} for r in heldout]
    errors = np.array([p["predicted_force_n"]-p["reference_force_n"] for p in predictions])
    return {"held_out_points": len(heldout), "held_out_point_ids": [r["point"] for r in heldout],
            "rmse_reference_force_n": float(np.sqrt(np.mean(errors**2))),
            "mean_prediction_error_n": float(errors.mean()),
            "max_absolute_reference_force_error_n": float(np.max(np.abs(errors))),
            "predictions": predictions,
            "verification": "Recorded held-out unloading reference observations; independent source force transducer, same specimen/setup; no complete uncertainty certificate",
            "computed_after_all_selection": True}


def recorded_stiffness_replay(data_dir: Path, *, measurement_budget: int = 4,
                              policy: str = "information_gain", random_seed: int = 0,
                              scale_relative_sd: float = .01, force_relative_sd: float = .005) -> dict[str, Any]:
    """Replay 3 initial plus 1–2 selected actual source observations.

    The five eligible loading records are fixed by displacement <=0.1 mm; future
    measured forces are never used for eligibility or selection. Four eligible
    unloading records remain held out until selection is complete. A budget is a
    count of source observations, not invented hardware acquisition seconds.
    """
    if isinstance(measurement_budget, bool) or not isinstance(measurement_budget, int) or not 3 <= measurement_budget <= 5:
        raise MeasurementError("Recorded replay supports a total observation budget of 3, 4 or 5.")
    if policy not in POLICIES:
        raise MeasurementError(f"Replay policy must be one of {POLICIES}.")
    if (isinstance(random_seed, bool) or not isinstance(random_seed, int) or random_seed < 0
            or not np.isfinite([scale_relative_sd, force_relative_sd]).all()
            or not 0 <= scale_relative_sd <= .5 or not 0 <= force_relative_sd <= .5):
        raise MeasurementError("Provide a nonnegative integer seed and scale sensitivities between zero and .5.")
    records, source_bytes = _load_records(data_dir)
    loading = [r for r in records if r["branch"] == "loading" and 0 <= r["displacement_m"] <= MAX_RECORDED_DISPLACEMENT_M]
    heldout = [r for r in records if r["branch"] == "unloading" and 0 <= r["displacement_m"] <= MAX_RECORDED_DISPLACEMENT_M]
    lookup = {r["point"]: r for r in loading}
    if set(lookup) != {1, 2, 3, 4, 5} or len(heldout) != 4:
        raise MeasurementError("Source setting manifest differs from the predeclared five-loading/four-validation protocol.")
    observed = [dict(lookup[i]) for i in INITIAL_POINTS]
    x = np.array([r["displacement_m"] for r in observed])
    y = np.array([r["reference_force_n"] for r in observed])
    h = np.column_stack([np.ones(3), x])
    initial_residuals = y-h@np.linalg.lstsq(h, y, rcond=None)[0]
    noise_sd = float(np.sqrt(initial_residuals@initial_residuals))  # 3-2=1 df
    if noise_sd <= 1e-12:
        raise MeasurementError("Initial records do not identify a nonzero residual scale; supply independent noise calibration.")
    settings = [{"point": r["point"], "displacement_m": r["displacement_m"], "noise_sd_n": noise_sd}
                for r in loading if r["point"] not in INITIAL_POINTS]
    initial = _infer(observed, noise_sd, 1, scale_relative_sd, force_relative_sd)
    current = initial
    stages = [{"stage": "initial_inference", "source_kind": "recorded replay", "revealed_point_ids": list(INITIAL_POINTS),
               "result": initial}]
    rng = np.random.default_rng(random_seed)
    while len(observed) < measurement_budget:
        # This selector sees settings and posterior covariance, never a candidate force response.
        scores = _candidate_scores(current["gaussian_design_covariance_proxy"], settings,
                                   current["assumed_shared_scale_floor_n_per_m"])
        if policy == "information_gain":
            selected = max(scores, key=lambda r: (r["gaussian_stiffness_variance_reduction_proxy"], -r["point"]))
        elif policy == "endpoint":
            # Strong predeclared fixed design: furthest setting from initial design center.
            center = float(np.mean(x))
            selected = max(scores, key=lambda r: (abs(r["displacement_m"]-center), -r["point"]))
        elif policy == "fixed_uniform":
            selected = min(scores, key=lambda r: r["point"])
        else:
            selected = scores[int(rng.integers(len(scores)))]
        stages.append({"stage": "next_record_selected", "source_kind": "recorded replay", "status": "selected_existing_record",
                       "selection": selected, "candidates": scores,
                       "reason": "Select only an unrevealed existing source record by known actuator setting; no new force or displacement is synthesized",
                       "physical_actuation": False})
        revealed = dict(lookup[selected["point"]])  # actual response is accessed only after selection
        observed.append(revealed)
        settings = [s for s in settings if s["point"] != selected["point"]]
        current = _infer(observed, noise_sd, 1, scale_relative_sd, force_relative_sd)
        stages.append({"stage": "record_revealed_and_inference_updated", "source_kind": "recorded replay",
                       "observation": revealed, "result": current})
    # Held-out observations are exposed only after every design decision is final.
    reference_initial = _reference_check(initial, heldout)
    reference_final = _reference_check(current, heldout)
    stages.append({"stage": "held_out_reference_check", "source_kind": "recorded replay", "initial": reference_initial,
                   "final": reference_final})
    warnings = [
        "Recorded replay only: no new live experiment, sensor connection or physical action occurred.",
        "The five low-displacement loading records are one specimen's existing observations, not repeatable independent trials.",
        "Candidate actuator settings are available metadata; future measured forces and all unloading responses are excluded from selection.",
        "Initial three records supply only one residual degree of freedom. This is a residual-scale proxy, not a repeated-measurement noise calibration; noise/model diagnostics are weak.",
        "Student-t(df=1) has infinite variance. Finite design covariance and information gains are plug-in Gaussian proxies, not moments or information of that inference distribution.",
        "The 1% length and .5% force values are default sensitivity assumptions, not source calibration certificates; custom values are reported explicitly.",
        "The source reports calibrated independent force-reference hardware but does not supply a complete uncertainty certificate or independent specimen-deflection sensor.",
        "Actuator displacement can include slack/backlash. Loading/unloading reference disagreement remains real model error.",
        "The source reports instability above about3N; this replay uses only recorded actuator settings<=0.1mm and grants no permission for physical loading.",
        "Gaussian covariance-based selection depends on design history and noise, not measured response values; no outcome-adaptive physics discovery is claimed.",
        "The ordinary product inference may reject linearity under its own stated fine-noise assumptions; this replay does not override that rejection."]
    return {"domain": "stiffness", "source_kind": "recorded replay", "source_name": "Dera et al. nickel-sensor recorded loading/unloading",
            "policy": policy, "measurement_budget": measurement_budget, "live_hardware_run": False,
            "environment": {"python": platform.python_version(), "numpy": np.__version__, "scipy": scipy.__version__},
            "plan": {"title": "Estimate stiffness from recorded actuator settings and calibrated-reference forces",
                     "compiler": "Bounded recorded force-on-displacement experiment compiler",
                     "identifiable": True, "identifiability_scope": "Statistical slope at distinct calibrated actuator settings; full physical uncertainty remains unavailable",
                     "steps": ["Freeze source/settings manifest and held-out unloading split", "Check source units and estimate a residual-scale proxy from predeclared loading points1–3",
                               "Infer an initial conditional stiffness", "Select an existing unrevealed setting by covariance gain",
                               "Reveal that recorded response once and update inference", "Check held-out unloading reference forces after selection", "Export raw bytes, stages and limitations"],
                     "execution": "recorded revelation; no physical actuation"},
            "calibration": {"initial_point_ids": list(INITIAL_POINTS), "residual_scale_sd_n": noise_sd,
                            "residual_scale_degrees_of_freedom": 1, "noise_estimate_frozen_before_selection": True,
                            "noise_basis": "Initial linear-model residual scatter, not repeated observations or a source noise certificate",
                            "length_scale_relative_sd_assumption": scale_relative_sd,
                            "force_scale_relative_sd_assumption": force_relative_sd,
                            "scale_basis": "Declared shared sensitivity assumptions; not source-certified values"},
            "initial_result": initial, "result": current, "stages": stages,
            "observed_records": observed, "unrevealed_available_settings": settings,
            "reference_check": reference_final, "initial_reference_check": reference_initial,
            "provenance": {"source_doi": "10.17632/syjkdyzmxj.1", "license": "CC-BY-4.0",
                           "source_csv": "nickel-sensor/force_displacement.csv",
                           "source_sha256": hashlib.sha256(source_bytes).hexdigest(),
                           "selection_rule": "loading, actuator displacement<=0.0001m; initial sourcepoints1,2,3",
                           "validation_rule": "unloading, actuator displacement<=0.0001m; never used for design or fitting",
                           "random_seed": random_seed, "inference_draw_seed": 73913,
                           "source_creators": ["Wojciech J. Dera", "Hanna Konopacka", "Dariusz M. Jarząbek"]},
            "warnings": warnings}


def export_replay_package(data_dir: Path, **kwargs: Any) -> bytes:
    """Export a self-contained recorded replay with source bytes and executable code."""
    result = recorded_stiffness_replay(data_dir, **kwargs)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("replay.json", json.dumps(result, indent=2, allow_nan=False)+"\n")
        archive.writestr("config.json", json.dumps(kwargs, indent=2, allow_nan=False)+"\n")
        archive.write(Path(data_dir)/"nickel-sensor/force_displacement.csv", "data/nickel-sensor/force_displacement.csv")
        for name in ("CC-BY-NOTICE.txt", "README-source.txt"):
            path = Path(data_dir)/"nickel-sensor"/name
            if path.is_file():
                archive.write(path, "data/nickel-sensor/"+name)
        source = Path(__file__).parent
        archive.writestr("instrumentzero/__init__.py", "")
        for name in ("replay.py", "spec.py"):
            archive.write(source/name, "instrumentzero/"+name)
        archive.writestr("requirements.txt", f"numpy=={np.__version__}\nscipy=={scipy.__version__}\n")
        archive.writestr("reproduce.py", 'import json\nfrom pathlib import Path\nfrom instrumentzero.replay import recorded_stiffness_replay\n'
                         'root=Path(__file__).parent\nconfig=json.loads((root/"config.json").read_text())\n'
                         'result=recorded_stiffness_replay(root/"data", **config)\n'
                         '(root/"reproduced-replay.json").write_text(json.dumps(result, indent=2, allow_nan=False)+"\\n")\n'
                         'print(json.dumps(result["reference_check"], indent=2))\n')
        archive.writestr("LIMITATIONS.txt", "\n".join(result["warnings"])+"\n")
        archive.writestr("README.txt", "Recorded replay only. Install requirements, then run python reproduce.py.\n"
                         "Only existing source responses are revealed; no counterfactual or live measurement occurs.\n"
                         "Read LIMITATIONS.txt and retained CC-BY source attribution before interpreting results.\n")
        license_path = source/"LICENSE"
        if not license_path.is_file():
            license_path = source.parents[1]/"LICENSE"
        if license_path.is_file():
            archive.write(license_path, "LICENSE")
    return buffer.getvalue()
