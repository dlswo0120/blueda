"""아래쪽 결과 세션(SessionPanel): 결과 줄, 히스토리 탭, 명령 입력칸"""


from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QStackedWidget, QVBoxLayout,
)

from .. import theme
from .base import button


# ======================================================================
# 아래: 결과 세션 (터미널 스타일)
# ======================================================================
class SessionPanel(QFrame):
    resultClicked = Signal(int)
    command = Signal(str)
    historyClicked = Signal(int)       # 히스토리 목록에서 누른 기록 번호 (store.entries 안의 위치)
    historyClearRequested = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("SessionBox")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 4, 12, 6)
        lay.setSpacing(2)
        mono = QFont()
        mono.setFamilies(theme.MONO_FAMILIES)
        mono.setPointSize(10)
        # 위쪽 전환: 결과 세션 | 히스토리
        tabs = QHBoxLayout()
        tabs.setSpacing(4)
        self.tab_session = button("결과 세션", "console_tab", checkable=True)
        self.tab_history = button("히스토리", "console_tab", checkable=True)
        self.tab_session.setChecked(True)
        for i, b in enumerate((self.tab_session, self.tab_history)):
            b.clicked.connect(lambda _=False, i=i: self.show_page(i))
            tabs.addWidget(b)
        tabs.addStretch(1)
        self.history_info = QLabel("")
        self.history_info.setObjectName("Prompt")
        self.history_clear = button("전체 삭제", "console_link")
        self.history_clear.clicked.connect(self.historyClearRequested)
        tabs.addWidget(self.history_info)
        tabs.addWidget(self.history_clear)
        lay.addLayout(tabs)
        self.pages = QStackedWidget()
        self.list = QListWidget()
        self.list.setObjectName("Session")
        self.list.setFont(mono)
        self.list.setToolTip("결과 줄을 누르면 그 결과를 다시 봅니다")
        self.history = QListWidget()
        self.history.setObjectName("Session")
        self.history.setFont(mono)
        self.history.setToolTip("기록을 누르면 그때의 조건과 분석 설정으로 되돌립니다 (실행은 직접)")
        self.history.itemClicked.connect(lambda it: self.historyClicked.emit(it.data(Qt.UserRole))
                                         if it.data(Qt.UserRole) is not None else None)
        self.pages.addWidget(self.list)
        self.pages.addWidget(self.history)
        lay.addWidget(self.pages, 1)
        self.show_page(0)
        row = QHBoxLayout()
        prompt = QLabel(">")
        prompt.setObjectName("Prompt")
        prompt.setFont(mono)
        self.input = QLineEdit()
        self.input.setObjectName("Command")
        self.input.setFont(mono)
        self.input.setPlaceholderText("명령 입력  (help: 명령 목록)")
        row.addWidget(prompt)
        row.addWidget(self.input, 1)
        lay.addLayout(row)
        self.input.returnPressed.connect(self._enter)
        self.list.itemClicked.connect(self._click)

    def add(self, status, text, time="", result_index=None):
        """한 줄 추가: 시각(회색) · 상태(색) · 내용. 시안처럼 상태 글자만 색을 입힙니다."""
        import html
        color = theme.STATUS_COLORS.get(status, theme.CONSOLE_TEXT)
        line = QLabel(
            f"<span style='color:{theme.CONSOLE_TIME}'>{html.escape(time)}</span>&nbsp;&nbsp;"
            f"<span style='color:{color}'>{html.escape(status).ljust(11).replace(' ', '&nbsp;')}</span>&nbsp;"
            f"<span style='color:{theme.CONSOLE_TEXT}'>{html.escape(text)}</span>")
        line.setFont(self.list.font())
        line.setTextFormat(Qt.RichText)
        line.setAttribute(Qt.WA_TransparentForMouseEvents)   # 클릭은 목록 줄이 받도록
        it = QListWidgetItem()
        it.setData(Qt.UserRole, result_index)
        it.setToolTip(text)
        it.setSizeHint(QSize(10, line.sizeHint().height() + 4))
        self.list.addItem(it)
        self.list.setItemWidget(it, line)
        self.list.scrollToBottom()
        return it

    def show_page(self, i):
        self.pages.setCurrentIndex(i)
        self.tab_session.setChecked(i == 0)
        self.tab_history.setChecked(i == 1)
        self.history_info.setVisible(i == 1)
        self.history_clear.setVisible(i == 1)
        if i == 1:
            QTimer.singleShot(0, self.history.scrollToBottom)   # 화면에 그려진 뒤 최신 기록으로

    def set_history(self, rows, info=""):
        """rows: [(번호, 시각, 종류, 내용)] 최근 것이 아래. info: 오른쪽 위 안내 (건수·용량)"""
        import html
        self.history.clear()
        if not rows:
            it = QListWidgetItem("기록이 없습니다. 필터를 적용하거나 분석을 실행하면 여기에 남습니다.")
            it.setForeground(QColor(theme.CONSOLE_TIME))
            self.history.addItem(it)
        for idx, when, kind, text in rows:
            line = QLabel(
                f"<span style='color:{theme.CONSOLE_TIME}'>{html.escape(when)}</span>&nbsp;&nbsp;"
                f"<span style='color:#8FB4E3'>{html.escape(kind).ljust(6, chr(12288))}</span>&nbsp;"
                f"<span style='color:{theme.CONSOLE_TEXT}'>{html.escape(text)}</span>")
            line.setFont(self.history.font())
            line.setTextFormat(Qt.RichText)
            line.setAttribute(Qt.WA_TransparentForMouseEvents)
            it = QListWidgetItem()
            it.setData(Qt.UserRole, idx)
            it.setToolTip(text)
            it.setSizeHint(QSize(10, line.sizeHint().height() + 4))
            self.history.addItem(it)
            self.history.setItemWidget(it, line)
        self.history.scrollToBottom()
        self.history_info.setText(info)

    def _click(self, it):
        idx = it.data(Qt.UserRole)
        if idx is not None:
            self.resultClicked.emit(idx)

    def _enter(self):
        t = self.input.text().strip()
        self.input.clear()
        if t:
            self.command.emit(t)
