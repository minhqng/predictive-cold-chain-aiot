"""Leader-owned reproducible commissioning build (member sources untouched).

Stages a COPY of the delivered firmware tree into an isolated output
directory, applies the commissioning parameter patch THERE ONLY (the member
tree stays byte-identical), saves the exact diff + a SHA-256 manifest of
every staged file, and optionally runs the ESP-IDF build.

The produced image is INERT until the physical gates are real:
- with --interlock-gpio 0 (default) the Leader adapter reads the interlock
  open forever (fail closed);
- with --duty-permille 0 (default) Member A refuses every START;
- the runtime interlock read, Member A's admission chain and the Leader
  adapter's force-off-on-refusal stay in the binary either way.

This script NEVER modifies the member firmware tree and never flashes.

Usage (safe, staging + manifest only):
  python leader_commissioning_build.py --output C:/cgb/staging-final

Usage (full build, after the owner supplies verified values):
  python leader_commissioning_build.py --output C:/cgb/staging-final \
      --interlock-gpio 7 --duty-permille 200 --build
"""

from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
FIRMWARE_SRC = REPO_ROOT / "firmware"
CONFIG_REL = Path("main") / "coldguard_config.h"
IDF_PROFILE = r"C:\Espressif\tools\Microsoft.v6.1.PowerShell_profile.ps1"

