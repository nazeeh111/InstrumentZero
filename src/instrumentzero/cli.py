"""Command line entry point. No credentials or physical actions required."""
from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from .acoustic import analyze_audio, load_wav
from .calibrated import calibrated_acoustic_validation, export_calibrated_package
from .edge.cli import add_parser as add_edge_parser
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
    add_edge_parser(sub)
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
    session = sub.add_parser("session", help="Save and replay a file-only stiffness experiment")
    actions = session.add_subparsers(dest="session_action", required=True)
    start = actions.add_parser("start", help="Start from a JSON specification")
    start.add_argument("spec");start.add_argument("--out", required=True)
    append = actions.add_parser("append", help="Add a JSON or CSV observation batch")
    append.add_argument("session");append.add_argument("data");append.add_argument("--label");append.add_argument("--out", required=True)
    cal = actions.add_parser("calibrate", help="Add a shared calibration revision from JSON")
    cal.add_argument("session");cal.add_argument("calibration");cal.add_argument("--label");cal.add_argument("--basis", help="Revision-specific calibration basis; absence is marked unverified");cal.add_argument("--out", required=True)
    review = actions.add_parser("review", help="Recompute historical analyses and optionally export")
    review.add_argument("session");review.add_argument("--export", metavar="JSON")
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
        if args.command == "session":
            from .session import ExperimentSession, MAX_SESSION, publish, read_file
            if args.session_action == "start":
                source = Path(args.spec)
                session_value = ExperimentSession.start(read_file(source), source.name)
                output = session_value.review()
                publish(args.out, session_value.to_bytes())
            else:
                session_value = ExperimentSession.load(read_file(args.session, MAX_SESSION))
                if args.session_action in ("append", "calibrate"):
                    path = Path(args.data if args.session_action == "append" else args.calibration)
                    kind = "observations" if args.session_action == "append" else "calibration"
                    fmt = "csv" if kind == "observations" and path.suffix.lower() == ".csv" else "json"
                    session_value = session_value.append(kind, read_file(path), args.label or path.name, fmt,
                                                         basis=args.basis if kind == "calibration" else None)
                    output = session_value.review()
                    publish(args.out, session_value.to_bytes())
                else:
                    output = session_value.review()
                    if args.export:
                        publish(args.export, session_value.export_bytes())
            print(json.dumps(output, indent=2, allow_nan=False))
            return 0
        if args.command == "edge":
            from .edge.cli import run
            print(json.dumps(run(args), indent=2, allow_nan=False))
            return 0
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
