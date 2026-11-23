"""파일 불러오기: 형식 판별 → 메모리 확인 → 작업 스레드로 읽기 → 시작 화면 표시 → 분석 화면 시작

MainWindow가 이 클래스를 함께 상속합니다 (app.py 참고). self는 MainWindow입니다.
"""

import os
import time

from PySide6.QtWidgets import (
    QMessageBox,
)

from ... import methods as M
from ...core import Blueda
from ...loader import detect_file, estimate_memory, load_file, total_memory
from ..dialogs import ColumnChooser
from ..widgets import Worker


class LoadingMixin:
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

