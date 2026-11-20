"""3단계 엔진 보강 테스트: 필터 칩, 대용량 읽기, 설정 저장, 분석 메뉴·실행 전 점검."""

import numpy as np
import pandas as pd
import pytest

from blueda import Blueda, BluedaConfig, methods
from blueda.loader import LoadCancelled, detect_file, estimate_memory, load_file, optimize_dtypes
from blueda.result import SUCCESS
from blueda.scope import AnalysisScope, Filter
from blueda.settings import load_settings, save_settings


@pytest.fixture
def cfg(tmp_path):
    return BluedaConfig(log_dir=str(tmp_path / "logs"), print_code=False)


@pytest.fixture
def df():
    rng = np.random.default_rng(3)
    n = 400
    return pd.DataFrame({
        "시도": rng.choice(["서울", "부산", "대구", "경기"], n),
        "성별": rng.choice(["남", "여"], n),
        "나이": rng.integers(19, 80, n),
        "처리일수": rng.gamma(3, 3, n).round(1),
        "만족도": rng.integers(1, 6, n),
        "접수일": pd.date_range("2025-01-01", periods=n, freq="D").astype(str),
    })


# ---------- 필터 칩 ----------
def test_filters_in_and_between(df):
    scope = AnalysisScope(filters=[Filter("시도", "in", values=["서울", "부산"]), Filter("나이", "between", lo=30, hi=50)])
    sub, code = scope.apply(df)
    expected = df[df["시도"].isin(["서울", "부산"]) & df["나이"].between(30, 50)]
    assert len(sub) == len(expected) == scope.count_rows(df)
    assert "isin" in code and ">= 30" in code


def test_filter_date_range_and_labels(df):
    f = Filter("접수일", "between", lo="2025-02-01", hi="2025-02-28")
    sub, _ = AnalysisScope(filters=[f]).apply(df)
    assert len(sub) == 28
    assert Filter("시도", "in", values=["서울", "부산", "대구"]).label() == "시도: 서울 외 2"


def test_filter_notna_and_iqr(df):
    d = df.copy()
    d.loc[:9, "처리일수"] = np.nan
    d.loc[10, "처리일수"] = 9999
    sub, _ = AnalysisScope(filters=[Filter(op="notna", columns=["처리일수"]), Filter("처리일수", "iqr_inside")]).apply(d)
    assert sub["처리일수"].notna().all() and sub["처리일수"].max() < 9999


def test_scope_does_not_change_original(df):
    sub, _ = AnalysisScope(filters=[Filter("성별", "in", values=["남"])]).apply(df)
    sub["나이"] = 0
    assert df["나이"].min() >= 19


def test_category_columns_drop_empty_groups_after_filter(df, cfg):
    d, changed = optimize_dtypes(df.copy())
    assert "시도" in changed["category"]
    bd = Blueda(d, cfg)
    bd.set_scope(filters=[Filter("시도", "in", values=["서울", "부산", "대구"])])
    r = bd.anova("시도", "처리일수")
    assert r.status == SUCCESS and r.metrics["그룹 수"] == 3   # 빠진 '경기'가 빈 그룹으로 남지 않음


# ---------- 대용량 읽기 ----------
def test_chunked_csv_progress_and_late_korean(tmp_path, monkeypatch):
    import blueda.loader as L
    monkeypatch.setattr(L, "CHUNK_ROWS", 1000)
    rows = 5000
    d = pd.DataFrame({"id": range(rows), "v": np.arange(rows) * 0.5, "name": ["abc"] * rows})
    d.loc[rows - 1, "name"] = "마지막줄한글"           # 한글이 파일 맨 끝에만 있는 cp949 파일
    p = tmp_path / "big.csv"
    d.to_csv(p, index=False, encoding="cp949")
    seen = []
    info, out, _ = load_file(str(p), progress=seen.append)
    assert info.encoding in ("cp949", "euc-kr")          # 앞부분만 보면 utf-8로 오판하던 경우
    assert len(out) == rows and out["name"].iloc[-1] == "마지막줄한글"
    assert len(seen) >= 5 and seen[-1] == 1.0 and seen == sorted(seen)


def test_load_cancel(tmp_path, monkeypatch):
    import blueda.loader as L
    monkeypatch.setattr(L, "CHUNK_ROWS", 100)
    p = tmp_path / "c.csv"
    pd.DataFrame({"a": range(1000)}).to_csv(p, index=False)
    with pytest.raises(LoadCancelled):
        load_file(str(p), cancelled=lambda: True)


