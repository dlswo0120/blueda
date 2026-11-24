"""표·차트 만들기 테스트 — pandas pivot_table·crosstab·groupby를 직접 실행한 값과 비교."""
import numpy as np
import pandas as pd
import pytest

from blueda import Blueda
from blueda import methods as M
from blueda.config import BluedaConfig
from blueda.loader import optimize_dtypes
from blueda.tables import CHART_TYPES


@pytest.fixture
def df():
    rng = np.random.default_rng(1)
    n = 3000
    return pd.DataFrame({
        "id": np.arange(1, n + 1),
        "region": rng.choice(["East", "West", "South", "Central"], n),
        "segment": rng.choice(["A", "B", "C"], n, p=[.5, .3, .2]),
        "sub": rng.choice([f"s{i:02d}" for i in range(40)], n),
        "date": pd.date_range("2024-01-01", periods=n, freq="5h").strftime("%Y-%m-%d"),
        "sales": rng.gamma(2, 100, n).round(2),
        "profit": rng.normal(20, 50, n).round(2),
        "qty": rng.integers(1, 10, n),
    })


@pytest.fixture
def bd(df):
    return Blueda(df.copy(), BluedaConfig(print_code=False))


def test_pivot_matches_pandas(bd, df):
    r = bd.pivot_table("region", "segment", "sales", "평균")
    t = r.tables["피벗 표"]
    exp = pd.pivot_table(df, index="region", columns="segment", values="sales", aggfunc="mean",
                         margins=True, margins_name="전체")
    np.testing.assert_allclose(t.loc[exp.index, exp.columns].to_numpy(), exp.round(4).to_numpy(), atol=1e-4)
    assert any("그룹 평균들을 다시 평균" in n for n in r.notes)        # 평균의 '전체'칸 안내


@pytest.mark.parametrize("agg,func", [("합계", "sum"), ("개수", "count"), ("중앙값", "median"),
                                      ("최솟값", "min"), ("최댓값", "max")])
def test_pivot_rows_only_each_agg(bd, df, agg, func):
    t = bd.pivot_table("region", None, "sales", agg).tables["피벗 표"]
    exp = df.groupby("region")["sales"].agg(func)
    np.testing.assert_allclose(t.loc[exp.index].iloc[:, 0], exp.round(4), atol=1e-4)
    np.testing.assert_allclose(t.loc["전체"].iloc[0], round(df["sales"].agg(func), 4), atol=1e-4)


def test_pivot_without_values_counts_rows(bd, df):
    t = bd.pivot_table("region", "segment").tables["피벗 표"]
    exp = pd.crosstab(df["region"], df["segment"], margins=True, margins_name="전체")
    assert (t.loc[exp.index, exp.columns] == exp).all().all()


def test_pivot_by_month_from_date_strings(bd, df):
    """글자로 된 날짜도 월 단위로 묶임 (원본은 그대로)"""
    t = bd.pivot_table("date", None, "sales", "합계", "월").tables["피벗 표"]
    exp = df.groupby(pd.to_datetime(df["date"]).dt.to_period("M").astype(str))["sales"].sum()
    np.testing.assert_allclose(t.loc[exp.index].iloc[:, 0], exp.round(4), atol=1e-3)
    assert not pd.api.types.is_datetime64_any_dtype(bd.df["date"])     # 원본은 글자 그대로
    q = bd.pivot_table("date", None, "sales", "합계", "분기").tables["피벗 표"]
    assert "2024Q1" in q.index


def test_pivot_works_on_optimized_categories(df):
    """화면처럼 category로 최적화된 데이터에서 빈 그룹이 생기지 않아야 함"""
    opt, _ = optimize_dtypes(df.copy())
    bd = Blueda(opt, BluedaConfig(print_code=False))
    bd.set_scope(filters=[__import__("blueda.scope", fromlist=["Filter"]).Filter("region", "in", values=["East"])])
    t = bd.pivot_table("region", "segment", "sales", "합계").tables["피벗 표"]
    assert list(t.index) == ["East", "전체"]


