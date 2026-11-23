"""행 조건(FilterBar): 필터 칩, '+ 조건' 열 고르기 창, 값 선택 창, 범위 창"""


import pandas as pd
from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLineEdit, QListWidget, QListWidgetItem, QMenu, QSizePolicy, QVBoxLayout,
    QWidget,
)

from .. import theme
from .base import FlowLayout, Popup, button, label
from .columns import KIND_ORDER, KIND_TITLE


# ======================================================================
# 가운데 위: 필터 칩 (행 조건)
# ======================================================================
class ColumnPickerPopup(Popup):
    picked = Signal(str)

    def __init__(self, df, kinds, parent=None):
        super().__init__(260, parent)
        self.search = QLineEdit()
        self.search.setPlaceholderText(f"열 검색 ({len(df.columns)}개)")
        self.box.addWidget(self.search)
        self.list = QListWidget()
        self.list.setFixedHeight(240)
        self.box.addWidget(self.list)
        for kind in KIND_ORDER:
            cols = [c for c in df.columns if kinds.get(c) == kind and kind != "텍스트"]
            if not cols:
                continue
            head = QListWidgetItem(KIND_TITLE[kind])
            head.setFlags(Qt.NoItemFlags)
            head.setForeground(Qt.gray)
            self.list.addItem(head)
            for c in cols:
                it = QListWidgetItem("  " + str(c))
                it.setData(Qt.UserRole, c)
                self.list.addItem(it)
        self.search.textChanged.connect(self._filter)
        self.list.itemClicked.connect(self._click)

    def _filter(self, t):
        q = t.strip().lower()
        for i in range(self.list.count()):
            it = self.list.item(i)
            c = it.data(Qt.UserRole)
            if c is not None:
                it.setHidden(bool(q) and q not in str(c).lower())

    def _click(self, it):
        c = it.data(Qt.UserRole)
        if c is not None:
            self.close()
            self.picked.emit(c)


class ValuePopup(Popup):
    """범주형 값 고르기: 검색 + 체크 목록 (값마다 행 수)."""
    applied = Signal(list)
    MAX_LIST = 5000

    def __init__(self, series, chosen=(), max_direct=20, parent=None):
        super().__init__(280, parent)
        counts = series.value_counts(dropna=True)
        self._total_values = len(counts)
        self.search = QLineEdit()
        self.search.setPlaceholderText(f"값 검색 ({len(counts):,}개)")
        self.search.setClearButtonEnabled(True)
        self.box.addWidget(self.search)
        if len(counts) > max_direct:
            self.search.setFocus()
        self.list = QListWidget()
        self.list.setFixedHeight(220)
        self.box.addWidget(self.list)
        chosen = set(map(str, chosen))
        for v, n in counts.head(self.MAX_LIST).items():
            it = QListWidgetItem(f"{v}")
            it.setData(Qt.UserRole, v)
            it.setData(Qt.UserRole + 1, f"{n:,}")
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked if str(v) in chosen else Qt.Unchecked)
            it.setToolTip(f"{v} · {n:,}행")
            it.setText(f"{v}    {n:,}")
            self.list.addItem(it)
        if len(counts) > self.MAX_LIST:
            self.box.addWidget(label(f"행 수가 많은 상위 {self.MAX_LIST:,}개만 표시합니다. 검색으로 찾으세요.", "sub", True))
        foot = QHBoxLayout()
        self.count = label("", "sub")
        foot.addWidget(self.count, 1)
        clear = button("해제", "link")
        ok = button("적용", "primary")
        foot.addWidget(clear)
        foot.addWidget(ok)
        self.box.addLayout(foot)
        self.search.textChanged.connect(self._filter)
        self.list.itemChanged.connect(self._update_count)
        clear.clicked.connect(self._clear)
        ok.clicked.connect(self._apply)
        self._update_count()

    def _filter(self, t):
        q = t.strip().lower()
        for i in range(self.list.count()):
            it = self.list.item(i)
            it.setHidden(bool(q) and q not in str(it.data(Qt.UserRole)).lower())

    def _checked(self):
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.Checked]

    def _update_count(self, *_):
        self.count.setText(f"{len(self._checked())}개 선택")

    def _clear(self):
        for i in range(self.list.count()):
            self.list.item(i).setCheckState(Qt.Unchecked)

    def _apply(self):
        self.close()
        self.applied.emit(self._checked())