def test_estimate_memory_is_reasonable(tmp_path, df):
    p = tmp_path / "e.csv"
    pd.concat([df] * 20).to_csv(p, index=False)
    est = estimate_memory(str(p))
    real = pd.read_csv(p).memory_usage(deep=True).sum()
    assert 0.5 < est / real < 2.0                       # 2배 이내 오차


def test_optimize_keeps_floats_and_values(df):
    out, changed = optimize_dtypes(df.copy())
    assert out["처리일수"].dtype == df["처리일수"].dtype   # 실수는 그대로
    assert (out["나이"] == df["나이"]).all()               # 정수 축소해도 값은 같음
    assert out.memory_usage(deep=True).sum() < df.memory_usage(deep=True).sum()


def test_chart_sampling_note(df, cfg):
    cfg.chart_sample_size = 100
    r = Blueda(df, cfg).describe("numeric")[0]
    assert any("표본 100행" in n for n in r.notes)


# ---------- 설정 저장 ----------
def test_settings_roundtrip(tmp_path):
    p = str(tmp_path / "s.json")
    cfg, ui = load_settings(p)                           # 파일 없음 → 기본값
    assert cfg.alpha == 0.05 and ui["theme"] == "light"
    cfg.alpha, ui["theme"] = 0.01, "dark"
    save_settings(cfg, ui, p)
    cfg2, ui2 = load_settings(p)
    assert cfg2.alpha == 0.01 and ui2["theme"] == "dark"


def test_settings_broken_file_falls_back(tmp_path):
    p = tmp_path / "s.json"
    p.write_text("{깨진 파일", encoding="utf-8")
    cfg, ui = load_settings(str(p))
    assert cfg.alpha == 0.05


# ---------- 분석 메뉴·실행 전 점검 ----------
def test_columns_for_filters_by_kind(df):
    kinds = methods.column_kinds(df)
    assert "처리일수" in methods.columns_for("numeric", kinds)
    assert "시도" in methods.columns_for("categorical", kinds) and "시도" not in methods.columns_for("numeric", kinds)
    assert "만족도" in methods.columns_for("categorical", kinds)   # 1~5 정수 → 코드로 적힌 범주로 판정


def test_precheck_ttest_suggests_anova(df):
    kinds = methods.column_kinds(df)
    c = methods.precheck("t_test", {"group_col": "시도", "value_col": "처리일수"}, df, kinds)
    assert not c.ok and c.alternative == "anova" and "4개" in c.message


def test_precheck_rejects_wrong_kind_and_same_column(df):
    kinds = methods.column_kinds(df)
    assert not methods.precheck("anova", {"group_col": "처리일수", "value_col": "나이"}, df, kinds).ok
    assert not methods.precheck("correlation_test", {"x": "나이", "y": "나이"}, df, kinds).ok
    assert not methods.precheck("multiple_regression", {"y": "나이", "xs": ["나이"]}, df, kinds).ok
    assert not methods.precheck("pivot_table", {}, df, kinds).ok        # 준비 중 기능


def test_every_available_method_runs(df, cfg):
    bd = Blueda(df, cfg)
    kinds = methods.column_kinds(df)
    params = {
        "analysis_unit": {"key_columns": "접수일"},
        "sampling_distribution": {"column": "처리일수", "sample_size": 20},
        "confidence_interval": {"column": "처리일수"},
        "ci_proportion": {"column": "성별", "category": "남"},
        "one_sample_ttest": {"column": "처리일수", "mu0": "9"},
        "t_test": {"group_col": "성별", "value_col": "처리일수"},
        "anova": {"group_col": "시도", "value_col": "처리일수"},
        "chi_square": {"row_col": "성별", "col_col": "시도"},
        "correlation_test": {"x": "나이", "y": "처리일수"},
        "simple_regression": {"x": "나이", "y": "처리일수"},
        "multiple_regression": {"y": "처리일수", "xs": ["나이", "시도"]},
    }
    for m in methods.METHODS:
        if not m.available:
            continue
        p = params.get(m.key, {})
        assert methods.precheck(m.key, p, df, kinds).ok, m.key
        out = methods.run(bd, m.key, p)
        results = out if isinstance(out, list) else [out]
        assert all(r.status == SUCCESS for r in results), (m.key, [r.message for r in results])
