"""시작 화면과 메인 분석 화면의 배치."""

import os

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFileDialog, QFrame, QGridLayout, QHBoxLayout, QListWidget, QListWidgetItem, QProgressBar,
    QScrollArea, QSplitter, QVBoxLayout, QWidget,
)

from .widgets import AnalysisBar, ColumnPanel, FilterBar, MethodMenu, ResultTabs, SessionPanel, button, label, panel

FILE_FILTER = "데이터 파일 (*.csv *.tsv *.txt *.xlsx);;모든 파일 (*)"


class DropZone(QFrame):
    """파일을 끌어다 놓거나 눌러서 고르는 영역."""
    fileChosen = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(200)
        self._style(False)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(8)
        icon = label("⬆")
        icon.setAlignment(Qt.AlignCenter)
        icon.setStyleSheet("font-size: 26px; color: #5F6B7A;")
        lay.addWidget(icon)
        t = label("파일을 끌어다 놓거나 클릭해서 선택")
        t.setStyleSheet("font-size: 16px;")
        t.setAlignment(Qt.AlignCenter)
        lay.addWidget(t)
        s = label("CSV, Excel 지원 · Word, PDF 표는 준비 중", "sub")
        s.setAlignment(Qt.AlignCenter)
        lay.addWidget(s)

    def _style(self, hover):
        self.setStyleSheet(
            "QFrame#DropZone { background: #FFFFFF; border-radius: 8px; border: "
            + ("2px dashed #2F5D9E;" if hover else "1px dashed #B8C0CC;") + " }")

    def mousePressEvent(self, e):
        path, _ = QFileDialog.getOpenFileName(self, "분석할 파일 선택", "", FILE_FILTER)
        if path:
            self.fileChosen.emit(path)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._style(True)

    def dragLeaveEvent(self, e):
        self._style(False)

    def dropEvent(self, e):
        self._style(False)
        urls = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        if urls:
            self.fileChosen.emit(urls[0])


