import itertools
import json

import pytest
from test_control import ack_bytes

from instrumentzero.edge import acquisition
from instrumentzero.edge.spec import EdgeError, default_spec


def sensor_spec():
    s = default_spec()
    s["source"]["adapter"] = "zephyr_adxl345"
    s["resources"]["edge_memory_bytes"] = 40960
    return s


def test_serial_cleanup_cannot_overwrite_a_regular_file(tmp_path):
    target = tmp_path / "keep.txt"
    original = b"KEEP-THIS-BYTE"
    target.write_bytes(original)
    with pytest.raises(EdgeError, match="character device"):
        with acquisition.SerialPort("/dev/.." + str(target)):
            pytest.fail("Regular file was accepted as a serial port")
    assert target.read_bytes() == original


def test_cancelled_capture_sends_stop_closes_and_retains_config_and_partial_bytes(tmp_path, monkeypatch):
    class FakeSerial:
        def __init__(self):
            self.commands = []
            self.closed = False
            self.reads = 0
            self.ack = None
            self.bytes_sent = 0

        def __enter__(self):
            return self

        def write(self, command):
            self.commands.append(command)
            if command.startswith(b"C"):
                self.ack = ack_bytes(command)
            self.bytes_sent += len(command)
            return len(command)

        def read(self, timeout):
            if self.ack is not None:
                ack, self.ack = self.ack, None
                return ack
            self.reads += 1
            if self.reads == 1:
                return b"partial-packet"
            raise KeyboardInterrupt()

        def __exit__(self, *_):
            self.write(b"S")
            self.closed = True

    serial = FakeSerial()
    monkeypatch.setattr(acquisition, "SerialPort", lambda device: serial)
    ticks = itertools.count(0, 0.01)
    monkeypatch.setattr(acquisition.time, "monotonic", lambda: next(ticks))
    output = tmp_path / "trial.izp"
    with pytest.raises(KeyboardInterrupt):
        acquisition.capture(sensor_spec(), "/dev/EXPLICIT-FAKE", 8, output, True)
    assert (
        serial.commands[0] == b"S"
        and b"G" in serial.commands
        and serial.commands[-1] == b"S"
        and serial.closed
    )
    assert output.read_bytes() == b"partial-packet"
    metadata = json.loads((tmp_path / "trial.izp.json").read_text())
    assert metadata["outcome"] == "cancelled"
    assert metadata["spec"] == sensor_spec()
    assert metadata["received_bytes"] == len(b"partial-packet")
    assert metadata["firmware_sha256"] is None
    with pytest.raises(FileExistsError):
        acquisition.capture(sensor_spec(), "/dev/EXPLICIT-FAKE", 8, output, True)


def test_missing_consent_never_opens_a_device_or_creates_a_trial(tmp_path, monkeypatch):
    monkeypatch.setattr(acquisition, "SerialPort", lambda device: pytest.fail("Opened without consent"))
    output = tmp_path / "not-created.izp"
    with pytest.raises(EdgeError, match="consent"):
        acquisition.capture(sensor_spec(), "/dev/EXPLICIT-FAKE", 8, output, False)
    assert not output.exists()


def test_explicit_uart_profile_is_115200_8n1_without_flow_control_and_is_restored(monkeypatch):
    import copy
    import stat
    import termios
    from types import SimpleNamespace

    flags = termios.CSTOPB | termios.PARENB | getattr(termios, "CRTSCTS", 0)
    input_flags = sum(
        getattr(termios, name, 0)
        for name in ("INLCR", "IGNCR", "PARMRK", "IXOFF", "IXANY", "ISTRIP", "ICRNL", "IXON")
    )
    local_flags = sum(getattr(termios, name, 0) for name in ("ECHONL", "ECHO", "ICANON", "ISIG", "IEXTEN"))
    original = [input_flags, termios.OPOST, flags, local_flags, termios.B9600, termios.B9600, [b"\0"] * 32]
    configured = []
    monkeypatch.setattr(acquisition.os, "open", lambda *args: 424242)
    monkeypatch.setattr(acquisition.os, "fstat", lambda _: SimpleNamespace(st_mode=stat.S_IFCHR))
    monkeypatch.setattr(acquisition.os, "isatty", lambda _: True)
    monkeypatch.setattr(acquisition.os, "close", lambda _: None)
    monkeypatch.setattr(termios, "tcgetattr", lambda _: copy.deepcopy(original))
    monkeypatch.setattr(termios, "tcsetattr", lambda fd, when, attrs: configured.append(copy.deepcopy(attrs)))
    monkeypatch.setattr(termios, "tcflush", lambda *args: None)
    # Only /dev/null metadata is inspected. os.open is replaced before entry.
    with acquisition.SerialPort("/dev/null"):
        pass
    applied = configured[0]
    assert applied[0] & input_flags == 0 and applied[1] & termios.OPOST == 0 and applied[3] & local_flags == 0
    assert applied[6][termios.VMIN] == 1 and applied[6][termios.VTIME] == 0
    assert applied[4:6] == [termios.B115200] * 2
    assert applied[2] & termios.CSIZE == termios.CS8
    assert not applied[2] & (termios.CSTOPB | termios.PARENB | getattr(termios, "CRTSCTS", 0))
    assert configured[-1] == original


def test_failed_native_capture_is_not_promoted_from_an_intact_packet_prefix(tmp_path):
    import uuid

    import numpy as np

    from instrumentzero.edge.acquisition import read_recording
    from instrumentzero.edge.runtime import packets
    from instrumentzero.edge.spec import compile_graph

    spec = sensor_spec()
    compiled = compile_graph(spec)
    frames = list(packets(np.zeros((64, 1), np.float32), np.arange(64) * 2500, compiled, str(uuid.uuid4())))
    import struct

    recording = tmp_path / "prefix.izp"
    recording.write_bytes(b"".join(struct.pack("<I", len(frame)) + frame for frame in frames))
    metadata = {
        "schema": "instrumentzero.edge.capture/1",
        "spec": spec,
        "spec_sha256": compiled["spec_sha256"],
        "received_bytes": recording.stat().st_size,
        "requested_seconds": 8,
        "outcome": "failed",
        "error_type": "OSError",
    }
    sidecar = tmp_path / "prefix.izp.json"
    for outcome in ("failed", "cancelled", "starting", "unknown"):
        metadata["outcome"] = outcome
        sidecar.write_text(json.dumps(metadata))
        with pytest.raises(EdgeError, match="native capture"):
            read_recording(recording, spec, "ab" * 32)
    metadata.pop("error_type")
    metadata["outcome"] = "captured_not_validated"
    sidecar.write_text(json.dumps(metadata))
    _, _, source = read_recording(recording, spec, "ab" * 32)
    assert source["native_capture_metadata"] == metadata
    sidecar.unlink()  # This test's disposable sidecar; generic recording remains supported.
    assert read_recording(recording, spec, "ab" * 32)[2]["native_capture_metadata"] is None
