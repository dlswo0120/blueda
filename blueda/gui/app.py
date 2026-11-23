"""BLUEDA 프로그램 창. 실행: python -m blueda"""

import os
import sys
import time
from datetime import datetime

from PySide6.QtCore import Qt, QTimer
from shiboken6 import isValid as shiboken_valid
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QRadioButton, QScrollArea, QStackedWidget, QVBoxLayout,
    QWidget,
)

from .. import charts, methods as M
from ..core import Blueda
from ..loader import detect_file, estimate_memory, load_file, total_memory
from ..result import AnalysisResult
from ..scope import AnalysisScope
from ..settings import EDITABLE, load_settings, save_settings
from . import theme
from .pages import MainPage, StartPage
from ..history import HistoryStore, describe_entry, same_file_name
from ..issues import NEED, collect_issues, summary
from ..settings import settings_path as default_settings_path
from .widgets import Popup, Worker, button, label, repolish

HELP = [
    ("help", "명령 목록"),
    ("show", "마지막 결과의 지표를 여기에 출력"),
    ("clear", "결과 세션 비우기"),
    ("theme dark / theme light", "화면 모드 바꾸기"),
    ("rows", "지금 조건에 맞는 행 수"),
    ("dates", "날짜 문자열 열을 날짜형으로 바꾸는 창 열기"),
    ("history", "조회 히스토리 보기 (기록을 누르면 그때 조건으로 되돌림)"),
]


# 열 선택과 상관없이 모든 열로 실행하는 분석
ALL_COLUMN_METHODS = ("check", "variable_types")


class SettingsDialog(QDialog):
    """오른쪽에 뜨는 설정 패널."""

    def __init__(self, cfg, ui, parent=None):
        super().__init__(parent)
        self.setWindowTitle("설정")
        self.setMinimumWidth(380)
        self.cfg, self.ui = cfg, ui
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(10)
        self.inputs = {}
        self.ranges = {}
        for key, name, desc, lo, hi, step in EDITABLE:
            cur = getattr(cfg, key)
            # 숫자 칸(QSpinBox)은 테두리 스타일을 주면 글자가 사라지는 Qt 문제가 있어 일반 입력칸 사용
            w = QLineEdit(f"{cur:,}" if isinstance(cur, int) else f"{cur:g}")
            w.setToolTip(f"{desc} · 허용 범위 {lo:,g} ~ {hi:,g}")
            self.ranges[key] = (lo, hi, isinstance(cur, int))
            box = QVBoxLayout()
            box.setSpacing(2)
            box.addWidget(w)
            box.addWidget(label(desc, "sub", True))
            form.addRow(name, box)
            self.inputs[key] = w
        mode = QHBoxLayout()
        self.light = QRadioButton("라이트")
        self.dark = QRadioButton("다크")
        (self.dark if ui.get("theme") == "dark" else self.light).setChecked(True)
        mode.addWidget(self.light)
        mode.addWidget(self.dark)
        form.addRow("화면 모드", mode)
        logrow = QHBoxLayout()
        self.log_dir = label(os.path.abspath(cfg.log_dir), "sub", True)
        change = button("바꾸기", "link")
        change.clicked.connect(self._pick_dir)
        logrow.addWidget(self.log_dir, 1)
        logrow.addWidget(change)
        form.addRow("로그 저장 위치", logrow)
        hist = QVBoxLayout()
        hist.setSpacing(2)
        self.hist_on = QCheckBox("조회 히스토리 기록")
        self.hist_on.setChecked(ui.get("history_enabled", True))
        self.hist_mask = QCheckBox("필터 값 가리기 (권장)")
        self.hist_mask.setChecked(ui.get("history_mask", True))
        hist.addWidget(self.hist_on)
        hist.addWidget(self.hist_mask)
        note = label("가리면 고른 값(예: 이름)이 기록 파일에 원문으로 남지 않습니다. "
                     "같은 파일을 열었을 때만 복원됩니다.", "sub", True)
        note.setMinimumWidth(300)
        hist.addWidget(note)
        form.addRow("히스토리", hist)
        # 항목이 많아 창이 길어지므로, 화면이 작거나 배율이 커도 넘치지 않게 스크롤 영역에 넣음
        holder = QWidget()
        holder.setLayout(form)
        scroll = QScrollArea()
        scroll.setWidget(holder)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        avail = QApplication.primaryScreen().availableGeometry().height() if QApplication.primaryScreen() else 900
        scroll.setMinimumHeight(min(holder.sizeHint().height() + 8, int(avail * 0.7)))
        scroll.setMinimumWidth(holder.sizeHint().width() + scroll.verticalScrollBar().sizeHint().width() + 8)
        lay.addWidget(scroll, 1)
        lay.addWidget(label("기준값들은 관례입니다. 바꾸면 이후 실행하는 분석부터 적용됩니다.", "sub", True))
        self.error = label("", "warn", True)
        self.error.hide()
        lay.addWidget(self.error)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Save).setText("저장")
        btns.button(QDialogButtonBox.Cancel).setText("취소")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "로그 저장 위치", self.log_dir.text())
        if d:
            self.log_dir.setText(d)

    def values(self):
        """입력값 검사. 문제가 있으면 (None, 오류 문장)."""
        out = {}
        for key, name, *_ in EDITABLE:
            lo, hi, is_int = self.ranges[key]
            text = self.inputs[key].text().strip().replace(",", "")
            try:
                v = int(float(text)) if is_int else float(text)
            except ValueError:
                return None, f"{name}: 숫자를 입력하세요."
            if not lo <= v <= hi:
                return None, f"{name}: {lo:,g} ~ {hi:,g} 사이로 입력하세요."
            out[key] = v if is_int else round(v, 4)
        return out, ""

    def accept(self):
        vals, err = self.values()
        if vals is None:
            self.error.setText(err)
            self.error.show()
            return
        super().accept()

    def apply(self):
        vals, _ = self.values()
        for key, v in (vals or {}).items():
            setattr(self.cfg, key, v)
        self.cfg.log_dir = self.log_dir.text()
        self.ui["theme"] = "dark" if self.dark.isChecked() else "light"
        self.ui["history_enabled"] = self.hist_on.isChecked()
        self.ui["history_mask"] = self.hist_mask.isChecked()


