"""화면 회귀 테스트 (v0.5.3 회귀 테스트에서 추가)

커버리지가 낮았던 화면 기능을 사용자 조작 순서대로 확인합니다.
- 필터: '+ 조건' 열 고르기 → 값 창·범위 창, 칩 편집·삭제, 결측 제외, 이상값 후보 제외, 직접 입력
- 열 상자: 검색, 전체/해제, 오른쪽 클릭으로 종류 바꾸기
- 분석 설정 줄: 여러 열 칸, 값 칸, 대안 분석 버튼
- 명령, 내보내기(Excel·CSV·로그), 이슈 팝업 바로 가기
- 파일 읽기: 메모리 확인 창, 취소, 읽을 수 없는 파일
"""
import os

import numpy as np
import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QFileDialog, QMessageBox  # noqa: E402

from blueda.gui import app as A  # noqa: E402
from blueda.gui import widgets as W  # noqa: E402
from blueda.scope import Filter  # noqa: E402


@pytest.fixture
def csv_path(tmp_path):
    rng = np.random.default_rng(7)
    n = 1500
    d = pd.DataFrame({
        "접수번호": np.arange(1, n + 1), "시도": rng.choice(["서울", "부산", "대구", "경기"], n),
        "성별": rng.choice(["남", "여"], n), "나이": rng.integers(19, 80, n),
        "처리일수": np.r_[rng.gamma(3, 3, n - 3).round(1), [300.0, 280.0, 260.0]],
        "점수": np.where(rng.random(n) < 0.05, np.nan, rng.normal(70, 10, n).round(1)),
        "접수일": pd.date_range("2025-01-01", periods=n, freq="h").strftime("%Y-%m-%d"),
    })
    p = tmp_path / "민원.csv"
    d.to_csv(p, index=False, encoding="cp949")
    return str(p)


@pytest.fixture
def win(qtbot, tmp_path, csv_path):
    w = A.MainWindow(settings_path=str(tmp_path / "settings.json"))
    w.cfg.log_dir = str(tmp_path / "logs")
    qtbot.addWidget(w)
    w.show()
    w.open_file(csv_path)
    qtbot.waitUntil(lambda: w.df is not None and w.start.start_btn.isEnabled(), timeout=30000)
    w.start_analysis()
    if getattr(w, "date_dialog", None) is not None:
        w.date_dialog.reject()                       # 날짜 변환은 이 테스트들에서 하지 않음
    qtbot.waitUntil(lambda: not any(x.isRunning() for x in getattr(w, "_bg_workers", [])), timeout=20000)
    return w


def rows(w):
    return w.current_scope().count_rows(w.df)


def last_lines(w, n=5):
    lst = w.main.session.list
    return [lst.item(i).toolTip() or lst.item(i).text() for i in range(max(0, lst.count() - n), lst.count())]


def close_menu_soon(pick_text=None):
    """뜬 메뉴를 잠시 뒤 닫거나(pick_text가 있으면 그 항목을 고름). QMenu.exec는 바꿔치기가 안 돼서 실제로 띄운 뒤 조작."""
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    def act():
        m = QApplication.activePopupWidget()
        if m is None:
            QTimer.singleShot(50, act)
            return
        target = next((a for a in m.actions() if pick_text and a.text() == pick_text), None)
        if target:
            target.trigger()
        m.close()
    QTimer.singleShot(50, act)


def newest(parent, cls):
    found = parent.findChildren(cls)
    assert found, f"{cls.__name__} 창이 열리지 않음"
    return found[-1]


def run_and_wait(qtbot, w):
    before = len(w.bd.results)
    qtbot.wait(300)                                   # 실행 전 점검(200ms 지연)이 끝나길 기다림
    assert w.main.bar.run_btn.isEnabled(), w.main.bar.warn.text()
    w.main.bar.run_btn.click()
    qtbot.waitUntil(lambda: len(w.bd.results) > before and not w.worker.isRunning(), timeout=60000)
    qtbot.wait(50)


def pick(bar, name, value):
    combo = bar.widgets[name][1]
    i = combo.findData(value)
    assert i >= 0, (name, value)
    combo.setCurrentIndex(i)


# ── 필터 ────────────────────────────────────────────────
def test_filter_add_value_via_picker_edit_and_remove(qtbot, win):
    fb = win.main.filters
    total = len(win.df)
    fb._add()                                          # '+ 조건'
    picker = newest(fb, W.ColumnPickerPopup)
    picker.picked.emit("시도")                         # 열 고르기 → 값 창
    vp = newest(fb, W.ValuePopup)
    for i in range(vp.list.count()):
        it = vp.list.item(i)
        if it.data(Qt.UserRole) in ("서울", "부산"):
            it.setCheckState(Qt.Checked)
    vp._apply()
    assert [f.values for f in fb.filters] == [["서울", "부산"]] or sorted(fb.filters[0].values) == ["부산", "서울"]
    exp = int(win.df["시도"].isin(["서울", "부산"]).sum())
    assert rows(win) == exp < total
    assert win.history.entries[-1]["kind"] == "filter"
    # 칩 편집: 값 하나 빼기
    fb._edit(0, fb.add_btn)
    vp2 = newest(fb, W.ValuePopup)
    for i in range(vp2.list.count()):
        if vp2.list.item(i).data(Qt.UserRole) == "부산":
            vp2.list.item(i).setCheckState(Qt.Unchecked)
    vp2._apply()
    assert fb.filters[0].values == ["서울"]
    # 값 창에서 모두 해제하고 적용하면 조건이 지워짐
    fb._edit(0, fb.add_btn)
    vp3 = newest(fb, W.ValuePopup)
    vp3._clear()
    vp3._apply()
    assert fb.filters == [] and rows(win) == total


