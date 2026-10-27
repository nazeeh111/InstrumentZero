#!/usr/bin/env python3
"""Reproduce a synthetic, paired, finite-budget adaptive-design experiment.

No benchmark values are physical measurements. See docs/RESEARCH.md for scope.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
from collections import defaultdict
from pathlib import Path
from time import perf_counter

import numpy as np
import scipy

from instrumentzero.design import (
    AcquisitionSurrogate,
    Action,
    acquisition,
    gaussian_update,
    surrogate_features,
)

REGIMES = ("nominal", "heteroscedastic", "calibration_drift", "nonlinear")
POLICIES = ("fixed_uniform", "random", "endpoint_video", "endpoint_gauge", "exact_target_per_cost",
            "exact_eig_per_cost", "learned_surrogate", "ablate_no_cost", "ablate_no_calibration")
PRIOR_MEAN = np.array([0., 0.001, 0., 0.])
CALIBRATION_SD = np.array([30e-6, 8e-6])  # shared additive compliance-scale uncertainty, m/N
PRIOR_COV = np.diag([0.001**2, 0.0007**2, *CALIBRATION_SD**2])


def action_set(regime: str) -> list[Action]:
    result = []
    for modality, base_noise, cost, index in (("video", 80e-6, 1., 2), ("gauge", 20e-6, 4., 3)):
        for f in np.linspace(0, 5, 6):
            noise = base_noise * (1 + (f / 3)**2 if regime == "heteroscedastic" and modality == "video" else 1)
            h = [1., float(f), 0., 0.]
            h[index] = float(f)
            result.append(Action(float(f), modality, float(noise), cost, tuple(h)))
    return result


def train_surrogate(states: int) -> tuple[AcquisitionSurrogate, dict]:
    started = perf_counter()
    rng = np.random.default_rng(7123)
    all_features, all_targets = [], []
    for _ in range(states):
        actions = action_set("heteroscedastic" if rng.random() < .5 else "nominal")
        # Observable instrument contexts and independent simulated histories.
        cov = PRIOR_COV * rng.uniform(.5, 2.)
        mean = PRIOR_MEAN.copy()
        for _ in range(int(rng.integers(0, 22))):
            action = actions[int(rng.integers(len(actions)))]
            mean, cov = gaussian_update(mean, cov, action, float(np.asarray(action.vector) @ mean))
        all_features.append(surrogate_features(cov, actions))
        all_targets.append(np.log(np.maximum(acquisition(cov, actions), 1e-14)))
    x, y = np.vstack(all_features), np.concatenate(all_targets)
    model = AcquisitionSurrogate.fit(x, y)
    # Independent validation states, not reused in benchmark test trials.
    errors, agreements = [], []
    val_rng = np.random.default_rng(88123)
    for _ in range(200):
        actions = action_set("heteroscedastic" if val_rng.random() < .5 else "nominal")
        cov, mean = PRIOR_COV.copy(), PRIOR_MEAN.copy()
        for _ in range(int(val_rng.integers(0, 22))):
            a = actions[int(val_rng.integers(len(actions)))]
            mean, cov = gaussian_update(mean, cov, a, float(np.asarray(a.vector) @ mean))
        target = np.log(np.maximum(acquisition(cov, actions), 1e-14))
        pred = model.predict(surrogate_features(cov, actions))
        errors.extend((pred - target).tolist())
        agreements.append(int(np.argmax(target)) == int(np.argmax(pred)))
    return model, {"states": states, "examples": len(y), "training_seed": 7123,
                   "validation_seed": 88123, "validation_states": 200,
                   "log_score_rmse": float(np.sqrt(np.mean(np.square(errors)))),
                   "validation_action_agreement": float(np.mean(agreements)),
                   "training_and_validation_seconds": perf_counter() - started,
                   "architecture": "7 observable features; 64 fixed tanh random features; ridge output",
                   "trainable_parameters": len(model.output_weights),
                   "teacher": "exact fractional compliance-variance reduction per cost"}


def select(policy: str, cov: np.ndarray, actions: list[Action], feasible: list[int], step: int,
           random_rng: np.random.Generator, model: AcquisitionSurrogate) -> int:
    if policy == "random":
        return int(random_rng.choice(feasible))
    if policy == "fixed_uniform":
        preferred = step % 6
        return preferred if preferred in feasible else feasible[0]
    if policy.startswith("endpoint_"):
        offset = 6 if policy == "endpoint_gauge" else 0
        preferred = offset + (0 if step % 2 == 0 else 5)
        # An unused tail budget remains unused for a fixed gauge-only protocol.
        return preferred if preferred in feasible else -1
    candidates = [actions[i] for i in feasible]
    if policy == "learned_surrogate":
        scores = model.predict(surrogate_features(cov, candidates))
    else:
        scores = acquisition(cov, candidates, objective="eig" if policy == "exact_eig_per_cost" else "target",
                             cost_aware=policy != "ablate_no_cost")
    return feasible[int(np.argmax(scores))]


def run_trial(regime: str, policy: str, seed: int, budget: float,
              model: AcquisitionSurrogate) -> dict:
    regime_index = REGIMES.index(regime)
    truth_rng = np.random.default_rng(np.random.SeedSequence([28011, seed, regime_index]))
    # Same truth and action/replicate observations for every policy in a paired trial.
    compliance = float(truth_rng.uniform(.0005, .002))
    true_b = float(truth_rng.normal(0, .001))
    drift_factor = 4 if regime == "calibration_drift" else 1
    offsets = truth_rng.normal(0, CALIBRATION_SD * drift_factor)
    nonlinear = float(truth_rng.choice([-1., 1.]) * 40e-6) if regime == "nonlinear" else 0.
    actions = action_set(regime)
    cov, mean = PRIOR_COV.copy(), PRIOR_MEAN.copy()
    if policy == "ablate_no_calibration":
        cov[2:, 2:] = 0.
    random_rng = np.random.default_rng(np.random.SeedSequence([35041, seed, regime_index]))
    repeats: dict[int, int] = defaultdict(int)
    spent, step, selection_seconds = 0., 0, 0.
    while True:
        feasible = [i for i, a in enumerate(actions) if spent + a.cost_seconds <= budget + 1e-10]
        if not feasible:
            break
        started = perf_counter()
        selected = select(policy, cov, actions, feasible, step, random_rng, model)
        selection_seconds += perf_counter() - started
        if selected < 0:
            break
        action = actions[selected]
        modality = 0 if action.modality == "video" else 1
        obs_rng = np.random.default_rng(np.random.SeedSequence([92417, seed, regime_index,
                                                               selected, repeats[selected]]))
        observed = (true_b + (compliance + offsets[modality]) * action.force_n
                    + nonlinear * action.force_n**2 + obs_rng.normal(0, action.noise_m))
        repeats[selected] += 1
        mean, cov = gaussian_update(mean, cov, action, float(observed))
        spent += action.cost_seconds
        step += 1
    sd = float(np.sqrt(cov[1, 1]))
    lower, upper = float(mean[1] - 1.959963984540054 * sd), float(mean[1] + 1.959963984540054 * sd)
    estimate_k = float(1 / mean[1]) if mean[1] > 0 else None
    true_k = 1 / compliance
    relative_error = (estimate_k - true_k) / true_k if estimate_k is not None else None
    width_relative = (1 / lower - 1 / upper) / true_k if lower > 0 else None
    return {"regime": regime, "policy": policy, "seed": seed, "true_stiffness_n_per_m": true_k,
            "estimated_stiffness_n_per_m": estimate_k, "relative_error": relative_error,
            "absolute_relative_error": abs(relative_error) if relative_error is not None else None,
            "covered_95": lower <= compliance <= upper, "interval_width_relative": width_relative,
            "unbounded_interval": lower <= 0, "failed_estimate": estimate_k is None,
            "cost_seconds": spent, "measurements": step,
            "gauge_measurements": sum(v for i, v in repeats.items() if actions[i].modality == "gauge"),
            "target_information_nats": float(.5 * np.log(PRIOR_COV[1, 1] / cov[1, 1])),
            "selection_seconds": selection_seconds,
            "action_counts": ";".join(f"{i}:{v}" for i, v in sorted(repeats.items()))}


def wilson(successes: int, n: int) -> list[float]:
    z, p = 1.959963984540054, successes / n
    center = (p + z*z / (2*n)) / (1 + z*z/n)
    half = z * np.sqrt(p*(1-p)/n + z*z/(4*n*n)) / (1 + z*z/n)
    return [float(center-half), float(center+half)]


def summarize(rows: list[dict]) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for row in rows:
        groups[(row["regime"], row["policy"])].append(row)
    result = []
    for (regime, policy), group in groups.items():
        errors = np.asarray([r["relative_error"] for r in group if r["relative_error"] is not None])
        widths = [r["interval_width_relative"] for r in group if r["interval_width_relative"] is not None]
        coverage = sum(r["covered_95"] for r in group)
        reference = groups[(regime, "fixed_uniform")]
        paired = np.asarray([r["absolute_relative_error"] - baseline["absolute_relative_error"]
                             for r, baseline in zip(group, reference, strict=True)
                             if r["absolute_relative_error"] is not None
                             and baseline["absolute_relative_error"] is not None])
        rng = np.random.default_rng(1653)
        bootstrap = np.mean(rng.choice(paired, size=(2000, len(paired)), replace=True), axis=1)
        comparisons = {}
        for reference_policy in ("endpoint_gauge", "exact_target_per_cost"):
            reference_rows = groups[(regime, reference_policy)]
            differences = np.asarray([r["absolute_relative_error"] - baseline["absolute_relative_error"]
                                      for r, baseline in zip(group, reference_rows, strict=True)
                                      if r["absolute_relative_error"] is not None
                                      and baseline["absolute_relative_error"] is not None])
            draws = np.mean(rng.choice(differences, size=(2000, len(differences)), replace=True), axis=1)
            comparisons[reference_policy] = {
                "paired_mae_difference": float(np.mean(differences)),
                "bootstrap_95": [float(v) for v in np.quantile(draws, [.025, .975])]}
        result.append({"regime": regime, "policy": policy, "trials": len(group),
                       "relative_rmse": float(np.sqrt(np.mean(errors**2))),
                       "mean_absolute_relative_error": float(np.mean(np.abs(errors))),
                       "coverage_95": coverage / len(group), "coverage_wilson_95": wilson(coverage, len(group)),
                       "mean_interval_width_relative": float(np.mean(widths)) if widths else None,
                       "failed_estimates": sum(r["failed_estimate"] for r in group),
                       "unbounded_intervals": sum(r["unbounded_interval"] for r in group),
                       "mean_measurements": float(np.mean([r["measurements"] for r in group])),
                       "mean_cost_seconds": float(np.mean([r["cost_seconds"] for r in group])),
                       "mean_gauge_measurements": float(np.mean([r["gauge_measurements"] for r in group])),
                       "mean_target_information_nats": float(np.mean([r["target_information_nats"] for r in group])),
                       "mean_selection_ms_per_trial": float(np.mean([r["selection_seconds"] for r in group]) * 1000),
                       "paired_mae_difference_vs_uniform": float(np.mean(paired)),
                       "paired_mae_difference_bootstrap_95": [float(v) for v in np.quantile(bootstrap, [.025, .975])],
                       "strong_baseline_comparisons": comparisons})
    return result


def plot(summary: list[dict], output: Path, budget: float) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10, "axes.spines.top": False,
                         "axes.spines.right": False, "savefig.facecolor": "#f8f7f2"})
    shown = ["fixed_uniform", "random", "endpoint_gauge", "exact_target_per_cost",
             "exact_eig_per_cost", "learned_surrogate", "ablate_no_calibration"]
    colors = ["#83908e", "#a7afad", "#b99960", "#00796b", "#387a9a", "#d25237", "#735c8b"]
    fig, axes = plt.subplots(2, 2, figsize=(13, 8), layout="constrained")
    fig.patch.set_facecolor("#f8f7f2")
    for ax, regime in zip(axes.flat, REGIMES, strict=True):
        lookup = {s["policy"]: s for s in summary if s["regime"] == regime}
        vals = [lookup[p]["relative_rmse"] * 100 for p in shown]
        ax.barh(np.arange(len(shown)), vals, color=colors)
        ax.set_yticks(np.arange(len(shown)), [p.replace("_", " ") for p in shown])
        ax.invert_yaxis()
        ax.set(title=regime.replace("_", " ").title(), xlabel="Stiffness relative RMSE (%)")
        ax.set_facecolor("#f8f7f2")
        ax.grid(axis="x", alpha=.15)
    fig.suptitle(f"Synthetic experiments • equal {budget:g}-second acquisition budgets", fontsize=16, weight="bold")
    fig.savefig(output / "error_by_regime.svg")
    fig.savefig(output / "error_by_regime.png", dpi=170)
    plt.close(fig)
    fig, axes = plt.subplots(1, 2, figsize=(13, 4.8), layout="constrained")
    fig.patch.set_facecolor("#f8f7f2")
    for ax, regime in zip(axes, ("nominal", "calibration_drift"), strict=True):
        lookup = {s["policy"]: s for s in summary if s["regime"] == regime}
        values = [lookup[p]["coverage_95"] for p in shown]
        bounds = np.asarray([lookup[p]["coverage_wilson_95"] for p in shown])
        ax.errorbar(values, np.arange(len(shown)),
                    xerr=np.stack([np.asarray(values)-bounds[:, 0], bounds[:, 1]-values]),
                    fmt="o", color="#00796b", capsize=3)
        ax.axvline(.95, color="#d25237", linestyle="--", linewidth=1)
        ax.set_yticks(np.arange(len(shown)), [p.replace("_", " ") for p in shown])
        ax.invert_yaxis()
        ax.set(xlim=(0, 1.02), title=regime.replace("_", " ").title(), xlabel="95% interval coverage")
        ax.set_facecolor("#f8f7f2")
    fig.suptitle("Calibration limits confidence • Wilson 95% intervals", fontsize=15, weight="bold")
    fig.savefig(output / "coverage.svg")
    fig.savefig(output / "coverage.png", dpi=170)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--trials", type=int, default=150)
    parser.add_argument("--training-states", type=int, default=1500)
    parser.add_argument("--budget", type=float, default=24.)
    parser.add_argument("--output", type=Path, default=Path("benchmarks/v0.1"))
    parser.add_argument("--no-plots", action="store_true")
    args = parser.parse_args()
    if args.trials < 2 or args.training_states < 10 or args.budget < 4:
        parser.error("Need at least 2 trials, 10 training states and budget >= 4")
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("Output must be a fresh directory; preserve earlier successful runs")
    args.output.mkdir(parents=True, exist_ok=True)
    started = perf_counter()
    model, training = train_surrogate(args.training_states)
    model.save(args.output / "surrogate.npz")
    rows = [run_trial(regime, policy, seed, args.budget, model)
            for regime in REGIMES for policy in POLICIES for seed in range(100000, 100000 + args.trials)]
    with (args.output / "trials.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    summary = summarize(rows)
    payload = {"evidence_kind": "controlled_synthetic_benchmark", "physical_validation": False,
               "config": {"trials_per_policy_per_regime": args.trials, "budget_seconds": args.budget,
                          "regimes": REGIMES, "policies": POLICIES, "test_seed_start": 100000,
                          "prior_mean": PRIOR_MEAN.tolist(), "prior_covariance": PRIOR_COV.tolist(),
                          "shared_calibration_compliance_sd_m_per_n": CALIBRATION_SD.tolist(),
                          "maximum_force_n": 5, "noise_video_m": 80e-6, "noise_gauge_m": 20e-6,
                          "cost_video_seconds": 1, "cost_gauge_seconds": 4,
                          "drift_sd_multiplier": 4, "nonlinear_quadratic_m_per_n2": 40e-6,
                          "setup_and_switching_cost": 0},
               "environment": {"python": platform.python_version(), "numpy": np.__version__,
                               "scipy": scipy.__version__, "platform": platform.platform()},
               "training": training, "results": summary, "total_wall_seconds": perf_counter() - started,
               "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "design_source_sha256": hashlib.sha256(
                   (Path(__file__).resolve().parents[1] / "src/instrumentzero/design.py").read_bytes()).hexdigest()}
    (args.output / "results.json").write_text(json.dumps(payload, indent=2, allow_nan=False) + "\n")
    (args.output / "config.json").write_text(json.dumps(payload["config"], indent=2, allow_nan=False) + "\n")
    if not args.no_plots:
        plot(summary, args.output, args.budget)
    print(json.dumps({"output": str(args.output), "trials": len(rows), "training": training,
                      "wall_seconds": perf_counter() - started}, indent=2))


if __name__ == "__main__":
    main()
