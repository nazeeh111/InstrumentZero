"""Auditable Gaussian design and an explicitly optional learned surrogate.

The acquisition functions recommend observations; they never actuate equipment.
Covariance order is intercept, compliance, then optional nuisance parameters.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from numpy.typing import NDArray

Array = NDArray[np.float64]


@dataclass(frozen=True)
class Action:
    force_n: float
    modality: str
    noise_m: float
    cost_seconds: float
    vector: tuple[float, ...]

    def __post_init__(self) -> None:
        if not np.isfinite([self.force_n, self.noise_m, self.cost_seconds, *self.vector]).all():
            raise ValueError("Action values must be finite")
        if self.force_n < 0 or self.noise_m <= 0 or self.cost_seconds <= 0:
            raise ValueError("Force must be nonnegative; noise and acquisition cost must be positive")


def _covariance(value: Any) -> Array:
    cov = np.asarray(value, dtype=float)
    if cov.ndim != 2 or cov.shape[0] != cov.shape[1] or cov.shape[0] < 2:
        raise ValueError("Covariance must be square with at least intercept and compliance")
    if not np.isfinite(cov).all() or not np.allclose(cov, cov.T, rtol=1e-8, atol=1e-18):
        raise ValueError("Covariance must be finite and symmetric")
    tolerance = 1e-10 * max(float(np.diag(cov).max()), 1e-30)
    if np.linalg.eigvalsh(cov).min() < -tolerance or cov[1, 1] <= 0:
        raise ValueError("Covariance must be positive semidefinite with positive compliance variance")
    return cov


def acquisition(covariance: Any, actions: list[Action], *, objective: str = "target",
                cost_aware: bool = True) -> Array:
    """Exact one-observation gain, divided by acquisition seconds by default.

    target: fractional reduction in marginal compliance variance.
    eig: mutual information about all parameters, in nats.
    These are different objectives; neither guarantees physical accuracy.
    """
    cov = _covariance(covariance)
    if not actions:
        return np.empty(0)
    h = np.asarray([a.vector for a in actions])
    if h.shape[1] != len(cov):
        raise ValueError("Action vector and covariance dimensions differ")
    predictive = np.einsum("ij,jk,ik->i", h, cov, h)
    variance = np.square([a.noise_m for a in actions])
    if objective == "target":
        cross = h @ cov[:, 1]
        score = np.square(cross) / (variance + predictive) / cov[1, 1]
    elif objective == "eig":
        score = 0.5 * np.log1p(np.maximum(predictive, 0) / variance)
    else:
        raise ValueError("Objective must be 'target' or 'eig'")
    if cost_aware:
        score /= np.asarray([a.cost_seconds for a in actions])
    return score


def gaussian_update(mean: Any, covariance: Any, action: Action, observation_m: float) -> tuple[Array, Array]:
    """Kalman update for a known linear Gaussian observation, retaining nuisances."""
    cov = _covariance(covariance)
    mu = np.asarray(mean, dtype=float)
    h = np.asarray(action.vector, dtype=float)
    if mu.shape != (len(cov),) or h.shape != mu.shape or not np.isfinite(mu).all():
        raise ValueError("Mean, action and covariance dimensions must agree and be finite")
    if not np.isfinite(observation_m):
        raise ValueError("Observation must be finite")
    cross = cov @ h
    denominator = action.noise_m**2 + h @ cross
    updated_mean = mu + cross * ((observation_m - h @ mu) / denominator)
    updated_cov = cov - np.outer(cross, cross) / denominator
    return updated_mean, (updated_cov + updated_cov.T) / 2


def recommend(forces: list[float], covariance: list[list[float]], noise_m: float,
              max_force_n: float, budget_seconds: float) -> dict[str, Any]:
    """Recommend an explicitly proposed video load from a calibrated 2-D fit.

    ``forces`` records prior loads for the explanation; all supported loads remain
    eligible for independent repeats. Hardware limits must be supplied by a human.
    The simple timing model is declared, not measured: 5 + F/F_max seconds.
    """
    cov = _covariance(covariance)
    if cov.shape != (2, 2):
        raise ValueError("This convenience recommendation requires a 2 by 2 covariance")
    if not np.isfinite([noise_m, max_force_n, budget_seconds, *forces]).all():
        raise ValueError("Loads, noise, force limit and budget must be finite")
    if noise_m <= 0 or max_force_n <= 0 or budget_seconds < 0 or any(f < 0 for f in forces):
        raise ValueError("Noise and force limit must be positive; budget and prior loads nonnegative")
    actions = [Action(float(f), "video", noise_m, 5 + float(f) / max_force_n, (1., float(f)))
               for f in np.linspace(0, max_force_n, 5)]
    feasible = [a for a in actions if a.cost_seconds <= budget_seconds]
    if not feasible:
        return {"feasible": False, "reason": "Insufficient time budget for any supported load",
                "candidates": [], "status": "proposed"}
    scores = acquisition(cov, feasible)
    best = feasible[int(np.argmax(scores))]
    fractional_gain = float(acquisition(cov, [best], cost_aware=False)[0])
    return {"feasible": True, "status": "proposed", "force_n": best.force_n,
            "modality": best.modality, "cost_seconds": best.cost_seconds,
            "expected_variance_reduction": fractional_gain * float(cov[1, 1]),
            "expected_fractional_variance_reduction": fractional_gain,
            "information_gain_nats": float(acquisition(cov, [best], objective="eig", cost_aware=False)[0]),
            "reason": "Largest expected compliance-variance reduction per acquisition second; "
                      "conditional on the linear model, stated noise and timing model. "
                      f"{len(forces)} prior load observations; this is a proposed human-supervised action.",
            "candidates": [{"force_n": a.force_n, "cost_seconds": a.cost_seconds,
                            "fractional_variance_reduction_per_second": float(s)}
                           for a, s in zip(feasible, scores, strict=True)]}


def surrogate_features(covariance: Any, actions: list[Action]) -> Array:
    """Observable posterior and sensor summaries; no true parameters or future data."""
    cov = _covariance(covariance)
    h = np.asarray([a.vector for a in actions])
    predictive = np.maximum(np.einsum("ij,jk,ik->i", h, cov, h), 1e-25)
    cross = np.maximum(np.abs(h @ cov[:, 1]), 1e-25)
    return np.column_stack([
        np.full(len(actions), np.log10(cov[1, 1])), np.log10(predictive), np.log10(cross),
        np.log10(np.square([a.noise_m for a in actions])),
        np.log10([a.cost_seconds for a in actions]),
        [a.force_n / 5 for a in actions], [float(a.modality == "gauge") for a in actions]])


@dataclass
class AcquisitionSurrogate:
    """Small random-feature ridge regressor trained to approximate exact acquisition.

    This is experimental. Exact acquisition remains the production default.
    Input/hidden weights are fixed random features, output weights are learned.
    """
    center: Array
    scale: Array
    hidden_weights: Array
    hidden_bias: Array
    output_weights: Array

    @classmethod
    def fit(cls, features: Array, target: Array, *, seed: int = 7123, width: int = 64,
            ridge: float = 0.03) -> AcquisitionSurrogate:
        x = np.asarray(features, dtype=float)
        y = np.asarray(target, dtype=float)
        if (x.ndim != 2 or y.ndim != 1 or len(y) != len(x) or len(x) < 2
                or not np.isfinite(x).all() or not np.isfinite(y).all()):
            raise ValueError("Finite aligned training features and targets are required")
        if width < 1 or ridge <= 0 or not np.isfinite(ridge):
            raise ValueError("Hidden width and ridge regularization must be positive")
        center, scale = x.mean(axis=0), np.maximum(x.std(axis=0), 1e-6)
        rng = np.random.default_rng(seed)
        weights = rng.normal(0, 0.65, (x.shape[1], width))
        bias = rng.normal(0, 0.5, width)
        z = (x - center) / scale
        basis = np.column_stack([np.ones(len(x)), z, np.tanh(z @ weights + bias)])
        output = np.linalg.solve(basis.T @ basis + ridge * np.eye(basis.shape[1]), basis.T @ y)
        return cls(center, scale, weights, bias, output)

    def predict(self, features: Array) -> Array:
        z = (np.asarray(features, dtype=float) - self.center) / self.scale
        basis = np.column_stack([np.ones(len(z)), z, np.tanh(z @ self.hidden_weights + self.hidden_bias)])
        return basis @ self.output_weights

    def save(self, path: str | Path) -> None:
        np.savez_compressed(path, center=self.center, scale=self.scale, hidden_weights=self.hidden_weights,
                            hidden_bias=self.hidden_bias, output_weights=self.output_weights)

    @classmethod
    def load(cls, path: str | Path) -> AcquisitionSurrogate:
        with np.load(path, allow_pickle=False) as source:
            return cls(**{name: source[name] for name in
                          ("center", "scale", "hidden_weights", "hidden_bias", "output_weights")})
