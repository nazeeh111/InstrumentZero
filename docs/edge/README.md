# InstrumentZero Edge: software preview

One explicit specification binds channels, units, rate, clock assumptions, calibration identity, a reviewed filter and ringdown estimator. The compiler supports one intentionally bounded six-node graph. It rejects other topologies, cycles, implicit unit conversions, unsupported rates, allocations and filters that miss their declared response budgets.

**No physical setup is available.** This preview can test software, expose failures and recompute synthetic or consented recorded inputs. It cannot establish sensor operation, physical sample timing, mounting repeatability, independent measurement agreement, MCU execution speed or power. The earlier v0.2 calibrated-recording release remains available and is not fresh physical validation for Edge.

## Install and use

Python 3.11+ and a free local C99 compiler (Clang or GCC) are required. The numerical core is compiled from the reviewed packaged C source, without a network request, into a unique temporary folder. No device is opened by the Lab or simulation commands.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-runtime.lock
python -m pip install --no-deps .
instrumentzero edge spec > experiment.json
instrumentzero edge compile experiment.json --output compiled-run
instrumentzero edge simulate --spec experiment.json --scenario mount_a --export mount-a.zip
instrumentzero edge simulate --spec experiment.json --scenario mount_b --export mount-b.zip
instrumentzero edge simulate --scenario silence
instrumentzero lab --port 58129
```

Open `http://127.0.0.1:58129/edge`. Change Mount A to Mount B and run again. Change a reduction or resource setting and observe that the prior result/export disappear. Try silence, changing frequency, close modes or saturation. The last case is an acquisition failure, rather than a numeric measurement. The interface never enables a sensor.

Exported evidence contains exact raw float32 samples and per-sample timestamps, IZP1 packets, specification/calibration identities, compiled coefficients, measured host cost profile, results, source, licenses and a SHA-256 manifest. Extract into an empty folder and run `python recompute.py`. It verifies every included file before running. The included source, NumPy/SciPy and local compiler are sufficient. Physical latency and performance need not match on another computer; numeric results use explicit tolerances. Do not run source from an untrusted archive without reviewing it.

## Placement contract

Candidates are raw streaming to host, calibration at the edge, and calibration plus FIR/decimation at the edge. Ringdown optimization remains on the host. Each cut actually encodes and decodes float32 IZP1 frames in the software execution path. Length prefixes, header and timestamp bytes count; a required raw validation stream counts as an additional stream. Raw samples are retained in evidence even when a simulated reduced stream is evaluated. A reduced stream alone cannot reconstruct discarded samples.

A deterministic enumeration rejects candidates outside bandwidth, declared processing/transport RAM and modeled block/transport/filter-delay latency budgets. It then minimizes normalized transfer plus a processing-cost proxy. Host measurements include C binding/array overhead. They are **not MCU cost measurements**. The total RAM budget includes an explicit fixed OS/driver/stack reserve and bounded processing/transport workspaces; it is checked separately against linker memory. Runtime high-water usage remains unmeasured. The firmware build separately reports linker memory. Models use an observed maximum; they do not establish a hard real-time bound. Per-mode host wall time includes processor initialization, software transport and analysis. A separate whole-workflow timer includes graph compilation, planning/cost measurement, numerical reference and native library startup. It excludes interpreter imports, prior signal generation and export. Physical acquisition-to-result latency is null, as are power and MCU utilization.

The compiler checks the float32 FIR response on a dense grid, including declared passband ripple and stopband attenuation. Decimation is restricted to supported integer divisors and continuous state. Zero-state startup samples are excluded from analysis; linear phase group delay is explicit. Filter response is not an analog sensor alias bound. Out-of-band energy could alias **before** the digital filter and must be bounded with actual sensor/reference bandwidth tests.

Every run compares native output with independently implemented float64 affine calibration and SciPy filtering on identical raw input. It compares frequency and identifiable damping against the numerical reference under declared budgets. Another calculation on those samples is not an independent physical measurement. Synthetic confirmation tests check known truths, unsuitable signals and host-favored graphs; no result is generalized to all physical signals.

## Measurement limits

The estimator fits one decaying sinusoid plus offset. It rejects insufficient cycles, weak/out-of-band signals, multiple strong modes and poor fits. Damping additionally requires enough observed decay, retained signal duration and a stricter fit. Frequency is accompanied by a resolution/declared-clock envelope, not a validated 95% interval. Calibration uncertainty is shared; no amplitude, stiffness, damage or safety certification is inferred. Signed gains declare orientation; they are not automatic orientation calibration.

Source values are float32 little endian in acceleration (`m/s^2`) or normalized audio full scale (`FS`). Audio is never implicitly converted to pascals, downmixed, resampled or gain-corrected. A consented signed PCM16/PCM32 WAV may use the WAV adapter, with unknown prior gain control/resampling and nominal file-clock timestamps marked in provenance. See `examples/edge/audio-spec.json`. No newly recorded microphone data is included.

## Verification and next gates

See [API and integration examples](API.md), [protocol](PROTOCOL.md), [provisional firmware](FIRMWARE.md), [physical validation](PHYSICAL.md), and [release evidence](VALIDATION.md). Software verification requires executed reference/protocol tests, sanitizer checks and actual cross-compilation. Acquisition verification additionally requires operation of the supported physical sensor adapter. Measurement verification additionally requires fresh, held-out independent physical comparisons. Simulation cannot satisfy the latter two gates.

The design is informed by [Zephyr native simulation](https://docs.zephyrproject.org/latest/boards/native/native_sim/doc/index.html), [NIST TN 1297](https://www.nist.gov/pml/nist-technical-note-1297), and [Bluesky](https://github.com/bluesky/bluesky). Native simulation exercises software and does not simulate physical sampling accuracy. Bluesky is a broader acquisition/orchestration system; Edge's contribution here is a bounded measurement specification and explicit host/edge placement comparison. No Bluesky source or model weights are included.
