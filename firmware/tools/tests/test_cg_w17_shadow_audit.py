"""Unit tests for ColdGuard Member A — W17 Shadow Mode Verification Tool."""

import unittest

from cg_w17_shadow_audit import (
    ENVELOPE_BOUND_CHAMBER_MAX_RATE_C_PER_SEC,
    REQUIRED_B_MODEL_CHANNELS,
    audit_shadow_session,
    monitor_plant_anomalies,
    verify_b_model_alignment,
    verify_frame_sequence_and_cadence,
    verify_predictive_isolation,
)


class TestW17ShadowAudit(unittest.TestCase):

    def setUp(self):
        self.valid_frame = {
            "seq": 1,
            "uptime_ms": 1000,
            "elapsed_ms": 1000,
            "t_inside_c": 5.0,
            "t_inside_status": "OK",
            "t_cold_side_c": 3.0,
            "t_hot_side_c": 28.0,
            "door_open": False,
            "door_status": "OK",
            "voltage_v": 12.0,
            "current_a": 4.5,
            "power_w": 54.0,
            "quality": "OK",
            "pwm_duty": 800,
        }

    def test_verify_b_model_alignment_success(self):
        missing = verify_b_model_alignment(self.valid_frame)
        self.assertEqual(missing, [])

    def test_verify_b_model_alignment_missing_channel(self):
        incomplete = dict(self.valid_frame)
        del incomplete["door_open"]
        del incomplete["power_w"]
        missing = verify_b_model_alignment(incomplete)
        self.assertEqual(missing, ["door_open", "power_w"])

    def test_verify_predictive_isolation_clean(self):
        applied = [500, 500, 500]
        shadow = [800, 900, 1000]
        auth_a = [500, 500, 500]
        leak, indices = verify_predictive_isolation(applied, shadow, auth_a)
        self.assertFalse(leak)
        self.assertEqual(indices, [])

    def test_verify_predictive_isolation_fail_closed_zero_duty_allowed(self):
        # Applied 0 is fail-closed, permitted even if auth_a was 500
        applied = [500, 0, 500]
        shadow = [800, 900, 1000]
        auth_a = [500, 500, 500]
        leak, indices = verify_predictive_isolation(applied, shadow, auth_a)
        self.assertFalse(leak)

    def test_verify_predictive_isolation_leak_detected(self):
        applied = [500, 900, 500]
        shadow = [800, 900, 1000]
        auth_a = [500, 500, 500]
        leak, indices = verify_predictive_isolation(applied, shadow, auth_a)
        self.assertTrue(leak)
        self.assertEqual(indices, [1])

    def test_verify_sequence_and_cadence_clean(self):
        f1 = dict(self.valid_frame, seq=1, uptime_ms=1000)
        f2 = dict(self.valid_frame, seq=2, uptime_ms=2000)
        errors = verify_frame_sequence_and_cadence([f1, f2])
        self.assertEqual(errors, [])

    def test_verify_sequence_and_cadence_gap_detected(self):
        f1 = dict(self.valid_frame, seq=1, uptime_ms=1000)
        f2 = dict(self.valid_frame, seq=5, uptime_ms=2000)  # Gap!
        errors = verify_frame_sequence_and_cadence([f1, f2])
        self.assertEqual(len(errors), 1)
        self.assertIn("Sequence gap", errors[0])

    def test_verify_sequence_and_cadence_non_monotonic_timestamp(self):
        f1 = dict(self.valid_frame, seq=1, uptime_ms=2000)
        f2 = dict(self.valid_frame, seq=2, uptime_ms=1000)  # Time backwards!
        errors = verify_frame_sequence_and_cadence([f1, f2])
        self.assertEqual(len(errors), 1)
        self.assertIn("Non-monotonic timestamp", errors[0])

    def test_monitor_plant_anomalies_none(self):
        f1 = {"elapsed_ms": 1000, "t_inside_c": 20.0}
        f2 = {"elapsed_ms": 2000, "t_inside_c": 19.95}  # 0.05 C/s <= 0.10 C/s limit
        anomalies = monitor_plant_anomalies([f1, f2])
        self.assertEqual(anomalies, [])

    def test_monitor_plant_anomalies_detected(self):
        f1 = {"elapsed_ms": 1000, "t_inside_c": 20.0}
        f2 = {"elapsed_ms": 2000, "t_inside_c": 19.5}   # 0.5 C/s > 0.10 C/s bound
        anomalies = monitor_plant_anomalies([f1, f2])
        self.assertEqual(len(anomalies), 1)
        self.assertEqual(anomalies[0]["reason"], "CHAMBER_RATE_EXCEEDS_W08_ENVELOPE")

    def test_audit_shadow_session_missing_shadow_data_fails_safely(self):
        # Negative test: Never PASS without synchronized shadow commands
        f1 = dict(self.valid_frame, seq=1, elapsed_ms=1000)
        result = audit_shadow_session([f1], shadow_commands=None, authorized_controller_a_duties=None)
        self.assertEqual(result.verdict, "DATA_INSUFFICIENT")

    def test_audit_shadow_session_pass_when_fully_provided_and_isolated(self):
        f1 = dict(self.valid_frame, seq=1, elapsed_ms=1000, uptime_ms=1000, t_inside_c=20.0, pwm_duty=500)
        f2 = dict(self.valid_frame, seq=2, elapsed_ms=2000, uptime_ms=2000, t_inside_c=19.98, pwm_duty=500)
        shadow_cmds = [800, 900]
        auth_a = [500, 500]
        result = audit_shadow_session([f1, f2], shadow_cmds, auth_a)
        self.assertEqual(result.verdict, "PASS")
        self.assertFalse(result.predictive_leak_detected)


