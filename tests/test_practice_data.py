"""실습 데이터 비교 테스트 — BLUEDA 결과가 pandas·numpy·scipy를 직접 실행한 값과 같은지 확인한다.

데이터 파일은 저장소에 넣지 않는다(개인 PC에서만 사용).
실행 방법:
    BLUEDA_TEST_DATA=C:\\경로\\testdata  pytest tests/test_practice_data.py -v
폴더에 ai4i2020.csv, superstore.csv 가 있어야 하며, 없으면 해당 테스트는 건너뛴다.
"""
import contextlib
import io
import os
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from blueda import Blueda

DATA_DIR = Path(os.environ.get("BLUEDA_TEST_DATA", ""))


def _path(name):
    p = DATA_DIR / name
    if not os.environ.get("BLUEDA_TEST_DATA") or not p.exists():
        pytest.skip(f"{name} 없음 — BLUEDA_TEST_DATA 폴더를 지정하세요")
    return p


def _quiet(fn, *a, **k):
    """BLUEDA의 로그 출력을 숨기고 실행"""
    with contextlib.redirect_stdout(io.StringIO()):
        return fn(*a, **k)


@pytest.fixture(scope="module")
def ai4i():
    p = _path("ai4i2020.csv")
    bd = _quiet(Blueda.from_file, str(p))
    raw = pd.read_csv(p)                      # 실습과 같은 방식의 '정답' 데이터
    return bd, raw


@pytest.fixture(scope="module")
def store():
    p = _path("superstore.csv")
    bd = _quiet(Blueda.from_file, str(p))
    raw = pd.read_csv(p)
    return bd, raw


# ── 1. 읽기: 실습의 pd.read_csv와 같은 데이터인지 ─────────────────────────
@pytest.mark.parametrize("fx", ["ai4i", "store"])
def test_load_same_as_read_csv(fx, request):
    bd, raw = request.getfixturevalue(fx)
    assert bd.df.shape == raw.shape
    assert list(bd.df.columns) == list(raw.columns)          # BOM이 첫 열 이름에 붙지 않아야 함
    for c in raw.select_dtypes("number"):
        np.testing.assert_allclose(bd.df[c].to_numpy(float), raw[c].to_numpy(float))


# ── 2. 기술통계: df.describe(), skew(), kurt()와 비교 ───────────────────────
@pytest.mark.parametrize("fx,cols", [
    ("ai4i", ["Air temperature [K]", "Process temperature [K]", "Rotational speed [rpm]",
              "Torque [Nm]", "Tool wear [min]"]),
    ("store", ["Sales", "Quantity", "Discount", "Profit"]),
])
def test_describe_matches_pandas(fx, cols, request):
    bd, raw = request.getfixturevalue(fx)
    res = _quiet(bd.describe)
    res = res if isinstance(res, list) else [res]
    s = res[0].tables["수치형 요약"]
    d = raw[cols].describe()
    for c in cols:
        assert s.loc[c, "개수"] == d.loc["count", c]
        np.testing.assert_allclose(s.loc[c, "평균"], d.loc["mean", c], atol=1e-4)
        np.testing.assert_allclose(s.loc[c, "표준편차"], d.loc["std", c], atol=1e-4)   # ddof=1
        np.testing.assert_allclose(s.loc[c, "Q1"], d.loc["25%", c], atol=1e-4)
        np.testing.assert_allclose(s.loc[c, "중앙값"], d.loc["50%", c], atol=1e-4)
        np.testing.assert_allclose(s.loc[c, "Q3"], d.loc["75%", c], atol=1e-4)
        # 왜도·첨도는 scipy 편향 보정값과 같아야 함
        np.testing.assert_allclose(s.loc[c, "왜도"], stats.skew(raw[c], bias=False), atol=1e-4)
        np.testing.assert_allclose(s.loc[c, "첨도"], stats.kurtosis(raw[c], bias=False), atol=1e-4)


