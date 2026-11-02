import ctypes
import json
import shutil
import struct
import subprocess
import time
import uuid
import zlib
from pathlib import Path

import numpy as np
import pytest

from instrumentzero.edge.control import (
    ACK,
    CONFIG,
    DeviceController,
    configuration,
    decode_ack,
    decode_configuration,
    write_all,
)
from instrumentzero.edge.spec import EdgeError, compile_graph, default_spec

ROOT = Path(__file__).resolve().parents[2]


class Config(ctypes.Structure):
    _fields_ = [
        ("request_id", ctypes.c_uint32),
        ("rate_hz", ctypes.c_uint32),
        ("flags", ctypes.c_uint16),
        ("block_samples", ctypes.c_uint16),
        ("queue_blocks", ctypes.c_uint16),
        ("taps", ctypes.c_uint16),
        ("decimation", ctypes.c_uint8),
        ("mode", ctypes.c_uint8),
        ("spec_sha256", ctypes.c_uint8 * 32),
        ("scale", ctypes.c_float),
        ("offset", ctypes.c_float),
        ("coefficients", ctypes.c_float * 255),
    ]


class Guard(ctypes.Structure):
    _fields_ = [("epoch", ctypes.c_uint32), ("armed", ctypes.c_uint8)]


@pytest.fixture(scope="module")
def control_library(tmp_path_factory):
    folder = tmp_path_factory.mktemp("native-control")
    binary = folder / "control.so"
    src = ROOT / "src/instrumentzero/edge/control"
    subprocess.run(
        [
            shutil.which("clang") or "cc",
            "-std=c11",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-shared",
            "-fPIC",
            str(src / "iz_control.c"),
            "-o",
            str(binary),
        ],
        check=True,
    )
    lib = ctypes.CDLL(str(binary))
    lib.iz_config_decode.argtypes = [
        ctypes.POINTER(Config),
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_uint16,
        ctypes.c_uint16,
    ]
    lib.iz_control_stage.argtypes = [
        ctypes.POINTER(Guard),
        ctypes.POINTER(Config),
        ctypes.c_void_p,
        ctypes.c_size_t,
        ctypes.c_uint16,
        ctypes.c_uint16,
    ]
    lib.iz_control_start.argtypes = [ctypes.POINTER(Guard)]
    lib.iz_control_stop.argtypes = [ctypes.POINTER(Guard)]
    lib.iz_config_ack.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(Config),
        ctypes.c_uint8,
        ctypes.c_uint32,
        ctypes.c_void_p,
    ]
    return lib


def sensor_spec():
    spec = default_spec()
    spec["source"]["adapter"] = "zephyr_adxl345"
    spec["resources"]["edge_memory_bytes"] = 40960
    return spec


def repair_crc(request):
    request = bytearray(request)
    request[-4:] = struct.pack("<I", zlib.crc32(request[3:-4]))
    return bytes(request)


def ack_bytes(request, epoch=1, session=None, status=0):
    c = decode_configuration(request)
    sid = uuid.UUID(session).bytes if session else uuid.uuid4().bytes
    data = ACK.pack(
        b"IZA1",
        1,
        status,
        ("raw_host", "calibrated_edge", "filtered_edge").index(c["placement"]) + 256 * c["raw_validation"],
        c["request_id"],
        epoch,
        sid,
        bytes.fromhex(c["spec_sha256"]),
        0,
    )
    return data[:-4] + struct.pack("<I", zlib.crc32(data[:-4]))


@pytest.mark.parametrize("mode", ["raw_host", "calibrated_edge", "filtered_edge"])
def test_python_configuration_c_parser_and_ack_roundtrip(control_library, mode):
    spec = sensor_spec()
    spec["resources"]["link_bytes_per_second"] = 10000
    spec["calibration"].update(scale=[-1.25], offset=[0.125])
    request, compiled = configuration(spec, mode, 0x4743534B)  # Includes command characters in payload.
    cfg = Config()
    assert control_library.iz_config_decode(ctypes.byref(cfg), request[3:], len(request) - 3, 64, 4) == 0
    assert (cfg.request_id, cfg.mode, cfg.scale, cfg.offset) == (
        0x4743534B,
        ("raw_host", "calibrated_edge", "filtered_edge").index(mode),
        -1.25,
        0.125,
    )
    assert np.array_equal(np.ctypeslib.as_array(cfg.coefficients)[: cfg.taps], compiled["coefficients"])
    reply = ctypes.create_string_buffer(ACK.size)
    sid = uuid.uuid4().bytes
    control_library.iz_config_ack(reply, ctypes.byref(cfg), 0, 19, sid)
    accepted = decode_ack(reply.raw)
    assert accepted["epoch"] == 19 and accepted["session"] == str(uuid.UUID(bytes=sid))
    assert accepted["spec_sha256"] == compiled["spec_sha256"] and accepted["placement"] == mode


