"""Replay the unchanged historical simulation plan in a verified isolated overlay."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PLAN = 'examples/edge/simulation-plan-v0.3-final.json'
PLAN_SHA256 = '6033d8d2626fd203647ac78ff5d7dad33be850d1f809e806e3bfbbff2f6e5de0'
SNAPSHOT_ROOT = 'examples/edge/historical-simulation-v0.3-source'
RESTORED = {
    name: f'{SNAPSHOT_ROOT}/{name}' for name in (
        'src/instrumentzero/__init__.py', 'src/instrumentzero/cli.py',
        'src/instrumentzero/edge/cli.py', 'src/instrumentzero/edge/estimator.py', 'src/instrumentzero/edge/simulation.py',
        'src/instrumentzero/server.py', 'src/instrumentzero/web/edge.css',
        'src/instrumentzero/web/edge.html', 'src/instrumentzero/web/edge.js',
        'src/instrumentzero/web/index.html', 'src/instrumentzero/web/style.css',
    )
}
RESTORED['src/instrumentzero/web/app.js'] = 'examples/acquisition-acceptance-v0.2/source-snapshot/app.js'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_inputs(root):
    plan_path = root / PLAN
    if digest(plan_path) != PLAN_SHA256:
        raise ValueError('Historical plan changed')
    plan = json.loads(plan_path.read_text())
    frozen = plan['frozen_sha256']
    if len(frozen) != 43 or not set(RESTORED).issubset(frozen):
        raise ValueError('Historical binding set changed')
    for name, expected in frozen.items():
        path = root / RESTORED.get(name, name)
        if digest(path) != expected:
            raise ValueError(f'Historical source/input changed: {name}')
    return frozen


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise SystemExit('Output already exists')
    frozen = verify_inputs(ROOT)
    base = subprocess.check_output(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True).strip()
    with tempfile.TemporaryDirectory(prefix='instrumentzero-historical-simulation-') as tmp:
        clone = Path(tmp) / 'source'
        subprocess.run(['git', 'clone', '--quiet', '--no-hardlinks', '--local', str(ROOT), str(clone)], check=True)
        clone_head = subprocess.check_output(['git', '-C', str(clone), 'rev-parse', 'HEAD'], text=True).strip()
        if clone_head != base:
            raise ValueError('Overlay checkout HEAD changed')
        shutil.copyfile(ROOT / PLAN, clone / PLAN)
        if digest(clone / PLAN) != PLAN_SHA256:
            raise ValueError('Overlay historical plan changed')
        for name in frozen:
            source = ROOT / RESTORED.get(name, name)
            target = clone / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
        for name, expected in frozen.items():
            if digest(clone / name) != expected:
                raise ValueError(f'Overlay source/input changed: {name}')
        env = dict(os.environ, PYTHONPATH=str(clone / 'src'))
        subprocess.run([sys.executable, str(clone / 'scripts/validate_simulation.py'), '--output', str(output)],
                       cwd=clone, env=env, check=True)
    metadata = {'kind': 'mixed historical-input replay', 'base_checkout_head': base,
                'historical_plan_sha256': PLAN_SHA256,
                'restored_source_sha256': {name: frozen[name] for name in RESTORED}}
    (output / 'overlay-provenance.json').write_text(json.dumps(metadata, indent=2) + '\n')


if __name__ == '__main__':
    main()
