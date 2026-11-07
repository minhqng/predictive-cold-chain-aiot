"""Command storage and lifecycle state-machine tests (C-W06-01/04).

Pure matrix units plus real-PostgreSQL provider tests for durability,
idempotency, conflict rejection, ACK arbitration and concurrency. Provider
tests skip honestly without COLDGUARD_TEST_DATABASE_URL.
"""

import os
import threading
from datetime import timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from coldguard_backend import command_store as cs
from tests.command_testkit import (
    ack_bytes,
    ack_topic,
    cleanup_commands,
    make_ack,
    make_command,
    utcnow,
)


# --- Pure transition-matrix units ------------------------------------------


def test_terminal_states_have_no_regression():
    for terminal in (cs.EXPIRED, cs.ACK_REJECTED, cs.VERIFIED, cs.FAILED_VERIFICATION):
        assert cs.ALLOWED_TRANSITIONS[terminal] == frozenset()


def test_puback_never_implies_ack_accepted_in_matrix_origin():
    # PUBLISHED is a broker-delivery state; ACK_ACCEPTED is only reachable from
    # PUBLISHED/UNKNOWN via a device verdict, never from CREATED directly.
    assert cs.ACK_ACCEPTED not in cs.ALLOWED_TRANSITIONS[cs.CREATED]
    assert cs.ACK_ACCEPTED in cs.ALLOWED_TRANSITIONS[cs.PUBLISHED]


def test_ack_accepted_does_not_advance_to_verified_software():
    # Physical verification states are reserved; the only edges out of
    # ACK_ACCEPTED are the later physical stages, not a software shortcut.
    assert cs.VERIFIED in cs.ALLOWED_TRANSITIONS[cs.ACK_ACCEPTED]
    assert cs.EXPIRED not in cs.ALLOWED_TRANSITIONS[cs.ACK_ACCEPTED]


def test_expired_cannot_return_to_publishable():
    assert cs.PUBLISHED not in cs.ALLOWED_TRANSITIONS[cs.EXPIRED]
    assert cs.VALIDATED not in cs.ALLOWED_TRANSITIONS[cs.EXPIRED]


# --- Provider tests --------------------------------------------------------


def _record_ack(engine, ack, *, validity="VALID", now=None, topic_device="coldguard-001"):
    raw = ack_bytes(ack)
    import hashlib

    with engine.begin() as conn:
        return cs.record_ack(
            conn,
            topic_device_id=topic_device,
            raw_payload=raw.decode(),
            payload_sha256=hashlib.sha256(raw).hexdigest(),
            backend_received_at=utcnow(),
            ack=ack,
            validity=validity,
            now=now,
        )


def test_create_idempotent_and_conflict(db_engine):
    cleanup_commands(db_engine)
    try:
        cmd = make_command("cmd-create")
        with db_engine.begin() as conn:
            first = cs.create_command(conn, cmd)
            again = cs.create_command(conn, cmd)
        assert first["outcome"] == "created"
        assert again["outcome"] == "exists"
        conflicting = make_command("cmd-create", reason_code="DIFFERENT")
        with pytest.raises(cs.CommandConflict):
            with db_engine.begin() as conn:
                cs.create_command(conn, conflicting)
    finally:
        cleanup_commands(db_engine)


def test_db_check_rejects_out_of_range_duty(db_engine):
    cleanup_commands(db_engine)
    try:
        cmd = make_command("cmd-duty")
        with pytest.raises(IntegrityError):
            with db_engine.begin() as conn:
                conn.execute(
                    cs.commands.insert().values(
                        command_id="cmd-duty", device_id=cmd.device_id,
                        schema_version=1, created_at=cmd.created_at,
                        expires_at=cmd.expires_at, controller_id="PREDICTIVE",
                        policy_version="p", reason_code="R", action_cooling="ON",
                        action_duty=2.0, status="VALIDATED", verification_status="NONE",
                        payload_sha256="x", created_db_at=utcnow(),
                    )
                )
    finally:
        cleanup_commands(db_engine)


def test_db_check_rejects_bad_expiry(db_engine):
    cleanup_commands(db_engine)
    try:
        now = utcnow()
        with pytest.raises(IntegrityError):
            with db_engine.begin() as conn:
                conn.execute(
                    cs.commands.insert().values(
                        command_id="cmd-exp", device_id="coldguard-001",
                        schema_version=1, created_at=now, expires_at=now,
                        controller_id="PREDICTIVE", policy_version="p", reason_code="R",
                        action_cooling="ON", action_duty=0.5, status="VALIDATED",
                        verification_status="NONE", payload_sha256="x", created_db_at=now,
                    )
                )
    finally:
        cleanup_commands(db_engine)


