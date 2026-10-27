# Engine, units and data contracts

`MeasurementSpec.parse(dict)` validates the public specification. `compile_experiment(spec)` generates a bounded model-specific plan. `analyze_stiffness(spec, rows)` and `analyze_audio(spec, samples, sample_rate_hz)` run the underlying inference. Failures raise `MeasurementError`, a `ValueError` subclass. No function actuates equipment.

## Specification

Required: `domain` (`stiffness` or `acoustic`) and a supported `question`. Available equipment is a list of descriptive strings, not proof of a connection. The question compiler uses a supported vocabulary and physical model templates; it is not a general-language reasoning model.

| Field | Meaning |
|---|---|
| `target_relative_uncertainty` | Requested relative half-width, e.g. .05; conditional on the stated uncertainty method |
| `budget_seconds` | Remaining acquisition budget, 1–3600 s; not wall-clock computation or previously spent time |
| `max_force_n` | Human-declared range ceiling, positive and ≤10 N; not a specimen safety certificate |
| `min_frequency_hz`, `max_frequency_hz` | Positive search band, strictly below Nyquist during analysis |
| `source_kind` | `synthetic`, `recorded`, `imported`, or `live`; user-declared evidence class, not an engine attestation |
| `source_name` | Human-readable source identity |
| `source_limitations` | Retained source caveats, also written to exports |
| `calibration_basis` | Origin of calibration values; certificates are not verified automatically |
| `source_attribution` | Structured creators, title, source/license URLs and modifications, retained in portable DATA-NOTICES.txt |
| `reference` | Optional `{value,unit,kind}` for a declared reference comparison; independent truth is not inferred |

Pixel observations require `calibration.meters_per_pixel` and `pixel_noise_sd`, both positive. `scale_relative_sd` and `force_relative_sd` are shared multiplicative standard uncertainties, not independent row noise. Zero explicitly assumes an exact scale and raises a warning. Common scales use positive lognormal factors with the declared relative SD. Per-point force noise is not modeled; material uncertainty in individual loads requires another model.

Audio requires `sample_clock_relative_sd`; zero explicitly assumes an exact clock. `interval_95` is retained as a common result-schema field, but acoustic results attach `interval_label` explicitly stating that its envelope has no validated 95% coverage. Clients must display that label. It combines FFT resolution, window scatter and shared clock uncertainty; it is not a formal posterior over arbitrary audio.

`compile_experiment(...).identifiable` describes calibration readiness in the specification. It cannot establish the rank/sampling of observations it has not seen. SI displacement imports with explicit `sigma_m` can be valid even when a pixel-calibration plan is not ready; the analyzer checks the actual route. `identifiability_scope` states this distinction.

## Observations and results

Stiffness uses a uniform list of `{force_n, position_px}` **or** `{force_n, displacement_m, sigma_m}` rows. At least four finite observations, two distinct forces, and positive observation noise are required. Forces must stay in the declared range. Mixed routes, nonfinite values and degenerate designs fail. Strong curvature or residual inconsistency marks a result unreliable. If compliance crosses zero, stiffness is unbounded and its value/interval are null, never NaN or infinity.

Audio is mono floating-point amplitude in [-1,1], at least .25 seconds and at most two million samples. The engine selects up to ten seconds near the strongest signal region and records its exact sample range. Anti-aliasing resampling precedes reduced-rate analysis. A Hann spectrum initializes a variable-projection sine fit. Boundary peaks and unusable sampling fail; residual energy, competitors and window instability guard reliability.

Results contain `quantity`, `fit`, `calibration`, `warnings`, `assumptions`, `next_experiment`, `model_comparison`, and SHA-256 `provenance`. A `reliable` label means the implemented checks passed conditionally; it is not independent physical verification. `target_reached` is false for unreliable results. Stiffness adds actual prefix `uncertainty_history`; audio adds `spectrum` and `waveform`. Next actions are explicitly proposed, respect the stated budget and never represent observations already acquired.

## Local HTTP

The Lab binds `127.0.0.1`. GET `/api/health`, `/api/session`, `/api/demo/stiffness`, `/api/demo/stiffness/recorded`, `/api/demo/acoustic` and `/api/demo/acoustic/samples`. POST `/api/compile` takes a specification; `/api/analyze` takes `{spec,rows}`; `/api/audio` takes `{spec,samples,sample_rate_hz}`; `/api/export` takes the same observation payload and returns ZIP bytes. Error responses contain `error` and a non-200 status.

Same-origin browser POSTs are accepted. A non-browser client obtains the per-process `/api/session` token and sends `X-InstrumentZero-Token` with `Content-Type: application/json`. Host and Origin are validated. Requests are capped at 64 MiB; this single-user server is not designed for untrusted network exposure or concurrent heavy jobs.
