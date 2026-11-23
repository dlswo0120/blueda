"""분석 범위·메뉴·실행 전 점검·실행: 왼쪽 열 선택과 필터로 범위를 만들고, 고른 분석을 작업 스레드에서 실행

MainWindow가 이 클래스를 함께 상속합니다 (app.py 참고). self는 MainWindow입니다.
"""

from datetime import datetime


from ... import methods as M
from ...result import AnalysisResult
from ...scope import AnalysisScope
from ..widgets import Worker

# 열 선택과 상관없이 모든 열로 실행하는 분석
# (전처리 점검·변수 종류는 일부 열만 보면 판단이 틀어짐: 예) ID 열이 빠지면 다른 행이 중복처럼 보임)
ALL_COLUMN_METHODS = ("check", "variable_types")


class AnalysisMixin:
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

