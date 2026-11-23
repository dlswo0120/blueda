"""왼쪽 열 상자(ColumnPanel): 열 목록, 검색, 종류별 묶음, 오른쪽 클릭으로 변수 종류 바꾸기"""


import pandas as pd
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout, QHeaderView, QLineEdit, QMenu, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from ...variables import KINDS
from .base import button, label


# ======================================================================
# 왼쪽: 열 상자
# ======================================================================
KIND_ORDER = ["수치형", "범주형", "날짜", "ID 후보", "텍스트"]
KIND_TITLE = {"수치형": "수치형", "범주형": "범주형", "날짜": "날짜", "ID 후보": "ID", "텍스트": "텍스트"}


def column_detail(s, kind):
    """열 이름 옆에 보여줄 짧은 정보 (범위 또는 값 개수)."""
    if kind == "수치형":
        x = pd.to_numeric(s, errors="coerce")
        if x.notna().any():
            lo, hi = x.min(), x.max()
            fmt = (lambda v: f"{v:,.0f}") if float(lo).is_integer() and float(hi).is_integer() else (lambda v: f"{v:,.3g}")
            return f"{fmt(lo)}~{fmt(hi)}"
        return ""
    if kind == "ID 후보":
        return "모두 다름"
    miss = s.isna().mean()
    base = f"{s.nunique(dropna=True):,}개"
    return base + (f" · 결측 {miss:.0%}" if miss >= 0.01 else "")


class ColumnPanel(QWidget):
    selectionChanged = Signal(list)
    typeChangeRequested = Signal(str, str)

    def __init__(self):
        super().__init__()
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(6)
        top = QHBoxLayout()
        self.count_label = label("열 0 / 0", "sub")
        top.addWidget(self.count_label, 1)
        self.all_btn = button("전체", "link")
        self.none_btn = button("해제", "link")
        top.addWidget(self.all_btn)
        top.addWidget(self.none_btn)
        box.addLayout(top)
        self.search = QLineEdit()
        self.search.setPlaceholderText("열 이름 검색")
        self.search.setClearButtonEnabled(True)
        box.addWidget(self.search)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setColumnCount(2)
        self.tree.setRootIsDecorated(False)
        self.tree.setIndentation(0)
        self.tree.setFixedHeight(260)          # 열이 많아도 아래 메뉴를 밀어내지 않음 (상자 안에서만 스크롤)
        self.tree.header().setStretchLastSection(False)
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.tree.setToolTip("오른쪽 클릭: 변수 종류 바꾸기")
        box.addWidget(self.tree)

        self.all_btn.clicked.connect(lambda: self._set_all(True))
        self.none_btn.clicked.connect(lambda: self._set_all(False))
        self.search.textChanged.connect(self._filter)
        self.tree.itemChanged.connect(self._on_item_changed)
        self.tree.customContextMenuRequested.connect(self._context_menu)
        self._updating = False
        self._total = 0

    def set_columns(self, df, kinds, selected=()):
        self._updating = True
        self.tree.clear()
        self._total = len(df.columns)
        for kind in KIND_ORDER:
            cols = [c for c in df.columns if kinds.get(c) == kind]
            if not cols:
                continue
            head = QTreeWidgetItem([f"{KIND_TITLE[kind]} {len(cols)}", ""])
            head.setFlags(Qt.ItemIsEnabled)
            f = head.font(0)
            f.setPointSizeF(max(f.pointSizeF() - 1.5, 7))
            head.setFont(0, f)
            head.setForeground(0, Qt.gray)
            self.tree.addTopLevelItem(head)
            for c in cols:
                it = QTreeWidgetItem(["  " + str(c), column_detail(df[c], kind)])
                it.setData(0, Qt.UserRole, c)
                it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable | Qt.ItemIsSelectable)
                it.setCheckState(0, Qt.Checked if c in selected else Qt.Unchecked)
                it.setForeground(1, Qt.gray)
                it.setToolTip(0, f"{c} · {kind}")
                self.tree.addTopLevelItem(it)
        self._updating = False
        self._emit()

    def selected(self):
        out = []
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            c = it.data(0, Qt.UserRole)
            if c is not None and it.checkState(0) == Qt.Checked:
                out.append(c)
        return out

    def set_selected(self, columns):
        """히스토리 복원: 이 열들만 체크합니다."""
        want = set(columns)
        self._updating = True
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            c = it.data(0, Qt.UserRole)
            if c is not None:
                it.setCheckState(0, Qt.Checked if str(c) in want or c in want else Qt.Unchecked)
        self._updating = False
        self._emit()

    def _set_all(self, on):
        self._updating = True
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            if it.data(0, Qt.UserRole) is not None and not it.isHidden():
                it.setCheckState(0, Qt.Checked if on else Qt.Unchecked)
        self._updating = False
        self._emit()

    def _filter(self, text):
        q = text.strip().lower()
        head = None
        visible_in_group = 0
        for i in range(self.tree.topLevelItemCount()):
            it = self.tree.topLevelItem(i)
            c = it.data(0, Qt.UserRole)
            if c is None:
                if head is not None:
                    head.setHidden(visible_in_group == 0)
                head, visible_in_group = it, 0
                continue
            show = not q or q in str(c).lower()
            it.setHidden(not show)
            visible_in_group += show
        if head is not None:
            head.setHidden(visible_in_group == 0)

    def _on_item_changed(self, *_):
        if not self._updating:
            self._emit()

    def _emit(self):
        sel = self.selected()
        self.count_label.setText(f"열 {len(sel)} / {self._total}")
        self.selectionChanged.emit(sel)

    def _context_menu(self, pos):
        it = self.tree.itemAt(pos)
        c = it.data(0, Qt.UserRole) if it else None
        if c is None:
            return
        menu = QMenu(self)
        menu.addSection(f"'{c}' 종류 바꾸기")
        for k in KINDS:
            act = menu.addAction(k)
            act.triggered.connect(lambda _=False, k=k: self.typeChangeRequested.emit(c, k))
        menu.exec(self.tree.viewport().mapToGlobal(pos))
