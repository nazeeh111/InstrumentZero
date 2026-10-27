import copy
import io
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import numpy as np
import pytest
from scipy.io import wavfile

from instrumentzero.acoustic import analyze_audio, load_wav
from instrumentzero.engine import analyze_stiffness, compile_experiment
from instrumentzero.examples import recorded_stiffness_example, stiffness_example
from instrumentzero.export import export_package
from instrumentzero.spec import MeasurementError, MeasurementSpec


@pytest.fixture
def spring():
    return stiffness_example()


def test_known_stiffness_and_offset(spring):
    result = spring["result"]
    assert abs(result["quantity"]["value"] - 80) < 2
    assert result["quantity"]["interval_95"][0] < 80 < result["quantity"]["interval_95"][1]
    assert abs(result["fit"]["offset_m"] - .002) < .0002
    assert result["source_kind"] == "synthetic"
    assert result["next_experiment"]["settings"]["mode"].startswith("proposed")


def test_shared_calibration_does_not_average_away(spring):
    spec = copy.deepcopy(spring["spec"])
    spec["calibration"]["scale_relative_sd"] = .1
    rows = spring["rows"] * 100
    result = analyze_stiffness(spec, rows)
    assert result["quantity"]["relative_uncertainty"] > .18
    assert "calibration" in result["next_experiment"]["reason"]


def test_missing_calibration_refuses_pixel_fit(spring):
    spec = copy.deepcopy(spring["spec"])
    spec["calibration"].pop("meters_per_pixel")
    with pytest.raises(MeasurementError, match="meters_per_pixel"):
        analyze_stiffness(spec, spring["rows"])
    assert not compile_experiment(spec)["identifiable"]


def test_equipment_name_alone_is_not_a_calibration(spring):
    spec = dict(spring["spec"], calibration={}, equipment=["csv", "recorded sensor data"])
    assert not compile_experiment(spec)["identifiable"]


def test_unidentifiable_offset_and_compliance(spring):
    with pytest.raises(MeasurementError, match="not identifiable"):
        analyze_stiffness(spring["spec"], [{"force_n": .5, "position_px": i} for i in range(6)])


def test_zero_crossing_is_unbounded(spring):
    rows = [{"force_n": float(f), "position_px": 20} for f in np.linspace(0, 1, 8)]
    result = analyze_stiffness(spring["spec"], rows)
    assert result["quantity"]["value"] is None
    assert result["status"] == "unreliable"
    json.dumps(result, allow_nan=False)


def test_nonlinear_spring_cannot_claim_linear_result(spring):
    rows = [{"force_n": float(f), "position_px": float(20 + 125 * f + 200 * f * f)}
            for f in np.linspace(0, 1, 10)]
    result = analyze_stiffness(spring["spec"], rows)
    assert result["status"] == "unreliable"
    assert any("Curvature" in text for text in result["warnings"])
    assert not result["next_experiment"]["feasible"]
    assert "force_n" not in result["next_experiment"]["settings"]


@pytest.mark.parametrize("field,value", [("budget_seconds", float("nan")), ("max_force_n", -1),
                                         ("target_relative_uncertainty", True), ("domain", "gravity")])
def test_invalid_specification(spring, field, value):
    spec = copy.deepcopy(spring["spec"])
    spec[field] = value
    with pytest.raises(MeasurementError):
        MeasurementSpec.parse(spec)


def test_unsupported_question_is_not_fake_reasoning(spring):
    spec = dict(spring["spec"], question="What is the mass of the moon?")
    with pytest.raises(MeasurementError, match="outside"):
        compile_experiment(spec)


def audio_spec():
    return {"domain": "acoustic", "question": "What is the resonance frequency?", "source_kind": "synthetic",
            "min_frequency_hz": 100, "max_frequency_hz": 1000,
            "calibration": {"sample_clock_relative_sd": .0001}}


def test_audio_known_tone_and_clock_floor():
    rate = 8000
    t = np.arange(rate * 2) / rate
    y = .4 * np.sin(2 * np.pi * 443.27 * t)
    result = analyze_audio(audio_spec(), y, rate)
    assert abs(result["quantity"]["value"] - 443.27) < .01
    assert result["quantity"]["interval_95"][0] < 443.27 < result["quantity"]["interval_95"][1]
    assert "not validated" in result["quantity"]["interval_label"]
    spec = dict(audio_spec(), budget_seconds=1)
    action = analyze_audio(spec, y, rate)["next_experiment"]
    assert action["settings"]["duration_seconds"] <= 1


def test_audio_competing_sources_are_flagged():
    rate = 8000
    t = np.arange(rate * 2) / rate
    y = .3 * np.sin(2 * np.pi * 440 * t) + .3 * np.sin(2 * np.pi * 615 * t)
    result = analyze_audio(audio_spec(), y, rate)
    assert result["status"] == "unreliable"
    assert any("Other strong peaks" in w for w in result["warnings"])