class StartPage(QScrollArea):
    fileChosen = Signal(str)
    startRequested = Signal()
    cancelRequested = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName("PageScroll")
        self.setWidgetResizable(True)
        self.setFrameShape(QFrame.NoFrame)
        inner = QWidget()
        inner.setObjectName("PageInner")
        self.setWidget(inner)
        outer = QHBoxLayout(inner)
        col = QVBoxLayout()
        col.setSpacing(20)
        col.setContentsMargins(24, 56, 24, 40)
        holder = QWidget()
        holder.setMaximumWidth(680)
        holder.setLayout(col)
        outer.addStretch(1)
        outer.addWidget(holder, 10)
        outer.addStretch(1)

        self.drop = DropZone()
        self.drop.fileChosen.connect(self.fileChosen)
        col.addWidget(self.drop)

        # 판별 결과 + 진행률
        self.info = panel()
        il = QVBoxLayout(self.info)
        il.setContentsMargins(20, 18, 20, 18)
        il.setSpacing(12)
        self.name = label("", None)
        self.name.setStyleSheet("font-size: 15px; font-weight: 600;")
        il.addWidget(self.name)
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        self.fields = {}
        for i, k in enumerate(["형식", "인코딩", "크기", "변수"]):
            box = QVBoxLayout()
            box.setSpacing(2)
            box.addWidget(label(k, "sub"))
            v = label("-")
            box.addWidget(v)
            self.fields[k] = v
            grid.addLayout(box, 0, i)
            grid.setColumnStretch(i, 1)        # 네 칸 같은 너비 (내용 길이로 위치가 움직이지 않게)
        il.addLayout(grid)
        prog = QHBoxLayout()
        self.progress = QProgressBar()
        self.progress.setRange(0, 1000)
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.cancel_btn = button("취소")
        prog.addWidget(self.progress, 1)
        prog.addWidget(self.cancel_btn)
        il.addLayout(prog)
        self.status = label("", "sub", True)
        il.addWidget(self.status)
        self.notice = label("", "warn", True)      # 잠깐 보여주는 안내 (진행 문구에 덮이지 않게 따로 둠)
        self.notice.hide()
        il.addWidget(self.notice)
        self._notice_timer = QTimer(self)
        self._notice_timer.setSingleShot(True)
        self._notice_timer.timeout.connect(self.notice.hide)
        foot = QHBoxLayout()
        foot.addStretch(1)
        self.start_btn = button("분석 시작", "primary")
        self.start_btn.setEnabled(False)
        foot.addWidget(self.start_btn)
        il.addLayout(foot)
        self.info.hide()
        col.addWidget(self.info)
        self.cancel_btn.clicked.connect(self.cancelRequested)
        self.start_btn.clicked.connect(self.startRequested)

        # 최근 파일
        self.recent_box = panel()
        rl = QVBoxLayout(self.recent_box)
        rl.setContentsMargins(20, 14, 20, 10)
        rl.addWidget(label("최근 파일", "sub"))
        self.recent = QListWidget()
        self.recent.setStyleSheet("QListWidget { border: none; }")
        self.recent.setFixedHeight(140)
        rl.addWidget(self.recent)
        self.recent.itemClicked.connect(lambda it: self.fileChosen.emit(it.data(Qt.UserRole)))
        col.addWidget(self.recent_box)
        col.addStretch(1)

    def set_recent(self, paths):
        self.recent.clear()
        shown = [p for p in paths if os.path.exists(p)][:8]
        for p in shown:
            it = QListWidgetItem(f"{os.path.basename(p)}    {os.path.dirname(p)}")
            it.setData(Qt.UserRole, p)
            it.setToolTip(p)
            self.recent.addItem(it)
        self.recent_box.setVisible(bool(shown))

    def show_detected(self, info):
        self.info.show()
        self.name.setText(os.path.basename(info.path))
        self.fields["형식"].setText(info.file_type.upper())
        self.fields["인코딩"].setText(info.encoding or (f"시트 {len(info.sheets)}개" if info.sheets else "-"))
        self.fields["크기"].setText(f"{info.size_bytes / 2**20:,.1f} MB")
        self.fields["변수"].setText("-")
        self.start_btn.setEnabled(False)
        self.progress.setValue(0)

    def set_loading(self, on, text=""):
        self.progress.setVisible(on)
        self.cancel_btn.setVisible(on)
        self.status.setText(text)
        self.status.setProperty("role", "sub")

    def set_progress(self, p, text):
        self.progress.setValue(int(p * 1000))
        self.status.setText(text)

    def show_loaded(self, df, kinds, detail):
        from collections import Counter
        c = Counter(kinds.values())
        self.fields["크기"].setText(f"{len(df):,}행 × {df.shape[1]}열")
        self.fields["변수"].setText(" · ".join(f"{k.replace(' 후보', '')} {n}" for k, n in c.items()))
        self.set_loading(False, detail)
        self.start_btn.setEnabled(True)

    def flash(self, text, ms=5000):
        """진행 문구는 그대로 두고, 그 아래에 안내를 잠깐 보여줍니다."""
        self.notice.setText(text)
        self.notice.show()
        self._notice_timer.start(ms)

    def show_error(self, text):
        self.info.show()
        self.set_loading(False, "")
        self.status.setText(f"<span style='color:#8A4B0F'>{text}</span>")
        self.start_btn.setEnabled(False)


class MainPage(QWidget):
    def __init__(self):
        super().__init__()
        self.setObjectName("Page")
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # 왼쪽 사이드바 (흰색, 다크 모드에서도 유지)
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(290)
        sl = QVBoxLayout(side)
        sl.setContentsMargins(16, 16, 16, 16)
        sl.setSpacing(18)
        self.columns = ColumnPanel()
        self.menu = MethodMenu()
        sl.addWidget(self.columns)
        sl.addWidget(self.menu, 1)
        root.addWidget(side)

        # 가운데 + 아래 결과 세션 (경계를 끌어서 높이 조절)
        split = QSplitter(Qt.Vertical)
        split.setHandleWidth(6)
        center = QWidget()
        center.setObjectName("Page")
        cl = QVBoxLayout(center)
        cl.setContentsMargins(24, 20, 24, 14)
        cl.setSpacing(14)
        fp = panel()
        fl = QVBoxLayout(fp)
        fl.setContentsMargins(16, 12, 16, 12)
        self.filters = FilterBar()
        fl.addWidget(self.filters)
        cl.addWidget(fp)
        ap = panel()
        al = QVBoxLayout(ap)
        al.setContentsMargins(20, 16, 20, 14)
        self.bar = AnalysisBar()
        al.addWidget(self.bar)
        cl.addWidget(ap)
        rp = panel()
        rl = QVBoxLayout(rp)
        rl.setContentsMargins(20, 6, 20, 16)
        self.tabs = ResultTabs()
        rl.addWidget(self.tabs)
        cl.addWidget(rp, 1)
        split.addWidget(center)
        self.session = SessionPanel()
        split.addWidget(self.session)
        split.setStretchFactor(0, 1)
        split.setSizes([700, 170])
        split.setCollapsible(0, False)
        root.addWidget(split, 1)
