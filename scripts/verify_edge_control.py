"""Execute firmware configuration parser/guard under sanitizers and cross-compile it."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

from instrumentzero.edge.control import configuration

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    compiler = shutil.which("clang")
    if not compiler:
        raise SystemExit("Clang is required for sanitizer and Cortex-M4 checks.")
    spec = json.loads((ROOT / "examples/edge/adxl345-spec.json").read_text())
    spec["resources"]["link_bytes_per_second"] = 10000
    fixtures = []
    for mode in ("raw_host", "calibrated_edge", "filtered_edge"):
        spec["dsp"]["taps"] = 255 if mode == "filtered_edge" else 127
        request, _ = configuration(spec, mode, request_id=0x4743534B)
        fixture = args.output / (mode + ".izc")
        fixture.write_bytes(request)
        fixtures.append(str(fixture))
    source = ROOT / "src/instrumentzero/edge/control"
    binary = args.output / "control-sanitized"
    obj = args.output / "control-cortex-m4.o"
    commands = [
        [
            compiler,
            "-std=c11",
            "-g",
            "-O1",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-fsanitize=address,undefined",
            "-fno-omit-frame-pointer",
            "-I" + str(source),
            str(source / "iz_control.c"),
            str(ROOT / "tests/edge/control_harness.c"),
            "-o",
            str(binary),
        ],
        [str(binary), *fixtures],
        [
            compiler,
            "--target=arm-none-eabi",
            "-mcpu=cortex-m4",
            "-mthumb",
            "-ffreestanding",
            "-fno-builtin",
            "-std=c11",
            "-Oz",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-c",
            str(source / "iz_control.c"),
            "-o",
            str(obj),
        ],
    ]
    receipts = []
    for command in commands:
        run = subprocess.run(command, capture_output=True, text=True)
        receipts.append(
            {"command": command, "returncode": run.returncode, "stdout": run.stdout, "stderr": run.stderr}
        )
        (args.output / "commands.json").write_text(json.dumps(receipts, indent=2))
        if run.returncode:
            raise SystemExit("Control verification failed: " + run.stderr)
    report = {
        "schema": "instrumentzero.edge.control-checks/1",
        "checks": "ASan/UBSan configuration/guard harness executed for all placements, CRC mutations, truncation, repeated start, epoch overflow, SPSC ring bursts/wrap/overflow",
        "cross_compilation": "actual Cortex-M4 freestanding control object",
        "control_sha256": hashlib.sha256(
            (source / "iz_control.h").read_bytes() + (source / "iz_control.c").read_bytes()
        ).hexdigest(),
        "object_sha256": hashlib.sha256(obj.read_bytes()).hexdigest(),
        "hardware_operation_verified": False,
        "commands": receipts,
    }
    (args.output / "report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({k: v for k, v in report.items() if k != "commands"}, indent=2))


if __name__ == "__main__":
    main()
