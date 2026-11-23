"""[!] 파일 이슈: 뒤에서 전처리 점검을 돌려 상단 버튼·팝업 목록을 갱신

MainWindow가 이 클래스를 함께 상속합니다 (app.py 참고). self는 MainWindow입니다.
"""


from PySide6.QtCore import Qt
from shiboken6 import isValid as shiboken_valid
from PySide6.QtWidgets import (
    QHBoxLayout,
)

from ...issues import NEED, collect_issues, summary
from ..widgets import Popup, Worker, button, label, repolish


class IssuesMixin:
    # ------------------------------------------------------------------ [!] 파일 이슈
    def refresh_issues(self):
        """전처리 점검을 뒤에서 돌려 이슈 버튼을 갱신합니다 (화면이 멈추지 않게 별도 스레드)."""
        if self.df is None:
            return
        self.issues = []
        self._issue_gen = getattr(self, "_issue_gen", 0) + 1
        gen = self._issue_gen
        w = Worker(collect_issues, self.df, self.cfg.outlier_iqr_k, self.cfg.missing_warn_ratio)
        w.done.connect(lambda issues, g=gen: self._issues_ready(issues, g))
        w.failed.connect(lambda msg: self.log("FAIL", f"이슈 점검 실패: {msg}"))
        # 이전 점검이 아직 돌고 있을 수 있으므로, 끝날 때까지 모든 스레드의 참조를 잡아 둡니다.
        # (참조를 놓치면 실행 중인 스레드가 지워지면서 프로그램이 강제 종료됨)
        self._bg_workers = [x for x in getattr(self, "_bg_workers", []) if x.isRunning()] + [w]
        self.issue_worker = w
        w.start()

    def _invalidate_issues(self):
        """새 파일을 열면 이슈 버튼을 지우고, 아직 도는 이전 파일 점검의 결과는 도착해도 버리게 합니다."""
        self._issue_gen = getattr(self, "_issue_gen", 0) + 1
        self.issues = []
        self.issue_btn.hide()

    def _issues_ready(self, issues, gen=None):
        if gen is None or gen != self._issue_gen:
            return                                 # 더 새 점검이 시작됐으면 이전 결과는 버림
        if not shiboken_valid(self.issue_btn):
            return                                 # 창이 이미 지워진 뒤 도착한 결과
        self.issues = issues
        text, level = summary(issues)
        self.issue_btn.setVisible(bool(text))
        self.issue_btn.setText(text)
        self.issue_btn.setProperty("level", "need" if level == NEED else "review")
        repolish(self.issue_btn)

    def show_issues(self):
        issues = getattr(self, "issues", [])
        pop = Popup(460, self)
        n_need = sum(i.level == NEED for i in issues)
        head = f"이 파일의 이슈 {len(issues)}개"
        if n_need:
            head += f" (확인 필요 {n_need}개)"
        pop.box.addWidget(label(head, None))
        for i in issues[:12]:
            row = QHBoxLayout()
            row.setSpacing(8)
            tag = label(i.level, "issue_need" if i.level == NEED else "issue_review")
            tag.setFixedWidth(64)
            row.addWidget(tag, 0, Qt.AlignTop)
            text = label(i.text, None, True)
            text.setFixedWidth(290)              # 너비를 정해야 줄바꿈 높이가 맞게 계산되어 잘리지 않음
            row.addWidget(text, 1)
            act = button("날짜로 바꾸기" if i.action == "dates" else "점검 보기", "link")
            act.setFixedWidth(84)
            act.clicked.connect(lambda _=False, a=i.action: (pop.close(), self._issue_action(a)))
            row.addWidget(act, 0, Qt.AlignTop)
            pop.box.addLayout(row)
        if len(issues) > 12:
            pop.box.addWidget(label(f"외 {len(issues) - 12}개는 전처리 점검 결과에서 볼 수 있습니다.", "sub"))
        foot = label("이슈가 있어도 분석은 할 수 있습니다. 결과를 해석할 때 참고하세요.", "sub", True)
        foot.setFixedWidth(440)
        pop.box.addWidget(foot)
        self.issue_popup = pop
        pop.show_below(self.issue_btn)

    def _issue_action(self, action):
        if action == "dates":
            self.offer_date_conversion(announce_none=True)
        else:
            self.choose_method("check")
            self.run_analysis("check", {})

