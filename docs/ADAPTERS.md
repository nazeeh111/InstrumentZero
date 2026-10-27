# Sensor adapters and tested boundaries

The reliable core accepts physical observations with explicit units and provenance. Instrument communication is a separate boundary.

| Path | Current implementation | Verification |
|---|---|---|
| CSV force/position | CLI and Lab import | Synthetic controls, authentic source data, invalid-input tests |
| WAV audio | SciPy PCM/float loader and analysis | Known tones, adverse signals, authentic recording |
| Browser audio files | Native decode and 16 kHz resampling, first 20 s | UI exercised; codec support follows browser |
| Microphone | Deliberate permission, then capture; local samples | Shared production code tested on generated media/mocks; actual device unverified |
| Webcam | Deliberate permission, selected dark fiducial, settled positions | Shared tracker/capture code tested on synthetic frames; actual optical calibration unverified |
| Phyphox | Offline `/get` response validation | Contract tests; no phone connected |
| PyVISA / PyMeasure / Bluesky | Documented extension targets | No adapter or live instrument connection claimed |

## Phyphox exports

`instrumentzero.adapters.phyphox_buffers(response, time_buffer, value_buffer)` consumes an explicitly obtained response from the [documented remote interface](https://phyphox.org/docs/remote-interface/). Requested buffers must exist and align. Nonfinite/null observations and non-increasing time fail. Irregular sampling is flagged rather than silently converted to a uniform rate. Units come from the actual experiment configuration. Session identity is retained.

```python
import json
from instrumentzero.adapters import phyphox_buffers
response = json.load(open("phone-response.json"))
signal = phyphox_buffers(response, "time", "audio")
# Check the actual configured units and clock calibration before audio analysis.
```

The client does not discover phones, enable remote access, pair a device, copy GPL experiment XML, or call control/set endpoints. The user obtains a response only after deliberately enabling a phone experiment. A fixture proves parsing, not a device connection.

## Optional instrument work

Bluesky already supplies orchestration/metadata/recovery; PyVISA supplies transport/backends; PyMeasure supplies named instrument drivers. Reuse these if adding a supported device, pin compatible versions and test a narrow operating envelope. Current Bluesky Adaptive crosses a substantial 0.x/1.0 API boundary; old snippets are not a verified integration. Do not emit arbitrary SCPI commands or infer safety from a device being discoverable. No extra dependency is needed for the supported local workflows.

The Replay & validation workspace adds actual public PTB calibrated-level records and sequential stiffness replay without device access. See [recording-based validation](NO_EQUIPMENT_VALIDATION.md). The 18 generated-media/mocked acquisition checks cover software contracts and cancellation, not physical transfer functions or browser anti-alias DSP quality.
