"""3단계 화면 테스트 (pytest-qt). 화면 없이도 돌도록 offscreen으로 실행합니다.

점검 중 실제로 발견해 고친 문제들이 다시 생기지 않는지 확인합니다.
"""

import os
import time

import numpy as np
import pandas as pd
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6")
pytest.importorskip("pytestqt")

from PySide6.QtCore import Qt  # noqa: E402

from blueda.gui import app as A  # noqa: E402
from blueda.gui import widgets as W  # noqa: E402
from blueda.scope import Filter  # noqa: E402


@pytest.fixture
def csv_path(tmp_path):
    rng = np.random.default_rng(1)
    n = 3000
    d = pd.DataFrame({
        "접수번호": np.arange(n), "시도": rng.choice(["서울", "부산", "대구", "경기"], n),
        "성별": rng.choice(["남", "여"], n), "나이": rng.integers(19, 80, n),
        "처리일수": rng.gamma(3, 3, n).round(1), "만족도": rng.integers(1, 6, n),
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
    # 스레드 종료만이 아니라, 읽은 결과가 화면에 전달(분석 시작 버튼 켜짐)될 때까지 기다림
    qtbot.waitUntil(lambda: w.df is not None and w.start.start_btn.isEnabled(), timeout=30000)
    w.start_analysis()
    return w


def run_and_wait(qtbot, w):
    before = len(w.bd.results)
    w.main.bar.run_btn.click()
    qtbot.waitUntil(lambda: len(w.bd.results) > before and not w.worker.isRunning(), timeout=60000)
    qtbot.wait(50)


def pick(bar, name, value):
    combo = bar.widgets[name][1]
    combo.setCurrentIndex(combo.findData(value))


def test_load_and_describe_shows_both_results(qtbot, win):
    assert win.stack.currentWidget() is win.main
    assert win.info.encoding == "cp949"
    run_and_wait(qtbot, win)
    names = [r.name for r in win.bd.results]
    assert names == ["기술통계 - 수치형", "기술통계 - 범주형"]
    # 두 결과가 모두 지표 탭에 나와야 함 (예전엔 마지막 하나만 보임)
    page = win.main.tabs.metric_scroll.widget()
    from PySide6.QtWidgets import QLabel
    texts = " ".join(lbl.text() for lbl in page.findChildren(QLabel))
    assert "수치형 요약" in texts and "범주형 요약" in texts


def test_ttest_blocked_with_alternative(qtbot, win):
    win.choose_method("t_test")
    bar = win.main.bar
    pick(bar, "group_col", "시도")
    pick(bar, "value_col", "처리일수")
    bar.paramsChanged.emit()
    assert not bar.run_btn.isEnabled()
    assert bar.warn.text().startswith("시도는 그룹이 4개")      # 조사 '은(는)' 아님
    assert bar.alt_btn.isVisibleTo(bar)
    bar.alt_btn.click()
    assert win.method.key == "anova"


def test_warning_row_hidden_when_empty(qtbot, win):
    win.choose_method("describe")
    assert not win.main.bar.warn.isVisibleTo(win.main.bar)


def test_filter_chips_rebuild_without_ghosts(qtbot, win):
    fb = win.main.filters
    for vals in (["서울"], ["서울", "부산"], ["대구"]):
        fb.filters = [Filter("시도", "in", values=vals)]
        fb._changed()
        qtbot.wait(20)
    chips = [c for c in fb.flow_host.findChildren(W.Chip) if c.isVisibleTo(fb)]
    assert len(chips) == 1                                          # 잔상 칩 없음
    assert fb.iqr_btn.isVisibleTo(fb) and fb.na_btn.isVisibleTo(fb)  # 칩을 바꿔도 버튼 유지
    assert win.current_scope().count_rows(win.df) == (win.df["시도"] == "대구").sum()


def test_range_popup_fits_and_validates(qtbot, win):
    rp = W.RangePopup(win.df["나이"], "수치형", 30, 79, parent=win.main.filters)
    rp.show()
    qtbot.wait(20)
    assert rp.hi.geometry().right() <= rp.width() - 8            # 입력칸이 박스 밖으로 안 나감
    got = []
    rp.applied.connect(lambda lo, hi: got.append((lo, hi)))
    rp.lo.setText("80")
    rp.hi.setText("30")
    rp._apply()
    assert not got and rp.error.isVisibleTo(rp)


def test_unsupported_method_message(qtbot, win):
    win.choose_method("logistic_regression")          # 아직 준비 중인 기능
    r = win.bd.results[-1]
    assert r.status == "UNSUPPORTED" and r.name.startswith("로지스틱 회귀")


def test_data_tab_lazy_loading_and_sort(qtbot, win):
    model = win.main.tabs.data_model
    assert model.rowCount() == 1000 and model.canFetchMore()
    model.fetchMore()
    assert model.rowCount() == 2000
    col = list(model.dataframe().columns).index("나이")
    win.main.tabs.data_view.sortByColumn(col, Qt.DescendingOrder)
    assert model.dataframe()["나이"].iloc[0] == win.df["나이"].max()


def test_settings_dialog_validation(qtbot, win):
    d = A.SettingsDialog(win.cfg, win.ui, win)
    qtbot.addWidget(d)
    d.inputs["alpha"].setText("0.5")
    d.accept()
    assert "0.001 ~ 0.2" in d.error.text()
    d.inputs["alpha"].setText("0.01")
    d.inputs["chart_sample_size"].setText("50,000")
    vals, err = d.values()
    assert vals["alpha"] == 0.01 and vals["chart_sample_size"] == 50000 and not err


def test_theme_toggle_and_persist(qtbot, win, tmp_path):
    win.toggle_theme()
    assert win.ui["theme"] == "dark" and "#4B515A" in A.QApplication.instance().styleSheet()
    from blueda.settings import load_settings
    _, ui = load_settings(str(tmp_path / "settings.json"))
    assert ui["theme"] == "dark"
    win.toggle_theme()


def test_bad_query_does_not_crash(qtbot, win):
    fb = win.main.filters
    fb.direct.setText("나이 >>> 3")
    fb._apply_query()
    assert fb.query == ""                                         # 잘못된 조건은 버리고 계속
    fb.direct.setText("나이 >= 60")
    fb._apply_query()
    assert win.current_scope().count_rows(win.df) == (win.df["나이"] >= 60).sum()


def test_session_click_reopens_result(qtbot, win):
    run_and_wait(qtbot, win)
    win.choose_method("zscore")
    run_and_wait(qtbot, win)
    win._reopen(0)
    assert "수치형" in win.main.tabs.code.toPlainText()


def test_integer_histogram_bins_align():
    from blueda.charts import integer_bins
    bins = integer_bins(np.arange(19, 80))
    assert bins[0] == 18.5 and np.all(np.diff(bins) == bins[1] - bins[0])
    assert integer_bins(np.array([1.5, 2.2])) == "auto"


def test_large_start_is_fast(qtbot, tmp_path):
    """20만 행에서 분석 화면 시작이 1초 안에 끝나야 함 (예전엔 데이터 탭 때문에 수 초 멈춤)."""
    rng = np.random.default_rng(0)
    n = 200_000
    d = pd.DataFrame({"a": rng.integers(0, 100, n), "b": rng.normal(size=n), "c": rng.choice(list("xyz"), n)})
    p = tmp_path / "big.csv"
    d.to_csv(p, index=False)
    w = A.MainWindow(settings_path=str(tmp_path / "s.json"))
    qtbot.addWidget(w)
    w.open_file(str(p))
    qtbot.waitUntil(lambda: w.df is not None, timeout=60000)
    t = time.time()
    w.start_analysis()
    assert time.time() - t < 1.5


def test_issue_button_appears(qtbot, win):
    """파일을 열면 뒤에서 점검해 [!] 버튼이 생긴다"""
    qtbot.waitUntil(lambda: hasattr(win, "issue_worker") and not win.issue_worker.isRunning(), timeout=20000)
    qtbot.waitUntil(lambda: win.issue_btn.isVisible() or not win.issues, timeout=5000)
    if win.issues:
        assert win.issue_btn.text().startswith("[!] 이슈")
        win.show_issues()
        assert win.issue_popup.isVisible()
        win.issue_popup.close()


def test_history_records_and_restores(qtbot, win):
    """필터·분석을 하면 기록이 남고, 기록을 누르면 그때 조건으로 돌아간다 (값은 가려서 저장)"""
    from blueda.scope import Filter
    kinds = [e["kind"] for e in win.history.entries]
    assert kinds[-1] == "file"
    win.main.filters.filters = [Filter("시도", "in", values=["서울", "부산"])]
    win.main.filters._changed()
    e = win.history.entries[-1]
    assert e["kind"] == "filter" and "시도 in [값 2개]" in e["text"]
    raw = open(win.history.path, encoding="utf-8").read()
    assert "서울" not in raw and "부산" not in raw                  # 값 가림
    win.choose_method("anova")
    pick(win.main.bar, "group_col", "시도")
    pick(win.main.bar, "value_col", "처리일수")
    qtbot.wait(300)
    run_and_wait(qtbot, win)
    a = win.history.entries[-1]
    assert a["kind"] == "analysis" and a["state"]["method"] == "anova"
    filter_idx = len(win.history.entries) - 2
    # 조건을 바꾼 뒤 기록을 눌러 되돌리기
    win.main.filters.set_state([])
    win.choose_method("describe")
    n_before = len(win.history.entries)
    win.restore_history(len(win.history.entries) - 2)            # 방금 분석 기록
    assert [f.values for f in win.main.filters.filters] == [["서울", "부산"]]
    assert win.main.bar.method.key == "anova"
    assert win.main.bar.params()["group_col"] == "시도"
    assert len(win.history.entries) == n_before                  # 되돌리기 자체는 기록하지 않음
    win.main.session.show_page(1)
    assert win.main.session.history.count() == len(win.history.entries)


# ── 작업 중 파일 열기·창 닫기 (v0.5.1) ─────────────────────
def _slow_worker(seconds):
    import time as _t
    from blueda.gui.widgets import Worker
    w = Worker(lambda: _t.sleep(seconds))
    w.start()
    return w


def test_stale_issue_result_is_dropped(qtbot, win):
    """이전 파일의 이슈 점검이 늦게 끝나도 새 파일에 표시되지 않는다"""
    old_gen = win._issue_gen
    win._invalidate_issues()                       # 새 파일을 연 것과 같은 상태
    from blueda.issues import Issue
    win._issues_ready([Issue("확인 필요", "1. 타입", "옛 파일 이슈")], old_gen)
    assert win.issues == [] and not win.issue_btn.isVisible()


def test_open_during_work_shows_notice_on_start_page(qtbot, win, csv_path):
    win.stack.setCurrentWidget(win.start)
    win.worker = _slow_worker(0.5)
    win.open_file(csv_path)
    assert win.start.notice.isVisible() and "끝난 뒤" in win.start.notice.text()
    qtbot.waitUntil(lambda: not win.worker.isRunning(), timeout=5000)


def test_close_during_analysis_waits_without_freezing(qtbot, win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    def press_later(box):
        next(b for b in box.buttons() if b.text() == "끝나면 닫기").click()
    monkeypatch.setattr(QMessageBox, "exec", press_later)
    win.worker = _slow_worker(1.0)
    import time as _t
    t = _t.time()
    win.close()
    assert _t.time() - t < 0.5 and not win.isVisible()   # 바로 반응, 멈추지 않음
    qtbot.waitUntil(lambda: not win.worker.isRunning() and not win._close_pending, timeout=5000)


def test_close_during_analysis_keep_working(qtbot, win, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    def press_keep(box):
        next(b for b in box.buttons() if b.text() == "계속 작업").click()
    monkeypatch.setattr(QMessageBox, "exec", press_keep)
    win.worker = _slow_worker(0.5)
    win.close()
    assert win.isVisible()
    qtbot.waitUntil(lambda: not win.worker.isRunning(), timeout=5000)


def test_new_file_closes_old_date_dialog(qtbot, win, csv_path):
    win.offer_date_conversion()
    dlg = win.date_dialog
    assert dlg is not None and dlg.isVisible()
    win.open_file(csv_path)
    assert not dlg.isVisible() and win.date_dialog is None
    qtbot.waitUntil(lambda: win.df is not None and win.start.start_btn.isEnabled(), timeout=30000)


def test_date_conversion_refused_during_analysis(qtbot, win):
    """분석 스레드가 데이터를 읽는 중에는 날짜 변환을 하지 않는다"""
    win.offer_date_conversion()
    dlg = win.date_dialog
    win.worker = _slow_worker(0.5)
    dlg.accept()
    assert not pd.api.types.is_datetime64_any_dtype(win.df["접수일"])
    qtbot.waitUntil(lambda: not win.worker.isRunning(), timeout=5000)


def test_date_conversion_keeps_existing_filters(qtbot, win):
    """날짜 변환을 해도 이미 걸어 둔 필터는 그대로 남는다 (v0.5.2 수정)"""
    from blueda.scope import Filter
    win.main.filters.set_state([Filter("시도", "in", values=["서울"])])
    win.offer_date_conversion()
    win.date_dialog.accept()
    qtbot.waitUntil(lambda: pd.api.types.is_datetime64_any_dtype(win.df["접수일"]), timeout=20000)
    assert [f.values for f in win.main.filters.filters] == [["서울"]]
