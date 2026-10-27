#!/usr/bin/env python3
"""Reproduce explicitly limited checks against authentic recorded reference data.

This runs no hardware. Regression reproduction, held-out recorded observations,
and independent physical reference instrumentation are separate evidence claims.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
from pathlib import Path

import numpy as np
import scipy
from scipy.optimize import brentq
from scipy.stats import t


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8-sig") as stream:
        return list(csv.DictReader(stream))


def linear_fit(displacement_m: np.ndarray, force_n: np.ndarray) -> dict:
    """OLS F-on-displacement; conditional uncertainty treats displacement as exact."""
    x, y = np.asarray(displacement_m, dtype=float), np.asarray(force_n, dtype=float)
    if x.ndim != 1 or x.shape != y.shape or len(x) < 3 or not np.isfinite([x, y]).all():
        raise ValueError("Need at least three finite aligned force/displacement observations")
    centered = x - x.mean()
    sxx = float(centered @ centered)
    if sxx <= 0:
        raise ValueError("At least two distinct displacement settings are required")
    slope = float(centered @ (y - y.mean()) / sxx)
    intercept = float(y.mean() - slope * x.mean())
    residuals = y - (intercept + slope * x)
    variance = float(residuals @ residuals / (len(x) - 2))
    slope_se = float(np.sqrt(variance / sxx))
    half_width = float(t.ppf(.975, len(x) - 2) * slope_se)
    return {"stiffness_n_per_m": slope, "intercept_n": intercept,
            "conditional_slope_standard_error_n_per_m": slope_se,
            "conditional_slope_interval_95_n_per_m": [slope - half_width, slope + half_width],
            "residual_standard_deviation_n": float(np.sqrt(variance)),
            "r_squared": float(1 - residuals @ residuals / ((y - y.mean()) @ (y - y.mean()))),
            "points": len(x), "regression_direction": "force_N = intercept_N + stiffness_N_per_m * displacement_m",
            "uncertainty_kind": "conditional OLS regression; displacement treated as exact; not total physical uncertainty"}


def validate_nickel(rows: list[dict[str, str]]) -> tuple[dict, list[dict]]:
    if len(rows) != 15 or {r["branch"] for r in rows} != {"loading", "unloading"}:
        raise ValueError("Expected the unchanged source's 15 loading/unloading observations")
    x = np.asarray([float(r["displacement_mm"]) / 1000 for r in rows])
    y = np.asarray([float(r["force_N"]) for r in rows])
    loading = np.asarray([r["branch"] == "loading" for r in rows])
    if loading.sum() != 8:
        raise ValueError("Expected eight training loading observations and seven held-out unloading observations")
    all_fit = linear_fit(x, y)
    training_fit = linear_fit(x[loading], y[loading])
    predicted = training_fit["intercept_n"] + training_fit["stiffness_n_per_m"] * x
    errors = predicted[~loading] - y[~loading]
    published_k = 19126.
    report = {
        "evidence_kind": "authentic_recorded_force_displacement_with_source_reported_independent_force_transducer",
        "source_doi": "10.17632/syjkdyzmxj.1", "article_doi": "10.1016/j.precisioneng.2025.05.003",
        "live_hardware_run": False,
        "source_reported_reference": "Calibrated Megatron Elektronik KM1403, 100 N range; independent force transducer",
        "displacement_source": "Thorlabs Z825B actuator reading; mechanical slack/backlash not independently corrected",
        "all_15_points_numerical_reproduction": all_fit,
        "article_equation_8": {"stiffness_n_per_m": published_k, "offset_n": .0994,
                               "slope_standard_deviation_n_per_m": 200.1,
                               "source_location": "article-source.pdf, PDF page 7 / journal page 257, Eq.8",
                               "comparison_kind": "same source curve; numerical reproduction, not independent physical stiffness truth",
                               "computed_minus_published_stiffness_n_per_m": all_fit["stiffness_n_per_m"]-published_k,
                               "relative_difference": (all_fit["stiffness_n_per_m"]-published_k)/published_k},
        "held_out_branch_validation": {
            "split": "all eight loading points train; all seven unloading points held out",
            "training_fit": training_fit, "training_points": 8, "held_out_points": 7,
            "rmse_reference_force_n": float(np.sqrt(np.mean(errors**2))),
            "mean_prediction_error_n": float(np.mean(errors)),
            "max_absolute_reference_force_error_n": float(np.max(np.abs(errors))),
            "full_scale_definition_n": float(y.max()),
            "rmse_as_fraction_of_source_maximum_force": float(np.sqrt(np.mean(errors**2))/y.max()),
            "independence": "Held-out recorded observations against separate force-reference instrumentation, same specimen/setup",
            "interpretation": "Conditional predictive agreement; not traceable total force/stiffness accuracy"},
        "limits": [
            "No new physical measurements or live device connection were made.",
            "The reference transducer is independent hardware, but the same specimen, source experiment and displacement actuator are reused.",
            "No calibration certificate or complete force/displacement systematic-uncertainty budget is supplied.",
            "The published regression slope uncertainty and fitted intervals exclude missing physical systematic uncertainties.",
            "Article reports buckling/instability above about 3 N; historical points above that threshold are replay evidence, not permission for new loading.",
            "This all-point F-on-displacement reproduction differs from the product's conservative <=2.5 N displacement-on-force analysis; neither validates the other's scientific assumptions."]}
    points = [{"point": int(row["point"]), "branch": row["branch"],
               "displacement_m": float(xx), "reference_force_n": float(yy),
               "loading_model_prediction_n": float(yp), "prediction_minus_reference_n": float(yp-yy),
               "used_for_training": bool(train)}
              for row, xx, yy, yp, train in zip(rows, x, y, predicted, loading, strict=True)]
    return report, points


def quadratic_forward(load: np.ndarray, deflection: np.ndarray) -> np.ndarray:
    """Fit with scaled loads to avoid ill-conditioned powers of million-scale values."""
    load, response = np.asarray(load, float), np.asarray(deflection, float)
    if load.ndim != 1 or load.shape != response.shape or len(load) < 4 or not np.isfinite([load, response]).all():
        raise ValueError("Need four or more finite aligned calibration points")
    z = load / 1e6
    h = np.column_stack([np.ones(len(z)), z, z*z])
    beta, _, rank, _ = np.linalg.lstsq(h, response, rcond=None)
    if rank != 3:
        raise ValueError("Calibration loads do not identify a quadratic response")
    return beta / np.array([1., 1e6, 1e12])


def invert_quadratic(beta: np.ndarray, deflection: float, *, maximum_load: float = 3.2e6) -> float:
    """Invert only a monotone response over the declared source-unit interval."""
    beta = np.asarray(beta, float)
    if beta.shape != (3,) or not np.isfinite([*beta, deflection, maximum_load]).all() or maximum_load <= 0:
        raise ValueError("Finite quadratic parameters and a positive load bound are required")
    derivatives = beta[1] + 2 * beta[2] * np.array([0., maximum_load])
    if np.any(derivatives <= 0):
        raise ValueError("Response is not strictly increasing over the inversion range")
    def residual(load: float) -> float:
        return float(beta[0] + beta[1]*load + beta[2]*load*load - deflection)
    if residual(0) > 0 or residual(maximum_load) < 0:
        raise ValueError("Recorded response is outside the declared invertible calibration range")
    return float(brentq(residual, 0., maximum_load, xtol=1e-7))


def validate_pontius(rows: list[dict[str, str]]) -> tuple[dict, list[dict]]:
    if len(rows) != 40:
        raise ValueError("Expected all 40 source Pontius observations")
    loads = np.asarray([float(r["load_source_units"]) for r in rows])
    deflections = np.asarray([float(r["deflection_source_units"]) for r in rows])
    training = np.asarray([r["run"] == "1" for r in rows])
    if training.sum() != 20:
        raise ValueError("Expected 20 observations in each source run")
    all_beta = quadratic_forward(loads, deflections)
    train_beta = quadratic_forward(loads[training], deflections[training])
    predicted = np.array([invert_quadratic(train_beta, d) for d in deflections])
    errors = predicted[~training] - loads[~training]
    certified = np.array([.673565789473684e-3, .732059160401003e-6, -.316081871345029e-14])
    report = {
        "evidence_kind": "authentic_recorded_NIST_load_cell_calibration",
        "source_url": "https://www.itl.nist.gov/div898/strd/lls/data/Pontius.shtml",
        "live_hardware_run": False, "units": "original unspecified source units; no SI conversion inferred",
        "numerical_reproduction_all_40": {
            "model": "deflection = B0 + B1 * load + B2 * load^2",
            "coefficients": all_beta.tolist(), "NIST_certified_coefficients": certified.tolist(),
            "coefficient_relative_differences": ((all_beta-certified)/certified).tolist(),
            "interpretation": "Published numerical certificate checks regression implementation, not physical stiffness accuracy"},
        "held_out_run_validation": {
            "split": "run 1's 20 points calibrate forward quadratic; invert run 2's 20 deflections to predict recorded reference loads",
            "training_points": 20, "held_out_points": 20, "training_coefficients": train_beta.tolist(),
            "inverse_domain_load_source_units": [0., 3.2e6],
            "rmse_reference_load_source_units": float(np.sqrt(np.mean(errors**2))),
            "mean_prediction_error_source_units": float(np.mean(errors)),
            "max_absolute_reference_load_error_source_units": float(np.max(np.abs(errors))),
            "full_scale_reference_load_source_units": 3e6,
            "rmse_as_fraction_of_full_scale": float(np.sqrt(np.mean(errors**2)) / 3e6),
            "interpretation": "Held-out source-run agreement with recorded known loads, same source instrument and experiment"},
        "limits": ["No new measurements were acquired.", "Source physical units are unspecified; never report these errors as N or N/m.",
                   "Run 2 is held out from fitting, but shares source apparatus and may share systematic errors.",
                   "Known reference loads and the numerical regression certificate do not supply a complete physical accuracy certificate.",
                   "The two increasing-load runs confound drift with load; results are not evidence of general calibration stability."]}
    points = [{"observation": int(row["observation"]), "run": int(row["run"]),
               "deflection_source_units": float(d), "reference_load_source_units": float(load),
               "run1_inverse_prediction_source_units": float(pred), "prediction_minus_reference_source_units": float(pred-load),
               "used_for_training": bool(train)}
              for row, d, load, pred, train in zip(rows, deflections, loads, predicted, training, strict=True)]
    return report, points


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def plots(output: Path, nickel: dict, nickel_points: list[dict], pontius: dict, pontius_points: list[dict]) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
                         "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), layout="constrained")
    fig.patch.set_facecolor("#f8f7f2")
    for branch, color, marker in (("loading", "#00796b", "o"), ("unloading", "#d25237", "s")):
        points = [p for p in nickel_points if p["branch"] == branch]
        label = "Loading • training" if branch == "loading" else "Unloading • held out"
        axes[0].scatter([p["displacement_m"]*1000 for p in points], [p["reference_force_n"] for p in points],
                        color=color, marker=marker, label=label, zorder=3)
    fit = nickel["held_out_branch_validation"]["training_fit"]
    x = np.linspace(0, .18, 100)
    axes[0].plot(x, fit["intercept_n"] + fit["stiffness_n_per_m"]*x/1000,
                 color="#00796b", alpha=.65, label="Loading-only OLS model")
    axes[0].axhline(3., color="#735c8b", linestyle=":", label="Source instability ~3 N")
    axes[0].set(xlabel="Actuator-derived displacement (mm)", ylabel="Reference-transducer force (N)",
                title="Authentic recorded nickel microsensor")
    axes[0].legend(fontsize=8, loc="upper left")
    held = [p for p in nickel_points if not p["used_for_training"]]
    axes[1].axhline(0, color="#83908e", linewidth=1)
    axes[1].scatter([p["reference_force_n"] for p in held], [p["prediction_minus_reference_n"] for p in held],
                    color="#d25237", marker="s")
    axes[1].set(xlabel="Held-out reference force (N)", ylabel="Prediction minus reference (N)",
                title=f"Held-out unloading RMSE: {nickel['held_out_branch_validation']['rmse_reference_force_n']:.5f} N")
    for ax in axes:
        ax.set_facecolor("#f8f7f2")
        ax.grid(alpha=.15)
    fig.suptitle("Recorded reference agreement • same specimen/setup • incomplete systematic uncertainty", fontsize=12)
    fig.savefig(output / "nickel_validation.png", dpi=170)
    fig.savefig(output / "nickel_validation.svg")
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), layout="constrained")
    fig.patch.set_facecolor("#f8f7f2")
    for run, color in ((1, "#00796b"), (2, "#d25237")):
        points = [p for p in pontius_points if p["run"] == run]
        axes[0].scatter([p["reference_load_source_units"]/1e6 for p in points],
                        [p["deflection_source_units"] for p in points], color=color,
                        label="Run 1 • calibration" if run == 1 else "Run 2 • held out", s=22)
    axes[0].set(xlabel="Recorded reference load (million source units)", ylabel="Recorded deflection (source units)",
                title="NIST Pontius • authentic observed data")
    axes[0].legend(fontsize=9)
    held = [p for p in pontius_points if not p["used_for_training"]]
    axes[1].axhline(0, color="#83908e", linewidth=1)
    axes[1].scatter([p["reference_load_source_units"]/1e6 for p in held],
                    [p["prediction_minus_reference_source_units"] for p in held], color="#d25237")
    rmse = pontius["held_out_run_validation"]["rmse_reference_load_source_units"]
    axes[1].set(xlabel="Held-out reference load (million source units)", ylabel="Prediction minus reference (source units)",
                title=f"Run-1 calibration → run-2 prediction • RMSE {rmse:.2f}")
    for ax in axes:
        ax.set_facecolor("#f8f7f2")
        ax.grid(alpha=.15)
    fig.suptitle("Held-out recorded calibration check • no SI-unit conversion or total-accuracy claim", fontsize=12)
    fig.savefig(output / "pontius_validation.png", dpi=170)
    fig.savefig(output / "pontius_validation.svg")
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("examples/validation"))
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("Use a fresh output directory; previous results are preserved")
    nickel_path = args.data / "nickel-sensor/force_displacement.csv"
    pontius_path = args.data / "pontius.csv"
    nickel, nickel_points = validate_nickel(read_csv(nickel_path))
    pontius, pontius_points = validate_pontius(read_csv(pontius_path))
    source_paths = [nickel_path, pontius_path, args.data/"Pontius.dat", args.data/"provenance.json",
                    args.data/"nickel-sensor/README-source.txt", args.data/"nickel-sensor/article-source.pdf"]
    payload = {"evidence_kind": "authentic_recorded_data_validation", "live_hardware_run": False,
               "nickel_sensor": nickel, "pontius": pontius,
               "source_sha256": {str(p.relative_to(args.data)): hashlib.sha256(p.read_bytes()).hexdigest()
                                 for p in source_paths},
               "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "environment": {"python": platform.python_version(), "numpy": np.__version__,
                               "scipy": scipy.__version__}}
    args.output.mkdir(parents=True, exist_ok=True)
    (args.output/"results.json").write_text(json.dumps(payload, indent=2, allow_nan=False)+"\n")
    write_csv(args.output/"nickel_predictions.csv", nickel_points)
    write_csv(args.output/"pontius_predictions.csv", pontius_points)
    if not args.no_plots:
        plots(args.output, nickel, nickel_points, pontius, pontius_points)
    print(json.dumps({"output": str(args.output),
                      "nickel_stiffness_n_per_m": nickel["all_15_points_numerical_reproduction"]["stiffness_n_per_m"],
                      "nickel_heldout_rmse_n": nickel["held_out_branch_validation"]["rmse_reference_force_n"],
                      "pontius_heldout_rmse_source_units": pontius["held_out_run_validation"]["rmse_reference_load_source_units"]},
                     indent=2))


if __name__ == "__main__":
    main()
