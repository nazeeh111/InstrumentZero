"""Portable, hash-bound samples, protocol, configuration and executable source."""
from __future__ import annotations

import hashlib
import io
import struct
import zipfile
from pathlib import Path

import numpy as np

from .native import core_identity
from .runtime import packets
from .spec import canonical


def generated_header(compiled, placement="raw_host"):
    s = compiled["spec"]
    def values(xs):
        return ", ".join(f"{float(v):.9e}f" for v in xs)
    return ("/* Generated from reviewed InstrumentZero Edge operators. No device flash implied. */\n"
            "#ifndef IZ_GENERATED_H\n#define IZ_GENERATED_H\n"
            f'#define IZ_SPEC_SHA256 "{compiled["spec_sha256"]}"\n'
            f'#define IZ_RATE_HZ {s["source"]["rate_hz"]}\n'
            f'#define IZ_CHANNELS {len(s["source"]["channels"])}\n'
            f'#define IZ_ADAPTER_KIND {("simulated", "wav", "zephyr_adxl345").index(s["source"]["adapter"])}\n'
            f'#define IZ_MODE {("raw_host", "calibrated_edge", "filtered_edge").index(placement)}\n'
            f'#define IZ_RAW_VALIDATION {int(s["resources"]["raw_validation"])}\n'
            f'#define IZ_BLOCK_SAMPLES {s["resources"]["block_samples"]}\n'
            f'#define IZ_QUEUE_BLOCKS {s["resources"]["queue_blocks"]}\n'
            f'#define IZ_TAPS {s["dsp"]["taps"]}\n#define IZ_DECIMATION {s["dsp"]["decimation"]}\n'
            f'static const float iz_scale[IZ_CHANNELS] = {{{values(s["calibration"]["scale"])}}};\n'
            f'static const float iz_offset[IZ_CHANNELS] = {{{values(s["calibration"]["offset"])}}};\n'
            f'static const float iz_coefficients[IZ_TAPS] = {{{values(compiled["coefficients"])}}};\n'
            "#endif\n")


def export_run(run, samples, timestamps_us, original_protocol=None):
    package = Path(__file__).parents[1]
    files = {}
    files["spec.json"] = canonical(run["compiled"]["spec"])
    files["compiled.json"] = canonical(run["compiled"])
    files["costs.json"] = canonical(run["cost_profile"])
    files["run.json"] = canonical(run)
    files["generated.h"] = generated_header(run["compiled"], run["placement"]["selected"]).encode()
    for name, data in [("samples.npy", np.asarray(samples, np.float32)), ("timestamps_us.npy", np.asarray(timestamps_us, np.int64))]:
        stream = io.BytesIO()
        np.save(stream, data, allow_pickle=False)
        files[name] = stream.getvalue()
    first = run["comparisons"][0]["session"]
    stream = io.BytesIO()
    for packet in packets(samples, timestamps_us, run["compiled"], first):
        stream.write(struct.pack("<I", len(packet)))
        stream.write(packet)
    files["raw.izp"] = stream.getvalue()
    if original_protocol is not None:
        files["original-device.izp"] = original_protocol
    for path in package.rglob("*"):
        if path.is_file() and path.suffix in (".py", ".c", ".h", ".html", ".css", ".js", ".svg") and "__pycache__" not in path.parts:
            files["source/instrumentzero/" + path.relative_to(package).as_posix()] = path.read_bytes()
    files["LICENSE"] = (package/"LICENSE").read_bytes() if (package/"LICENSE").is_file() else package.parents[1].joinpath("LICENSE").read_bytes()
    lock = Path(__file__).with_name("requirements-runtime.lock")
    if not lock.is_file():
        lock = package.parents[1] / "requirements-runtime.lock"
    files["requirements.txt"] = lock.read_bytes()
    files["source/instrumentzero/edge/requirements-runtime.lock"] = files["requirements.txt"]
    files["recompute.py"] = b'''"""Recompute offline with included source, NumPy/SciPy and local C99 compiler."""
import hashlib, json, sys
from pathlib import Path
import numpy as np
root = Path(__file__).resolve().parent
manifest = json.loads((root / "manifest.json").read_text())
for name, digest in manifest["sha256"].items():
    if hashlib.sha256((root/name).read_bytes()).hexdigest() != digest:
        raise SystemExit("Artifact hash mismatch: " + name)
sys.path.insert(0, str(root/"source"))
from instrumentzero.edge.simulation import compare
run = json.loads((root/"run.json").read_text())
if (root/"original-device.izp").is_file():
    from instrumentzero.edge.acquisition import read_recording
    device_y, device_t, device_source = read_recording(root/"original-device.izp", run["compiled"]["spec"], run["source"]["firmware_sha256"])
    assert np.array_equal(device_y, np.load(root/"samples.npy", allow_pickle=False))
    assert np.array_equal(device_t, np.load(root/"timestamps_us.npy", allow_pickle=False))
result = compare(json.loads((root/"spec.json").read_text()),
    np.load(root/"samples.npy", allow_pickle=False), np.load(root/"timestamps_us.npy", allow_pickle=False),
    json.loads((root/"costs.json").read_text()), run["source"])
for old, new in zip(run["comparisons"], result["comparisons"], strict=True):
    for key in ("frequency_hz", "damping_ratio", "explained_energy_fraction"):
        a, b = old["result"].get(key), new["result"].get(key)
        if a is None or b is None:
            assert a is b, (key, a, b)
        else:
            assert np.isclose(a, b, rtol=1e-6, atol=1e-8), (key, a, b)
print(json.dumps({"recomputed": True, "source": run["source"], "selected": result["placement"]["selected"],
    "results": [c["result"] for c in result["comparisons"]]}, indent=2, allow_nan=False))
'''
    files["README.txt"] = b"InstrumentZero Edge software preview.\nRaw samples retained; summaries cannot reconstruct discarded samples.\nRun: python -m pip install -r requirements.txt\nThen: python recompute.py\nA free C99 compiler (Clang/GCC) is required. No private files or network are used by recompute.py.\nTiming metrics vary by computer; recorded host costs freeze the provisional placement rules.\nSynthetic data is not independently measured physical evidence.\n"
    manifest = {"schema": "instrumentzero.edge.artifact/1", "spec_sha256": run["compiled"]["spec_sha256"],
                "core_sha256": core_identity(), "firmware_sha256": None,
                "source": run["source"], "physical_acquisition_verified": False,
                "sha256": {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}}
    files["manifest.json"] = canonical(manifest)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in sorted(files.items()):
            archive.writestr(zipfile.ZipInfo(name, date_time=(2026, 10, 29, 0, 0, 0)), data, compress_type=zipfile.ZIP_DEFLATED)
    return out.getvalue()
