r"""Launch the ColdGuard Member A hardware acceptance application.

    py -3 tools\member_a_app\app.py
    py -3 tools\member_a_app\app.py --check
"""

from __future__ import annotations

import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from member_a_app.requirements import DEFINITIONS, validate  # noqa: E402


def main() -> int:
    if "--check" in sys.argv:
        errors = validate()
        print(f"definitions={len(DEFINITIONS)} errors={len(errors)}")
        for error in errors:
            print(error)
        return 1 if errors else 0
    smoke = "--smoke" in sys.argv
    if smoke:
        os.environ["CG_ACCEPTANCE_SMOKE"] = "1"
    from member_a_app.gui import main as gui_main
    gui_main(smoke=smoke)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
