r"""Launch the ColdGuard Member A hardware acceptance application.

    py -3 tools\member_a_app\app.py
    py -3 tools\member_a_app\app.py --check
    py -3 tools\member_a_app\app.py --compat [--port COM4]
    py -3 tools\member_a_app\app.py --capture-h8 --port COM4 --seconds 30
    py -3 tools\member_a_app\app.py --import-evidence --session <dir>
    py -3 tools\member_a_app\app.py --readiness [--port COM4] [--session <dir>]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import os
import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from member_a_app.requirements import DEFINITIONS, validate  # noqa: E402

APP_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _check() -> int:
    errors = validate()
    print(f"definitions={len(DEFINITIONS)} errors={len(errors)}")
    for error in errors:
        print(error)
    return 1 if errors else 0


def _compat(port: str | None) -> int:
    from member_a_app import compat
    from member_a_app.device import DeviceLink, list_ports

    print("\n".join(compat.static_matrix()))
    print()
    ports = list_ports()
    if not port:
        print("LIVE: NOT RUN (no --port; no COM device was opened)")
        if ports:
            print("Available ports: " + ", ".join(item.device for item in ports))
        return 0
    link = DeviceLink(None)
    try:
        link.open(port)
        deadline = time.monotonic() + 4.0
        while time.monotonic() < deadline and link.latest_frame() is None:
            time.sleep(0.1)
        result = compat.classify(link.snapshot)
        print(compat.markdown(result))
        return 0 if result.telemetry else 1
    except Exception as exc:
        print(f"LIVE: NOT RUN ({exc})")
        return 2
    finally:
        link.close()


def _latest_acceptance_session() -> pathlib.Path:
    import json
    candidates: list[pathlib.Path] = []
    for folder in ("h8-captures", "app-sessions"):
        base = APP_ROOT / "evidence" / "A" / folder
        if base.is_dir():
            candidates.extend(path for path in base.glob("*/session.json")
                              if path.is_file())
    if not candidates:
        raise FileNotFoundError("no acceptance session found")
    def result_count(path: pathlib.Path) -> int:
        try:
            return len(json.loads(path.read_text(encoding="utf-8")).get("results", {}))
        except (OSError, ValueError):
            return 0
    return max(candidates, key=lambda path: (result_count(path), path.stat().st_mtime)).parent


def _readiness(port: str | None, session: str | None, out: str | None,
               probe_commands: bool) -> int:
    from member_a_app import readiness
    from member_a_app.device import DeviceLink
    from member_a_app.evidence import SessionStore

    root = pathlib.Path(session) if session else _latest_acceptance_session()
    store = SessionStore(root, create=False)
    link = None
    snapshot = readiness.CapabilitySnapshot()
    try:
        if port:
            link = DeviceLink(None)
            try:
                link.open(port)
                snapshot = readiness.build_snapshot(link, probe_commands=probe_commands)
            except Exception as exc:
                print(f"READINESS: live probe unavailable ({exc})")
            finally:
                if link is not None:
                    link.close()
        rows = readiness.evaluate(DEFINITIONS, store.results(), snapshot)
        print(readiness.markdown(rows))
        target = pathlib.Path(out) if out else root
        paths = readiness.write_report(DEFINITIONS, store.results(), snapshot, target)
        print(f"readiness report: {paths['markdown']}")
        print("summary: " + " ".join(
            f"{state}={count}" for state, count in readiness.summarize(rows).items()))
        return 0
    finally:
        store.close()


def _capture_h8(port: str | None, seconds: float, out_dir: str | None) -> int:
    from member_a_app.device import DeviceLink, list_ports
    from member_a_app.evidence import SessionStore
    from member_a_app.h8_bench import H8Bench, SilentOperator

    if not port:
        print("NOT RUN: no --port; available ports: "
              + (", ".join(item.device for item in list_ports()) or "none"))
        return 2
    root = pathlib.Path(out_dir) if out_dir else (
        APP_ROOT / "evidence" / "A" / "h8-captures"
        / f"capture-{_dt.datetime.now(_dt.timezone.utc):%Y%m%dT%H%M%SZ}")
    store = SessionStore(root, operator="h8-read-only")
    link = DeviceLink(store)
    try:
        link.open(port)
        bench = H8Bench(link, store, SilentOperator())
        payload = bench.read_only(seconds)
        print(f"H8 capture: {payload['outcome']} {payload.get('reason', '')}")
        print(f"session: {root}")
        measurements = payload.get("measurements", {})
        print(f"frames={measurements.get('frames')} state={measurements.get('latest_state')}"
              f" current={measurements.get('latest_current_a')}"
              f" hot_side={measurements.get('latest_hot_side_c')}")
        return 0 if payload["outcome"] == "PASS" else 1
    except Exception as exc:
        print(f"NOT RUN: {exc}")
        return 2
    finally:
        link.close()
        store.close()


def _import_evidence(session: str | None) -> int:
    from member_a_app.evidence import SessionStore
    from member_a_app.evidence_import import import_all

    if not session:
        print("NOT RUN: --session <dir> is required")
        return 2
    store = SessionStore(pathlib.Path(session), create=False)
    try:
        summary = import_all(store)
        print(f"imported={summary['imported']} duplicates={summary['skipped_duplicate']}"
              f" missing_patterns={len(summary['missing'])} errors={len(summary['errors'])}")
        for test_id, count in sorted(summary["by_test"].items()):
            print(f"  {test_id}: {count} file(s)")
        for missing in summary["missing"]:
            print(f"  MISSING {missing['test_id']}: {missing['pattern']}")
        for error in summary["errors"]:
            print(f"  ERROR {error}")
        return 0 if not summary["errors"] else 1
    finally:
        store.close()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate the 114-ID registry")
    parser.add_argument("--smoke", action="store_true", help="launch the GUI and close it")
    parser.add_argument("--compat", action="store_true", help="print the image compatibility matrix")
    parser.add_argument("--capture-h8", action="store_true", help="read-only H8S capture")
    parser.add_argument("--import-evidence", action="store_true", help="import W01-W04 evidence")
    parser.add_argument("--readiness", action="store_true",
                        help="execution-readiness gate for the 114 workflows")
    parser.add_argument("--readiness-out", help="readiness report directory")
    parser.add_argument("--no-command-probe", action="store_true",
                        help="do not send the non-actuating STATUS readiness probe")
    parser.add_argument("--port", help="COM port, e.g. COM4")
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--out", help="capture/session output directory")
    parser.add_argument("--session", help="existing session directory")
    args = parser.parse_args()
    if args.check:
        return _check()
    if args.compat:
        return _compat(args.port)
    if args.capture_h8:
        return _capture_h8(args.port, args.seconds, args.out)
    if args.import_evidence:
        return _import_evidence(args.session)
    if args.readiness:
        return _readiness(args.port, args.session, args.readiness_out,
                          not args.no_command_probe)
    smoke = args.smoke
    if smoke:
        os.environ["CG_ACCEPTANCE_SMOKE"] = "1"
    from member_a_app.gui import main as gui_main
    gui_main(smoke=smoke)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
