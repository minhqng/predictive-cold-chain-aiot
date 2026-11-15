import json
import os
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url

from coldguard_backend.prediction_store import predictions
from scripts import verify_restore
from tests.test_command_migration import ENV, _upgrade


RESTORE_URLS = ("COLDGUARD_BACKUP_SOURCE_URL", "COLDGUARD_BACKUP_RESTORE_URL")


@pytest.mark.skipif(
    not all(os.environ.get(name) for name in RESTORE_URLS),
    reason="requires two fresh, dedicated loopback PostgreSQL restore test databases",
)
def test_restore_verifier_covers_installed_evidence_and_fails_on_omission(monkeypatch, tmp_path):
    urls = [make_url(os.environ[name]) for name in RESTORE_URLS]
    assert all(url.drivername == "postgresql+psycopg" and url.host == "127.0.0.1"
               and not url.query for url in urls)
    assert (urls[0].port or 5432, urls[0].database) != (urls[1].port or 5432, urls[1].database)
    engines = [create_engine(url) for url in urls]
    expected_additions = {
        "0009": set(),
        "0010": {"predictions", "prediction_inputs"},
        "0011": {"shadow_decisions"},
        "0012": {"physical_assessments", "policy_approvals"},
    }
    expected = set()
    try:
        assert all(not inspect(engine).get_table_names(schema="public") for engine in engines)
        for revision, additions in expected_additions.items():
            expected.update(additions)
            for name, engine in zip(RESTORE_URLS, engines):
                monkeypatch.setenv(ENV, os.environ[name])
                _upgrade(revision)
                report = verify_restore.fingerprint(engine.url)
                assert report["revisions"] == [revision]
                assert set(report["tables"]) & set.union(*expected_additions.values()) == expected
                assert set(report["tables"]) == set(inspect(engine).get_table_names(schema="public"))

        stamp = datetime(2026, 1, 1, tzinfo=timezone.utc)
        for engine in engines:
            with engine.begin() as conn:
                conn.execute(text(
                    "UPDATE reconciliation_boundary SET normalization_active_since = :stamp, recorded_at = :stamp"
                ), {"stamp": stamp})
                conn.execute(predictions.insert().values(
                    prediction_id="restore-prediction", device_id="restore-fixture", model_version="fixture",
                    model_sha256="a" * 64, feature_version="fixture", feature_schema_sha256="b" * 64,
                    risk_score=0.7, horizon_sec=60, created_at=stamp, recorded_at=stamp,
                    input_window_start=stamp, input_window_end=stamp, latest_input_at=stamp,
                    fresh_until=stamp + timedelta(seconds=60), payload_sha256="c" * 64,
                ))

        def check(name, status):
            output = tmp_path / name
            monkeypatch.setattr("sys.argv", ["verify_restore.py", "--output", str(output)])
            assert verify_restore.main() == status
            return json.loads(output.read_text())

        assert check("matching.json", 0)["match"] is True
        with engines[1].begin() as conn:
            conn.execute(predictions.delete().where(predictions.c.prediction_id == "restore-prediction"))
        mismatch = check("missing-prediction.json", 1)
        assert mismatch["match"] is False
        assert mismatch["source"]["tables"]["predictions"]["rows"] == 1
        assert mismatch["restored"]["tables"]["predictions"]["rows"] == 0
    finally:
        for engine in engines:
            engine.dispose()