@pytest.mark.parametrize(
    "field,offset,data",
    [
        ("version", 7, b"\2"),
        ("opcode", 8, b"\2"),
        ("flags", 9, b"\2\0"),
        ("rate", 15, struct.pack("<I", 333)),
        ("block", 19, struct.pack("<H", 63)),
        ("queue", 21, struct.pack("<H", 5)),
        ("taps", 23, struct.pack("<H", 256)),
        ("decimation", 25, b"\3"),
        ("mode", 26, b"\3"),
        ("scale", 59, struct.pack("<f", 0)),
        ("offset", 63, struct.pack("<f", float("nan"))),
        ("reserved", 67, b"\1"),
        ("coefficient", 3 + CONFIG.size, struct.pack("<f", float("inf"))),
    ],
)
def test_crc_valid_invalid_fields_never_mutate_c_configuration(control_library, field, offset, data):
    request, _ = configuration(sensor_spec(), request_id=9)
    bad = bytearray(request)
    bad[offset : offset + len(data)] = data
    bad = repair_crc(bad)
    cfg = Config()
    ctypes.memset(ctypes.byref(cfg), 0x5A, ctypes.sizeof(cfg))
    before = bytes(cfg)
    assert control_library.iz_config_decode(ctypes.byref(cfg), bad[3:], len(bad) - 3, 64, 4) == 1, field
    assert bytes(cfg) == before
    if field not in ("block", "queue"):
        with pytest.raises(EdgeError):
            decode_configuration(bad)
    else:
        # A different firmware envelope could support these globally valid sizes.
        assert (
            decode_configuration(bad)["block_samples"] != 64 or decode_configuration(bad)["queue_blocks"] != 4
        )


def test_rejected_truncated_config_disarms_and_epoch_overflow_is_closed(control_library):
    request, _ = configuration(sensor_spec(), request_id=42)
    guard, cfg = Guard(), Config()
    assert control_library.iz_control_start(ctypes.byref(guard)) == 1
    assert (
        control_library.iz_control_stage(
            ctypes.byref(guard), ctypes.byref(cfg), request[3:], len(request) - 3, 64, 4
        )
        == 0
    )
    assert guard.armed and guard.epoch == 1
    for n in (0, 1, 67, len(request) - 4):
        before = bytes(cfg)
        assert (
            control_library.iz_control_stage(ctypes.byref(guard), ctypes.byref(cfg), request[3:], n, 64, 4)
            == 1
        )
        assert bytes(cfg) == before and not guard.armed and guard.epoch == 1
        assert control_library.iz_control_start(ctypes.byref(guard)) == 1
    assert (
        control_library.iz_control_stage(
            ctypes.byref(guard), ctypes.byref(cfg), request[3:], len(request) - 3, 64, 4
        )
        == 0
    )
    assert guard.epoch == 2 and control_library.iz_control_start(ctypes.byref(guard)) == 0
    assert control_library.iz_control_start(ctypes.byref(guard)) == 1
    guard.epoch = 0xFFFFFFFF
    assert (
        control_library.iz_control_stage(
            ctypes.byref(guard), ctypes.byref(cfg), request[3:], len(request) - 3, 64, 4
        )
        == 3
    )
    assert not guard.armed


