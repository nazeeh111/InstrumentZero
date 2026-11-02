import io
import json
import os
import subprocess
import sys
import zipfile

import numpy as np
import pytest

from instrumentzero.edge import SimulationModel
from instrumentzero.edge.artifacts import export_run
from instrumentzero.edge.simulation import compare, generate
from instrumentzero.edge.spec import EdgeError, default_spec


def test_custom_model_is_seeded_bound_and_checked_against_analytic_truth():
    spec = default_spec()
    model = {'frequency_hz': 19.4, 'decay_per_second': .7, 'noise_rms': .0004, 'amplitude': .8}
    y, ticks, source = generate(spec, 'custom_ringdown', 6001, 8, model)
    again, same_ticks, same_source = generate(spec, 'custom_ringdown', 6001, 8, model)
    assert np.array_equal(y, again) and np.array_equal(ticks, same_ticks) and source == same_source
    t = ticks / 1e6
    clean = .8*np.exp(-.7*t)*np.sin(2*np.pi*19.4*t+.3)
    assert np.std(y[:, 0]-clean) == pytest.approx(.0004, rel=.08)
    assert generate(spec, 'custom_ringdown', 6002, 8, model)[2]['simulation_id'] != source['simulation_id']
    assert generate(spec, 'custom_ringdown', 6001, 8, {**model, 'frequency_hz': 20.4})[2]['simulation_id'] != source['simulation_id']
    run = compare(spec, y, ticks, source=source)
    truth = run['simulation_truth']
    assert run['project_scope'] == 'simulation_only' and truth['status'] == 'within_budgets'
    assert truth['model_damping_ratio'] == pytest.approx(.7 / np.hypot(.7, 2*np.pi*19.4))
    assert truth['frequency_absolute_error_hz'] < .001 and truth['damping_relative_error'] < .01


@pytest.mark.parametrize('model', [[], {'arbitrary': 1}, {'frequency_hz': True}, {'frequency_hz': 200},
                                   {'frequency_hz': float('nan')}, {'decay_per_second': -1},
                                   {'noise_rms': float('inf')}, {'amplitude': 20}])
def test_invalid_models_fail_before_generation(model):
    with pytest.raises(EdgeError):
        generate(default_spec(), 'custom_ringdown', model=model)


def test_typed_model_cannot_bypass_validation_or_override_an_existing_preset():
    with pytest.raises(EdgeError):
        generate(default_spec(), 'custom_ringdown', model=SimulationModel(frequency_hz=-2))
    with pytest.raises(EdgeError, match='custom_ringdown'):
        generate(default_spec(), 'mount_a', model={'frequency_hz': 12})
    run = compare(scenario='custom_ringdown', model=SimulationModel(decay_per_second=0, noise_rms=0))
    assert run['simulation_truth']['status'] == 'frequency_only'
    assert run['simulation_truth']['model_damping_ratio'] == 0
    assert run['simulation_truth']['damping_relative_error'] is None
    assert next(c for c in run['comparisons'] if c['selected'])['result']['damping_ratio'] is None
    assert compare(scenario='silence')['simulation_truth']['status'] == 'unavailable'


def test_cli_custom_model_export_recomputes_truth_from_included_source(tmp_path):
    command = [sys.executable, '-c', 'from instrumentzero.cli import main; main()', 'edge', 'simulate',
               '--scenario', 'custom_ringdown', '--frequency', '21.3', '--decay', '.85', '--noise', '.0003',
               '--amplitude', '.9', '--seed', '6003', '--export', str(tmp_path/'custom.zip')]
    cli = subprocess.run(command, capture_output=True, text=True)
    assert cli.returncode == 0, cli.stderr
    run = json.loads(cli.stdout)
    assert run['source']['model']['frequency_hz'] == 21.3 and run['simulation_truth']['status'] == 'within_budgets'
    with zipfile.ZipFile(tmp_path/'custom.zip') as z:
        assert json.loads(z.read('run.json'))['simulation_truth'] == run['simulation_truth']
        z.extractall(tmp_path/'portable')
    env = os.environ.copy()
    env.pop('PYTHONPATH', None)
    recomputed = subprocess.run([sys.executable, str(tmp_path/'portable/recompute.py')], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert recomputed.returncode == 0, recomputed.stderr
    assert json.loads(recomputed.stdout)['simulation_truth']['status'] == 'within_budgets'
    # A recording extension keeps its actual source label; it is not relabeled synthetic.
    samples, ticks, _ = generate(default_spec())
    recording = compare(samples=samples, timestamps_us=ticks, source={'source_kind':'user_supplied_recording'})
    assert recording['project_scope'] == 'recording_analysis_extension'
    assert recording['simulation_truth']['status'] == 'unavailable'
    with zipfile.ZipFile(io.BytesIO(export_run(recording, samples, ticks))) as z:
        assert json.loads(z.read('run.json'))['source']['source_kind'] == 'user_supplied_recording'