def test_filter_range_and_invalid_range(qtbot, win):
    fb = win.main.filters
    fb._open_editor("나이", None, fb.add_btn)
    rp = newest(fb, W.RangePopup)
    rp.lo.setText("60")
    rp.hi.setText("30")                                # 최소 > 최대
    rp._apply()
    assert fb.filters == [] and rp.error.text()        # 막고 이유 표시
    rp.hi.setText("70")
    rp._apply()
    assert (fb.filters[0].lo, fb.filters[0].hi) == (60, 70)
    assert rows(win) == int(win.df["나이"].between(60, 70).sum())


def test_filter_date_range_on_text_dates(qtbot, win):
    fb = win.main.filters
    fb._open_editor("접수일", None, fb.add_btn)
    rp = newest(fb, W.RangePopup)
    rp.lo.setText("2025-01-10")
    rp.hi.setText("2025-01-20")
    rp._apply()
    d = pd.to_datetime(win.df["접수일"].astype(str))
    assert rows(win) == int(d.between("2025-01-10", "2025-01-20").sum())


def test_notna_iqr_and_query(qtbot, win):
    fb = win.main.filters
    fb._add_notna()
    fb._add_notna()                                    # 두 번 눌러도 하나만
    assert sum(f.op == "notna" for f in fb.filters) == 1
    close_menu_soon("처리일수")                        # 메뉴가 뜨면 '처리일수'를 고름
    fb._add_iqr()
    assert any(f.op == "iqr_inside" and f.column == "처리일수" for f in fb.filters)
    sub, _ = win.current_scope().apply(win.df)          # apply는 (범위 적용 데이터, 설명 줄들)
    assert sub["처리일수"].max() < 260                  # 극단값 3개가 빠짐
    fb.direct.setText("나이 >= 50")
    fb._apply_query()
    assert win.current_scope().apply(win.df)[0]["나이"].min() >= 50
    fb.direct.setText("없는열 > 3")                    # 잘못된 조건
    fb._apply_query()
    assert any("FAIL" in l or "조건" in l for l in last_lines(win, 3))


# ── 열 상자 ──────────────────────────────────────────────
def test_column_panel_search_select_and_type_change(qtbot, win):
    cp = win.main.columns
    cp._filter("처리")
    visible = [cp.tree.topLevelItem(i).data(0, Qt.UserRole) for i in range(cp.tree.topLevelItemCount())
               if not cp.tree.topLevelItem(i).isHidden() and cp.tree.topLevelItem(i).data(0, Qt.UserRole)]
    assert visible == ["처리일수"]
    cp._filter("")
    cp._set_all(False)
    assert cp.selected() == []
    cp._set_all(True)
    assert set(cp.selected()) == set(win.df.columns)
    # 오른쪽 클릭 메뉴 → 종류 바꾸기 (나이를 범주형으로)
    it = next(cp.tree.topLevelItem(i) for i in range(cp.tree.topLevelItemCount())
              if cp.tree.topLevelItem(i).data(0, Qt.UserRole) == "나이")
    seen = []
    cp.typeChangeRequested.connect(lambda c, k: seen.append((c, k)))
    close_menu_soon("범주형")                          # 오른쪽 클릭 메뉴에서 '범주형'을 고름
    cp._context_menu(cp.tree.visualItemRect(it).center())
    assert seen == [("나이", "범주형")]
    assert win.kinds["나이"] == "범주형" and win.bd.var_types["나이"] == "범주형"
    win.choose_method("anova")
    assert win.main.bar.widgets["group_col"][1].findData("나이") >= 0   # 이제 그룹 열로 고를 수 있음


# ── 분석 설정 줄 ─────────────────────────────────────────
def test_multi_column_value_param_and_alternative(qtbot, win):
    bar = win.main.bar
    win.choose_method("multiple_regression")
    pick(bar, "y", "처리일수")
    bar.widgets["xs"][1].set_columns(["나이", "시도"])
    run_and_wait(qtbot, win)
    assert win.bd.results[-1].status == "SUCCESS" and win.bd.results[-1].name == "다중회귀"
    # 값 칸: 비율 신뢰구간은 고른 열의 값으로 채워짐
    win.choose_method("ci_proportion")
    pick(bar, "column", "성별")
    qtbot.wait(50)
    vals = [bar.widgets["category"][1].itemData(i) for i in range(bar.widgets["category"][1].count())]
    assert set(vals) >= {"남", "여"}
    # 대안 버튼: 그룹 4개 t검정 → 분산분석으로 바꾸기
    win.choose_method("t_test")
    pick(bar, "group_col", "시도")
    pick(bar, "value_col", "처리일수")
    qtbot.wait(300)
    assert not bar.run_btn.isEnabled() and bar.alt_btn.isVisible()
    bar.alt_btn.click()
    qtbot.wait(50)
    assert win.main.bar.method.key == "anova"


