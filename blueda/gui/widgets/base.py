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
    """글자 부품. role은 스타일 이름(title, sub, muted, warn 등, theme.py 참고), wrap은 줄바꿈 여부."""
    w = QLabel(text)
    if role:
        w.setProperty("role", role)
    w.setWordWrap(wrap)
    return w


def button(text, kind=None, checkable=False):
    """버튼 부품. kind는 스타일 이름(primary 파란 버튼, link 글자 버튼, ghost 등), checkable은 눌림 상태 유지 여부."""
    b = QPushButton(text)
    if kind:
        b.setProperty("kind", kind)
    b.setCheckable(checkable)
    b.setCursor(Qt.PointingHandCursor)
    return b


def panel():
    """흰 바탕 둥근 상자(QFrame#Panel)와 그 안쪽 세로 배치를 돌려줍니다."""
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
        """fn(*args, **kwargs)를 별도 스레드에서 실행할 준비. start()를 부르면 run()이 실행됩니다.

        주의: 실행 중인 Worker의 참조를 놓치면(변수를 덮어쓰면) 프로그램이 강제 종료됩니다. 끝날 때까지 참조를 잡아 두세요.
        """
        super().__init__()
        self._fn, self._args, self._kwargs = fn, args, kwargs
        self._cancel = False

    def cancel(self):
        """취소 표시만 합니다. 실제로 멈추려면 fn이 is_cancelled()를 확인해야 합니다 (파일 읽기만 지원)."""
        self._cancel = True

    def is_cancelled(self):
        """취소가 요청됐는지."""
        return self._cancel

    def run(self):
        """스레드에서 fn을 실행하고 결과는 done, 오류는 failed('오류이름: 내용') 신호로 보냅니다."""
        try:
            self.done.emit(self._fn(*self._args, **self._kwargs))
        except Exception as e:  # 스레드 안의 오류는 화면에 문장으로 전달
            self.failed.emit(f"{type(e).__name__}: {e}")


class FlowLayout(QLayout):
    """줄이 넘치면 다음 줄로 넘어가는 가로 배치 (필터 칩용)."""

    def __init__(self, parent=None, spacing=8):
        """가로로 놓다가 줄이 넘치면 다음 줄로 넘기는 배치 (필터 칩용). Qt에 기본으로 없는 배치라 직접 구현했습니다."""
        super().__init__(parent)
        self._items = []
        self.setSpacing(spacing)
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item):
        """항목을 끝에 추가합니다 (Qt 배치 규약)."""
        self._items.append(item)

    def count(self):
        """항목 수."""
        return len(self._items)

    def itemAt(self, i):
        """i번째 항목 (없으면 None)."""
        return self._items[i] if 0 <= i < len(self._items) else None

    def takeAt(self, i):
        """i번째 항목을 빼서 돌려줍니다."""
        return self._items.pop(i) if 0 <= i < len(self._items) else None

    def expandingDirections(self):
        """가로·세로로 늘어나지 않음."""
        return Qt.Orientations(0)

    def hasHeightForWidth(self):
        """너비에 따라 높이가 정해지는 배치임을 Qt에 알립니다."""
        return True

    def heightForWidth(self, width):
        """주어진 너비에서 필요한 높이 (실제로 배치하지 않고 계산만)."""
        return self._do_layout(QRect(0, 0, width, 0), True)

    def setGeometry(self, rect):
        """주어진 영역 안에 항목들을 배치합니다."""
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self):
        """권장 크기 = 최소 크기."""
        return self.minimumSize()

    def minimumSize(self):
        """가장 큰 항목이 들어갈 크기 + 여백."""
        size = QSize()
        for it in self._items:
            size = size.expandedTo(it.minimumSize())
        return size

    def _do_layout(self, rect, test):
        """실제 배치 계산. test=True면 위치를 바꾸지 않고 높이만 계산합니다.

        숨긴 항목(isHidden)만 건너뜁니다. isVisible로 판단하면 창이 아직 안 보일 때 모든 항목을 건너뛰는 문제가 있었습니다.
        """
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
        """버튼 아래에 뜨는 작은 창. 바깥을 누르면 닫힙니다(Qt.Popup). 내용은 self.box에 넣습니다."""
        super().__init__(parent, Qt.Popup)
        self.setObjectName("Popup")
        self.setFixedWidth(width)
        self.box = QVBoxLayout(self)
        self.box.setContentsMargins(10, 10, 10, 10)
        self.box.setSpacing(8)

    def show_below(self, anchor):
        """anchor 아래에 띄웁니다. 화면 오른쪽·아래로 넘치면 안쪽으로 옮기거나 위쪽에 띄웁니다."""
        self.adjustSize()
        pos = anchor.mapToGlobal(QPoint(0, anchor.height() + 4))
        screen = QGuiApplication.screenAt(pos) or QGuiApplication.primaryScreen()
        area = screen.availableGeometry()
        x = min(pos.x(), area.right() - self.width() - 8)        # 화면 오른쪽 밖으로 나가지 않게
        y = pos.y() if pos.y() + self.height() < area.bottom() else anchor.mapToGlobal(QPoint(0, -self.height() - 4)).y()
        self.move(max(area.left() + 8, x), y)
        self.show()
