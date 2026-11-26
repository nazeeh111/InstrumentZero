# Ringdown figure provenance

The current README images, `studio-trace.png` and `studio-trace-mobile.png`, are live Chrome captures of the local Ringdown studio at 1280 and 390 CSS pixels. Run the README’s custom model in the studio with 8 seconds and 4× decimation. Both plots show the selected placement’s processed samples after FIR startup, with time zero at the first plotted sample. The dashed upper and lower curves use the fitted offset plus or minus fitted initial amplitude times exp(−decay × time). Their separation describes signal magnitude. Frequency resolution, declared clock error and confidence coverage are separate concepts. Use the sample slider for exact stored plotted values, then export `run.json` and the original sample array.

## Earlier stored-trace illustration

`seeded-ringdown.png` and the editable SVG render `../../examples/edge/simulation-confirmation-v0.3-final/custom-1.json` at source commit `c1a252300159e2e8e161db43191aafcbea701077`.

Every one of the 769 stored `plot.time_seconds` / `plot.signal` samples is displayed, without filtering, interpolation, smoothing, fitting, exclusions or normalization. Time is seconds; the stored signal unit is m/s². Connecting lines aid reading between stored plot samples; they are not extra observations. The run is eight seconds; the captured, processed plot segment ends at 7.68 s after the pipeline's boundaries.

The analytic model is 9.75 Hz, decay 0.45 s⁻¹, amplitude 1 and noise RMS 0.0006, seed 9132301. The printed fit, read directly from `independent_numerical_reference.result`, is frequency 9.750006565906396 Hz and decay 0.4499236618270089 s⁻¹. This reference uses NumPy float64 affine processing plus SciPy lfilter on the same captured input. It is not an independent physical measurement. The source also retains raw-host/calibrated-edge/filtered-edge C-path results.

No new solver run, hardware capture or fit was performed to make this figure. The record's resolution/declared-clock envelope is not presented as a confidence interval or validated coverage claim. Raw samples, estimator diagnostics, source identities and explicit simulation/physical boundaries remain in the linked JSON.

## Regenerate the presentation

With existing NumPy and Matplotlib, run `python docs/presentation/render.py` (desktop) and `python docs/presentation/render.py --mobile` (stacked/narrow) from the repository root. It reads the stored source JSON above and writes the PNG, editable SVG and `manifest.json` beside this note. It performs no new solve, fit or experiment. Matplotlib 3.11.2 and NumPy 2.5.4 were used for these outputs. The manifest records exact inputs, transformations and output hashes.
