import argparse
import struct
import uuid

import numpy as np
import pytest
from scipy.io import wavfile

from instrumentzero.edge.acquisition import read_recording
from instrumentzero.edge.cli import run
from instrumentzero.edge.runtime import packets
from instrumentzero.edge.simulation import compare
from instrumentzero.edge.spec import EdgeError, canonical, compile_graph, default_spec


def test_raw_protocol_import_and_truncation_rejection(tmp_path):
    s = default_spec()
    s['source']['adapter'] = 'zephyr_adxl345'
    c = compile_graph(s)
    data = tmp_path/'trial.izp'
    y = np.sin(np.arange(128))[:, None].astype(np.float32)
    with data.open('wb') as stream:
        for packet in packets(y, np.arange(128)*2500, c, str(uuid.uuid4())):
            stream.write(struct.pack('<I', len(packet)))
            stream.write(packet)
    values, ticks, provenance = read_recording(data, s, 'ab'*32)
    np.testing.assert_array_equal(values, y)
    np.testing.assert_array_equal(ticks, np.arange(128)*2500)
    assert not provenance['hardware_verified']
    data.write_bytes(data.read_bytes()[:-1])
    with pytest.raises(EdgeError, match='length|Truncated'):
        read_recording(data, s, 'ab'*32)


@pytest.mark.parametrize('dtype,bits', [(np.int16,15), (np.int32,31)])
def test_signed_pcm_wav_uses_same_graph_without_implicit_resampling(tmp_path, dtype, bits):
    s = default_spec()
    s['source'].update(adapter='wav', unit='FS', full_scale=1, rate_hz=8000)
    s['calibration'].update(unit_in='FS', unit_out='FS')
    s['dsp'].update(decimation=2, passband_hz=1000, stopband_hz=2000)
    s['estimator'].update(min_hz=100, max_hz=900)
    s['resources'].update(link_bytes_per_second=1000000)
    spec = tmp_path/'spec.json'
    spec.write_bytes(canonical(s))
    audio = tmp_path/'signal.wav'
    t = np.arange(8000)/8000
    wavfile.write(audio, 8000, (.7*np.exp(-.8*t)*np.sin(2*np.pi*220*t)*(2**bits-1)).astype(dtype))
    args = argparse.Namespace(edge_command='recording', spec=spec, wav=audio, consent=True, export=None)
    result = run(args)
    assert result['source']['gain_control'] == 'unknown'
    assert result['comparisons'][0]['result']['frequency_hz'] == pytest.approx(220, abs=.01)
    wavfile.write(audio, 16000, np.zeros(8000, dtype))
    with pytest.raises(EdgeError, match='rate differs'):
        run(args)


def test_simulated_disconnect_recovery_cannot_reuse_previous_session():
    result = compare(scenario='disconnect_recover', seconds=4)
    demo = result['lifecycle_demo']
    assert demo['interrupted_session'] != demo['recovered_session']
    assert demo['old_session_rejected'] and demo['result_invalidated_on_disconnect']
    assert not demo['physical_unplug_tested']


def test_corrupt_but_crc_valid_device_processing_is_not_ignored(tmp_path):
    from instrumentzero.edge.protocol import Frame, encode
    from instrumentzero.edge.runtime import reference_samples
    from instrumentzero.edge.simulation import generate
    s = default_spec()
    y, ticks, _ = generate(s, seconds=4)
    s['source']['adapter'] = 'zephyr_adxl345'
    compiled = compile_graph(s)
    sid = str(uuid.uuid4())
    path = tmp_path/'device.izp'
    reference = reference_samples(compiled, y).astype(np.float32)
    for corrupt in (False, True):
        with path.open('wb') as stream:
            raw_frames = list(packets(y,ticks,compiled,sid))
            for packet in raw_frames:
                stream.write(struct.pack('<I',len(packet)))
                stream.write(packet)
            filtered_ticks = ticks[3::4]
            for pos in range(0,len(reference),16):
                values = np.zeros_like(reference[pos:pos+16]) if corrupt else reference[pos:pos+16]
                packet = encode(Frame(sid,0,pos,100,compiled['spec_sha256'],filtered_ticks[pos:pos+16],values,kind=3))
                stream.write(struct.pack('<I',len(packet)))
                stream.write(packet)
        if corrupt:
            with pytest.raises(EdgeError, match='numeric error'):
                read_recording(path,s,'ab'*32)
        else:
            _, _, source = read_recording(path,s,'ab'*32)
            assert source['device_processing_checks'][0]['supplied_stream_numerical_consistency_passed']