class RangePopup(Popup):
    """수치형·날짜 범위 고르기: 최소 ~ 최대."""
    applied = Signal(object, object)

    def __init__(self, series, kind, lo=None, hi=None, parent=None):
        super().__init__(260, parent)
        self.kind = kind
        row = QHBoxLayout()
        self.lo = QLineEdit("" if lo is None else str(lo))
        self.hi = QLineEdit("" if hi is None else str(hi))
        for w, name in ((self.lo, "최소" if kind == "수치형" else "시작"), (self.hi, "최대" if kind == "수치형" else "끝")):
            col = QVBoxLayout()
            col.setSpacing(2)
            col.addWidget(label(name, "sub"))
            w.setMinimumWidth(0)
            w.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)   # 상자 안에 맞게 줄어듦 (튀어나옴 방지)
            col.addWidget(w)
            row.addLayout(col, 1)
        self.box.addLayout(row)
        if kind == "수치형":
            x = pd.to_numeric(series, errors="coerce").dropna()
            self.lo.setValidator(QDoubleValidator())
            self.hi.setValidator(QDoubleValidator())
            if len(x):
                self.box.addWidget(label(f"데이터 범위 {x.min():,.4g} ~ {x.max():,.4g} · 중앙값 {x.median():,.4g}", "sub", True))
        else:
            d = pd.to_datetime(series, errors="coerce", format="mixed").dropna()
            self.lo.setPlaceholderText("2025-01-01")
            self.hi.setPlaceholderText("2025-12-31")
            if len(d):
                self.box.addWidget(label(f"데이터 범위 {d.min():%Y-%m-%d} ~ {d.max():%Y-%m-%d}", "sub", True))
        self.error = label("", "warn", True)
        self.error.hide()
        self.box.addWidget(self.error)
        ok = button("적용", "primary")
        foot = QHBoxLayout()
        foot.addStretch(1)
        foot.addWidget(ok)
        self.box.addLayout(foot)
        ok.clicked.connect(self._apply)

    def _value(self, text):
        t = text.strip().replace(",", "")
        if not t:
            return None
        if self.kind == "수치형":
            return float(t) if "." in t or "e" in t.lower() else int(t)
        pd.Timestamp(t)          # 날짜 형식 확인 (틀리면 오류)
        return t

    def _apply(self):
        try:
            lo, hi = self._value(self.lo.text()), self._value(self.hi.text())
        except (ValueError, TypeError):
            self.error.setText("형식을 확인하세요. 예: 30 또는 2025-01-31")
            self.error.show()
            return
        if lo is not None and hi is not None:
            a, b = (lo, hi) if self.kind == "수치형" else (pd.Timestamp(lo), pd.Timestamp(hi))
            bad = a > b
        else:
            bad = False
        if bad:
            self.error.setText("최소가 최대보다 큽니다.")
            self.error.show()
            return
        self.close()
        self.applied.emit(lo, hi)


class Chip(QFrame):
    clicked = Signal()
    removed = Signal()

    def __init__(self, text):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        self.btn = button(text + "  ▾", "chip")
        self.x = button("×", "ghost")
        self.x.setFixedWidth(22)
        self.x.setToolTip("조건 지우기")
        lay.addWidget(self.btn)
        lay.addWidget(self.x)
        self.btn.clicked.connect(self.clicked)
        self.x.clicked.connect(self.removed)

    def set_text(self, text):
        self.btn.setText(text + "  ▾")


