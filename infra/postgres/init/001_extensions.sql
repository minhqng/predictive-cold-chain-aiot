-- ColdGuard database initialization.
-- Ensures the TimescaleDB extension exists. No application tables yet;
-- telemetry, command, twin, and run schemas belong to Member C slices.
CREATE EXTENSION IF NOT EXISTS timescaledb;
