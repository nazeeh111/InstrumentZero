#!/usr/bin/env python3
"""Capture reproducible acceptance evidence from shared production browser code.

Requires Node.js, no npm packages, browser permissions, microphones or cameras.
The Node runner exercises generated media and mocked asynchronous device APIs.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('Use a fresh output directory to preserve earlier acceptance evidence')
    root = Path(__file__).resolve().parents[1]
    run = subprocess.run(['node', '--test', '--test-reporter=tap', 'tests/browser-acquisition.mjs'],
                         cwd=root, capture_output=True, text=True, check=True)
    counts = {}
    for key in ('tests', 'pass', 'fail', 'cancelled', 'skipped', 'todo'):
        match = re.search(rf'^# {key}\s+(\d+)\s*$', run.stdout, re.MULTILINE)
        if not match:
            raise RuntimeError(f'The Node acceptance transcript did not report {key}')
        counts[key] = int(match.group(1))
    if counts['fail'] or counts['cancelled'] or counts['skipped'] or counts['pass'] != counts['tests']:
        raise RuntimeError('All required acquisition checks must run and pass')
    files = ['src/instrumentzero/web/acquisition.js', 'src/instrumentzero/web/app.js',
             'tests/browser-acquisition.mjs', 'scripts/validate_acquisition.py']
    payload = {'evidence_kind': 'synthetic_media_and_mocked_browser_software_acceptance',
               'live_hardware_run': False, 'tests_passed': counts['pass'], 'counts': counts,
               'node_version': subprocess.check_output(['node', '--version'], text=True).strip(),
               'source_sha256': {name: hashlib.sha256((root/name).read_bytes()).hexdigest() for name in files},
               'summary': 'Shared marker/audio transforms and actual Lab capture entrypoints were exercised. '
               'Tests include stop/cancellation races, stale permissions, domain changes, lost markers, '
               'known synthetic positions, mono/stereo preparation and duration limits.',
               'limits': ['Synthetic frames and tones are not new physical measurements.',
                          'Mocked devices do not establish operating-system permission or hardware behavior.',
                          'Node audio mocks test the WebAudio adapter contract, not browser anti-alias filter quality.',
                          'Optical calibration, physical sample clocks, room response and independent physical accuracy remain unverified.']}
    args.output.mkdir(parents=True)
    (args.output/'results.json').write_text(json.dumps(payload, indent=2)+'\n')
    (args.output/'node-test-transcript.tap').write_text(run.stdout)
    print(json.dumps({'tests_passed': counts['pass'], 'output': str(args.output), 'live_hardware_run': False}))


if __name__ == '__main__':
    main()
