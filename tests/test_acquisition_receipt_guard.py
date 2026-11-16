"""Current evidence must not execute a historical app override."""
import os
import shutil
import subprocess
import sys
from pathlib import Path


def test_historical_override_refused_before_runner_or_receipt(tmp_path):
    root = Path(__file__).resolve().parents[1]
    workspace = tmp_path / "workspace"
    (workspace / "scripts").mkdir(parents=True)
    (workspace / "src/instrumentzero/web").mkdir(parents=True)
    shutil.copyfile(root / "scripts/validate_acquisition.py", workspace / "scripts/validate_acquisition.py")
    (workspace / "src/instrumentzero/web/app.js").write_text("broken current app\n")
    marker = tmp_path / "node-was-called"
    node = tmp_path / "node"
    node.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 0\n")
    node.chmod(0o755)
    output = tmp_path / "current-receipt"
    env = dict(os.environ, INSTRUMENTZERO_TEST_APP_REF="331272ebe5a86248322fc13ee0fb5e6f4b31fe10")
    env["PATH"] = str(tmp_path) + os.pathsep + env.get("PATH", "")
    result = subprocess.run(
        [sys.executable, str(workspace / "scripts/validate_acquisition.py"), "--output", str(output)],
        capture_output=True, text=True, env=env, check=False,
    )
    assert result.returncode == 2
    assert "Unset INSTRUMENTZERO_TEST_APP_REF" in result.stderr
    assert not output.exists()
    assert not marker.exists()
