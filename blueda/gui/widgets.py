"""화면 부품: 열 상자, 분석 메뉴, 필터 칩, 분석 설정 줄, 결과 탭, 결과 세션, 작업 스레드."""

import pandas as pd
from PySide6.QtCore import QPoint, QRect, QSize, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QDoubleValidator, QFont, QGuiApplication, QIntValidator
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel,
    QLayout, QLineEdit, QListWidget, QListWidgetItem, QMenu, QPlainTextEdit, QPushButton, QScrollArea,
    QSizePolicy, QTabWidget, QTableView, QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
)

from .. import methods as M
from ..variables import KINDS
from . import theme
from .models import DataFrameModel


# ======================================================================
# 공통
# ======================================================================
def label(text, role=None, wrap=False):
    w = QLabel(text)
    if role:
        w.setProperty("role", role)
    w.setWordWrap(wrap)
    return w


def button(text, kind=None, checkable=False):
    b = QPushButton(text)
    if kind:
        b.setProperty("kind", kind)
    b.setCheckable(checkable)
    b.setCursor(Qt.PointingHandCursor)
    return b


def panel():
    f = QFrame()
    f.setProperty("panel", True)
    return f


def repolish(w):
    """동적 속성을 바꾼 뒤 스타일을 다시 적용."""
    w.style().unpolish(w)
    w.style().polish(w)


class Worker(QThread):
    """무거운 작업(파일 읽기, 분석)을 별도 스레드에서 돌려 화면이 멈추지 않게 합니다."""
    progress = Signal(float)
    done = Signal(object)
    failed = Signal(str)

    def __init__(self, fn, *args, **kwargs):
        super().__init__()
        self._fn, self._args, self._kwargs = fn, args, kwargs
        self._cancel = False

    def cancel(self):
        self._cancel = True

    def is_cancelled(self):
        return self._cancel

    def run(self):
        try:
            self.done.emit(self._fn(*self._args, **self._kwargs))
        except Exception as e:  # 스레드 안의 오류는 화면에 문장으로 전달
            self.failed.emit(f"{type(e).__name__}: {e}")


class FlowLayout(QLayout):
    """줄이 넘치면 다음 줄로 넘어가는 가로 배치 (필터 칩용)."""

    def __init__(self, parent=None, spacing=8):
        super().__init__(parent)
        self._items = []
        self.setSpacing(spacing)
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, i):
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for it in self._items:
            size = size.expandedTo(it.minimumSize())
        return size

    def _do_layout(self, rect, test):
        x, y, line_h = rect.x(), rect.y(), 0
        sp = self.spacing()
        for it in self._items:
            if it.widget() is not None and it.widget().isHidden():   # 일부러 숨긴 것만 건너뜀
                continue
            hint = it.sizeHint()
            if x + hint.width() > rect.right() and line_h > 0:
                x, y, line_h = rect.x(), y + line_h + sp, 0
            if not test:
                it.setGeometry(QRect(QPoint(x, y), hint))
            x += hint.width() + sp
            line_h = max(line_h, hint.height())
        return y + line_h - rect.y()


class Popup(QFrame):
    """버튼 아래에 뜨는 작은 창. 바깥을 누르면 닫힙니다."""

    def __init__(self, width=260, parent=None):
        super().__init__(parent, Qt.Popup)
        self.setObjectName("Popup")
        self.setFixedWidth(width)
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(10, 10, 10, 10)
        self.box.setSpacing(8)

    def show_below(self, anchor):
        self.adjustSize()
        pos = anchor.mapToGlobal(QPoint(0, anchor.height() + 4))
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        x = min(pos.x(), area.right() - self.width() - 8)        # 화면 오른쪽 밖으로 나가지 않게
        y = pos.y() if pos.y() + self.height() < area.bottom() else anchor.mapToGlobal(QPoint(0, -self.height() - 4)).y()
        self.move(max(area.left() + 8, x), y)
        self.show()


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
        self.df, self.kinds, self.max_direct = df, kinds, max_direct
        self.filters, self.query = [], ""
        self.direct.clear()
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

    def _remove(self, i):
        self.filters.pop(i)
        self._changed()

    # ---- 조건 추가 ----
    def _add(self):
        pop = ColumnPickerPopup(self.df, self.kinds, self)
        pop.picked.connect(lambda c: self._open_editor(c, None, self.add_btn))
        pop.show_below(self.add_btn)

    def _open_editor(self, column, index, anchor):
        from ..scope import Filter
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
        from ..scope import Filter
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
        from ..scope import Filter
        self.filters.append(Filter(c, "iqr_inside"))
        self._changed()

    def _apply_query(self):
        self.query = self.direct.text().strip()
        self.changed.emit()


