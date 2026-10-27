# Calibrated recorded-audio validation: PTB HiFUSPEx

This is a small, unchanged subset of Cieslak, Kling and Wolff's **CC BY 4.0**
dataset, [DOI 10.7795/720.20211214](https://oar.ptb.de/resources/show/10.7795/720.20211214).
It contains genuine microphone recordings of a controlled laboratory sound field,
microphone calibration curves with expanded uncertainty, original analysis
outputs, and paired sound-level maps from two separate instruments.

The equipment scenario is an idealized welding machine, produced by playing a
20 kHz signal through a loudspeaker in PTB's physical scanning facility. The
microphone observations are real. These are externally recorded laboratory
measurements, not live captures or numerically generated sensor observations.

## Independently reproduced reference comparison

The retained scene is **20 kHz / standing / left ear / no protection grid**.
Both `CalculatedFigureSPL` files contain 33 × 33 calibrated sound-level values
in dB relative to 20 µPa. Taking HiFUSPEx minus USPM at all 1,089 corresponding
positions gives:

| Quantity | Recomputed | Published Table 1 |
|---|---:|---:|
| Mean device difference | 0.7050944807 dB | 0.71 dB |
| Twice the sample standard deviation of differences | 5.9495892699 dB | 5.95 dB |

The comparison reproduces an independently published cross-instrument result.
The second quantity describes spatial dispersion of the device differences;
it is **not** uncertainty of the mean and **not** a per-point calibration
uncertainty. Using twice the standard error of the mean instead would produce
0.1802905839 dB and would not reproduce this published quantity.

## Calibration and registration evidence

The [primary paper](https://doi.org/10.3390/ijerph182413289), §4.5, reports
calibration of both microphones traceable to PTB's national standard, using
primary calibrated reference microphones. The retained calibration tables give
pressure sensitivity and expanded uncertainty with coverage factor **k = 2**.
At 20 kHz both state **0.6 dB** expanded uncertainty. This concerns pressure
sensitivity, not sample-clock or frequency accuracy. Shared-reference correlations
are not provided, so do not assume all calibration errors are independent.

Sections 4.6–4.7 identify sequential same-day scans and a 9 mm microphone-length
difference compensated in the scanning patterns. Thus the 9 mm difference in
the raw scanner Y coordinates is documented registration, rather than evidence
of unmatched nominal grid positions. These scans are not simultaneous. Source
instability, positioning and noise remain relevant comparison limitations.

## Retained recordings and exact limits

| Device | Format | Header sample rate | Samples | Duration |
|---|---|---:|---:|---:|
| HiFUSPEx center position 543 | mono IEEE float32 WAV | 250,000 Hz | 770,048 | 3.080192 s |
| USPM center position 543 | mono IEEE float32 WAV | 192,000 Hz | 384,001 | 2.0000052083 s |

Both raw recordings contain substantial DC components. A frequency estimator
must remove DC and must not silently interpret float WAV values as calibrated
pascals. A raw-WAV-to-Pa reproduction has **not** been established here: the
original summary references electrical-response files and a calibration
normalization whose complete application has not been verified. The USPM
offline-analysis header also reports missing original recording information
and fallback settings. Preserve that warning when using its processed outputs.

The calibrated maps can be imported and compared as source-reported sound levels.
They do not prove InstrumentZero independently reconstructs absolute pressure
from these raw WAVs. No sample-clock calibration certificate or quantitative
frequency-reference uncertainty was found in the retained files. Acoustic
pressure calibration therefore must not be converted into a narrow frequency
accuracy claim.

The original HiFUSPEx calibration table repeats 89–100 kHz entries with conflicting
sensitivities. The 20 kHz row used here is unique. Do not silently accept or
average the conflicting high-frequency rows.

## Integrity and reproduction

`hifuspex/provenance.json` records every retained source entry, its original ZIP path,
ZIP CRC32 and local SHA-256. The 599,142,922-byte source ZIP was **not** downloaded
in full. Its public central directory and only selected compressed entries were
fetched using supported HTTP byte ranges. Each retained entry passed its ZIP
CRC32 and byte-length checks. PTB's published whole-archive SHA-256 is recorded
as source metadata, not claimed as independently verified locally.

Run the offline check from the repository root:

```sh
python data/calibrated-v2/verify.py
```

See `LICENSE-SOURCE.txt` for attribution and license. No instrument was connected
or physically controlled, and no sound was played during this work.
