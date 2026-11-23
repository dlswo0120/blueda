"""2) 추론통계 기초: 표본을 바탕으로 모집단의 특성을 추론합니다.

- 모집단·표본·표본분포: 지금 데이터를 모집단으로 보고 표본을 반복 추출해서
  '표본평균의 분포'가 어떻게 생기는지 시뮬레이션합니다 (중심극한정리 체험).
- 신뢰구간: 평균은 t분포, 비율은 Wilson 방법으로 구합니다.
- 가설검정: 단일표본 t검정 + p값 해석 문장.
"""

import numpy as np
import pandas as pd
from scipy import stats

from . import charts
from .interpret import EFFECT_NOTE, effect_label, fmt_p, interpret_p, josa
from .result import constant_message, FAIL, SUCCESS, AnalysisResult


def _numeric_series(df, column):
    """열을 숫자로 바꾸고 결측을 뺀 Series를 돌려줍니다 (숫자로 못 바꾼 값도 결측 처리)."""
    if column not in df.columns:
        raise KeyError(f"데이터에 없는 열: {column}")
    s = pd.to_numeric(df[column], errors="coerce").dropna()
    return s


def sampling_distribution(df, column, sample_size=30, n_samples=1000, seed=42):
    """표본분포 실험. 표본평균들의 평균이 모평균에, 표준편차가 σ/√n에 가까운지 비교합니다 (중심극한정리).

    seed를 고정해 같은 결과를 다시 얻을 수 있습니다.
    """
    code = f'''# [목적] 표본분포 시뮬레이션: 크기 {sample_size}인 표본을 {n_samples}번 뽑아 표본평균의 분포 보기
rng = np.random.default_rng({seed})                       # 재현성을 위한 시드 고정
pop = sub[{column!r}].dropna().to_numpy()                 # 지금 데이터를 '모집단'으로 간주
means = [rng.choice(pop, {sample_size}, replace=True).mean() for _ in range({n_samples})]  # 복원 추출
print(np.mean(means), np.std(means, ddof=1))              # 표본평균들의 평균과 표준편차(=표준오차)
print(pop.std(ddof=0) / np.sqrt({sample_size}))            # 이론적 표준오차 σ/√n'''
    pop = _numeric_series(df, column).to_numpy()
    if len(pop) < 2:
        return AnalysisResult("표본분포 시뮬레이션", FAIL, "값이 2개 이상 필요합니다.", code=code)
    rng = np.random.default_rng(seed)
    means = rng.choice(pop, size=(n_samples, sample_size), replace=True).mean(axis=1)
    se_theory = pop.std(ddof=0) / np.sqrt(sample_size)
    fig = charts.histogram(pd.Series(means, name=f"{column} 표본평균 (n={sample_size})"))
    return AnalysisResult(
        "표본분포 시뮬레이션", SUCCESS,
        f"표본평균 {n_samples}개의 평균 {means.mean():.4f}, 표준오차 {means.std(ddof=1):.4f}",
        metrics={"모집단 평균 μ": round(pop.mean(), 4), "표본평균들의 평균": round(means.mean(), 4),
                 "모집단 표준편차 σ": round(pop.std(ddof=0), 4),
                 "표준오차(시뮬레이션)": round(means.std(ddof=1), 4), "표준오차(이론 σ/√n)": round(se_theory, 4),
                 "표본 크기 n": sample_size, "반복 횟수": n_samples},
        figures={"표본평균의 분포": fig},
        notes=["표본평균들의 평균은 모집단 평균에 가깝고, 퍼짐(표준오차)은 σ/√n에 가깝습니다.",
               "원래 분포가 치우쳐 있어도 n이 커지면 표본평균의 분포는 정규분포에 가까워집니다 (중심극한정리).",
               "여기서는 지금 데이터를 모집단으로 보고 복원 추출했습니다."],
        code=code,
    )


def confidence_interval_mean(df, column, level=0.95):
    """평균의 신뢰구간 (t분포). 하한·상한 = 평균 ± t × 표준오차, 표준오차 = s/√n."""
    code = f'''# [목적] 모평균의 {int(level*100)}% 신뢰구간 (t분포 사용)
x = sub[{column!r}].dropna()
n, mean = len(x), x.mean()
se = x.std(ddof=1) / np.sqrt(n)                           # 표준오차 = s / √n
t_crit = stats.t.ppf(1 - (1 - {level}) / 2, df=n - 1)     # 양쪽 꼬리 임계값, 자유도 n-1
print(mean - t_crit * se, mean + t_crit * se)             # 신뢰구간 = 평균 ± t × 표준오차'''
    x = _numeric_series(df, column)
    n = len(x)
    if n < 2:
        return AnalysisResult("신뢰구간 (평균)", FAIL, "값이 2개 이상 필요합니다.", code=code)
    se = x.std(ddof=1) / np.sqrt(n)
    t_crit = stats.t.ppf(1 - (1 - level) / 2, df=n - 1)
    lo, hi = x.mean() - t_crit * se, x.mean() + t_crit * se
    return AnalysisResult(
        "신뢰구간 (평균)", SUCCESS, f"{column} 평균의 {level:.0%} 신뢰구간: [{lo:.4f}, {hi:.4f}]",
        metrics={"표본 크기": n, "표본평균": round(x.mean(), 4), "표준오차": round(se, 4),
                 "t 임계값": round(t_crit, 4), "하한": round(lo, 4), "상한": round(hi, 4)},
        notes=[f"같은 방법으로 표본을 여러 번 뽑아 구간을 만들면, 그중 약 {level:.0%}가 실제 모평균을 포함한다는 뜻입니다. "
               f"'모평균이 이 구간에 있을 확률이 {level:.0%}'라는 뜻은 아닙니다.",
               "표본이 작으면 모집단이 정규분포에 가까워야 정확합니다."],
        code=code,
    )


