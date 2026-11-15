"""Compile and run the Leader TEC hardware adapter harness on the host.

Links the REAL member control core (``cg_tec_control.c`` + ``cg_tec_limits.c``),
the REAL member stub (``cg_tec_hw.c``), the REAL member safe-state module
(``cg_actuator.c``) and the Leader adapter (``cg_leader_tec_hw.c``) against a
recording host mock of the GPIO/LEDC drivers, and asserts the fail-closed
contract end to end for these build shapes:

* shipped default: the interposed accessor answers as the delivered stub;
* adapter active but unsigned gates / no U6: still refused, force-off;
* commissioning-shaped signed configuration: full authorized run lifecycle
  (arm -> start -> bounded cooling -> cooldown -> OFF, estop, clear, fault
  paths) with the IBT-2 R_EN/PWM writes asserted;
* the named SUPERVISED_NO_COLD_PROBE profile: only the cold-presence check
  is omitted, with the real T2 hot input and every other guard in force.

The ops-boundary interposition is expressed with the same
``__wrap_cg_tec_hw_ops`` / ``__real_cg_tec_hw_ops`` symbols the target build
uses with GNU ``--wrap``: per-TU ``-Dcg_tec_hw_ops=...`` renames give the
identical semantics on MSVC.

Requires a host C compiler; skips otherwise. Member sources are never edited:
the signed-gate variant compiles a runtime COPY of cg_actuator.c against a
runtime COPY of coldguard_config.h in a temporary directory with exactly three
documented define flips (the same auditable staging mechanism owner-approved
for the door builds).
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

TESTS = pathlib.Path(__file__).resolve().parent
TOOLS = TESTS.parent
FIRMWARE = TOOLS.parent
MAIN = FIRMWARE / "main"
ADAPTER = FIRMWARE / "components" / "cg_leader_tec_hw"
HARNESS_DIR = TESTS / "harness-leader-tec"
MOCKS = HARNESS_DIR / "mocks"

sys.path.insert(0, str(TESTS))
from test_cg_tec_state_machine import find_gcc, find_vcvars  # noqa: E402

# Member defines flipped ONLY in the temporary signed-gate variant copy.
SIGNED_FLIPS = (
    ("#define CG_ACTUATOR_ENABLE_ALLOWED 0", "#define CG_ACTUATOR_ENABLE_ALLOWED 1"),
    ("#define CG_TEC_OUTPUT_STAGE_ENABLED 0", "#define CG_TEC_OUTPUT_STAGE_ENABLED 1"),
    ("#define CG_TEC_HARDWARE_GATES_VERIFIED 0", "#define CG_TEC_HARDWARE_GATES_VERIFIED 1"),
)

VARIANTS = (
    ("default", ["CGH_VARIANT_DEFAULT"], {}),
    ("active-unsigned", ["CGH_VARIANT_ACTIVE_UNSIGNED"],
     {"CONFIG_CG_LEADER_TEC_HW": "1"}),
    ("active-signed", ["CGH_VARIANT_ACTIVE_SIGNED"],
     {"CONFIG_CG_LEADER_TEC_HW": "1",
      "CONFIG_CG_LEADER_TEC_HW_INTERLOCK_PIN": "33",
      "CONFIG_CG_LEADER_TEC_HW_ACTIVE_LOW": "1",
      "CONFIG_CG_LEADER_TEC_HW_FAN_CONTINUOUS": "1"}),
    # The owner's as-built decision: NO physical interlock exists or will be
    # added; the none-by-design mode is an explicitly configured, recorded
    # commissioning decision (never a silent spoof).
    ("active-signed-noilock", ["CGH_VARIANT_ACTIVE_SIGNED_NOILOCK"],
     {"CONFIG_CG_LEADER_TEC_HW": "1",
      "CONFIG_CG_LEADER_TEC_HW_INTERLOCK_PIN": "-1",
      "CONFIG_CG_LEADER_TEC_HW_INTERLOCK_NONE_BY_DESIGN": "1",
      "CONFIG_CG_LEADER_TEC_HW_FAN_CONTINUOUS": "1"}),
    # The named attended characterization profile: no cold probe exists, so
    # ONLY that presence check is omitted; the supervised table and every
    # other guard stay linked and in force.
    ("active-signed-nocold", ["CGH_VARIANT_ACTIVE_SIGNED_NOCOLD"],
     {"CONFIG_CG_LEADER_TEC_HW": "1",
      "CONFIG_CG_LEADER_TEC_HW_INTERLOCK_PIN": "-1",
      "CONFIG_CG_LEADER_TEC_HW_INTERLOCK_NONE_BY_DESIGN": "1",
      "CONFIG_CG_LEADER_TEC_HW_FAN_CONTINUOUS": "1",
      "CONFIG_CG_LEADER_TEC_HW_SUPERVISED_LIMITS": "1",
      "CONFIG_CG_LEADER_TEC_HW_SUPERVISED_NO_COLD_PROBE": "1"}),
    # The explicit TEC1000 full-duty demo: same guards, 1000 permille and the
    # 10.0 A supervisory stop; 8191/8192 PWM saturation.
    ("active-signed-nocold-1000", ["CGH_VARIANT_ACTIVE_SIGNED_NOCOLD_1000"],
     {"CONFIG_CG_LEADER_TEC_HW": "1",
      "CONFIG_CG_LEADER_TEC_HW_INTERLOCK_PIN": "-1",
      "CONFIG_CG_LEADER_TEC_HW_INTERLOCK_NONE_BY_DESIGN": "1",
      "CONFIG_CG_LEADER_TEC_HW_FAN_CONTINUOUS": "1",
      "CONFIG_CG_LEADER_TEC_HW_SUPERVISED_LIMITS": "1",
      "CONFIG_CG_LEADER_TEC_HW_SUPERVISED_NO_COLD_PROBE": "1",
      "CONFIG_CG_LEADER_TEC_HW_SUPERVISED_FULL_DUTY_DEMO": "1"}),
    # Negative: the no-cold flag is present but the three signed member gates
    # are not. The public profile must keep the cold probe required and
    # refuse every start.
    ("active-unsigned-nocold", ["CGH_VARIANT_ACTIVE_UNSIGNED_NOCOLD"],
     {"CONFIG_CG_LEADER_TEC_HW": "1",
      "CONFIG_CG_LEADER_TEC_HW_INTERLOCK_PIN": "-1",
      "CONFIG_CG_LEADER_TEC_HW_INTERLOCK_NONE_BY_DESIGN": "1",
      "CONFIG_CG_LEADER_TEC_HW_FAN_CONTINUOUS": "1",
      "CONFIG_CG_LEADER_TEC_HW_SUPERVISED_LIMITS": "1",
      "CONFIG_CG_LEADER_TEC_HW_SUPERVISED_NO_COLD_PROBE": "1"}),
)


def make_variant_dir(workdir: pathlib.Path, tag: str, duty: int | None = None) -> pathlib.Path:
    """Runtime staging copy: variant coldguard_config.h + member cg_actuator.c.

    Only the signed-gate commissioning variant flips the three member defines;
    every other variant compiles the baseline configuration verbatim. This is
    the same auditable staging mechanism owner-approved for the door builds:
    the delivered member files are never edited.
    """
    cfg = workdir / "coldguard_config.h"
    src_config = (MAIN / "coldguard_config.h").read_text(encoding="utf-8")
    flipped = src_config
    for old, new in SIGNED_FLIPS:
        count = src_config.count(old)
        if count != 1:
            raise AssertionError(f"member config flip not unique ({count}x): {old}")
    if tag.startswith("active-signed"):
        for old, new in SIGNED_FLIPS:
            flipped = flipped.replace(old, new)
    if duty is not None or tag in ("active-signed-nocold", "active-unsigned-nocold",
                                   "active-signed-nocold-1000"):
        old = "#define CG_TEC_REQUEST_DUTY_PERMILLE 0"
        selected = duty if duty is not None else (
            1000 if tag.endswith("-1000") else 200)
        if flipped.count(old) != 1:
            raise AssertionError("request-duty define not unique for profile variant")
        flipped = flipped.replace(old, f"#define CG_TEC_REQUEST_DUTY_PERMILLE {selected}")
    cfg.write_text(flipped, encoding="utf-8")
    shutil.copyfile(MAIN / "cg_actuator.c", workdir / "cg_actuator.c")
    return workdir


def build_variant_msvc(vcvars: pathlib.Path, tag: str, workdir: pathlib.Path,
                       cfgdir: pathlib.Path,
                       variant_labels: list[str], preproc: dict[str, str]) -> pathlib.Path:
    exe = workdir / f"cg_leader_tec_{tag}.exe"
    bat = workdir / f"build_{tag}.bat"
    log = workdir / f"build_{tag}.log"

    tus = [
        (MAIN / "cg_tec_hw.c", "stub.obj", {"cg_tec_hw_ops": "__real_cg_tec_hw_ops"}),
        (ADAPTER / "cg_leader_tec_hw.c", "adapter.obj", {}),
        (cfgdir / "cg_actuator.c", "actuator.obj", {}),
        (MAIN / "cg_tec_control.c", "control.obj",
         {"cg_tec_control_init": "__real_cg_tec_control_init"}),
        (MAIN / "cg_tec_limits.c", "limits.obj", {}),
        (HARNESS_DIR / "hw_host.c", "host.obj", {}),
        (HARNESS_DIR / "cg_leader_tec_host_harness.c", "main.obj",
         {"cg_tec_hw_ops": "__wrap_cg_tec_hw_ops",
          "cg_tec_control_init": "__wrap_cg_tec_control_init"}),
    ]
    lines = [
        "@echo off",
        f'call "{vcvars}" >nul',
        f'cd /d "{workdir}"',
    ]
    jobs: list[str] = []
    for idx, (src, obj, renames) in enumerate(tus):
        flags = ["/nologo", "/std:c11", "/W4", "/WX"]
        flags += [f"/I\"{cfgdir}\"", f"/I\"{MOCKS}\"", f"/I\"{MAIN}\"", f"/I\"{ADAPTER}\""]
        flags += [f"/D{lblr}" for lblr in variant_labels]
        flags += [f"/D{k}={v}" for k, v in preproc.items()]
        flags += [f"/D{k}={v}" for k, v in renames.items()]
        lines.append("cl " + " ".join(flags)
                     + f' /c "{src}" /Fo"{obj}" >> "{log}" 2>&1 || exit /b %ERRORLEVEL%')
        jobs.append(obj)
    lines.append("link /nologo /OUT:\"" + str(exe) + "\" " + " ".join(jobs)
                 + f' >> "{log}" 2>&1 || exit /b %ERRORLEVEL%')
    lines.append("exit /b 0")
    bat.write_text("\r\n".join(lines) + "\r\n", encoding="ascii", newline="")
    result = subprocess.run(["cmd", "/c", str(bat)], capture_output=True, text=True, timeout=300)
    if result.returncode != 0 or not exe.exists():
        output = log.read_text(encoding="utf-8", errors="replace") if log.exists() \
            else result.stdout + result.stderr
        raise AssertionError(f"MSVC build failed for {tag} (exit {result.returncode}):\n{output}")
    return exe


def build_variant_gcc(cc: str, tag: str, workdir: pathlib.Path, cfgdir: pathlib.Path,
                      variant_labels: list[str], preproc: dict[str, str]) -> pathlib.Path:
    exe = workdir / f"cg_leader_tec_{tag}"
    tus = [
        (MAIN / "cg_tec_hw.c", "stub.o", {"cg_tec_hw_ops": "__real_cg_tec_hw_ops"}),
        (ADAPTER / "cg_leader_tec_hw.c", "adapter.o", {}),
        (cfgdir / "cg_actuator.c", "actuator.o", {}),
        (MAIN / "cg_tec_control.c", "control.o",
         {"cg_tec_control_init": "__real_cg_tec_control_init"}),
        (MAIN / "cg_tec_limits.c", "limits.o", {}),
        (HARNESS_DIR / "hw_host.c", "host.o", {}),
        (HARNESS_DIR / "cg_leader_tec_host_harness.c", "main.o",
         {"cg_tec_hw_ops": "__wrap_cg_tec_hw_ops",
          "cg_tec_control_init": "__wrap_cg_tec_control_init"}),
    ]
    objs = []
    log: list[str] = []
    for src, obj, renames in tus:
        cmd = [cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
               "-I", str(cfgdir), "-I", str(MOCKS), "-I", str(MAIN), "-I", str(ADAPTER),
               *[f"-D{lblr}" for lblr in variant_labels]]
        cmd += [f"-D{k}={v}" for k, v in preproc.items()]
        cmd += [f"-D{k}={v}" for k, v in renames.items()]
        cmd += ["-c", str(src), "-o", str(workdir / obj)]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        log.append(result.stdout + result.stderr)
        if result.returncode != 0:
            raise AssertionError(f"gcc failed for {src.name} in {tag}:\n" + "\n".join(log[-1:]))
        objs.append(str(workdir / obj))
    link = [cc, *objs, "-o", str(exe)]
    result = subprocess.run(link, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise AssertionError(f"gcc link failed for {tag}: {result.stdout}{result.stderr}")
    return exe


class LeaderTecAdapterHarnessTests(unittest.TestCase):
    def test_three_variants(self) -> None:
        with tempfile.TemporaryDirectory(prefix="cg-leader-tec-harness-") as tmp:
            workdir = pathlib.Path(tmp)
            vcvars = find_vcvars()
            cc = None if vcvars else find_gcc()
            if vcvars is None and cc is None:
                self.skipTest("no host C compiler (MSVC or cc/gcc) found")
            min_checks = {"default": 12, "active-unsigned": 9, "active-signed": 34,
                          "active-signed-noilock": 18, "active-signed-nocold": 9,
                          "active-signed-nocold-1000": 9,
                          "active-unsigned-nocold": 6}
            for tag, labels, preproc in VARIANTS:
                cfgdir = workdir / tag
                cfgdir.mkdir(parents=True, exist_ok=True)
                make_variant_dir(cfgdir, tag)
                if vcvars is not None:
                    exe = build_variant_msvc(vcvars, tag, workdir, cfgdir, labels, preproc)
                    compiler = "MSVC"
                else:
                    exe = build_variant_gcc(cc, tag, workdir, cfgdir, labels, preproc)
                    compiler = cc
                run = subprocess.run([str(exe)], capture_output=True, text=True, timeout=120)
                output = run.stdout + run.stderr
                self.assertEqual(run.returncode, 0,
                                 f"harness failed [{tag}] ({compiler}):\n{output}")
                self.assertNotIn("FAIL [", output, output)
                got = re.search(r"ALL (\d+) CHECKS PASS", output)
                self.assertIsNotNone(got, output)
                self.assertGreaterEqual(int(got.group(1)), min_checks[tag],
                                        f"too few checks in {tag}: {output}")
                print(f"leader-tec-adapter[{tag}]: {got.group(1)} checks pass ({compiler})")

    def test_supervised_duty_outside_the_two_profiles_fails_the_build(self) -> None:
        """250/600/0 cannot silently select an envelope: the adapter's
        compile-time guard refuses any duty other than 200 or 1000."""
        with tempfile.TemporaryDirectory(prefix="cg-leader-tec-badduty-") as tmp:
            workdir = pathlib.Path(tmp)
            cfgdir = workdir / "bad"
            cfgdir.mkdir()
            make_variant_dir(cfgdir, "active-signed-nocold", duty=250)
            labels, preproc = next((labels, preproc) for tag, labels, preproc in VARIANTS
                                   if tag == "active-signed-nocold")
            vcvars = find_vcvars()
            with self.assertRaises(AssertionError) as failure:
                if vcvars is not None:
                    build_variant_msvc(vcvars, "badduty", workdir, cfgdir, labels, preproc)
                else:
                    cc = find_gcc()
                    if cc is None:
                        self.skipTest("no host C compiler (MSVC or cc/gcc) found")
                    build_variant_gcc(cc, "badduty", workdir, cfgdir, labels, preproc)
            self.assertIn("200 or 1000", str(failure.exception))


if __name__ == "__main__":
    unittest.main()
