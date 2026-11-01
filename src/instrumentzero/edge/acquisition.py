"""Consented POSIX serial acquisition and strict raw IZP1 recording import.

No camera/microphone/serial device is opened at module import or by the web preview.
"""
from __future__ import annotations

import hashlib
import json
import os
import select
import stat
import struct
import time
from pathlib import Path

import numpy as np

from .protocol import MAX_FRAME, Validator, decode
from .spec import EdgeError, compile_graph, number


def read_recording(path, spec, firmware_sha256):
    compiled = compile_graph(spec)
    if compiled['spec']['source']['adapter'] != 'zephyr_adxl345':
        raise EdgeError('IZP1 sensor recordings require the zephyr_adxl345 source adapter.')
    if len(firmware_sha256) != 64 or any(c not in '0123456789abcdef' for c in firmware_sha256):
        raise EdgeError('Provide the exact linked firmware SHA-256 (lowercase hex).')
    path = Path(path)
    if path.stat().st_size > 16*1024*1024:
        raise EdgeError('Protocol recording exceeds the 16 MiB bound.')
    raw, timestamps, validator = [], [], None
    transforms = {}
    transformed_values, transformed_times = {}, {}
    with path.open('rb') as stream:
        while prefix := stream.read(4):
            if len(prefix) != 4:
                raise EdgeError('Truncated packet length prefix.')
            n = struct.unpack('<I', prefix)[0]
            if not 84 < n <= MAX_FRAME:
                raise EdgeError('Invalid packet length in recording.')
            packet = stream.read(n)
            frame = decode(packet)
            if validator is None:
                validator = Validator(compiled, frame.session, frame.epoch)
            if frame.kind == 1:
                frame = validator.accept(packet)
                raw.append(frame.samples)
                timestamps.append(frame.timestamps_us)
            else:
                if frame.kind not in transforms:
                    transforms[frame.kind] = Validator(compiled, validator.session, validator.epoch, frame.kind)
                transforms[frame.kind].accept(packet)
                transformed_values.setdefault(frame.kind, []).append(frame.samples)
                transformed_times.setdefault(frame.kind, []).append(frame.timestamps_us)
    if not raw or validator.count < 32:
        raise EdgeError('Recording has no sufficient raw validation stream. Summaries cannot reconstruct discarded samples.')
    values, ticks = np.concatenate(raw), np.concatenate(timestamps)
    device_checks = []
    for kind in transforms:
        actual = np.concatenate(transformed_values[kind])
        actual_ticks = np.concatenate(transformed_times[kind])
        device_checks.append(_check_device_stream(compiled, values, ticks, actual, actual_ticks, kind))
    return values, ticks, {
        'source_kind': 'user_supplied_sensor_recording', 'file_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'firmware_sha256': firmware_sha256, 'firmware_identity_basis': 'user-declared image hash; not device-attested',
        'session': validator.session, 'epoch': validator.epoch, 'independent_physical_reference': False,
        'timestamp_location': 'Zephyr driver-thread callback before sample fetch; not physical sample aperture',
        'hardware_verified': False, 'device_processing_checks': device_checks,
        'device_processing_scope': 'Consistency of supplied transformed bytes against retained raw input. No physical operation or attestation inferred.'}


def _check_device_stream(compiled, raw, raw_ticks, actual, actual_ticks, kind):
    from scipy import signal

    from .estimator import ringdown
    from .runtime import reference_samples
    s, d = compiled['spec'], compiled['spec']['dsp']
    expected = ((raw.astype(np.float64)-s['calibration']['offset'])*s['calibration']['scale']
                if kind == 2 else reference_samples(compiled, raw))
    expected_ticks = raw_ticks if kind == 2 else raw_ticks[d['decimation']-1::d['decimation']]
    if actual.shape != expected.shape or not np.array_equal(actual_ticks, expected_ticks):
        raise EdgeError('Device transformed stream has missing samples or mismatched timestamp alignment.')
    relative_error = float(np.linalg.norm(actual-expected)/max(np.linalg.norm(expected),1e-12))
    if relative_error > d['max_numeric_relative_error']:
        raise EdgeError(f'Device transformed waveform exceeds declared numeric error budget ({relative_error:.6g}).')
    rate = (len(raw)-1)*1e6/(int(raw_ticks[-1])-int(raw_ticks[0]))/d['decimation']
    ids = np.arange(d['decimation']-1,len(raw),d['decimation'])
    valid = ids >= d['taps']-1
    analyzed = (signal.lfilter(compiled['coefficients'],[1.],actual.astype(float),axis=0)[d['decimation']-1::d['decimation']]
                if kind == 2 else actual)
    reference = reference_samples(compiled,raw)
    settings = s['estimator']
    ch = s['source']['channels'].index(settings['channel'])
    clock = s['source']['clock_uncertainty_ppm']
    estimate = ringdown(analyzed[valid,ch],rate,settings,clock)
    ref_fit = ringdown(reference[valid,ch],rate,settings,clock)
    f, fref = estimate['frequency_hz'], ref_fit['frequency_hz']
    damping, damping_ref = estimate['damping_ratio'], ref_fit['damping_ratio']
    freq_error = abs(f-fref) if f is not None and fref is not None else None
    damping_error = abs(damping/damping_ref-1) if damping is not None and damping_ref is not None else None
    if (estimate['status'] != ref_fit['status'] or (f is None) != (fref is None) or
            (damping is None) != (damping_ref is None) or
            (freq_error is not None and freq_error > settings['max_frequency_error_hz']) or
            (damping_error is not None and damping_error > settings['max_damping_relative_error'])):
        raise EdgeError('Device transformed stream does not preserve identifiable frequency/damping within declared budgets.')
    return {'kind':kind,'samples':len(actual),'waveform_relative_l2_error':relative_error,
            'frequency_disagreement_hz':freq_error,'damping_relative_disagreement':damping_error,
            'supplied_stream_numerical_consistency_passed':True,'physical_operation_verified':False}


