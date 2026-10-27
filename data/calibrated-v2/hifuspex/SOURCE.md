# PTB source and interpretation

Dataset: Cieslak M., Kling C., Wolff A. (2022), *Dataset of the high-frequency
and ultrasound personal exposimeter (HiFUSPEx) validation scans performed in
three simulated industrial sound fields*. PTB.
[DOI 10.7795/720.20211214](https://oar.ptb.de/resources/show/10.7795/720.20211214).
CC BY 4.0. Original source files here are unchanged.

The `Dataset_description.pdf` describes acquisition and layout. It identifies
`CalculatedFigureSPL` as an average sound-level map, with columns corresponding
to Z and rows to Y. Each scan spans a 32 × 32 cm area at 10 mm resolution.
The retained 33 × 33 matrices correspond to one scene and were compared by
matching array indices. Detailed per-cell physical-coordinate reconstruction
and raw-summary-to-map generation were not independently reproduced here.
Do not infer a particular matrix cell for raw point 543 without checking the
source scan-order transformation.

Primary paper: Cieslak M., Kling C., Wolff A. (2021), *Development of a Personal
Ultrasound Exposimeter for Occupational Health Monitoring*, IJERPH 18, 13289.
[DOI 10.3390/ijerph182413289](https://doi.org/10.3390/ijerph182413289).

Decisive locations in the paper:

- §4.5: pressure-response calibration traceable to PTB; primary reference
  microphones; electrical response calibration; repeated calibrator checks.
- §§4.6–4.7: sequential same-day scans; the 9 mm microphone-length difference
  was accommodated in scanner patterns. Raw scanner coordinates therefore
  differ even for corresponding intended acoustic locations.
- Table 1, **Welding Machine (20 kHz) without PG / Standing-Left**: mean
  difference 0.71 dB and expanded quantity 5.95 dB.
- §7: the prototype uncertainty budget covers electro-acoustical contributions;
  overall uncertainty depends on the measurement situation.

Our independent matrix calculation gives 0.7050944807 dB and twice the sample
spatial standard deviation 5.9495892699 dB. These round to Table 1. The latter
is spatial dispersion, not uncertainty of the mean. Individual observations
can disagree much more than microphone-calibration uncertainty alone.

The two calibration files label their sensitivities in dB re 1 V/Pa and expanded
uncertainties with k = 2. Their unique 20 kHz rows report 0.6 dB each. No
quantitative sample-clock calibration was established, and pressure-response
calibration does not establish frequency accuracy.

The original USPM analysis file explicitly reports missing recording metadata
and fallback settings, and refers to electrical-response files not retained in
this subset. Consequently neither a calibrated raw-WAV-to-Pa result nor a total
per-point uncertainty is asserted. The complete primary paper was not retained;
its DOI and decisive section/table locations are given above. The source's
six-page dataset description is retained locally.
