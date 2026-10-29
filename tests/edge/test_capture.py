import itertools
import json

import pytest

from instrumentzero.edge import acquisition
from instrumentzero.edge.spec import EdgeError, default_spec


def sensor_spec():
    s = default_spec()
    s['source']['adapter'] = 'zephyr_adxl345'
    return s


def test_serial_cleanup_cannot_overwrite_a_regular_file(tmp_path):
    target = tmp_path/'keep.txt'
    original = b'KEEP-THIS-BYTE'
    target.write_bytes(original)
    with pytest.raises(EdgeError, match='character device'):
        with acquisition.SerialPort('/dev/..'+str(target)):
            pytest.fail('Regular file was accepted as a serial port')
    assert target.read_bytes() == original


def test_cancelled_capture_sends_stop_closes_and_retains_config_and_partial_bytes(tmp_path, monkeypatch):
    class FakeSerial:
        def __init__(self):
            self.commands = []
            self.closed = False
            self.reads = 0
            self.bytes_sent = 0
        def __enter__(self):
            return self
        def write(self, command):
            self.commands.append(command)
            self.bytes_sent += len(command)
            return len(command)
        def read(self, timeout):
            self.reads += 1
            if self.reads == 1:
                return b'partial-packet'
            raise KeyboardInterrupt()
        def __exit__(self, *_):
            self.write(b'S')
            self.closed = True
    serial = FakeSerial()
    monkeypatch.setattr(acquisition, 'SerialPort', lambda device: serial)
    ticks = itertools.count(0, .01)
    monkeypatch.setattr(acquisition.time, 'monotonic', lambda: next(ticks))
    output = tmp_path/'trial.izp'
    with pytest.raises(KeyboardInterrupt):
        acquisition.capture(sensor_spec(), '/dev/EXPLICIT-FAKE', 8, output, True)
    assert serial.commands[0] == b'G' and serial.commands[-1] == b'S' and serial.closed
    assert output.read_bytes() == b'partial-packet'
    metadata = json.loads((tmp_path/'trial.izp.json').read_text())
    assert metadata['outcome'] == 'cancelled'
    assert metadata['spec'] == sensor_spec()
    assert metadata['received_bytes'] == len(b'partial-packet')
    assert metadata['firmware_sha256'] is None
    with pytest.raises(FileExistsError):
        acquisition.capture(sensor_spec(), '/dev/EXPLICIT-FAKE', 8, output, True)


def test_missing_consent_never_opens_a_device_or_creates_a_trial(tmp_path, monkeypatch):
    monkeypatch.setattr(acquisition, 'SerialPort', lambda device: pytest.fail('Opened without consent'))
    output = tmp_path/'not-created.izp'
    with pytest.raises(EdgeError, match='consent'):
        acquisition.capture(sensor_spec(), '/dev/EXPLICIT-FAKE', 8, output, False)
    assert not output.exists()
