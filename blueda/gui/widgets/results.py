"""결과 탭(ResultTabs): 차트·지표·데이터·코드 탭, 표 보기, 차트 이미지(ChartView)"""


import pandas as pd
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QPlainTextEdit,
    QScrollArea, QSizePolicy, QTabWidget, QTableView, QVBoxLayout, QWidget,
)

from .. import theme
from ..models import DataFrameModel
from .base import button, label


# ======================================================================
# 가운데 아래: 결과 탭 (차트 / 지표 / 데이터 / 코드)
# ======================================================================
def table_view(df, show_index=True):
    v = QTableView()
    model = DataFrameModel(df, show_index=show_index, parent=v)
    v.setModel(model)
    v.setAlternatingRowColors(True)
    v.setSelectionBehavior(QAbstractItemView.SelectItems)
    v.verticalHeader().setDefaultSectionSize(26)
    v.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
    v.horizontalHeader().setStretchLastSection(False)
    v.resizeColumnsToContents()
    for i in range(model.columnCount()):
        v.setColumnWidth(i, min(max(v.columnWidth(i), 70), 360))
    if _has_long_text(df):
        # 긴 문장(전처리 점검 '내용' 등)은 잘리지 않게 줄바꿈하고, 마지막 열을 오른쪽 끝까지 늘림
        v.setWordWrap(True)
        v.setTextElideMode(Qt.ElideNone)
        v.horizontalHeader().setStretchLastSection(True)
        v.resizeRowsToContents()
        v.horizontalHeader().sectionResized.connect(lambda *_: _rewrap(v))
    return v, model


def _rewrap(v):
    """열 너비가 바뀌면 줄바꿈 높이를 다시 계산하고, 높이를 맞춰둔 표면 높이도 다시 맞춤"""
    v.resizeRowsToContents()
    if v.property("fit_rows"):
        fit_table_height(v, v.property("fit_rows"))


def _has_long_text(df, limit=60):
    """문자열 칸 중 줄바꿈이 있거나 limit자보다 긴 값이 있는지 (앞 200행만 확인)"""
    head = df.head(200)
    for c in head.columns:
        if head[c].dtype == object or pd.api.types.is_string_dtype(head[c]):
            s = head[c].dropna().astype(str)
            if len(s) and (s.str.contains("\n").any() or (s.str.len() > limit).any()):
                return True
    return False


def fit_table_height(view, max_rows=12):
    """행이 max_rows 이하면 스크롤바 없이 표 전체가 보이는 높이로 맞춤."""
    rows = view.model().rowCount()
    shown = min(rows, max_rows)
    rows_h = sum(view.rowHeight(i) for i in range(shown)) or view.verticalHeader().defaultSectionSize()
    h = view.horizontalHeader().sizeHint().height() + rows_h    # 줄바꿈으로 높아진 행도 반영
    h += 2 * view.frameWidth() + 2
    if view.horizontalScrollBar().isVisible() or sum(view.columnWidth(i) for i in range(view.model().columnCount())) > 900:
        h += view.horizontalScrollBar().sizeHint().height()
    if rows <= max_rows:
        view.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
    view.setProperty("fit_rows", max_rows)
    view.setFixedHeight(h)


