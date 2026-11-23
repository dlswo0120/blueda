"""날짜형 변환: 날짜 문자열 열을 알려주고 사용자가 고른 열만 pd.to_datetime으로 변환

MainWindow가 이 클래스를 함께 상속합니다 (app.py 참고). self는 MainWindow입니다.
"""


from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QDialog,
)

from ..dialogs import ColumnChooser


class DatesMixin:
    # ------------------------------------------------------------------ 날짜형 변환 (사용자 선택)
    """날짜형 변환: 날짜처럼 보이는 글자 열을 알려주고, 사용자가 고른 열만 바꿉니다 (자동으로 바꾸지 않음)."""
    def offer_date_conversion(self, announce_none=False):
        """날짜 문자열 열이 있으면 바꿀 열을 고르는 창을 띄웁니다. 창은 화면을 막지 않습니다(open)."""
        if self.bd is None:
            return
        cands = self.bd.date_candidates()
        if not cands:
            if announce_none:
                self.log("INFO", "날짜 문자열로 보이는 열이 없습니다.")
            return
        dlg = ColumnChooser(
            cands, self, title="날짜형으로 바꾸기",
            message="아래 열은 날짜처럼 보이지만 글자로 저장돼 있습니다.\n"
                    "날짜형으로 바꾸면 기간 필터와 월별 집계를 쓸 수 있습니다.\n"
                    "코드(예: 20230103이 주문번호)라면 체크를 빼세요.",
            ok_text="바꾸기", cancel_text="그대로 두기")
        dlg.finished.connect(lambda code: self._dates_chosen(dlg, code))
        self.date_dialog = dlg
        dlg.open()

    def _dates_chosen(self, dlg, code):
        """날짜 창을 닫은 뒤 처리합니다.

        - 분석이 도는 중이면 바꾸지 않음 (같은 데이터를 동시에 바꾸면 충돌)
        - 이슈 점검이 도는 중이면 끝난 뒤 다시 시도
        - 바꾼 뒤: 열 종류를 '날짜'로, 필터는 그대로 두고 데이터만 갱신(update_data), 이슈 다시 계산, 히스토리 기록
        """
        chosen = dlg.chosen() if code == QDialog.Accepted else []
        if chosen:
            main, bg = self._running()
            if main is not None:
                # 분석 스레드가 같은 데이터를 읽는 중에 열을 바꾸면 결과가 섞이거나 오류가 날 수 있음
                self.log("INFO", "분석이 끝난 뒤에 날짜를 바꿀 수 있습니다. 끝나면 'dates' 명령으로 다시 여세요.")
                return
            if bg:                                        # 이슈 점검(몇 초)은 끝나기를 기다렸다가 바꿈
                bg[0].finished.connect(lambda d=dlg, c=code: QTimer.singleShot(50, lambda: self._dates_chosen(d, c)))
                return
        if not chosen:
            self.log("INFO", "날짜형 변환을 건너뛰었습니다. 나중에 'dates' 명령으로 다시 열 수 있습니다.")
            return
        r = self.bd.convert_dates(chosen)
        self._log_result(r, len(self.bd.results) - 1)
        self.main.tabs.show_result(r)
        if r.status == "SUCCESS":
            for c in chosen:
                self.kinds[c] = "날짜"
            # set_data를 쓰면 사용자가 걸어 둔 필터가 지워지므로, 데이터만 갱신하는 update_data 사용
            self.main.filters.update_data(self.df, self.kinds, self.cfg.dropdown_max_values)
            self._scope_changed()
            self._refresh_data_tab()
            self.refresh_issues()                       # 날짜를 바꿨으니 이슈 다시 계산
            self.record("dates", "날짜형 변환 · " + ", ".join(map(str, chosen)))

