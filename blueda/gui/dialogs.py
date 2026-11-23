"""설정 창(SettingsDialog)과 열 고르기 창(ColumnChooser)."""

import os

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QHBoxLayout, QLineEdit,
    QListWidget, QListWidgetItem, QRadioButton, QScrollArea, QVBoxLayout, QWidget,
)

from ..settings import EDITABLE
from .widgets import button, label


class SettingsDialog(QDialog):
    """오른쪽에 뜨는 설정 패널."""

    def __init__(self, cfg, ui, parent=None):
        super().__init__(parent)
        self.setWindowTitle("설정")
        self.setMinimumWidth(380)
        self.cfg, self.ui = cfg, ui
        lay = QVBoxLayout(self)
        form = QFormLayout()
        form.setVerticalSpacing(10)
        self.inputs = {}
        self.ranges = {}
        for key, name, desc, lo, hi, step in EDITABLE:
            cur = getattr(cfg, key)
            # 숫자 칸(QSpinBox)은 테두리 스타일을 주면 글자가 사라지는 Qt 문제가 있어 일반 입력칸 사용
            w = QLineEdit(f"{cur:,}" if isinstance(cur, int) else f"{cur:g}")
            w.setToolTip(f"{desc} · 허용 범위 {lo:,g} ~ {hi:,g}")
            self.ranges[key] = (lo, hi, isinstance(cur, int))
            box = QVBoxLayout()
            box.setSpacing(2)
            box.addWidget(w)
            box.addWidget(label(desc, "sub", True))
            form.addRow(name, box)
            self.inputs[key] = w
        mode = QHBoxLayout()
        self.light = QRadioButton("라이트")
        self.dark = QRadioButton("다크")
        (self.dark if ui.get("theme") == "dark" else self.light).setChecked(True)
        mode.addWidget(self.light)
        mode.addWidget(self.dark)
        form.addRow("화면 모드", mode)
        logrow = QHBoxLayout()
        self.log_dir = label(os.path.abspath(cfg.log_dir), "sub", True)
        change = button("바꾸기", "link")
        change.clicked.connect(self._pick_dir)
        logrow.addWidget(self.log_dir, 1)
        logrow.addWidget(change)
        form.addRow("로그 저장 위치", logrow)
        hist = QVBoxLayout()
        hist.setSpacing(2)
        self.hist_on = QCheckBox("조회 히스토리 기록")
        self.hist_on.setChecked(ui.get("history_enabled", True))
        self.hist_mask = QCheckBox("필터 값 가리기 (권장)")
        self.hist_mask.setChecked(ui.get("history_mask", True))
        hist.addWidget(self.hist_on)
        hist.addWidget(self.hist_mask)
        note = label("가리면 고른 값(예: 이름)이 기록 파일에 원문으로 남지 않습니다. "
                     "같은 파일을 열었을 때만 복원됩니다.", "sub", True)
        note.setMinimumWidth(300)
        hist.addWidget(note)
        form.addRow("히스토리", hist)
        # 항목이 많아 창이 길어지므로, 화면이 작거나 배율이 커도 넘치지 않게 스크롤 영역에 넣음
        holder = QWidget()
        holder.setLayout(form)
        scroll = QScrollArea()
        scroll.setWidget(holder)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        avail = QApplication.primaryScreen().availableGeometry().height() if QApplication.primaryScreen() else 900
        scroll.setMinimumHeight(min(holder.sizeHint().height() + 8, int(avail * 0.7)))
        scroll.setMinimumWidth(holder.sizeHint().width() + scroll.verticalScrollBar().sizeHint().width() + 8)
        lay.addWidget(scroll, 1)
        lay.addWidget(label("기준값들은 관례입니다. 바꾸면 이후 실행하는 분석부터 적용됩니다.", "sub", True))
        self.error = label("", "warn", True)
        self.error.hide()
        lay.addWidget(self.error)
        btns = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Save).setText("저장")
        btns.button(QDialogButtonBox.Cancel).setText("취소")
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def _pick_dir(self):
        d = QFileDialog.getExistingDirectory(self, "로그 저장 위치", self.log_dir.text())
        if d:
            self.log_dir.setText(d)

    def values(self):
        """입력값 검사. 문제가 있으면 (None, 오류 문장)."""
        out = {}
        for key, name, *_ in EDITABLE:
            lo, hi, is_int = self.ranges[key]
            text = self.inputs[key].text().strip().replace(",", "")
            try:
                v = int(float(text)) if is_int else float(text)
            except ValueError:
                return None, f"{name}: 숫자를 입력하세요."
            if not lo <= v <= hi:
                return None, f"{name}: {lo:,g} ~ {hi:,g} 사이로 입력하세요."
            out[key] = v if is_int else round(v, 4)
        return out, ""

    def accept(self):
        vals, err = self.values()
        if vals is None:
            self.error.setText(err)
            self.error.show()
            return
        super().accept()

    def apply(self):
        vals, _ = self.values()
        for key, v in (vals or {}).items():
            setattr(self.cfg, key, v)
        self.cfg.log_dir = self.log_dir.text()
        self.ui["theme"] = "dark" if self.dark.isChecked() else "light"
        self.ui["history_enabled"] = self.hist_on.isChecked()
        self.ui["history_mask"] = self.hist_mask.isChecked()


class ColumnChooser(QDialog):
    """열을 체크해서 고르는 창. 기본은 '메모리가 부족할 때 일부 열만 읽기'이고, 날짜 변환에도 씁니다."""

    def __init__(self, columns, parent=None, title="읽을 열 고르기",
                 message="분석에 필요한 열만 고르면 메모리를 아낄 수 있습니다.", ok_text=None, cancel_text=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        lay = QVBoxLayout(self)
        lay.addWidget(label(message, None, True))
        self.list = QListWidget()
        for c in columns:
            it = QListWidgetItem(str(c))
            it.setData(Qt.UserRole, c)
            it.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
            it.setCheckState(Qt.Checked)
            self.list.addItem(it)
        lay.addWidget(self.list)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        if ok_text:
            btns.button(QDialogButtonBox.Ok).setText(ok_text)
        if cancel_text:
            btns.button(QDialogButtonBox.Cancel).setText(cancel_text)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)
        lay.addWidget(btns)

    def chosen(self):
        return [self.list.item(i).data(Qt.UserRole) for i in range(self.list.count())
                if self.list.item(i).checkState() == Qt.Checked]
