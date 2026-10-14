"""ColdGuard backend package (Member C).

W01 foundation: FastAPI application entry point (`main`), deterministic
runtime configuration (`config`), telemetry/command wire-contract models
(`contracts`) and the Alembic migration baseline (`migrations`).
Ingestion, persistence logic, twin, commands runtime, predictions, auth
and realtime belong to later slices; the module boundary map lives in
the root README.
"""

__version__ = "0.1.0"
