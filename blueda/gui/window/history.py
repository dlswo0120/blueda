"""조회 히스토리: 확정한 동작 기록, 히스토리 탭 갱신, 기록 눌러 되돌리기, 전체 삭제

MainWindow가 이 클래스를 함께 상속합니다 (app.py 참고). self는 MainWindow입니다.
"""

import os

from PySide6.QtWidgets import (
    QMessageBox,
)

from ... import methods as M
from ...history import describe_entry, same_file_name


class HistoryMixin:
    # ------------------------------------------------------------------ 조회 히스토리
    """조회 히스토리: 확정한 동작을 기록하고(record), 히스토리 탭을 갱신하고, 기록을 눌러 되돌립니다."""
    def _file_name(self):
        """지금 연 파일 이름 (경로 없이). 다른 파일의 기록인지 비교할 때 씁니다."""
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
        """되돌리기에 필요한 상태(필터·직접 입력 조건·고른 열·분석·입력값)를 만듭니다. 값 가림은 HistoryStore가 합니다."""
        value_params = ()
        if method in M.BY_KEY:
            value_params = tuple(p.name for p in M.BY_KEY[method].params if p.kind == M.VALUE)
        f = self.main.filters
        return self.history.state(f.filters, f.query, self.main.columns.selected(), method, params, value_params)

    def refresh_history_panel(self):
        """히스토리 탭 목록과 '건수 · 용량 · 값 가림' 표시를 갱신합니다."""
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
        """확인 창을 띄운 뒤 히스토리를 모두 지웁니다."""
        if QMessageBox.question(self, "히스토리 삭제", "조회 히스토리를 모두 지울까요? 되돌릴 수 없습니다.") \
                != QMessageBox.Yes:
            return
        self.history.clear()
        self.refresh_history_panel()
        self.log("INFO", "조회 히스토리를 모두 지웠습니다.")

    def _filters_changed(self):
        """필터가 바뀌면 남는 행 수를 다시 세고, 조건 문구(값은 가림)와 함께 기록합니다."""
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

