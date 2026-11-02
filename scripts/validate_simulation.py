"""Execute a source-frozen simulation acceptance plan and retain every outcome."""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np

from instrumentzero.edge.simulation import compare, generate
from instrumentzero.edge.spec import EdgeError

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--plan', type=Path, default=ROOT/'examples/edge/simulation-plan-v0.3-final.json')
    parser.add_argument('--output', type=Path, required=True, help='New folder; never overwrites prior evidence')
    args = parser.parse_args()
    plan = json.loads(args.plan.read_text())
    for name, digest in plan['frozen_sha256'].items():
        if hashlib.sha256((ROOT/name).read_bytes()).hexdigest() != digest:
            raise SystemExit('Frozen source/input changed: '+name)
    args.output.mkdir(parents=True, exist_ok=False)
    report = {'schema':'instrumentzero.simulation.acceptance/1', 'scope':'simulation_only',
              'source_commit':subprocess.check_output(['git','-C',str(ROOT),'rev-parse','HEAD'], text=True).strip(),
              'plan_sha256':hashlib.sha256(args.plan.read_bytes()).hexdigest(), 'trials':[],
              'hardware_required':False, 'physical_measurements_claimed':False}
    for case in plan['cases']:
        trial = {'case':case, 'passed':False}
        spec = json.loads((ROOT/case['spec']).read_text())
        costs = json.loads((ROOT/case['costs']).read_text())
        try:
            y, ticks, source = generate(spec, case['scenario'], case['seed'], case['seconds'], case.get('model'))
            np.savez_compressed(args.output/(case['id']+'.npz'), samples=y, timestamps_us=ticks)
            trial['raw_sha256'] = hashlib.sha256(y.tobytes()+ticks.tobytes()).hexdigest()
            try:
                run = compare(spec, y, ticks, costs, source)
            except EdgeError as exc:
                trial['rejected_input'] = str(exc)
                trial['passed'] = case['expected']=='clip' and 'clip' in str(exc).lower()
            else:
                (args.output/(case['id']+'.json')).write_text(json.dumps(run, indent=2, allow_nan=False)+'\n')
                chosen = next(c for c in run['comparisons'] if c['selected'])
                truth = run['simulation_truth']
                trial.update(selected=chosen['mode'], truth=truth,
                             framed_bytes=[c['metrics']['wire_bytes_including_headers'] for c in run['comparisons']])
                expected = case['expected']
                if expected == 'fit':
                    trial['passed'] = (truth['status']=='within_budgets' and
                        truth['frequency_absolute_error_hz'] <= plan['acceptance']['frequency_absolute_error_hz'] and
                        truth['damping_relative_error'] <= plan['acceptance']['damping_relative_error'] and
                        all(c['measurement_error_budget_passed_for_this_input'] for c in run['comparisons']))
                elif expected == 'frequency_only':
                    trial['passed'] = (truth['status']=='frequency_only' and chosen['result']['damping_ratio'] is None and
                        truth['frequency_absolute_error_hz'] <= plan['acceptance']['frequency_absolute_error_hz'])
                elif expected == 'reject':
                    trial['passed'] = all(c['result']['status']=='rejected' for c in run['comparisons'])
                elif expected == 'recovery':
                    life = run['lifecycle_demo']
                    trial['passed'] = (life['old_session_rejected'] and life['result_invalidated_on_disconnect'] and
                        life['recovered_sequence_starts_at_zero'] and life['interrupted_session']!=life['recovered_session'] and
                        chosen['result']['status']=='accepted_model_fit')
                if 'selected' in case:
                    trial['passed'] = trial['passed'] and chosen['mode']==case['selected']
        except Exception as exc:
            trial['error'] = type(exc).__name__+': '+str(exc)
        report['trials'].append(trial)
    report['all_passed'] = all(t['passed'] for t in report['trials'])
    (args.output/'results.json').write_text(json.dumps(report, indent=2, allow_nan=False)+'\n')
    print(json.dumps({'trials':len(report['trials']), 'all_passed':report['all_passed'], 'report':str(args.output/'results.json')}))
    if not report['all_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