class SerialPort:
    """Own exactly one descriptor; release it even when setup or capture fails."""
    def __init__(self, device):
        self.device = device
        self.fd = None
        self.old_attributes = None
        self.started = False
        self.bytes_sent = 0

    def __enter__(self):
        import termios
        import tty
        resolved = Path(self.device).resolve(strict=True)
        if not resolved.is_relative_to('/dev') or not stat.S_ISCHR(resolved.stat().st_mode):
            raise EdgeError('Serial device must resolve to a character device under /dev/.')
        try:
            self.fd = os.open(resolved, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK | os.O_NOFOLLOW)
            if not stat.S_ISCHR(os.fstat(self.fd).st_mode) or not os.isatty(self.fd):
                raise EdgeError('The opened character device is not a TTY serial endpoint.')
            self.old_attributes = termios.tcgetattr(self.fd)
            tty.setraw(self.fd)
            attrs = termios.tcgetattr(self.fd)
            attrs[4] = attrs[5] = termios.B115200
            termios.tcsetattr(self.fd, termios.TCSANOW, attrs)
            termios.tcflush(self.fd, termios.TCIFLUSH)
            return self
        except BaseException:
            if self.fd is not None:
                self.__exit__(None,None,None)
            raise

    def write(self, data):
        written = os.write(self.fd, data)
        self.bytes_sent += written
        if data == b'G' and written == 1:
            self.started = True
        return written

    def read(self, timeout):
        ready, _, _ = select.select([self.fd],[],[],timeout)
        return os.read(self.fd,8192) if ready else None

    def __exit__(self, *_):
        import termios
        if self.fd is None:
            return
        try:
            if self.started:
                self.write(b'S')
        except OSError:
            pass
        try:
            if self.old_attributes is not None:
                termios.tcsetattr(self.fd,termios.TCSANOW,self.old_attributes)
        except OSError:
            pass
        finally:
            os.close(self.fd)
            self.fd = None


def capture(spec, device, seconds, output, consent):
    if not consent:
        raise EdgeError('Serial capture requires explicit recording consent.')
    compiled = compile_graph(spec)
    if compiled['spec']['source']['adapter'] != 'zephyr_adxl345':
        raise EdgeError('Capture requires the provisional zephyr_adxl345 binding.')
    number(seconds, 1, 30, 'capture duration')
    if not str(device).startswith('/dev/'):
        raise EdgeError('A serial device must be explicitly named under /dev/.')
    sidecar = Path(str(output)+'.json')
    metadata = {'schema':'instrumentzero.edge.capture/1','spec':compiled['spec'],
                'spec_sha256':compiled['spec_sha256'],'requested_seconds':seconds,
                'consent_confirmed':True,'firmware_sha256':None,'firmware_identity_basis':'unknown at capture',
                'physical_acceptance_verified':False,'outcome':'starting'}
    with Path(output).open('xb') as recording, sidecar.open('x+') as manifest:
        def save_manifest():
            manifest.seek(0)
            manifest.write(json.dumps(metadata,indent=2,allow_nan=False))
            manifest.truncate()
            manifest.flush()
            os.fsync(manifest.fileno())
        save_manifest()
        try:
            with SerialPort(device) as port:
                port.write(b'G')
                deadline = time.monotonic()+seconds
                heartbeat = 0
                received_at = time.monotonic()
                received = 0
                while time.monotonic() < deadline:
                    now = time.monotonic()
                    if now >= heartbeat:
                        port.write(b'K')
                        heartbeat = now+.5
                    data = port.read(min(.1,max(0.,deadline-now)))
                    if data is not None:
                        if not data:
                            raise EdgeError('Sensor disconnected; partial bytes retained in the trial file.')
                        recording.write(data)
                        received += len(data)
                        received_at = now
                        if received > 16*1024*1024:
                            raise EdgeError('Capture allocation bound reached; partial bytes retained.')
                    if now-received_at > 2:
                        raise EdgeError('No sensor packets for two seconds; partial trial retained.')
                port.write(b'S')
                until = time.monotonic()+.4
                while time.monotonic() < until:
                    data = port.read(.05)
                    if data is not None:
                        if not data:
                            break
                        recording.write(data)
                        received += len(data)
                        if received > 16*1024*1024:
                            raise EdgeError('Capture bound reached during stop; partial trial retained.')
                recording.flush()
                os.fsync(recording.fileno())
            metadata['outcome']='captured_not_validated'
        except BaseException as exc:
            metadata.update(outcome='cancelled' if isinstance(exc,KeyboardInterrupt) else 'failed',
                            error_type=type(exc).__name__,error=str(exc)[:1000])
            raise
        finally:
            recording.flush()
            os.fsync(recording.fileno())
            metadata['received_bytes']=recording.tell()
            save_manifest()
    return {'recording': str(output), 'bytes': Path(output).stat().st_size, 'host_control_bytes_sent': port.bytes_sent,
            'status': 'captured bytes; validate with edge protocol before using any result',
            'hardware_acceptance': 'unverified until executed on a supported physical setup'}
