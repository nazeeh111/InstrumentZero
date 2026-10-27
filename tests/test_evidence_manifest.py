"""Committed validation claims must correspond to the actual checked source."""
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
def test_retained_evidence_is_tied_to_current_source(relative):
    result = json.loads((ROOT/relative).read_text())
    if relative.endswith('comparison.json'):
        checks = {'src/instrumentzero/replay.py': result['replay_source_sha256'],
                  'scripts/validate_replay.py': result['script_sha256']}
    elif 'ptb-validation' in relative:
        checks = result['analysis_source_sha256']
    else:
        checks = result['source_sha256']
    assert checks
    for source, expected in checks.items():
        assert hashlib.sha256((ROOT/source).read_bytes()).hexdigest() == expected, source
