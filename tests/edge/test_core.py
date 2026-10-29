import ctypes as ct

import numpy as np
import pytest
from scipy import signal

from instrumentzero.edge.native import Processor
from instrumentzero.edge.spec import EdgeError, compile_graph, default_spec


@pytest.mark.parametrize("channels", [1, 3])
@pytest.mark.parametrize("decimation", [1, 2, 4, 8])
def test_streaming_matches_independent_float64_across_chunks_and_reset(channels, decimation):
    rng = np.random.default_rng(822)
    y = rng.normal(0, .2, (1027, channels)).astype(np.float32)
    y[0] = 1  # impulse + noise exercises startup and ring wrap
    scale = np.array([.7, -1.1, 1.2][:channels], np.float32)
    offset = np.array([.1, -.01, .07][:channels], np.float32)
    taps = signal.firwin(127, .1).astype(np.float32)
    expected = signal.lfilter(taps.astype(float), [1.], (y.astype(float)-offset)*scale, axis=0)[decimation-1::decimation]
    p = Processor(scale, offset, taps, decimation)
    output = []
    pos = 0
    for n in [0, 1, 2, 0, 7, 31, 257, 3, 61, 665]:
        output.append(p.process(y[pos:pos+n]))
        pos += n
    assert pos == len(y)
    np.testing.assert_allclose(np.concatenate(output), expected, rtol=3e-5, atol=2e-7)
    p.reset()
    np.testing.assert_array_equal(p.process(y), np.concatenate(output))


def test_capacity_and_nonfinite_rejections_are_transactional():
    p = Processor([1], [0], [1], 1)
    before = bytes(p.state)
    data = np.ones((4, 1), np.float32)
    output = np.full(4, 99, np.float32)
    written = ct.c_size_t(77)
    def ptr(a):
        return a.ctypes.data_as(ct.POINTER(ct.c_float))
    assert p.lib.iz_process(p.state, ptr(data), 4, ptr(output), 3, ct.byref(written)) == -2
    assert bytes(p.state) == before and written.value == 77
    np.testing.assert_array_equal(output, [99]*4)
    with pytest.raises(EdgeError):
        p.process([[1], [np.inf]])
    assert bytes(p.state) == before


@pytest.mark.parametrize("scale,offset,taps", [([1, 2], [0], [1]), ([[1]], [0], [1]), ([1], [0], []), ([1], [0], [[1]])])
def test_native_wrapper_rejects_unsafe_pointer_shapes(scale, offset, taps):
    with pytest.raises(EdgeError):
        Processor(scale, offset, taps, 1)


def test_fir_prevents_a_decimation_alias_and_keeps_passband():
    compiled = compile_graph(default_spec())
    t = np.arange(8000)/400
    p = Processor([1], [0], compiled["coefficients"], 4)
    wanted = np.sin(2*np.pi*17*t)
    alien = np.sin(2*np.pi*83*t)  # would alias onto 17 Hz after 4x decimation
    out = p.process((wanted+alien)[:, None])[100:, 0]
    expected = signal.lfilter(compiled["coefficients"], [1.], wanted)[3::4][100:]
    assert np.sqrt(np.mean((out-expected)**2)) < .0003
    assert abs(np.sqrt(2*np.mean(out**2))-1) < .002
