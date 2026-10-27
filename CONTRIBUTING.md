# Contributing

Start with a reproducible measurement or concrete failing case. Include the question, instruments, units, calibration, data license and expected behavior. Keep observations, simulations and proposed actions separate.

Install `python -m pip install -e '.[dev]'`, run `python -m pytest -q`, `python -m ruff check src tests scripts data/reproduce.py`, and `python data/reproduce.py`. HTTP tests use temporary loopback ports. Evaluations require fresh output directories and retained seeds/configuration.

Useful contributions:

- Calibrated camera fixtures: known loads, original frames, scale uncertainty and an independently measured reference.
- Camera/microphone acceptance: permission denial, stop, cancellation, lost markers and actual-device checks.
- Model-discrimination or nonlinear designs against strong equal-budget conventional protocols.
- One tested named instrument adapter with limits and device metadata.
- Accessibility improvements backed by real browser checks.

Never submit secrets, restricted datasets, private recordings, or simulations labeled real. Measurement fixtures need provenance and checksums. Report negative comparisons. Do not change a physical assumption just to improve a benchmark score.
