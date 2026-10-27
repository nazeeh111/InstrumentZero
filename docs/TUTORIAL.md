# A question becomes a measurement

## Start with an inspectable control

Run `instrumentzero lab`, open the loopback URL and load the controlled spring example. The observations are synthetic and labeled accordingly. Its true stiffness is 80 N/m; the fitted value is approximately 80.68 N/m. Inspect the residual plot and uncertainty history. Prefix intervals may widen when a new observation challenges earlier assumptions; the UI never forces them to shrink.

Compile the question to inspect the procedure. The model is position = offset + compliance × force; compliance is 1/stiffness. Fitting the offset means a single force cannot identify both unknowns. The next-load recommendation uses conditional variance reduction and an explicit timing assumption, not observed hardware throughput. Collecting it requires a human.

## Import your measurements

For video positions, CSV columns are `force_n,position_px`. For direct SI measurements use `force_n,displacement_m,sigma_m`. Supply at least four observations at two or more distinct loads. `sigma_m` is each observation's standard uncertainty, not a desired accuracy. Positions can include an arbitrary common offset.

In Calibration, replace the example values with actual measurements. Measure a known length in the same image plane. Divide its metres by its pixel span to obtain metres per pixel. Record uncertainty in that scale and the shared force scale. For a known mass, calculate force from mass × gravitational acceleration and propagate both uncertainties. Tilt, parallax, camera movement, backlash and temperature can dominate nominal pixel precision.

The Camera tab offers optional dark-fiducial tracking. Arrange a fixed camera, sufficient light and known low-risk loads. Enable the camera deliberately, select a marker, let each load settle and capture its position. Inspect every tracked region. No force is applied by the software, and no video is saved. A lost marker must be reselected. Stop the device when finished. Actual-device acceptance remains a documented release limitation.

Choose the recorded nickel example to see real source observations. The source paper reports buckling above about 3 N; this example uses a predeclared ≤2.5 N subset. Its noise and scale uncertainties are sensitivity assumptions because total certificates are unavailable. The engine flags inconsistency rather than calling the conditional slope a verified material property. See [data provenance](DATA.md) and [held-out validation](VALIDATION.md).

## A second family: acoustic resonance

Switch to Acoustic resonance and load the recorded tuning fork. Inspect its spectrum and waveform. The result near 440.21 Hz need not equal the nominal 440 Hz stamp. Clock calibration, decay and source temperature matter. The interval is a resolution/repeatability/clock envelope, not validated 95% confidence coverage.

Import WAV or another browser-supported audio format. Browser imports analyze the first 20 seconds resampled to 16 kHz; keep the original. The CLI reads PCM/float WAV directly, preserving sample rate. Alternatively enable a microphone and then choose Capture. A steady resonator in a quiet space works better than arbitrary speech. A peak does not automatically identify the fundamental. Silence, clipping, out-of-band leakage, multiple sources and changing frequency can invalidate the result.

## Export and reproduce

Choose Export experiment. Inspect `spec.json`, `observations.json`, `calibration.json`, `procedure.json`, `result.json`, source digests and `scientific-limitations.txt`. The package carries engine source. Install NumPy/SciPy as recorded in `environment.json`, then run `python reproduce.py` in the extracted directory. Compare its numeric result and observation digest with the original.

A ZIP proves that the same observations can be analyzed again. It cannot prove that a camera was fixed, a load was correct, or a sensor clock was calibrated. Retain original recordings, independent reference measurements, dates, instrument identities and physical setup notes alongside the package.