@pytest.mark.parametrize("source", ["below_band", "ramp"])
def test_audio_leakage_cannot_be_a_reliable_resonance(source):
    rate = 8000
    t = np.arange(rate * 2) / rate
    y = .4 * np.sin(2 * np.pi * 90.3 * t) if source == "below_band" else .4 * t / t[-1]
    with pytest.raises(MeasurementError, match="boundary"):
        analyze_audio(audio_spec(), y, rate)


def test_unresolved_equal_nearby_tones_are_unreliable():
    rate = 8000
    t = np.arange(rate * 2) / rate
    y = .3 * np.sin(2 * np.pi * 440 * t) + .3 * np.sin(2 * np.pi * 441 * t)
    assert analyze_audio(audio_spec(), y, rate)["status"] == "unreliable"


def test_audio_invalid_sampling_and_silence():
    with pytest.raises(MeasurementError, match="Nyquist"):
        analyze_audio(audio_spec(), np.zeros(4000), 1800)
    with pytest.raises(MeasurementError, match="silent"):
        analyze_audio(audio_spec(), np.zeros(8000), 8000)
    spec = audio_spec()
    spec["calibration"] = {}
    with pytest.raises(MeasurementError, match="sample_clock"):
        analyze_audio(spec, np.ones(8000), 8000)


def test_wav_stereo_and_unsigned_normalization(tmp_path):
    file = tmp_path / "stereo.wav"
    samples = np.array([[0, 0], [32767, 32767], [-32768, -32768]], dtype=np.int16)
    wavfile.write(file, 8000, samples)
    normalized, rate = load_wav(file)
    assert rate == 8000
    assert normalized[2] == pytest.approx(-1)
    wavfile.write(file, 8000, np.array([0, 128, 255], dtype=np.uint8))
    normalized, _ = load_wav(file)
    assert normalized[1] == 0
    assert normalized[0] == -1


def test_export_reproduces_without_installed_package(spring, tmp_path):
    data = export_package({"spec": spring["spec"], "rows": spring["rows"]})
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert {"calibration.json", "observations.csv", "reproduce.py", "instrumentzero/engine.py", "LICENSE"} <= set(archive.namelist())
        archive.extractall(tmp_path)
    run = subprocess.run([sys.executable, str(tmp_path / "reproduce.py")], cwd=tmp_path,
                         text=True, capture_output=True)
    assert run.returncode == 0, run.stderr
    output = json.loads((tmp_path / "reproduced-result.json").read_text())
    assert output["quantity"] == spring["result"]["quantity"]
    assert output["provenance"]["observation_sha256"] == spring["result"]["provenance"]["observation_sha256"]


def test_authentic_fixture_when_present():
    path = Path(__file__).parents[1] / "data/tuning-fork-440Hz.wav"
    if not path.exists():
        pytest.skip("External fixture absent; core tests do not download data")
    samples, rate = load_wav(path)
    spec = audio_spec()
    spec.update(source_kind="recorded", source_name="jmuehlhans CC0 tuning fork")
    result = analyze_audio(spec, samples, rate)
    assert 439 < result["quantity"]["value"] < 441
    assert result["source_kind"] == "recorded"
    assert "No independently calibrated" in result["provenance"]["validation"]


def test_recorded_export_keeps_source_license_and_limits():
    example = recorded_stiffness_example(Path(__file__).parents[1] / "data")
    with zipfile.ZipFile(io.BytesIO(export_package(example))) as archive:
        notice = archive.read("DATA-NOTICES.txt").decode()
        assert "10.17632/syjkdyzmxj.1" in notice
        assert "Wojciech J. Dera" in notice
        assert "https://creativecommons.org/licenses/by/4.0/" in notice
        assert "sensitivity assumptions" in notice
        result = json.loads(archive.read("result.json"))
        assert result["provenance"]["source_attribution"] == example["spec"]["source_attribution"]
        assert not result["next_experiment"]["feasible"]


def test_audio_export_retains_calibration_caveat_and_nominal_reference():
    spec = audio_spec()
    spec["source_limitations"] = ["Clock SD is an assumption without a certificate."]
    spec["reference"] = {"value": 440, "unit": "Hz", "kind": "synthetic comparison only"}
    rate = 8000
    t = np.arange(rate) / rate
    y = .4 * np.sin(2 * np.pi * 443 * t)
    with zipfile.ZipFile(io.BytesIO(export_package({"spec": spec, "samples": y, "sample_rate_hz": rate}))) as archive:
        result = json.loads(archive.read("result.json"))
        assert result["reference"]["kind"] == "synthetic comparison only"
        assert "Clock SD is an assumption without a certificate." in result["warnings"]
