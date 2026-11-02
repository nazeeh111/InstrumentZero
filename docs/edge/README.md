# InstrumentZero Edge: signal and placement simulation studio

Create seeded signals, estimate resonance and identifiable damping, compare where processing belongs, and export a run that can be recomputed elsewhere. This project is simulation-only. No sensor, camera, microphone, MCU, API key or cloud service is needed.

## Install and run

Python 3.11+ and a free local C99 compiler, Clang or GCC, are required. NumPy and SciPy are pinned by Python version. The shared C core compiles locally from the packaged source, without a network request.

```sh
python -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-runtime.lock
python -m pip install --no-deps .
instrumentzero lab --port 58134
```

Open `http://127.0.0.1:58134/edge`. Run a preset, choose Custom, change frequency/decay/noise/amplitude/seed, and run again. Each edit clears the old result/export. Try silence, changing frequency, close modes, impulse, saturation and simulated disconnect/recovery. Frequency and damping are withheld when the signal or model is unsuitable.

```sh
instrumentzero edge simulate --scenario custom_ringdown --frequency 18.6 \
  --decay .8 --noise .0006 --amplitude 1 --seed 6001 --export custom.zip
instrumentzero edge simulate --scenario silence --export rejected.zip
instrumentzero edge simulate --scenario disconnect_recover
```

Extract an exported package into a new empty folder. Run `python -m pip install -r requirements.txt`, then `python recompute.py`. It uses included source and exact retained data, not your checkout or private caches. Review source from untrusted packages before running it. Install and export never require device permissions.

## What is checked

One typed graph declares channels, units, sample rate, calibration, FIR/reduction, estimation and recording. Only reviewed operators are allowed. Unsupported units/rates, cycles and impossible budgets fail explicitly. The C core preserves state across chunks and resets.

The interface shows an analytic model truth comparison separately from the float64 processing reference. The planner compares raw-host, calibrated-edge and filtered-edge paths on the same synthetic samples. It uses measured local host costs and explicit resource models. It may tie a sensible fixed-edge baseline or prefer the host. It does not promise a universal optimization win.

The model uses an ideal sample clock and seeded analytic signals, not a beam/material or physical sensor simulation. Digital FIR analysis does not establish analog alias immunity. Physical timing, device utilization and power are outside this simulation project's claims. See [model equations, bounds and interpretation](SIMULATION.md).

## Evidence and extensions

[Executed simulation acceptance](SIMULATION_VALIDATION.md) · [Typed API and integration](API.md) · [Protocol and epoch contract](PROTOCOL.md) · [Editable architecture](architecture.mmd)

The original recording Lab remains available at `/`. Consented recording imports and the provisional hardware adapter are optional extensions. Their source and historical build receipts are preserved in [CONTROL.md](CONTROL.md), [FIRMWARE.md](FIRMWARE.md), and earlier release tags. [PHYSICAL.md](PHYSICAL.md) is an optional future commissioning plan, not a requirement for completing or using the simulation project.