@pytest.mark.parametrize("norm,arg", [("행 %", "index"), ("열 %", "columns"), ("전체 %", "all")])
def test_crosstab_percent(bd, df, norm, arg):
    r = bd.crosstab("region", "segment", norm)
    pct = r.tables[f"교차표 ({norm})"]
    exp = (pd.crosstab(df["region"], df["segment"], normalize=arg, margins=True, margins_name="전체") * 100).round(1)
    np.testing.assert_allclose(pct.loc[exp.index, exp.columns].to_numpy(), exp.to_numpy(), atol=0.05)
    assert "교차표 (개수)" in r.tables


@pytest.mark.parametrize("ctype", CHART_TYPES)
def test_every_chart_type_draws(bd, ctype):
    args = {"막대": dict(x="region", y="sales", color="segment", agg="평균"),
            "선": dict(x="date", y="sales", color="region", agg="합계"),
            "산점도": dict(x="sales", y="profit", color="segment"),
            "히스토그램": dict(x="profit"),
            "상자그림": dict(x="region", y="sales"),
            "상관 히트맵": {}}[ctype]
    r = bd.chart(ctype, **args)
    assert r.status == "SUCCESS", r.message
    assert r.figures and "차트 데이터" in r.tables                  # 차트마다 집계표도 함께


def test_bar_values_match_groupby_and_sorted(bd, df):
    t = bd.chart("막대", x="region", y="sales", agg="합계").tables["차트 데이터"]
    exp = df.groupby("region")["sales"].sum().sort_values(ascending=False)
    assert list(t.index) == list(exp.index)                             # 큰 값부터
    np.testing.assert_allclose(t.iloc[:, 0], exp.round(4), atol=1e-3)
    assert t.index.name == "region"


def test_bar_top_n_and_other_series(bd):
    r = bd.chart("막대", x="sub")                                        # 범주 40개
    assert any("30개만" in n for n in r.notes)
    r2 = bd.chart("막대", x="region", color="sub")                       # 색 구분 40개 → 7 + 기타
    assert "기타" in r2.tables["차트 데이터"].columns and r2.tables["차트 데이터"].shape[1] == 8


def test_heatmap_skips_id(bd):
    t = bd.chart("상관 히트맵").tables["차트 데이터"]
    assert "id" not in t.columns and {"sales", "profit", "qty"} <= set(t.columns)


def test_precheck_tables(df):
    kinds = M.column_kinds(df)
    ok = lambda key, **p: M.precheck(key, p, df, kinds)              # noqa: E731
    assert not ok("pivot_table", rows="region", columns="region").ok
    assert ok("pivot_table", rows="region", columns="sub").ok            # 열 방향 40개는 허용(50 이하)
    wide = df.assign(code=[f"c{i % 60}" for i in range(len(df))])
    assert not M.precheck("pivot_table", {"rows": "region", "columns": "code"}, wide, M.column_kinds(wide)).ok
    assert ok("pivot_table", rows="region").message.startswith("값을 고르지 않아")
    assert ok("crosstab", rows="region", columns="segment").alternative == "chi_square"
    assert not ok("chart_builder", chart_type="막대", x="sales").ok       # 수치 X 막대 → 히스토그램 안내
    assert not ok("chart_builder", chart_type="선", x="region").ok
    assert not ok("chart_builder", chart_type="산점도", x="sales", y="sales").ok
    assert ok("chart_builder", chart_type="산점도", x="sales", y="profit").ok
    assert not ok("chart_builder", chart_type="상자그림", x="region").ok   # Y 필요
    assert ok("chart_builder", chart_type="상관 히트맵").ok