# The recalibrated polarity (owner live observation 2026-11-13): raw 1 = OPEN.
DOOR_RAW_OPEN_LEVEL_DEFAULT = 1
# The three member commissioning constants (docs/06 section 9 conditions).
TOGGLES = {
    "CG_ACTUATOR_ENABLE_ALLOWED": 1,
    "CG_TEC_OUTPUT_STAGE_ENABLED": 1,
    "CG_TEC_HARDWARE_GATES_VERIFIED": 1,
    # D25: authorizes the calibrated raw->semantic mapping (owner live
    # observation recorded 2026-11-13: raw 0 = CLOSED, raw 1 = OPEN; the
    # level itself comes from --door-open-level). The per-boot physical
    # open/close attestation stays in force: a fresh boot still reports
    # UNVERIFIED until both committed levels appear on that boot's stream.
    "CG_DOOR_POLARITY_CONFIRMED": 1,
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def patch_config(text: str, duty: int, door_open_level: int) -> str:
    """Apply the member-documented commissioning constants + parameters.

    Only whole-line `#define <NAME> <value>` replacements; anything the
    regex cannot find fails the build loudly instead of silently producing
    an image without the intended semantics.
    """
    replacements = {
        **{name: f"#define {name} {value}" for name, value in TOGGLES.items()},
        "CG_TEC_REQUEST_DUTY_PERMILLE": f"#define CG_TEC_REQUEST_DUTY_PERMILLE {duty}",
        "CG_DOOR_RAW_OPEN_LEVEL": f"#define CG_DOOR_RAW_OPEN_LEVEL {door_open_level}",
    }
    out_lines = []
    replaced = {name: 0 for name in replacements}
    for line in text.splitlines(keepends=True):
        stripped = line.strip()
        for name, replacement in replacements.items():
            if stripped.startswith(f"#define {name} "):
                out_lines.append(replacement + "\n")
                replaced[name] += 1
                break
        else:
            out_lines.append(line)
    missing = [name for name, n in replaced.items() if n != 1]
    if missing:
        raise SystemExit(f"patch error: expected exactly one define for {missing}; "
                         f"found counts {replaced} - refusing to stage")
    return "".join(out_lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", required=True, type=Path,
                        help="staging/build output directory (created fresh)")
    parser.add_argument("--interlock-gpio", type=int, default=0,
                        help="U6 sense GPIO configured via Kconfig (0/-1 = none "
                             "installed: the image stays fail-closed). Required "
                             "with --interlock-mode pin; ignored with none.")
    parser.add_argument("--interlock-mode", choices=["pin", "none"], default="pin",
                        help="pin: a real U6 loop is installed and wired "
                             "(requires --interlock-gpio). none: the owner's "
                             "as-built decision - NO physical interlock exists; "
                             "the protection set is the supervised session, the "
                             "branch fuse and the software chain; the manifest "
                             "records 'NOT FITTED', never 'closed'.")
    parser.add_argument("--interlock-active-low", choices=["0", "1"], default="1",
                        help="U6 electrical polarity (default 1: normally-closed "
                             "loop pulls the input low when closed). Pin mode only.")
    parser.add_argument("--duty-permille", type=int, default=0,
                        help="starting duty in permille (0 = Member A refuses "
                             "every START; the commissioning ladder starts low)")
    parser.add_argument("--door-open-level", type=int,
                        default=DOOR_RAW_OPEN_LEVEL_DEFAULT,
                        help="device door raw level meaning OPEN (recalibrated "
                             "default 1; 0 reproduces the shipped constant)")
    parser.add_argument("--build", action="store_true",
                        help="run the ESP-IDF build after staging (minutes)")
    parser.add_argument("--evidence-note", default="",
                        help="free-text note stored in the manifest (gate "
                             "evidence references for this configuration)")
    parser.add_argument("--supervised-limits", action="store_true",
                        help="link the owner-proposed single-session "
                             "supervisory limit set into the member control "
                             "init (wrap of cg_tec_control_init); WITHOUT it "
                             "the shipped all-unresolved table stays and "
                             "every start is refused fail-closed")
    parser.add_argument("--supervised-no-cold-probe", action="store_true",
                        help="select the named SUPERVISED_NO_COLD_PROBE "
                             "attended characterization profile: omit ONLY "
                             "the missing cold-probe presence check. Requires "
                             "--supervised-limits and --duty-permille 200; "
                             "every other guard stays in force")
    args = parser.parse_args()

    # Interlock mode validation: an explicitly recorded decision, never a
    # silent default. Pin mode requires a real GPIO; none mode records the
    # owner's as-built decision and forbids a simultaneous pin.
    if args.interlock_mode == "pin" and args.interlock_gpio < 1:
        raise SystemExit("--interlock-mode pin requires --interlock-gpio >= 1 "
                         "(no invented pins; use --interlock-mode none only for "
                         "the owner's recorded no-interlock decision)")
    if args.interlock_mode == "none" and args.interlock_gpio >= 1:
        raise SystemExit("--interlock-mode none contradicts --interlock-gpio "
                         "(either a real loop exists, or it does not)")
    # The no-cold-probe profile is a named, narrow deviation: it is only
    # meaningful on top of the supervised session table and its exact first
    # step. Anything else is refused here (and again fail-closed in firmware).
    if args.supervised_no_cold_probe:
        if not args.supervised_limits:
            raise SystemExit("--supervised-no-cold-probe requires "
                             "--supervised-limits (refusing a silent profile)")
        if args.duty_permille != 200:
            raise SystemExit("--supervised-no-cold-probe requires "
                             "--duty-permille 200 (the recorded first step)")

    out: Path = args.output.resolve()
    if out.exists():
        parser.error("--output must identify a new directory")
    out.mkdir(parents=True)
    staging = out / "staging"
    print(f"staging copy: {FIRMWARE_SRC} -> {staging}")
    shutil.copytree(
        FIRMWARE_SRC, staging,
        ignore=shutil.ignore_patterns("build*", "sdkconfig.old", "__pycache__",
                                      "managed_components", ".git*"),
    )
    for entry in staging.glob("sdkconfig"):
        entry.unlink()  # regenerate from sdkconfig.defaults + overlay

    # 1. Parameter patch on the STAGING copy only.
    config_path = staging / CONFIG_REL
    original = config_path.read_text(encoding="utf-8")
    patched = patch_config(original, args.duty_permille, args.door_open_level)
    config_path.write_text(patched, encoding="utf-8")
    diff_path = out / "staging-config.diff"
    diff_path.write_text("".join(difflib.unified_diff(
        original.splitlines(keepends=True), patched.splitlines(keepends=True),
        fromfile="member/coldguard_config.h",
        tofile=f"{out.name}/staging/coldguard_config.h")), encoding="utf-8")

    # 2. sdkconfig overlay (Leader-owned Kconfig knobs; member keys untouched).
    overlay = [
        "CONFIG_CG_LEADER_TEC_HW=y",
    ]
    if args.interlock_mode == "none":
        overlay += [
            "CONFIG_CG_LEADER_TEC_HW_INTERLOCK_PIN=-1",
            "CONFIG_CG_LEADER_TEC_HW_INTERLOCK_NONE_BY_DESIGN=y",
        ]
    else:
        overlay += [
            f"CONFIG_CG_LEADER_TEC_HW_INTERLOCK_PIN={args.interlock_gpio}",
            "CONFIG_CG_LEADER_TEC_HW_INTERLOCK_NONE_BY_DESIGN=",
        ]
    overlay += [
        f"CONFIG_CG_LEADER_TEC_HW_ACTIVE_LOW={args.interlock_active_low}",
        "CONFIG_CG_LEADER_TEC_HW_FAN_CONTINUOUS=y",
    ]
    if args.supervised_limits:
        overlay += ["CONFIG_CG_LEADER_TEC_HW_SUPERVISED_LIMITS=y"]
    if args.supervised_no_cold_probe:
        overlay += ["CONFIG_CG_LEADER_TEC_HW_SUPERVISED_NO_COLD_PROBE=y"]
    defaults_path = staging / "sdkconfig.defaults"
    with defaults_path.open("a", encoding="utf-8") as fh:
        fh.write("\n# Leader commissioning overlay (generated; see manifest)\n")
        for line in overlay:
            fh.write(line + "\n")

    # 3. Manifest: every staged file + the inputs + the gate reminders.
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "generator": "firmware/tools/leader_commissioning_build.py (Leader-owned)",
        "member_tree_untouched": True,
        "inputs": {
            "interlock_mode": args.interlock_mode,
            "interlock_gpio": args.interlock_gpio,
            "interlock_active_low": args.interlock_active_low,
            "duty_permille": args.duty_permille,
            "door_raw_open_level": args.door_open_level,
            "supervised_limits": bool(args.supervised_limits),
            "supervised_limits_statement":
                "owner-proposed single-session envelope 2026-11-13: first "
                "step 200 permille, 30 s, 5.0 A stop, 40.0 C T2 stop, "
                "escalation forbidden - a SESSION envelope, NOT a certified "
                "rating" if args.supervised_limits else "shipped unresolved "
                "(fail closed)",
            "supervised_no_cold_probe": bool(args.supervised_no_cold_probe),
            "cold_probe_profile": (
                "SUPERVISED_NO_COLD_PROBE: attended characterization "
                "deviation; real hardware has NO cold-side probe "
                "(NOT_FITTED). Only the cold-presence check is omitted; "
                "real T2 ROM 28AEBF2200000006 hot input, PZEM, freshness, "
                "interlock/fan, heartbeat and the envelope 200 permille / "
                "30 s / 5 A / 40 C all stay in force. Actuator route matches "
                "H8: R_EN+L_EN driven together, RPWM 1000 Hz / 13 bit, "
                "mixed enables refused. Output is OFF after the deadline. "
                "This is NOT a production mode and makes no cold-performance, "
                "freeze, G3-acceptance or COP claim."
            ) if args.supervised_no_cold_probe else "NORMAL: a cold-side "
                "probe is required (missing = NO_COLD_SIDE_SENSOR refusal)",
            "cold_probe_fitted": not args.supervised_no_cold_probe,
            "hot_side_probe_rom": "28AEBF2200000006",
            "hot_side_role": "T2",
            "actuator_route": ("H8_DUAL_ENABLE: R_EN=GPIO6 L_EN=GPIO10 "
                               "RPWM=GPIO5 1000Hz 13bit LPWM=GND"),
            "evidence_note": args.evidence_note,
        },
        "interlock_statement": (
            "NOT FITTED - owner design decision 2026-11-13: the as-built "
            "hardware has no separate interlock; protection = supervised "
            "operator session + branch fuse + member software chain. This "
            "build records the decision; it never reports a physical loop."
        ) if args.interlock_mode == "none" else (
            "PIN mode: a real U6 normally-closed loop is installed and wired "
            "to the configured GPIO; the adapter reads it live."
        ),
        "inert_by_design": {
            "interlock_unconfigured": (args.interlock_mode == "pin"
                                       and args.interlock_gpio < 1),
            "duty_zero_blocks_start": args.duty_permille == 0,
            "note": "a pin-mode image acts ONLY with a real interlock loop AND "
                    "a non-zero duty AND Member A's admission chain passing; a "
                    "none-mode image records the owner's no-interlock decision "
                    "and acts only under the supervised session with these "
                    "same software gates",
        },
        "files": {},
    }
    for path in sorted(staging.rglob("*")):
        if path.is_file():
            manifest["files"][str(path.relative_to(staging))] = sha256(path)
    (out / "manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"staged {len(manifest['files'])} files; diff + manifest written")

    # 4. Optional build through the documented ESP-IDF environment.
    if args.build:
        script = out / "build.ps1"
        script.write_text(
            "Remove-Item Env:MSYSTEM -ErrorAction SilentlyContinue\n"
            "$env:PYTHONUTF8 = '1'\n"
            # The supervised-fitted-trim seam (Leader ingress hook):
            # project_include.cmake only adds CG_BME280_TRIM_LAYOUT_CONFIRMED=1
            # when this exact env knob is "1"; without it the member producer
            # fail-closed-discards every ambient reading (TRIM_UNCONFIRMED).
            # The trim decode verification evidence: 2026-11-12 bundle.
            "$env:COLDGUARD_BME280_TRIM_CONFIRM = '1'\n"
            f". '{IDF_PROFILE}'\n"
            f"Set-Location {staging}\n"
            f"idf.py -B {out / 'build'} build 2>&1 | "
            f"Tee-Object -FilePath {out / 'build.log'} | Select-Object -Last 8\n"
            "Write-Output (\"BUILD_EXIT=\" + $LASTEXITCODE)\n",
            encoding="utf-8")
        print("building (this takes minutes)...")
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-File", str(script)],
            capture_output=True, text=True, timeout=1800)
        (out / "build-log.txt").write_text(
            (result.stdout or "") + (result.stderr or ""), encoding="utf-8")
        binary = out / "build" / "coldguard_firmware.bin"
        if binary.exists():
            digest = sha256(binary)
            manifest["build"] = {
                "binary": str(binary),
                "sha256": digest,
                "size_bytes": binary.stat().st_size,
            }
            (out / "manifest.json").write_text(
                json.dumps(manifest, indent=2), encoding="utf-8")
            print(f"BUILD OK sha256={digest}")
        else:
            print("BUILD FAILED - see build-log.txt")
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
