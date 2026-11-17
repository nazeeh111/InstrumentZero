import contextlib
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from instrumentzero.cli import main

SPEC = {
    "domain": "stiffness",
    "question": "How stiff is this synthetic spring?",
    "source_kind": "synthetic",
    "source_name": "Invented export control",
    "calibration": {"scale_relative_sd": 0.01, "force_relative_sd": 0.005},
}
ROWS = [
    {"force_n": force, "displacement_m": 0.004 + 0.01 * force, "sigma_m": 0.0001}
    for force in (0, 0.5, 1, 1.5)
]


class CliExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.spec = self.root / "spec.json"
        self.data = self.root / "observations.json"
        self.spec.write_text(json.dumps(SPEC))
        self.data.write_text(json.dumps(ROWS))

    def call(self, arguments):
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = main(arguments)
        return code, output.getvalue(), error.getvalue()

    def analyze(self, target):
        return self.call(["analyze", str(self.spec), str(self.data), "--export", str(target)])

    def test_analysis_cannot_replace_its_own_observations_or_specification(self):
        for target in (self.data, self.spec):
            with self.subTest(target=target.name):
                target.chmod(0o640)
                before, metadata = target.read_bytes(), target.stat()
                code, output, error = self.analyze(target)
                self.assertEqual(code, 2)
                self.assertEqual(output, "")
                self.assertTrue(error)
                self.assertEqual(target.read_bytes(), before)
                self.assertEqual(target.stat().st_ino, metadata.st_ino)
                self.assertEqual(target.stat().st_mode, metadata.st_mode)
                self.assertEqual(target.stat().st_mtime_ns, metadata.st_mtime_ns)
                self.assertFalse(list(self.root.glob("*.pending")))

    def test_new_export_retains_measurements_units_calibration_and_result(self):
        target = self.root / "evidence.zip"
        code, output, error = self.analyze(target)
        self.assertEqual(code, 0, error)
        result = json.loads(output)
        with zipfile.ZipFile(target) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(json.loads(archive.read("observations.json")), ROWS)
            self.assertEqual(json.loads(archive.read("result.json")), result)
            calibration = json.loads(archive.read("calibration.json"))
            for key, value in SPEC["calibration"].items():
                self.assertEqual(calibration[key], value)
            self.assertEqual(calibration, json.loads(archive.read("spec.json"))["calibration"])
            self.assertEqual(json.loads(archive.read("spec.json"))["source_kind"], "synthetic")

    def test_existing_demo_export_and_dangling_link_are_preserved(self):
        target = self.root / "demo.zip"
        target.write_bytes(b"prior analyst work")
        code, _, _ = self.call(["demo", "stiffness", "--export", str(target)])
        self.assertEqual(code, 2)
        self.assertEqual(target.read_bytes(), b"prior analyst work")
        target.unlink()
        target.symlink_to("absent.zip")
        self.assertEqual(self.analyze(target)[0], 2)
        self.assertTrue(target.is_symlink())
        self.assertEqual(target.readlink(), Path("absent.zip"))

    def test_late_flush_failure_preserves_input_and_same_path_retry_succeeds(self):
        target = self.root / "evidence.zip"
        before = self.data.read_bytes()
        with patch("instrumentzero.session.os.fsync", side_effect=OSError("flush failed")):
            self.assertEqual(self.analyze(target)[0], 2)
        self.assertFalse(target.exists())
        self.assertFalse(list(self.root.glob("*.pending")))
        self.assertEqual(self.data.read_bytes(), before)
        self.assertEqual(self.analyze(target)[0], 0)

    def test_replay_and_calibrated_routes_preserve_existing_exports(self):
        for command, calculation, exporter in (
            ("replay", "recorded_stiffness_replay", "export_replay_package"),
            ("validate-calibrated", "calibrated_acoustic_validation", "export_calibrated_package"),
        ):
            with self.subTest(command=command):
                target = self.root / (command + ".zip")
                target.write_bytes(b"prior evidence")
                with patch("instrumentzero.cli." + calculation, return_value={}), patch(
                    "instrumentzero.cli." + exporter, return_value=b"bounded route fixture"
                ):
                    self.assertEqual(self.call([command, "--export", str(target)])[0], 2)
                self.assertEqual(target.read_bytes(), b"prior evidence")


if __name__ == "__main__":
    unittest.main()
