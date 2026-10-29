"""InstrumentZero Edge. Simulation and recording support; hardware gates are explicit."""
from .spec import EdgeError, EdgeSpec, compile_graph, default_spec

__all__ = ["EdgeError", "EdgeSpec", "compile_graph", "default_spec"]
