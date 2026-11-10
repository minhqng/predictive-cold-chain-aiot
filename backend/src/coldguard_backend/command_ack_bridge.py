"""Owner-owned command/ACK serial integration bridge (W06/W13 prerequisite).

Connects the Member C backend command producer (``Command``, Doc 02 section
28.1) to the Member A device serial consumer, and the device ``#CG CMDACK``
back to the Member C ``CommandAck`` envelope. C#69's serial gateway publishes
JSON commands and explicitly skips CMDACK records ("have their own contracts");
the device consumes flat ``key=value``. This bridge is the bounded integration
layer between those two immutable implementations, built from the existing
``command_translation`` and ``ack_translation`` adapters.

It is owner-owned additive code. Wiring it into Member C's immutable
``backend/scripts/serial_gateway.py`` (calling ``dispatch_command`` on the
downlink and ``ingest_ack`` on the uplink) is a separate member-source decision
(REQUIRES_MEMBER_SOURCE_MODIFICATION); this module does not override or
monkey-patch any member internal.

Safety: correlation is fail-closed (an ACK whose command_id does not match the
dispatched command is refused, never silently accepted); device clock-sync,
expiry and action-range validation remain the device's own authority. No
timestamp, threshold or verdict is invented.
"""

from __future__ import annotations

from .ack_translation import device_ack_to_backend
from .command_translation import translate_command_to_device_serial
from .contracts import Command


class CommandAckCorrelationError(ValueError):
    """An ACK did not correlate to the dispatched command (fail-closed refusal)."""


def dispatch_command(command: Command) -> str:
    """Downlink: render the backend Command as the device key=value record."""
    return translate_command_to_device_serial(command)


def ingest_ack(line: str, *, expected_command_id: str | None = None) -> dict:
    """Uplink: render a device #CG CMDACK as the backend CommandAck envelope.

    When ``expected_command_id`` is supplied, the ACK must carry the same
    command_id or it is refused (fail-closed correlation). The device verdict
    and interpretability fields pass through unchanged.
    """
    envelope = device_ack_to_backend(line)
    if expected_command_id is not None and envelope["command_id"] != expected_command_id:
        raise CommandAckCorrelationError(
            f"ACK_COMMAND_MISMATCH: ack command_id={envelope['command_id']!r} "
            f"!= expected {expected_command_id!r}; refusing to correlate"
        )
    return envelope


def round_trip(command: Command, ack_line: str) -> dict:
    """Execute the full command/ACK loop: dispatch then ingest the correlated ACK.

    Returns the device record and the backend ACK envelope. Raises on any
    translation or correlation failure (fail-closed); never fabricates a PASS.
    """
    record = dispatch_command(command)
    envelope = ingest_ack(ack_line, expected_command_id=command.command_id)
    return {"device_record": record, "ack_envelope": envelope}