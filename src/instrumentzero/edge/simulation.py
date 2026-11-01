"""Seeded synthetic cantilever signals. No physical capture or independent reference."""
from __future__ import annotations

import time

import numpy as np
from scipy import signal

from .estimator import ringdown
from .planner import measure_costs, plan
from .runtime import Session, execute, packets, reference_samples
from .spec import EdgeError, compile_graph, default_spec, integer, number

SCENARIOS = ("mount_a", "mount_b", "silence", "chirp", "close_modes", "saturation", "impulse", "disconnect_recover")


def generate(spec, scenario="mount_a", seed=20261029, seconds=8.):
    compiled = compile_graph(spec)
    a = compiled["spec"]["source"]
    if a["adapter"] != "simulated":
        raise EdgeError("Synthetic generation requires the simulated adapter.")
    if scenario not in SCENARIOS:
        raise EdgeError("Unknown synthetic signal scenario.")
    integer(seed, 0, 2**32-1, "seed")
    number(seconds, 1, min(30, 200000/a["rate_hz"]), "duration")
    n = int(seconds*a["rate_hz"])
    t = np.arange(n)/a["rate_hz"]
    rng = np.random.default_rng(seed)
    frequency, decay = (17.25, .65) if scenario != "mount_b" else (22.5, .9)
    noise = rng.normal(0, .0006, n)
    y = np.exp(-decay*t)*np.sin(2*np.pi*frequency*t+.3)+noise
    if scenario == "silence":
        y = np.zeros(n)
    elif scenario == "chirp":
        y = .5*signal.chirp(t, 7, seconds, 27)+noise
    elif scenario == "close_modes":
        y = np.exp(-.3*t)*(np.sin(2*np.pi*17*t)+.85*np.sin(2*np.pi*17.65*t))+noise
    elif scenario == "saturation":
        y = np.clip(40*np.sin(2*np.pi*17*t), -a["full_scale"], a["full_scale"])
    elif scenario == "impulse":
        y = np.zeros(n)
        y[n//3] = 1
    values = np.column_stack([y*(1-.2*c) for c in range(len(a["channels"]))]).astype(np.float32)
    ticks = np.rint(t*1e6).astype(np.int64)
    return values, ticks, {"source_kind": "synthetic", "scenario": scenario, "seed": seed,
                           "model_frequency_hz": frequency if scenario in ("mount_a", "mount_b") else None,
                           "model_decay_per_second": decay if scenario in ("mount_a", "mount_b") else None,
                           "independent_physical_reference": False, "seconds": seconds}


def compare(spec=None, samples=None, timestamps_us=None, profile=None, source=None, scenario="mount_a", seed=20261029, seconds=8.):
    started = time.perf_counter()
    compiled = compile_graph(default_spec() if spec is None else spec)
    if samples is None:
        samples, timestamps_us, source = generate(compiled["spec"], scenario, seed, seconds)
    profile = measure_costs(compiled) if profile is None else profile
    placement = plan(compiled, profile)
    result = {"schema": "instrumentzero.edge.run/1", "source": source or {"source_kind": "user_supplied_recording", "independent_physical_reference": False},
              "compiled": compiled, "cost_profile": profile, "placement": placement,
              "verification": {"software": "See executed acceptance evidence; this run alone is not a release gate.",
                               "acquisition": "UNVERIFIED: no supported physical sensor operation demonstrated",
                               "measurement": "UNVERIFIED: no fresh independent physical comparisons"}, "comparisons": []}
    if result["source"].get("scenario") == "disconnect_recover":
        interrupted = Session(compiled["spec"])
        first = next(packets(samples, timestamps_us, compiled, interrupted.session_id))
        interrupted.enqueue(first)
        interrupted.consume()
        interrupted.disconnect()
        recovered = Session(compiled["spec"])
        try:
            interrupted.consume()
        except EdgeError:
            blocked_old_session = True
        else:
            blocked_old_session = False
        recovered.enqueue(next(packets(samples, timestamps_us, compiled, recovered.session_id)))
        recovered.consume()
        result["lifecycle_demo"] = {"source_kind": "simulated_transport_failure", "interrupted_session": interrupted.session_id,
                                    "recovered_session": recovered.session_id, "old_session_rejected": blocked_old_session,
                                    "recovered_sequence_starts_at_zero": True, "result_invalidated_on_disconnect": interrupted.result is None,
                                    "physical_unplug_tested": False}
        recovered.close()
    raw = np.asarray(samples, np.float32)
    ref = reference_samples(compiled, raw)
    d = compiled["spec"]["dsp"]
    ids = np.arange(d["decimation"]-1, len(raw), d["decimation"])
    reference_valid = ref[ids >= d["taps"]-1]
    a = compiled["spec"]["source"]
    ch = a["channels"].index(compiled["spec"]["estimator"]["channel"])
    observed_rate = (len(raw)-1)*1e6/(int(timestamps_us[-1])-int(timestamps_us[0]))/d["decimation"]
    reference_fit = ringdown(reference_valid[:, ch], observed_rate, compiled["spec"]["estimator"], a["clock_uncertainty_ppm"])
    result["independent_numerical_reference"] = {"implementation": "NumPy float64 affine + SciPy lfilter (same captured input; not independent physical measurement)",
                                               "result": reference_fit}
    for mode in ("raw_host", "calibrated_edge", "filtered_edge"):
        run = execute(compiled, raw, timestamps_us, mode)
        output = run.pop("samples_out")
        analyzed = run.pop("analysis_samples")
        run["waveform_max_abs_error_vs_float64"] = float(np.max(np.abs(output-ref)))
        run["waveform_relative_l2_error_vs_float64"] = float(np.linalg.norm(output-ref)/max(np.linalg.norm(ref), 1e-12))
        estimate, reference_frequency = run["result"]["frequency_hz"], reference_fit["frequency_hz"]
        disagreement = abs(estimate-reference_frequency) if estimate is not None and reference_frequency is not None else None
        damping, ref_damping = run["result"]["damping_ratio"], reference_fit["damping_ratio"]
        damping_disagreement = abs(damping-ref_damping)/max(abs(ref_damping), 1e-12) if damping is not None and ref_damping is not None else None
        run["frequency_disagreement_hz"] = disagreement
        run["damping_relative_disagreement"] = damping_disagreement
        run["measurement_error_budget_passed_for_this_input"] = (
            run["waveform_relative_l2_error_vs_float64"] <= d["max_numeric_relative_error"] and
            disagreement is not None and disagreement <= compiled["spec"]["estimator"]["max_frequency_error_hz"] and
            ((damping is None and ref_damping is None) or
             (damping_disagreement is not None and damping_disagreement <= compiled["spec"]["estimator"]["max_damping_relative_error"])))
        run["resource_model"] = next(c for c in placement["candidates"] if c["mode"] == mode)
        run["selected"] = mode == placement["selected"]
        result["comparisons"].append(run)
        if run["selected"]:
            stride = max(1, len(analyzed)//500)
            result["plot"] = {"time_seconds": (np.arange(len(analyzed))[::stride]/observed_rate).tolist(),
                              "signal": analyzed[::stride, ch].tolist(), "unit": a["unit"]}
    chosen = next(c for c in result["comparisons"] if c["selected"])
    if chosen["result"]["frequency_hz"] is not None and not chosen["measurement_error_budget_passed_for_this_input"]:
        chosen["unchecked_fit"] = dict(chosen["result"])
        chosen["result"].update(status="rejected", frequency_hz=None, damping_ratio=None,
                               reasons=["Selected placement failed the declared numerical measurement-preservation budget."])
    result["workflow_metrics"] = {"wall_seconds_including_graph_planning_reference_and_native_startup": time.perf_counter()-started,
                                   "acquisition_to_result_latency_seconds": None,
                                   "scope": "This software workflow, excluding interpreter import, prior sample generation, export and physical acquisition."}
    return result