# ======================================================================
# 가운데: 분석 설정 줄
# ======================================================================
class MultiColumnButton(QPushButton):
    """여러 열 고르기 (다중회귀의 설명 변수)."""
    changedColumns = Signal(list)

    def __init__(self):
        super().__init__("고르기  ▾")
        self.setProperty("kind", "chip")
        self.columns = []
        self.options = []
        self.clicked.connect(self._open)

    def set_options(self, options):
        self.options = list(options)
        self.columns = [c for c in self.columns if c in self.options]
        self._label()

    def _label(self):
        n = len(self.columns)
        self.setText(("고르기" if n == 0 else ", ".join(map(str, self.columns)) if n <= 2 else f"{self.columns[0]} 외 {n - 1}") + "  ▾")

    def _open(self):
        pop = ValuePopup(pd.Series(self.options, dtype=object), self.columns, parent=self)
        for i in range(pop.list.count()):              # 열 목록이라 행 수 표시는 빼기
            it = pop.list.item(i)
            it.setText(str(it.data(Qt.UserRole)))
        pop.search.setPlaceholderText(f"열 검색 ({len(self.options)}개)")

        def done(cols):
            self.columns = cols
            self._label()
            self.changedColumns.emit(cols)
        pop.applied.connect(done)
        pop.show_below(self)


class AnalysisBar(QWidget):
    runRequested = Signal(str, dict)
    switchRequested = Signal(str)
    paramsChanged = Signal()

    def __init__(self):
        super().__init__()
        self.method = None
        self.widgets = {}
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
        self.fields = QHBoxLayout()
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
        self.method = method
        self.title.setText(method.label)
        self.desc.setText(method.desc)
        while self.fields.count():
            item = self.fields.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                lay = item.layout()
                while lay.count():
                    w = lay.takeAt(0).widget()
                    if w:
                        w.deleteLater()
        self.widgets = {}
        for p in method.params:
            col = QVBoxLayout()
            col.setSpacing(4)
            col.addWidget(label(p.label, "sub"))
            if p.kind in (M.COL_NUM, M.COL_CAT, M.COL_ANY):
                w = QComboBox()
                w.setMinimumWidth(140)
                options = M.columns_for(p.kind, kinds)
                if options:
                    w.addItem("선택", None)
                    for c in options:
                        w.addItem(str(c), c)
                else:
                    w.addItem("맞는 열 없음", None)
                w.currentIndexChanged.connect(self._changed)
                if p.name == "column" and method.key == "ci_proportion":
                    w.currentIndexChanged.connect(lambda _=0, df=df: self._fill_values(df))
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
            self.fields.addLayout(col)
            self.widgets[p.name] = (p, w)
        self._changed()

    def _fill_values(self, df):
        _, cw = self.widgets["column"]
        _, vw = self.widgets["category"]
        vw.clear()
        c = cw.currentData()
        if c is not None:
            for v in df[c].value_counts().head(200).index:
                vw.addItem(str(v), v)

    def params(self):
        out = {}
        for name, (p, w) in self.widgets.items():
            if isinstance(w, MultiColumnButton):
                out[name] = list(w.columns)
            elif isinstance(w, QComboBox):
                out[name] = w.currentData()
            else:
                out[name] = w.text().strip()
        return out

    def needed_columns(self):
        cols = []
        for name, (p, _) in self.widgets.items():
            v = self.params()[name]
            if p.kind in (M.COL_NUM, M.COL_CAT, M.COL_ANY) and v:
                cols.append(v)
            elif p.kind == M.COL_MULTI:
                cols += v
        return list(dict.fromkeys(cols))

    def _changed(self, *_):
        self._timer.start()

    def set_check(self, check, running=False):
        self.run_btn.setEnabled(bool(check.ok) and not running)
        self.warn.setText(check.message)
        self.warn.setVisible(bool(check.message))
        self._alt = check.alternative
        if check.alternative:
            alt = M.BY_KEY[check.alternative]
            self.alt_btn.setText(f"{alt.label}(으)로 바꾸기")
            self.alt_btn.show()
        else:
            self.alt_btn.hide()

    def _run(self):
        if self.method:
            self.runRequested.emit(self.method.key, self.params())


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
        from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
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
                    fig.set_dpi(90)                       # 화면용: 글자가 너무 커지지 않게
                    canvas = FigureCanvasQTAgg(fig)
                    canvas.setMinimumHeight(320)
                    canvas.setToolTip(name)
                    self._canvases.append(canvas)
                    figs.addWidget(canvas, i // 2, i % 2)
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


# ======================================================================
# 아래: 결과 세션 (터미널 스타일)
# ======================================================================
class SessionPanel(QFrame):
    resultClicked = Signal(int)
    command = Signal(str)

    def __init__(self):
        super().__init__()
        self.setObjectName("SessionBox")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 6, 12, 6)
        lay.setSpacing(0)
        self.list = QListWidget()
        self.list.setObjectName("Session")
        mono = QFont()
        mono.setFamilies(theme.MONO_FAMILIES)
        mono.setPointSize(10)
        self.list.setFont(mono)
        self.list.setToolTip("결과 줄을 누르면 그 결과를 다시 봅니다")
        lay.addWidget(self.list, 1)
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

    def _click(self, it):
        idx = it.data(Qt.UserRole)
        if idx is not None:
            self.resultClicked.emit(idx)

    def _enter(self):
        t = self.input.text().strip()
        self.input.clear()
        if t:
            self.command.emit(t)

