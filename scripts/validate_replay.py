#!/usr/bin/env python3
"""Export a finite recorded adaptive replay and honest same-record comparisons."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path

from instrumentzero.replay import export_replay_package, recorded_stiffness_replay


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--output", type=Path, default=Path("examples/replay-validation"))
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error("Use a fresh output directory; preserve existing valid replay artifacts")
    configs = [(policy, seed, budget) for budget in (4, 5)
               for policy, seeds in (("information_gain", (0,)), ("fixed_uniform", (0,)),
                                     ("endpoint", (0,)), ("random", (0, 1))) for seed in seeds]
    runs = [recorded_stiffness_replay(args.data, policy=policy, random_seed=seed, measurement_budget=budget)
            for policy, seed, budget in configs]
    summaries = [{"policy": r["policy"], "random_seed": r["provenance"]["random_seed"],
                  "measurement_budget": r["measurement_budget"],
                  "observed_point_ids": r["result"]["observed_point_ids"],
                  "initial_rmse_reference_force_n": r["initial_reference_check"]["rmse_reference_force_n"],
                  "final_rmse_reference_force_n": r["reference_check"]["rmse_reference_force_n"],
                  "stiffness_n_per_m": r["result"]["quantity"]["value"],
                  "status": r["result"]["status"],
                  "interval_95_n_per_m": r["result"]["quantity"]["interval_95"],
                  "incremental_model_f_check_p": r["result"]["model_check"]["incremental_f_check_p"]}
                 for r in runs]
    random_first = {r["observed_point_ids"][-1] for r in summaries
                    if r["policy"] == "random" and r["measurement_budget"] == 4}
    if random_first != {4, 5}:
        raise RuntimeError("Random seeds no longer enumerate the two available first choices; update before reporting")
    args.output.mkdir(parents=True, exist_ok=True)
    authoritative = runs[0]
    (args.output/"replay.json").write_text(json.dumps(authoritative, indent=2, allow_nan=False)+"\n")
    summary = {"evidence_kind": "recorded replay; no new physical acquisition", "source_doi": "10.17632/syjkdyzmxj.1",
               "source_experiments": 1, "new_physical_experiments": 0, "reused_source_loading_records": 5,
               "held_out_source_unloading_records": 4, "independent_trials": False,
               "random_ordering_denominator": 2,
               "random_ordering_interpretation": "Both possible next recorded settings, each weight one half; reused same data, not independent physical trials",
               "source_sha256": authoritative["provenance"]["source_sha256"],
               "replay_source_sha256": hashlib.sha256(
                   (Path(__file__).resolve().parents[1]/"src/instrumentzero/replay.py").read_bytes()).hexdigest(),
               "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
               "results": summaries}
    (args.output/"comparison.json").write_text(json.dumps(summary, indent=2, allow_nan=False)+"\n")
    with (args.output/"comparison.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)
    (args.output/"recorded-replay.zip").write_bytes(export_replay_package(args.data))
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, 2, figsize=(12, 4.8), layout="constrained")
    fig.patch.set_facecolor("#f8f7f2")
    initial = authoritative["initial_result"]
    final = authoritative["result"]
    initial_n = initial["samples"]
    observed = authoritative["observed_records"]
    axes[0].scatter([r["displacement_m"]*1000 for r in observed[:initial_n]],
                    [r["reference_force_n"] for r in observed[:initial_n]], color="#00796b", label="Initial points 1–3")
    selected = observed[initial_n:]
    axes[0].scatter([r["displacement_m"]*1000 for r in selected], [r["reference_force_n"] for r in selected],
                    color="#d25237", marker="s", s=70, label="Selected actual source point 5")
    for label, result, color in (("Initial fit", initial, "#83908e"), ("Updated fit", final, "#00796b")):
        import numpy as np
        x = np.linspace(0, .1, 50)
        axes[0].plot(x, result["intercept_n"]+result["quantity"]["value"]*x/1000, color=color, label=label)
    axes[0].set(xlabel="Recorded actuator setting (mm)", ylabel="Revealed reference force (N)",
                title="Select setting → reveal existing measurement")
    axes[0].legend(fontsize=8)
    four = [r for r in summaries if r["measurement_budget"] == 4]
    labels = ["Gaussian design proxy", "Fixed uniform", "Strong endpoint", "Random: point5", "Random: point4"]
    axes[1].barh(labels, [r["final_rmse_reference_force_n"] for r in four],
                 color=["#00796b", "#83908e", "#b99960", "#a7afad", "#a7afad"])
    axes[1].axvline(authoritative["initial_reference_check"]["rmse_reference_force_n"], color="#d25237",
                    linestyle="--", label="Initial 3-point model")
    axes[1].set(xlabel="RMSE vs four held-out reference forces (N)", title="Equal budget: four source observations")
    axes[1].invert_yaxis()
    axes[1].legend(fontsize=8)
    for ax in axes:
        ax.set_facecolor("#f8f7f2")
        ax.grid(alpha=.12)
    fig.suptitle("Authentic recorded replay • one specimen • no new or counterfactual measurements", fontsize=12)
    fig.savefig(args.output/"recorded_replay.png", dpi=170)
    fig.savefig(args.output/"recorded_replay.svg")
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
