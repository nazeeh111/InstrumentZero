"""Checks on paired, source-calibrated PTB acoustic field recordings.

Source-calibrated SPL grids and raw ADC waveform diagnostics have deliberately
different units and evidence scopes. Missing transfer gains are never guessed.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import scipy
from scipy import signal
from scipy.io import wavfile

from .spec import MeasurementError


def compare_level_grids(measured_db: np.ndarray, reference_db: np.ndarray) -> dict:
    """Descriptive paired differences; grid positions are not independent trials."""
    measured, reference = np.asarray(measured_db, float), np.asarray(reference_db, float)
    if (measured.ndim != 2 or measured.shape != reference.shape or measured.size < 2
            or not np.isfinite(measured).all() or not np.isfinite(reference).all()):
        raise MeasurementError("Provide two matching finite sound-level matrices.")
    differences = measured-reference
    mean = float(np.mean(differences))
    spatial_sd = float(np.std(differences, ddof=1))
    return {"positions": measured.size, "grid_shape": list(measured.shape), "mean_difference_db": mean,
            "spatial_difference_sd_db": spatial_sd, "twice_spatial_sd_db": 2*spatial_sd,
            "rmse_difference_db": float(np.sqrt(np.mean(differences**2))),
            "median_difference_db": float(np.median(differences)),
            "minimum_difference_db": float(np.min(differences)),
            "maximum_difference_db": float(np.max(differences)),
            "difference_db": differences.tolist(), "measured_level_db": measured.tolist(),
            "reference_level_db": reference.tolist(),
            "mean_confidence_interval": None,
            "dispersion_interpretation": "Two times the spatial sample SD of device differences; "
            "not an interval for the mean, not total per-position measurement uncertainty, "
            "and not 1089 independent repeat measurements."}


def _one(root: Path, pattern: str) -> Path:
    matches = list(root.rglob(pattern))
    if len(matches) != 1:
        raise MeasurementError(f"Expected exactly one retained PTB source matching {pattern}.")
    return matches[0]


def _sensitivity(path: Path, frequency_hz: float) -> dict:
    entries = []
    with path.open(newline='', encoding='utf-8-sig') as stream:
        for row in csv.reader(stream):
            if len(row) < 3:
                continue
            try:
                f, value, expanded = map(float, row[:3])
            except ValueError:
                continue
            if f == frequency_hz:
                entries.append((f, value, expanded))
    if len(entries) != 1 or not np.isfinite(entries).all():
        raise MeasurementError("The requested frequency needs one unambiguous finite pressure-sensitivity calibration.")
    f, value, expanded = entries[0]
    return {"frequency_hz": f, "sensitivity_db_re_1_v_per_pa": value,
            "expanded_sensitivity_uncertainty_db": expanded, "coverage_factor": 2,
            "standard_sensitivity_uncertainty_db": expanded/2,
            "scope": "Microphone pressure sensitivity only; not ADC-clock calibration or total sound-level uncertainty."}


def waveform_diagnostic(path: Path) -> dict:
    rate, raw = wavfile.read(path)
    if raw.ndim != 1 or not np.isfinite(raw).all() or len(raw) < rate*.25:
        raise MeasurementError("Expected the retained finite mono PTB waveform.")
    samples = raw.astype(float)
    dc = float(np.mean(samples))
    ac = samples-dc
    frequencies, power = signal.periodogram(ac, rate, window='hann')
    band = (frequencies >= 18000) & (frequencies <= 22000)
    ids = np.where(band)[0]
    if not len(ids) or np.max(power[ids]) <= 0:
        raise MeasurementError("No resolvable source-band signal in the retained waveform.")
    peak = int(ids[np.argmax(power[ids])])
    if len(ids) > 600:
        ids = np.array([chunk[np.argmax(power[chunk])] for chunk in np.array_split(ids, 600)])
    return {"sample_rate_hz_nominal": int(rate), "samples": len(samples), "duration_seconds": len(samples)/rate,
            "raw_adc_mean": dc, "raw_adc_ac_rms": float(np.sqrt(np.mean(ac**2))),
            "spectral_peak_hz_on_nominal_clock": float(frequencies[peak]),
            "fft_resolution_hz": rate/len(samples), "clock_calibration_verified": False,
            "spectrum": {"frequency_hz": frequencies[ids].tolist(), "power_raw_units": power[ids].tolist()},
            "raw_waveform_pressure_pa": None,
            "scope": "DC-removed raw ADC spectrum on nominal sample-rate axis; missing complete transfer gains "
            "prevent an independently reconstructed raw-WAV-to-Pa calibration."}


def calibrated_acoustic_validation(data_dir: Path) -> dict:
    root = Path(data_dir)/'calibrated-v2/hifuspex'
    if not root.is_dir():
        raise MeasurementError("The public calibrated PTB fixture is absent; obtain the attributed source subset.")
    manifest = json.loads((root/'provenance.json').read_text())
    for item in manifest['retained_source_files']:
        path = (root.parent/item['local_path']).resolve()
        if not path.is_relative_to(root.resolve()):
            raise MeasurementError("Source provenance must remain inside the retained PTB fixture.")
        if path.stat().st_size != item['bytes'] or hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise MeasurementError("A retained PTB source differs from its recorded checksum.")
    measured_path = _one(root, '*Standing_HiFUSPEx_X17.csv')
    reference_path = _one(root, '*Standing_USPM_X17.csv')
    measured = np.loadtxt(measured_path, delimiter=',')
    reference = np.loadtxt(reference_path, delimiter=',')
    if measured.shape != (33, 33) or reference.shape != (33, 33):
        raise MeasurementError("The retained PTB surface must contain 33 by 33 matched positions.")
    comparison = compare_level_grids(measured, reference)
    calibration = {name: _sensitivity(root/f'{name}_CalibrationData.txt', 20000)
                   for name in ('HiFUSPEx', 'USPM')}
    waves = {name: waveform_diagnostic(_one(root/f'WeldingMachine/WithoutProtectionGrid/20kHz/Standing/LeftEar/{name}', '*.wav'))
             for name in ('HiFUSPEx', 'USPM')}
    paths = sorted(p for p in root.rglob('*') if p.is_file())
    return {"domain": "acoustic", "source_kind": "recorded calibrated reference comparison",
            "source_name": "PTB HiFUSPEx validation measurements / 20 kHz / standing / left ear / no grid",
            "live_hardware_run": False, "quantity": {"name": "Mean measured-minus-reference SPL", "value": comparison['mean_difference_db'],
            "unit": "dB", "interval_95": None,
            "interval_label": "No mean confidence interval: spatial positions are correlated, not independent repeats"},
            "comparison": comparison, "calibration": calibration, "waveforms": waves,
            "published_numerical_check": {"source": "Dataset description, Table 1, 20 kHz standing left ear",
                "rounded_mean_difference_db": .71, "rounded_twice_spatial_sd_db": 5.95,
                "mean_reproduced_to_publication_rounding": abs(comparison['mean_difference_db']-.71) <= .005,
                "spatial_dispersion_reproduced_to_publication_rounding": abs(comparison['twice_spatial_sd_db']-5.95) <= .005,
                "interpretation": "Numerical reproduction of the published cross-instrument comparison; "
                "not a new independent laboratory replication."},
            "provenance": {"source_doi": "10.7795/720.20211214", "license": "CC-BY-4.0",
                "source_sha256": {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
                "reference": "USPM ultrasound level meter; source reports calibration traceability to PTB national standards",
                "matching": "Source-matched grid indices after its 9 mm microphone-geometry adjustment; sequential same-day scans"},
            "warnings": [
                "Authentic externally recorded measurements; no physical equipment was accessed in this validation.",
                "Use the source-calibrated SPL matrices as level measurements. Raw ADC files are analyzed only as raw-unit waveform diagnostics.",
                "Pressure sensitivity calibration does not calibrate the sample clock. No traceable frequency-accuracy claim follows from the 20 kHz peaks.",
                "Two times spatial SD is a dispersion of device differences, not a 95% interval for the mean or total point uncertainty.",
                "The source reference and device scans were sequential rather than simultaneous; alignment, spatial gradients and temporal changes matter.",
                "Exact physical coordinates for each matrix cell and raw point-to-matrix reconstruction have not been independently reproduced.",
                "Calibration sensitivity uncertainties may share reference-system correlations; no unjustified independence combination is made.",
                "This validates a recorded cross-instrument acoustic field comparison, not live browser microphone behavior or arbitrary audio accuracy."]}


def export_calibrated_package(data_dir: Path) -> bytes:
    result = calibrated_acoustic_validation(data_dir)
    root = Path(data_dir)/'calibrated-v2/hifuspex'
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('result.json', json.dumps(result, indent=2, allow_nan=False)+'\n')
        for relative in result['provenance']['source_sha256']:
            archive.write(root/relative, 'data/calibrated-v2/hifuspex/'+relative)
        source = Path(__file__).parent
        archive.writestr('instrumentzero/__init__.py', '')
        for filename in ('calibrated.py', 'spec.py'):
            archive.write(source/filename, 'instrumentzero/'+filename)
        license_path = source/'LICENSE'
        if not license_path.exists():
            license_path = source.parents[1]/'LICENSE'
        archive.write(license_path, 'LICENSE')
        archive.writestr('requirements.txt', f'numpy=={np.__version__}\nscipy=={scipy.__version__}\n')
        archive.writestr('reproduce.py', 'import json\nfrom pathlib import Path\n'
                         'from instrumentzero.calibrated import calibrated_acoustic_validation\n'
                         'root=Path(__file__).parent\nresult=calibrated_acoustic_validation(root/"data")\n'
                         '(root/"reproduced-result.json").write_text(json.dumps(result,indent=2,allow_nan=False)+"\\n")\n'
                         'print(json.dumps(result["quantity"],indent=2))\n')
        archive.writestr('LIMITATIONS.txt', '\n'.join(result['warnings'])+'\n')
        archive.writestr('README.txt', 'Recorded calibrated PTB source data, not a live experiment.\n'
                         'Install requirements, then python reproduce.py. See retained CC-BY-NOTICE and SOURCE documentation under data/.\n'
                         'Source-calibrated level matrices and raw ADC diagnostics have different units/evidence scopes.\n')
    return archive_buffer.getvalue()
