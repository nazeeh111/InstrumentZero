import importlib.util
from pathlib import Path

import numpy as np

ROOT = Path(__file__).parents[1]
SPEC = importlib.util.spec_from_file_location('acoustic_acceptance', ROOT/'scripts/validate_acoustic.py')
acceptance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(acceptance)


def test_generated_case_is_repeatable_and_labeled_synthetic():
    spec, signal, reference = acceptance.signal_case('nominal_clock', 1)
    other_spec, other, other_reference = acceptance.signal_case('nominal_clock', 1)
    assert spec['source_kind'] == 'synthetic'
    assert spec == other_spec and reference == other_reference
    np.testing.assert_array_equal(signal, other)


def test_two_tones_and_clock_drift_have_different_acceptance_meanings():
    rejected = acceptance.evaluate_case('nearby_tones', 0, 20261026)
    assert not rejected['reliable']
    assert rejected['reference_frequency_hz'] is None
    assert rejected['envelope_covers_reference'] is None
    tone = acceptance.evaluate_case('unmodeled_clock_drift', 0, 20261026)
    assert tone['reference_frequency_hz'] is not None
    assert tone['error_hz'] is not None
    assert acceptance.wilson(0, 0) is None
    assert acceptance.wilson(5, 10)[0] < .5 < acceptance.wilson(5, 10)[1]
