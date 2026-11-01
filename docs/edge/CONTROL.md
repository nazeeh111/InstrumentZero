# Runtime configuration: implementation contract

This work adds software-tested configuration of the provisional ADXL345 adapter without rebuilding it for every supported specification. Physical behavior remains unverified. Existing v0.3.0-rc.1 artifacts retain their original compiled-configuration contract.

Only the reviewed z-axis acceleration graph is supported. Rates are 100/200/400 Hz; signed calibration, FIR coefficients, 1/2/4/8 decimation, placement and raw validation may change. The acquisition block and queue envelope must exactly match the flashed binding. Different allocation envelopes still need a reviewed build. The host checks graph, units, filter response and resource budgets before generating a request. Firmware checks binary integrity, rate, allocation envelope and bounded numerical representations; it cannot attest the full JSON or physical calibration.

The host sends `C`, a little-endian uint16 payload length, then IZC1. Firmware stops acquisition before reading configuration. The payload contains version, opcode, raw-validation flag, random request ID, rate, block/queue sizes, taps, decimation, placement, specification SHA-256, signed scale/offset, float32 coefficients and CRC32. The maximum payload is 1,092 bytes. There is no arbitrary code execution or memory allocation.

A fixed 68-byte IZA1 response binds request ID, accepted specification hash, placement, raw-validation flag, device-selected epoch and a fresh session UUID. CRC32 detects transmission errors, not malicious forgery. The host requires this exact acknowledgement before sending `G`. A new valid configuration advances the epoch and replaces the session, clears queued samples and resets filter/sequence state. Rejected, partial, timed-out or overflowing requests disarm `G`; no stale configuration is started accidentally. `S` disarms and stops; `K` keeps an active capture alive. No heartbeat for two seconds stops acquisition. A configuration response does not enable acquisition callbacks or emit samples. It may change the sensor sampling-rate register. An unused acknowledgement expires after two seconds.

UART reception uses an interrupt-driven 2,048-byte single-producer/single-consumer ring. Overflow poisons the stream, disables receive interrupts and ends acquisition; it requires a clean device restart, rather than interpreting retained partial bytes as commands. The ring, active/pending configurations, bounded control frame and acknowledgement use an explicit 6,144-byte reserve; the processing state is reserved even in raw mode. The current board example declares a 40,960-byte total planning budget and a 6,144-byte main stack. The stack was increased after compiler allocation reports showed a 2,672-byte main frame plus a 1,160-byte configuration decoder frame; those reports are not runtime high-water measurements. The ring accommodates a complete maximum configuration request even while the previous raw-plus-filtered block finishes transmission. C11 atomics provide the ISR/main memory-order boundary; the numerical core remains C99-compatible.

Configuration reception is bounded to 500 ms from the initial `C`. A malformed request is rejected; a fresh complete request is required. During reception every byte belongs to the transaction, so embedded command characters have no control meaning. Start requires a newly accepted configuration. Epoch wrap refuses further configuration until a reboot creates a new UUID namespace. Firmware identity remains operator-declared, not device-attested.

Capture preserves the exact configuration and acknowledgement in its trial sidecar, plus the timestamped IZP1 data in its original file. No raw samples from separate sessions or epochs may be spliced. Numerical validation of edge outputs still requires a raw validation stream; discarded samples cannot be recovered from reduced data.

Software acceptance includes native C parser checks under sanitizers, byte-for-byte Python/C round trips, CRC-valid invalid fields, truncation, stale acknowledgements, partial writes, transaction timeout, cancellation and same-port reconfiguration. Full board compilation is required separately. None of these proves physical sampling, driver reconfiguration timing, actual unplugging or independent measurement accuracy.

## Use the API and CLI

Compile bytes for inspection without opening a port:

```sh
instrumentzero edge control examples/edge/adxl345-spec.json --output reviewed-request.izc
```

After inspecting actual equipment, using compatible firmware and obtaining recording consent, `edge capture` performs stop/configure/ack/start automatically. It never flashes. The `--placement` option selects raw-host, calibrated-edge or filtered-edge processing. Non-raw captures require `resources.raw_validation=true` and sufficient declared bandwidth so their retained raw stream can check the device result. A new block/queue allocation envelope still requires a matching firmware build. Old rc1 firmware cannot acknowledge this protocol; the host fails rather than silently falling back to an unchecked start.

For an already consented, explicitly owned `SerialPort`, `DeviceController(port).configure(spec, placement)` returns the accepted session/epoch and exact request/reply bytes. Call `start()` within 1.8 seconds, read that trial, then `stop()`. Configure again before every new start. The same controller can apply another supported specification after stopping. Every error invalidates its accepted configuration. Closing the serial context sends stop even if configuration was accepted but start was never sent. A firmware overflow requires a clean restart; do not reuse a poisoned partial stream.

The capture sidecar records protocol byte counts, rejected/prior bytes encountered before the matching ACK, validation/open/configuration time, start-to-first-read time and time through data flush. The return value also measures the complete host capture call. These are host observations, without a calibrated physical aperture or shared device clock. UART 8N1 and USB electrical framing are not measured. Analysis and physical acquisition-to-result latency remain separate and unverified.

## Binary layout

All multibyte fields are little endian. An IZC1 payload follows `C` and its two-byte payload length. Floats are IEEE-754 binary32.

| Payload offset | Field |
|---:|---|
| 0 | `IZC1` magic (4 bytes) |
| 4, 5 | Version 1, configure opcode 1 |
| 6 | uint16 flags: bit0 requires raw validation, other bits zero |
| 8 | uint32 random request ID |
| 12 | uint32 input rate (100, 200 or 400 Hz) |
| 16, 18, 20 | uint16 block size, queue blocks, odd tap count |
| 22, 23 | uint8 decimation (1/2/4/8), placement (0 raw/1 calibration/2 FIR) |
| 24 | 32-byte canonical specification SHA-256 |
| 56, 60 | float32 signed calibration gain and offset |
| 64 | Reserved uint32, must be zero |
| 68 | Tap-count float32 coefficients |
| 68 + 4 × taps | CRC32 of the preceding payload bytes |

IZA1 is fixed at 68 bytes, without a length prefix. Offsets0..3 contain `IZA1`, offset4 is version1, offset5 is status (0 accepted,1 invalid,2 timeout,3 epoch exhausted), offset6 is placement, offset7 is raw-validation boolean, offset8 is the echoed uint32 request ID, offset12 is the assigned uint32 epoch, offset16 is a16-byte UUID, offset32 is the32-byte spec hash, and offset64 is CRC32 over bytes0..63. Rejected requests never authorize `G`. A malformed header may not retain a request ID, so the host may observe a timeout rather than a correlated rejection.
