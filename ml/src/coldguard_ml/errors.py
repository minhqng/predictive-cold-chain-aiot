"""Exception hierarchy for the ColdGuard ML pipeline (Member B).

Each public failure path is explicit per the W01 contracts
(``ml/data-dictionary-v0.md`` §§3, 9, 13; ``ml/leakage-risk-register.md``):
malformed identity/order, leakage-unsafe splits, and contradictory
manifests raise instead of being silently repaired.
"""

from __future__ import annotations


class ColdguardError(Exception):
    """Base class for all ColdGuard ML pipeline errors."""


class DataContractError(ColdguardError):
    """A row violates the W01 data-dictionary consumer contract."""


class IdentityContradictionError(DataContractError):
    """Same ``(device_id, boot_id, seq)`` identity carries different payloads."""


class OrderContradictionError(DataContractError):
    """Event time / ``boot_id`` + ``seq`` ordering is self-contradictory."""


class ManifestError(ColdguardError):
    """A manifest record is malformed, contradictory, or cross-referenced badly."""


class SplitError(ColdguardError):
    """A grouped-split request cannot be satisfied without leakage."""


class WindowError(ColdguardError):
    """Window generation was requested in a leakage-unsafe or invalid way."""


class LabelError(ColdguardError):
    """Label generation received an invalid spec, series, or coverage source."""
