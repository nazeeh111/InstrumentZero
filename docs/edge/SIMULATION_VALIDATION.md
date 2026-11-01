# Simulation-only acceptance evidence

The current project is a complete software simulation workflow. Physical equipment and independent physical measurements are outside its completion scope. This report covers numerical behavior, provenance, source reproduction and the installed interface; it makes no hardware-performance claim.

## Executed local checks

The full Python suite passed 187 tests in 16.76 s. Browser logic passed 32 tests, and Ruff passed. New tests cover finite/bounded custom models, typed-constructor validation, source-dependent units/bounds, seeded identity, analytic frequency/damping truth, zero-decay damping rejection, API/CLI custom input, portable truth recomputation, and invalidation after model edits.

Independent read-only review passed 26 focused model/measurement/import tests, one loopback API test and nine browser tests. It also executed an FS-unit custom model and recomputed an exported source package in a separate Python 3.13 environment. A real UI-label/bounds defect was found, corrected and independently checked before freezing acceptance.

The unchanged shared C99 core retains its executed ASan/UBSan harness, C++17 integration and actual Cortex-M4 object evidence from rc3. Its source identity is unchanged. Optional provisional board builds remain historical extension evidence, not simulation acceptance gates.

## Frozen confirmation

The source-bound [plan](../../examples/edge/simulation-plan-v0.3.json) defines fresh, explicit model cases, rejection/fault cases, frozen measured-host cost profiles and numerical thresholds before execution. All outcomes, including rejected input, are retained. Current results will be recorded here after the frozen run succeeds; no result is implied by the plan alone.

## Scope and reproduction

[Model equations and limits](SIMULATION.md), [quickstart](README.md) and [API](API.md) define the supported behavior. Data bytes include packet prefixes/headers/timestamps/CRC but exclude startup/control and electrical framing. Timings are local host observations and proxy costs; physical latency, MCU utilization/power and physical uncertainty coverage are not claimed.

Versioned public release notes retain exact-commit CI and public-download/independent-install checks after those steps execute. Earlier rc1–rc3 reports remain preserved under their original scope.