def test_db_check_rejects_invented_status(db_engine):
    cleanup_commands(db_engine)
    try:
        cmd = make_command("cmd-status")
        with pytest.raises(IntegrityError):
            with db_engine.begin() as conn:
                conn.execute(
                    cs.commands.insert().values(
                        command_id="cmd-status", device_id=cmd.device_id,
                        schema_version=1, created_at=cmd.created_at,
                        expires_at=cmd.expires_at, controller_id="PREDICTIVE",
                        policy_version="p", reason_code="R", action_cooling="ON",
                        action_duty=0.5, status="COOLED", verification_status="NONE",
                        payload_sha256="x", created_db_at=utcnow(),
                    )
                )
    finally:
        cleanup_commands(db_engine)


def test_publish_then_accepted_ack(db_engine):
    cleanup_commands(db_engine)
    try:
        with db_engine.begin() as conn:
            cs.create_command(conn, make_command("cmd-ack"))
            cs.transition_command(conn, "cmd-ack", cs.PUBLISHED, reason="puback")
        result = _record_ack(db_engine, make_ack("cmd-ack", "ACCEPTED"))
        assert result["outcome"] == "applied"
        assert result["status"] == cs.ACK_ACCEPTED
        with db_engine.begin() as conn:
            row = cs.get_command(conn, "cmd-ack")
        assert row["status"] == cs.ACK_ACCEPTED
        assert row["ack_at"] is not None
        assert row["verification_status"] == "NONE"  # never physical proof
    finally:
        cleanup_commands(db_engine)


def test_rejected_ack_records_reason(db_engine):
    cleanup_commands(db_engine)
    try:
        with db_engine.begin() as conn:
            cs.create_command(conn, make_command("cmd-rej"))
            cs.transition_command(conn, "cmd-rej", cs.PUBLISHED)
        result = _record_ack(
            db_engine, make_ack("cmd-rej", "SAFETY_BLOCKED", reason_code="EPOCH_UNSYNCHRONIZED")
        )
        assert result["status"] == cs.ACK_REJECTED
        with db_engine.begin() as conn:
            row = cs.get_command(conn, "cmd-rej")
        assert row["reject_reason"] == "EPOCH_UNSYNCHRONIZED"
    finally:
        cleanup_commands(db_engine)


def test_duplicate_ack_no_double_transition(db_engine):
    cleanup_commands(db_engine)
    try:
        with db_engine.begin() as conn:
            cs.create_command(conn, make_command("cmd-dup"))
            cs.transition_command(conn, "cmd-dup", cs.PUBLISHED)
        ack = make_ack("cmd-dup", "ACCEPTED")
        first = _record_ack(db_engine, ack)
        second = _record_ack(db_engine, ack)
        assert first["outcome"] == "applied"
        assert second["outcome"] == "duplicate"
        with db_engine.begin() as conn:
            transitions = conn.execute(
                cs.command_transitions.select().where(
                    cs.command_transitions.c.command_id == "cmd-dup",
                    cs.command_transitions.c.to_status == cs.ACK_ACCEPTED,
                )
            ).all()
        assert len(transitions) == 1
    finally:
        cleanup_commands(db_engine)


def test_conflicting_ack_preserves_settled_verdict(db_engine):
    cleanup_commands(db_engine)
    try:
        with db_engine.begin() as conn:
            cs.create_command(conn, make_command("cmd-conf"))
            cs.transition_command(conn, "cmd-conf", cs.PUBLISHED)
        _record_ack(db_engine, make_ack("cmd-conf", "ACCEPTED"))
        result = _record_ack(db_engine, make_ack("cmd-conf", "REJECTED", reason_code="LOCAL_SAFETY_BLOCKED"))
        assert result["outcome"] == "conflict"
        with db_engine.begin() as conn:
            row = cs.get_command(conn, "cmd-conf")
            evidence = conn.execute(
                cs.command_acks.select().where(cs.command_acks.c.command_id == "cmd-conf")
            ).mappings().all()
        assert row["status"] == cs.ACK_ACCEPTED  # not overwritten
        assert any(e["validity"] == "CONFLICT" for e in evidence)
    finally:
        cleanup_commands(db_engine)


def test_unmatched_ack_quarantined(db_engine):
    cleanup_commands(db_engine)
    try:
        result = _record_ack(db_engine, make_ack("ghost-command", "ACCEPTED"))
        assert result["outcome"] == "unmatched"
        with db_engine.begin() as conn:
            evidence = conn.execute(
                cs.command_acks.select().where(cs.command_acks.c.command_id == "ghost-command")
            ).mappings().one()
        assert evidence["validity"] == "UNMATCHED"
    finally:
        cleanup_commands(db_engine)


def test_late_ack_after_expiry_no_resurrection(db_engine):
    cleanup_commands(db_engine)
    try:
        now = utcnow()
        expired = make_command("cmd-late", created_at=now - timedelta(minutes=10), ttl_s=60)
        with db_engine.begin() as conn:
            cs.create_command(conn, expired)
            cs.transition_command(conn, "cmd-late", cs.PUBLISHED)
        result = _record_ack(db_engine, make_ack("cmd-late", "ACCEPTED"), now=now)
        assert result["outcome"] == "late_expired"
        assert result["status"] == cs.EXPIRED
        with db_engine.begin() as conn:
            row = cs.get_command(conn, "cmd-late")
        assert row["status"] == cs.EXPIRED
    finally:
        cleanup_commands(db_engine)


