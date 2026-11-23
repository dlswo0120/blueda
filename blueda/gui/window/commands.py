"""결과 세션 명령(help, show, rows, dates, history, clear, theme)과 내보내기(Excel·CSV·로그)

MainWindow가 이 클래스를 함께 상속합니다 (app.py 참고). self는 MainWindow입니다.
"""

import os
from datetime import datetime

from PySide6.QtWidgets import (
    QFileDialog,
)


HELP = [
    ("help", "명령 목록"),
    ("show", "마지막 결과의 지표를 여기에 출력"),
    ("clear", "결과 세션 비우기"),
    ("theme dark / theme light", "화면 모드 바꾸기"),
    ("rows", "지금 조건에 맞는 행 수"),
    ("dates", "날짜 문자열 열을 날짜형으로 바꾸는 창 열기"),
    ("history", "조회 히스토리 보기 (기록을 누르면 그때 조건으로 되돌림)"),
]




class CommandsMixin:
    # ------------------------------------------------------------------ 명령
    def _command(self, text):
        t = text.strip()
        self.main.session.add("INFO", f"> {t}", datetime.now().strftime("%H:%M:%S"))
        low = t.lower()
        if low.split(" ")[0] in {c.split(" ")[0] for c, _ in HELP} and low != "history":
            self.record("command", t)
        if low == "history":
            self.main.session.show_page(1)
        elif low == "help":
            for cmd, desc in HELP:
                self.log("INFO", f"{cmd:<26} {desc}")
            self.log("INFO", "분석 명령(예: 성별 처리일수 t검정)은 5단계에서 지원합니다.")
        elif low == "clear":
            self.main.session.list.clear()
        elif low in ("theme dark", "theme light"):
            self.ui["theme"] = low.split()[1]
            self.apply_theme()
            self._save_settings()
        elif low == "dates" and self.bd is not None:
            self.offer_date_conversion(announce_none=True)
        elif low == "rows" and self.df is not None:
            self.log("INFO", f"조건에 맞는 행: {self.current_scope().count_rows(self.df):,} / {len(self.df):,}")
        elif low == "show" and self.bd and self.bd.results:
            r = self.bd.results[-1]
            self.log("INFO", f"[{r.name}] {r.message}")
            for k, v in r.metrics.items():
                self.log("INFO", f"  {k}: {v}")
        else:
            self.log("UNSUPPORTED", f"'{t}' — 분석 명령 해석은 5단계에서 지원합니다. help로 지금 쓸 수 있는 명령을 보세요.")

    # ------------------------------------------------------------------ 내보내기
    def _need_results(self):
        if not self.bd or not self.bd.results:
            self.log("FAIL", "내보낼 분석 결과가 없습니다. 먼저 분석을 실행하세요.")
            return False
        return True

    def export_excel(self):
        if not self._need_results():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Excel로 저장", "BLUEDA_결과.xlsx", "Excel (*.xlsx)")
        if path:
            try:
                self.bd.export_excel(path)
                self.log("SUCCESS", f"Excel 저장  {path}")
                self.record("export", f"Excel 저장 · {os.path.basename(path)}")
            except Exception as e:
                self.log("FAIL", f"Excel 저장 실패: {e}")

    def export_csv(self):
        if not self._need_results():
            return
        d = QFileDialog.getExistingDirectory(self, "CSV를 저장할 폴더")
        if d:
            paths = self.bd.export_csv(d)
            self.log("SUCCESS", f"CSV {len(paths)}개 저장  {d}")
            self.record("export", f"CSV {len(paths)}개 저장")

    def save_logs(self):
        if not self._need_results():
            return
        paths = self.bd.save()
        self.log("SUCCESS", "로그 저장  " + " · ".join(os.path.basename(p) for p in paths.values()))
        self.record("export", "분석 로그 저장")

    def report(self):
        self.log("UNSUPPORTED", "보고서(Word·PDF) 만들기는 4단계에서 지원합니다. 지금은 내보내기 → Excel을 쓰세요.")

