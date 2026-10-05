"""Main window: pick files and tools, see the isolation passes, export a VCarve-ready DXF."""

from __future__ import annotations

import os
import sys
import traceback
from typing import Callable, List, Optional

from PySide6.QtCore import QObject, QRunnable, QSettings, Qt, QThreadPool, QTimer, Signal
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox, QPlainTextEdit, QPushButton, QScrollArea,
    QSpinBox, QSplitter, QVBoxLayout, QWidget,
)

from .. import __version__
from ..detect import detect_files
from ..dxf_out import write_dxf
from ..isolation import IsolationSettings
from ..job import JobConfig, JobResult, LoadedJob, load_job, process_job
from ..setup_sheet import build_setup_sheet
from ..tools import Tool, drill_sizes, read_vtdb
from .preview import LAYERS, BoardView

DEFAULT_DRILLS = "0.8, 1.0, 1.1, 1.2, 2.0, 3.0, 3.1"
BUILTIN_TOOLS = [
    Tool("30° V-bit, 0.1 mm tip (built-in)", "vbit", 3.175, 30.0, 0.1, "PCB Bits"),
    Tool("20° V-bit, 0.1 mm tip (built-in)", "vbit", 3.175, 20.0, 0.1, "PCB Bits"),
    *[Tool(f"{d:g}mm Drill (built-in)", "drill", d, 118.0, 0.0, "PCB Bits") for d in (0.8, 1.0, 1.1, 1.2, 2.0, 3.0, 3.1)],
]


class _Signals(QObject):
    done = Signal(object)
    failed = Signal(str)


class _Task(QRunnable):
    def __init__(self, fn: Callable[[], object]) -> None:
        super().__init__()
        self.fn, self.signals = fn, _Signals()

    def run(self) -> None:
        try:
            self.signals.done.emit(self.fn())
        except Exception as exc:  # reported in the status bar, not a crash
            traceback.print_exc()
            self.signals.failed.emit(str(exc))


def _spin(lo, hi, val, step, decimals=3, suffix="") -> QDoubleSpinBox:
    w = QDoubleSpinBox()
    w.setRange(lo, hi)
    w.setDecimals(decimals)
    w.setSingleStep(step)
    w.setValue(val)
    if suffix:
        w.setSuffix(suffix)
    return w