def test_numpy_std_vs_pandas_note(ai4i):
    """실습에서 자주 헷갈리는 부분: np.std 기본 ddof=0, pandas std 기본 ddof=1"""
    bd, raw = ai4i
    x = raw["Torque [Nm]"]
    assert not np.isclose(np.std(x), x.std())                 # 기본값끼리는 다름
    assert np.isclose(np.std(x, ddof=1), x.std())             # ddof를 맞추면 같음


# ── 3. 빈도: value_counts()와 비교 ─────────────────────────────────────────
@pytest.mark.parametrize("fx,col", [("ai4i", "Type"), ("store", "Segment"), ("store", "Region")])
def test_value_counts(fx, col, request):
    bd, raw = request.getfixturevalue(fx)
    res = _quiet(bd.describe)
    t = res[1].tables[f"{col} 빈도표"]
    vc = raw[col].value_counts()
    for k, v in vc.items():
        assert t.loc[k, "빈도"] == v
    np.testing.assert_allclose(t["비율"].sum(), 1.0, atol=1e-3)


# ── 4. 그룹 비교: groupby().agg()와 비교 + scipy 분산분석 ─────────────────
def test_groupby_and_anova(store):
    bd, raw = store
    r = _quiet(bd.anova, "Region", "Sales")
    g = r.tables["그룹별 요약"]
    exp = raw.groupby("Region")["Sales"].agg(["count", "mean", "std"])
    for k in exp.index:
        assert g.loc[k, "개수"] == exp.loc[k, "count"]
        np.testing.assert_allclose(g.loc[k, "평균"], exp.loc[k, "mean"], atol=1e-3)
        np.testing.assert_allclose(g.loc[k, "표준편차"], exp.loc[k, "std"], atol=1e-3)
    f, p = stats.f_oneway(*[x["Sales"] for _, x in raw.groupby("Region")])
    np.testing.assert_allclose(r.metrics["F 통계량"], f, atol=1e-3)


def test_failure_rate_by_type(ai4i):
    """Type별 고장률 — 실습의 groupby().mean()과 같은 값"""
    bd, raw = ai4i
    r = _quiet(bd.chi_square, "Type", "Machine failure")
    ct = r.tables["교차표 (관측빈도)"]
    exp = pd.crosstab(raw["Type"], raw["Machine failure"])
    for t in exp.index:
        for v in exp.columns:
            assert ct.loc[t, v] == exp.loc[t, v]
    chi2, p, dof, _ = stats.chi2_contingency(exp)
    np.testing.assert_allclose(r.metrics["카이제곱 χ²"], chi2, atol=1e-3)
    assert r.metrics["자유도"] == dof


# ── 5. 상관: df.corr()와 비교 ──────────────────────────────────────────────
@pytest.mark.parametrize("fx,x,y", [
    ("ai4i", "Rotational speed [rpm]", "Torque [Nm]"),
    ("ai4i", "Air temperature [K]", "Process temperature [K]"),
    ("store", "Sales", "Profit"),
])
def test_correlation(fx, x, y, request):
    bd, raw = request.getfixturevalue(fx)
    r = _quiet(bd.correlation_test, x, y)
    pear = float(str(r.metrics["Pearson r"]).split()[0])
    spear = float(r.metrics["Spearman ρ"])
    np.testing.assert_allclose(pear, raw[x].corr(raw[y]), atol=1e-4)
    np.testing.assert_allclose(spear, raw[x].corr(raw[y], method="spearman"), atol=1e-4)


# ── 6. 신뢰구간: scipy t분포와 비교 ───────────────────────────────────────
def test_confidence_interval(store):
    bd, raw = store
    r = _quiet(bd.confidence_interval, "Sales")
    x = raw["Sales"]
    lo, hi = stats.t.interval(0.95, len(x) - 1, loc=x.mean(), scale=stats.sem(x))
    np.testing.assert_allclose([r.metrics["하한"], r.metrics["상한"]], [lo, hi], atol=1e-3)


