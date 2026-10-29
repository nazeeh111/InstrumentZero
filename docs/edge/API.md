# Edge API and integration examples

The public typed entry points are `EdgeSpec`, `compile_graph`, `EdgeError` and `default_spec` from `instrumentzero.edge`. The bounded specification schema is demonstrated by `examples/edge/simulation-spec.json`, `adxl345-spec.json`, `audio-spec.json` and `host-favored-spec.json`.

```python
from instrumentzero.edge import EdgeSpec, compile_graph, default_spec
from instrumentzero.edge.planner import measure_costs, plan
from instrumentzero.edge.simulation import generate, compare
from instrumentzero.edge.artifacts import export_run
from pathlib import Path

spec = EdgeSpec.parse(default_spec())  # Owns an immutable canonical snapshot.
compiled = compile_graph(spec)
costs = measure_costs(compiled)       # Measured on this host; not MCU costs.
placement = plan(compiled, costs)     # Deterministic for these exact inputs.

samples, ticks, provenance = generate(spec.to_dict(), 'mount_b', seed=20261029, seconds=8)
result = compare(spec, samples, ticks, costs, provenance)
with Path('new-evidence.zip').open('xb') as output:
    output.write(export_run(result, samples, ticks))
```

Input arrays are frame-major `float32` with 1–3 declared channels; per-sample timestamps are integer microseconds. A session contains at most 200,000 frames. The provisional board binding exposes only z, at 100/200/400 Hz, with blocks at most 64. The simulation and WAV adapters support the rates enumerated by the compiler. `FS` means normalized audio full scale, not pressure.

`Session(spec)` owns a fresh UUID and an epoch. `reconfigure(spec)` validates first, increments the epoch, clears queued samples/results, and rejects stale packets. `enqueue(packet)` only accepts bounded bytes; `consume()` performs validation. Queue overflow and packet faults invalidate the epoch. A context manager or `close()` ends the session. A disconnected session cannot be reopened; construct another session. These lifecycle tests are software checks, not real unplug verification.

For the reviewed native primitives, `Processor(scale, offset, coefficients, decimation)` uses the shared packaged C99 implementation. Calibration vectors must match channel count. `process()` preserves state across arbitrary chunks; `reset()` uses a frozen copy of its original configuration. Zero-state FIR startup and phase are explicit. Direct C errors leave state/output unchanged. No arbitrary generated code or graph operator is executed.

## Local HTTP integration

Start `instrumentzero lab`. `GET /api/edge/spec` returns the supported default. `POST /api/edge/run` accepts a JSON object with `spec`, `scenario`, `seconds` and `seed`. Simulation is the only source permitted by this web endpoint; it never opens hardware. Browser requests must be same-origin. Non-browser clients obtain `/api/session` and send its token in `X-InstrumentZero-Token`. Bind only to loopback; no public server mode exists.

The response contains the compiled contract, source label, measured host cost profile, all placement outcomes and `artifact_url`. The artifact cache keeps the latest four successful exports. The URL points to the exact result's source/data package, rather than regenerating a different request. Configuration changes invalidate the browser's old result/export. An expired URL returns an explained error.

For consented local recording imports, use `edge recording` or `edge protocol`. Protocol imports retain the original device packet file and compare supplied calibrated/filtered values with the raw numerical reference. Imported firmware identity is operator-declared, not device-attested. `edge capture` is an explicit POSIX serial command and has not been exercised on physical equipment. See [firmware limits](FIRMWARE.md).

## C++ caller

[cpp-integration.cpp](../../examples/edge/cpp-integration.cpp) wraps the C header in `extern "C"` and links against the separately compiled C99 implementation. `scripts/verify_edge_core.py` builds and executes this C++17 example along with the sanitizer and ARM checks. The numerical implementation stays in C99.
