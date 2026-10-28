"""Render evidence/D/W01/trust-boundary.png with the Python standard library.

This script exists so the diagram is reproducible without installing a
graphics dependency. It is evidence tooling only: it is not part of the
control package and contains no policy logic.

Run:  python evidence/D/W01/trust_boundary_source.py
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

WIDTH = 1500
HEIGHT = 980

WHITE = (255, 255, 255)
INK = (20, 28, 38)
MUTED = (90, 102, 118)
BLUE = (36, 92, 168)
LIGHT_BLUE = (232, 241, 252)
GREEN = (20, 122, 82)
LIGHT_GREEN = (228, 246, 238)
RED = (186, 38, 46)
LIGHT_RED = (253, 235, 235)
AMBER = (166, 106, 0)

FONT: dict[str, tuple[str, ...]] = {
    "A": ("01110", "10001", "10001", "11111", "10001", "10001", "10001"),
    "B": ("11110", "10001", "10001", "11110", "10001", "10001", "11110"),
    "C": ("01111", "10000", "10000", "10000", "10000", "10000", "01111"),
    "D": ("11110", "10001", "10001", "10001", "10001", "10001", "11110"),
    "E": ("11111", "10000", "10000", "11110", "10000", "10000", "11111"),
    "F": ("11111", "10000", "10000", "11110", "10000", "10000", "10000"),
    "G": ("01111", "10000", "10000", "10111", "10001", "10001", "01111"),
    "H": ("10001", "10001", "10001", "11111", "10001", "10001", "10001"),
    "I": ("11111", "00100", "00100", "00100", "00100", "00100", "11111"),
    "J": ("00111", "00010", "00010", "00010", "00010", "10010", "01100"),
    "K": ("10001", "10010", "10100", "11000", "10100", "10010", "10001"),
    "L": ("10000", "10000", "10000", "10000", "10000", "10000", "11111"),
    "M": ("10001", "11011", "10101", "10101", "10001", "10001", "10001"),
    "N": ("10001", "11001", "10101", "10011", "10001", "10001", "10001"),
    "O": ("01110", "10001", "10001", "10001", "10001", "10001", "01110"),
    "P": ("11110", "10001", "10001", "11110", "10000", "10000", "10000"),
    "Q": ("01110", "10001", "10001", "10001", "10101", "10010", "01101"),
    "R": ("11110", "10001", "10001", "11110", "10100", "10010", "10001"),
    "S": ("01111", "10000", "10000", "01110", "00001", "00001", "11110"),
    "T": ("11111", "00100", "00100", "00100", "00100", "00100", "00100"),
    "U": ("10001", "10001", "10001", "10001", "10001", "10001", "01110"),
    "V": ("10001", "10001", "10001", "10001", "10001", "01010", "00100"),
    "W": ("10001", "10001", "10001", "10101", "10101", "10101", "01010"),
    "X": ("10001", "10001", "01010", "00100", "01010", "10001", "10001"),
    "Y": ("10001", "10001", "01010", "00100", "00100", "00100", "00100"),
    "Z": ("11111", "00001", "00010", "00100", "01000", "10000", "11111"),
    "0": ("01110", "10001", "10011", "10101", "11001", "10001", "01110"),
    "1": ("00100", "01100", "00100", "00100", "00100", "00100", "01110"),
    "2": ("01110", "10001", "00001", "00010", "00100", "01000", "11111"),
    "3": ("11111", "00010", "00100", "00010", "00001", "10001", "01110"),
    "4": ("00010", "00110", "01010", "10010", "11111", "00010", "00010"),
    "5": ("11111", "10000", "11110", "00001", "00001", "10001", "01110"),
    "6": ("00110", "01000", "10000", "11110", "10001", "10001", "01110"),
    "7": ("11111", "00001", "00010", "00100", "01000", "01000", "01000"),
    "8": ("01110", "10001", "10001", "01110", "10001", "10001", "01110"),
    "9": ("01110", "10001", "10001", "01111", "00001", "00010", "01100"),
    " ": ("00000", "00000", "00000", "00000", "00000", "00000", "00000"),
    "-": ("00000", "00000", "00000", "11111", "00000", "00000", "00000"),
    ".": ("00000", "00000", "00000", "00000", "00000", "01100", "01100"),
    "/": ("00001", "00010", "00010", "00100", "01000", "01000", "10000"),
    ":": ("00000", "01100", "01100", "00000", "01100", "01100", "00000"),
    "(": ("00010", "00100", "01000", "01000", "01000", "00100", "00010"),
    ")": ("01000", "00100", "00010", "00010", "00010", "00100", "01000"),
    ">": ("01000", "00100", "00010", "00001", "00010", "00100", "01000"),
    "<": ("00010", "00100", "01000", "10000", "01000", "00100", "00010"),
    "+": ("00000", "00100", "00100", "11111", "00100", "00100", "00000"),
    ",": ("00000", "00000", "00000", "00000", "01100", "00100", "01000"),
    "?": ("01110", "10001", "00001", "00010", "00100", "00000", "00100"),
    "!": ("00100", "00100", "00100", "00100", "00100", "00000", "00100"),
    "'": ("00100", "00100", "01000", "00000", "00000", "00000", "00000"),
    "=": ("00000", "00000", "11111", "00000", "11111", "00000", "00000"),
    "[": ("01110", "01000", "01000", "01000", "01000", "01000", "01110"),
    "]": ("01110", "00010", "00010", "00010", "00010", "00010", "01110"),
    "_": ("00000", "00000", "00000", "00000", "00000", "00000", "11111"),
}


class Canvas:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.pixels = bytearray(
            channel
            for _ in range(width * height)
            for channel in WHITE
        )

    def _set(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            offset = (y * self.width + x) * 3
            self.pixels[offset : offset + 3] = bytes(color)

    def fill(self, x: int, y: int, w: int, h: int, color) -> None:
        for yy in range(max(0, y), min(self.height, y + h)):
            for xx in range(max(0, x), min(self.width, x + w)):
                self._set(xx, yy, color)

    def rect(
        self,
        x: int,
        y: int,
        w: int,
        h: int,
        color,
        thickness: int = 3,
        fill_color=None,
    ) -> None:
        if fill_color is not None:
            self.fill(x, y, w, h, fill_color)
        for t in range(thickness):
            for xx in range(x - t, x + w + t):
                self._set(xx, y - t, color)
                self._set(xx, y + h + t, color)
            for yy in range(y - t, y + h + t):
                self._set(x - t, yy, color)
                self._set(x + w + t, yy, color)

    def line(
        self,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        color,
        thickness: int = 3,
        dash: int = 0,
    ) -> None:
        dx = x1 - x0
        dy = y1 - y0
        steps = max(abs(dx), abs(dy), 1)
        for step in range(steps + 1):
            if dash and (step // dash) % 2 == 1:
                continue
            x = round(x0 + dx * step / steps)
            y = round(y0 + dy * step / steps)
            half = thickness // 2
            for oy in range(-half, half + 1):
                for ox in range(-half, half + 1):
                    self._set(x + ox, y + oy, color)

    def arrow(
        self,
        x0: int,
        y0: int,
        x1: int,
        y1: int,
        color,
        thickness: int = 3,
        dash: int = 0,
    ) -> None:
        self.line(x0, y0, x1, y1, color, thickness, dash)
        dx = x1 - x0
        dy = y1 - y0
        length = max((dx * dx + dy * dy) ** 0.5, 1.0)
        ux, uy = dx / length, dy / length
        px, py = -uy, ux
        head = 16
        spread = 7
        self.line(
            x1,
            y1,
            round(x1 - ux * head + px * spread),
            round(y1 - uy * head + py * spread),
            color,
            thickness,
        )
        self.line(
            x1,
            y1,
            round(x1 - ux * head - px * spread),
            round(y1 - uy * head - py * spread),
            color,
            thickness,
        )

    def text(
        self,
        x: int,
        y: int,
        value: str,
        color=INK,
        scale: int = 2,
        spacing: int = 2,
    ) -> None:
        cursor = x
        for char in value.upper():
            glyph = FONT.get(char, FONT["?"])
            for row_index, row in enumerate(glyph):
                for col_index, bit in enumerate(row):
                    if bit == "1":
                        self.fill(
                            cursor + col_index * scale,
                            y + row_index * scale,
                            scale,
                            scale,
                            color,
                        )
            cursor += (5 + spacing) * scale

    def save(self, path: Path) -> None:
        raw = bytearray()
        stride = self.width * 3
        for row in range(self.height):
            raw.append(0)
            raw.extend(self.pixels[row * stride : (row + 1) * stride])

        def chunk(kind: bytes, data: bytes) -> bytes:
            return (
                struct.pack(">I", len(data))
                + kind
                + data
                + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
            )

        png = (
            b"\x89PNG\r\n\x1a\n"
            + chunk(
                b"IHDR",
                struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0),
            )
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b"")
        )
        path.write_bytes(png)


def build() -> Canvas:
    c = Canvas(WIDTH, HEIGHT)

    c.text(40, 28, "COLDGUARD TRUST BOUNDARIES - MEMBER D W01", INK, scale=3)
    c.text(
        40,
        74,
        "MODEL ADVISES BACKEND ONLY. NO MODEL, DB, FRONTEND OR OPERATOR PATH "
        "REACHES GPIO DIRECTLY.",
        MUTED,
        scale=2,
    )

    # ---- trust zones -----------------------------------------------------
    c.rect(40, 130, 530, 760, BLUE, thickness=3, fill_color=LIGHT_BLUE)
    c.text(58, 146, "DEVICE / LOCAL SAFETY ZONE", BLUE, scale=2)
    c.rect(620, 130, 840, 430, BLUE, thickness=3, fill_color=(247, 250, 255))
    c.text(638, 146, "CLOUD / BACKEND ZONE", BLUE, scale=2)
    c.rect(960, 650, 500, 240, BLUE, thickness=3, fill_color=(247, 250, 255))
    c.text(978, 666, "USER / OPERATIONS ZONE", BLUE, scale=2)

    # ---- device ----------------------------------------------------------
    c.rect(70, 200, 470, 230, INK, thickness=3, fill_color=WHITE)
    c.text(88, 214, "DEVICE (ESP32)", INK, scale=2)
    c.text(
        88,
        246,
        "SENSORS: DS18B20 / BME280 / PZEM",
        MUTED,
        scale=1,
    )
    c.rect(78, 278, 220, 58, GREEN, thickness=3, fill_color=LIGHT_GREEN)
    c.text(92, 292, "LOCAL POLICY +", GREEN, scale=2)
    c.text(92, 312, "SAFETY GATE", GREEN, scale=2)
    c.rect(322, 278, 206, 58, INK, thickness=3, fill_color=WHITE)
    c.text(338, 292, "TEC + FAN", INK, scale=2)
    c.text(338, 312, "ACTUATOR DRIVER", INK, scale=2)
    c.text(
        88,
        352,
        "BOOT DEFAULT = OFF / WATCHDOG / PHYSICAL INTERLOCKS",
        MUTED,
        scale=1,
    )
    c.text(
        88,
        374,
        "LOCAL PROTECTION ALWAYS WINS; ANY COMMAND CAN BE REJECTED.",
        GREEN,
        scale=1,
    )

    # ---- broker / backend / db / model ----------------------------------
    c.rect(640, 220, 190, 130, BLUE, thickness=3, fill_color=WHITE)
    c.text(656, 234, "MQTT BROKER", BLUE, scale=2)
    c.text(656, 266, "TLS CAPABLE", MUTED, scale=1)
    c.text(656, 284, "ACL / AUTH", MUTED, scale=1)
    c.text(656, 302, "QOS1 / NO RETAIN", MUTED, scale=1)
    c.text(656, 320, "ROUTE ONLY", MUTED, scale=1)

    c.rect(900, 210, 280, 150, BLUE, thickness=3, fill_color=WHITE)
    c.text(916, 224, "BACKEND (C)", BLUE, scale=2)
    c.text(916, 256, "AUTHN + AUTHZ", MUTED, scale=1)
    c.text(916, 274, "COMMAND VALIDATE", MUTED, scale=1)
    c.text(916, 292, "TTL / IDEMPOTENCY", MUTED, scale=1)
    c.text(916, 310, "ACK + AUDIT", MUTED, scale=1)
    c.text(916, 328, "CANNOT BYPASS DEVICE GATE", RED, scale=1)

    c.rect(1240, 210, 200, 150, BLUE, thickness=3, fill_color=WHITE)
    c.text(1256, 224, "DATABASE", BLUE, scale=2)
    c.text(1256, 256, "AUDIT / STATE", MUTED, scale=1)
    c.text(1256, 274, "HISTORY", MUTED, scale=1)
    c.text(1256, 292, "CANNOT PUBLISH", RED, scale=1)
    c.text(1256, 310, "CONTROL COMMANDS", RED, scale=1)

    c.rect(1240, 410, 200, 130, BLUE, thickness=3, fill_color=WHITE)
    c.text(1256, 424, "MODEL (B)", BLUE, scale=2)
    c.text(1256, 456, "RISK ADVISORY", MUTED, scale=1)
    c.text(1256, 474, "VERSION + HORIZON", MUTED, scale=1)
    c.text(1256, 492, "NO ACTUATION", RED, scale=1)
    c.text(1256, 510, "NO GPIO ACCESS", RED, scale=1)

    # ---- frontend / operator --------------------------------------------
    c.rect(1000, 700, 240, 120, BLUE, thickness=3, fill_color=WHITE)
    c.text(1016, 714, "FRONTEND", BLUE, scale=2)
    c.text(1016, 746, "USER INTENT ONLY", MUTED, scale=1)
    c.text(1016, 764, "NO DEVICE CREDENTIALS", RED, scale=1)
    c.text(1016, 782, "NO DIRECT ACTUATION", RED, scale=1)

    c.rect(1280, 700, 180, 120, BLUE, thickness=3, fill_color=WHITE)
    c.text(1296, 714, "OPERATOR", BLUE, scale=2)
    c.text(1296, 746, "AUTHENTICATED", MUTED, scale=1)
    c.text(1296, 764, "HUMAN INTENT", MUTED, scale=1)
    c.text(1296, 782, "NO GPIO ACCESS", RED, scale=1)

    # ---- authority flows -------------------------------------------------
    c.arrow(298, 307, 322, 307, GREEN, thickness=4)

    # broker <-> device: commands arrive, telemetry/ACK leaves
    c.arrow(640, 250, 540, 250, BLUE, thickness=2)
    c.text(548, 228, "COMMAND V1", BLUE, scale=1)
    c.arrow(540, 310, 640, 310, BLUE, thickness=2)
    c.text(548, 316, "ACK / TELEM", BLUE, scale=1)

    # backend <-> broker
    c.arrow(900, 250, 830, 250, BLUE, thickness=2)
    c.text(836, 228, "CMD", BLUE, scale=1)
    c.arrow(830, 290, 900, 290, BLUE, thickness=2)
    c.text(836, 296, "TELEM", BLUE, scale=1)

    # backend <-> db
    c.line(1180, 250, 1240, 250, BLUE, thickness=2)
    c.arrow(1180, 270, 1240, 270, BLUE, thickness=2)
    c.text(1186, 228, "AUDIT", BLUE, scale=1)
    c.text(1186, 278, "STATE", BLUE, scale=1)

    # model -> backend (advisory only)
    c.arrow(1240, 450, 1160, 362, BLUE, thickness=2, dash=6)

    # frontend -> backend (routed right of the forbidden box)
    c.arrow(1120, 700, 1120, 362, BLUE, thickness=2)
    c.text(1000, 600, "HTTPS + RBAC", BLUE, scale=1)
    c.text(1000, 618, "INTENT ONLY", BLUE, scale=1)

    # operator -> frontend
    c.arrow(1280, 760, 1240, 760, BLUE, thickness=2)
    c.text(1252, 736, "LOGIN", BLUE, scale=1)

    # ---- explicitly forbidden model path --------------------------------
    c.line(1240, 485, 1040, 500, RED, thickness=4, dash=8)
    c.text(1036, 476, "X", RED, scale=6)
    c.rect(630, 455, 400, 85, RED, thickness=4, fill_color=LIGHT_RED)
    c.text(646, 468, "FORBIDDEN PATH", RED, scale=2)
    c.text(
        646,
        502,
        "MODEL / DB / UI / OPERATOR -> GPIO OR ACTUATOR",
        RED,
        scale=1,
    )

    # ---- authority notes -------------------------------------------------
    c.rect(70, 470, 470, 390, AMBER, thickness=2, fill_color=(255, 251, 240))
    c.text(88, 486, "AUTHORITY NOTES", AMBER, scale=2)
    notes = (
        "DEVICE: MAY REJECT ANY COMMAND. LOCAL SAFETY GATE IS LAST.",
        "BROKER: ROUTES AUTHENTICATED MESSAGES. CANNOT AUTHORIZE.",
        "BACKEND: AUTHZ + VALIDATION + TTL + IDEMPOTENCY + AUDIT.",
        "DATABASE: STORES EVIDENCE. CANNOT ISSUE CONTROL.",
        "MODEL: ADVISORY SCORE ONLY. NEVER TOUCHES AN ACTUATOR.",
        "FRONTEND: REQUESTS INTENT. NO DEVICE CREDENTIALS.",
        "OPERATOR: AUTHENTICATED HUMAN. NO GPIO / DIRECT ACTUATION.",
        "ALL PATHS MUST PASS: AUTHZ -> TTL -> IDEMPOTENCY -> RANGE",
        "-> LOCAL SAFETY -> PHYSICAL VERIFICATION.",
    )
    y = 522
    for note in notes:
        c.text(88, y, note, INK, scale=1)
        y += 30

    # ---- legend / footer -------------------------------------------------
    c.rect(620, 720, 30, 18, GREEN, thickness=1, fill_color=GREEN)
    c.text(660, 724, "LOCAL AUTHORITY / SAFETY", GREEN, scale=1)
    c.rect(620, 750, 30, 18, BLUE, thickness=1, fill_color=BLUE)
    c.text(660, 754, "TRUST BOUNDARY / AUTHORIZED FLOW", BLUE, scale=1)
    c.rect(620, 780, 30, 18, RED, thickness=1, fill_color=RED)
    c.text(660, 784, "FORBIDDEN / BLOCKED PATH", RED, scale=1)
    c.text(
        620,
        830,
        "SOURCE: DOCS 00-02. DOC 05D D-W01-03.",
        MUTED,
        scale=1,
    )
    c.text(
        620,
        850,
        "DESIGN EVIDENCE, NOT A CERTIFICATION.",
        MUTED,
        scale=1,
    )
    c.text(
        620,
        870,
        "SYNTHETIC; NO DEVICE WAS COMMANDED.",
        MUTED,
        scale=1,
    )

    return c


if __name__ == "__main__":
    destination = Path(__file__).with_name("trust-boundary.png")
    build().save(destination)
    print(f"wrote {destination} ({destination.stat().st_size} bytes)")