class TestW17EvidenceIsPerFrame(unittest.TestCase):
    """Shadow isolation must be evaluated on every frame, and absence must refuse."""

    BASE = {
        "t_inside_c": 5.0, "t_inside_status": "OK", "t_cold_side_c": 3.0,
        "t_hot_side_c": 28.0, "door_open": False, "door_status": "OK",
        "voltage_v": 12.0, "current_a": 4.5, "power_w": 54.0, "quality": "OK",
        "pwm_duty": 800,
    }

    def session(self, n=4, mutate=None):
        frames = []
        for i in range(n):
            frame = dict(self.BASE, seq=i + 1, uptime_ms=1000 * (i + 1), elapsed_ms=1000 * (i + 1))
            if mutate and i in mutate:
                mutate[i](frame)
            frames.append(frame)
        return frames

    def audit(self, frames, n=None):
        n = n if n is not None else len(frames)
        return audit_shadow_session(
            frames,
            shadow_commands=[0] * n,
            authorized_controller_a_duties=[800] * n,
        )

    def test_complete_session_still_passes(self):
        """Positive control: the guards must not have become an always-refuse stub."""
        self.assertEqual(self.audit(self.session()).verdict, "PASS")

    def test_channel_missing_only_on_middle_frame_is_not_pass(self):
        frames = self.session(4, mutate={2: lambda f: f.pop("current_a")})
        result = self.audit(frames)
        self.assertEqual(result.verdict, "CHANNEL_MISMATCH")
        self.assertIn("current_a", result.missing_b_channels)
        self.assertEqual(result.details["frames_with_missing_channels"], 1)

    def test_channel_missing_only_on_last_frame_is_not_pass(self):
        frames = self.session(3, mutate={2: lambda f: f.pop("quality")})
        result = self.audit(frames)
        self.assertEqual(result.verdict, "CHANNEL_MISMATCH")
        self.assertIn("quality", result.missing_b_channels)

    def test_absent_applied_duty_is_refused_instead_of_read_as_zero(self):
        frames = self.session(3, mutate={1: lambda f: f.pop("pwm_duty")})
        result = self.audit(frames)
        self.assertEqual(result.verdict, "DATA_INSUFFICIENT")
        self.assertEqual(result.details["frames_without_applied_duty"], [1])

    def test_nan_applied_duty_is_refused(self):
        frames = self.session(3, mutate={0: lambda f: f.update(pwm_duty=float("nan"))})
        result = self.audit(frames)
        self.assertEqual(result.verdict, "DATA_INSUFFICIENT")
        self.assertEqual(result.details["frames_without_applied_duty"], [0])

    def test_stream_without_sequence_identity_does_not_pass(self):
        frames = [dict(f) for f in self.session(3)]
        for frame in frames:
            frame.pop("seq")
            frame.pop("uptime_ms")
            frame.pop("elapsed_ms")
        result = audit_shadow_session(frames, shadow_commands=[0] * 3,
                                      authorized_controller_a_duties=[800] * 3)
        self.assertEqual(result.verdict, "SEQUENCE_ERROR")
        self.assertTrue(any("missing or invalid seq" in e for e in result.frame_sequence_errors))
        self.assertTrue(any("uptime_ms" in e for e in result.frame_sequence_errors))

    def test_desynchronised_shadow_arrays_refuse_without_raising(self):
        frames = self.session(3)
        result = audit_shadow_session(frames, shadow_commands=[0, 0],
                                      authorized_controller_a_duties=[800] * 3)
        self.assertEqual(result.verdict, "DATA_INSUFFICIENT")
        self.assertIn("desynchronised", result.details["note"])

    def test_nan_chamber_temperature_is_not_treated_as_compliant(self):
        frames = self.session(3)
        frames[1]["t_inside_c"] = float("nan")
        result = self.audit(frames)
        self.assertEqual(result.verdict, "CHANNEL_MISMATCH")
        self.assertIn("t_inside_c", result.missing_b_channels)

    def test_monitor_skips_unusable_samples_without_claiming_clean(self):
        frames = self.session(3)
        frames[1]["t_inside_c"] = float("nan")
        self.assertEqual(monitor_plant_anomalies(frames), [])
        frames[1]["t_inside_c"] = 5.0
        frames[2]["t_inside_c"] = 40.0
        anomalies = monitor_plant_anomalies(frames)
        self.assertTrue(anomalies and anomalies[0]["index"] == 2)
        self.assertEqual(anomalies[0]["reason"], "CHAMBER_RATE_EXCEEDS_W08_ENVELOPE")


