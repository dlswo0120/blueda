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
    texts = " ".join(lbl.text() for lbl in page.findChildren(W.QLabel))
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