class FilterBar(QWidget):
    """조건 칩 줄. filters가 바뀌면 changed를 보냅니다."""
    changed = Signal()

    def __init__(self):
        super().__init__()
        self.filters = []
        self.query = ""
        self.df = None
        self.kinds = {}
        self.max_direct = 20
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(8)
        row = QHBoxLayout()
        row.setSpacing(8)
        self.flow_host = QWidget()
        self.flow = FlowLayout(self.flow_host)
        row.addWidget(label("조건", "sub"), 0, Qt.AlignTop)
        row.addWidget(self.flow_host, 1)
        right = QHBoxLayout()
        right.setSpacing(4)
        self.rows = label("", None)
        self.direct_btn = button("직접 입력", "ghost", checkable=True)
        right.addWidget(self.rows)
        right.addWidget(self.direct_btn)
        row.addLayout(right)
        outer.addLayout(row)
        self.direct = QLineEdit()
        self.direct.setPlaceholderText("pandas query 문법. 예: 나이 >= 30 and 시도 == '서울'  (Enter로 적용)")
        self.direct.hide()
        outer.addWidget(self.direct)
        self.direct_btn.toggled.connect(self.direct.setVisible)
        self.direct.returnPressed.connect(self._apply_query)
        self._rebuild()

    def set_data(self, df, kinds, max_direct=20):
        """새 파일을 열 때: 데이터를 바꾸고 필터·직접 입력 조건을 모두 비웁니다."""
        self.df, self.kinds, self.max_direct = df, kinds, max_direct
        self.filters, self.query = [], ""
        self.direct.clear()
        self._rebuild()

    def update_data(self, df, kinds, max_direct=20):
        """데이터 내용만 바뀌었을 때(날짜 변환 등) 쓰는 갱신. 걸어 둔 필터와 직접 입력 조건은 그대로 둡니다.
        (set_data는 새 파일을 열 때 쓰며 필터를 모두 비웁니다.)"""
        self.df, self.kinds, self.max_direct = df, kinds, max_direct
        self._rebuild()

    def set_row_count(self, n, total):
        self.rows.setText(f"→ <b>{n:,}</b>행" + ("" if n == total else f" <span style='color:{theme.SUB}'>/ {total:,}</span>"))

    # ---- 칩 다시 그리기 ----
    def _rebuild(self):
        while self.flow.count():
            w = self.flow.takeAt(0).widget()
            if w:
                w.hide()               # deleteLater만 하면 다음 그리기까지 잔상이 남음
                w.setParent(None)
                w.deleteLater()
        for i, f in enumerate(self.filters):
            chip = Chip(f.label())
            chip.clicked.connect(lambda i=i, c=chip: self._edit(i, c.btn))
            chip.removed.connect(lambda i=i: self._remove(i))
            self.flow.addWidget(chip)
        self.add_btn = button("+ 조건", "dashed")
        self.add_btn.clicked.connect(self._add)
        self.flow.addWidget(self.add_btn)
        self.na_btn = button("결측 제외", "ghost")
        self.na_btn.clicked.connect(self._add_notna)
        self.flow.addWidget(self.na_btn)
        self.iqr_btn = button("이상값 후보 제외", "ghost")
        self.iqr_btn.clicked.connect(self._add_iqr)
        self.flow.addWidget(self.iqr_btn)
        enabled = self.df is not None
        for b in (self.add_btn, self.na_btn, self.iqr_btn):
            b.setEnabled(enabled)
        self.flow_host.updateGeometry()

    def _changed(self):
        self._rebuild()
        self.changed.emit()

    def set_state(self, filters, query=""):
        """히스토리 복원: 필터와 직접 입력 조건을 한 번에 바꿉니다."""
        self.filters = list(filters)
        self.query = query or ""
        if hasattr(self, "direct"):
            self.direct.setText(self.query)
        self._changed()

    def _remove(self, i):
        self.filters.pop(i)
        self._changed()

    # ---- 조건 추가 ----
    def _add(self):
        pop = ColumnPickerPopup(self.df, self.kinds, self)
        pop.picked.connect(lambda c: self._open_editor(c, None, self.add_btn))
        pop.show_below(self.add_btn)

    def _open_editor(self, column, index, anchor):
        from ...scope import Filter
        kind = self.kinds.get(column)
        current = self.filters[index] if index is not None else None
        if kind in ("수치형", "날짜"):
            pop = RangePopup(self.df[column], kind, current.lo if current else None, current.hi if current else None, self)

            def done(lo, hi):
                if lo is None and hi is None:
                    return
                f = Filter(column, "between", lo=lo, hi=hi)
                self._put(index, f)
            pop.applied.connect(done)
        else:
            pop = ValuePopup(self.df[column], current.values if current else (), self.max_direct, self)

            def done(values):
                if not values:
                    if index is not None:
                        self._remove(index)
                    return
                self._put(index, Filter(column, "in", values=values))
            pop.applied.connect(done)
        pop.show_below(anchor)

    def _put(self, index, f):
        if index is None:
            self.filters.append(f)
        else:
            self.filters[index] = f
        self._changed()

    def _edit(self, i, anchor):
        f = self.filters[i]
        if f.op in ("between", "in"):
            self._open_editor(f.column, i, anchor)

    def _add_notna(self):
        from ...scope import Filter
        if any(f.op == "notna" for f in self.filters):
            return
        self.filters.append(Filter(op="notna"))
        self._changed()

    def _add_iqr(self):
        nums = [c for c, k in self.kinds.items() if k == "수치형"]
        if not nums:
            return
        menu = QMenu(self)
        menu.addSection("어느 열의 이상값 후보를 뺄까요?")
        for c in nums:
            menu.addAction(str(c)).triggered.connect(lambda _=False, c=c: self._put_iqr(c))
        menu.exec(self.iqr_btn.mapToGlobal(QPoint(0, self.iqr_btn.height())))

    def _put_iqr(self, c):
        from ...scope import Filter
        self.filters.append(Filter(c, "iqr_inside"))
        self._changed()

    def _apply_query(self):
        self.query = self.direct.text().strip()
        self.changed.emit()
