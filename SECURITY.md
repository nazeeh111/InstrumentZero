# Security and physical boundaries

The Lab binds only to loopback. It is a local single-user application; do not expose it through a tunnel or public bind. Host/Origin checks protect requests. Non-browser POST clients need the per-process token from `/api/session`. No endpoint executes submitted code or accepts arbitrary file paths. Imports have size and numeric validation limits.

Sensors require deliberate browser permission and separate capture controls. Numeric observations go to the local engine. Stop controls, family changes and page exit stop tracks. Exports contain the submitted observations and source names. Keep originals and inspect what is visible/audible before enabling a device.

The engine does not actuate hardware. Proposed loads require human setup and supervision. The application's 10 N ceiling is not a safe-load certificate for a specimen. High voltage, hazardous chemistry, lasers, pressure systems and unsupervised robotics are unsupported.

Report ordinary defects through repository issues. Use GitHub private security reporting, when available, for exploitable boundaries involving private data. Never post private recordings or credentials publicly. Report scientific model failures with assumptions and reproducible data.
