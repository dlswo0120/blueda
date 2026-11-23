"""분석 설정 줄(AnalysisBar): 고른 분석의 입력칸, 실행 전 점검 문구, 실행 버튼"""


import pandas as pd
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QDoubleValidator, QIntValidator
from PySide6.QtWidgets import (
    QComboBox, QHBoxLayout, QLineEdit, QPushButton, QVBoxLayout, QWidget,
)

from ... import methods as M
from ...interpret import josa
from .base import button, label
from .filters import ValuePopup


# ======================================================================
# 가운데: 분석 설정 줄
# ======================================================================
class MultiColumnButton(QPushButton):
    """여러 열 고르기 (다중회귀의 설명 변수)."""
    changedColumns = Signal(list)

    def __init__(self):
        """여러 열을 고르는 버튼 (다중회귀 독립변수 등). columns는 고른 열, options는 고를 수 있는 열."""
        super().__init__("고르기  ▾")
        self.setProperty("kind", "chip")
        self.columns = []
        self.options = []
        self.clicked.connect(self._open)

    def set_options(self, options):
        """고를 수 있는 열을 바꿉니다. 이미 고른 열 중 목록에 없는 것은 뺍니다."""
        self.options = list(options)
        self.columns = [c for c in self.columns if c in self.options]
        self._label()

    def set_columns(self, cols):
        """고른 열을 직접 정합니다 (히스토리 복원용). 목록에 없는 열은 무시합니다."""
        self.columns = [c for c in cols if c in self.options]
        self._label()

    def _label(self):
        """버튼 글자를 '고르기' / 'A, B' / 'A 외 N'으로 바꿉니다."""
        n = len(self.columns)
        self.setText(("고르기" if n == 0 else ", ".join(map(str, self.columns)) if n <= 2 else f"{self.columns[0]} 외 {n - 1}") + "  ▾")

    def _open(self):
        """열 목록 팝업(ValuePopup)을 열고, 적용하면 changedColumns 신호를 보냅니다."""
        pop = ValuePopup(pd.Series(self.options, dtype=object), self.columns, parent=self)
        for i in range(pop.list.count()):              # 열 목록이라 행 수 표시는 빼기
            it = pop.list.item(i)
            it.setText(str(it.data(Qt.UserRole)))
        pop.search.setPlaceholderText(f"열 검색 ({len(self.options)}개)")

        def done(cols):
            """팝업에서 적용한 열을 저장하고 알립니다."""
            self.columns = cols
            self._label()
            self.changedColumns.emit(cols)
        pop.applied.connect(done)
        pop.show_below(self)


