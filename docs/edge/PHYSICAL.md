# Physical confirmation plan: not executed

No physical setup is available. The following is an editable acceptance procedure, not an experiment report or a certified fixture design. It does not authorize purchasing, wiring, energizing or flashing equipment.

## Equipment and safe limits

Inspect and record exact board, accelerometer/carrier, supply, cables, cantilever material/dimensions/mass, clamp and reference camera/instrument. Keep the development board off the moving beam. Use a lightweight sensor and strain-relieved flexible wires; weigh attached sensor/wire mass and document placement. If the reference can see the beam without the sensor, compare sensor-mounted and unmounted resonance to bound sensor loading.

Use a securely clamped, low-energy flexible strip with a protected free end, away from eyes, brittle/sharp materials, mains wiring and valuables. Begin with a small displacement visible to the reference, suggested at most 1 mm as a conservative starting protocol, not a universal safe-load rating. Reduce displacement or stop if mounting slips, permanent deformation appears, cables snag, the strip can eject, or anyone is near its motion. Exact safe displacement/load must follow the actual material/geometry and fixture review. No motor, shaker, custom PCB or high-energy excitation is required.

## Calibration and reference suitability

1. Verify every electrical connection against the exact carrier and DK revision. Back up existing device contents and test recovery before any separately authorized flash.
2. With sensor supported, record orientation, bias, full-scale configuration and sensitivity uncertainty. A stationary gravity check can diagnose axes/bias but does not calibrate dynamic frequency response or shared clock error.
3. Characterize sample rate, timestamp location, jitter, FIFO/IRQ losses, rollover, clipping, device unplug/reconnect, stop and release. Record complete failures and packet bytes. Measure full linker memory, stack/queue high-water marks and utilization where observable.
4. Separately acquire a camera-motion trace or reference-instrument recording during each trial. Check its independent clock/frame times, exposure, effective bandwidth, spatial scale, dropped frames and gain. A nominal camera frame rate alone is inadequate. Choose excitation frequencies sufficiently below its effective Nyquist/bandwidth, with enough samples per cycle and record length to resolve modes/decay.
5. Record a shared visible/measurable synchronization event to characterize clock offset/drift. A second calculation of the accelerometer stream is not a second measurement. Retain raw independent reference frames/values and the extraction source.

## Development and held-out confirmation

Assign whole session IDs to development or confirmation before fitting. At each of at least two controlled mounting conditions, release and freshly remount the strip, repeat calibration notes, and record the remount identity. Keep all trials, including weak, clipped, multiple-mode, failed and rejected records. Never split adjacent windows of the same session across development and confirmation.

Use development sessions to choose reviewed primitives, passband/anti-alias/rate settings, placement budgets and fit/rejection rules. Freeze source commit, calibration records, operator/placement rules, cost profiles and the signed confirmation schedule before examining confirmation data. No rules are tuned on the confirmation results.

Evaluate raw-host, sensible fixed-edge and chosen placements on equivalent inputs. Retain a raw validation stream during development and validation. Measure actual framed bytes, startup/transport overhead, acquisition-to-result latency, jitter/drops, memory and utilization. Measure power only with an appropriate instrument; otherwise leave it unknown. The worst observed time is not a hard real-time guarantee.

Compare resonance and only identifiable damping against the separately acquired reference. Include clock and scale uncertainty, aliasing, sensor loading, mounting variation, shared calibration, reference extraction and model mismatch in the uncertainty budget. Follow [NIST TN 1297](https://www.nist.gov/pml/nist-technical-note-1297) for documented standard/combined uncertainty and coverage assumptions. Do not let repeated windows shrink shared calibration error. Reject damping when decay, length or the model fit is inadequate. Compare fresh confirmation sessions without discarding unfavorable trials.

## Completion gates

Through the installed interface, change a supported specification, observe a real mounting change, obtain a checked result, reject an unsuitable signal and recover from actual disconnection. Export raw sensor/reference observations, protocol, configuration, firmware identity, calibration and executable analysis. Recompute on an independent installation. Only then can acquisition and measurement gates be assessed. This preview cannot claim universal stiffness, damage detection or safety certification.
