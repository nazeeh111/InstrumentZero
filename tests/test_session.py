import base64
import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from instrumentzero.engine import digest
from instrumentzero.session import ExperimentSession, publish, read_file
from instrumentzero.spec import MeasurementError

SPEC = {
    "domain": "stiffness",
    "question": "How stiff is this spring?",
    "source_kind": "synthetic",
    "source_name": "Independent linear control",
    "calibration": {"scale_relative_sd": 0.01, "force_relative_sd": 0.005},
}


def rows(forces):
    return [{"force_n": f, "displacement_m": 0.004 + 0.01 * f, "sigma_m": 0.0001} for f in forces]


def packed(x):
    return json.dumps(x).encode()


class SessionTests(unittest.TestCase):
    def test_reopen_followup_calibration_and_independent_oracle(self):
        first = packed(rows([0, 0.5, 1, 1.5]))
        follow = packed(rows([0, 2]))
        s = ExperimentSession.start(packed(SPEC), "spec.json").append("observations", first, "initial.json")
        r = s.review()
        self.assertAlmostEqual(r["analyses"][-1]["result"]["quantity"]["value"], 100, places=9)
        s = s.append("observations", follow, "follow.json")
        r = s.review()
        self.assertEqual([a["observations"] for a in r["analyses"]], [4, 6])
        self.assertLess(
            r["analyses"][1]["result"]["quantity"]["relative_uncertainty"],
            r["analyses"][0]["result"]["quantity"]["relative_uncertainty"],
        )
        before = copy.deepcopy(r["analyses"])
        s = s.append(
            "calibration", packed({"scale_relative_sd": 0.1, "force_relative_sd": 0.005}), "new calibration"
        )
        r = s.review()
        self.assertEqual(r["analyses"][:2], before)
        self.assertEqual(r["comparisons"][-1]["trigger"], "calibration")
        self.assertGreater(
            r["analyses"][-1]["result"]["quantity"]["relative_uncertainty"],
            r["analyses"][-2]["result"]["quantity"]["relative_uncertainty"],
        )
        self.assertEqual(ExperimentSession.load(s.to_bytes()).review(), r)
        self.assertEqual(ExperimentSession.load(s.export_bytes()).review(), r)
        raw = json.loads(s.to_bytes())
        self.assertEqual(base64.b64decode(raw["events"][0]["source"]["base64"]), first)

    def test_refusals_preserved_and_tamper_rejected(self):
        s = ExperimentSession.start(packed(SPEC), "spec").append(
            "observations", packed(rows([0.5, 0.5, 0.5, 0.5])), "same force"
        )
        self.assertEqual(s.review()["analyses"][0]["result"]["status"], "refused")
        obj = json.loads(s.to_bytes())
        obj["events"][0]["source"]["label"] = "rewritten"
        with self.assertRaises(MeasurementError):
            ExperimentSession.load(packed(obj))
        obj = json.loads(s.to_bytes())
        obj["events"][0]["source"]["base64"] = base64.b64encode(b"[]").decode()
        obj["sha256"] = digest({k: obj[k] for k in ("schema", "spec", "events")})
        with self.assertRaises(MeasurementError):
            ExperimentSession.load(packed(obj))
        with self.assertRaises(MeasurementError):
            s.append("calibration", b'{"scale_relative_sd": NaN}', "bad")
        with self.assertRaises(MeasurementError):
            ExperimentSession.load(b" " * 16000001)

    def test_pixel_calibration_revision_never_inherits_old_basis(self):
        spec = dict(
            SPEC,
            calibration_basis="OLD synthetic certificate for baseline calibration only",
            calibration={
                "meters_per_pixel": 0.001,
                "pixel_noise_sd": 0.01,
                "scale_relative_sd": 0.01,
                "force_relative_sd": 0.005,
            },
        )
        pixel = [{"force_n": f, "position_px": 4 + 10 * f} for f in (0, 0.5, 1, 1.5)]
        original = ExperimentSession.start(packed(spec), "spec").append(
            "observations", packed(pixel), "pixels"
        )
        before = original.review()["analyses"][0]
        changed = original.append(
            "calibration",
            packed(
                {
                    "meters_per_pixel": 0.002,
                    "pixel_noise_sd": 0.01,
                    "scale_relative_sd": 0.1,
                    "force_relative_sd": 0.005,
                }
            ),
            "revision",
        )
        report = changed.review()
        old, new = report["analyses"]
        self.assertEqual(old, before)
        self.assertAlmostEqual(old["result"]["quantity"]["value"], 100)
        self.assertAlmostEqual(new["result"]["quantity"]["value"], 50)
        self.assertEqual(old["calibration_basis"], spec["calibration_basis"])
        self.assertIn("no revision-specific certificate", new["calibration_basis"])
        self.assertEqual(new["calibration_basis"], new["result"]["provenance"]["calibration_basis"])
        self.assertEqual(report["comparisons"][0]["calibration_basis_before"], old["calibration_basis"])
        self.assertEqual(report["comparisons"][0]["calibration_basis_after"], new["calibration_basis"])
        self.assertEqual(ExperimentSession.load(changed.export_bytes()).review(), report)
        declared = original.append(
            "calibration",
            packed({"meters_per_pixel": 0.002, "pixel_noise_sd": 0.01}),
            "revision",
            basis="New synthetic basis",
        ).review()["analyses"][-1]
        self.assertEqual(declared["calibration_basis"], "New synthetic basis")
        self.assertEqual(declared["result"]["provenance"]["calibration_basis"], "New synthetic basis")

    def test_curved_model_stays_unreliable_without_load_recommendation(self):
        curved = [
            {"force_n": f, "displacement_m": 0.004 + 0.01 * f + 0.02 * f * f, "sigma_m": 0.0001}
            for f in (0, 0.3, 0.6, 0.9, 1.2, 1.5)
        ]
        result = (
            ExperimentSession.start(packed(SPEC), "spec")
            .append("observations", packed(curved), "curved")
            .review()["analyses"][0]["result"]
        )
        self.assertEqual(result["status"], "unreliable")
        self.assertFalse(result["next_experiment"]["feasible"])
        self.assertTrue(any("Curvature" in warning for warning in result["warnings"]))

    def test_publish_failure_collision_retry_and_bounded_files(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            old = root / "old"
            old.write_bytes(b"KEEP")
            with self.assertRaises(FileExistsError):
                publish(old, b"new")
            self.assertEqual(old.read_bytes(), b"KEEP")
            out = root / "out"
            with patch("instrumentzero.session.os.fsync", side_effect=OSError("synthetic failure")):
                with self.assertRaises(OSError):
                    publish(out, b"complete")
            self.assertFalse(out.exists())
            self.assertFalse(list(root.glob("*.pending")))
            publish(out, b"complete")
            self.assertEqual(read_file(out), b"complete")
            fifo = root / "fifo"
            os.mkfifo(fifo)
            with self.assertRaises(MeasurementError):
                read_file(fifo)
            link = root / "link"
            link.symlink_to(out)
            with self.assertRaises(OSError):
                read_file(link)
