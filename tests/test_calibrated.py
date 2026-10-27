import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pytest

from instrumentzero.calibrated import (
    calibrated_acoustic_validation,
    compare_level_grids,
    export_calibrated_package,
)
from instrumentzero.spec import MeasurementError

ROOT = Path(__file__).parents[1]


def test_paired_levels_are_not_averaged_as_pressures_or_independent_repeats():
    reference = np.array([[60, 70], [80, 90.]])
    measured = reference+np.array([[1, 2], [-1, -2.]])
    result = compare_level_grids(measured, reference)
    assert result['mean_difference_db'] == 0
    assert result['twice_spatial_sd_db'] == pytest.approx(2*np.std([1, 2, -1, -2], ddof=1))
    assert result['mean_confidence_interval'] is None
    with pytest.raises(MeasurementError, match='matching'):
        compare_level_grids(measured, reference[:1])


def test_ptb_calibrated_field_matches_published_comparison_and_preserves_scope():
    result = calibrated_acoustic_validation(ROOT/'data')
    assert result['comparison']['positions'] == 1089
    assert result['comparison']['mean_difference_db'] == pytest.approx(.7050944807, abs=1e-9)
    assert result['comparison']['twice_spatial_sd_db'] == pytest.approx(5.9495892699, abs=1e-9)
    assert result['published_numerical_check']['mean_reproduced_to_publication_rounding']
    assert result['calibration']['HiFUSPEx']['expanded_sensitivity_uncertainty_db'] == .6
    assert result['calibration']['USPM']['coverage_factor'] == 2
    assert result['quantity']['interval_95'] is None
    assert not result['live_hardware_run']
    for wave in result['waveforms'].values():
        assert 19999 < wave['spectral_peak_hz_on_nominal_clock'] < 20001
        assert wave['raw_waveform_pressure_pa'] is None
        assert not wave['clock_calibration_verified']


def test_ptb_portable_export_keeps_measured_sources_and_limits():
    with zipfile.ZipFile(io.BytesIO(export_calibrated_package(ROOT/'data'))) as archive:
        result = json.loads(archive.read('result.json'))
        assert result['provenance']['source_doi'] == '10.7795/720.20211214'
        assert 'LICENSE' in archive.namelist()
        assert len([n for n in archive.namelist() if n.endswith('.wav')]) == 2
        assert 'sample clock' in archive.read('LIMITATIONS.txt').decode()
