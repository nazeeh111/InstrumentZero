# Launch draft: InstrumentZero Edge simulation studio

Draft only. No outreach has been sent.

InstrumentZero Edge is a local signal and placement simulation studio. Choose a known frequency, decay, amplitude, noise level and seed. Compare raw-host, calibrated-edge and filtered-edge processing, check numerical error, reject an unsuitable signal and export a source-complete reproducible experiment.

The analytic truth check and C-versus-float64 reference answer different questions. Host timings are measured on the running computer; they are not MCU benchmarks. The planner can tie a sensible fixed-edge pipeline or leave processing on the host. No universal win or physical measurement claim is made.

No hardware, API key or cloud service is required. The simulator uses an analytic ringdown and ideal sample clock, not a finite-element material model. Existing recording/firmware code remains an optional extension. Completion is defined by the simulation acceptance report, not future physical experiments.

Useful audiences: signal-processing students, embedded-software developers comparing data paths, and researchers who need explicit reproducible numerical fixtures. Do not claim adoption, accuracy on real sensors or physical validation without evidence.
