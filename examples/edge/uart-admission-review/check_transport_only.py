"""Run the retained independent oracle with CPU timing isolated from UART math.

Synthetic positive costs are a test fixture, never a measured performance result.
The original independent schedule/Fraction algorithm stays byte-for-byte intact.
"""

from pathlib import Path
import runpy

from instrumentzero.edge import control, planner
from instrumentzero.edge.native import core_identity, library


def fixed_costs(compiled):
    return {
        "schema": "instrumentzero.edge.costs/1",
        "basis": "measured_host_proxy",
        "platform": "transport-only-test-fixture",
        "machine": "test-fixture",
        "core_sha256": core_identity(),
        "spec_sha256": compiled["spec_sha256"],
        "state_bytes": library().iz_state_bytes(),
        "primitive_costs": {
            name: {"ns_per_input_frame": 1000.0, "observed_max_ns_per_input_frame": 1000.0}
            for name in ("calibration", "calibration_fir")
        },
        "limits": "Synthetic CPU dependency for transport-only verification, not a benchmark.",
    }


old_control, old_planner = control.measure_costs, planner.measure_costs
try:
    control.measure_costs = planner.measure_costs = fixed_costs
    print("Transport logic only: fixed synthetic CPU costs; no performance or hardware claim.")
    runpy.run_path(str(Path(__file__).with_name("independent_uart_check.py")), run_name="__main__")
finally:
    control.measure_costs, planner.measure_costs = old_control, old_planner
