"""BLUEDA 프로그램 창. 실행: python -m blueda"""

import os
import sys
import time
from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLineEdit,
    QListWidget, QListWidgetItem, QMainWindow, QMenu, QMessageBox, QRadioButton, QStackedWidget, QVBoxLayout,
    QWidget,
)

from .. import charts, methods as M
from ..core import Blueda
from ..loader import LoadCancelled, detect_file, estimate_memory, load_file, total_memory
from ..result import AnalysisResult
from ..scope import AnalysisScope
from ..settings import EDITABLE, load_settings, save_settings
from . import theme
from .pages import MainPage, StartPage
from .widgets import Worker, button, label

HELP = [
    ("help", "명령 목록"),
    ("show", "마지막 결과의 지표를 여기에 출력"),
    ("clear", "결과 세션 비우기"),
    ("theme dark / theme light", "화면 모드 바꾸기"),
    ("rows", "지금 조건에 맞는 행 수"),
    ("dates", "날짜 문자열 열을 날짜형으로 바꾸는 창 열기"),
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
        lay.addLayout(form)
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
        m.filters.changed.connect(self._scope_changed)
        m.menu.methodChosen.connect(self.choose_method)
        m.bar.paramsChanged.connect(self._precheck)
        m.bar.runRequested.connect(self.run_analysis)
        m.bar.switchRequested.connect(self.choose_method)
        m.session.resultClicked.connect(self._reopen)
        m.session.command.connect(self._command)
        self.apply_theme()

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
            self.log("INFO", "설정 저장: 유의수준 {a}, IQR×{k}, |z|>{z}, 차트 표본 {n:,}행".format(
                a=self.cfg.alpha, k=self.cfg.outlier_iqr_k, z=self.cfg.z_threshold, n=self.cfg.chart_sample_size))

    def _save_settings(self):
        try:
            save_settings(self.cfg, self.ui, self.settings_path)
        except OSError as e:
            self.log("FAIL", f"설정을 저장하지 못했습니다: {e}")

    # ------------------------------------------------------------------ 파일 불러오기
    def open_file(self, path):
        if self.worker and self.worker.isRunning():
            return
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
        if low == "help":
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
            except Exception as e:
                self.log("FAIL", f"Excel 저장 실패: {e}")

    def export_csv(self):
        if not self._need_results():
            return
        d = QFileDialog.getExistingDirectory(self, "CSV를 저장할 폴더")
        if d:
            paths = self.bd.export_csv(d)
            self.log("SUCCESS", f"CSV {len(paths)}개 저장  {d}")

    def save_logs(self):
        if not self._need_results():
            return
        paths = self.bd.save()
        self.log("SUCCESS", "로그 저장  " + " · ".join(os.path.basename(p) for p in paths.values()))

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