class FileRow(QWidget):
    changed = Signal()

    def __init__(self, label: str, filt: str) -> None:
        super().__init__()
        self.filt = filt
        self.edit = QLineEdit()
        self.edit.setPlaceholderText("(none)")
        self.edit.editingFinished.connect(self.changed)
        btn = QPushButton("…")
        btn.setFixedWidth(30)
        btn.clicked.connect(self._browse)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        name = QLabel(label.split(" (")[0])
        name.setFixedWidth(95)
        lay.addWidget(name)
        lay.addWidget(self.edit)
        lay.addWidget(btn)
        self.label = label

    def _browse(self) -> None:
        start = os.path.dirname(self.edit.text()) if self.edit.text() else ""
        path, _ = QFileDialog.getOpenFileName(self, f"Choose {self.label}", start, self.filt)
        if path:
            self.edit.setText(path)
            self.changed.emit()

    def path(self) -> Optional[str]:
        t = self.edit.text().strip()
        return t if t and os.path.isfile(t) else None

    def set_path(self, p: Optional[str]) -> None:
        self.edit.setText(p or "")


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle(f"PCB → VCarve  {__version__}")
        self.resize(1400, 850)
        self.settings = QSettings("PricklyGuy", "pcb2vectric")
        self.pool = QThreadPool.globalInstance()
        self.loaded: Optional[LoadedJob] = None
        self.result: Optional[JobResult] = None
        self.tools: List[Tool] = list(BUILTIN_TOOLS)
        self._gen = 0
        self._first_result = True
        self._depth = 0.1
        self._busy_tasks: List[_Task] = []

        self._debounce = QTimer(self)
        self._debounce.setSingleShot(True)
        self._debounce.setInterval(250)
        self._debounce.timeout.connect(self._reprocess)

        self._build_ui()
        self._load_initial_tools()
        self._refresh_tool_widgets()
        self.statusBar().showMessage("Choose a Gerber folder to begin.")

    # ---------------------------------------------------------------- UI construction
    def _build_ui(self) -> None:
        left = QWidget()
        lv = QVBoxLayout(left)

        # files
        g = QGroupBox("1. Gerber files")
        fl = QVBoxLayout(g)
        pick = QPushButton("Open Gerber folder…")
        pick.clicked.connect(self._open_folder)
        fl.addWidget(pick)
        self.f_top = FileRow("Top copper", "Gerber (*.gtl *.gbr *.ger *.top *.cmp);;All (*)")
        self.f_bot = FileRow("Bottom copper", "Gerber (*.gbl *.gbr *.ger *.bot *.sol);;All (*)")
        self.f_out = FileRow("Board outline", "Gerber (*.gko *.gm1 *.gml *.gbr *.oln);;All (*)")
        self.f_drl = FileRow("Drill (Excellon)", "Drill (*.drl *.xln *.exc *.txt);;All (*)")
        self.f_drl2 = FileRow("2nd drill file", "Drill (*.drl *.xln *.exc *.txt);;All (*)")
        for row in (self.f_top, self.f_bot, self.f_out, self.f_drl, self.f_drl2):
            fl.addWidget(row)
            row.changed.connect(self._files_changed)
        lv.addWidget(g)

        # drill bits
        g = QGroupBox("2. Drill bits you own (mm)")
        tl = QFormLayout(g)
        self.drill_sizes = QLineEdit(self.settings.value("drill_sizes", DEFAULT_DRILLS))
        self.drill_sizes.setToolTip("Each hole uses the smallest bit in this list that is big enough. "
                                    "Holes bigger than the largest bit go to the DRILL_MILL layer.")
        self.drill_sizes.editingFinished.connect(self._drills_edited)
        tl.addRow(self.drill_sizes)
        row = QHBoxLayout()
        self.db_label = QLabel("")
        self.db_label.setWordWrap(True)
        b = QPushButton("Import from VCarve tool database…")
        b.clicked.connect(self._import_drills)
        row.addWidget(b, 1)
        r = QPushButton("Reset")
        r.setToolTip("Back to 0.8, 1.0, 1.1, 1.2, 2.0, 3.0, 3.1")
        r.clicked.connect(self._reset_drills)
        row.addWidget(r)
        tl.addRow(row)
        tl.addRow(self.db_label)
        self.skip_vias = QCheckBox("Ignore vias (don't drill them, drop lone via pads)")
        self.skip_vias.setChecked(self.settings.value("skip_vias", "true") in (True, "true"))
        self.skip_vias.toggled.connect(self._vias_edited)
        tl.addRow(self.skip_vias)
        self.via_max = _spin(0.1, 2.0, float(self.settings.value("via_max", 0.6)), 0.05, 2, " mm")
        self.via_max.valueChanged.connect(self._vias_edited)
        tl.addRow("Holes smaller than", self.via_max)
        lv.addWidget(g)

        # copper check
        g = QGroupBox("3. Copper check")
        cl = QFormLayout(g)
        self.gap = _spin(0, 2, 0.2, 0.05, 2, " mm")
        self.gap.valueChanged.connect(self._settings_changed)
        cl.addRow("Warn if copper gaps are under", self.gap)
        note = QLabel("Your VCarve offset runs on both sides of a gap, so gaps narrower than the offsets "
                      "you plan to use will be marked in red. 0 turns this off.")
        note.setWordWrap(True)
        cl.addRow(note)
        lv.addWidget(g)

        # optional isolation passes
        self.iso_group = QGroupBox("Optional: also write pre-offset isolation passes")
        self.iso_group.setCheckable(True)
        self.iso_group.setChecked(False)
        self.iso_group.toggled.connect(self._settings_changed)
        il = QFormLayout(self.iso_group)
        self.iso_tool = QComboBox()
        self.iso_tool.currentIndexChanged.connect(self._settings_changed)
        il.addRow("Isolation bit", self.iso_tool)
        self.mode = QComboBox()
        self.mode.addItems(["Cut depth", "Groove width"])
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.value = _spin(0.005, 5.0, 0.1, 0.01, 3, " mm")
        self.value.valueChanged.connect(self._settings_changed)
        vr = QHBoxLayout()
        vr.addWidget(self.mode)
        vr.addWidget(self.value)
        il.addRow("Set by", vr)
        self.cut_info = QLabel("")
        self.cut_info.setWordWrap(True)
        il.addRow(self.cut_info)
        self.passes = QSpinBox()
        self.passes.setRange(1, 12)
        self.passes.setValue(2)
        self.passes.valueChanged.connect(self._settings_changed)
        il.addRow("Passes", self.passes)
        self.overlap = _spin(0, 90, 30, 5, 0, " %")
        self.overlap.valueChanged.connect(self._settings_changed)
        il.addRow("Pass overlap", self.overlap)
        lv.addWidget(self.iso_group)

        # board
        g = QGroupBox("4. Board")
        bl = QFormLayout(g)
        self.zero = QCheckBox("Move board corner to 0,0")
        self.zero.setChecked(True)
        self.zero.toggled.connect(self._settings_changed)
        bl.addRow(self.zero)
        self.align = QCheckBox("Alignment holes for flipping (double-sided)")
        self.align.toggled.connect(self._settings_changed)
        bl.addRow(self.align)
        self.align_d = _spin(0.5, 10, 3.0, 0.1, 2, " mm")
        self.align_d.valueChanged.connect(self._settings_changed)
        bl.addRow("Alignment hole Ø", self.align_d)
        self.align_m = _spin(1, 30, 5.0, 0.5, 1, " mm")
        self.align_m.valueChanged.connect(self._settings_changed)
        bl.addRow("Distance from board edge", self.align_m)
        lv.addWidget(g)

        self.export_btn = QPushButton("Export DXF for VCarve…")
        self.export_btn.setStyleSheet("font-weight: bold; padding: 10px;")
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._export)
        lv.addWidget(self.export_btn)
        lv.addStretch(1)

        scroll = QScrollArea()
        scroll.setWidget(left)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(400)
        scroll.setMaximumWidth(480)

        # right side: preview + layer toggles + setup sheet
        right = QSplitter(Qt.Vertical)
        top = QWidget()
        tv = QVBoxLayout(top)
        tv.setContentsMargins(0, 0, 0, 0)
        self.view = BoardView()
        tv.addWidget(self.view, 1)
        row = QHBoxLayout()
        self.toggles = {}
        for key, label, _ in LAYERS:
            cb = QCheckBox(label)
            cb.setChecked(self.view.visible_map()[key])
            cb.toggled.connect(lambda on, k=key: self.view.set_layer_visible(k, on))
            self.toggles[key] = cb
            row.addWidget(cb)
        fit = QPushButton("Fit")
        fit.clicked.connect(self.view.fit)
        row.addWidget(fit)
        tv.addLayout(row)
        right.addWidget(top)

        sheet = QWidget()
        sv = QVBoxLayout(sheet)
        sv.setContentsMargins(0, 0, 0, 0)
        hdr = QHBoxLayout()
        hdr.addWidget(QLabel("<b>VCarve setup sheet</b> — what to enter for each layer"))
        copy = QPushButton("Copy")
        copy.clicked.connect(lambda: QApplication.clipboard().setText(self.sheet.toPlainText()))
        hdr.addStretch(1)
        hdr.addWidget(copy)
        sv.addLayout(hdr)
        self.sheet = QPlainTextEdit()
        self.sheet.setReadOnly(True)
        self.sheet.setStyleSheet("font-family: monospace;")
        sv.addWidget(self.sheet)
        right.addWidget(sheet)
        right.setStretchFactor(0, 4)
        right.setStretchFactor(1, 2)

        split = QSplitter()
        split.addWidget(scroll)
        split.addWidget(right)
        split.setStretchFactor(1, 1)
        self.setCentralWidget(split)

    # ---------------------------------------------------------------- tools
    def _load_initial_tools(self) -> None:
        candidates = [self.settings.value("vtdb", "")]
        here = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        candidates.append(os.path.join(here, "shop PC", "tools.vtdb"))
        for p in candidates:
            if p and os.path.isfile(p) and self._load_vtdb(p, quiet=True):
                return

    def _load_vtdb(self, path: str, quiet: bool = False) -> bool:
        try:
            tools = [t for t in read_vtdb(path) if t.kind in ("vbit", "endmill", "tapered", "drill")]
        except Exception as exc:
            if not quiet:
                QMessageBox.warning(self, "Tool database", f"Couldn't read {path}:\n{exc}")
            return False
        self.tools = tools
        self.settings.setValue("vtdb", path)
        self.db_label.setText(f"Tool database: {os.path.basename(path)}")
        return True

    def _import_drills(self) -> None:
        start = self.settings.value("vtdb", "") or ""
        path, _ = QFileDialog.getOpenFileName(self, "Vectric tool database", start, "Vectric tools (*.vtdb *.upload *.cloud);;All (*)")
        if not path or not self._load_vtdb(path):
            return
        sizes, elsewhere = drill_sizes(self.tools)
        name = os.path.basename(path)
        if not sizes:
            QMessageBox.information(
                self, "Drill bits",
                f"{name} has no drill bits in its “PCB Bits” group ({elsewhere} drills in other groups were ignored).\n\n"
                "Your list is unchanged. If you have another copy of the database (e.g. the file named exactly "
                "tools.vtdb on the shop PC), try that one.")
        else:
            merged = sorted(set(self._drill_sizes()) | set(sizes))  # keep sizes you added by hand, like 3.1
            self.drill_sizes.setText(", ".join(f"{v:g}" for v in merged))
            self._drills_edited()
            self.db_label.setText(f"Added {len(sizes)} drill sizes from {name} (“PCB Bits” group)")
        self._refresh_tool_widgets()

    def _vias_edited(self, *_) -> None:
        self.settings.setValue("skip_vias", self.skip_vias.isChecked())
        self.settings.setValue("via_max", self.via_max.value())
        self.via_max.setEnabled(self.skip_vias.isChecked())
        self._settings_changed()

    def _reset_drills(self) -> None:
        self.drill_sizes.setText(DEFAULT_DRILLS)
        self._drills_edited()

    def _drills_edited(self) -> None:
        self.settings.setValue("drill_sizes", self.drill_sizes.text())
        self._settings_changed()

    def _visible_tools(self) -> List[Tool]:
        pcb = [t for t in self.tools if t.group == "PCB Bits"]
        return pcb or self.tools

    def _refresh_tool_widgets(self) -> None:
        """Fill the isolation-bit list (used only by the optional pre-offset passes)."""
        self.iso_tool.blockSignals(True)
        prev = self.iso_tool.currentText()
        self.iso_tool.clear()
        cuts = [t for t in self._visible_tools() if t.kind in ("vbit", "endmill", "tapered")]
        for t in cuts:
            self.iso_tool.addItem(t.name, t)
        self.iso_tool.addItem("Custom cutter (enter groove width)", None)
        idx = self.iso_tool.findText(prev)
        if idx < 0:  # default to the finest-tipped 30° V-bit, the usual PCB trace bit
            v30 = [(t.tip_diameter or 99, i) for i, t in enumerate(cuts) if t.kind == "vbit" and t.included_angle == 30]
            idx = min(v30)[1] if v30 else 0
        self.iso_tool.setCurrentIndex(idx)
        self.iso_tool.blockSignals(False)
        self._settings_changed()

    # ---------------------------------------------------------------- files
    def _open_folder(self) -> None:
        start = self.settings.value("last_dir", "") or ""
        folder = QFileDialog.getExistingDirectory(self, "Folder with Gerber + drill files", start)
        if not folder:
            return
        self.settings.setValue("last_dir", folder)
        d = detect_files(folder)
        self.f_top.set_path(d.top)
        self.f_bot.set_path(d.bottom)
        self.f_out.set_path(d.outline)
        self.f_drl.set_path(d.drills[0] if d.drills else None)
        self.f_drl2.set_path(d.drills[1] if len(d.drills) > 1 else None)
        self.align.setChecked(bool(d.top and d.bottom))
        self._first_result = True
        self._files_changed()

    def _files_changed(self) -> None:
        cfg = self._cfg()
        if not (cfg.top or cfg.bottom):
            self.statusBar().showMessage("Need at least one copper layer.")
            return
        self.statusBar().showMessage("Reading Gerber files…")
        self._gen += 1
        gen = self._gen
        self._run(lambda: load_job(cfg), lambda loaded: self._on_loaded(gen, loaded))

    def _on_loaded(self, gen: int, loaded: LoadedJob) -> None:
        if gen != self._gen:
            return
        self.loaded = loaded
        self._reprocess()

    # ---------------------------------------------------------------- settings -> config
    def _tool(self) -> Optional[Tool]:
        return self.iso_tool.currentData()

    def _drill_sizes(self) -> List[float]:
        sizes = []
        for part in self.drill_sizes.text().replace(";", ",").replace(" ", ",").split(","):
            try:
                v = float(part)
                if v > 0:
                    sizes.append(v)
            except ValueError:
                pass
        return sizes or [float(x) for x in DEFAULT_DRILLS.split(",")]

    def _cut(self):
        """(tool, groove_width, depth) from the current widgets."""
        tool = self._tool()
        v = self.value.value()
        if tool is None:
            tool = Tool("Custom cutter", "endmill", v)
            return tool, v, 0.0
        if tool.kind == "vbit":
            width, depth = tool.cut(depth=v) if self.mode.currentIndex() == 0 else tool.cut(width=v)
        else:
            width, depth = tool.diameter, v
        return tool, width, depth

    def _cfg(self) -> JobConfig:
        tool, width, _ = self._cut()
        drills = [p for p in (self.f_drl.path(), self.f_drl2.path()) if p]
        return JobConfig(
            top=self.f_top.path(), bottom=self.f_bot.path(), outline=self.f_out.path(), drills=drills,
            isolation=IsolationSettings(cut_width=width, passes=self.passes.value(), overlap=self.overlap.value() / 100),
            precompute_isolation=self.iso_group.isChecked(), gap_check=self.gap.value(),
            skip_vias=self.skip_vias.isChecked(), via_max=self.via_max.value(),
            drill_bits=self._drill_sizes(), zero_at_corner=self.zero.isChecked(),
            align_holes=self.align.isChecked(), align_diameter=self.align_d.value(), align_margin=self.align_m.value(),
        )

    def _mode_changed(self) -> None:
        tool = self._tool()
        if tool is not None and tool.kind == "vbit":  # carry the number across so the groove stays the same
            _, width, depth = self._cut_prev
            self.value.blockSignals(True)
            self.value.setValue(depth if self.mode.currentIndex() == 0 else width)
            self.value.blockSignals(False)
        self._settings_changed()

    _cut_prev = (None, 0.2, 0.1)

    def _settings_changed(self, *_) -> None:
        tool, width, depth = self._cut()
        # when the mode flips the widgets already show the new mode, so remember the last real pair
        self._cut_prev = (tool, width, depth)
        self._depth = depth
        if tool.kind == "vbit":
            note = f"Groove {width:.3f} mm wide at {depth:.3f} mm deep"
            if tool.tip_diameter and self.mode.currentIndex() == 1 and self.value.value() < tool.tip_diameter:
                note += f"  (narrower than the {tool.tip_diameter:g} mm tip, using the tip width)"
        elif self._tool() is None:
            note = f"Groove {width:.3f} mm wide"
        else:
            note = f"Groove {width:.3f} mm wide (tool diameter) at {depth:.3f} mm deep"
        self.cut_info.setText(note)
        vbit = self._tool() is not None and tool.kind == "vbit"
        if not vbit and self.mode.currentIndex() != 0:
            self.mode.blockSignals(True)
            self.mode.setCurrentIndex(0)
            self.mode.blockSignals(False)
        self.mode.setEnabled(vbit)
        self._debounce.start()

    # ---------------------------------------------------------------- compute / show
    def _run(self, fn: Callable[[], object], done: Callable[[object], None]) -> None:
        task = _Task(fn)
        self._busy_tasks.append(task)

        def finish(obj):
            self._busy_tasks.remove(task)
            done(obj)

        def fail(msg):
            self._busy_tasks.remove(task)
            self.statusBar().showMessage(f"Error: {msg}")
            QMessageBox.warning(self, "Problem", msg)

        task.signals.done.connect(finish)
        task.signals.failed.connect(fail)
        self.pool.start(task)

    def _reprocess(self) -> None:
        if self.loaded is None:
            return
        cfg = self._cfg()
        loaded = self.loaded
        self._gen += 1
        gen = self._gen
        self._run(lambda: process_job(loaded, cfg), lambda res: self._on_result(gen, res, cfg))

    def _on_result(self, gen: int, res: JobResult, cfg: JobConfig) -> None:
        if gen != self._gen:
            return
        self.result, self._cfg_used = res, cfg
        self.view.set_result(res, self._first_result)
        if self._first_result:
            for key, cb in self.toggles.items():
                cb.blockSignals(True)
                cb.setChecked(self.view.visible_map()[key])
                cb.blockSignals(False)
        self._first_result = False
        tool, _, depth = self._cut()
        self.sheet.setPlainText(build_setup_sheet(res, cfg, tool if self._tool() else None, depth))
        self.export_btn.setEnabled(True)
        tight = sum(len(v) for v in res.tight.values())
        msg = f"Board {res.width:.1f} × {res.height:.1f} mm"
        if res.vias_ignored:
            msg += f"  —  {res.vias_ignored} via holes ignored"
        if tight:
            msg += f"  —  {tight} spot(s) where copper gaps are narrower than {cfg.gap_check:g} mm (red circles)"
        self.statusBar().showMessage(msg)

    # ---------------------------------------------------------------- export
    def _export(self) -> None:
        if self.result is None:
            return
        base = self.f_top.path() or self.f_bot.path() or "board"
        default = os.path.join(os.path.dirname(base), os.path.splitext(os.path.basename(base))[0] + "_vcarve.dxf")
        path, _ = QFileDialog.getSaveFileName(self, "Save DXF", default, "DXF (*.dxf)")
        if not path:
            return
        try:
            write_dxf(self.result, path)
            with open(os.path.splitext(path)[0] + "_setup.txt", "w", encoding="utf-8") as f:
                f.write(self.sheet.toPlainText())
        except Exception as exc:
            QMessageBox.warning(self, "Export failed", str(exc))
            return
        self.statusBar().showMessage(f"Saved {path} and setup sheet")


def main() -> None:
    app = QApplication(sys.argv)
    win = MainWindow()
    win.show()
    sys.exit(app.exec())
