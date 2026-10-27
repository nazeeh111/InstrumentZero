import pytest

from instrumentzero.adapters import phyphox_buffers
from instrumentzero.spec import MeasurementError


def test_phyphox_missing_and_irregular_samples():
    response = {"status": {"session": "example"}, "buffer": {
        "t": {"buffer": [0, .1, .2]}, "x": {"buffer": [1, 2, 3]}}}
    result = phyphox_buffers(response, "t", "x")
    assert result["sample_rate_hz"] == 10
    response["buffer"]["t"]["buffer"] = [0, .1, .3]
    assert phyphox_buffers(response, "t", "x")["sample_rate_hz"] is None
    response["buffer"]["x"]["buffer"] = [1, None, 3]
    with pytest.raises(MeasurementError, match="nonfinite"):
        phyphox_buffers(response, "t", "x")
    with pytest.raises(MeasurementError, match="missing"):
        phyphox_buffers(response, "absent", "x")
