"""Verify retained evidence against its recorded historical or unchanged source."""
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]


@pytest.mark.parametrize('relative', [
    'examples/acoustic-acceptance-v0.2/results.json',
    'examples/acquisition-acceptance-v0.2/results.json',
    'examples/ptb-validation-v0.2/results.json',
    'examples/replay-validation/comparison.json',
])
def test_retained_evidence_is_tied_to_recorded_source(relative):
    result = json.loads((ROOT/relative).read_text())
    if relative.endswith('comparison.json'):
        checks = {'src/instrumentzero/replay.py': result['replay_source_sha256'],
                  'scripts/validate_replay.py': result['script_sha256']}
    elif 'ptb-validation' in relative:
        checks = result['analysis_source_sha256']
    else:
        checks = result['source_sha256']
    assert checks
    if relative == 'examples/acquisition-acceptance-v0.2/results.json':
        assert set(checks) == {
            'src/instrumentzero/web/acquisition.js',
            'src/instrumentzero/web/app.js',
            'tests/browser-acquisition.mjs',
            'scripts/validate_acquisition.py',
        }
    for source, expected in checks.items():
        # The v0.2 acquisition receipt predates the current responsive UI.
        # Its original app is retained byte-for-byte; current UI behavior is
        # exercised separately by tests/browser-acquisition.mjs.
        historical = {
            'src/instrumentzero/web/app.js': 'app.js',
            'scripts/validate_acquisition.py': 'validate_acquisition.py',
        }
        if relative == 'examples/acquisition-acceptance-v0.2/results.json' and source in historical:
            path = ROOT/'examples/acquisition-acceptance-v0.2/source-snapshot'/historical[source]
        else:
            path = ROOT/source
        assert hashlib.sha256(path.read_bytes()).hexdigest() == expected, source