class TestW17NoPassOnUnusableEvidence(unittest.TestCase):
    """Presence of a field is not usability, and identical arrays cannot falsify a leak."""

    BASE = {
        "t_inside_c": 5.0, "t_inside_status": "OK", "t_cold_side_c": 3.0,
        "t_hot_side_c": 28.0, "door_open": False, "door_status": "OK",
        "voltage_v": 12.0, "current_a": 4.5, "power_w": 54.0, "quality": "OK",
        "pwm_duty": 800,
    }

    def frames(self, n=4, step_ms=1000, mutate=None):
        out = []
        for i in range(n):
            f = dict(self.BASE, seq=i + 1, uptime_ms=1000 * (i + 1), elapsed_ms=1000 * (i + 1))
            if i:
                f["uptime_ms"] = 1000 + step_ms * i
                f["elapsed_ms"] = 1000 + step_ms * i
            if mutate and i in mutate:
                mutate[i](f)
            out.append(f)
        return out

    def audit(self, frames, shadow=None, authorized=None):
        n = len(frames)
        return audit_shadow_session(
            frames,
            shadow_commands=[0] * n if shadow is None else shadow,
            authorized_controller_a_duties=[800] * n if authorized is None else authorized,
        )

    def test_positive_control_still_passes(self):
        self.assertEqual(self.audit(self.frames()).verdict, "PASS")

    def test_empty_numeric_channel_is_not_evidence(self):
        f = self.frames(4, mutate={2: lambda x: x.update(t_inside_c="")})
        self.assertEqual(self.audit(f).verdict, "CHANNEL_MISMATCH")

    def test_placeholder_sentinel_is_not_evidence(self):
        f = self.frames(4, mutate={1: lambda x: x.update(current_a=-9999)})
        res = self.audit(f)
        self.assertEqual(res.verdict, "CHANNEL_MISMATCH")
        self.assertIn("current_a", res.missing_b_channels)

    def test_blank_status_is_not_evidence(self):
        f = self.frames(4, mutate={3: lambda x: x.update(door_status="   ")})
        self.assertEqual(self.audit(f).verdict, "CHANNEL_MISMATCH")

    def test_aliased_shadow_and_authorized_arrays_refuse(self):
        duty = [800, 800, 800, 800]
        res = self.audit(self.frames(4), shadow=duty, authorized=duty)
        self.assertEqual(res.verdict, "DATA_INSUFFICIENT")
        self.assertIn("same object", res.details["note"])

    def test_elementwise_identical_arrays_refuse(self):
        res = self.audit(self.frames(4), shadow=[800, 800, 800, 800], authorized=[800, 800, 800, 800])
        self.assertEqual(res.verdict, "DATA_INSUFFICIENT")
        self.assertIn("leak could not be detected", res.details["note"])

    def test_single_frame_session_is_refused(self):
        res = self.audit(self.frames(1))
        self.assertEqual(res.verdict, "DATA_INSUFFICIENT")
        self.assertTrue(any("SESSION_TOO_SHORT" in e for e in res.frame_sequence_errors))

    def test_two_frame_session_is_still_comparable(self):
        """The minimum guard must refuse only sessions with no pair to compare."""
        self.assertEqual(self.audit(self.frames(2)).verdict, "PASS")

    def test_cadence_gap_cannot_dilute_a_real_excursion(self):
        """A 20 K rise spread over ten minutes must not read as a compliant rate."""
        f = self.frames(4, step_ms=600000)
        f[2]["t_inside_c"] = 25.0
        f[3]["t_inside_c"] = 45.0
        res = self.audit(f)
        self.assertNotEqual(res.verdict, "PASS")
        self.assertTrue(any("Cadence gap" in e for e in res.frame_sequence_errors))

    def test_real_leak_still_detected_with_independent_shadow(self):
        """Hardening must not have blinded the isolation check itself."""
        frames = self.frames(4, mutate={
            2: lambda x: x.update(pwm_duty=650),   # applied matches neither authorised nor 0
        })
        res = self.audit(frames, shadow=[0, 0, 650, 0], authorized=[800, 800, 800, 800])
        self.assertTrue(res.predictive_leak_detected)


if __name__ == "__main__":
    unittest.main()
