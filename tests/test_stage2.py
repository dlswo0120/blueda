"""2단계 테스트: 추론통계·이변량·다변량.

결과값을 scipy/statsmodels로 직접 계산한 값과 대조해서 BLUEDA가 숫자를 틀리지 않는지 확인합니다.
"""

import numpy as np
import pandas as pd
import pytest
import statsmodels.api as sm
from scipy import stats

from blueda import Blueda, BluedaConfig
from blueda.result import FAIL, SUCCESS


@pytest.fixture
def cfg(tmp_path):
    return BluedaConfig(log_dir=str(tmp_path / "logs"), print_code=False)


@pytest.fixture
def df():
    rng = np.random.default_rng(7)
    n = 150
    region = rng.choice(["서울", "부산", "대구"], n)
    gender = rng.choice(["남", "여"], n)
    ad = rng.normal(50, 10, n)
    visits = rng.normal(30, 5, n)
    sales = 20 + 1.5 * ad + 0.8 * visits + np.where(region == "서울", 15, 0) + rng.normal(0, 8, n)
    buy = np.where(gender == "여", rng.choice(["Y", "N"], n, p=[0.7, 0.3]), rng.choice(["Y", "N"], n, p=[0.4, 0.6]))
    return pd.DataFrame({"지역": region, "성별": gender, "광고비": ad, "방문수": visits, "매출": sales, "구매": buy})


def _p(text):
    return 0.0 if text.startswith("<") else float(text)


# ---------- 추론통계 ----------
def test_ci_mean_matches_scipy(df, cfg):
    r = Blueda(df, cfg).confidence_interval("매출", 0.95)
    lo, hi = stats.t.interval(0.95, len(df) - 1, loc=df["매출"].mean(), scale=stats.sem(df["매출"]))
    assert r.status == SUCCESS
    assert np.isclose(r.metrics["하한"], lo, atol=1e-4) and np.isclose(r.metrics["상한"], hi, atol=1e-4)


def test_ci_proportion(df, cfg):
    r = Blueda(df, cfg).confidence_interval("구매", category="Y")
    assert r.metrics["하한"] < r.metrics["표본비율"] < r.metrics["상한"]


def test_one_sample_ttest_matches_scipy(df, cfg):
    r = Blueda(df, cfg).one_sample_ttest("매출", 120)
    expected = stats.ttest_1samp(df["매출"], 120)
    assert np.isclose(r.metrics["t 통계량"], expected.statistic, atol=1e-4)
    assert "귀무가설" in r.message


def test_sampling_distribution_se_close_to_theory(df, cfg):
    r = Blueda(df, cfg).sampling_distribution("매출", sample_size=30, n_samples=3000)
    sim, theory = r.metrics["표준오차(시뮬레이션)"], r.metrics["표준오차(이론 σ/√n)"]
    assert abs(sim - theory) / theory < 0.1                       # 10% 이내로 일치


# ---------- 이변량 ----------
def test_ttest_matches_scipy_welch(df, cfg):
    r = Blueda(df, cfg).t_test("성별", "매출", method="welch")
    a, b = df.loc[df["성별"] == "남", "매출"], df.loc[df["성별"] == "여", "매출"]
    assert np.isclose(r.metrics["t 통계량"], stats.ttest_ind(a, b, equal_var=False).statistic, atol=1e-4)
    assert "Welch" in r.metrics["검정 방법"]


def test_ttest_needs_two_groups(df, cfg):
    r = Blueda(df, cfg).t_test("지역", "매출")
    assert r.status == FAIL and "ANOVA" in r.message


def test_anova_matches_scipy_and_runs_tukey(df, cfg):
    r = Blueda(df, cfg).anova("지역", "매출")
    groups = [g["매출"] for _, g in df.groupby("지역")]
    assert np.isclose(r.metrics["F 통계량"], stats.f_oneway(*groups).statistic, atol=1e-4)
    assert "사후검정 (Tukey HSD)" in r.tables                     # 서울 효과가 있어서 유의 → 사후검정 실행


def test_chi_square_matches_scipy(df, cfg):
    r = Blueda(df, cfg).chi_square("성별", "구매")
    chi2 = stats.chi2_contingency(pd.crosstab(df["성별"], df["구매"]))[0]
    assert np.isclose(r.metrics["카이제곱 χ²"], chi2, atol=1e-4)
    assert "교차표 (관측빈도)" in r.tables


