"""분석 메뉴(MethodMenu): 방법별/질문별 보기, 항목마다 한 줄 설명"""


from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView, QFrame, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QVBoxLayout, QWidget,
)

from ... import methods as M
from .. import theme
from .base import button


# ======================================================================
# 왼쪽: 분석 메뉴 (방법별 / 질문별)
# ======================================================================
class MethodMenu(QWidget):
    methodChosen = Signal(str)

    def __init__(self):
        super().__init__()
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(8)
        seg = QFrame()
        seg.setObjectName("Seg")
        sl = QHBoxLayout(seg)
        sl.setContentsMargins(2, 2, 2, 2)
        sl.setSpacing(2)
        self.by_method = button("방법별", "seg", checkable=True)
        self.by_question = button("질문별", "seg", checkable=True)
        self.by_method.setChecked(True)
        sl.addWidget(self.by_method)
        sl.addWidget(self.by_question)
        box.addWidget(seg)
        self.list = QListWidget()
        self.list.setSpacing(1)
        self.list.setWordWrap(True)
        self.list.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        box.addWidget(self.list, 1)
        self.by_method.clicked.connect(lambda: self._mode(True))
        self.by_question.clicked.connect(lambda: self._mode(False))
        self.list.itemClicked.connect(self._clicked)
        self._fill_methods()

    def _mode(self, methods_view):
        self.by_method.setChecked(methods_view)
        self.by_question.setChecked(not methods_view)
        self._fill_methods() if methods_view else self._fill_questions()

    def _group_header(self, text):
        it = QListWidgetItem(text)
        it.setFlags(Qt.NoItemFlags)
        f = it.font()
        f.setPointSizeF(max(f.pointSizeF() - 1.5, 7))
        it.setFont(f)
        it.setForeground(Qt.gray)
        self.list.addItem(it)

    def _entry(self, title, sub, key, enabled=True):
        """메뉴 한 줄: 이름(보통 글씨) + 설명(작은 회색 글씨)."""
        w = QWidget()
        w.setAttribute(Qt.WA_TransparentForMouseEvents)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(6, 4, 6, 4)
        lay.setSpacing(0)
        name = QLabel(title)
        name.setStyleSheet(f"color: {theme.TEXT if enabled else theme.MUTED}; font-size: 14px;")
        desc = QLabel(sub)
        desc.setStyleSheet(f"color: {theme.SUB if enabled else theme.MUTED}; font-size: 11px;")
        lay.addWidget(name)
        lay.addWidget(desc)
        it = QListWidgetItem()
        it.setData(Qt.UserRole, key)
        it.setToolTip(f"{title} · {sub}")
        it.setSizeHint(QSize(10, w.sizeHint().height()))
        self.list.addItem(it)
        self.list.setItemWidget(it, w)

    def _fill_methods(self):
        self.list.clear()
        for g in M.GROUPS:
            self._group_header(g)
            for m in [m for m in M.METHODS if m.group == g]:
                self._entry(m.label + ("" if m.available else " (준비 중)"), m.desc, m.key, m.available)

    def _fill_questions(self):
        self.list.clear()
        self._group_header("무엇을 알고 싶나요?")
        for m in M.METHODS:
            if m.question:
                self._entry(m.question, "→ " + m.label, m.key)

    def select(self, key):
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == key:
                self.list.setCurrentRow(i)
                return

    def _clicked(self, it):
        key = it.data(Qt.UserRole)
        if key:
            self.methodChosen.emit(key)
