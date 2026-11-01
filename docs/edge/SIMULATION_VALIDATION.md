# Simulation-only acceptance evidence

The current project is a complete software simulation workflow. Physical equipment and independent physical measurements are outside its completion scope. This report covers numerical behavior, provenance, source reproduction and the installed interface; it makes no hardware-performance claim.

## Executed local checks

The full Python suite passed 187 tests in 16.76 s. Browser logic passed 32 tests, and Ruff passed. New tests cover finite/bounded custom models, typed-constructor validation, source-dependent units/bounds, seeded identity, analytic frequency/damping truth, zero-decay damping rejection, API/CLI custom input, portable truth recomputation, and invalidation after model edits.

Independent read-only review passed 26 focused model/measurement/import tests, one loopback API test and nine browser tests. It also executed an FS-unit custom model and recomputed an exported source package in a separate Python 3.13 environment. A real UI-label/bounds defect was found, corrected and independently checked before freezing acceptance.

The unchanged shared C99 core retains its executed ASan/UBSan harness, C++17 integration and actual Cortex-M4 object evidence from rc3. Its source identity is unchanged. Optional provisional board builds remain historical extension evidence, not simulation acceptance gates.

## Frozen confirmation

The source-bound [plan](../../examples/edge/simulation-plan-v0.3-final.json) defines fresh, explicit model cases, rejection/fault cases, frozen measured-host cost profiles and numerical thresholds before execution. All outcomes, including rejected input, are retained. The initial plan at commit `4e504a9` retained a failed expectation: a fast-decaying signal correctly withheld damping after reaching the noise floor too early, whereas the plan had required damping. That complete failed run remains in `simulation-confirmation-v0.3`. Production rules and thresholds were not loosened. The final plan uses disjoint fresh seeds and explicitly checks correct frequency-only output for this signal. All [13 final cases](../../examples/edge/simulation-confirmation-v0.3-final/results.json) passed after freeze commit `696a112`, with fresh disjoint seeds 9132301–9132313. They include custom/preset models, a host-favored graph, no-decay and fast-decay damping withholding, four unsuitable signals, clipping and session recovery. Maximum observed frequency error across checked analytic cases was 0.00002669 Hz; maximum relative damping error among identifiable cases was 0.00017031. These are bounded numerical results on the specified models, not physical accuracy claims.

## Scope and reproduction

[Model equations and limits](SIMULATION.md), [quickstart](README.md) and [API](API.md) define the supported behavior. Data bytes include packet prefixes/headers/timestamps/CRC but exclude startup/control and electrical framing. Timings are local host observations and proxy costs; physical latency, MCU utilization/power and physical uncertainty coverage are not claimed.

Versioned public release notes retain exact-commit CI and public-download/independent-install checks after those steps execute. Earlier rc1–rc3 reports remain preserved under their original scope.

## Installed interface and comparison

The installed 0.3.0 candidate wheel's 38 runtime files matched the frozen source. Actual desktop and 390 px mobile custom-model views were inspected; mobile body/document widths were both 390 px, with no page overflow. Model edits removed the old export, keyboard Tab moved between custom controls, raw validation selected host processing, silence was rejected with evidence retained, and a restored custom model exported successfully.

| Identical synthetic eight-second data | Raw host | Fixed FIR edge | Planner |
|---|---:|---:|---:|
| Reduced stream permitted | 30,000 B | 10,800 B | 10,800 B |
| Raw validation required | 30,000 B | 40,800 B | 30,000 B |

The planner ties fixed edge in the first case and retains raw host in the second. Counts are framed data bytes, not electrical transfer or startup/control bytes. The current [walkthrough](../../assets/edge-simulation/instrumentzero-simulation-walkthrough.mp4) is a silent, edited sequence of actual installed UI screenshots. Its captures and timeline are retained; it does not pretend to be a continuous recording or a hardware experiment.