class NativeDevicePort:
    """Serial test double executes the actual firmware C parser and guard."""

    def __init__(self, lib):
        self.lib = lib
        self.guard = Guard()
        self.config = Config()
        self.pending = bytearray()
        self.reply = bytearray()
        self.started = False
        self.starts = []
        self.bytes_sent = 0
        self.wire = bytearray()

    def write(self, data):
        data = data[:7]  # Exercise partial POSIX writes across binary boundaries.
        self.bytes_sent += len(data)
        self.wire.extend(data)
        self.pending.extend(data)
        while self.pending:
            if self.pending[0] == ord("C"):
                if len(self.pending) < 3:
                    break
                n = struct.unpack_from("<H", self.pending, 1)[0]
                if len(self.pending) < n + 3:
                    break
                body = bytes(self.pending[3 : n + 3])
                del self.pending[: n + 3]
                status = self.lib.iz_control_stage(
                    ctypes.byref(self.guard), ctypes.byref(self.config), body, n, 64, 4
                )
                ack = ctypes.create_string_buffer(ACK.size)
                self.lib.iz_config_ack(
                    ack, ctypes.byref(self.config), status, self.guard.epoch, uuid.uuid4().bytes
                )
                self.reply.extend(ack.raw)
            else:
                command = self.pending.pop(0)
                if command == ord("S"):
                    self.lib.iz_control_stop(ctypes.byref(self.guard))
                elif command == ord("G") and self.lib.iz_control_start(ctypes.byref(self.guard)) == 0:
                    self.starts.append(
                        (self.guard.epoch, self.config.rate_hz, bytes(self.config.spec_sha256))
                    )
        return len(data)

    def read(self, timeout):
        if not self.reply:
            return None
        result = bytes(self.reply[:13])
        del self.reply[:13]
        return result


def test_same_open_port_reconfigures_only_after_matching_ack_and_invalidates_start(control_library):
    port = NativeDevicePort(control_library)
    controller = DeviceController(port)
    with pytest.raises(EdgeError, match="acknowledg|accepted"):
        controller.start()
    spec = sensor_spec()
    first = controller.configure(spec)
    controller.start()
    spec["calibration"].update(id="changed orientation", scale=[-2.0])
    spec["source"]["rate_hz"] = 200
    spec["dsp"].update(decimation=2)
    second = controller.configure(spec)
    controller.start()
    assert first["accepted"]["session"] != second["accepted"]["session"]
    assert [x[:2] for x in port.starts] == [(1, 400), (2, 200)]
    assert port.starts[0][2] != port.starts[1][2]
    controller.stop()
    with pytest.raises(EdgeError):
        controller.start()
    assert not port.guard.armed


@pytest.mark.parametrize(
    "fault", ["timeout", "stale", "wrong_hash", "bad_crc", "reject", "disconnect", "trailing"]
)
def test_unaccepted_control_response_never_sends_start(fault, monkeypatch):
    class Port:
        started = False
        bytes_sent = 0

        def __init__(self):
            self.commands = []
            self.reply = b""

        def write(self, data):
            self.commands.append(data)
            if data.startswith(b"C"):
                reply = ack_bytes(data, status=1 if fault == "reject" else 0)
                if fault == "stale":
                    reply = reply[:8] + struct.pack("<I", 0) + reply[12:-4] + b"\0" * 4
                if fault == "wrong_hash":
                    reply = reply[:32] + b"\0" * 32 + reply[-4:]
                if fault in ("stale", "wrong_hash"):
                    reply = reply[:-4] + struct.pack("<I", zlib.crc32(reply[:-4]))
                if fault == "bad_crc":
                    reply = reply[:-1] + bytes([reply[-1] ^ 1])
                if fault == "trailing":
                    reply += b"unrequested-data"
                self.reply = reply if fault != "timeout" else b""
            return len(data)

        def read(self, timeout):
            if fault == "disconnect":
                return b""
            reply = self.reply
            self.reply = b""
            return reply or None

    port = Port()
    clock = iter(np.arange(0, 20, 0.01))
    monkeypatch.setattr(time, "monotonic", lambda: next(clock))
    with pytest.raises(EdgeError):
        DeviceController(port).configure(sensor_spec(), timeout=0.5)
    assert b"G" not in port.commands and port.commands[-1] == b"S"


def test_write_failure_is_bounded_and_zero_scale_rounding_is_rejected():
    spec = sensor_spec()
    spec["calibration"]["scale"] = [1e-60]
    with pytest.raises(EdgeError, match="float32"):
        configuration(spec)

    class Port:
        def write(self, data):
            return 0

        def read(self, timeout):
            return None

    with pytest.raises(EdgeError, match="timed out"):
        write_all(Port(), b"G", time.monotonic() - 0.01)