def confidence_interval_proportion(df, column, category, level=0.95):
    """비율의 신뢰구간 (Wilson 방법). 표본이 작거나 비율이 0·1에 가까워도 정확한 편입니다."""
    from statsmodels.stats.proportion import proportion_confint
    code = f'''# [목적] '{category}' 비율의 {int(level*100)}% 신뢰구간 (Wilson 방법)
from statsmodels.stats.proportion import proportion_confint
x = sub[{column!r}].dropna()
count, n = (x == {category!r}).sum(), len(x)              # 해당 범주 개수, 전체 개수
print(count / n, proportion_confint(count, n, alpha=1 - {level}, method="wilson"))'''
    if column not in df.columns:
        raise KeyError(f"데이터에 없는 열: {column}")
    x = df[column].dropna()
    n, count = len(x), int((x == category).sum())
    if n == 0:
        return AnalysisResult("신뢰구간 (비율)", FAIL, "값이 없습니다.", code=code)
    lo, hi = proportion_confint(count, n, alpha=1 - level, method="wilson")
    return AnalysisResult(
        "신뢰구간 (비율)", SUCCESS, f"'{category}' 비율 {count / n:.4f}, {level:.0%} 신뢰구간 [{lo:.4f}, {hi:.4f}]",
        metrics={"해당 개수": count, "전체 개수": n, "표본비율": round(count / n, 4),
                 "하한": round(lo, 4), "상한": round(hi, 4)},
        notes=["Wilson 방법은 표본이 작거나 비율이 0·1에 가까워도 비교적 정확합니다."],
        code=code,
    )


def one_sample_ttest(df, column, mu0, alpha=0.05, alternative="two-sided"):
    """단일표본 t검정: 평균이 mu0과 다른지. 효과 크기 Cohen's d = (평균 − mu0) / s."""
    sign = {"two-sided": "≠", "greater": ">", "less": "<"}[alternative]
    code = f'''# [목적] 단일표본 t검정: 모평균이 {mu0}인지 검정
# 귀무가설 H0: μ = {mu0} / 대립가설 H1: μ {sign} {mu0}
x = sub[{column!r}].dropna()
t, p = stats.ttest_1samp(x, popmean={mu0}, alternative={alternative!r})
d = (x.mean() - {mu0}) / x.std(ddof=1)                    # 효과 크기 Cohen's d
print(t, p, d)'''
    x = _numeric_series(df, column)
    if len(x) < 2:
        return AnalysisResult("단일표본 t검정", FAIL, "값이 2개 이상 필요합니다.", code=code)
    if x.nunique() < 2:
        return AnalysisResult("단일표본 t검정", FAIL, constant_message(column), code=code)
    res = stats.ttest_1samp(x, popmean=mu0, alternative=alternative)
    d = (x.mean() - mu0) / x.std(ddof=1)
    h1_text = {"two-sided": f"{column}의 평균이 {josa(mu0, '과/와')} 다르다",
               "greater": f"{column}의 평균이 {mu0}보다 크다",
               "less": f"{column}의 평균이 {mu0}보다 작다"}[alternative]
    conclusion = interpret_p(res.pvalue, alpha, f"평균 = {mu0}", h1_text)
    notes = [EFFECT_NOTE]
    if len(x) < 30:
        sw_p = stats.shapiro(x).pvalue if len(x) >= 3 else None
        notes.append(f"표본이 {len(x)}개로 작습니다. 정규성 검정 p = {fmt_p(sw_p)}"
                     + (" → 정규성 가정이 의심되니 결과를 조심해서 해석하세요." if sw_p is not None and sw_p < alpha else "."))
    return AnalysisResult(
        "단일표본 t검정", SUCCESS, conclusion,
        metrics={"H0": f"μ = {mu0}", "H1": f"μ {sign} {mu0}", "표본 크기": len(x),
                 "표본평균": round(x.mean(), 4), "t 통계량": round(res.statistic, 4),
                 "자유도": len(x) - 1, "p값": fmt_p(res.pvalue), "유의수준": alpha,
                 "Cohen's d": f"{d:.3f} ({effect_label(d, 'd')})"},
        notes=notes, code=code,
    )