def test_visibility_rules():
    m = M.BY_KEY["chart_builder"]
    p = {q.name: q for q in m.params}
    kinds = {"date": "날짜", "region": "범주형"}
    assert not M.visible(p["y"], {"chart_type": "히스토그램"})
    assert M.visible(p["color"], {"chart_type": "히스토그램"})
    assert not M.visible(p["x"], {"chart_type": "상관 히트맵"})
    assert M.visible(p["date_unit"], {"chart_type": "선", "x": "date"}, kinds, m)
    assert not M.visible(p["date_unit"], {"chart_type": "선", "x": "region"}, kinds, m)
    pv = M.BY_KEY["pivot_table"]
    assert M.visible(pv.params[-1], {"rows": "region", "columns": "date"}, kinds, pv)


def test_code_log_reproduces_pivot(bd, df):
    """로그 코드가 Colab에서 그대로 돌아가는지"""
    r = bd.pivot_table("region", "segment", "sales", "합계")
    ns = {"pd": pd, "np": np, "sub": df.copy()}
    exec(r.code, ns)
    assert np.isclose(ns["table"].loc["East", "A"], r.tables["피벗 표"].loc["East", "A"], atol=1e-3)


def test_heavy_tail_rule():
    from blueda.tables import heavy_tail
    rng = np.random.default_rng(0)
    assert not heavy_tail(rng.normal(0, 1, 100_000))
    assert not heavy_tail(rng.exponential(1, 100_000))
    assert heavy_tail(np.r_[rng.normal(0, 1, 5000), [500, -400]])


def test_hist_clips_view_but_stats_use_all(bd):
    d = bd.df.copy()
    d.loc[:4, "profit"] = [9e4, -8e4, 7e4, 1e5, -9e4]                 # 극단값
    b2 = Blueda(d, BluedaConfig(print_code=False))
    r = b2.chart("히스토그램", x="profit")
    assert any("범위 밖" in n for n in r.notes)
    assert r.tables["차트 데이터"].loc["최댓값", "값"] == 1e5           # 통계는 전체


def test_box_log_scale_for_heavy_positive(bd):
    d = bd.df.copy()
    d.loc[:2, "sales"] = [1e6, 2e6, 3e6]
    from blueda.tables import chart
    r = chart(d, "상자그림", x="region", y="sales")          # 엔진 함수는 그림 객체를 돌려줌
    assert any("로그 눈금" in n for n in r.notes)
    assert r.figures["상자그림 차트"].axes[0].get_yscale() == "log"


def test_scatter_point_count_stays_numeric(bd):
    """점 개수가 글자가 아니라 숫자 (Excel 내보내기에서 계산 가능해야 함, v0.5.0과 같게)"""
    t = bd.chart("산점도", x="sales", y="profit").tables["차트 데이터"]
    assert isinstance(t.loc["점 개수(전체)", "값"], (int, np.integer))


@pytest.mark.parametrize("fmt", ["%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y"])
def test_code_log_reproduces_same_table(fmt):
    """코드 로그를 실행하면 오류 없이 도는 것에 그치지 않고 툴과 같은 표가 나와야 한다 (글자 날짜 형식별)"""
    rng = np.random.default_rng(1)
    n = 200
    d = pd.DataFrame({"d": (pd.Timestamp("2024-01-01") + pd.to_timedelta(rng.integers(0, 400, n), unit="D")).strftime(fmt),
                      "g": rng.choice(["a", "b"], n), "v": rng.normal(0, 1, n)})
    from blueda import tables
    for r, var in [(tables.pivot_table(d, "d", "g", "v", "합계", "월"), "table"),
                   (tables.crosstab(d, "d", "g", "행 %", "월"), "pct")]:
        ns = {"pd": pd, "np": np, "sub": d.copy(), "df": d.copy()}
        exec(r.code, ns)
        tool = list(r.tables.values())[0]
        assert ns[var].shape == tool.shape
        assert np.allclose(ns[var].to_numpy(float), tool.to_numpy(float), equal_nan=True, atol=0.06), r.name
