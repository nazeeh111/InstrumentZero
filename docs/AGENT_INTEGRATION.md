# Optional coding-agent integration

Codex, Claude Code or another terminal-capable coding agent can use the same CLI/Python engine as the Lab. No model API key, MCP server or agent-specific plugin is needed. The user's chosen agent supplies any broader language reasoning; InstrumentZero performs the supported numeric analysis and validation.

Give an agent a constrained task such as:

> Inspect `examples/stiffness-spec.json` and the CSV schema. Compile the supported question, run the analysis, inspect residuals and calibration warnings, then export a reproducible package. Keep synthetic and recorded data distinct. Do not enable sensors, contact instruments, apply loads or claim independent physical verification without actual evidence and my setup.

Useful commands:

```sh
instrumentzero compile examples/stiffness-spec.json
instrumentzero analyze examples/stiffness-spec.json examples/stiffness.csv --export evidence.zip
instrumentzero demo acoustic
python scripts/validate_real.py --output examples/my-validation
```

Exit status 2 indicates an explained input/scientific failure. Standard output is JSON; standard error carries the failure. Tools should inspect `status`, `warnings`, the uncertainty method and the source class, not merely the exit code. A numerically successful fit can still be scientifically unreliable.

For an HTTP integration use the loopback contract in [API.md](API.md), including its per-process token for non-browser POSTs. Avoid exposing this server publicly. Physical setup/permissions remain a human responsibility; generating a protocol does not execute it.
