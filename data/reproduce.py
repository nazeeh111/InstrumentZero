"""Verify retained source bytes and rebuild derived fixtures without network access.

Usage: python data/reproduce.py [--rebuild]
FFmpeg is needed only for --rebuild. The default verifies all retained hashes.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pcm_hash(path: Path) -> str:
    with wave.open(str(path)) as recording:
        return hashlib.sha256(recording.readframes(recording.getnframes())).hexdigest()


def pontius_csv() -> bytes:
    source = (ROOT / "Pontius.dat").read_text(encoding="ascii")
    data = source.split("Data:       y             x", 1)[1]
    pairs = [line.split() for line in data.splitlines() if line.strip()]
    if len(pairs) != 40 or any(len(pair) != 2 for pair in pairs):
        raise ValueError("Unexpected Pontius source layout; inspect original before parsing")
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(["observation", "run", "deflection_source_units", "load_source_units"])
    for index, (response, load) in enumerate(pairs):
        writer.writerow([index + 1, index // 20 + 1, response, load])
    return stream.getvalue().encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rebuild", action="store_true", help="rebuild CSV/WAV after source verification")
    args = parser.parse_args()
    provenance = json.loads((ROOT / "provenance.json").read_text())
    for filename in ("Pontius.dat", "tuning-fork-440Hz.ogg"):
        if sha256(ROOT / filename) != provenance["files"][filename]["sha256"]:
            raise ValueError(f"Source checksum mismatch: {filename}")
    csv_bytes = pontius_csv()
    if hashlib.sha256(csv_bytes).hexdigest() != provenance["files"]["pontius.csv"]["sha256"]:
        raise ValueError("Parsed Pontius CSV differs from the retained provenance")
    if args.rebuild:
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            raise RuntimeError("Install FFmpeg to decode the retained OGG source")
        with tempfile.TemporaryDirectory(prefix="instrumentzero-fixtures-") as folder:
            output = Path(folder) / "tuning-fork-440Hz.wav"
            subprocess.run([
                ffmpeg, "-hide_banner", "-loglevel", "error", "-i",
                str(ROOT / "tuning-fork-440Hz.ogg"), "-ac", "1", "-c:a", "pcm_s16le",
                "-map_metadata", "-1", str(output),
            ], check=True)
            audio = next(item for item in provenance["datasets"] if item["id"] == "tuning-fork-440Hz")
            if pcm_hash(output) != audio["pcm_sha256"]:
                raise ValueError("Decoded samples differ; check FFmpeg version before replacing fixture")
            # WAV container metadata can differ by FFmpeg version; preserve the
            # retained exact container if samples agree, rather than mutating it.
            if not (ROOT / "tuning-fork-440Hz.wav").exists():
                shutil.copyfile(output, ROOT / "tuning-fork-440Hz.wav")
        target = ROOT / "pontius.csv"
        with tempfile.NamedTemporaryFile(dir=ROOT, prefix=".pontius-", delete=False) as stream:
            stream.write(csv_bytes)
            temporary = Path(stream.name)
        os.replace(temporary, target)
    for filename, item in provenance["files"].items():
        actual = sha256(ROOT / filename)
        if actual != item["sha256"]:
            # Equivalent decoded samples are sufficient for a rebuilt container.
            if filename == "tuning-fork-440Hz.wav":
                audio = next(item for item in provenance["datasets"] if item["id"] == "tuning-fork-440Hz")
                if pcm_hash(ROOT / filename) == audio["pcm_sha256"]:
                    print(f"{filename}: PCM verified; container metadata differs")
                    continue
            raise ValueError(f"Checksum mismatch: {filename}")
        print(f"{filename}: SHA-256 verified")
    print("Source data and derived fixture provenance verified.")


if __name__ == "__main__":
    main()
