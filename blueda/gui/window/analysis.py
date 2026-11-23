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
    """분석 범위(열·필터)를 만들고, 메뉴 선택·실행 전 점검·실행·결과 표시를 처리합니다."""
    def current_scope(self, for_method=None, params=None):
        """지금 화면 상태로 분석 범위(AnalysisScope)를 만듭니다.

        - 열: 왼쪽에서 체크한 열 (없으면 텍스트를 뺀 모든 열)
        - 전처리 점검·변수 종류는 항상 모든 열 (ALL_COLUMN_METHODS)
        - 입력칸이 있는 분석은 그 칸에서 고른 열만 (계산을 가볍게)
        - 행: 필터 칩 + 직접 입력 조건
        """
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
        """열·필터가 바뀌면 남는 행 수를 다시 세고, 데이터 탭과 실행 전 점검을 갱신합니다."""
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
        """데이터 탭에 지금 범위의 데이터를 보여줍니다."""
        try:
            scope = self.current_scope()
            mask, _ = scope.row_mask(self.df)
            cols = scope.columns or list(self.df.columns)
            self.main.tabs.set_data(self.df.loc[mask.to_numpy(dtype=bool), cols])
        except Exception:
            pass

    def choose_method(self, key):
        """메뉴에서 분석을 고르면 설정 줄을 바꿉니다. 준비 중인 분석이면 안내(UNSUPPORTED)를 남깁니다."""
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
        """실행 전 점검: 지금 범위의 데이터로 methods.precheck를 돌려 실행 버튼·안내를 정합니다."""
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
        """오른쪽 클릭으로 변수 종류를 바꾸면 엔진·열 목록·필터·설정 줄에 반영합니다."""
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
        """분석을 작업 스레드에서 실행합니다 (창이 멈추지 않게). 동시에 하나만 실행합니다."""
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
        """분석이 끝나면 새 결과들을 결과 세션·결과 탭에 보이고 히스토리에 기록합니다."""
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
        """작업 스레드에서 예상하지 못한 오류가 나면 FAIL로 알립니다."""
        r = AnalysisResult(method.label, "FAIL", msg)
        self.bd.results.append(r)
        self._log_result(r, len(self.bd.results) - 1)
        self.main.tabs.show_result(r)
        self._precheck()

    def _show_result(self, r):
        """결과 하나를 결과 탭에 보입니다."""
        idx = self.bd.results.index(r) if r in self.bd.results else None
        self._log_result(r, idx)
        self.main.tabs.show_result(r)

    def _log_result(self, r, idx):
        """결과 세션에 한 줄 추가합니다 (줄을 누르면 idx번째 결과를 다시 봄)."""
        short = r.message if len(r.message) <= 120 else r.message[:117] + "…"
        self.main.session.add(r.status, f"{r.name}  {short}", r.created_at, idx)

    def _reopen(self, idx):
        """결과 세션 줄을 누르면 그 결과를 다시 보여줍니다."""
        if self.bd and 0 <= idx < len(self.bd.results):
            self.main.tabs.show_result(self.bd.results[idx])

    def log(self, status, text):
        """결과 세션에 상태(INFO/FAIL 등)와 문장을 한 줄 남깁니다."""
        self.main.session.add(status, text, datetime.now().strftime("%H:%M:%S"))

