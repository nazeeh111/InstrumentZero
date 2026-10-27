"""Numerical certificate and held-out-reference checks on authentic observations."""
import hashlib
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("instrumentzero_real_validation", ROOT / "scripts/validate_real.py")
validation = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(validation)


def test_nickel_reproduces_published_curve_and_heldout_force():
    rows = validation.read_csv(ROOT / "data/nickel-sensor/force_displacement.csv")
    result, predictions = validation.validate_nickel(rows)
    # Paper Eq.8 rounds the slope to 19.126 N/mm; do not invent extra reference digits.
    assert result["all_15_points_numerical_reproduction"]["stiffness_n_per_m"] == pytest.approx(19126., abs=.1)
    assert result["held_out_branch_validation"]["rmse_reference_force_n"] == pytest.approx(.0453666205, rel=1e-6)
    assert sum(p["used_for_training"] for p in predictions) == 8
    assert not result["live_hardware_run"]


def test_nickel_heldout_force_values_do_not_change_trained_model():
    rows = validation.read_csv(ROOT / "data/nickel-sensor/force_displacement.csv")
    original, predictions = validation.validate_nickel(rows)
    modified = [dict(r) for r in rows]
    for row in modified:
        if row["branch"] == "unloading":
            row["force_N"] = str(float(row["force_N"]) + 1)
    changed, changed_predictions = validation.validate_nickel(modified)
    assert original["held_out_branch_validation"]["training_fit"] == changed["held_out_branch_validation"]["training_fit"]
    assert [p["loading_model_prediction_n"] for p in predictions] == [
        p["loading_model_prediction_n"] for p in changed_predictions]


def test_pontius_certified_fit_and_heldout_inverse():
    rows = validation.read_csv(ROOT / "data/pontius.csv")
    result, predictions = validation.validate_pontius(rows)
    reproduction = result["numerical_reproduction_all_40"]
    np.testing.assert_allclose(reproduction["coefficients"], reproduction["NIST_certified_coefficients"], rtol=2e-10)
    assert result["held_out_run_validation"]["rmse_reference_load_source_units"] == pytest.approx(327.899, rel=1e-5)
    assert sum(not p["used_for_training"] for p in predictions) == 20
    assert "unspecified" in result["units"]


def test_pontius_heldout_responses_do_not_change_calibration():
    rows = validation.read_csv(ROOT / "data/pontius.csv")
    original, _ = validation.validate_pontius(rows)
    modified = [dict(r) for r in rows]
    for row in modified:
        if row["run"] == "2":
            row["deflection_source_units"] = str(float(row["deflection_source_units"]) + .00001)
    changed, _ = validation.validate_pontius(modified)
    assert original["held_out_run_validation"]["training_coefficients"] == changed["held_out_run_validation"]["training_coefficients"]


def test_inverse_rejects_nonmonotone_or_out_of_range_response():
    with pytest.raises(ValueError, match="strictly increasing"):
        validation.invert_quadratic(np.array([0., 1., -1.]), .1)
    with pytest.raises(ValueError, match="outside"):
        validation.invert_quadratic(np.array([0., 1., 0.]), -1.)


def test_saved_validation_matches_current_script_and_raw_data():
    result = json.loads((ROOT / "examples/validation/results.json").read_text())
    assert result["script_sha256"] == hashlib.sha256((ROOT / "scripts/validate_real.py").read_bytes()).hexdigest()
    for relative_path in ("nickel-sensor/force_displacement.csv", "pontius.csv", "Pontius.dat"):
        assert result["source_sha256"][relative_path] == hashlib.sha256((ROOT / "data" / relative_path).read_bytes()).hexdigest()
    assert result["evidence_kind"] == "authentic_recorded_data_validation"
    assert result["live_hardware_run"] is False
