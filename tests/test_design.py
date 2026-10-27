"""Scientific invariants: batch equivalence, calibration floors and honest bounds."""
import numpy as np
import pytest

from instrumentzero.design import AcquisitionSurrogate, Action, acquisition, gaussian_update, recommend


def test_sequential_update_equals_batch_with_shared_nuisance():
    prior = np.diag([1e-6, 1e-6, 9e-10])
    mu = np.array([0., .001, 0.])
    actions = [Action(f, "video", 80e-6, 1., (1., f, f)) for f in [0., 5., 1., 4.]]
    data = np.array([.0001, .0052, .0012, .0041])
    actual_mu, actual_cov = mu.copy(), prior.copy()
    for a, y in zip(actions, data, strict=True):
        actual_mu, actual_cov = gaussian_update(actual_mu, actual_cov, a, y)
    h = np.asarray([a.vector for a in actions])
    precision = np.linalg.inv(prior)
    expected_cov = np.linalg.inv(precision + h.T @ h / actions[0].noise_m**2)
    expected_mu = expected_cov @ (precision @ mu + h.T @ data / actions[0].noise_m**2)
    np.testing.assert_allclose(actual_cov, expected_cov, rtol=1e-8, atol=1e-16)
    np.testing.assert_allclose(actual_mu, expected_mu, rtol=1e-8, atol=1e-12)


def test_calibration_floor_does_not_average_away():
    calibration_variance = (30e-6)**2
    mu, cov = np.array([0., .001, 0.]), np.diag([1e-6, 1e-6, calibration_variance])
    for i in range(400):
        f = 0. if i % 2 == 0 else 5.
        a = Action(f, "video", 20e-6, 1., (1., f, f))
        mu, cov = gaussian_update(mu, cov, a, .001 * f)
    # Only c+delta is observed. Its components remain confounded despite repeats.
    assert cov[1, 1] > .98 * calibration_variance
    assert cov[1, 1] < 1.02 * calibration_variance


def test_exact_gain_matches_actual_covariance_update():
    cov = np.array([[1e-6, -1e-7], [-1e-7, 5e-7]])
    a = Action(3., "video", 1e-4, 2., (1., 3.))
    _, updated = gaussian_update([0., .001], cov, a, .003)
    expected_fraction = (cov[1, 1] - updated[1, 1]) / cov[1, 1]
    assert acquisition(cov, [a])[0] == pytest.approx(expected_fraction / 2)
    assert acquisition(cov, [a], objective="eig")[0] > 0


def test_same_load_does_not_identify_intercept_and_slope():
    mean, cov = np.array([0., .001]), np.diag([1., 1.])
    for _ in range(50):
        mean, cov = gaussian_update(mean, cov, Action(1., "video", .001, 1., (1., 1.)), .001)
    assert cov[1, 1] > .49
    assert np.linalg.det(cov) < 1e-7


def test_recommendation_is_proposed_and_obeys_budget():
    result = recommend([0., 1.], [[1e-6, 0.], [0., 1e-6]], 1e-4, 5., 5.3)
    assert result["status"] == "proposed"
    assert result["cost_seconds"] <= 5.3
    assert 0 <= result["force_n"] <= 5
    assert 0 <= result["expected_fractional_variance_reduction"] <= 1
    assert not recommend([], [[1e-6, 0], [0, 1e-6]], 1e-4, 5, 4)["feasible"]


@pytest.mark.parametrize("cov", [[[1, 2], [2, 1]], [[1, 0], [0, -1]], [[1, float("nan")], [0, 1]]])
def test_invalid_covariance_rejected(cov):
    with pytest.raises(ValueError):
        recommend([], cov, .001, 5., 10.)


def test_nonfinite_or_negative_acquisition_inputs_rejected():
    with pytest.raises(ValueError):
        Action(1., "video", 0., 1., (1., 1.))
    with pytest.raises(ValueError):
        recommend([float("nan")], [[1., 0], [0, 1.]], .001, 5., 10.)
    with pytest.raises(ValueError):
        recommend([], [[1., 0], [0, 1.]], .001, -5., 10.)


def test_surrogate_serialization_preserves_predictions(tmp_path):
    rng = np.random.default_rng(4)
    x = rng.normal(size=(100, 7))
    y = x[:, 0] - .1 * x[:, 1]**2
    fitted = AcquisitionSurrogate.fit(x, y, width=12)
    dest = tmp_path / "surrogate.npz"
    fitted.save(dest)
    restored = AcquisitionSurrogate.load(dest)
    np.testing.assert_array_equal(fitted.predict(x), restored.predict(x))