def test_expire_due_commands(db_engine):
    cleanup_commands(db_engine)
    try:
        now = utcnow()
        with db_engine.begin() as conn:
            cs.create_command(conn, make_command("cmd-fresh"))
            cs.create_command(conn, make_command("cmd-stale", created_at=now - timedelta(minutes=10), ttl_s=60))
            expired = cs.expire_due_commands(conn, now=now)
        assert "cmd-stale" in expired
        assert "cmd-fresh" not in expired
        with db_engine.begin() as conn:
            assert cs.get_command(conn, "cmd-stale")["status"] == cs.EXPIRED
            assert cs.get_command(conn, "cmd-fresh")["status"] == cs.VALIDATED
    finally:
        cleanup_commands(db_engine)


def test_invalid_transition_raises(db_engine):
    cleanup_commands(db_engine)
    try:
        with db_engine.begin() as conn:
            cs.create_command(conn, make_command("cmd-trans"))
        with pytest.raises(cs.InvalidTransition):
            with db_engine.begin() as conn:
                cs.transition_command(conn, "cmd-trans", cs.VERIFIED)
    finally:
        cleanup_commands(db_engine)


def test_restart_durability(db_engine):
    cleanup_commands(db_engine)
    try:
        with db_engine.begin() as conn:
            cs.create_command(conn, make_command("cmd-durable"))
            cs.transition_command(conn, "cmd-durable", cs.PUBLISHED)
        # A brand-new engine (simulated restart) reads the same durable state.
        fresh = create_engine(os.environ["COLDGUARD_TEST_DATABASE_URL"])
        try:
            with fresh.begin() as conn:
                row = cs.get_command(conn, "cmd-durable")
            assert row["status"] == cs.PUBLISHED
            assert row["published_at"] is not None
        finally:
            fresh.dispose()
    finally:
        cleanup_commands(db_engine)


def test_concurrent_creators_converge_one_row(db_engine):
    cleanup_commands(db_engine)
    try:
        url = os.environ["COLDGUARD_TEST_DATABASE_URL"]
        outcomes = []
        cmd = make_command("cmd-race")

        def worker():
            engine = create_engine(url)
            try:
                with engine.begin() as conn:
                    outcomes.append(cs.create_command(conn, cmd)["outcome"])
            finally:
                engine.dispose()

        threads = [threading.Thread(target=worker) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert outcomes.count("created") == 1
        assert outcomes.count("exists") == 5
        with db_engine.begin() as conn:
            rows = cs.list_commands(conn, device_id="coldguard-001")
        assert len([r for r in rows if r["command_id"] == "cmd-race"]) == 1
    finally:
        cleanup_commands(db_engine)


def test_concurrent_ack_and_expiry_deterministic(db_engine):
    cleanup_commands(db_engine)
    try:
        now = utcnow()
        # Command expires exactly now; ACK and expiry race. Either ACK_ACCEPTED
        # (ack won before expiry) or EXPIRED (expiry won) — never both, never a
        # regression afterward.
        cmd = make_command("cmd-arb", created_at=now - timedelta(seconds=30), ttl_s=30)
        with db_engine.begin() as conn:
            cs.create_command(conn, cmd)
            cs.transition_command(conn, "cmd-arb", cs.PUBLISHED)
        url = os.environ["COLDGUARD_TEST_DATABASE_URL"]
        barrier = threading.Barrier(2)

        def ack_worker():
            engine = create_engine(url)
            try:
                barrier.wait()
                _record_ack_engine(engine, make_ack("cmd-arb", "ACCEPTED"), now=now)
            finally:
                engine.dispose()

        def expiry_worker():
            engine = create_engine(url)
            try:
                barrier.wait()
                with engine.begin() as conn:
                    cs.expire_due_commands(conn, now=now + timedelta(seconds=1))
            finally:
                engine.dispose()

        threads = [threading.Thread(target=ack_worker), threading.Thread(target=expiry_worker)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        with db_engine.begin() as conn:
            status = cs.get_command(conn, "cmd-arb")["status"]
        assert status in (cs.ACK_ACCEPTED, cs.EXPIRED)
        # Once settled, a further ACK cannot regress it.
        result = _record_ack(db_engine, make_ack("cmd-arb", "REJECTED", reason_code="X"), now=now)
        assert result["outcome"] in ("duplicate", "conflict", "late_expired")
        with db_engine.begin() as conn:
            assert cs.get_command(conn, "cmd-arb")["status"] == status
    finally:
        cleanup_commands(db_engine)


def _record_ack_engine(engine, ack, *, now=None):
    import hashlib

    raw = ack_bytes(ack)
    with engine.begin() as conn:
        return cs.record_ack(
            conn, topic_device_id="coldguard-001", raw_payload=raw.decode(),
            payload_sha256=hashlib.sha256(raw).hexdigest(), backend_received_at=utcnow(),
            ack=ack, validity="VALID", now=now,
        )