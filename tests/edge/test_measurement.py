import io
import json
import os
import subprocess
import sys
import zipfile

import numpy as np
import pytest
from scipy import signal

from instrumentzero.edge.artifacts import export_run
from instrumentzero.edge.estimator import ringdown
from instrumentzero.edge.runtime import execute
from instrumentzero.edge.simulation import compare, generate
from instrumentzero.edge.spec import EdgeError, compile_graph, default_spec


@pytest.mark.parametrize("scenario,frequency", [("mount_a", 17.25), ("mount_b", 22.5)])
def test_known_changed_input_and_separate_peak_reference(scenario, frequency):
    s = default_spec()
    samples, ticks, source = generate(s, scenario, seed=82739)
    run = compare(s, samples, ticks, source=source)
    assert not run["source"]["independent_physical_reference"]
    for mode in run["comparisons"]:
        assert mode["measurement_error_budget_passed_for_this_input"]
        assert mode["result"]["frequency_hz"] == pytest.approx(frequency, abs=.001)
        expected_zeta = source["model_decay_per_second"]/np.sqrt((2*np.pi*frequency)**2+source["model_decay_per_second"]**2)
        assert mode["result"]["damping_ratio"] == pytest.approx(expected_zeta, rel=.005)
    # Separate, simple zero crossings and log-peak regression on the known raw waveform.
    y = samples[:, 0]
    crossings = np.flatnonzero((y[:-1] < 0) & (y[1:] >= 0))
    fractional = crossings-y[crossings]/(y[crossings+1]-y[crossings])
    reference = 400/np.median(np.diff(fractional[:50]))
    assert reference == pytest.approx(frequency, abs=.015)
    peaks, _ = signal.find_peaks(y[:1200], distance=int(400/frequency*.8))
    slope, _ = np.polyfit(peaks/400, np.log(y[peaks]), 1)
    assert -slope == pytest.approx(source["model_decay_per_second"], abs=.01)


@pytest.mark.parametrize("scenario", ["silence", "chirp", "close_modes", "impulse"])
def test_unsuitable_signals_reject(scenario):
    run = compare(scenario=scenario)
    assert all(c["result"]["status"] == "rejected" for c in run["comparisons"])


def test_clipping_and_mismatched_clock_are_acquisition_failures():
    c = compile_graph(default_spec())
    y, t, _ = generate(c["spec"], "saturation")
    with pytest.raises(EdgeError, match="clip"):
        execute(c, y, t)
    y, t, _ = generate(c["spec"])
    with pytest.raises(EdgeError, match="sample rate"):
        execute(c, y, np.rint(t*1.01).astype(np.int64))


def test_stationary_tone_does_not_identify_damping():
    s = default_spec()
    result = ringdown(np.sin(2*np.pi*17*np.arange(800)/100), 100, s["estimator"])
    assert result["frequency_hz"] == pytest.approx(17, abs=.001)
    assert result["damping_ratio"] is None
    assert any("not identifiable" in r for r in result["damping_rejection_reasons"])


def test_source_complete_portable_bundle_recomputes_without_project_path(tmp_path):
    s = default_spec()
    y, t, source = generate(s, seed=536)
    run = compare(s, y, t, source=source)
    archive = export_run(run, y, t)
    with zipfile.ZipFile(io.BytesIO(archive)) as z:
        z.extractall(tmp_path)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    result = subprocess.run([sys.executable, str(tmp_path/"recompute.py")], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["recomputed"]
