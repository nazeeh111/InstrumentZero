"""Guard checks for historical and current simulation generations."""
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HISTORICAL = 'examples/edge/simulation-plan-v0.3-final.json'
CURRENT = 'examples/edge/simulation-plan-current-v0.3.1-dev.json'


def copy_source(destination):
    shutil.copytree(ROOT, destination, ignore=shutil.ignore_patterns('.git', '__pycache__', '.pytest_cache', '.venv'))


def test_current_plan_keeps_historical_cases_and_acceptance():
    old = json.loads((ROOT / HISTORICAL).read_text())
    new = json.loads((ROOT / CURRENT).read_text())
    assert new['cases'] == old['cases']
    assert new['acceptance'] == old['acceptance']
    assert set(new['frozen_sha256']) == set(old['frozen_sha256'])
    assert len(new['frozen_sha256']) == 43


def test_historical_snapshot_tampering_refused_before_output(tmp_path):
    copy = tmp_path / 'source'
    copy_source(copy)
    (copy / 'examples/edge/historical-simulation-v0.3-source/src/instrumentzero/web/style.css').write_text('poison')
    output = tmp_path / 'historic-output'
    run = subprocess.run([sys.executable, str(copy / 'scripts/replay_historical_simulation.py'), '--output', str(output)],
                         capture_output=True, text=True, check=False)
    assert run.returncode != 0
    assert 'Historical source/input changed' in run.stderr
    assert not output.exists()


def test_current_input_tampering_refused_before_output(tmp_path):
    copy = tmp_path / 'source'
    copy_source(copy)
    (copy / 'src/instrumentzero/web/style.css').write_text('poison')
    output = tmp_path / 'current-output'
    env = dict(os.environ, PYTHONPATH=str(copy / 'src'))
    run = subprocess.run([sys.executable, str(copy / 'scripts/validate_simulation.py'), '--plan', str(copy / CURRENT),
                          '--output', str(output)], cwd=copy, env=env, capture_output=True, text=True, check=False)
    assert run.returncode != 0
    assert 'Frozen source/input changed: src/instrumentzero/web/style.css' in run.stderr
    assert not output.exists()
