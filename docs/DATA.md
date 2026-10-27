# Data provenance and evidence limits

InstrumentZero ships authentic externally recorded observations separately from
generated benchmark observations. Neither bundled source was collected live by
InstrumentZero. Metadata, transformations, source URLs and checksums are in
[`data/provenance.json`](../data/provenance.json). Run the offline integrity check:

```sh
python data/reproduce.py
```

## Acoustic resonance: a recorded tuning fork

[`tuning-fork-440Hz.ogg`](../data/tuning-fork-440Hz.ogg) is the unchanged file from
[Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Tuning-fork-440Hz.ogg).
The Commons page credits **jmuehlhans**, links to the original
[2014 Freesound recording](https://freesound.org/people/jmuehlhans/sounds/220747/),
and identifies the license as **CC0 1.0**. The creator describes a measurement
microphone in an anechoic chamber, with a 440 Hz tuning fork and resonance box.
The retained Commons derivative is shorter than the original recording.

The decoded WAV contains 1,309,959 mono samples at 48,000 Hz, or 27.2908125 s.
Decoding applies no resampling, trimming, normalization or frequency correction:

```sh
ffmpeg -hide_banner -i data/tuning-fork-440Hz.ogg \
  -ac 1 -c:a pcm_s16le -map_metadata -1 tuning-fork-rebuilt.wav
```

The retained conversion used FFmpeg 7.1 / libavformat 61.7.100. Container metadata
can vary between FFmpeg versions. Compare the PCM sample hash recorded in
`provenance.json` when reproducing the conversion. `python data/reproduce.py
--rebuild` parses the CSV again and verifies a fresh audio decode before using a
missing WAV. It preserves an existing retained WAV.

**Evidence limits.** The nominal 440 Hz label is not a traceable frequency
certificate. The ADC clock uncertainty and temperature are unavailable. The
retained audio has undergone lossy compression. Frequency estimates also vary
over its decay, so a narrow estimator-only interval cannot establish total
measurement accuracy. This example supports real recorded-signal analysis and
nominal agreement checks, not a new live measurement or certified tuning-fork
calibration. See [`CC0-NOTICE.txt`](../data/CC0-NOTICE.txt).

## Load-cell calibration: NIST Pontius

[`Pontius.dat`](../data/Pontius.dat) is the unmodified ASCII fixture published by
[NIST/ITL Statistical Reference Datasets](https://www.itl.nist.gov/div898/strd/lls/data/Pontius.shtml).
The [collection description](https://www.itl.nist.gov/div898/handbook/pmd/section6/pmd611.htm)
identifies known applied loads and observed deflections, collected in two runs.
[`pontius.csv`](../data/pontius.csv) preserves the original decimal strings and
adds observation and run indices. It performs no physical-unit conversion.

NIST supplies a quadratic fit and
[certified regression coefficients](https://www.itl.nist.gov/div898/strd/lls/data/LINKS/v-Pontius.shtml).
These are useful independent numerical reference values for testing an estimator.
They are not a separate physical measurement of the fitted stiffness. A held-out
load-prediction experiment may compare predictions with source-reported known
loads, but must identify its split and distinguish that check from traceable
calibration or newly collected observations.

**Evidence limits.** Source physical units are unspecified. Preserve labels such
as `load_source_units`; never relabel these values as N, m or N/m. The increasing
load order confounds temporal drift with load. A high linear R² alone does not
establish a sufficiently accurate calibration. Reuse is accompanied by NIST
acknowledgment and the applicable [NIST data terms](https://www.nist.gov/open/license)
in [`NIST-NOTICE.txt`](../data/NIST-NOTICE.txt).

## What is still needed for independent stiffness validation

These fixtures do not establish an independently calibrated webcam stiffness
measurement. That requires a real specimen, physical scale calibration, known
loads, retained observations, an independently measured stiffness/reference, and
their uncertainties. A reference derived from the same fitted observations is
not independent. A generated video, synthetic curve, nominal material property
or second implementation of the same estimator cannot replace that evidence.

## Recorded SI stiffness with a separate force reference

The retained [`nickel-sensor`](../data/nickel-sensor/) subset from Dera, Konopacka
and Jarząbek, [Mendeley Data v1, DOI 10.17632/syjkdyzmxj.1](https://data.mendeley.com/datasets/syjkdyzmxj/1),
contains 15 measured force/displacement points and reference-force/capacitance
records. Source CSV units are N and mm; `stiffness_si.csv` converts mm to m
exactly. Files retain source checksums and attribution under CC BY 4.0.

The authors' [primary article](https://www.ippt.pan.pl/repository/open/o10366.pdf),
retained unchanged as `article-source.pdf`, identifies a calibrated Megatron
KM1403 force transducer and a Thorlabs Z825B actuator. Equation 8, PDF page 7,
reports a slope of **19.126 N/mm**, offset **0.0994 N**, and slope standard
deviation **0.2001 N/mm**. This slope precision excludes unreported systematic
uncertainty. Sections 4.2–4.3 describe instability above approximately 3 N and
displacement errors from slack/backlash; direct displacement sensing is proposed.
New physical measurements above the reported instability onset are not justified
by this curve, even though existing source observations extend to 3.488 N.

Fitting loading observations and predicting the held-out unloading branch gives
a limited check against the separate force reference. Both branches share a
specimen/setup, with possible systematic errors. Reproducing the published
all-point slope is a numerical check, not an independent stiffness certificate.
No per-observation displacement uncertainty or full calibration certificate is
supplied. Never invent `sigma_m` from displayed decimal places, actuator
resolution, or the paper's capacitance-converter specifications. Any assumed
uncertainty used for sensitivity analysis must be labeled as an assumption.

## Other sources investigated

A public research lead is J. Yang's
[Measurement of spring stiffness and damping](https://data.mendeley.com/datasets/fnw2jrwwhx/1),
DOI **10.17632/fnw2jrwwhx.1**, published March 1, 2022 under CC BY 4.0.
The repository describes measured torsional torque/angle and accelerometer
free-vibration response. Its file list names `SpringStiffness_FigS1_data.xlsx`
and `damping_test_raw.lvm`. A follow-up request was denied HTTP 403, so those
files are **not bundled or validated** here. The available description does not
establish that static and dynamic records concern the same spring or provide
the independent physical reference required above.
