# InstrumentZero Edge simulation studio assets

Current 0.3.0 installed-wheel captures, 2026-11-01. All 38 runtime files matched the frozen source. The custom screen uses 18.6 Hz, decay0.8/s, noise0.0006, amplitude1 and seed6001. Mobile capture uses21.3 Hz and the same other controls. Actual390 px body/document widths were390 px with no page overflow; viewport override was reset.

The 28-second silent master is an edited sequence of actual UI screenshots. It shows setup, analytic truth, host-favored raw validation, no-signal rejection and source-complete export. It is not a continuous screen recording. walkthrough.json and render_walkthrough.py are editable sources; captions state only behavior executed in the installed application. Images and generated master are original project material. The existing system Arial font is used for rendering but is not redistributed.

Re-render into a new output/work folder with Python3 and free local FFmpeg:

```sh
python render_walkthrough.py --output NEW_MASTER.mp4 --work NEW_RENDER_FOLDER
```

The diagram served by the app is editable source/instrumentzero/web/edge-architecture.svg in portable exports, or src/instrumentzero/web/edge-architecture.svg in the checkout. docs/edge/architecture.mmd is the editable graph form. Original rc1/rc2/rc3 material remains preserved separately.
