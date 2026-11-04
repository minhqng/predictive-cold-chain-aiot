"""Tkinter desktop application for the Member A hardware acceptance campaign."""

from __future__ import annotations

import csv
import dataclasses
import datetime as _dt
import json
import os
import pathlib
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk
from typing import Any

from . import compat, evidence_import, protocol
from .charts import LiveChart
from .device import DeviceError, DeviceLink, list_ports
from .evidence import APP_VERSION, SessionStore
from .h8_bench import H8Bench
from .model import Outcome, SafetyClass, TestDefinition, TestMode, TestResult, now_iso
from .requirements import DEFINITIONS, by_week, get as get_definition, validate
from .runner import TestRunner

OUTCOME_TAG = {
    Outcome.PASS.value: "pass",
    Outcome.FAIL.value: "fail",
    Outcome.INCOMPLETE.value: "incomplete",
    Outcome.NOT_RUN.value: "notrun",
}


def _add_list(lines: list[str], title: str, items: Any) -> None:
    lines.append(title)
    values = list(items)
    if values:
        lines.extend(f"  - {item}" for item in values)
    else:
        lines.append("  (none)")
    lines.append("")


@dataclasses.dataclass
class OperatorRequest:
    kind: str
    kwargs: dict[str, Any]
    event: threading.Event
    response: Any = None


class GuiOperator:
    def __init__(self, app: "AcceptanceApp"):
        self.app = app
        self.requests: queue.Queue[OperatorRequest] = queue.Queue()
        self._cancel = threading.Event()

    def reset_cancel(self) -> None:
        self._cancel.clear()

    def cancel(self) -> None:
        self._cancel.set()

    def _ask(self, kind: str, **kwargs: Any) -> Any:
        request = OperatorRequest(kind=kind, kwargs=kwargs, event=threading.Event())
        self.requests.put(request)
        while not request.event.wait(0.2):
            if self.app.closing:
                return None
        return request.response

    def info(self, title: str, message: str) -> None:
        self._ask("info", title=title, message=message)

    def confirm(self, title: str, message: str) -> bool:
        return bool(self._ask("confirm", title=title, message=message))

    def choose(self, title: str, message: str, options: list[str]) -> str | None:
        return self._ask("choose", title=title, message=message, options=options)

    def text(self, title: str, message: str, multiline: bool = False) -> str | None:
        return self._ask("text", title=title, message=message, multiline=multiline)

    def number(self, title: str, message: str, unit: str = "",
               minimum: float | None = None, maximum: float | None = None) -> float | None:
        return self._ask("number", title=title, message=message, unit=unit,
                         minimum=minimum, maximum=maximum)

    def file(self, title: str, kinds: list[tuple[str, str]] | None = None) -> str | None:
        return self._ask("file", title=title, kinds=kinds)

    def progress(self, message: str, fraction: float | None = None) -> None:
        self.app.ui_queue.put(("progress", message, fraction))

    def cancelled(self) -> bool:
        return self._cancel.is_set() or self.app.closing


class ChoiceDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, title: str, message: str, options: list[str]):
        super().__init__(parent)
        self.title(title)
        self.result: str | None = None
        self.resizable(False, False)
        ttk.Label(self, text=message, wraplength=560, justify="left").pack(
            padx=16, pady=(14, 8), anchor="w")
        self.choice = tk.StringVar(value=options[0] if options else "")
        for option in options:
            ttk.Radiobutton(self, text=option, value=option, variable=self.choice).pack(
                anchor="w", padx=24, pady=2)
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=16, pady=12)
        ttk.Button(buttons, text="OK", command=self._ok).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=self._cancel).pack(side="right", padx=6)
        self.transient(parent)
        self.grab_set()
        self.wait_window(self)

    def _ok(self) -> None:
        self.result = self.choice.get()
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


class TextDialog(tk.Toplevel):
    def __init__(self, parent: tk.Misc, title: str, message: str, multiline: bool = False):
        super().__init__(parent)
        self.title(title)
        self.result: str | None = None
        ttk.Label(self, text=message, wraplength=600, justify="left").pack(
            padx=16, pady=(14, 8), anchor="w")
        if multiline:
            self.text = tk.Text(self, width=72, height=8)
            self.text.pack(padx=16, fill="both", expand=True)
        else:
            self.entry = ttk.Entry(self, width=72)
            self.entry.pack(padx=16, fill="x")
            self.entry.focus_set()
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=16, pady=12)
        ttk.Button(buttons, text="OK", command=self._ok).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=self._cancel).pack(side="right", padx=6)
        self.transient(parent)
        self.grab_set()
        self.wait_window(self)

    def _ok(self) -> None:
        self.result = (self.text.get("1.0", "end-1c") if hasattr(self, "text")
                       else self.entry.get())
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent: "AcceptanceApp"):
        super().__init__(parent)
        self.title("Campaign settings")
        self.result: dict[str, Any] | None = None
        fields = [
            ("critical_tmax_c", "Frozen critical Tmean boundary (C)", "e.g. 30"),
            ("critical_tmin_c", "Frozen lower critical boundary (C, optional)", ""),
            ("soak_duration_s", "Soak target (seconds)", "7200"),
            ("fuse_a", "Final fuse rating (A)", "15"),
            ("pzem_profile", "PZEM profile", "50A"),
        ]
        self.vars: dict[str, tk.StringVar] = {}
        for row, (key, label, hint) in enumerate(fields):
            ttk.Label(self, text=label).grid(row=row, column=0, sticky="w",
                                             padx=(14, 8), pady=6)
            value = parent.store.config(key, "")
            var = tk.StringVar(value="" if value is None else str(value))
            ttk.Entry(self, textvariable=var, width=24).grid(row=row, column=1, pady=6,
                                                              sticky="w")
            ttk.Label(self, text=hint, foreground="#666").grid(row=row, column=2,
                                                               sticky="w", padx=8)
            self.vars[key] = var
        ttk.Label(self, text="Critical boundaries are research decisions; the app does not invent them.",
                  foreground="#666").grid(row=len(fields), column=0, columnspan=3,
                                          padx=14, pady=(4, 8), sticky="w")
        buttons = ttk.Frame(self)
        buttons.grid(row=len(fields) + 1, column=0, columnspan=3, sticky="e",
                     padx=14, pady=12)
        ttk.Button(buttons, text="Save", command=self._save).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=6)
        self.transient(parent)
        self.grab_set()
        self.wait_window(self)

    def _save(self) -> None:
        result: dict[str, Any] = {}
        for key, var in self.vars.items():
            text = var.get().strip()
            if not text:
                result[key] = None
                continue
            if key in {"critical_tmax_c", "critical_tmin_c", "fuse_a"}:
                try:
                    result[key] = float(text)
                except ValueError:
                    messagebox.showerror("Invalid value", f"{key} must be numeric", parent=self)
                    return
            elif key == "soak_duration_s":
                try:
                    result[key] = int(float(text))
                except ValueError:
                    messagebox.showerror("Invalid value", f"{key} must be an integer", parent=self)
                    return
            else:
                result[key] = text
        self.result = result
        self.destroy()


class AcceptanceApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"ColdGuard — Member A Hardware Acceptance {APP_VERSION}")
        self.geometry("1420x900")
        self.minsize(1100, 720)
        self.repo_root = pathlib.Path(__file__).resolve().parents[2]
        self.closing = False
        self.worker: threading.Thread | None = None
        self.ui_queue: queue.Queue[tuple[Any, ...]] = queue.Queue()
        self.store = self._open_session()
        self.device = DeviceLink(self.store)
        self.operator = GuiOperator(self)
        self.runner = TestRunner(self.store, self.device, self.operator, DEFINITIONS)
        self._frame_cursor = 0
        self._event_cursor = 0
        self._last_frame_time = 0.0
        self._running = False
        self._results_dirty = True
        self._last_identity: tuple[Any, ...] | None = None
        self._last_bench_refresh = 0.0
        self._build_style()
        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll_operator)
        self.after(120, self._poll_ui)
        self.after(150, self._poll_device)
        self._refresh_ports()
        self._refresh_tree()
        self._refresh_evidence()
        self._update_connection_label()

    # ------------------------------------------------------------------
    # Session lifecycle
    # ------------------------------------------------------------------
    def _open_session(self) -> SessionStore:
        if os.environ.get("CG_ACCEPTANCE_SMOKE") == "1":
            import tempfile
            root = pathlib.Path(tempfile.mkdtemp(prefix="cg-acceptance-smoke-"))
            return SessionStore(root, operator="smoke")
        base = self.repo_root / "evidence" / "A" / "app-sessions"
        base.mkdir(parents=True, exist_ok=True)
        existing = sorted(
            [path for path in base.iterdir() if (path / "session.json").is_file()],
            key=lambda path: path.stat().st_mtime, reverse=True)
        if existing:
            answer = messagebox.askyesnocancel(
                "ColdGuard acceptance",
                f"Resume the most recent session?\n\n{existing[0].name}\n\n"
                "Yes = resume, No = new session, Cancel = choose a session folder.")
            if answer is True:
                return SessionStore(existing[0])
            if answer is None:
                chosen = filedialog.askdirectory(title="Choose a session folder",
                                                 initialdir=str(base))
                if chosen:
                    return SessionStore(pathlib.Path(chosen))
        operator = simpledialog.askstring(
            "Operator", "Operator name for this acceptance session:",
            initialvalue=os.environ.get("USERNAME", "operator"))
        if operator is None:
            operator = os.environ.get("USERNAME", "operator")
        root = base / f"session-{_dt.datetime.now(_dt.timezone.utc):%Y%m%dT%H%M%SZ}"
        return SessionStore(root, operator=operator)

    def _switch_session(self, store: SessionStore) -> None:
        if self._running:
            messagebox.showwarning("Test running", "Stop the current test before switching sessions.")
            return
        if self.device.snapshot.connected:
            if not messagebox.askyesno(
                    "Disconnect required",
                    "Switching sessions closes the serial port. Closing the USB-Serial/JTAG port "
                    "may reset the board. Continue?"):
                return
            self.device.close()
        self.store.close()
        self.store = store
        self.device = DeviceLink(self.store)
        self.runner = TestRunner(self.store, self.device, self.operator, DEFINITIONS)
        self._frame_cursor = 0
        self._event_cursor = 0
        self._last_identity = None
        self._refresh_tree()
        self._refresh_evidence()
        self._update_connection_label()
        self._update_session_label()

    def _new_session(self) -> None:
        operator = simpledialog.askstring("New session", "Operator name:",
                                          initialvalue=os.environ.get("USERNAME", "operator"))
        if operator is None:
            return
        root = (self.repo_root / "evidence" / "A" / "app-sessions"
                / f"session-{_dt.datetime.now(_dt.timezone.utc):%Y%m%dT%H%M%SZ}")
        self._switch_session(SessionStore(root, operator=operator))

    def _open_session_dialog(self) -> None:
        chosen = filedialog.askdirectory(
            title="Open an existing acceptance session",
            initialdir=str(self.repo_root / "evidence" / "A" / "app-sessions"))
        if not chosen:
            return
        try:
            self._switch_session(SessionStore(pathlib.Path(chosen), create=False))
        except Exception as exc:
            messagebox.showerror("Session", str(exc))

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------
    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("Treeview", rowheight=22)
        style.configure("Pass.TLabel", foreground="#1a7f37")
        style.configure("Fail.TLabel", foreground="#b42318")
        style.configure("Incomplete.TLabel", foreground="#9a6700")

    def _build_ui(self) -> None:
        self._build_menu()
        toolbar = ttk.Frame(self, padding=(8, 6))
        toolbar.pack(side="top", fill="x")
        ttk.Label(toolbar, text="Port").pack(side="left")
        self.port_var = tk.StringVar()
        self.port_box = ttk.Combobox(toolbar, textvariable=self.port_var, width=46,
                                     state="readonly")
        self.port_box.pack(side="left", padx=6)
        ttk.Button(toolbar, text="Refresh", command=self._refresh_ports).pack(side="left")
        self.connect_button = ttk.Button(toolbar, text="Connect", command=self._connect)
        self.connect_button.pack(side="left", padx=6)
        self.disconnect_button = ttk.Button(toolbar, text="Disconnect",
                                            command=self._disconnect, state="disabled")
        self.disconnect_button.pack(side="left")
        ttk.Button(toolbar, text="Status", command=self._send_status).pack(side="left", padx=6)
        self.connection_label = ttk.Label(toolbar, text="disconnected")
        self.connection_label.pack(side="left", padx=12)
        self.session_label = ttk.Label(toolbar, text="")
        self.session_label.pack(side="right")
        self._update_session_label()

        paned = ttk.PanedWindow(self, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=(0, 4))
        left = ttk.Frame(paned, width=620)
        paned.add(left, weight=3)
        right = ttk.Frame(paned)
        paned.add(right, weight=4)

        filter_bar = ttk.Frame(left)
        filter_bar.pack(fill="x", pady=(0, 4))
        ttk.Label(filter_bar, text="Search").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_args: self._refresh_tree())
        ttk.Entry(filter_bar, textvariable=self.search_var, width=18).pack(side="left", padx=4)
        ttk.Label(filter_bar, text="Outcome").pack(side="left", padx=(8, 0))
        self.filter_var = tk.StringVar(value="ALL")
        filter_box = ttk.Combobox(filter_bar, textvariable=self.filter_var, width=12,
                                  state="readonly",
                                  values=["ALL"] + [item.value for item in Outcome])
        filter_box.pack(side="left", padx=4)
        filter_box.bind("<<ComboboxSelected>>", lambda _event: self._refresh_tree())

        columns = ("id", "title", "mode", "safety", "outcome", "reason")
        self.tree = ttk.Treeview(left, columns=columns, show="tree headings",
                                 selectmode="extended")
        headings = {"id": "ID", "title": "Requirement", "mode": "Mode",
                    "safety": "Safety", "outcome": "Outcome", "reason": "Reason"}
        for key, heading in headings.items():
            self.tree.heading(key, text=heading)
        self.tree.column("#0", width=66, stretch=False)
        self.tree.column("id", width=82, stretch=False)
        self.tree.column("title", width=220, stretch=True)
        self.tree.column("mode", width=92, stretch=False)
        self.tree.column("safety", width=90, stretch=False)
        self.tree.column("outcome", width=88, stretch=False)
        self.tree.column("reason", width=150, stretch=True)
        self.tree.tag_configure("pass", background="#e6f4ea")
        self.tree.tag_configure("fail", background="#fde8e8")
        self.tree.tag_configure("incomplete", background="#fff4d6")
        self.tree.tag_configure("notrun", background="#f4f4f4")
        self.tree.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.tree.yview)
        scroll.pack(side="right", fill="y")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._show_selected())

        buttons = ttk.Frame(left)
        buttons.pack(fill="x", pady=4)
        self.run_selected_button = ttk.Button(buttons, text="Run selected",
                                              command=self._run_selected)
        self.run_selected_button.pack(side="left")
        self.run_week_button = ttk.Button(buttons, text="Run week",
                                          command=self._run_week)
        self.run_week_button.pack(side="left", padx=4)
        self.run_all_button = ttk.Button(buttons, text="Run all eligible",
                                         command=self._run_all)
        self.run_all_button.pack(side="left")
        self.stop_button = ttk.Button(buttons, text="Stop test", command=self._stop_test,
                                      state="disabled")
        self.stop_button.pack(side="right")

        notebook = ttk.Notebook(right)
        notebook.pack(fill="both", expand=True)
        self._build_dashboard(notebook)
        self._build_detail(notebook)
        self._build_bench(notebook)
        self._build_console(notebook)
        self._build_evidence(notebook)

        status = ttk.Frame(self, padding=(8, 4))
        status.pack(side="bottom", fill="x")
        self.progress = ttk.Progressbar(status, mode="determinate", maximum=1.0, length=220)
        self.progress.pack(side="left")
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(status, textvariable=self.status_var).pack(side="left", padx=10)
        self.rx_label = ttk.Label(status, text="RX 0 | TX 0")
        self.rx_label.pack(side="right")

    def _build_menu(self) -> None:
        menu = tk.Menu(self)
        session = tk.Menu(menu, tearoff=False)
        session.add_command(label="New session", command=self._new_session)
        session.add_command(label="Open session folder…", command=self._open_session_dialog)
        session.add_separator()
        session.add_command(label="Export 114-ID report", command=self._export_report)
        session.add_command(label="Verify evidence hashes", command=self._verify_evidence)
        session.add_separator()
        session.add_command(label="Exit", command=self._on_close)
        menu.add_cascade(label="Session", menu=session)
        tools = tk.Menu(menu, tearoff=False)
        tools.add_command(label="Campaign settings…", command=self._open_settings)
        tools.add_command(label="Import existing W01-W04 evidence",
                          command=self._import_existing_evidence)
        tools.add_command(label="Create BOM audit template", command=self._create_bom_template)
        tools.add_command(label="Open session folder", command=self._open_session_folder)
        menu.add_cascade(label="Tools", menu=tools)
        help_menu = tk.Menu(menu, tearoff=False)
        help_menu.add_command(label="About and limitations", command=self._about)
        menu.add_cascade(label="Help", menu=help_menu)
        self.config(menu=menu)

    def _build_dashboard(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Dashboard")
        self.identity_vars: dict[str, tk.StringVar] = {}
        identity = ttk.LabelFrame(tab, text="Device identity", padding=6)
        identity.pack(fill="x", padx=6, pady=(6, 2))
        fields = ["device_id", "boot_id", "firmware", "hardware_config", "pin_map",
                  "calibration", "firmware_kind", "port", "h8_mode", "h8_stage",
                  "h8_supervised", "h8_ack"]
        for index, field in enumerate(fields):
            ttk.Label(identity, text=field + ":").grid(row=index // 4, column=(index % 4) * 2,
                                                       sticky="w", padx=(0, 3), pady=1)
            var = tk.StringVar(value="—")
            self.identity_vars[field] = var
            ttk.Label(identity, textvariable=var, width=24).grid(
                row=index // 4, column=(index % 4) * 2 + 1, sticky="w", padx=(0, 12), pady=1)

        values = ttk.LabelFrame(tab, text="Live channels", padding=6)
        values.pack(fill="x", padx=6, pady=2)
        self.value_vars: dict[str, tk.StringVar] = {}
        channel_fields = [
            ("T1", "T1"), ("T2", "T2 (hot side)"), ("T3", "T3"), ("SPARE", "SPARE / near door"),
            ("chamber", "Chamber air"), ("hot_side", "Hot side"), ("ambient", "Ambient"),
            ("humidity", "RH"), ("door", "Door"), ("door_polarity", "Door polarity"),
            ("voltage", "Voltage"), ("current", "Current"),
            ("power", "Power"), ("energy", "Energy"), ("state", "TEC state"),
            ("quality", "Quality"), ("applied", "Applied"), ("pwm", "PWM"),
            ("fault", "Fault"),
        ]
        for index, (key, label) in enumerate(channel_fields):
            ttk.Label(values, text=label + ":").grid(row=index // 5, column=(index % 5) * 2,
                                                      sticky="w", padx=(0, 3), pady=1)
            var = tk.StringVar(value="—")
            self.value_vars[key] = var
            ttk.Label(values, textvariable=var, width=17, font=("Consolas", 10)).grid(
                row=index // 5, column=(index % 5) * 2 + 1, sticky="w", padx=(0, 10), pady=1)

        self.banner_var = tk.StringVar(value="")
        self.banner = ttk.Label(tab, textvariable=self.banner_var, foreground="#9a6700",
                                padding=(8, 2))
        self.banner.pack(fill="x", padx=6)

        self.chart = LiveChart(tab)
        self.chart.pack(fill="both", expand=True, padx=6, pady=4)

        controls = ttk.LabelFrame(tab, text="Supervised actuation (manual)", padding=6)
        controls.pack(fill="x", padx=6, pady=(2, 6))
        ttk.Label(controls, text="ARM token").pack(side="left")
        self.token_var = tk.StringVar()
        ttk.Entry(controls, textvariable=self.token_var, width=12).pack(side="left", padx=4)
        ttk.Button(controls, text="ARM", command=self._send_arm).pack(side="left")
        ttk.Label(controls, text="seconds").pack(side="left", padx=(12, 2))
        self.seconds_var = tk.StringVar(value="10")
        ttk.Spinbox(controls, from_=1, to=600, textvariable=self.seconds_var,
                    width=6).pack(side="left")
        self.start_button = ttk.Button(controls, text="START", command=self._send_start)
        self.start_button.pack(side="left", padx=6)
        ttk.Button(controls, text="STOP", command=self._send_stop).pack(side="left")
        ttk.Button(controls, text="ESTOP", command=self._send_estop).pack(side="left", padx=6)
        ttk.Button(controls, text="Warm reset (USB-JTAG)",
                   command=self._warm_reset).pack(side="right")

    def _build_detail(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Test detail")
        self.detail_text = scrolledtext.ScrolledText(tab, wrap="word", state="disabled",
                                                     font=("Consolas", 10))
        self.detail_text.pack(fill="both", expand=True, padx=6, pady=6)
        bar = ttk.Frame(tab)
        bar.pack(fill="x", padx=6, pady=(0, 6))
        ttk.Button(bar, text="Run this test", command=self._run_selected).pack(side="left")

    def _build_bench(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Bench readiness")
        bar = ttk.Frame(tab)
        bar.pack(fill="x", padx=6, pady=6)
        self.h8_read_only_button = ttk.Button(
            bar, text="Read-only H8 capture 60 s", command=self._start_h8_read_only)
        self.h8_read_only_button.pack(side="left")
        self.h8_stage_f_button = ttk.Button(
            bar, text="Supervised Stage F check (30 s, 20 %)",
            command=self._start_h8_stage_f)
        self.h8_stage_f_button.pack(side="left", padx=6)
        ttk.Button(bar, text="Import W01-W04 evidence",
                   command=self._import_existing_evidence).pack(side="left", padx=6)
        ttk.Button(bar, text="Open bench results",
                   command=self._open_bench_folder).pack(side="left")
        split = ttk.PanedWindow(tab, orient="vertical")
        split.pack(fill="both", expand=True, padx=6, pady=(0, 6))
        compat_frame = ttk.LabelFrame(split, text="Detected image compatibility")
        split.add(compat_frame, weight=1)
        self.bench_compat_text = scrolledtext.ScrolledText(
            compat_frame, wrap="word", state="disabled", font=("Consolas", 10), height=12)
        self.bench_compat_text.pack(fill="both", expand=True, padx=4, pady=4)
        result_frame = ttk.LabelFrame(split, text="Bench results")
        split.add(result_frame, weight=1)
        self.bench_result_text = scrolledtext.ScrolledText(
            result_frame, wrap="word", state="disabled", font=("Consolas", 10))
        self.bench_result_text.pack(fill="both", expand=True, padx=4, pady=4)
        self._refresh_bench()

    def _build_console(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Console")
        bar = ttk.Frame(tab)
        bar.pack(fill="x", padx=6, pady=4)
        self.autoscroll_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(bar, text="Autoscroll", variable=self.autoscroll_var).pack(side="left")
        ttk.Button(bar, text="Clear", command=self._clear_console).pack(side="left", padx=6)
        self.console = scrolledtext.ScrolledText(tab, wrap="none", state="disabled",
                                                 font=("Consolas", 9), background="#0d1117",
                                                 foreground="#c9d1d9")
        self.console.tag_configure("TX", foreground="#79c0ff")
        self.console.tag_configure("RX", foreground="#c9d1d9")
        self.console.tag_configure("ERROR", foreground="#ff7b72")
        self.console.pack(fill="both", expand=True, padx=6, pady=(0, 6))

    def _build_evidence(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook)
        notebook.add(tab, text="Evidence")
        bar = ttk.Frame(tab)
        bar.pack(fill="x", padx=6, pady=6)
        ttk.Button(bar, text="Export 114-ID report", command=self._export_report).pack(side="left")
        ttk.Button(bar, text="Export telemetry CSV", command=self._export_telemetry).pack(
            side="left", padx=6)
        ttk.Button(bar, text="Import W01-W04 evidence",
                   command=self._import_existing_evidence).pack(side="left", padx=6)
        ttk.Button(bar, text="Verify evidence", command=self._verify_evidence).pack(
            side="left", padx=6)
        ttk.Button(bar, text="Open folder", command=self._open_session_folder).pack(side="left")
        ttk.Button(bar, text="Settings", command=self._open_settings).pack(side="left", padx=6)
        self.evidence_text = scrolledtext.ScrolledText(tab, wrap="word", state="disabled",
                                                       font=("Consolas", 10))
        self.evidence_text.pack(fill="both", expand=True, padx=6, pady=(0, 6))

    # ------------------------------------------------------------------
    # Session/UI refresh
    # ------------------------------------------------------------------
    def _update_session_label(self) -> None:
        if hasattr(self, "session_label"):
            self.session_label.configure(
                text=f"Session {self.store.session_id} | {self.store.root}")

    def _refresh_tree(self) -> None:
        if not hasattr(self, "tree"):
            return
        selected = set(self.tree.selection())
        for item in self.tree.get_children(""):
            self.tree.delete(item)
        search = self.search_var.get().strip().lower() if hasattr(self, "search_var") else ""
        outcome_filter = self.filter_var.get() if hasattr(self, "filter_var") else "ALL"
        results = self.store.results()
        for week in range(1, 25):
            parent = f"W{week:02d}"
            week_defs = by_week(week)
            self.tree.insert("", "end", iid=parent,
                             text=f"W{week:02d}", values=("", f"Member A Week {week}",
                                                          "", "", "", ""), open=True)
            for definition in week_defs:
                result = results.get(definition.test_id)
                outcome = result.outcome.value if result else Outcome.NOT_RUN.value
                reason = result.failure_reason if result else ""
                haystack = f"{definition.test_id} {definition.title} {definition.criterion}".lower()
                if search and search not in haystack:
                    continue
                if outcome_filter != "ALL" and outcome != outcome_filter:
                    continue
                self.tree.insert(parent, "end", iid=definition.test_id,
                                 text="",
                                 values=(definition.test_id, definition.title,
                                         definition.mode.value, definition.safety.value,
                                         outcome, reason),
                                 tags=(OUTCOME_TAG.get(outcome, "notrun"),))
        for item in selected:
            if self.tree.exists(item):
                self.tree.selection_add(item)

    def _refresh_evidence(self) -> None:
        if not hasattr(self, "evidence_text"):
            return
        results = self.store.results()
        counts = {outcome.value: 0 for outcome in Outcome}
        for definition in DEFINITIONS:
            result = results.get(definition.test_id)
            counts[result.outcome.value if result else Outcome.NOT_RUN.value] += 1
        problems = self.store.verify_attachments()
        lines = [
            f"Session: {self.store.root}",
            f"Session ID: {self.store.session_id}",
            f"Operator: {self.store.operator or 'UNRECORDED'}",
            f"App version: {APP_VERSION}",
            f"Device: {json.dumps(self.store.session.get('device_identity', {}), indent=2)}",
            f"Firmware kind: {self.store.session.get('firmware_kind') or 'UNRECORDED'}",
            "",
            "Coverage:",
            f"  PASS       {counts.get('PASS', 0)}",
            f"  FAIL       {counts.get('FAIL', 0)}",
            f"  INCOMPLETE {counts.get('INCOMPLETE', 0)}",
            f"  NOT_RUN    {counts.get('NOT_RUN', 0)}",
            f"  TOTAL      {len(DEFINITIONS)}",
            "",
            f"Imported W01-W04 files: {len(self.store.imported_manifest())}",
            f"H8 bench results: {len(self.store.bench_results())}",
            "",
            f"Evidence integrity: {'OK' if not problems else str(len(problems)) + ' problem(s)'}",
        ]
        for problem in problems[:20]:
            lines.append(f"  {problem}")
        if len(problems) > 20:
            lines.append(f"  ... {len(problems) - 20} more")
        lines.append("")
        lines.append("Result files:")
        for result in sorted(results.values(), key=lambda item: item.test_id):
            lines.append(f"  {result.test_id:10s} {result.outcome.value:10s} "
                         f"{len(result.evidence)} evidence  {result.failure_reason}")
        self.evidence_text.configure(state="normal")
        self.evidence_text.delete("1.0", "end")
        self.evidence_text.insert("1.0", "\n".join(lines))
        self.evidence_text.configure(state="disabled")

    def _refresh_bench(self) -> None:
        if not hasattr(self, "bench_compat_text"):
            return
        result = compat.classify(self.device.snapshot)
        lines = [f"{name}: {value}" for name, value in result.capability_rows()]
        lines += ["", "Notes:", *[f"- {note}" for note in result.notes], "",
                  f"Connected: {self.device.snapshot.connected}"]
        self.bench_compat_text.configure(state="normal")
        self.bench_compat_text.delete("1.0", "end")
        self.bench_compat_text.insert("1.0", "\n".join(lines))
        self.bench_compat_text.configure(state="disabled")
        h8 = result.kind == "H8_BENCH"
        state = "normal" if h8 and not self._running else "disabled"
        if hasattr(self, "h8_read_only_button"):
            self.h8_read_only_button.configure(state=state)
            self.h8_stage_f_button.configure(state=state)
        bench_lines = []
        for payload in self.store.bench_results()[:20]:
            bench_lines.append(
                f"{payload.get('recorded_at', '')} {payload.get('kind', '')} "
                f"{payload.get('outcome', '')} {payload.get('reason', '')} [{payload.get('_path')}]")
        self.bench_result_text.configure(state="normal")
        self.bench_result_text.delete("1.0", "end")
        self.bench_result_text.insert("1.0", "\n".join(bench_lines) or
                                      "No H8 bench results in this session.")
        self.bench_result_text.configure(state="disabled")

    def _require_h8(self) -> bool:
        frame = self.device.latest_frame()
        if not self.device.snapshot.connected or frame is None:
            messagebox.showwarning("H8 readiness", "Connect the device and wait for telemetry first.")
            return False
        if not frame.is_h8:
            messagebox.showwarning(
                "H8 readiness",
                "This action requires the H8 bench image (#CG H8S). The canonical W06 "
                "acceptance tests are on the Requirements tab.")
            return False
        return True

    def _start_generic_worker(self, function, label: str) -> None:
        if self._running:
            messagebox.showinfo("Busy", "A test or bench action is already running.")
            return
        self.operator.reset_cancel()
        self._set_running(True)
        self.status_var.set(f"{label} running…")

        def worker() -> None:
            try:
                payload = function()
                self.ui_queue.put(("bench_done", payload))
            except Exception as exc:
                self.ui_queue.put(("error", f"{label}: {exc}"))
            finally:
                self.ui_queue.put(("generic_done", None))

        self.worker = threading.Thread(target=worker, name="cg-h8-bench", daemon=True)
        self.worker.start()

    def _start_h8_read_only(self) -> None:
        if not self._require_h8():
            return
        if not messagebox.askyesno(
                "H8 read-only capture",
                "Capture 60 s of H8S telemetry. This sends NO commands to the device. Continue?"):
            return
        self._start_generic_worker(
            lambda: H8Bench(self.device, self.store, self.operator).read_only(60),
            "H8 read-only capture")

    def _start_h8_stage_f(self) -> None:
        if not self._require_h8():
            return
        if not messagebox.askyesno(
                "H8 Stage F supervised check",
                "This may energize the TEC for a 30 s, 20 % Stage F check.\n\n"
                "The app will require your prechecks, the boot token, fan confirmation, "
                "door polarity, SUPERVISE and ARM. The H8 firmware refuses START if the "
                "Stage F guard, limits, host ACK or OFF-current gate are not satisfied.\n\n"
                "Continue?"):
            return
        self._start_generic_worker(
            lambda: H8Bench(self.device, self.store, self.operator).supervised_stage_f(),
            "H8 Stage F check")

    def _import_existing_evidence(self) -> None:
        try:
            summary = evidence_import.import_all(self.store)
        except Exception as exc:
            messagebox.showerror("Evidence import", str(exc))
            return
        lines = [
            f"Imported: {summary['imported']}",
            f"Duplicates skipped: {summary['skipped_duplicate']}",
            f"Missing patterns: {len(summary['missing'])}",
            f"Errors: {len(summary['errors'])}",
        ]
        for test_id, count in sorted(summary["by_test"].items()):
            lines.append(f"{test_id}: {count}")
        if summary["errors"]:
            lines.append("")
            lines.extend(str(error) for error in summary["errors"][:10])
        messagebox.showinfo("W01-W04 evidence import", "\n".join(lines))
        self._results_dirty = True
        self._refresh_evidence()
        self._refresh_bench()

    def _open_bench_folder(self) -> None:
        try:
            os.startfile(self.store.bench_dir)
        except Exception as exc:
            messagebox.showerror("Open bench results", str(exc))

    def _show_selected(self) -> None:
        selection = self.tree.selection()
        if not selection:
            return
        test_id = selection[0]
        definition = get_definition(test_id)
        if definition is None:
            return
        result = self.store.result(test_id)
        lines = [
            f"{definition.test_id} — {definition.title}",
            f"Week {definition.week} | {definition.mode.value} | {definition.safety.value}"
            + (f" | duration {definition.duration_s:.0f}s" if definition.duration_s else "")
            + f" | repetitions {definition.repetitions}",
            "",
            "Canonical criterion:",
            definition.criterion,
            "",
        ]
        _add_list(lines, "Hardware prerequisites:", definition.hardware_prereqs)
        _add_list(lines, "Firmware prerequisites:", definition.firmware_prereqs)
        _add_list(lines, "Test prerequisites:", definition.prerequisites)
        _add_list(lines, "Required actions:", definition.actions or ("(handler prompts)",))
        _add_list(lines, "Checks:", definition.checks)
        _add_list(lines, "Evidence:", definition.evidence)
        lines.append(f"Result: {result.outcome.value if result else Outcome.NOT_RUN.value}")
        if result is not None:
            lines.append(f"Source: {result.source}")
            lines.append(f"Failure reason: {result.failure_reason or '(none)'}")
            lines.append(f"Started: {result.started_at}  Ended: {result.ended_at}")
            if result.checks:
                lines.append("")
                lines.append("Check results:")
                for check in result.checks:
                    marker = "PASS" if check.passed else "FAIL"
                    lines.append(f"  [{marker}] {check.name}: {check.detail}"
                                 + (f" ({check.failure_reason})" if check.failure_reason else ""))
            if result.evidence:
                lines.append("")
                lines.append("Evidence files:")
                for item in result.evidence:
                    lines.append(f"  {item.get('stored')} sha256={item.get('sha256', '')[:16]}…")
            if result.measurements:
                lines.append("")
                lines.append("Measurements:")
                lines.append(json.dumps(result.measurements, indent=2)[:8000])
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", "\n".join(lines))
        self.detail_text.configure(state="disabled")

    # ------------------------------------------------------------------
    # Device
    # ------------------------------------------------------------------
    def _refresh_ports(self) -> None:
        ports = list_ports()
        labels = []
        self._port_map: dict[str, str] = {}
        for port in ports:
            label = f"{port.device} — {port.description}"
            if port.vid is not None and port.pid is not None:
                label += f" [{port.vid:04X}:{port.pid:04X}]"
            labels.append(label)
            self._port_map[label] = port.device
        self.port_box["values"] = labels
        if labels:
            preferred = next((label for label in labels
                              if ("303A" in label and "1001" in label)
                              or "USB" in label.upper()), labels[0])
            self.port_var.set(preferred)
        else:
            self.port_var.set("")

    def _connect(self) -> None:
        if self.device.snapshot.connected:
            return
        label = self.port_var.get()
        port = self._port_map.get(label, label.split(" — ")[0] if label else "")
        if not port:
            messagebox.showwarning("Port", "Select a COM port first.")
            return
        try:
            self.device.close()
            self.device.open(port)
        except Exception as exc:
            messagebox.showerror("Connection failed", str(exc))
            self._update_connection_label()
            return
        self.status_var.set(f"Connected to {port}; waiting for telemetry")
        self.connect_button.configure(state="disabled")
        self.disconnect_button.configure(state="normal")
        self._update_connection_label()

    def _disconnect(self) -> None:
        if self.device.snapshot.connected:
            if not messagebox.askyesno(
                    "Disconnect",
                    "Closing the USB-Serial/JTAG port may reset the board. Disconnect?"):
                return
        self.device.close()
        self.connect_button.configure(state="normal")
        self.disconnect_button.configure(state="disabled")
        self.status_var.set("Disconnected")
        self._update_connection_label()

    def _update_connection_label(self) -> None:
        snapshot = self.device.snapshot
        if snapshot.connected:
            text = f"connected {snapshot.port} | {snapshot.firmware_kind or 'waiting'}"
        else:
            text = "disconnected"
        if hasattr(self, "connection_label"):
            self.connection_label.configure(text=text)
        if hasattr(self, "rx_label"):
            self.rx_label.configure(text=f"RX {snapshot.rx_lines} | TX {snapshot.tx_commands}")
        if hasattr(self, "connect_button") and not self._running:
            self.connect_button.configure(state="disabled" if snapshot.connected else "normal")
            self.disconnect_button.configure(state="normal" if snapshot.connected else "disabled")

    def _poll_device(self) -> None:
        if self.closing:
            return
        try:
            frames, self._frame_cursor = self.device.frames_since(self._frame_cursor)
            for frame in frames:
                self._last_frame_time = time.monotonic()
                self.chart.add_frame(frame)
                self._update_dashboard(frame)
            events, self._event_cursor = self.device.events_since(self._event_cursor)
            for event in events:
                self._append_console(event.raw, "RX")
                if event.kind == "ERR":
                    self._append_console(event.raw, "ERROR")
            self._update_connection_label()
            if self.device.snapshot.connected and self.device.snapshot.last_frame is not None:
                if time.monotonic() - self._last_frame_time > 4.0:
                    self.status_var.set("No telemetry for more than 4 s")
            if time.monotonic() - self._last_bench_refresh > 2.0:
                self._last_bench_refresh = time.monotonic()
                self._refresh_bench()
        except Exception as exc:
            self.status_var.set(f"Device poll error: {exc}")
        self.after(150, self._poll_device)

    def _update_dashboard(self, frame: protocol.TelemetryFrame) -> None:
        snapshot = self.device.snapshot

        def fmt(value: Any, digits: int = 2) -> str:
            if value is None:
                return "—"
            if isinstance(value, float):
                return f"{value:.{digits}f}"
            return str(value)

        self.identity_vars["device_id"].set(fmt(snapshot.boot.device_id or frame.device_id))
        self.identity_vars["boot_id"].set(fmt(frame.boot_id))
        self.identity_vars["firmware"].set(fmt(frame.firmware_version))
        self.identity_vars["hardware_config"].set(fmt(frame.hardware_config_id))
        self.identity_vars["pin_map"].set(fmt(snapshot.boot.pin_map))
        self.identity_vars["calibration"].set(fmt(frame.calibration_id))
        self.identity_vars["firmware_kind"].set(fmt(snapshot.firmware_kind))
        self.identity_vars["port"].set(fmt(snapshot.port))
        for role in ("T1", "T2", "T3", "SPARE"):
            self.value_vars[role].set(fmt(frame.temperature(role)))
        self.value_vars["chamber"].set(fmt(frame.chamber_c))
        self.value_vars["hot_side"].set(fmt(frame.hot_side_c))
        self.value_vars["ambient"].set(fmt(frame.ambient_c))
        self.value_vars["humidity"].set(fmt(frame.humidity_pct))
        self.value_vars["door"].set("OPEN" if frame.door_open else
                                    "CLOSED" if frame.door_open is False else "UNVERIFIED")
        self.value_vars["door_polarity"].set(
            snapshot.door_polarity or frame.kv.get("door_polarity") or "—")
        self.value_vars["voltage"].set(fmt(frame.voltage_v))
        self.value_vars["current"].set(fmt(frame.current_a))
        self.value_vars["power"].set(fmt(frame.power_w))
        self.value_vars["energy"].set(fmt(frame.energy_wh, 1))
        self.value_vars["state"].set(fmt(frame.state))
        self.value_vars["quality"].set(fmt(frame.quality))
        self.value_vars["applied"].set(fmt(frame.cooling_applied))
        self.value_vars["pwm"].set(fmt(frame.pwm_applied if frame.pwm_applied is not None
                                       else frame.pwm_duty))
        self.value_vars["fault"].set(f"0x{frame.fault_bits:08X}" if frame.fault_bits
                                     else "0x00000000")
        self.identity_vars["h8_mode"].set(fmt(snapshot.h8.get("test_mode")))
        self.identity_vars["h8_stage"].set(fmt(frame.test_phase))
        self.identity_vars["h8_supervised"].set(fmt(
            snapshot.h8.get("supervised_bench") or snapshot.h8.get("supervised")))
        self.identity_vars["h8_ack"].set(str(snapshot.h8_ack_count))
        stage = (frame.output_stage or "UNKNOWN").upper()
        if frame.is_h8:
            self.banner_var.set("H8 benchmark image detected — use the Bench readiness tab for "
                                "read-only H8S capture and the supervised Stage F probe. "
                                "Canonical W06 tests are INCOMPLETE on this image.")
        elif stage == "DISABLED":
            self.banner_var.set("Output stage is compiled out. Tests that need TEC energization "
                                "will be INCOMPLETE; manual START is disabled.")
        else:
            self.banner_var.set("")
        self.start_button.configure(state="normal" if stage == "ENABLED" else "disabled")
        if not self.token_var.get() and snapshot.auth_token:
            self.token_var.set(snapshot.auth_token)
        identity_key = (snapshot.port, snapshot.boot.boot_id, snapshot.firmware_kind,
                        snapshot.boot.hardware_config_id)
        if identity_key != self._last_identity:
            self._last_identity = identity_key
            self.store.set_device(snapshot.port, snapshot.identity(), snapshot.firmware_kind)

    def _poll_operator(self) -> None:
        if self.closing:
            return
        while True:
            try:
                request = self.operator.requests.get_nowait()
            except queue.Empty:
                break
            try:
                request.response = self._show_operator_request(request)
            finally:
                request.event.set()
        self.after(100, self._poll_operator)

    def _show_operator_request(self, request: OperatorRequest) -> Any:
        kind = request.kind
        kwargs = request.kwargs
        if kind == "info":
            messagebox.showinfo(kwargs.get("title"), kwargs.get("message"), parent=self)
            return None
        if kind == "confirm":
            return messagebox.askyesno(kwargs.get("title"), kwargs.get("message"), parent=self)
        if kind == "choose":
            dialog = ChoiceDialog(self, kwargs.get("title"), kwargs.get("message"),
                                  list(kwargs.get("options", [])))
            return dialog.result
        if kind == "text":
            dialog = TextDialog(self, kwargs.get("title"), kwargs.get("message"),
                                bool(kwargs.get("multiline")))
            return dialog.result
        if kind == "number":
            unit = kwargs.get("unit") or ""
            value = simpledialog.askfloat(
                kwargs.get("title"), f"{kwargs.get('message')} {unit}".strip(),
                initialvalue=kwargs.get("minimum") if kwargs.get("minimum") is not None else 0.0,
                minvalue=kwargs.get("minimum"), maxvalue=kwargs.get("maximum"),
                parent=self)
            return value
        if kind == "file":
            kinds = kwargs.get("kinds") or [("All files", "*.*")]
            return filedialog.askopenfilename(title=kwargs.get("title"), filetypes=kinds,
                                              parent=self) or None
        return None

    def _poll_ui(self) -> None:
        if self.closing:
            return
        while True:
            try:
                message = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            kind = message[0]
            if kind == "progress":
                _, text, fraction = message
                self.status_var.set(text)
                if fraction is not None:
                    self.progress["value"] = max(0.0, min(1.0, fraction))
            elif kind == "result":
                self.progress["value"] = 1.0
                self.status_var.set(f"{message[1].test_id} {message[1].outcome.value}")
                self._results_dirty = True
            elif kind == "batch_done":
                self._set_running(False)
                self.status_var.set("Batch finished")
                self.progress["value"] = 0.0
                self._results_dirty = True
            elif kind == "bench_done":
                payload = message[1]
                self.status_var.set(f"{payload.get('kind')} {payload.get('outcome')}")
                self._results_dirty = True
                self._refresh_bench()
            elif kind == "generic_done":
                self._set_running(False)
                self.progress["value"] = 0.0
                self._results_dirty = True
            elif kind == "error":
                self.status_var.set(str(message[1]))
        if self._results_dirty:
            self._results_dirty = False
            self._refresh_tree()
            self._refresh_evidence()
        self.after(120, self._poll_ui)

    # ------------------------------------------------------------------
    # Test execution
    # ------------------------------------------------------------------
    def _selected_ids(self) -> list[str]:
        selection = self.tree.selection()
        ids: list[str] = []
        for item in selection:
            if item.startswith("W") and len(item) == 3:
                ids.extend(definition.test_id for definition in by_week(int(item[1:])))
            elif get_definition(item) is not None:
                ids.append(item)
        return sorted(set(ids))

    def _run_selected(self) -> None:
        ids = self._selected_ids()
        if not ids:
            messagebox.showinfo("Run", "Select a requirement or a week first.")
            return
        passed = [test_id for test_id in ids
                  if (self.store.result(test_id) is not None
                      and self.store.result(test_id).outcome is Outcome.PASS)]
        force = False
        if passed:
            force = messagebox.askyesno(
                "Re-run passed tests",
                f"{len(passed)} selected test(s) already PASS. Re-running preserves the prior "
                "attempt under results/history and replaces the current result.\n\nRe-run?")
            if not force:
                ids = [test_id for test_id in ids if test_id not in passed]
                if not ids:
                    return
        self._start_batch(ids, ask_powered=True, force=force)

    def _run_week(self) -> None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showinfo("Run week", "Select a week node first.")
            return
        item = selection[0]
        if not (item.startswith("W") and len(item) == 3):
            definition = get_definition(item)
            if definition is None:
                return
            week = definition.week
        else:
            week = int(item[1:])
        ids = [definition.test_id for definition in by_week(week)]
        self._start_batch(ids, ask_powered=True)

    def _run_all(self) -> None:
        ids = [definition.test_id for definition in DEFINITIONS]
        self._start_batch(ids, ask_powered=True)

    def _start_batch(self, ids: list[str], ask_powered: bool, force: bool = False) -> None:
        if self._running:
            messagebox.showinfo("Run", "A test batch is already running.")
            return
        powered = [test_id for test_id in ids
                   if (get_definition(test_id) and
                       get_definition(test_id).safety is SafetyClass.POWERED_GUIDED)]
        allow_powered = False
        if powered:
            allow_powered = messagebox.askyesno(
                "Powered tests selected",
                f"{len(powered)} selected test(s) may energize the TEC under supervision.\n\n"
                "The application will NOT ARM or START by itself. Each powered test asks for "
                "explicit prechecks, the boot token and operator confirmation.\n\n"
                "Include powered tests in this batch?")
        self.operator.reset_cancel()
        self._set_running(True)
        self.status_var.set("Running tests…")

        def worker() -> None:
            try:
                for test_id in ids:
                    if self.operator.cancelled() or self.closing:
                        break
                    definition = get_definition(test_id)
                    if definition is None:
                        continue
                    if definition.safety is SafetyClass.POWERED_GUIDED and not allow_powered:
                        existing = self.store.result(test_id)
                        if existing is not None and existing.outcome is Outcome.PASS:
                            continue
                        result = TestResult(
                            test_id=test_id,
                            outcome=Outcome.INCOMPLETE,
                            started_at=now_iso(),
                            ended_at=now_iso(),
                            failure_reason="POWERED_TEST_REQUIRES_EXPLICIT_OPERATOR_SELECTION",
                            operator=self.store.operator,
                            device_identity=self.device.snapshot.identity(),
                            source="HARDWARE" if not self.device.is_simulated else "SIMULATED",
                        )
                        self.store.record_result(result)
                        self.ui_queue.put(("result", result))
                        continue
                    result = self.runner.run(test_id, force=force)
                    self.ui_queue.put(("result", result))
            except Exception as exc:
                self.ui_queue.put(("error", f"Batch error: {exc}"))
            finally:
                self.ui_queue.put(("batch_done", None))

        self.worker = threading.Thread(target=worker, name="cg-test-runner", daemon=True)
        self.worker.start()

    def _set_running(self, running: bool) -> None:
        self._running = running
        state = "disabled" if running else "normal"
        for button in (self.run_selected_button, self.run_week_button, self.run_all_button):
            button.configure(state=state)
        self.stop_button.configure(state="normal" if running else "disabled")
        if running:
            self.connect_button.configure(state="disabled")
            self.disconnect_button.configure(state="disabled")
        elif self.device.snapshot.connected:
            self.connect_button.configure(state="disabled")
            self.disconnect_button.configure(state="normal")
        else:
            self.connect_button.configure(state="normal")
            self.disconnect_button.configure(state="disabled")
        self._refresh_bench()

    def _stop_test(self) -> None:
        self.operator.cancel()
        self.status_var.set("Cancellation requested; the current check will stop at the next safe point")
        try:
            if self.device.snapshot.connected:
                self.device.send(protocol.stop(), "operator STOP from GUI")
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Manual controls
    # ------------------------------------------------------------------
    def _send_arm(self) -> None:
        frame = self.device.latest_frame()
        if frame is not None and frame.is_h8:
            messagebox.showerror(
                "ARM",
                "The H8 image uses a different command grammar. Use the Bench readiness tab "
                "(SUPERVISE/STAGE F/FAN/DOOR/ARM); no canonical ARM was sent.")
            return
        token = self.token_var.get().strip()
        try:
            command = protocol.arm(token)
        except protocol.CommandError as exc:
            messagebox.showerror("ARM", str(exc))
            return
        if not messagebox.askyesno(
                "ARM", "ARM authorizes one bounded run. This does not energize the TEC yet.\n"
                       "Continue?"):
            return
        try:
            supervised = (frame is not None
                          and (str(frame.kv.get("supervised_bench")) == "1"
                               or str(frame.kv.get("bench_policy", "")).upper()
                               .startswith("SUPERVISED")))
            if supervised:
                self.device.send(protocol.supervise(token), "manual SUPERVISE")
            self.device.send(command, "manual ARM")
            self.status_var.set("SUPERVISE + ARM sent" if supervised else "ARM sent")
        except Exception as exc:
            messagebox.showerror("ARM", str(exc))

    def _send_start(self) -> None:
        frame = self.device.latest_frame()
        if frame is None:
            messagebox.showwarning("START", "No telemetry yet.")
            return
        if frame.is_h8:
            messagebox.showerror(
                "START",
                "The H8 image uses the Bench readiness Stage F flow, not canonical START. "
                "No command was sent.")
            return
        if (frame.output_stage or "").upper() != "ENABLED":
            messagebox.showerror("START", "The output stage is compiled out; START is refused by design.")
            return
        try:
            seconds = int(self.seconds_var.get())
            command = protocol.start(seconds)
        except (ValueError, protocol.CommandError) as exc:
            messagebox.showerror("START", str(exc))
            return
        if not messagebox.askyesno(
                "Supervised START",
                f"START {seconds} s will energize the TEC under supervision.\n\n"
                "Confirm: fuse installed, fan unobstructed, no loose terminal, operator present, "
                "hot-side probe valid and cooling polarity frozen.\n\nContinue?"):
            return
        try:
            self.device.send(command, "manual START")
            self.status_var.set(f"START {seconds}s sent")
        except Exception as exc:
            messagebox.showerror("START", str(exc))

    def _send_stop(self) -> None:
        try:
            self.device.send(protocol.stop(), "manual STOP")
            self.status_var.set("STOP sent")
        except Exception as exc:
            messagebox.showerror("STOP", str(exc))

    def _send_estop(self) -> None:
        try:
            self.device.send(protocol.estop(), "manual ESTOP")
            self.status_var.set("ESTOP sent")
        except Exception as exc:
            messagebox.showerror("ESTOP", str(exc))

    def _send_status(self) -> None:
        try:
            self.device.send(protocol.status(), "STATUS")
            self.status_var.set("STATUS sent")
        except Exception as exc:
            self.status_var.set(f"STATUS failed: {exc}")

    def _warm_reset(self) -> None:
        if not self.device.snapshot.connected:
            messagebox.showwarning("Warm reset", "Connect the device first.")
            return
        if not messagebox.askyesno(
                "Warm reset",
                "This pulses the USB-Serial/JTAG reset control lines. It is a warm SoC reset, "
                "NOT a logic-power cycle. The 12 V PSU and TEC branch are not touched.\n\n"
                "This board has no reset button. Continue?"):
            return
        ok = self.device.pulse_warm_reset()
        self.status_var.set("Warm reset (close/reopen + DTR/RTS drop) sent" if ok
                            else "Warm reset failed")

    # ------------------------------------------------------------------
    # Reports and tools
    # ------------------------------------------------------------------
    def _export_report(self) -> None:
        try:
            paths = self.store.export_report(DEFINITIONS)
        except Exception as exc:
            messagebox.showerror("Export", str(exc))
            return
        messagebox.showinfo("Report exported",
                            "\n".join(f"{key}: {value}" for key, value in paths.items()))
        self._refresh_evidence()

    def _export_telemetry(self) -> None:
        try:
            info = self.store.export_telemetry_csv()
        except Exception as exc:
            messagebox.showerror("Telemetry export", str(exc))
            return
        messagebox.showinfo("Telemetry exported",
                            f"{info['path']}\nrows={info['rows']}\nsha256={info['sha256']}")

    def _verify_evidence(self) -> None:
        problems = self.store.verify_attachments()
        if problems:
            messagebox.showerror("Evidence integrity",
                                 "\n".join(str(problem) for problem in problems[:20]))
        else:
            messagebox.showinfo("Evidence integrity", "All attachment hashes match.")
        self._refresh_evidence()

    def _open_settings(self) -> None:
        dialog = SettingsDialog(self)
        if dialog.result is None:
            return
        for key, value in dialog.result.items():
            self.store.set_config(key, value)
            if value is None:
                self.runner.config.pop(key, None)
            else:
                self.runner.config[key] = value
        self.status_var.set("Settings saved to the session")

    def _create_bom_template(self) -> None:
        path = self.store.root / "bom-audit-template.csv"
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["id", "present", "quantity", "marking", "seller_sku",
                             "condition", "unknown_notes"])
            for index in range(1, 25):
                writer.writerow([f"HW-{index:02d}", "", "", "", "", "", ""])
        messagebox.showinfo("BOM template", f"Created {path}")

    def _open_session_folder(self) -> None:
        try:
            os.startfile(self.store.root)
        except Exception as exc:
            messagebox.showerror("Open folder", str(exc))

    def _clear_console(self) -> None:
        self.console.configure(state="normal")
        self.console.delete("1.0", "end")
        self.console.configure(state="disabled")

    def _append_console(self, text: str, tag: str) -> None:
        self.console.configure(state="normal")
        self.console.insert("end", text + "\n", tag)
        if int(self.console.index("end-1c").split(".")[0]) > 6000:
            self.console.delete("1.0", "1000.0")
        self.console.configure(state="disabled")
        if self.autoscroll_var.get():
            self.console.see("end")

    def _about(self) -> None:
        messagebox.showinfo(
            "About",
            f"ColdGuard Member A Hardware Acceptance {APP_VERSION}\n\n"
            "Coverage: 114 canonical A-W01..A-W24 requirements.\n"
            "Protocol: canonical #CG TELEM schema 3 / #CG H8S; console UART 115200 8N1.\n\n"
            "Safety:\n"
            "- No reset button is assumed: warm reset pulses USB-JTAG lines; cold boot is a guided "
            "USB power removal.\n"
            "- The app never energizes the TEC automatically. Powered tests require explicit "
            "selection, prechecks, the boot token and ARM/START.\n"
            "- Simulated telemetry can never produce PASS for a hardware-measurement test; "
            "documentary and operator-attested results keep their explicit source.\n\n"
            "Known limitations:\n"
            "- The shipped firmware compiles the TEC output stage out; tests needing energization "
            "are INCOMPLETE until a supervised stage-enabled image is flashed.\n"
            "- No network command transport exists, so duplicate-canonical and true expired-command "
            "tests are INCOMPLETE.\n"
            "- A-W06-06 is INCOMPLETE until an accepted command state exists (network transport); "
            "the local console source is refused before the idempotency store.\n"
            "- The installed H8 bench image speaks #CG H8S, not the canonical W06 console; "
            "canonical hardware tests are INCOMPLETE. Use Bench readiness for read-only H8S "
            "capture and a supervised Stage F probe.\n"
            "- W01-W04 documentary evidence can be imported from the authoritative corpora "
            "instead of being recreated; import never marks a requirement PASS.\n"
            "- PWM duty control is not exposed by the canonical console.")

    def _on_close(self) -> None:
        if self._running and not messagebox.askyesno(
                "Exit", "A test batch is running. Stop it and exit?"):
            return
        self.closing = True
        self.operator.cancel()

        def safe_stop() -> None:
            try:
                if self.device.snapshot.connected:
                    self.device.send(protocol.stop(), "controlled STOP on application exit")
            except Exception:
                pass

        safe_stop()
        if self.worker is not None and self.worker.is_alive():
            self.worker.join(timeout=3.0)
        safe_stop()
        try:
            self.device.close()
        except Exception:
            pass
        self.store.close()
        self.destroy()


def main(smoke: bool = False) -> None:
    errors = validate()
    if errors:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Registry error", "\n".join(errors))
        root.destroy()
        raise SystemExit(2)
    app = AcceptanceApp()
    if smoke:
        def close_smoke() -> None:
            app.closing = True
            try:
                app.device.close()
            except Exception:
                pass
            app.store.close()
            app.destroy()
            print("SMOKE_OK")
        app.after(1200, close_smoke)
    app.mainloop()


if __name__ == "__main__":
    main()