class ColumnChooser(QDialog):
    """열을 체크해서 고르는 창. 기본은 '메모리가 부족할 때 일부 열만 읽기'이고, 날짜 변환에도 씁니다."""

    def __init__(self, columns, parent=None, title="읽을 열 고르기",
                 message="분석에 필요한 열만 고르면 메모리를 아낄 수 있습니다.", ok_text=None, cancel_text=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        lay = QVBoxLayout(self)
        lay.addWidget(label(message, None, True))
        self.list = QListWidget()
        for c in columns:
            it = QListWidgetItem(str(c))
            it.setData(Qt.UserRole, c)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked)
            self.list.addItem(it)
        lay.addWidget(self.list)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        if ok_text:
            btns.button(QDialogButtonBox.Ok).setText(ok_text)
        if cancel_text:
            btns.button(QDialogButtonBox.Cancel).setText(cancel_text)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def chosen(self):
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.Checked]


class MainWindow(QMainWindow):
    def __init__(self, settings_path=None):
        super().__init__()
        self.settings_path = settings_path
        self.cfg, self.ui = load_settings(settings_path)
        self._restoring = False
        self.last_run = None
        self.history = HistoryStore(os.path.dirname(settings_path or default_settings_path()),
                                    self.cfg.history_max_entries, self.cfg.history_max_days,
                                    self.ui.get("history_mask", True))
        self.cfg.print_code = False
        self.bd = None
        self.df = None
        self.kinds = {}
        self.info = None
        self.method = None
        self.worker = None
        self.load_started = 0.0
        self.setWindowTitle("BLUEDA")
        self.resize(1440, 900)

        root = QWidget()
        root.setObjectName("Root")
        rl = QVBoxLayout(root)
        rl.setContentsMargins(0, 0, 0, 0)
        rl.setSpacing(0)
        rl.addWidget(self._header())
        self.stack = QStackedWidget()
        self.start = StartPage()
        self.main = MainPage()
        self.stack.addWidget(self.start)
        self.stack.addWidget(self.main)
        rl.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self.start.set_recent(self.ui.get("recent_files", []))
        self.start.fileChosen.connect(self.open_file)
        self.start.cancelRequested.connect(self._cancel_load)
        self.start.startRequested.connect(self.start_analysis)
        m = self.main
        m.columns.selectionChanged.connect(self._scope_changed)
        m.columns.typeChangeRequested.connect(self._change_type)
        m.filters.changed.connect(self._filters_changed)
        m.session.historyClicked.connect(self.restore_history)
        m.session.historyClearRequested.connect(self.clear_history)
        m.menu.methodChosen.connect(self.choose_method)
        m.bar.paramsChanged.connect(self._precheck)
        m.bar.runRequested.connect(self.run_analysis)
        m.bar.switchRequested.connect(self.choose_method)
        m.session.resultClicked.connect(self._reopen)
        m.session.command.connect(self._command)
        self.apply_theme()
        self.refresh_history_panel()

    def _running(self):
        main = self.worker if (self.worker is not None and self.worker.isRunning()) else None
        bg = [w for w in getattr(self, "_bg_workers", []) if w.isRunning()]
        return main, bg

    def closeEvent(self, event):
        """작업 중에 창을 닫아도 멈추거나 강제 종료되지 않게 합니다.
        - 읽기: 취소하고 닫음 (읽기는 중간에 멈출 수 있음)
        - 분석: 중간에 멈출 수 없으므로 [끝나면 닫기] / [계속 작업]을 묻고, 끝나면 닫음
        - 이슈 점검만: 묻지 않고 창을 숨긴 뒤, 끝나는 대로(몇 초) 닫음
        """
        main, bg = self._running()
        if main is None and not bg:
            super().closeEvent(event)
            return
        event.ignore()                                  # 지금 바로 닫지 않음 (스레드가 끝난 뒤 닫음)
        if main is not None and getattr(self, "_loading", False):
            main.cancel()                               # 읽기는 취소 가능
        elif main is not None and not getattr(self, "_close_pending", False):
            box = QMessageBox(self)
            box.setWindowTitle("분석 진행 중")
            box.setText("분석이 아직 진행 중입니다. 중간에 멈출 수 없어 끝난 뒤에 닫을 수 있습니다.")
            later = box.addButton("끝나면 닫기", QMessageBox.AcceptRole)
            box.addButton("계속 작업", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() is not later:
                return
        self._close_pending = True
        self.hide()                                     # 사용자에게는 바로 닫힌 것처럼
        for w in ([main] if main is not None else []) + bg:
            w.finished.connect(self._close_when_idle)
        self._close_when_idle()

    def _close_when_idle(self):
        if not getattr(self, "_close_pending", False):
            return
        main, bg = self._running()
        if main is None and not bg:
            self._close_pending = False
            self.close()
        else:                                           # 끝남 신호 직후에도 잠깐 실행 중으로 보일 수 있어 다시 확인
            QTimer.singleShot(100, self._close_when_idle)

    # ------------------------------------------------------------------ 조회 히스토리
    def _file_name(self):
        return os.path.basename(self.info.path) if self.info else None

    def record(self, kind, text, rows=None, state=None):
        """확정한 동작 한 줄 기록. 복원 중이거나 설정에서 끈 경우에는 남기지 않음."""
        if self._restoring or not self.ui.get("history_enabled", True):
            return
        try:
            self.history.add(kind, text, rows=rows, file=self._file_name(), state=state)
        except OSError as e:
            self.log("FAIL", f"히스토리를 저장하지 못했습니다: {e}")
            return
        self.refresh_history_panel()

    def _state(self, method=None, params=None):
        value_params = ()
        if method in M.BY_KEY:
            value_params = tuple(p.name for p in M.BY_KEY[method].params if p.kind == M.VALUE)
        f = self.main.filters
        return self.history.state(f.filters, f.query, self.main.columns.selected(), method, params, value_params)

    def refresh_history_panel(self):
        rows = [(i, *describe_entry(e)) for i, e in enumerate(self.history.entries)]
        size = self.history.size_bytes()
        info = f"{len(rows)}건 · {size / 1024:,.0f}KB" if rows else ""
        if self.history.mask:
            info += ("  · " if info else "") + "값 가림"
        self.main.session.set_history(rows, info)

    def restore_history(self, idx):
        """기록을 누르면 그때의 필터·열·분석 설정으로 되돌립니다. 실행은 사용자가 직접 누릅니다."""
        if not (0 <= idx < len(self.history.entries)):
            return
        e = self.history.entries[idx]
        st = e.get("state")
        if self.df is None:
            self.log("INFO", "파일을 연 뒤에 기록을 되돌릴 수 있습니다.")
            return
        if not st:
            self.log("INFO", f"되돌릴 조건이 없는 기록입니다: {e.get('text', '')}")
            return
        if not same_file_name(e, self._file_name()):
            self.log("INFO", f"다른 파일({e.get('file')})의 기록입니다. 그 파일을 연 뒤 다시 누르세요.")
            return
        filters, problems = self.history.unpack_filters(st.get("filters", []), self.df)
        self._restoring = True
        try:
            self.main.filters.set_state(filters, st.get("query", ""))
            cols = [c for c in st.get("columns", []) if c in self.df.columns]
            if cols:
                self.main.columns.set_selected(cols)
            method = st.get("method")
            if method in M.BY_KEY:
                self.choose_method(method)
                params = self.history.unpack_params(st.get("params"), self.df, {})
                self.main.bar.set_params(params)
        finally:
            self._restoring = False
        self._scope_changed()
        self.log("INFO", f"기록 되돌림: {e.get('text', '')}" + ("  (실행 버튼을 누르면 다시 계산합니다)" if st.get("method") else ""))
        for p in problems:
            self.log("INFO", "  " + p)
        if st.get("query_hidden"):
            self.log("INFO", "  직접 입력 조건은 값 가림 모드라 저장하지 않아 되돌리지 않았습니다.")

    def clear_history(self):
        if QMessageBox.question(self, "히스토리 삭제", "조회 히스토리를 모두 지울까요? 되돌릴 수 없습니다.") \
                != QMessageBox.Yes:
            return
        self.history.clear()
        self.refresh_history_panel()
        self.log("INFO", "조회 히스토리를 모두 지웠습니다.")

    def _filters_changed(self):
        self._scope_changed()
        if self.df is None:
            return
        f = self.main.filters
        parts = [self.history.filter_text(x) for x in f.filters]
        if f.query:
            parts.append("직접 입력 조건" if self.history.mask else f.query)
        try:
            n = self.current_scope().count_rows(self.df)
        except Exception:
            n = None
        self.record("filter", " · ".join(parts) or "조건 모두 해제", n, self._state())

    # ------------------------------------------------------------------ 상단 바
    def _header(self):
        h = QFrame()
        h.setObjectName("Header")
        h.setFixedHeight(52)
        lay = QHBoxLayout(h)
        lay.setContentsMargins(20, 0, 20, 0)
        lay.setSpacing(16)
        lay.addWidget(label("BLUEDA", "brand"))
        self.file_label = label("", "muted")
        lay.addWidget(self.file_label)
        # 파일 이슈 알림: 파일을 열면 뒤에서 전처리 점검을 돌려 이슈가 있을 때만 나타남
        self.issue_btn = button("", "issue")
        self.issue_btn.setToolTip("이 파일에서 찾은 이슈 보기")
        self.issue_btn.clicked.connect(self.show_issues)
        self.issue_btn.hide()
        lay.addWidget(self.issue_btn)
        lay.addStretch(1)
        lay.addWidget(label("오프라인", "sub"))
        self.theme_btn = button("", None)
        self.theme_btn.setFixedWidth(36)
        self.theme_btn.clicked.connect(self.toggle_theme)
        lay.addWidget(self.theme_btn)
        self.settings_btn = button("⚙", None)
        self.settings_btn.setFixedWidth(36)
        self.settings_btn.setToolTip("설정")
        self.settings_btn.clicked.connect(self.open_settings)
        lay.addWidget(self.settings_btn)
        self.export_btn = button("내보내기", None)
        menu = QMenu(self.export_btn)
        menu.addAction("Excel (.xlsx)").triggered.connect(self.export_excel)
        menu.addAction("CSV (표마다 파일)").triggered.connect(self.export_csv)
        menu.addAction("분석 로그 저장 (.md · .py · .json)").triggered.connect(self.save_logs)
        self.export_btn.setMenu(menu)
        lay.addWidget(self.export_btn)
        self.report_btn = button("보고서", "primary")
        self.report_btn.clicked.connect(self.report)
        lay.addWidget(self.report_btn)
        self._header_enabled(False)
        return h

    def _header_enabled(self, on):
        for b in (self.export_btn, self.report_btn):
            b.setEnabled(on)

    # ------------------------------------------------------------------ 화면 모드·설정
    def apply_theme(self):
        dark = self.ui.get("theme") == "dark"
        QApplication.instance().setStyleSheet(theme.stylesheet(dark))
        self.theme_btn.setText("☀" if dark else "☾")
        self.theme_btn.setToolTip("라이트 모드로" if dark else "다크 모드로")

    def toggle_theme(self):
        self.ui["theme"] = "light" if self.ui.get("theme") == "dark" else "dark"
        self.apply_theme()
        self._save_settings()

    def open_settings(self):
        dlg = SettingsDialog(self.cfg, self.ui, self)
        dlg.move(self.geometry().right() - dlg.sizeHint().width() - 24, self.geometry().top() + 70)
        if dlg.exec():
            dlg.apply()
            charts.SAMPLE_N = self.cfg.chart_sample_size
            if self.bd:
                self.bd.config = self.cfg
            self.apply_theme()
            self._save_settings()
            self.refresh_issues()                       # IQR 배수 등이 바뀌면 이슈도 다시 계산
            self.history.mask = self.ui.get("history_mask", True)
            self.history.max_entries = self.cfg.history_max_entries
            self.history.max_days = self.cfg.history_max_days
            self.refresh_history_panel()
            self.log("INFO", "설정 저장: 유의수준 {a}, IQR×{k}, |z|>{z}, 차트 표본 {n:,}행".format(
                a=self.cfg.alpha, k=self.cfg.outlier_iqr_k, z=self.cfg.z_threshold, n=self.cfg.chart_sample_size))

    def _save_settings(self):
        try:
            save_settings(self.cfg, self.ui, self.settings_path)
        except OSError as e:
            self.log("FAIL", f"설정을 저장하지 못했습니다: {e}")

    # ------------------------------------------------------------------ 파일 불러오기
    def open_file(self, path):
        if self.worker is not None and self.worker.isRunning():
            # 읽기·분석 스레드가 도는 중에 새 작업을 시작하면 실행 중인 스레드를 잃어 강제 종료될 수 있음
            msg = "진행 중인 작업이 끝난 뒤에 다른 파일을 열어 주세요."
            self.log("INFO", msg)
            if self.stack.currentWidget() is self.start:      # 시작 화면에서는 결과 세션이 안 보이므로
                self.start.flash(msg)
            return
        self._invalidate_issues()                              # 이전 파일의 이슈 점검 결과는 버림
        for name in ("date_dialog", "issue_popup"):            # 이전 파일에 대해 띄운 창은 닫음
            dlg = getattr(self, name, None)
            if dlg is not None and dlg.isVisible():
                if name == "date_dialog":
                    dlg.finished.disconnect()                  # 닫으면서 '건너뜀'이 기록되지 않게
                dlg.close()
            setattr(self, name, None)
        try:
            info = detect_file(path)
        except OSError as e:
            self.start.show_error(f"파일을 열 수 없습니다: {e}")
            return
        self.start.show_detected(info)
        if not info.supported:
            self.start.show_error(info.detail)
            return
        usecols = None
        est = estimate_memory(path, info) if info.file_type == "csv" else None
        ram = total_memory()
        if est and ram and est > ram / 2:
            box = QMessageBox(self)
            box.setWindowTitle("메모리 확인")
            box.setText(f"이 파일을 읽으려면 메모리가 약 {est / 2**30:,.1f}GB 필요합니다 "
                        f"(이 PC {ram / 2**30:,.0f}GB).\n일부 열만 읽을까요?")
            part = box.addButton("일부 열만 읽기", QMessageBox.AcceptRole)
            whole = box.addButton("그대로 읽기", QMessageBox.DestructiveRole)
            box.addButton("취소", QMessageBox.RejectRole)
            box.exec()
            if box.clickedButton() == part:
                import pandas as pd
                cols = list(pd.read_csv(path, encoding=info.encoding, sep=info.delimiter, nrows=0).columns)
                chooser = ColumnChooser(cols, self)
                if not chooser.exec() or not chooser.chosen():
                    self.start.set_loading(False, "취소했습니다.")
                    return
                usecols = chooser.chosen()
            elif box.clickedButton() != whole:
                self.start.set_loading(False, "취소했습니다.")
                return
        est_text = f" · 예상 메모리 약 {est / 2**20:,.0f}MB" if est else ""
        self.start.set_loading(True, "읽는 중 0%" + est_text)
        w = Worker(None)

        def job():
            info2, df, code = load_file(path, progress=w.progress.emit, cancelled=w.is_cancelled,
                                        usecols=usecols, optimize=True)
            kinds = M.column_kinds(df, max_categories=self.cfg.category_max_unique)
            return info2, df, code, kinds
        w._fn = job
        self._loading = True
        w.finished.connect(lambda: setattr(self, "_loading", False))
        self.load_started = time.time()
        w.progress.connect(self._load_progress)
        w.done.connect(lambda res: self._loaded(path, res))
        w.failed.connect(self._load_failed)
        self.worker = w
        w.start()

    def _load_progress(self, p):
        spent = time.time() - self.load_started
        left = spent / p - spent if p > 0.02 else None
        self.start.set_progress(p, f"읽는 중 {p:.0%}" + (f" · 약 {left:,.0f}초 남음" if left else ""))

    def _cancel_load(self):
        if self.worker and self.worker.isRunning():
            self.worker.cancel()

    def _load_failed(self, msg):
        if "LoadCancelled" in msg:
            self.start.show_error("읽기를 취소했습니다.")
        else:
            self.start.show_error(f"읽기 실패: {msg}")

    def _loaded(self, path, res):
        info, df, code, kinds = res
        self.info, self.df, self.kinds, self.load_code = info, df, kinds, code
        spent = time.time() - self.load_started
        self.load_detail = f"{spent:,.1f}초 · {info.detail}" if info.detail else f"{spent:,.1f}초"
        self.start.show_loaded(df, kinds, "읽기 완료 · " + self.load_detail)
        recent = [path] + [p for p in self.ui.get("recent_files", []) if p != path]
        self.ui["recent_files"] = recent[:10]
        self._save_settings()

    # ------------------------------------------------------------------ 분석 화면 시작
    def start_analysis(self):
        if self.df is None:
            return
        self.bd = Blueda(self.df, config=self.cfg, data_path=self.info.path)
        self.bd.file_info = self.info
        self.bd.log.log("데이터 불러오기", self.load_code, f"{self.df.shape}", self.info.summary())
        self.record("file", f"{self._file_name()} 열기 · {self.df.shape[1]}열", len(self.df))
        m = self.main
        default = [c for c, k in self.kinds.items() if k in ("수치형", "범주형")]
        m.filters.set_data(self.df, self.kinds, self.cfg.dropdown_max_values)
        m.columns.set_columns(self.df, self.kinds, default)   # 선택 변경 신호로 행 수·데이터 탭이 한 번 갱신됨
        self.file_label.setText(f"{os.path.basename(self.info.path)} · {len(self.df):,}행 × {self.df.shape[1]}열 · "
                                f"메모리 {self.df.memory_usage(deep=True).sum() / 2**20:,.0f}MB")
        self._header_enabled(True)
        m.session.list.clear()
        self.log("SUCCESS", f"불러오기  {os.path.basename(self.info.path)}  {len(self.df):,}행 × {self.df.shape[1]}열  ({self.load_detail})")
        self.stack.setCurrentWidget(m)
        self.choose_method("describe")
        self.offer_date_conversion()
        self.refresh_issues()

    # ------------------------------------------------------------------ [!] 파일 이슈
    def refresh_issues(self):
        """전처리 점검을 뒤에서 돌려 이슈 버튼을 갱신합니다 (화면이 멈추지 않게 별도 스레드)."""
        if self.df is None:
            return
        self.issues = []
        self._issue_gen = getattr(self, "_issue_gen", 0) + 1
        gen = self._issue_gen
        w = Worker(collect_issues, self.df, self.cfg.outlier_iqr_k, self.cfg.missing_warn_ratio)
        w.done.connect(lambda issues, g=gen: self._issues_ready(issues, g))
        w.failed.connect(lambda msg: self.log("FAIL", f"이슈 점검 실패: {msg}"))
        # 이전 점검이 아직 돌고 있을 수 있으므로, 끝날 때까지 모든 스레드의 참조를 잡아 둡니다.
        # (참조를 놓치면 실행 중인 스레드가 지워지면서 프로그램이 강제 종료됨)
        self._bg_workers = [x for x in getattr(self, "_bg_workers", []) if x.isRunning()] + [w]
        self.issue_worker = w
        w.start()

    def _invalidate_issues(self):
        """새 파일을 열면 이슈 버튼을 지우고, 아직 도는 이전 파일 점검의 결과는 도착해도 버리게 합니다."""
        self._issue_gen = getattr(self, "_issue_gen", 0) + 1
        self.issues = []
        self.issue_btn.hide()

    def _issues_ready(self, issues, gen=None):
        if gen is None or gen != self._issue_gen:
            return                                 # 더 새 점검이 시작됐으면 이전 결과는 버림
        if not shiboken_valid(self.issue_btn):
            return                                 # 창이 이미 지워진 뒤 도착한 결과
        self.issues = issues
        text, level = summary(issues)
        self.issue_btn.setVisible(bool(text))
        self.issue_btn.setText(text)
        self.issue_btn.setProperty("level", "need" if level == NEED else "review")
        repolish(self.issue_btn)

    def show_issues(self):
        issues = getattr(self, "issues", [])
        pop = Popup(460, self)
        n_need = sum(i.level == NEED for i in issues)
        head = f"이 파일의 이슈 {len(issues)}개"
        if n_need:
            head += f" (확인 필요 {n_need}개)"
        pop.box.addWidget(label(head, None))
        for i in issues[:12]:
            row = QHBoxLayout()
            row.setSpacing(8)
            tag = label(i.level, "issue_need" if i.level == NEED else "issue_review")
            tag.setFixedWidth(64)
            row.addWidget(tag, 0, Qt.AlignTop)
            text = label(i.text, None, True)
            text.setFixedWidth(290)              # 너비를 정해야 줄바꿈 높이가 맞게 계산되어 잘리지 않음
            row.addWidget(text, 1)
            act = button("날짜로 바꾸기" if i.action == "dates" else "점검 보기", "link")
            act.setFixedWidth(84)
            act.clicked.connect(lambda _=False, a=i.action: (pop.close(), self._issue_action(a)))
            row.addWidget(act, 0, Qt.AlignTop)
            pop.box.addLayout(row)
        if len(issues) > 12:
            pop.box.addWidget(label(f"외 {len(issues) - 12}개는 전처리 점검 결과에서 볼 수 있습니다.", "sub"))
        foot = label("이슈가 있어도 분석은 할 수 있습니다. 결과를 해석할 때 참고하세요.", "sub", True)
        foot.setFixedWidth(440)
        pop.box.addWidget(foot)
        self.issue_popup = pop
        pop.show_below(self.issue_btn)

    def _issue_action(self, action):
        if action == "dates":
            self.offer_date_conversion(announce_none=True)
        else:
            self.choose_method("check")
            self.run_analysis("check", {})

    # ------------------------------------------------------------------ 날짜형 변환 (사용자 선택)
    def offer_date_conversion(self, announce_none=False):
        """날짜 문자열 열이 있으면 바꿀 열을 고르는 창을 띄웁니다. 창은 화면을 막지 않습니다(open)."""
        if self.bd is None:
            return
        cands = self.bd.date_candidates()
        if not cands:
            if announce_none:
                self.log("INFO", "날짜 문자열로 보이는 열이 없습니다.")
            return
        dlg = ColumnChooser(
            cands, self, title="날짜형으로 바꾸기",
            message="아래 열은 날짜처럼 보이지만 글자로 저장돼 있습니다.\n"
                    "날짜형으로 바꾸면 기간 필터와 월별 집계를 쓸 수 있습니다.\n"
                    "코드(예: 20230103이 주문번호)라면 체크를 빼세요.",
            ok_text="바꾸기", cancel_text="그대로 두기")
        dlg.finished.connect(lambda code: self._dates_chosen(dlg, code))
        self.date_dialog = dlg
        dlg.open()

    def _dates_chosen(self, dlg, code):
        chosen = dlg.chosen() if code == QDialog.Accepted else []
        if chosen:
            main, bg = self._running()
            if main is not None:
                # 분석 스레드가 같은 데이터를 읽는 중에 열을 바꾸면 결과가 섞이거나 오류가 날 수 있음
                self.log("INFO", "분석이 끝난 뒤에 날짜를 바꿀 수 있습니다. 끝나면 'dates' 명령으로 다시 여세요.")
                return
            if bg:                                        # 이슈 점검(몇 초)은 끝나기를 기다렸다가 바꿈
                bg[0].finished.connect(lambda d=dlg, c=code: QTimer.singleShot(50, lambda: self._dates_chosen(d, c)))
                return
        if not chosen:
            self.log("INFO", "날짜형 변환을 건너뛰었습니다. 나중에 'dates' 명령으로 다시 열 수 있습니다.")
            return
        r = self.bd.convert_dates(chosen)
        self._log_result(r, len(self.bd.results) - 1)
        self.main.tabs.show_result(r)
        if r.status == "SUCCESS":
            for c in chosen:
                self.kinds[c] = "날짜"
            self.main.filters.set_data(self.df, self.kinds, self.cfg.dropdown_max_values)
            self._refresh_data_tab()
            self.refresh_issues()                       # 날짜를 바꿨으니 이슈 다시 계산
            self.record("dates", "날짜형 변환 · " + ", ".join(map(str, chosen)))

    # ------------------------------------------------------------------ 범위·메뉴·점검
    def current_scope(self, for_method=None, params=None):
        m = self.main
        selected = m.columns.selected()
        cols = selected or [c for c, k in self.kinds.items() if k not in ("텍스트",)]
        if for_method is not None and getattr(for_method, "key", None) in ALL_COLUMN_METHODS:
            # 전처리 점검·변수 종류는 고른 열과 상관없이 모든 열을 봅니다.
            # 일부 열만 보면 ID 열이 빠져 다른 행이 중복처럼 보이는 등 판단이 틀어지기 때문입니다.
            cols = list(self.df.columns)
        elif for_method is not None and for_method.params:
            cols = m.bar.needed_columns() or cols
        return AnalysisScope(columns=list(cols), filters=list(m.filters.filters), query=m.filters.query)

    def _scope_changed(self, *_):
        if self.df is None:
            return
        try:
            n = self.current_scope().count_rows(self.df)
        except Exception as e:  # 직접 입력 조건 문법 오류 등
            self.log("FAIL", f"행 조건 오류: {e}")
            m = self.main.filters
            m.query = ""
            n = AnalysisScope(filters=list(m.filters)).count_rows(self.df)
        self.main.filters.set_row_count(n, len(self.df))
        self._precheck()
        self._refresh_data_tab()

    def _refresh_data_tab(self):
        try:
            scope = self.current_scope()
            mask, _ = scope.row_mask(self.df)
            cols = scope.columns or list(self.df.columns)
            self.main.tabs.set_data(self.df.loc[mask.to_numpy(dtype=bool), cols])
        except Exception:
            pass

    def choose_method(self, key):
        method = M.BY_KEY.get(key)
        if method is None:
            return
        self.main.menu.select(key)
        if not method.available:
            r = self.bd.request(key, user_text=method.label) if self.bd else None
            if r is not None:
                self._show_result(r)
            return
        self.method = method
        self.main.bar.set_method(method, self.kinds, self.df)
        self._precheck()

    def _precheck(self):
        if self.df is None or self.method is None:
            return
        bar = self.main.bar
        params = bar.params()
        try:
            scope = self.current_scope(self.method, params)
            mask, _ = scope.row_mask(self.df)
            cols = [c for c in scope.columns if c in self.df.columns]
            sub = self.df.loc[mask.to_numpy(dtype=bool), cols]
            check = M.precheck(self.method.key, params, sub, self.kinds)
        except Exception as e:
            check = M.Check(False, f"조건을 확인할 수 없습니다: {e}")
        bar.set_check(check, running=bool(self.worker and self.worker.isRunning()))

    def _change_type(self, column, kind):
        if not self.bd:
            return
        self.bd.set_variable_type(column, kind)
        self.kinds[column] = kind
        sel = self.main.columns.selected()
        self.main.columns.set_columns(self.df, self.kinds, sel)
        self.main.filters.kinds = self.kinds
        if self.method:
            self.main.bar.set_method(self.method, self.kinds, self.df)
        self.log("INFO", f"변수 종류 변경  {column} → {kind}")

    # ------------------------------------------------------------------ 실행
    def run_analysis(self, key, params):
        if self.worker and self.worker.isRunning():
            return
        self.last_run = (key, dict(params))
        method = M.BY_KEY[key]
        scope = self.current_scope(method, params)
        self.bd.scope = scope
        self.main.bar.run_btn.setEnabled(False)
        self.log("RUN", f"{method.label} 실행 중 · {scope.describe()}")
        before = len(self.bd.results)
        w = Worker(lambda: M.run(self.bd, key, params))
        w.done.connect(lambda _out: self._finished(before))
        w.failed.connect(lambda msg: self._failed(method, msg))
        self.worker = w
        w.start()

    def _finished(self, before):
        new = self.bd.results[before:]
        for i, r in enumerate(new, start=before):
            self._log_result(r, i)
        if new and self.last_run:
            key, params = self.last_run
            r = new[-1]
            n = self.current_scope().count_rows(self.df) if self.df is not None else None
            self.record("analysis", f"{r.name} [{r.status}] {r.message}"[:140], n, self._state(key, params))
        if new:
            self.main.tabs.show_results(new)
        self._precheck()

    def _failed(self, method, msg):
        r = AnalysisResult(method.label, "FAIL", msg)
        self.bd.results.append(r)
        self._log_result(r, len(self.bd.results) - 1)
        self.main.tabs.show_result(r)
        self._precheck()

    def _show_result(self, r):
        idx = self.bd.results.index(r) if r in self.bd.results else None
        self._log_result(r, idx)
        self.main.tabs.show_result(r)

    def _log_result(self, r, idx):
        short = r.message if len(r.message) <= 120 else r.message[:117] + "…"
        self.main.session.add(r.status, f"{r.name}  {short}", r.created_at, idx)

    def _reopen(self, idx):
        if self.bd and 0 <= idx < len(self.bd.results):
            self.main.tabs.show_result(self.bd.results[idx])

    def log(self, status, text):
        self.main.session.add(status, text, datetime.now().strftime("%H:%M:%S"))

    # ------------------------------------------------------------------ 명령
    def _command(self, text):
        t = text.strip()
        self.main.session.add("INFO", f"> {t}", datetime.now().strftime("%H:%M:%S"))
        low = t.lower()
        if low.split(" ")[0] in {c.split(" ")[0] for c, _ in HELP} and low != "history":
            self.record("command", t)
        if low == "history":
            self.main.session.show_page(1)
        elif low == "help":
            for cmd, desc in HELP:
                self.log("INFO", f"{cmd:<26} {desc}")
            self.log("INFO", "분석 명령(예: 성별 처리일수 t검정)은 5단계에서 지원합니다.")
        elif low == "clear":
            self.main.session.list.clear()
        elif low in ("theme dark", "theme light"):
            self.ui["theme"] = low.split()[1]
            self.apply_theme()
            self._save_settings()
        elif low == "dates" and self.bd is not None:
            self.offer_date_conversion(announce_none=True)
        elif low == "rows" and self.df is not None:
            self.log("INFO", f"조건에 맞는 행: {self.current_scope().count_rows(self.df):,} / {len(self.df):,}")
        elif low == "show" and self.bd and self.bd.results:
            r = self.bd.results[-1]
            self.log("INFO", f"[{r.name}] {r.message}")
            for k, v in r.metrics.items():
                self.log("INFO", f"  {k}: {v}")
        else:
            self.log("UNSUPPORTED", f"'{t}' — 분석 명령 해석은 5단계에서 지원합니다. help로 지금 쓸 수 있는 명령을 보세요.")

    # ------------------------------------------------------------------ 내보내기
    def _need_results(self):
        if not self.bd or not self.bd.results:
            self.log("FAIL", "내보낼 분석 결과가 없습니다. 먼저 분석을 실행하세요.")
            return False
        return True

    def export_excel(self):
        if not self._need_results():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Excel로 저장", "BLUEDA_결과.xlsx", "Excel (*.xlsx)")
        if path:
            try:
                self.bd.export_excel(path)
                self.log("SUCCESS", f"Excel 저장  {path}")
                self.record("export", f"Excel 저장 · {os.path.basename(path)}")
            except Exception as e:
                self.log("FAIL", f"Excel 저장 실패: {e}")

    def export_csv(self):
        if not self._need_results():
            return
        d = QFileDialog.getExistingDirectory(self, "CSV를 저장할 폴더")
        if d:
            paths = self.bd.export_csv(d)
            self.log("SUCCESS", f"CSV {len(paths)}개 저장  {d}")
            self.record("export", f"CSV {len(paths)}개 저장")

    def save_logs(self):
        if not self._need_results():
            return
        paths = self.bd.save()
        self.log("SUCCESS", "로그 저장  " + " · ".join(os.path.basename(p) for p in paths.values()))
        self.record("export", "분석 로그 저장")

    def report(self):
        self.log("UNSUPPORTED", "보고서(Word·PDF) 만들기는 4단계에서 지원합니다. 지금은 내보내기 → Excel을 쓰세요.")


def main(argv=None):
    os.environ.setdefault("QT_ENABLE_HIGHDPI_SCALING", "1")
    app = QApplication.instance() or QApplication(argv if argv is not None else sys.argv)
    f = QFont()
    f.setFamilies(theme.FONT_FAMILIES)
    f.setPointSize(10)
    app.setFont(f)
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
