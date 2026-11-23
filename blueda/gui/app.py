"""BLUEDA 프로그램 창. 실행: python -m blueda

MainWindow는 역할별 믹스인(gui/window/)을 함께 상속합니다. 고칠 기능에 따라 해당 파일을 여세요.

| 파일                 | 하는 일 |
|----------------------|---------|
| app.py (이 파일)     | 창 만들기·화면 배치·신호 연결, 창 닫기, 상단 바, 화면 모드·설정 |
| window/loading.py    | 파일 열기·읽기·시작 화면 → 분석 화면 시작 |
| window/analysis.py   | 분석 범위(열·필터), 메뉴 선택, 실행 전 점검, 실행·결과 표시 |
| window/issues.py     | [!] 이슈 버튼 (뒤에서 전처리 점검) |
| window/dates.py      | 날짜형 변환 창 |
| window/history.py    | 조회 히스토리 기록·되돌리기 |
| window/commands.py   | 결과 세션 명령, 내보내기 |
| dialogs.py           | 설정 창, 열 고르기 창 |
"""

import os
import sys

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QMainWindow, QMenu, QMessageBox, QStackedWidget, QVBoxLayout, QWidget,
)

from .. import charts
from ..settings import load_settings, save_settings
from . import theme
from .pages import MainPage, StartPage
from ..history import HistoryStore
from ..settings import settings_path as default_settings_path
from .widgets import button, label
from .dialogs import ColumnChooser, SettingsDialog  # noqa: F401  (예전 경로 A.SettingsDialog 유지)
from .window.analysis import ALL_COLUMN_METHODS, AnalysisMixin  # noqa: F401
from .window.commands import HELP, CommandsMixin  # noqa: F401
from .window.dates import DatesMixin
from .window.history import HistoryMixin
from .window.issues import IssuesMixin
from .window.loading import LoadingMixin

__all__ = ["MainWindow", "SettingsDialog", "ColumnChooser", "HELP", "ALL_COLUMN_METHODS", "main"]


class MainWindow(HistoryMixin, LoadingMixin, IssuesMixin, DatesMixin, AnalysisMixin, CommandsMixin, QMainWindow):
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