def test_control_allocation_reserve_applies_to_raw_device_mode():
    from instrumentzero.edge.planner import measure_costs, plan
    from instrumentzero.edge.protocol import CONTROL_RESERVE_BYTES

    simulated = default_spec()
    device = sensor_spec()
    a = compile_graph(simulated)
    b = compile_graph(device)
    host_ram = plan(a, measure_costs(a))["candidates"][0]["reserved_edge_memory_bytes"]
    device_ram = plan(b, measure_costs(b))["candidates"][0]["reserved_edge_memory_bytes"]
    assert device_ram - host_ram == CONTROL_RESERVE_BYTES + measure_costs(b)["state_bytes"]
    assert ctypes.sizeof(Config) * 2 + 1092 + 68 + 2060 + 8 + 16 <= CONTROL_RESERVE_BYTES


def test_cancel_after_ack_before_start_disarms_native_guard_and_closes(
    tmp_path, monkeypatch, control_library
):
    from instrumentzero.edge import acquisition

    cleanup = acquisition.SerialPort.__exit__

    class Port(NativeDevicePort):
        old_attributes = None

        def __enter__(self):
            self.fd = 424242
            return self

        def __exit__(self, *args):
            cleanup(self, *args)

    port = Port(control_library)
    monkeypatch.setattr(acquisition, "SerialPort", lambda device: port)
    fsync = acquisition.os.fsync
    calls = 0

    def fail_after_ack(fd):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("Injected post-ack/pre-start save failure")
        return fsync(fd)

    closed = []
    monkeypatch.setattr(acquisition.os, "fsync", fail_after_ack)
    real_close = acquisition.os.close

    def close_owned(fd):
        if fd == 424242:
            closed.append(fd)
        else:
            real_close(fd)

    monkeypatch.setattr(acquisition.os, "close", close_owned)
    output = tmp_path / "cancelled.izp"
    with pytest.raises(OSError, match="post-ack"):
        acquisition.capture(sensor_spec(), "/dev/EXPLICIT-FAKE", 8, output, True)
    assert not port.guard.armed and not port.starts and closed == [424242]
    assert port.wire[-1:] == b"S" and output.read_bytes() == b""
    assert json.loads(Path(str(output) + ".json").read_text())["outcome"] == "failed"


@pytest.mark.parametrize("field", ["accepted", "configuration_hex", "acknowledgement_hex"])
def test_missing_control_receipt_fields_are_contract_errors(field):
    from instrumentzero.edge.control import validate_receipt

    receipt = {"accepted": {}, "configuration_hex": "", "acknowledgement_hex": ""}
    del receipt[field]
    with pytest.raises(EdgeError, match="receipt"):
        validate_receipt(receipt, compile_graph(sensor_spec()), str(uuid.uuid4()), 1, {1})


def test_offline_cli_emits_bound_bytes_without_opening_any_device(tmp_path, monkeypatch):
    from argparse import Namespace

    from instrumentzero.edge import acquisition
    from instrumentzero.edge.cli import run

    spec_path = tmp_path / "spec.json"
    spec_path.write_text(json.dumps(sensor_spec()))
    output = tmp_path / "request.izc"
    monkeypatch.setattr(
        acquisition, "SerialPort", lambda _: pytest.fail("Offline compilation opened a device")
    )
    result = run(Namespace(edge_command="control", spec=spec_path, output=output, placement="raw_host"))
    assert decode_configuration(output.read_bytes())["spec_sha256"] == result["spec_sha256"]
    assert result["bytes"] == len(output.read_bytes()) and not result["hardware_operation_verified"]
    with pytest.raises(FileExistsError):
        run(Namespace(edge_command="control", spec=spec_path, output=output, placement="raw_host"))


def transport_cost_fixture(compiled):
    # Deliberately synthetic CPU inputs isolate byte admission from scheduler load.
    # These are test dependencies, never reported as a benchmark.
    from instrumentzero.edge.native import core_identity, library

    return {
        "schema": "instrumentzero.edge.costs/1",
        "basis": "measured_host_proxy",
        "platform": "transport-test-fixture",
        "machine": "test-fixture",
        "core_sha256": core_identity(),
        "spec_sha256": compiled["spec_sha256"],
        "state_bytes": library().iz_state_bytes(),
        "primitive_costs": {
            name: {"ns_per_input_frame": 1000.0, "observed_max_ns_per_input_frame": 1000.0}
            for name in ("calibration", "calibration_fir")
        },
        "limits": "Synthetic positive costs for transport-only tests; not a measured benchmark.",
    }