# ── 7. 날짜: 실습의 pd.to_datetime 후 월별 집계 ──────────────────────────
def test_date_filter_matches_to_datetime(store):
    bd, raw = store
    od = pd.to_datetime(raw["Order Date"])
    exp = int(((od >= "2025-01-01") & (od <= "2025-12-31")).sum())
    from blueda.scope import Filter
    n = Filter("Order Date", "between", lo="2025-01-01", hi="2025-12-31")
    mask, _ = n.mask_and_code(bd.df)
    assert int(mask.sum()) == exp


# ── 8. 코드 로그: Colab에 붙여 넣어도 돌아가는지 ─────────────────────────
def test_code_log_runs_standalone(store, tmp_path):
    bd, raw = store
    r = _quiet(bd.anova, "Region", "Sales")
    ns = {"pd": pd, "np": np, "df": raw.copy()}
    _quiet(exec, "sub = df\n" + r.code.split("sub = df", 1)[-1], ns)    # 로그 코드를 그대로 실행


# ── 알려진 문제 (고치면 xfail → 통과로 바뀜) ─────────────────────────────
@pytest.mark.parametrize("fx", ["ai4i", "store"])
def test_no_false_outliers_on_binary_or_discrete(fx, request):
    """0/1·이산값 열은 이상치 후보로 잡지 않는다 (v0.4.1 수정)"""
    bd, raw = request.getfixturevalue(fx)
    r = _quiet(bd.preprocess_check)
    txt = str(r.tables["전처리 점검"].loc["4. 이상치", "내용"])
    for c in ["Machine failure", "TWF", "RNF", "Discount", "Quantity", "UDI", "Row ID"]:
        assert f"{c}:" not in txt
    assert "Rotational speed [rpm]:" in txt or "Sales:" in txt     # 연속형 열은 계속 점검


def test_outliers_only_is_not_preprocessing_needed(ai4i):
    """AI4I는 이상치 후보만 있으므로 '전처리 필요'가 아니라 '확인 권장'"""
    bd, raw = ai4i
    r = _quiet(bd.preprocess_check)
    assert "전처리 필요" not in r.message
    assert r.tables["전처리 점검"].loc["4. 이상치", "상태"] == "확인 권장"


def test_checks_still_work_after_dtype_optimization(store):
    """화면처럼 메모리 최적화(category 변환) 후에도 타입·범주 불일치 점검이 동작해야 한다 (v0.4.1 수정)"""
    from blueda.loader import optimize_dtypes
    from blueda.preprocess_check import check_result
    bd, raw = store
    df, changed = optimize_dtypes(raw.copy())
    assert "Region" in changed["category"]
    df["Region"] = df["Region"].cat.add_categories(["west "])
    df.loc[0, "Region"] = "west "                          # 일부러 넣은 표기 오류
    t = check_result(df).tables["전처리 점검"]
    assert "Order Date" in t.loc["1. 타입", "내용"]          # 날짜 문자열 안내
    assert "Region" in t.loc["5. 범주 불일치", "내용"]       # 표기 오류 감지


@pytest.mark.parametrize("fx,idcol", [("ai4i", "UDI"), ("store", "Row ID")])
def test_describe_skips_id(fx, idcol, request):
    """기술통계에서 ID 후보 열은 빠지고 안내 문구가 나온다 (v0.4.1 수정)"""
    bd, raw = request.getfixturevalue(fx)
    res = _quiet(bd.describe)
    assert idcol not in res[0].tables["수치형 요약"].index
    assert any(idcol in n for n in res[0].notes)
    # 사용자가 수치형으로 지정하면 다시 포함
    bd.var_types[idcol] = "수치형"
    try:
        assert idcol in _quiet(bd.describe)[0].tables["수치형 요약"].index
    finally:
        bd.var_types.pop(idcol)
