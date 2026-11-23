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
    """왼쪽 분석 메뉴. '방법별'(그룹별 목록)과 '질문별'(예: 두 그룹 평균이 다른가요?) 두 가지 보기.

    신호: methodChosen(분석 키). 준비 중인 분석도 보여주고 누르면 안내합니다.
    """
    methodChosen = Signal(str)

    def __init__(self):
        """위쪽 세그먼트 버튼(방법별/질문별)과 목록을 만듭니다."""
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
        """보기 전환 (True: 방법별, False: 질문별)."""
        self.by_method.setChecked(methods_view)
        self.by_question.setChecked(not methods_view)
        self._fill_methods() if methods_view else self._fill_questions()

    def _group_header(self, text):
        """그룹 제목 줄(누를 수 없음)을 추가합니다."""
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
        """방법별 목록: 그룹 제목 + 항목(이름 14px, 한 줄 설명 11px)."""
        self.list.clear()
        for g in M.GROUPS:
            self._group_header(g)
            for m in [m for m in M.METHODS if m.group == g]:
                self._entry(m.label + ("" if m.available else " (준비 중)"), m.desc, m.key, m.available)

    def _fill_questions(self):
        """질문별 목록: 질문 문장 → 해당 분석."""
        self.list.clear()
        self._group_header("무엇을 알고 싶나요?")
        for m in M.METHODS:
            if m.question:
                self._entry(m.question, "→ " + m.label, m.key)

    def select(self, key):
        """key 분석을 목록에서 선택 표시합니다 (신호는 보내지 않음)."""
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.UserRole) == key:
                self.list.setCurrentRow(i)
                return

    def _clicked(self, it):
        """항목을 누르면 methodChosen 신호를 보냅니다."""
        key = it.data(Qt.UserRole)
        if key:
            self.methodChosen.emit(key)
