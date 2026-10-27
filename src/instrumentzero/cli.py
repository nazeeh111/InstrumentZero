"""Command line entry point. No credentials or physical actions required."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from .acoustic import analyze_audio, load_wav
from .calibrated import calibrated_acoustic_validation, export_calibrated_package
from .engine import analyze_stiffness, compile_experiment
from .examples import acoustic_example, recorded_stiffness_example, stiffness_example
from .export import export_package
from .replay import POLICIES, export_replay_package, recorded_stiffness_replay
from .spec import MeasurementError


def _json(path: str):
    return json.loads(Path(path).read_text())


def _rows(path: str):
    file = Path(path)
    if file.suffix.lower() == ".csv":
        with file.open(newline="") as stream:
            return list(csv.DictReader(stream))
    return _json(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="instrumentzero", description="Compile questions into calibrated measurement workflows.")
    sub = parser.add_subparsers(dest="command", required=True)
    plan = sub.add_parser("compile", help="Compile a supported measurement specification")
    plan.add_argument("spec")
    analyze = sub.add_parser("analyze", help="Analyze CSV/JSON force observations or WAV audio")
    analyze.add_argument("spec")
    analyze.add_argument("data")
    analyze.add_argument("--export", metavar="ZIP")
    demo = sub.add_parser("demo", help="Run a clearly labeled reproducible example")
    demo.add_argument("domain", choices=["stiffness", "acoustic"])
    demo.add_argument("--data-dir", type=Path, default=Path("data"))
    demo.add_argument("--export", metavar="ZIP")
    demo.add_argument("--recorded", action="store_true", help="Use the authentic nickel-sensor stiffness observations")
    lab = sub.add_parser("lab", help="Serve the local Lab at http://127.0.0.1:8765")
    lab.add_argument("--port", type=int, default=8765)
    lab.add_argument("--data-dir", type=Path, default=Path("data"))
    replay = sub.add_parser("replay", help="Select and reveal only available recorded stiffness observations")
    replay.add_argument("--data-dir", type=Path, default=Path("data"))
    replay.add_argument("--budget", type=int, default=4, choices=[3, 4, 5])
    replay.add_argument("--policy", default="information_gain", choices=POLICIES)
    replay.add_argument("--seed", type=int, default=0)
    replay.add_argument("--export", metavar="ZIP")
    ptb = sub.add_parser("validate-calibrated", help="Compare recorded PTB acoustic levels with their reference instrument")
    ptb.add_argument("--data-dir", type=Path, default=Path("data"))
    ptb.add_argument("--export", metavar="ZIP")
    args = parser.parse_args(argv)
    try:
        if args.command == "lab":
            from .server import serve
            serve(args.port, args.data_dir)
            return 0
        if args.command == "replay":
            options = {"measurement_budget": args.budget, "policy": args.policy, "random_seed": args.seed}
            output = recorded_stiffness_replay(args.data_dir, **options)
            if args.export:
                Path(args.export).write_bytes(export_replay_package(args.data_dir, **options))
        elif args.command == "validate-calibrated":
            output = calibrated_acoustic_validation(args.data_dir)
            if args.export:
                Path(args.export).write_bytes(export_calibrated_package(args.data_dir))
        elif args.command == "compile":
            output = compile_experiment(_json(args.spec))
        elif args.command == "demo":
            output = stiffness_example() if args.domain == "stiffness" else acoustic_example(args.data_dir)
            if args.domain == "stiffness" and args.recorded:
                output = recorded_stiffness_example(args.data_dir)
            if args.export:
                payload = {"spec": output["spec"], "rows": output.get("rows")}
                if args.domain == "acoustic":
                    wav = next(args.data_dir.glob("*440*.wav"))
                    samples, rate = load_wav(wav)
                    payload.update(samples=samples.tolist(), sample_rate_hz=rate)
                Path(args.export).write_bytes(export_package(payload))
        else:
            spec = _json(args.spec)
            payload = {"spec": spec}
            if spec.get("domain") == "acoustic":
                samples, rate = load_wav(args.data)
                output = analyze_audio(spec, samples, rate)
                payload.update(samples=samples.tolist(), sample_rate_hz=rate)
            else:
                rows = _rows(args.data)
                output = analyze_stiffness(spec, rows)
                payload["rows"] = rows
            if args.export:
                Path(args.export).write_bytes(export_package(payload))
        print(json.dumps(output, indent=2, allow_nan=False))
        return 0
    except (MeasurementError, OSError, ValueError) as exc:
        print(f"instrumentzero: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
