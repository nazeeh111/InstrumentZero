"""Recorded revelation has no fabricated observations, reuse or validation leakage."""
import csv
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest

from instrumentzero.replay import _apply_scale_corrections, export_replay_package, recorded_stiffness_replay
from instrumentzero.spec import MeasurementError

DATA = Path(__file__).resolve().parents[1]/"data"


def mutated_data(tmp_path: Path, transform) -> Path:
    source = DATA/"nickel-sensor/force_displacement.csv"
    rows = list(csv.DictReader(io.StringIO(source.read_text())))
    for row in rows:
        transform(row)
    target = tmp_path/"nickel-sensor"
    target.mkdir()
    with (target/"force_displacement.csv").open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return tmp_path


def selections(replay: dict) -> list[int]:
    return [stage["selection"]["point"] for stage in replay["stages"] if stage["stage"] == "next_record_selected"]


def test_replay_reveals_one_actual_record_and_checks_heldout_afterwards():
    result = recorded_stiffness_replay(DATA)
    assert result["source_kind"] == "recorded replay"
    assert result["result"]["observed_point_ids"] == [1, 2, 3, 5]
    assert selections(result) == [5]
    assert result["observed_records"][-1]["displacement_m"] == pytest.approx(.0000953)
    assert result["observed_records"][-1]["reference_force_n"] == 1.982
    assert result["reference_check"]["held_out_point_ids"] == [12, 13, 14, 15]
    assert result["stages"][-1]["stage"] == "held_out_reference_check"
    assert result["reference_check"]["rmse_reference_force_n"] == pytest.approx(.04005204266, abs=1e-9)
    assert result["reference_check"]["computed_after_all_selection"]
    assert result["result"]["physical_accuracy_verified"] is False
    assert result["live_hardware_run"] is False


def test_future_recorded_forces_do_not_affect_selection(tmp_path):
    baseline = recorded_stiffness_replay(DATA, measurement_budget=5)
    def change(row):
        if int(row["point"]) in {4, 5}:
            row["force_N"] = str(float(row["force_N"])+10)
    changed = recorded_stiffness_replay(mutated_data(tmp_path, change), measurement_budget=5)
    assert selections(baseline) == selections(changed)
    first_baseline = next(s for s in baseline["stages"] if s["stage"] == "next_record_selected")
    first_changed = next(s for s in changed["stages"] if s["stage"] == "next_record_selected")
    assert first_baseline["candidates"] == first_changed["candidates"]
    assert baseline["calibration"] == changed["calibration"]


def test_validation_references_never_affect_fits_or_decisions(tmp_path):
    baseline = recorded_stiffness_replay(DATA)
    def change(row):
        if row["branch"] == "unloading":
            row["force_N"] = str(float(row["force_N"])+1)
    changed = recorded_stiffness_replay(mutated_data(tmp_path, change))
    assert selections(baseline) == selections(changed)
    assert baseline["result"] == changed["result"]
    assert baseline["reference_check"] != changed["reference_check"]


def test_equal_budgets_and_full_pool_agreement():
    runs = [recorded_stiffness_replay(DATA, policy=p, measurement_budget=5)
            for p in ("information_gain", "fixed_uniform", "endpoint", "random")]
    for replay in runs:
        ids = replay["result"]["observed_point_ids"]
        assert len(ids) == len(set(ids)) == 5
        assert set(ids) == {1, 2, 3, 4, 5}
        assert not replay["unrevealed_available_settings"]
        assert replay["result"]["quantity"]["value"] == pytest.approx(runs[0]["result"]["quantity"]["value"])
        assert replay["reference_check"]["rmse_reference_force_n"] == pytest.approx(
            runs[0]["reference_check"]["rmse_reference_force_n"])


def test_shared_calibration_floor_survives_revelation_and_is_assumption():
    result = recorded_stiffness_replay(DATA, measurement_budget=5)
    assert result["calibration"]["residual_scale_degrees_of_freedom"] == 1
    assert "not repeated observations" in result["calibration"]["noise_basis"]
    for stage in result["stages"]:
        if "result" in stage:
            fit = stage["result"]
            assert fit["assumed_shared_scale_floor_n_per_m"] == pytest.approx(
                abs(fit["quantity"]["value"])*np.hypot(.01, .005))


def test_stiffness_calibration_correction_direction():
    # Doubling force doubles stiffness; doubling displacement halves stiffness.
    actual = _apply_scale_corrections(np.array([100., 100., 100.]),
                                      np.array([1., 2., 4.]), np.array([2., 1., 2.]))
    np.testing.assert_array_equal(actual, [200., 50., 50.])


def test_incremental_f_check_preserves_initial_noise_degrees_of_freedom():
    result = recorded_stiffness_replay(DATA, measurement_budget=5)
    initial = result["initial_result"]["model_check"]
    final = result["result"]["model_check"]
    assert initial["incremental_f_check_p"] is None
    assert initial["screen_passed"] is None
    assert final["numerator_degrees_of_freedom"] == 2
    assert final["denominator_degrees_of_freedom"] == 1
    expected = ((final["full_residual_sse_n2"]-final["initial_residual_sse_n2"])/2
                / result["calibration"]["residual_scale_sd_n"]**2)
    assert final["incremental_f_statistic"] == pytest.approx(expected)


@pytest.mark.parametrize("budget", [True, 2, 6, 4.5, "4"])
def test_invalid_budget_rejected(budget):
    with pytest.raises(MeasurementError):
        recorded_stiffness_replay(DATA, measurement_budget=budget)


def test_exported_replay_reproduces_without_checkout(tmp_path):
    package = export_replay_package(DATA)
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        archive.extractall(tmp_path)
    expected = json.loads((tmp_path/"replay.json").read_text())
    subprocess.run([sys.executable, str(tmp_path/"reproduce.py")], cwd=tmp_path,
                   check=True, capture_output=True, text=True, timeout=30)
    actual = json.loads((tmp_path/"reproduced-replay.json").read_text())
    assert actual == expected
    assert (tmp_path/"data/nickel-sensor/CC-BY-NOTICE.txt").is_file()


def test_two_random_orders_are_exhaustive_same_records_not_trials():
    choices = {tuple(selections(recorded_stiffness_replay(DATA, policy="random", random_seed=seed)))
               for seed in (0, 1)}
    assert choices == {(4,), (5,)}