def test_nominal_uart_ceiling_rejects_impossible_raw_but_preserves_feasible_tiny_filtered_graph(
    control_library,
    monkeypatch,
):
    from instrumentzero.edge import control
    from instrumentzero.edge.planner import plan

    monkeypatch.setattr(control, "measure_costs", transport_cost_fixture)

    spec = sensor_spec()
    spec["resources"].update(block_samples=1, link_bytes_per_second=1e9, max_latency_ms=10000)
    compiled = compile_graph(spec)
    result = plan(compiled, transport_cost_fixture(compiled))
    raw, _, filtered = result["candidates"]
    assert raw["estimated_transfer_bytes_per_second"] == 38400 and not raw["legal_under_declared_model"]
    assert filtered["estimated_transfer_bytes_per_second"] == 9600 and filtered["legal_under_declared_model"]
    assert result["selected"] == "filtered_edge" and result["effective_link_bytes_per_second"] == 11520
    from instrumentzero.edge.runtime import execute

    samples = np.sin(np.arange(400) * 2 * np.pi * 17.25 / 400).astype(np.float32)[:, None]
    stream = execute(compiled, samples, np.arange(400) * 2500, mode="filtered_edge", chunks=[1])
    assert stream["metrics"]["wire_bytes_including_headers"] == 9600
    with pytest.raises(EdgeError, match="throughput"):
        configuration(spec, "raw_host")
    request, _ = configuration(spec, "filtered_edge")
    cfg = Config()
    assert control_library.iz_config_decode(ctypes.byref(cfg), request[3:], len(request) - 3, 1, 4) == 0
    # CRC-valid raw request bypassing the host is also refused by firmware.
    bad = bytearray(request)
    bad[26] = 0
    bad = repair_crc(bad)
    assert control_library.iz_config_decode(ctypes.byref(cfg), bad[3:], len(bad) - 3, 1, 4) == 1
    with pytest.raises(EdgeError, match="UART"):
        decode_configuration(bad)
    spec["resources"]["raw_validation"] = True
    with pytest.raises(EdgeError, match="No placement"):
        configuration(spec, "filtered_edge")
    spec["source"]["adapter"] = "simulated"
    virtual = compile_graph(spec)
    assert plan(virtual, transport_cost_fixture(virtual))["candidates"][0]["legal_under_declared_model"]


def test_small_nondivisible_blocks_use_actual_packet_cadence_and_wait(control_library, monkeypatch):
    from instrumentzero.edge import control
    from instrumentzero.edge.planner import plan

    monkeypatch.setattr(control, "measure_costs", transport_cost_fixture)

    spec = sensor_spec()
    spec["resources"].update(block_samples=3, link_bytes_per_second=11520, max_latency_ms=10000)
    compiled = compile_graph(spec)
    candidate = plan(compiled, transport_cost_fixture(compiled))["candidates"][2]
    assert candidate["estimated_transfer_bytes_per_second"] == 9600
    # A block3/decimation4 output may wait6input samples, then transmit96bytes.
    lower = 1000 * (6 / 400 + compiled["filter"]["group_delay_seconds"] + 96 / 11520)
    assert candidate["modeled_latency_ms"] >= lower
    request, _ = configuration(spec, "filtered_edge")
    cfg = Config()
    assert control_library.iz_config_decode(ctypes.byref(cfg), request[3:], len(request) - 3, 3, 4) == 0


def test_control_write_backpressure_never_consumes_received_sample_bytes():
    class Port:
        def __init__(self):
            self.writes = 0
            self.pending = b"raw-trial-bytes"

        def write(self, data):
            self.writes += 1
            return 0 if self.writes == 1 else len(data)

        def read(self, timeout):
            data, self.pending = self.pending, b""
            return data

    port = Port()
    write_all(port, b"S", time.monotonic() + 1)
    assert port.pending == b"raw-trial-bytes"
