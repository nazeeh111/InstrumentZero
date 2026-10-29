"""Typed Edge API exposed as a bounded CLI. Hardware actions stay explicit."""
from __future__ import annotations

import json
from pathlib import Path

from scipy.io import wavfile

from .artifacts import export_run, generated_header
from .planner import measure_costs, plan
from .simulation import SCENARIOS, compare, generate
from .spec import EdgeError, compile_graph, default_spec


def add_parser(sub):
    parser = sub.add_parser("edge", help="Compile, simulate and recompute the Edge software preview")
    commands = parser.add_subparsers(dest="edge_command", required=True)
    example = commands.add_parser("spec", help="Write the supported default specification to stdout")
    example.set_defaults(edge_command="spec")
    compiler = commands.add_parser("compile", help="Validate graph/units/FIR; emit configuration and C bindings")
    compiler.add_argument("spec", type=Path)
    compiler.add_argument("--output", type=Path)
    compiler.add_argument("--placement", choices=["raw_host", "calibrated_edge", "filtered_edge"], default="raw_host")
    planner = commands.add_parser("plan", help="Measure local primitive costs and choose a provisional placement")
    planner.add_argument("spec", type=Path)
    planner.add_argument("--costs", type=Path, help="Use a frozen matching measured-host cost profile")
    demo = commands.add_parser("simulate", help="Compare placements on an explicitly synthetic cantilever")
    demo.add_argument("--spec", type=Path)
    demo.add_argument("--scenario", choices=SCENARIOS, default="mount_a")
    demo.add_argument("--seed", type=int, default=20261029)
    demo.add_argument("--seconds", type=float, default=8.)
    demo.add_argument("--costs", type=Path)
    demo.add_argument("--export", type=Path)
    recording = commands.add_parser("recording", help="Analyze a consented local PCM WAV through the same contracts")
    recording.add_argument("spec", type=Path)
    recording.add_argument("wav", type=Path)
    recording.add_argument("--consent", action="store_true", required=True, help="Confirm you have permission to use this recording")
    recording.add_argument("--export", type=Path)
    protocol = commands.add_parser("protocol", help="Validate and analyze a consented raw IZP1 sensor recording")
    protocol.add_argument("spec", type=Path)
    protocol.add_argument("data", type=Path)
    protocol.add_argument("--firmware-sha256", required=True)
    protocol.add_argument("--consent", action="store_true", required=True)
    protocol.add_argument("--export", type=Path)
    capture = commands.add_parser("capture", help="Explicitly open one provisional sensor serial port; never flashes")
    capture.add_argument("spec", type=Path)
    capture.add_argument("--device", required=True)
    capture.add_argument("--seconds", type=float, default=8.)
    capture.add_argument("--output", type=Path, required=True)
    capture.add_argument("--consent", action="store_true", required=True)


def read_json(path):
    return json.loads(path.read_text()) if path else None


def run(args):
    if args.edge_command == "spec":
        return default_spec()
    spec = read_json(args.spec) if args.spec is not None else default_spec()
    compiled = compile_graph(spec)
    if args.edge_command == "capture":
        from .acquisition import capture
        return capture(spec, args.device, args.seconds, args.output, args.consent)
    if args.edge_command == "compile":
        profile = measure_costs(compiled)
        placement = plan(compiled, profile)
        binding = next(c for c in placement["candidates"] if c["mode"] == args.placement)
        if not binding["legal_under_declared_model"]:
            raise EdgeError("Requested firmware binding violates declared resources: " + "; ".join(binding["reasons"]))
        compiled["binding"] = {"placement": args.placement, "resource_model": binding,
                               "cost_profile": profile, "scope": "provisional measured-host cost model; actual MCU timing unverified"}
        if args.output:
            args.output.mkdir(parents=True, exist_ok=True)
            # Refuse overwrites so a compile never silently replaces a prior reviewed binding.
            for name, value in [("compiled.json", json.dumps(compiled, indent=2)), ("generated.h", generated_header(compiled, args.placement))]:
                with (args.output/name).open("x") as stream:
                    stream.write(value)
        return compiled
    if args.edge_command == "plan":
        profile = measure_costs(compiled) if args.costs is None else read_json(args.costs)
        return {"cost_profile": profile, "placement": plan(compiled, profile)}
    if args.edge_command == "protocol":
        from .acquisition import read_recording
        y, ticks, source = read_recording(args.data, spec, args.firmware_sha256)
        result = compare(spec, y, ticks, source=source)
    elif args.edge_command == "recording":
        import hashlib

        import numpy as np
        if compiled["spec"]["source"]["adapter"] != "wav":
            raise EdgeError("Recording import requires source.adapter=wav and FS units.")
        rate, y = wavfile.read(args.wav)
        if rate != compiled["spec"]["source"]["rate_hz"]:
            raise EdgeError("Recording rate differs from specification; implicit resampling is forbidden.")
        if y.dtype not in (np.int16, np.int32):
            raise EdgeError("Supported WAV encodings: signed PCM16 or PCM32. No implicit unsigned/float conversion.")
        y = y.astype(np.float32) / (2**(15 if y.dtype == np.int16 else 31))
        if y.ndim == 1:
            y = y[:, None]
        ticks = np.rint(np.arange(len(y))*1e6/rate).astype(np.int64)
        source = {"source_kind": "user_supplied_recording", "file_sha256": hashlib.sha256(args.wav.read_bytes()).hexdigest(),
                  "consent_confirmed": True, "gain_control": "unknown", "resampling_before_import": "unknown",
                  "independent_physical_reference": False, "clock": "nominal file rate; no device timestamps"}
        result = compare(spec, y, ticks, source=source)
    else:
        y, ticks, source = generate(spec, args.scenario, args.seed, args.seconds)
        costs = read_json(args.costs)
        if args.costs is not None and not isinstance(costs, dict):
            raise EdgeError("A frozen cost profile must be a JSON object.")
        result = compare(spec, y, ticks, costs, source)
    if args.export:
        with args.export.open("xb") as stream:
            stream.write(export_run(result, y, ticks, original_protocol=args.data.read_bytes() if args.edge_command == "protocol" else None))
    return result