def test_chi_square_small_expected_suggests_fisher(cfg):
    small = pd.DataFrame({"a": ["x"] * 3 + ["y"] * 3, "b": ["p", "p", "q", "q", "q", "p"]})
    r = Blueda(small, cfg).chi_square("a", "b")
    assert "Fisher 정확검정 p" in r.metrics


def test_correlation_test_matches_scipy(df, cfg):
    r = Blueda(df, cfg).correlation_test("광고비", "매출")
    expected = stats.pearsonr(df["광고비"], df["매출"]).statistic
    assert np.isclose(float(r.metrics["Pearson r"].split()[0]), expected, atol=1e-4)


def test_simple_regression_matches_statsmodels(df, cfg):
    r = Blueda(df, cfg).simple_regression("광고비", "매출")
    m = sm.OLS(df["매출"], sm.add_constant(df["광고비"])).fit()
    assert np.isclose(r.metrics["기울기 b1"], m.params["광고비"], atol=1e-4)
    assert np.isclose(r.metrics["결정계수 R²"], m.rsquared, atol=1e-4)


# ---------- 다변량 ----------
def test_multiple_regression_with_dummies_and_vif(df, cfg):
    r = Blueda(df, cfg).multiple_regression("매출", ["광고비", "방문수", "지역"])
    coef = r.tables["회귀계수"]
    assert {"광고비", "방문수", "지역_부산", "지역_서울"} <= set(coef.index)   # 더미 변수 (대구가 기준)
    assert abs(coef.loc["광고비", "계수"] - 1.5) < 0.3                         # 실제 계수 1.5 근처
    assert coef["VIF"].dropna().max() < 5
    assert r.metrics["수정 R²"] <= r.metrics["R²"]


def test_multiple_regression_too_few_rows(cfg):
    tiny = pd.DataFrame({"y": [1, 2, 3], "a": [1, 2, 3], "b": [3, 1, 2]})
    assert Blueda(tiny, cfg).multiple_regression("y", ["a", "b"]).status == FAIL


# ---------- request 연결 ----------
def test_request_dispatch_and_missing_params(df, cfg):
    bd = Blueda(df, cfg)
    assert bd.request("anova", group_col="지역", value_col="매출").status == SUCCESS
    missing = bd.request("anova")
    assert missing.status == FAIL and "사용법" in missing.message


def test_scope_applies_to_stage2(df, cfg):
    bd = Blueda(df, cfg)
    bd.set_scope(query="지역 != '대구'")
    r = bd.anova("지역", "매출")
    assert r.metrics["그룹 수"] == 2


# ---------- 해석 문장 ----------
def test_josa_and_p_sentence():
    from blueda.interpret import interpret_p, josa
    assert [josa("매출", "을/를"), josa("광고비", "을/를"), josa(120, "과/와"), josa(12.5, "과/와")] == \
           ["매출을", "광고비를", "120과", "12.5와"]
    s = interpret_p(0.0001, 0.05, "H0", "H1이 맞다")
    assert "p < 0.001로 유의수준 0.05보다 작으므로" in s and "< 0.001 <" not in s
    assert "기각하지 못합니다" in interpret_p(0.3, 0.05, "H0", "H1")


def test_regression_chart_is_deterministic_and_matches_ols():
    """회귀 차트가 실행할 때마다 같고(무작위 부트스트랩 없음), 선이 표의 회귀식과 같다 (v0.5.3)"""
    import hashlib
    import numpy as np
    import pandas as pd
    import statsmodels.api as sm
    from blueda.bivariate import simple_regression
    from blueda.result import ChartImage
    rng = np.random.default_rng(3)
    df = pd.DataFrame({"x": rng.normal(0, 1, 400)})
    df["y"] = 2 + 3 * df["x"] + rng.normal(0, 1, 400)
    h = [hashlib.md5(ChartImage(simple_regression(df, "x", "y").figures["산점도와 회귀선"]).png).hexdigest()
         for _ in range(2)]
    assert h[0] == h[1]
    fig = simple_regression(df, "x", "y").figures["산점도와 회귀선"]
    line = next(l for l in fig.axes[0].lines if l.get_label() == "회귀선")
    m = sm.OLS(df["y"], sm.add_constant(df["x"])).fit()
    xs, ys = line.get_data()
    np.testing.assert_allclose(ys, m.params["const"] + m.params["x"] * xs, atol=1e-9)