class AnalysisBar(QWidget):
    """분석 설정 줄: 고른 분석의 이름·설명, 입력칸들, 실행 전 점검 문구, 대안 버튼, 실행 버튼.

    주요 속성
    - method: 지금 분석(methods.Method)
    - widgets: {칸 이름: (Param, 입력 위젯, 칸 상자)}. 칸 상자는 차트 종류 등에 따라 숨김/보임
    - kinds: 열마다 변수 종류 (칸에 맞는 열만 목록에 넣고, 날짜 단위 칸 표시 여부를 정할 때 사용)
    신호: runRequested(분석 키, 값) / switchRequested(대안 분석 키) / paramsChanged(입력이 바뀐 뒤 200ms)
    """
    runRequested = Signal(str, dict)
    switchRequested = Signal(str)
    paramsChanged = Signal()

    def __init__(self):
        """빈 설정 줄을 만듭니다. 입력이 바뀔 때마다 점검하지 않고 200ms 기다렸다 한 번만 점검합니다(_timer)."""
        super().__init__()
        self.method = None  # 지금 분석(methods.Method)
        self.widgets = {}  # {칸 이름: (Param, 입력 위젯, 칸 상자)}
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        top = QHBoxLayout()
        top.setSpacing(16)
        head = QVBoxLayout()
        head.setSpacing(0)
        self.title = label("분석을 고르세요", "title")
        self.desc = label("왼쪽 메뉴에서 분석을 고르면 여기서 설정합니다", "sub")
        head.addWidget(self.title)
        head.addWidget(self.desc)
        top.addLayout(head, 1)
        self.fields = QHBoxLayout()  # 입력칸 상자들이 가로로 놓이는 자리
        self.fields.setSpacing(12)
        top.addLayout(self.fields)
        self.run_btn = button("실행", "primary")
        self.run_btn.setEnabled(False)
        top.addWidget(self.run_btn, 0, Qt.AlignBottom)
        lay.addLayout(top)
        warn = QHBoxLayout()
        warn.setSpacing(10)
        self.warn = label("", "warn", True)
        self.alt_btn = button("", None)
        self.alt_btn.hide()
        self.warn.hide()
        warn.addWidget(self.warn, 1)
        warn.addWidget(self.alt_btn)
        lay.addLayout(warn)
        self.run_btn.clicked.connect(self._run)
        self.alt_btn.clicked.connect(lambda: self.switchRequested.emit(self._alt))
        self._alt = ""
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(200)          # 입력이 멈춘 뒤 0.2초 후 점검 (큰 데이터에서 매 글자마다 계산 방지)
        self._timer.timeout.connect(self.paramsChanged)

    def set_method(self, method, kinds, df):
        """분석을 바꾸면 이전 입력칸을 지우고 새 분석의 입력칸을 만듭니다.

        칸 종류(Param.kind)에 따라: 열 고르기 → 콤보(맞는 종류의 열만), 선택지 → 콤보, 여러 열 → MultiColumnButton,
        값 → 콤보(열의 값 목록), 숫자 → 입력칸(검사기 포함). 이전 칸은 숨기고 부모에서 떼어 낸 뒤 지웁니다(잔상 방지).
        """
        self.method = method
        self.title.setText(method.label)
        self.desc.setText(method.desc)
        while self.fields.count():
            item = self.fields.takeAt(0)
            if item.widget():
                # deleteLater만 하면 실제로 지워지기 전까지 이전 칸이 화면에 남아 새 칸과 겹칩니다.
                old = item.widget()
                old.hide()
                old.setParent(None)
                old.deleteLater()
            elif item.layout():
                lay = item.layout()
                while lay.count():
                    w = lay.takeAt(0).widget()
                    if w:
                        w.deleteLater()
        self.widgets = {}
        self.kinds = kinds
        for p in method.params:
            box = QWidget()                       # 칸 하나 (숨기기·보이기 단위)
            col = QVBoxLayout(box)
            col.setContentsMargins(0, 0, 0, 0)
            col.setSpacing(4)
            col.addWidget(label(p.label, "sub"))
            if p.kind in M.COLUMN_KINDS:
                w = QComboBox()
                w.setMinimumWidth(130)
                options = M.columns_for(p.kind, kinds)
                if p.optional:
                    w.addItem("없음", None)
                elif options:
                    w.addItem("선택", None)
                if not options and not p.optional:
                    w.addItem("맞는 열 없음", None)
                for c in options:
                    w.addItem(str(c), c)
                w.currentIndexChanged.connect(self._changed)
                if p.name == "column" and method.key == "ci_proportion":
                    w.currentIndexChanged.connect(lambda _=0, df=df: self._fill_values(df))
            elif p.kind == M.CHOICE:
                w = QComboBox()
                w.setMinimumWidth(96)
                for v in p.choices:
                    w.addItem(str(v), v)
                if p.default in p.choices:
                    w.setCurrentIndex(list(p.choices).index(p.default))
                w.currentIndexChanged.connect(self._changed)
            elif p.kind == M.COL_MULTI:
                w = MultiColumnButton()
                w.set_options(M.columns_for(p.kind, kinds))
                w.changedColumns.connect(self._changed)
            elif p.kind == M.VALUE:
                w = QComboBox()
                w.setMinimumWidth(120)
                w.currentIndexChanged.connect(self._changed)
            else:
                w = QLineEdit("" if p.default is None else str(p.default))
                w.setFixedWidth(100)
                w.setValidator(QIntValidator(2, 10_000_000) if p.kind == M.INT else QDoubleValidator())
                w.textChanged.connect(self._changed)
            col.addWidget(w)
            self.fields.addWidget(box)
            self.widgets[p.name] = (p, w, box)
        self._update_visibility()
        self._changed()

    def _update_visibility(self):
        """차트 종류·날짜 열 선택에 따라 필요한 칸만 보이게 합니다."""
        raw = self._raw_params()
        for name, (p, w, box) in self.widgets.items():
            box.setVisible(M.visible(p, raw, getattr(self, "kinds", {}), self.method))

    def _fill_values(self, df):
        """비율 신뢰구간의 '범주 값' 칸을 고른 열의 값(많은 순)으로 채웁니다."""
        _, cw, _ = self.widgets["column"]
        _, vw, _ = self.widgets["category"]
        vw.clear()
        c = cw.currentData()
        if c is not None:
            for v in df[c].value_counts().head(200).index:
                vw.addItem(str(v), v)

    def set_params(self, params):
        """히스토리 복원: 저장된 값으로 칸을 채웁니다. 지금 파일에 없는 값은 건너뜀."""
        for name in [n for n, (p, *_r) in self.widgets.items() if p.kind == M.CHOICE] + \
                [n for n, (p, *_r) in self.widgets.items() if p.kind != M.CHOICE]:
            if name not in params:                # 차트 종류(선택지)를 먼저 맞춰야 필요한 칸이 보임
                continue
            p, w, _ = self.widgets[name]
            v = params[name]
            if isinstance(w, MultiColumnButton):
                w.set_columns(v or [])
            elif isinstance(w, QComboBox):
                i = w.findData(v)
                if i >= 0:
                    w.setCurrentIndex(i)
            elif v is not None:
                w.setText(str(v))
        self._changed()

    def _raw_params(self):
        """모든 칸(숨은 칸 포함)의 현재 값을 {칸 이름: 값}으로 돌려줍니다."""
        out = {}
        for name, (p, w, _) in self.widgets.items():
            if isinstance(w, MultiColumnButton):
                out[name] = list(w.columns)
            elif isinstance(w, QComboBox):
                out[name] = w.currentData()
            else:
                out[name] = w.text().strip()
        return out

    def params(self):
        """보이는 칸의 값만 (숨은 칸은 분석에 쓰지 않음)."""
        raw = self._raw_params()
        return {name: raw[name] for name, (p, _, box) in self.widgets.items()
                if M.visible(p, raw, getattr(self, "kinds", {}), self.method)}

    def needed_columns(self):
        """고른 열 목록(중복 없이). 분석 범위를 이 열들로 좁혀 계산을 가볍게 합니다."""
        cols = []
        for name, v in self.params().items():
            p = self.widgets[name][0]
            if p.kind in M.COLUMN_KINDS and v:
                cols.append(v)
            elif p.kind == M.COL_MULTI:
                cols += v
        return list(dict.fromkeys(cols))

    def _changed(self, *_):
        """입력이 바뀌면 칸 보임/숨김을 다시 정하고 200ms 뒤 점검하도록 타이머를 다시 겁니다."""
        if self.widgets:
            self._update_visibility()
        self._timer.start()

    def set_check(self, check, running=False):
        """실행 전 점검 결과를 보여줍니다. 실패면 실행 버튼을 끄고 이유를, 대안이 있으면 '…으로 바꾸기' 버튼을 보입니다.

        running=True(분석 중)면 점검이 통과해도 실행 버튼을 끕니다.
        """
        self.run_btn.setEnabled(bool(check.ok) and not running)
        self.warn.setText(check.message)
        self.warn.setVisible(bool(check.message))
        self._alt = check.alternative
        if check.alternative:
            alt = M.BY_KEY[check.alternative]
            self.alt_btn.setText(f"{josa(alt.label, '으로/로')} 바꾸기")
            self.alt_btn.show()
        else:
            self.alt_btn.hide()

    def _run(self):
        """실행 버튼: 보이는 칸의 값으로 runRequested 신호를 보냅니다."""
        if self.method:
            self.runRequested.emit(self.method.key, self.params())
