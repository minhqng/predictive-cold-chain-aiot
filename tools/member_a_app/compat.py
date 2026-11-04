"""Image compatibility classification for the acceptance application.

The application speaks two real grammars:

* canonical W06 `#CG TELEM` schema 3 plus the canonical console verbs;
* H8 bench `#CG H8S` schema 3 plus STAGE/SUPERVISE/ARM/START/STOP/ACK.

An image is never silently treated as the other. Canonical acceptance tests
that need W06 fields are INCOMPLETE on an H8 image, and H8 supervised checks
are never reported as canonical W06 PASS.
"""

from __future__ import annotations

import dataclasses
import pathlib
from typing import Any

from .device import DeviceSnapshot


@dataclasses.dataclass(frozen=True)
class ImageCompatibility:
    kind: str
    device_id: str | None
    boot_id: str | None
    firmware_version: str | None
    telemetry: bool
    canonical_telemetry: bool
    canonical_console_commands: bool
    accepted_canonical_commands: bool
    h8_console_commands: bool
    h8_host_ack_required: bool
    h8_stage_f_probe: bool
    h8_endurance_stages_present: bool
    output_stage: str | None
    supervised: bool | None
    off_current_approved: bool | None
    h8_stages: str | None
    notes: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)

    def capability_rows(self) -> list[tuple[str, str]]:
        return [
            ("Image class", self.kind),
            ("Telemetry capture", "YES" if self.telemetry else "NO"),
            ("Canonical W06 telemetry", "YES" if self.canonical_telemetry else "NO"),
            ("Canonical console verbs", "YES" if self.canonical_console_commands else "NO"),
            ("Accepted canonical command path",
             "YES" if self.accepted_canonical_commands else "NO"),
            ("H8 console verbs", "YES" if self.h8_console_commands else "NO"),
            ("H8 host ACK required", "YES" if self.h8_host_ack_required else "NO"),
            ("H8 Stage F probe", "IMPLEMENTED_APPROVAL_UNREPORTED"
             if self.h8_stage_f_probe else "NO"),
            ("H8 A-E endurance stages", "PRESENT_NOT_USED" if self.h8_endurance_stages_present else "NO"),
            ("W06 output stage", self.output_stage or "UNKNOWN"),
            ("H8 supervised bench", _tri(self.supervised)),
            ("H8 OFF-current gate", _tri(self.off_current_approved)),
            ("H8 stages", self.h8_stages or "UNKNOWN"),
        ]


def _tri(value: bool | None) -> str:
    if value is None:
        return "UNKNOWN"
    return "YES" if value else "NO"


def _flag(value: Any) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    text = str(value).strip().upper()
    if text in {"1", "TRUE", "YES", "CONFIRMED", "APPROVED"}:
        return True
    if text in {"0", "FALSE", "NO", "UNCONFIRMED"}:
        return False
    return None


def classify(snapshot: DeviceSnapshot) -> ImageCompatibility:
    kind = snapshot.firmware_kind or "UNKNOWN"
    frame = snapshot.last_frame
    h8: dict[str, Any] = snapshot.h8 or {}
    if kind == "H8_BENCH":
        supervised = _flag(h8.get("supervised_bench", h8.get("supervised")))
        off_approved = _flag(h8.get("off_current_approved"))
        return ImageCompatibility(
            kind="H8_BENCH",
            device_id=snapshot.boot.device_id,
            boot_id=snapshot.boot.boot_id,
            firmware_version=snapshot.boot.firmware_version or h8.get("firmware"),
            telemetry=True,
            canonical_telemetry=False,
            canonical_console_commands=False,
            accepted_canonical_commands=False,
            h8_console_commands=True,
            h8_host_ack_required=True,
            h8_stage_f_probe=True,
            h8_endurance_stages_present=True,
            output_stage="H8_STAGE_ENGINE",
            supervised=supervised,
            off_current_approved=off_approved,
            h8_stages=h8.get("stages"),
            notes=(
                "Read-only H8S telemetry is supported.",
                "Canonical W06 acceptance tests are INCOMPLETE on this image.",
                "H8 Stage F is the only conservative supervised probe; the image does not report its approval, so START may refuse.",
                "H8 A-E are endurance stages and are not used for acceptance.",
                "H8 START requires a fresh host ACK and the FAN, DOOR, SUPERVISE and ARM gates.",
            ),
        )
    if kind == "CANONICAL":
        stage = (frame.output_stage if frame is not None else None) or "UNKNOWN"
        return ImageCompatibility(
            kind="CANONICAL_W06",
            device_id=snapshot.boot.device_id,
            boot_id=snapshot.boot.boot_id,
            firmware_version=snapshot.boot.firmware_version,
            telemetry=True,
            canonical_telemetry=True,
            canonical_console_commands=True,
            accepted_canonical_commands=False,
            h8_console_commands=False,
            h8_host_ack_required=False,
            h8_stage_f_probe=False,
            h8_endurance_stages_present=False,
            output_stage=stage,
            supervised=None,
            off_current_approved=None,
            h8_stages=None,
            notes=(
                "Canonical W06 telemetry and console verbs are supported.",
                "The local CMDTEST bridge is refused at the source gate; accepted/idempotent commands need Member C's network transport.",
                "The shipped image compiles the output stage out; supervised START is refused.",
                "A stage-enabled image requires a reviewed hardware adapter; it is not a build-only change.",
            ),
        )
    return ImageCompatibility(
        kind="UNKNOWN",
        device_id=snapshot.boot.device_id,
        boot_id=snapshot.boot.boot_id,
        firmware_version=snapshot.boot.firmware_version,
        telemetry=False,
        canonical_telemetry=False,
        canonical_console_commands=False,
        accepted_canonical_commands=False,
        h8_console_commands=False,
        h8_host_ack_required=False,
        h8_stage_f_probe=False,
        h8_endurance_stages_present=False,
        output_stage=None,
        supervised=None,
        off_current_approved=None,
        h8_stages=None,
        notes=("No recognised image identity has been observed yet.",),
    )


def static_matrix() -> list[str]:
    return [
        "H8_BENCH: #CG H8S schema 3; read-only telemetry; STAGE/SUPERVISE/ARM/START/"
        "STOP/ESTOP/CLEAR/FAN/DOOR/ACK/STATUS; host ACK required; canonical W06 tests INCOMPLETE.",
        "CANONICAL_W06: #CG TELEM schema 3; ARM/START/STOP/ESTOP/CLEAR/RUN/PHASE/"
        "STATUS/CMDTEST; output stage DISABLED in the shipped image; accepted network "
        "commands INCOMPLETE without Member C transport.",
        "Supervised TEC: H8 Stage F probe only (30 s, 20 %); H8 A-E are endurance stages "
        "and are not used. W06 stage enable requires a reviewed hardware adapter.",
    ]


def markdown(compat: ImageCompatibility) -> str:
    lines = [
        f"# Image compatibility: {compat.kind}",
        "",
        f"- device_id: {compat.device_id or 'UNRECORDED'}",
        f"- boot_id: {compat.boot_id or 'UNRECORDED'}",
        f"- firmware: {compat.firmware_version or 'UNRECORDED'}",
        "",
        "| Capability | Result |",
        "|---|---|",
    ]
    lines.extend(f"| {name} | {value} |" for name, value in compat.capability_rows())
    lines.append("")
    lines.append("## Notes")
    lines.extend(f"- {note}" for note in compat.notes)
    return "\n".join(lines) + "\n"


def write_report(compat: ImageCompatibility, path: pathlib.Path) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown(compat), encoding="utf-8")
    return path
