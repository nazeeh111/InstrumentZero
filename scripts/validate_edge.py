"""Execute frozen synthetic confirmation and retain every trial, including failures."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from instrumentzero.edge.simulation import compare, generate
from instrumentzero.edge.spec import EdgeError, identity

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True, help='New empty confirmation folder')
    args = parser.parse_args()
    plan_path = ROOT/'examples/edge/confirmation-plan.json'
    plan = json.loads(plan_path.read_text())
    for name, expected in plan['frozen_sha256'].items():
        actual = hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
        if actual != expected:
            raise SystemExit('Frozen confirmation input changed: '+name)
    args.output.mkdir(parents=True, exist_ok=False)
    standard = json.loads((ROOT/'examples/edge/simulation-spec.json').read_text())
    host = json.loads((ROOT/'examples/edge/host-favored-spec.json').read_text())
    costs = json.loads((ROOT/'examples/edge/cost-profile.json').read_text())
    host_costs = json.loads((ROOT/'examples/edge/host-favored-cost-profile.json').read_text())
    trials = []
    for case in ('standard','host_favored'):
        spec, profile = (standard,costs) if case=='standard' else (host,host_costs)
        scenarios = plan['scenarios'] if case=='standard' else plan['host_favored_cases']
        for scenario in scenarios:
            for seed in plan['confirmation_seeds']:
                name = f'{case}-{scenario}-{seed}'
                y, ticks, source = generate(spec, scenario, seed, plan['duration_seconds'])
                # Keep rejected raw trials as well as successful numeric results.
                np.savez_compressed(args.output/(name+'.npz'), samples=y, timestamps_us=ticks)
                trial = {'case':case,'scenario':scenario,'seed':seed,'source':source,
                         'raw_sha256':hashlib.sha256(y.tobytes()+ticks.tobytes()).hexdigest()}
                try:
                    result = compare(spec,y,ticks,profile,source)
                    trial['result_file'] = name+'.json'
                    (args.output/(name+'.json')).write_text(json.dumps(result,indent=2,allow_nan=False))
                    chosen = next(c for c in result['comparisons'] if c['selected'])
                    if scenario in ('mount_a','mount_b'):
                        expected_frequency = source['model_frequency_hz']
                        expected_damping = source['model_decay_per_second']/np.hypot(source['model_decay_per_second'],2*np.pi*expected_frequency)
                        freq_error = abs(chosen['result']['frequency_hz']-expected_frequency) if chosen['result']['frequency_hz'] is not None else None
                        damping_error = abs(chosen['result']['damping_ratio']/expected_damping-1) if chosen['result']['damping_ratio'] is not None else None
                        passed = (freq_error is not None and freq_error <= plan['truth_acceptance']['max_frequency_abs_error_hz'] and
                                  damping_error is not None and damping_error <= plan['truth_acceptance']['max_damping_relative_error'] and
                                  all(c['measurement_error_budget_passed_for_this_input'] for c in result['comparisons']))
                        trial.update(frequency_abs_error_hz=freq_error,damping_relative_error=damping_error)
                    else:
                        passed = all(c['result']['status']=='rejected' for c in result['comparisons'])
                    trial.update(passed=passed,selected=chosen['mode'],wire_bytes=[c['metrics']['wire_bytes_including_headers'] for c in result['comparisons']],
                                 results=[c['result'] for c in result['comparisons']],metrics=[c['metrics'] for c in result['comparisons']])
                except EdgeError as exc:
                    trial.update(passed=scenario=='saturation', acquisition_rejection=str(exc))
                trials.append(trial)
                (args.output/'results.json').write_text(json.dumps({'in_progress':True,'trials':trials},indent=2))
    report = {'schema':'instrumentzero.edge.confirmation-results/1','scope':'SYNTHETIC SOFTWARE CONFIRMATION',
              'plan_sha256':identity(plan),'trials':trials,'all_passed':all(t['passed'] for t in trials),
              'physical_acquisition_verified':False,'independent_physical_measurement_verified':False,
              'limits':'Frozen rules and measured host proxies only; chosen placement ties fixed edge on standard case. Host-favored cases test raw retention cost. No MCU timing/power or physical uncertainty validation.'}
    (args.output/'results.json').write_text(json.dumps(report,indent=2,allow_nan=False))
    print(json.dumps({'trials':len(trials),'all_passed':report['all_passed'],'report':str(args.output/'results.json')},indent=2))
    if not report['all_passed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
