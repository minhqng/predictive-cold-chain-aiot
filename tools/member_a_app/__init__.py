"""Shared Member A acceptance core (independently testable foundation).

This package is the cross-week foundation for the Member A acceptance
application. Only the hardware-free, downstream-free core lives here:

- ``model``     result/definition/operator abstractions (no I/O).
- ``protocol``  telemetry wire parsing and shared frame models.
- ``analysis``  pure data/analysis primitives.
- ``evidence``  evidence identity, SHA-256 integrity, safe paths and the
  session store that keeps requirement definitions separate from executed
  results.

Downstream layers (requirements registry, evaluators, runners, GUI and live
hardware acquisition) are deliberately NOT part of this core and are added in
later slices. Nothing here opens a serial port, energizes hardware, or marks a
requirement PASS on its own.
"""

__all__ = ["model", "protocol", "analysis", "evidence"]