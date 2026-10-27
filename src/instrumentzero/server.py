"""Loopback-only Lab server with no remote device control or arbitrary file endpoints."""
from __future__ import annotations

import json
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from . import __version__
from .acoustic import analyze_audio, load_wav
from .calibrated import calibrated_acoustic_validation, export_calibrated_package
from .engine import analyze_stiffness, compile_experiment
from .examples import acoustic_example, recorded_stiffness_example, stiffness_example
from .export import export_package
from .replay import export_replay_package, recorded_stiffness_replay
from .spec import MeasurementError


def make_server(port: int = 8765, data_dir: Path | None = None) -> ThreadingHTTPServer:
    web = Path(__file__).parent / "web"
    data_dir = (data_dir or Path("data")).resolve()
    token = secrets.token_urlsafe(32)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            return  # Sensor observations and questions never appear in access logs.

        def _send(self, value, code=200, content_type="application/json"):
            data = value if isinstance(value, bytes) else json.dumps(value, allow_nan=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                             "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; frame-ancestors 'none'")
            if content_type == "application/zip":
                self.send_header("Content-Disposition", 'attachment; filename="instrumentzero-evidence.zip"')
            self.end_headers()
            self.wfile.write(data)

        def _host_ok(self):
            return self.headers.get("Host") in {f"127.0.0.1:{self.server.server_port}",
                                                 f"localhost:{self.server.server_port}"}

        def do_GET(self):
            if not self._host_ok():
                return self._send({"error": "Use the loopback Lab URL."}, 403)
            path = urlsplit(self.path).path
            try:
                if path == "/api/health":
                    return self._send({"status": "ok", "version": __version__, "device_connections": 0})
                if path == "/api/session":
                    return self._send({"token": token})
                if path == "/api/demo/stiffness":
                    return self._send(stiffness_example())
                if path == "/api/demo/stiffness/recorded":
                    return self._send(recorded_stiffness_example(data_dir))
                if path == "/api/demo/acoustic":
                    return self._send(acoustic_example(data_dir))
                if path == "/api/demo/acoustic/samples":
                    paths = list(data_dir.glob("*440*.wav"))
                    if not paths:
                        raise MeasurementError("Recorded acoustic fixture is absent.")
                    samples, rate = load_wav(paths[0])
                    return self._send({"samples": samples.tolist(), "sample_rate_hz": rate})
                if path in {"/api/replay", "/api/replay/export"}:
                    query = parse_qs(urlsplit(self.path).query)
                    options = {"measurement_budget": int(query.get("budget", ["4"])[0]),
                               "policy": query.get("policy", ["information_gain"])[0],
                               "random_seed": int(query.get("seed", ["0"])[0])}
                    if path.endswith("/export"):
                        return self._send(export_replay_package(data_dir, **options), content_type="application/zip")
                    return self._send(recorded_stiffness_replay(data_dir, **options))
                if path == "/api/validation/ptb":
                    return self._send(calibrated_acoustic_validation(data_dir))
                if path == "/api/validation/ptb/export":
                    return self._send(export_calibrated_package(data_dir), content_type="application/zip")
                if path == "/api/validation/software":
                    examples = data_dir.parent/"examples"
                    acoustic = examples/"acoustic-acceptance-v0.2/results.json"
                    acquisition = examples/"acquisition-acceptance-v0.2/results.json"
                    return self._send({"acoustic": json.loads(acoustic.read_text()) if acoustic.is_file() else None,
                                       "acquisition": json.loads(acquisition.read_text()) if acquisition.is_file() else None,
                                       "physical_hardware_acceptance": "Not verified by these software tests"})
                allowed = {"/": ("index.html", "text/html; charset=utf-8"),
                           "/index.html": ("index.html", "text/html; charset=utf-8"),
                           "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                           "/acquisition.js": ("acquisition.js", "text/javascript; charset=utf-8"),
                           "/validation.js": ("validation.js", "text/javascript; charset=utf-8"),
                           "/style.css": ("style.css", "text/css; charset=utf-8"),
                           "/mark.svg": ("mark.svg", "image/svg+xml"),
                           "/favicon.svg": ("favicon.svg", "image/svg+xml")}
                if path not in allowed:
                    return self._send({"error": "Not found"}, 404)
                filename, mime = allowed[path]
                return self._send((web / filename).read_bytes(), content_type=mime)
            except (MeasurementError, OSError, ValueError) as exc:
                return self._send({"error": str(exc)}, 422)

        def do_POST(self):
            if not self._host_ok():
                return self._send({"error": "Use the loopback Lab URL."}, 403)
            origin = self.headers.get("Origin")
            if origin is not None and origin not in {f"http://127.0.0.1:{self.server.server_port}",
                                                    f"http://localhost:{self.server.server_port}"}:
                return self._send({"error": "Cross-origin requests are not permitted."}, 403)
            # Browser Origin protects the web UI. CLI clients may send no Origin and use the session token.
            if origin is None and self.headers.get("X-InstrumentZero-Token") != token:
                return self._send({"error": "Obtain /api/session and send X-InstrumentZero-Token."}, 403)
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 64 * 1024 * 1024:
                    return self._send({"error": "Request must be nonempty and at most 64 MiB."}, 413)
                if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                    return self._send({"error": "Use application/json."}, 415)
                payload = json.loads(self.rfile.read(length), parse_constant=lambda s: (_ for _ in ()).throw(
                    MeasurementError(f"Nonfinite JSON value: {s}")))
                if not isinstance(payload, dict):
                    raise MeasurementError("The request must be a JSON object.")
                path = urlsplit(self.path).path
                if path == "/api/compile":
                    output = compile_experiment(payload)
                elif path == "/api/analyze":
                    output = analyze_stiffness(payload.get("spec"), payload.get("rows"))
                elif path == "/api/audio":
                    output = analyze_audio(payload.get("spec"), payload.get("samples"), payload.get("sample_rate_hz"))
                elif path == "/api/export":
                    return self._send(export_package(payload), content_type="application/zip")
                else:
                    return self._send({"error": "Not found"}, 404)
                return self._send(output)
            except (MeasurementError, ValueError, TypeError, KeyError) as exc:
                return self._send({"error": str(exc)}, 422)

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(port: int = 8765, data_dir: Path | None = None):
    server = make_server(port, data_dir)
    print(f"INSTRUMENTZERO LAB · http://127.0.0.1:{server.server_port}", flush=True)
    print("Local analysis only. Camera and microphone stay off until deliberately enabled in the browser.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