# ── 명령·내보내기 ────────────────────────────────────────
def test_commands(qtbot, win):
    win.choose_method("describe")
    run_and_wait(qtbot, win)
    for c, expect in [("help", "history"), ("show", "수치형"), ("rows", "조건에 맞는 행"),
                      ("없는명령", "5단계에서 지원")]:
        win._command(c)
        assert any(expect in l for l in last_lines(win, 30)), (c, last_lines(win, 5))
    win._command("theme dark")
    assert win.ui["theme"] == "dark"
    win._command("theme light")
    win._command("history")
    assert win.main.session.pages.currentIndex() == 1
    win._command("clear")
    assert win.main.session.list.count() == 0


def test_exports(qtbot, win, tmp_path, monkeypatch):
    win.export_excel()                                  # 결과 없음 → 안내
    assert any("내보낼 분석 결과가 없습니다" in l for l in last_lines(win))
    win.choose_method("describe")
    run_and_wait(qtbot, win)
    out = tmp_path / "out"
    out.mkdir()
    monkeypatch.setattr(QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(out / "r.xlsx"), "")))
    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(out)))
    win.export_excel()
    win.export_csv()
    win.save_logs()
    files = os.listdir(out)
    assert "r.xlsx" in files and any(f.endswith(".csv") for f in files)
    assert os.listdir(tmp_path / "logs")
    assert [e["kind"] for e in win.history.entries][-3:] == ["export", "export", "export"]
    win.report()
    assert any("4단계" in l for l in last_lines(win))


# ── 이슈 팝업 ────────────────────────────────────────────
def test_issue_popup_actions(qtbot, win):
    assert win.issue_btn.isVisible() and win.issues
    win.show_issues()
    assert win.issue_popup.isVisible()
    n = len(win.bd.results)
    win._issue_action("check")                          # 점검 보기 → 전처리 점검 실행
    qtbot.waitUntil(lambda: len(win.bd.results) > n and not win.worker.isRunning(), timeout=30000)
    assert win.bd.results[-1].name == "전처리 점검"
    win._issue_action("dates")
    assert win.date_dialog is not None and win.date_dialog.isVisible()
    win.date_dialog.reject()


# ── 파일 읽기 ────────────────────────────────────────────
def test_memory_confirm_and_cancel_and_bad_file(qtbot, tmp_path, csv_path, monkeypatch):
    w = A.MainWindow(settings_path=str(tmp_path / "s2" / "settings.json"))
    qtbot.addWidget(w)
    w.show()
    # 메모리가 부족해 보이게 → '일부 열만 읽기' 창에서 2개 열만 고름
    try:                                               # v0.5.2부터 파일 읽기는 window/loading.py에 있음
        import blueda.gui.window.loading as L
    except ImportError:                                # 그 전 버전과 비교할 때
        L = A
    monkeypatch.setattr(L, "total_memory", lambda: 1)
    def press(box):                                    # 메모리 확인 창에서 '일부 열만 읽기'를 누름
        next(b for b in box.buttons() if b.text() == "일부 열만 읽기").click()
        return 0
    monkeypatch.setattr(QMessageBox, "exec", press)
    monkeypatch.setattr(A.ColumnChooser, "exec", lambda self: (
        [self.list.item(i).setCheckState(Qt.Unchecked) for i in range(2, self.list.count())], 1)[1])
    w.open_file(csv_path)
    qtbot.waitUntil(lambda: w.df is not None and w.start.start_btn.isEnabled(), timeout=30000)
    assert list(w.df.columns) == ["접수번호", "시도"]
    # 읽을 수 없는 파일
    bad = tmp_path / "bad.csv"
    bad.write_bytes(b"\x00\x01\x02" * 100)
    w.open_file(str(bad))
    qtbot.waitUntil(lambda: w.worker is None or not w.worker.isRunning(), timeout=10000)
    qtbot.wait(100)
    assert not w.start.start_btn.isEnabled() or w.start.status.text()


def test_known_commands_without_data_explain_why(qtbot, tmp_path):
    """있는 명령인데 지금 쓸 수 없으면 '5단계' 대신 이유를 알려준다 (v0.5.3)"""
    w = A.MainWindow(settings_path=str(tmp_path / "s3" / "settings.json"))
    qtbot.addWidget(w)
    for c, expect in [("show", "아직 실행한 분석이 없습니다"), ("rows", "파일을 열고"), ("dates", "파일을 열고")]:
        w._command(c)
        assert any(expect in l for l in last_lines(w, 2)), (c, last_lines(w, 2))