class ResultTabs(QTabWidget):
    def __init__(self):
        super().__init__()
        self.setDocumentMode(True)
        # 차트
        self.chart_scroll = QScrollArea()
        self.chart_scroll.setObjectName("ResultScroll")
        self.chart_scroll.setWidgetResizable(True)
        self.chart_scroll.setFrameShape(QFrame.NoFrame)
        self.addTab(self.chart_scroll, "차트")
        # 지표
        self.metric_scroll = QScrollArea()
        self.metric_scroll.setObjectName("ResultScroll")
        self.metric_scroll.setWidgetResizable(True)
        self.metric_scroll.setFrameShape(QFrame.NoFrame)
        self.addTab(self.metric_scroll, "지표")
        # 데이터
        data = QWidget()
        dl = QVBoxLayout(data)
        dl.setContentsMargins(0, 8, 0, 0)
        self.data_info = label("", "sub")
        dl.addWidget(self.data_info)
        self.data_view = QTableView()
        self.data_model = DataFrameModel(parent=self.data_view)
        self.data_view.setModel(self.data_model)
        self.data_view.setSortingEnabled(True)
        self.data_view.setAlternatingRowColors(True)
        self.data_view.verticalHeader().setDefaultSectionSize(26)
        self.data_view.horizontalHeader().setSortIndicatorShown(True)
        self.data_view.horizontalHeader().setResizeContentsPrecision(200)   # 열 너비는 앞 200행만 보고 맞춤
        self.data_model.loadedChanged.connect(self._data_info)
        dl.addWidget(self.data_view)
        self.addTab(data, "데이터")
        # 코드
        self.code = QPlainTextEdit()
        self.code.setObjectName("Code")
        self.code.setReadOnly(True)
        f = QFont()
        f.setFamilies(theme.MONO_FAMILIES)
        f.setPointSize(10)
        self.code.setFont(f)
        self.addTab(self.code, "코드")
        self._canvases = []
        self.show_empty()

    def _data_info(self, loaded, total):
        self.data_info.setText(f"{total:,}행 중 1~{loaded:,}행 표시 · 아래로 스크롤하면 이어서 불러옵니다 · 열 이름을 누르면 정렬"
                               if total else "데이터 없음")

    def set_data(self, df):
        self.data_model.set_dataframe(df)
        self.data_view.horizontalHeader().setSortIndicator(-1, Qt.AscendingOrder)
        self.data_view.resizeColumnsToContents()
        for i in range(self.data_model.columnCount()):
            self.data_view.setColumnWidth(i, min(max(self.data_view.columnWidth(i), 70), 300))

    @staticmethod
    def _page():
        page = QWidget()
        page.setObjectName("ResultPage")          # 흰 배경 (테마의 ResultPage 규칙)
        lay = QVBoxLayout(page)
        lay.setContentsMargins(0, 12, 8, 12)
        lay.setSpacing(14)
        return page, lay

    def _set_page(self, scroll, page):
        scroll.setWidget(page)
        scroll.viewport().setAutoFillBackground(False)

    def show_empty(self):
        page, lay = self._page()
        lay.addStretch(1)
        lay.addWidget(label("분석을 실행하면 결과가 여기에 나옵니다.", "muted"), 0, Qt.AlignCenter)
        lay.addStretch(1)
        self._set_page(self.chart_scroll, page)
        mp, ml = self._page()
        ml.addWidget(label("지표가 없습니다.", "muted"), 0, Qt.AlignCenter)
        ml.addStretch(1)
        self._set_page(self.metric_scroll, mp)
        self.code.setPlainText("")

    def show_result(self, r):
        self.show_results([r])

    def show_results(self, results):
        """한 번 실행에서 나온 결과를 모두 위아래로 이어서 보여줍니다 (예: 요약 통계 = 수치형 + 범주형)."""
        for c in self._canvases:
            c.deleteLater()
        self._canvases = []
        many = len(results) > 1
        # ---- 차트 탭: 결과마다 제목 · 해석 문장 · 핵심 지표 · 그림 · 주의사항 ----
        page, lay = self._page()
        for n, r in enumerate(results):
            if n:
                line = QFrame()
                line.setFrameShape(QFrame.HLine)
                line.setStyleSheet(f"color: {theme.LINE};")
                lay.addWidget(line)
            if many:
                lay.addWidget(label(f"<b>{r.name}</b>"))
            msg = label(r.message, None, True)
            msg.setTextInteractionFlags(Qt.TextSelectableByMouse)
            lay.addWidget(msg)
            if r.metrics:
                grid = QGridLayout()
                grid.setHorizontalSpacing(28)
                grid.setVerticalSpacing(10)
                for i, (k, v) in enumerate(list(r.metrics.items())[:8]):
                    cell = QVBoxLayout()
                    cell.setSpacing(0)
                    cell.setAlignment(Qt.AlignTop)
                    cell.addWidget(label(str(k), "sub"))
                    text = f"{v:,}" if isinstance(v, int) and not isinstance(v, bool) else str(v)
                    val = label(text, "big" if len(text) <= 24 else None, True)
                    val.setTextInteractionFlags(Qt.TextSelectableByMouse)
                    cell.addWidget(val)
                    grid.addLayout(cell, i // 4, i % 4)
                for c in range(4):
                    grid.setColumnStretch(c, 1)
                lay.addLayout(grid)
            if r.figures:
                figs = QGridLayout()
                figs.setSpacing(12)
                for i, (name, fig) in enumerate(r.figures.items()):
                    view = ChartView(fig)
                    view.setToolTip(name)
                    self._canvases.append(view)
                    figs.addWidget(view, i // 2, i % 2)
                lay.addLayout(figs)
            elif r.ok and not many:
                lay.addWidget(label("이 분석은 차트가 없습니다. 지표 탭에서 결과 표를 보세요.", "sub"))
            for note in r.notes:
                lay.addWidget(label("· " + note, "sub", True))
        lay.addStretch(1)
        self._set_page(self.chart_scroll, page)
        # ---- 지표 탭: 결과 표마다 복사 · CSV 저장 ----
        mp, ml = self._page()
        tables = [(f"{r.name} · {name}" if many else name, df) for r in results for name, df in r.tables.items()]
        if not tables:
            ml.addWidget(label("표로 된 결과가 없습니다.", "muted"))
        for name, df in tables:
            df = df if isinstance(df, pd.DataFrame) else pd.DataFrame(df)
            head = QHBoxLayout()
            head.addWidget(label(f"<b>{name}</b>  <span style='color:{theme.SUB}'>{len(df):,}행</span>"), 1)
            copy_b = button("복사", "link")
            csv_b = button("CSV 저장", "link")
            copy_b.clicked.connect(lambda _=False, d=df: QGuiApplication.clipboard().setText(d.to_csv(sep="\t")))
            csv_b.clicked.connect(lambda _=False, d=df, n=name: self._save_csv(d, n))
            head.addWidget(copy_b)
            head.addWidget(csv_b)
            ml.addLayout(head)
            view, _ = table_view(df)
            fit_table_height(view)
            ml.addWidget(view)
        ml.addStretch(1)
        self._set_page(self.metric_scroll, mp)
        codes = [f"# ===== {r.name} =====\n{r.code}" if many else r.code for r in results if r.code]
        self.code.setPlainText("\n\n".join(codes) or "# 이 결과에는 실행 코드가 없습니다.")

    def _save_csv(self, df, name):
        path, _ = QFileDialog.getSaveFileName(self, "CSV 저장", f"{name}.csv", "CSV (*.csv)")
        if path:
            df.to_csv(path, encoding="utf-8-sig")


class ChartView(QLabel):
    """PNG 차트를 칸 너비에 맞춰 비율을 지키며 보여줍니다 (창 크기를 바꾸면 다시 맞춤)."""

    def __init__(self, image):
        super().__init__()
        from PySide6.QtGui import QPixmap
        from ...result import ChartImage
        if not isinstance(image, ChartImage):          # 엔진 밖에서 만든 그림도 받음
            image = ChartImage(image)
        self._pix = QPixmap()
        self._pix.loadFromData(image.png, "PNG")
        self.setAlignment(Qt.AlignCenter)
        self.setMinimumSize(240, 160)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self._fit()

    def _fit(self):
        if self._pix.isNull():
            return
        w = max(240, min(self.width(), int(self._pix.width() * 1.1)))
        if w == getattr(self, "_last_w", None):        # 같은 너비면 다시 그리지 않음 (크기 조정 반복 방지)
            return
        self._last_w = w
        self.setPixmap(self._pix.scaledToWidth(w, Qt.SmoothTransformation))

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit()

    def heightForWidth(self, w):
        return int(self._pix.height() * min(w, self._pix.width() * 1.1) / max(1, self._pix.width()))

    def hasHeightForWidth(self):
        return True
