"""Reopenable, file-only stiffness sessions using the existing analysis engine."""
from __future__ import annotations

import base64
import copy
import csv
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import stat
import tempfile

import numpy as np
import scipy

from .engine import analyze_stiffness, compile_experiment, digest
from .spec import MeasurementError, MeasurementSpec

MAX_INPUT = 2_000_000
MAX_SESSION = 16_000_000
MAX_EVENTS = 32
UNVERIFIED_CALIBRATION_BASIS = "Revised calibration values are user-declared; no revision-specific certificate is verified."


def read_file(path, limit=MAX_INPUT):
    flags = os.O_RDONLY | getattr(os, 'O_NONBLOCK', 0)
    if not hasattr(os, 'O_NOFOLLOW'):
        raise MeasurementError('Safe no-follow file access is unavailable.')
    fd = os.open(path, flags | os.O_NOFOLLOW)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise MeasurementError('Input must be a bounded regular file.')
        pieces, count = [], 0
        while True:
            part = os.read(fd, min(65536, limit - count + 1))
            if not part:
                break
            count += len(part)
            if count > limit:
                raise MeasurementError('Input exceeds its byte limit.')
            pieces.append(part)
        return b''.join(pieces)
    finally:
        os.close(fd)


def _source(data, label, kind):
    if not isinstance(data, bytes) or not data or len(data) > MAX_INPUT:
        raise MeasurementError('Source bytes must be nonempty and at most 2 MB.')
    if not isinstance(label, str) or not label.strip() or len(label) > 200:
        raise MeasurementError('Source label must contain 1–200 characters.')
    if kind not in ('json', 'csv'):
        raise MeasurementError('Only JSON and CSV sources are supported.')
    return {'label': label, 'format': kind, 'sha256': hashlib.sha256(data).hexdigest(),
            'base64': base64.b64encode(data).decode('ascii')}


def _decode(source):
    if not isinstance(source, dict) or set(source) != {'label', 'format', 'sha256', 'base64'}:
        raise MeasurementError('Invalid session source record.')
    if not isinstance(source['base64'], str) or len(source['base64']) > (MAX_INPUT + 2) // 3 * 4:
        raise MeasurementError('Invalid bounded source encoding.')
    try:
        raw = base64.b64decode(source['base64'], validate=True)
        if _source(raw, source['label'], source['format']) != source:
            raise MeasurementError('Source bytes or digest differ.')
        return raw.decode('utf-8')
    except (ValueError, UnicodeError) as exc:
        raise MeasurementError('Invalid session source encoding.') from exc


def _json_source(source):
    if source['format'] != 'json':
        raise MeasurementError('Specification and calibration must be JSON.')
    try:
        return json.loads(_decode(source), parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
    except (ValueError, TypeError) as exc:
        raise MeasurementError('Invalid source JSON.') from exc


def _rows(source):
    text = _decode(source)
    try:
        rows = json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value))) if source['format'] == 'json' else list(csv.DictReader(io.StringIO(text, newline='')))
    except (ValueError, csv.Error) as exc:
        raise MeasurementError('Invalid observation source.') from exc
    if not isinstance(rows, list) or not rows or len(rows) > 10000 or any(not isinstance(x, dict) for x in rows):
        raise MeasurementError('Observation batch must contain 1–10000 rows.')
    return rows


def _revise(spec, event):
    values = spec.to_dict()
    values['calibration'] = _json_source(event['source'])
    values['calibration_basis'] = event.get('basis', UNVERIFIED_CALIBRATION_BASIS)
    return MeasurementSpec.parse(values)


