# Independent software review oracle

The script is retained byte-for-byte from independent review. Run from the repository root after installing project dependencies, with Clang available:

```sh
python examples/edge/uart-admission-review/check_transport_only.py
```

It enumerates 4,224 binary control-field combinations using exact rational byte counts from repeating packet-send schedules, then checks the actual C decoder and Python decoder. It also checks public planner admission and virtual budgets. This covers representational control/transport cases, not every possible measurement graph or filter-response contract. It never opens a serial port or physical sensor. The script writes a new disposable evidence folder and prints its path. The original report/reproduction receipt retain review provenance.

The transport-only harness fixes its CPU-cost dependency at explicitly synthetic positive values. This prevents unrelated scheduler pauses from changing a bandwidth test. It does not change the production planner or its 70% processing guard, and none of those fixture costs is used as a reported benchmark. The original independent script remains intact for provenance; its unwrapped public-path assertions use live host timings.
