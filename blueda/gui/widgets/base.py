"""공통 부품: 글자·버튼·패널 만들기, 작업 스레드(Worker), 줄바꿈 배치(FlowLayout), 팝업 창(Popup)"""


from PySide6.QtCore import QPoint, QRect, QSize, Qt, QThread, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QFrame, QLabel, QLayout, QPushButton, QVBoxLayout,
)



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
