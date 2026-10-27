"""Portable evidence packages include input bytes, code and explicitly scoped conclusions."""
from __future__ import annotations

import csv
import io
import json
import platform
import zipfile
from pathlib import Path

import numpy as np
import scipy
from scipy.io import wavfile

from . import __version__
from .acoustic import analyze_audio
from .engine import analyze_stiffness, compile_experiment
from .spec import MeasurementError, MeasurementSpec


def export_package(payload: dict) -> bytes:
    if not isinstance(payload, dict):
        raise MeasurementError("An export requires a specification and observations.")
    spec = MeasurementSpec.parse(payload.get("spec"))
    rows = payload.get("rows")
    if spec.domain == "stiffness":
        result = analyze_stiffness(spec, rows)
    else:
        result = analyze_audio(spec, payload.get("samples"), payload.get("sample_rate_hz"))
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        def write_json(name, value):
            archive.writestr(name, json.dumps(value, indent=2, allow_nan=False) + "\n")
        write_json("spec.json", spec.to_dict())
        write_json("result.json", result)
        write_json("procedure.json", compile_experiment(spec))
        write_json("calibration.json", spec.to_dict()["calibration"])
        write_json("source-attribution.json", spec.source_attribution)
        notices = ["DATA NOTICES (separate from the code's MIT license)"]
        for item in spec.source_attribution:
            notices.extend(["", item["title"], ", ".join(item["creators"]), item["source_url"],
                            item["license"], item["license_url"], "Changes: " + item["modifications"]])
        if not spec.source_attribution:
            notices.append("Source rights/provenance are user supplied; no third-party rights are inferred.")
        archive.writestr("DATA-NOTICES.txt", "\n".join(notices) + "\n")
        write_json("environment.json", {"python": platform.python_version(), "numpy": np.__version__,
                                        "scipy": scipy.__version__, "instrumentzero": __version__})
        if spec.domain == "stiffness":
            write_json("observations.json", rows)
            output = io.StringIO()
            columns = ["force_n", "position_px"] if "position_px" in rows[0] else ["force_n", "displacement_m", "sigma_m"]
            writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
            archive.writestr("observations.csv", output.getvalue())
        else:
            samples = np.asarray(payload["samples"], dtype=np.float64)
            wave = io.BytesIO()
            wavfile.write(wave, int(payload["sample_rate_hz"]), samples)
            archive.writestr("observations.wav", wave.getvalue())
            # Preserve exact float samples and possibly non-integer sample rate for exact reproduction.
            write_json("observations.json", {"samples": samples.tolist(), "sample_rate_hz": payload["sample_rate_hz"]})
        replay = '''"""Run from this exported directory: python reproduce.py"""
import json
from pathlib import Path
from instrumentzero.engine import analyze_stiffness
from instrumentzero.acoustic import analyze_audio

root = Path(__file__).parent
spec = json.loads((root / "spec.json").read_text())
observations = json.loads((root / "observations.json").read_text())
if spec["domain"] == "stiffness":
    result = analyze_stiffness(spec, observations)
else:
    result = analyze_audio(spec, observations["samples"], observations["sample_rate_hz"])
(root / "reproduced-result.json").write_text(json.dumps(result, indent=2, allow_nan=False) + "\\n")
print(json.dumps(result["quantity"], indent=2))
'''
        archive.writestr("reproduce.py", replay)
        archive.writestr("requirements.txt", f"numpy=={np.__version__}\nscipy=={scipy.__version__}\n")
        # A package must remain executable even before a package-index upload; carry the engine source.
        source = Path(__file__).parent
        for file in source.glob("*.py"):
            archive.write(file, f"instrumentzero/{file.name}")
        archive.writestr("scientific-limitations.txt", "\n".join([
            f"Evidence: {spec.source_kind}: {spec.source_name}",
            result["uncertainty_method"], *result["assumptions"], *result["warnings"],
            "An exported result is not an independent physical validation.",
            "No hardware was actuated by this package."]))
        archive.writestr("README.txt", "INSTRUMENTZERO EVIDENCE PACKAGE\n\n"
            "Install NumPy and SciPy (see environment.json), then run python reproduce.py.\n"
            "The included instrumentzero/ source makes this independent of a package-index release.\n"
            "spec.json records units, calibration assumptions, source identity and budget.\n"
            "observations.json preserves exact numeric inputs. result.json contains source digests.\n"
            "The procedure is for deliberate human-supervised setup. Recommendations are not executed.\n"
            "Read scientific-limitations.txt before interpreting the reported interval.\n")
        license_file = source / "LICENSE"
        if not license_file.exists():
            license_file = source.parents[1] / "LICENSE"
        if license_file.exists():
            archive.write(license_file, "LICENSE")
        write_json("manifest.json", {"format": "instrumentzero-evidence-1", "engine_version": __version__,
                                     "domain": spec.domain, "provenance": result["provenance"]})
    return buffer.getvalue()
