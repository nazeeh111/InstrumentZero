# Historical acquisition UI source

`app.js` is the exact `src/instrumentzero/web/app.js` from commit `331272ebe5a86248322fc13ee0fb5e6f4b31fe10`, retained to check the unchanged v0.2 acquisition receipt's source hash `df0cf8cf49098345e7251f574a9e49aa82214b1e982c00d2b9e8906df3ac67df`. The historical receipt describes that source, not the later responsive UI. Current acquisition behavior is exercised separately by `tests/browser-acquisition.mjs` with synthetic fixtures and mocked device APIs. Neither check establishes hardware or physical-measurement validity.

`validate_acquisition.py` is the corresponding exact historical writer at the same commit, retained because the old receipt hashes it. The current writer rejects the historical test override before executing the runner or writing a current receipt. The historical Node-only override remains available for explicitly historical regression checks.
