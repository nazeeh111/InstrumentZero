# Launch draft: InstrumentZero Edge software preview

Draft only. No social post, email, forum message or outreach has been sent.

## Short project update

InstrumentZero Edge is a local measurement compiler that lets one specification control a signal's units, calibration, filtering, recording and host/edge placement.

The software preview compares raw streaming, a fixed edge pipeline and a deterministic placement planner on identical input. In the retained synthetic test, reduction cuts framed transfer from 30,000 to 10,800 bytes. The planner ties the fixed edge pipeline there. When raw validation is required, it keeps processing on the host and avoids an extra stream.

The release includes a shared C core, protocol and numerical tests, three actual Zephyr firmware builds, a local interface, raw sample exports and source that recomputes the result. No physical setup was available. Sensor operation and independent physical measurement validation are still open, and MCU speed or power is not claimed.

Source and evidence: https://github.com/nazeeh111/InstrumentZero

## Technical discussion opener

I wanted the placement decision to preserve the measurement, including what happens when an edge pipeline discards samples. The current design uses reviewed operators, explicit units, filter-response checks, configuration epochs and raw validation when it is needed. It keeps the planner deterministic and uses measured host costs until hardware costs can be obtained.

A useful next evaluation would be fresh cantilever remounts with a separately recorded camera or reference instrument. The current software evidence cannot substitute for that comparison.

## Relevant audiences and boundaries

This may fit an existing discussion about scientific data acquisition, reproducible DSP or small embedded instruments when its limitations answer a real question. Share the exact relevant example and evidence if invited. Do not claim adoption, traceable physical calibration, power savings, hard real-time behavior or hardware support established only by a build. No bulk outreach or unsolicited promotional replies are part of this release.
