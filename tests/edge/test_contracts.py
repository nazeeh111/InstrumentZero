import copy
import uuid

import numpy as np
import pytest

from instrumentzero.edge.planner import measure_costs, plan
from instrumentzero.edge.protocol import Frame, TickUnwrapper, Validator, decode, encode
from instrumentzero.edge.runtime import Session, packets
from instrumentzero.edge.spec import EdgeError, EdgeSpec, compile_graph, default_spec


@pytest.mark.parametrize("edit", [
    lambda s: s["graph"][0].update(inputs=["recorder"]),
    lambda s: s["graph"][3].update(operator="eval"),
    lambda s: s["calibration"].update(unit_out="Pa"),
    lambda s: s["source"].update(rate_hz=333),
    lambda s: s["source"].update(channels=["z", "z"]),
    lambda s: s["resources"].update(block_samples=100000),
    lambda s: s["calibration"].update(scale=[float("nan")]),
    lambda s: s["dsp"].update(taps=7),
    lambda s: s["dsp"].update(stopband_hz=60),
    lambda s: s.update(custom="unreviewed"),
    lambda s: s["resources"].update(block_samples=64.0),
    lambda s: s["dsp"].update(decimation=4.0),
    lambda s: s["dsp"].update(decimation=3),
])
def test_unsupported_graphs_units_rates_allocations_fail(edit):
    s = default_spec()
    edit(s)
    with pytest.raises(ValueError):
        compile_graph(s)


def test_spec_is_owned_and_calibration_change_changes_identity():
    s = default_spec()
    frozen = EdgeSpec.parse(s)
    s["calibration"]["scale"] = [-1]
    assert frozen.to_dict()["calibration"]["scale"] == [1]
    assert EdgeSpec.parse(s).sha256 != frozen.sha256


def make_frames():
    compiled = compile_graph(default_spec())
    session = str(uuid.uuid4())
    data = np.sin(np.arange(128))[:, None].astype(np.float32)
    frames = list(packets(data, np.arange(128)*2500, compiled, session))
    return compiled, session, frames


@pytest.mark.parametrize("fault", ["drop", "repeat", "reorder", "integrity", "epoch", "session", "config", "rate", "clock", "clip", "overrun", "truncate", "version"])
def test_protocol_faults_invalidate_epoch(fault):
    c, sid, frames = make_frames()
    validator = Validator(c, sid)
    if fault in ("drop", "reorder"):
        packet = frames[1]
    elif fault == "repeat":
        validator.accept(frames[0])
        packet = frames[0]
    elif fault in ("integrity", "version"):
        packet = bytearray(frames[0])
        packet[20 if fault == "integrity" else 4] ^= 0x7f
        packet = bytes(packet)
    elif fault == "truncate":
        packet = frames[0][:-1]
    else:
        f = decode(frames[0])
        if fault == "epoch":
            f.epoch = 1
        elif fault == "session":
            f.session = str(uuid.uuid4())
        elif fault == "config":
            f.spec_sha256 = "ab"*32
        elif fault == "rate":
            f.rate_hz = 800
        elif fault == "clock":
            f.timestamps_us[5:] += 2000
        elif fault == "clip":
            f.samples[5, 0] = 20
        elif fault == "overrun":
            f.flags = 2
        packet = encode(f)
    with pytest.raises(EdgeError):
        validator.accept(packet)
    with pytest.raises(EdgeError, match="already invalid"):
        validator.accept(frames[0])


def test_timestamp_rollover_and_clock_ambiguity():
    clock = TickUnwrapper()
    assert clock.update(0xffffff00) == 0xffffff00
    assert clock.update(0x100) == 0x100000100
    with pytest.raises(EdgeError):
        clock.update(0x100)
    with pytest.raises(EdgeError):
        clock.update(0xff)


def test_epoch_change_clears_queued_samples_and_analysis_and_reconnect_is_distinct():
    s = default_spec()
    with Session(s) as session:
        old = list(packets(np.ones((64, 1)), np.arange(64)*2500, session.compiled, session.session_id))[0]
        session.enqueue(old)
        session.result = {"frequency_hz": 17}
        changed = copy.deepcopy(s)
        changed["calibration"]["id"] = "fresh calibration"
        session.reconfigure(changed)
        assert session.epoch == 1 and session.result is None and not session.queue
        session.enqueue(old)
        with pytest.raises(EdgeError, match="epoch/configuration"):
            session.consume()
    assert session.closed and session.result is None
    with pytest.raises(EdgeError):
        session.reconfigure(s)
    assert Session(s).session_id != session.session_id


def test_queue_overflow_stops_capture_instead_of_hiding_loss():
    c, sid, frames = make_frames()
    session = Session(c["spec"])
    for _ in range(c["spec"]["resources"]["queue_blocks"]):
        session.enqueue(frames[0])
    with pytest.raises(EdgeError, match="overflow"):
        session.enqueue(frames[1])
    assert session.failure and not session.queue


def test_queue_refuses_a_valid_packet_larger_than_declared_block():
    c, sid, _ = make_frames()
    frame = Frame(sid, 0, 0, 400, c["spec_sha256"], np.arange(256)*2500, np.ones((256, 1)))
    with pytest.raises(EdgeError, match="bounded storage"):
        Session(c["spec"]).enqueue(encode(frame))


@pytest.mark.parametrize("field,value", [("state_bytes", -100000), ("primitive_costs", {"calibration": -1})])
def test_cost_profile_cannot_forge_negative_resource_costs(field, value):
    c = compile_graph(default_spec())
    p = measure_costs(c)
    p[field] = value
    with pytest.raises(EdgeError):
        plan(c, p)


def test_raw_validation_latency_counts_both_streams():
    s = default_spec()
    s["resources"].update(raw_validation=True, link_bytes_per_second=10000, max_latency_ms=350)
    c = compile_graph(s)
    with pytest.raises(EdgeError, match="No placement"):
        plan(c, measure_costs(c))


def test_placement_includes_host_favored_and_impossible_graphs():
    c = compile_graph(default_spec())
    profile = measure_costs(c)
    assert plan(c, profile)["selected"] == "filtered_edge"
    s = default_spec()
    s["resources"]["raw_validation"] = True
    s["resources"]["link_bytes_per_second"] = 10000
    host = compile_graph(s)
    assert plan(host, measure_costs(host))["selected"] == "raw_host"
    s["resources"]["edge_memory_bytes"] = 1
    with pytest.raises(EdgeError, match="allocation"):
        compile_graph(s)
    with pytest.raises(EdgeError, match="stale"):
        plan(c, measure_costs(host))


def test_recording_validator_also_enforces_configured_block_bound():
    c, sid, _ = make_frames()
    packet = encode(Frame(sid,0,0,400,c['spec_sha256'],np.arange(256)*2500,np.ones((256,1))))
    with pytest.raises(EdgeError,match='configured block'):
        Validator(c,sid).accept(packet)


def test_empty_explicit_specification_does_not_silently_use_defaults():
    from instrumentzero.edge.simulation import compare
    with pytest.raises(EdgeError):
        compare({})


def test_direct_typed_constructor_cannot_bypass_reviewed_graph_validation():
    from instrumentzero.edge.spec import canonical
    s = default_spec()
    s['graph'][0]['operator'] = 'unreviewed'
    with pytest.raises(EdgeError, match='unsupported binding'):
        compile_graph(EdgeSpec(canonical(s)))
