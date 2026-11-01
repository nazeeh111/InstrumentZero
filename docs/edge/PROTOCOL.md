# IZP1 protocol and session contract

Every packet is prefixed with its **uint32 little-endian byte length**, not including the prefix. The packet has an 80-byte header, timestamp offsets, interleaved float32 values and a four-byte CRC32 (IEEE polynomial). CRC detects transmission faults; it is not authentication.

| Byte offset | Type | Meaning |
|---|---|---|
| 0 | 4 bytes | `IZP1` |
| 4 | uint8 | Version 1 |
| 5 | uint8 | Kind 1 raw, 2 calibrated, 3 filtered/decimated |
| 6 | uint16 | Flags: bit 0 clipping, bit 1 overrun/fetch failure; others rejected |
| 8 | 16 bytes | Session UUID |
| 24 | uint32 | Configuration epoch |
| 28 | uint32 | First sample sequence, modulo 2^32; independent sequence per kind |
| 32 | uint64 | First device-relative timestamp, microseconds |
| 40 | uint32 | This stream's nominal rate in Hz |
| 44 | uint16 | 1–256 sample frames, also bounded by configured block size |
| 46 | uint16 | 1–3 channels |
| 48 | 32 bytes | Exact canonical specification SHA-256 |
| 80 | n × uint32 | Timestamp offsets from first timestamp; first is zero |
| 80+4n | n × channels × float32 | Little-endian interleaved samples |
| end−4 | uint32 | CRC of all preceding packet bytes |

The maximum encoded packet is 4180 bytes; configured block/channel bounds may be smaller. Lengths, offsets, version/kind, flags and CRC are checked before trusting array dimensions. Nonfinite or out-of-range representations fail. First sequence is zero; gaps, repeats and reorder poison the epoch. Reuse after a fault requires explicit reconfiguration or a new session. Source clipping is checked against its declared range. Unknown or mismatched configuration identities never merge.

A producer enqueues bounded packet bytes. A consumer validates and processes them. Queue overflow stops capture and invalidates analysis; no silent drop-oldest behavior exists. The C core has bounded state, no heap, and transactional argument/capacity/nonfinite rejection. Arbitrary chunk boundaries preserve FIR and decimation phase. A state reset clears filter history and startup validity.

A configuration change increments the host epoch, drops queued old packets, resets processing and invalidates analysis/export. Disconnect/cancel closes the host device handle and ends the session. Reconnection must create a new UUID. The provisional firmware starts a new UUID for each start command; its compiled configuration is epoch zero. It currently requires a newly compiled binding for hardware configuration changes. Runtime firmware reconfiguration is an open physical-integration gate, not demonstrated by the browser's simulated reconfiguration.

The firmware source timestamps in the Zephyr driver's acquisition-thread callback **before** sensor fetch. This includes interrupt/thread scheduling delay and is not the MEMS conversion instant. A 32-bit CPU cycle counter is extended modulo 2^32 between frequent callbacks and converted to microseconds. A gap exceeding half-range is ambiguous and must not be used to infer a clock history. The host helper rejects half-range ambiguity; actual firmware rollover and interrupt-loss behavior remain hardware checks. Source sequence counts delivered driver samples, not an independent sensor sample counter. Timing gaps can expose losses; coalesced/hidden sensor losses are not proven absent.

Nominal rate and measured timestamp rate are separate. The host rejects large period jumps and sample-rate disagreement, reports observed period jitter, and refuses uniform-sample fitting above its explicit jitter tolerance. These checks do not calibrate the clock. Device-relative time has no shared UTC origin or independently verified host clock mapping. Accurate cross-instrument phase/latency requires an independently recorded synchronization event and drift/scale characterization.

Raw recording import preserves an operator-declared linked-image hash and labels it as not device-attested. The binary frame binds configuration, not firmware attestation. Firmware binary hash, board/sensor revision, driver/OS version and calibration provenance must be supplied and verified during physical commissioning.