class ExperimentSession:
    """Immutable source history; all displayed analyses are replayed, not cached."""
    def __init__(self, document):
        if not isinstance(document, dict) or set(document) != {'schema', 'spec', 'events', 'sha256'} or document['schema'] != 'instrumentzero-stiffness-session-v1':
            raise MeasurementError('Unsupported session document.')
        body = {k: document[k] for k in ('schema', 'spec', 'events')}
        if not isinstance(document['sha256'], str) or document['sha256'] != digest(body):
            raise MeasurementError('Session checksum differs.')
        if not isinstance(document['events'], list) or len(document['events']) > MAX_EVENTS:
            raise MeasurementError('Session event limit exceeded.')
        spec = MeasurementSpec.parse(_json_source(document['spec']))
        if spec.domain != 'stiffness':
            raise MeasurementError('Session workflow currently supports stiffness only.')
        # Validate all sources and chronological calibration/row structure before admission.
        rows = []
        for event in document['events']:
            if (not isinstance(event, dict) or event.get('kind') not in ('observations', 'calibration')
                    or set(event) not in ({'kind', 'source'}, {'kind', 'source', 'basis'})
                    or ('basis' in event and event['kind'] != 'calibration')):
                raise MeasurementError('Invalid session event.')
            if event['kind'] == 'observations':
                rows.extend(_rows(event['source']))
                if len(rows) > 10000:
                    raise MeasurementError('Session exceeds 10000 observations.')
            else:
                spec = _revise(spec, event)
        self._document = copy.deepcopy(document)

    @classmethod
    def start(cls, spec_bytes, label):
        body = {'schema': 'instrumentzero-stiffness-session-v1', 'spec': _source(spec_bytes, label, 'json'), 'events': []}
        return cls({**body, 'sha256': digest(body)})

    @classmethod
    def load(cls, data):
        if not isinstance(data, bytes) or len(data) > MAX_SESSION:
            raise MeasurementError('Session exceeds 16 MB.')
        try:
            value = json.loads(data, parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))
        except (ValueError, UnicodeError) as exc:
            raise MeasurementError('Invalid session JSON.') from exc
        if isinstance(value, dict) and value.get('schema') == 'instrumentzero-session-export-v1':
            if set(value) != {'schema', 'session', 'review'}:
                raise MeasurementError('Invalid session export.')
            value = value['session']  # Stored review is data, never an authority.
        return cls(value)

    def to_bytes(self):
        data = (json.dumps(self._document, indent=2, allow_nan=False) + '\n').encode()
        if len(data) > MAX_SESSION:
            raise MeasurementError('Session exceeds 16 MB.')
        return data

    def append(self, kind, data, label, format='json', *, basis=None):
        if kind not in ('observations', 'calibration'):
            raise MeasurementError('Unsupported session event.')
        body = {k: copy.deepcopy(self._document[k]) for k in ('schema', 'spec', 'events')}
        event = {'kind': kind, 'source': _source(data, label, format)}
        if basis is not None:
            if kind != 'calibration':
                raise MeasurementError('Only calibration revisions may declare a basis.')
            event['basis'] = basis
        body['events'].append(event)
        return ExperimentSession({**body, 'sha256': digest(body)})

    def export_bytes(self):
        report = {'schema': 'instrumentzero-session-export-v1', 'session': copy.deepcopy(self._document),
                  'review': self.review()}
        data = (json.dumps(report, indent=2, allow_nan=False) + '\n').encode()
        if len(data) > MAX_SESSION:
            raise MeasurementError('Session export exceeds 16 MB.')
        return data

    def review(self):
        spec = MeasurementSpec.parse(_json_source(self._document['spec']))
        rows = []; sources = []; analyses = []
        for index, event in enumerate(self._document['events'], 1):
            source = event['source']
            if event['kind'] == 'observations':
                rows.extend(_rows(source)); sources.append({'label': source['label'], 'sha256': source['sha256']})
            else:
                spec = _revise(spec, event)
            if not rows:
                continue
            try:
                result = analyze_stiffness(spec, rows)
            except MeasurementError as exc:
                result = {'status': 'refused', 'reason': str(exc)}
            analyses.append({'revision': index, 'trigger': event['kind'], 'trigger_label': source['label'],
                             'observation_sources': copy.deepcopy(sources), 'observations': len(rows),
                             'calibration': spec.to_dict()['calibration'],
                             'calibration_basis': spec.calibration_basis, 'result': result})
        comparisons = []
        for before, after in zip(analyses, analyses[1:]):
            a, b = before['result'], after['result']; av = a.get('quantity', {}).get('value');bv = b.get('quantity', {}).get('value')
            comparisons.append({'from_revision': before['revision'], 'to_revision': after['revision'],
                                'trigger': after['trigger'], 'earlier_status': a['status'], 'later_status': b['status'],
                                'calibration_basis_before': before['calibration_basis'],
                                'calibration_basis_after': after['calibration_basis'],
                                'stiffness_change_n_per_m': bv - av if av is not None and bv is not None else None,
                                'uncertainty_before': a.get('quantity', {}).get('relative_uncertainty'),
                                'uncertainty_after': b.get('quantity', {}).get('relative_uncertainty'),
                                'interpretation': 'A numerical change is not independent physical validation; inspect calibration and model diagnostics.'})
        source = Path(__file__).parent
        identity = {name: hashlib.sha256((source / name).read_bytes()).hexdigest() for name in ('engine.py', 'design.py', 'spec.py', 'session.py')}
        return {'schema': 'instrumentzero-session-review-v1', 'session_sha256': self._document['sha256'],
                'spec_source': {'label': self._document['spec']['label'], 'sha256': self._document['spec']['sha256']},
                'plan': compile_experiment(spec), 'analyses': analyses, 'comparisons': comparisons,
                'environment': {'python': platform.python_version(), 'numpy': np.__version__, 'scipy': scipy.__version__, 'source_sha256': identity},
                'limitations': ['Calibration values and source labels are user-declared; no independent certificate or physical accuracy is established.',
                                'Opening and replaying this session does not acquire data or actuate hardware.',
                                'Checksums detect changes but do not authenticate a source.']}


def publish(path, data):
    path = Path(path)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name + '.', suffix='.pending', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data);stream.flush();os.fsync(stream.fileno())
        os.link(temporary, path)
    finally:
        os.unlink(temporary)
