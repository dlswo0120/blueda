"""3) 이변량 분석: 두 변수 사이의 차이와 관계.

- 범주형 × 수치형 : 독립표본 t검정(두 그룹), 일원분산분석 ANOVA(세 그룹 이상) + Tukey HSD 사후검정
- 범주형 × 범주형 : 교차표, 카이제곱 독립성 검정 (기대빈도 부족 시 Fisher 정확검정 안내)
- 수치형 × 수치형 : 상관분석(Pearson·Spearman + p값), 단순회귀

각 검정은 전제 조건(정규성, 등분산, 기대빈도)을 함께 점검해서 결과에 적습니다.
"""

import numpy as np
import pandas as pd
from scipy import stats

from . import charts
from .interpret import EFFECT_NOTE, effect_label, fmt_p, interpret_p, josa, p_column
from .result import constant_message, FAIL, SUCCESS, AnalysisResult


def _check_cols(df, *cols):
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise KeyError(f"데이터에 없는 열: {missing}")


def _group_boxplot(df, group_col, value_col, title):
    df = charts.sample(df)  # 큰 데이터는 표본으로 그림
    fig, ax = charts.new_figure()
    names = sorted(df[group_col].dropna().unique().tolist(), key=str)
    values = [pd.to_numeric(df.loc[df[group_col] == n, value_col], errors="coerce").dropna() for n in names]
    ax.boxplot(values, patch_artist=True, flierprops=charts.FLIER,
               boxprops={"facecolor": "#DCE6F2", "edgecolor": charts.EDGE},
               medianprops={"color": charts.EDGE, "linewidth": 2})
    # 그룹 평균(◆)과 95% 신뢰구간(세로 막대): 평균 ± t × 표준오차
    for i, v in enumerate(values, start=1):
        if len(v) >= 2:
            half = stats.t.ppf(0.975, len(v) - 1) * v.std(ddof=1) / np.sqrt(len(v))
            ax.errorbar(i, v.mean(), yerr=half, fmt="D", color="#E07B39", capsize=4)
    ax.set_xticks(range(1, len(names) + 1), [str(n) for n in names])
    ax.set_xlabel(group_col)
    ax.set_ylabel(value_col)
    suffix = charts.fit_box_axis(ax, values)              # 꼬리가 긴 분포면 로그 눈금 또는 가운데 99%
    ax.set_title(title + suffix, fontsize=10 if suffix else None)
    fig.tight_layout()
    charts.plt.close(fig)
    return fig


def _normality_by_group(groups, alpha):
    """그룹별 Shapiro-Wilk. 표본이 크면(그룹당 30 이상) 중심극한정리로 정규성 부담이 줄어듭니다."""
    lines = []
    for name, g in groups.items():
        if len(g) < 3:
            lines.append(f"{name}: 표본 부족")
        elif len(g) > 5000:
            lines.append(f"{name}: 표본이 커서 검정 생략 (중심극한정리)")
        else:
            p = stats.shapiro(g).pvalue
            lines.append(f"{name}: p={fmt_p(p)}{' (정규성 의심)' if p < alpha else ''}")
    return lines


# ---------------- 범주형 × 수치형 ----------------
def t_test(df, group_col, value_col, groups=None, alpha=0.05, method="auto", alternative="two-sided"):
    """독립표본 t검정. method: auto(등분산 검정으로 선택) / student / welch"""
    _check_cols(df, group_col, value_col)
    data = df[[group_col, value_col]].dropna()
    levels = groups or sorted(data[group_col].unique().tolist(), key=str)
    first, second = (levels + [None, None])[:2]
    code = f'''# [목적] 두 그룹({group_col})의 {value_col} 평균 차이 검정
# 귀무가설 H0: 두 그룹의 평균이 같다 / 대립가설 H1: 다르다
a = sub.loc[sub[{group_col!r}] == {first!r}, {value_col!r}].dropna()
b = sub.loc[sub[{group_col!r}] == {second!r}, {value_col!r}].dropna()
lev_p = stats.levene(a, b).pvalue                         # 등분산 검정 (center=median, Brown-Forsythe)
equal_var = lev_p >= {alpha}                             # 등분산이면 Student, 아니면 Welch
t, p = stats.ttest_ind(a, b, equal_var=equal_var, alternative={alternative!r})
sp = np.sqrt(((len(a)-1)*a.var() + (len(b)-1)*b.var()) / (len(a)+len(b)-2))  # 합동 표준편차
d = (a.mean() - b.mean()) / sp                            # 효과 크기 Cohen's d
print(lev_p, t, p, d)'''
    if len(levels) == 2 and data[value_col].nunique() < 2:
        return AnalysisResult("독립표본 t검정", FAIL, constant_message(value_col), code=code)
    if len(levels) != 2:
        return AnalysisResult("독립표본 t검정", FAIL,
                              f"그룹이 2개여야 합니다 (현재 {len(levels)}개: {levels[:5]}). 3개 이상은 ANOVA를 쓰세요.",
                              code=code)
    a = pd.to_numeric(data.loc[data[group_col] == levels[0], value_col], errors="coerce").dropna()
    b = pd.to_numeric(data.loc[data[group_col] == levels[1], value_col], errors="coerce").dropna()
    if len(a) < 2 or len(b) < 2:
        return AnalysisResult("독립표본 t검정", FAIL, "각 그룹에 값이 2개 이상 필요합니다.", code=code)
    lev_p = stats.levene(a, b).pvalue
    equal_var = {"auto": lev_p >= alpha, "student": True, "welch": False}[method]
    res = stats.ttest_ind(a, b, equal_var=equal_var, alternative=alternative)
    sp = np.sqrt(((len(a) - 1) * a.var(ddof=1) + (len(b) - 1) * b.var(ddof=1)) / (len(a) + len(b) - 2))
    d = (a.mean() - b.mean()) / sp
    test_name = "Student t검정 (등분산 가정)" if equal_var else "Welch t검정 (등분산 가정 안 함)"
    conclusion = interpret_p(res.pvalue, alpha, f"{josa(levels[0], '과/와')} {levels[1]}의 {value_col} 평균이 같다",
                             f"두 그룹의 {value_col} 평균이 다르다")
    summary = data.groupby(group_col)[value_col].agg(["count", "mean", "std", "median"]).loc[levels].round(4)
    summary.columns = ["개수", "평균", "표준편차", "중앙값"]
    return AnalysisResult(
        "독립표본 t검정", SUCCESS, conclusion,
        metrics={"검정 방법": test_name, "등분산 검정 p (Levene/Brown-Forsythe)": fmt_p(lev_p),
                 "t 통계량": round(res.statistic, 4), "p값": fmt_p(res.pvalue), "유의수준": alpha,
                 "평균 차이": round(a.mean() - b.mean(), 4), "Cohen's d": f"{d:.3f} ({effect_label(d, 'd')})"},
        tables={"그룹별 요약": summary},
        figures={f"{group_col}별 {value_col}": _group_boxplot(data[data[group_col].isin(levels)], group_col, value_col,
                                                            f"{group_col}별 {value_col} (◆ 평균, 막대 95% CI)")},
        notes=["정규성 (Shapiro-Wilk): " + " / ".join(_normality_by_group({str(levels[0]): a, str(levels[1]): b}, alpha)),
               "method='auto'는 등분산 검정 결과로 Student/Welch를 고릅니다. 처음부터 Welch를 쓰자는 의견도 많습니다.",
               EFFECT_NOTE],
        code=code,
    )


def anova(df, group_col, value_col, alpha=0.05, posthoc=True):
    from statsmodels.formula.api import ols
    from statsmodels.stats.anova import anova_lm
    from statsmodels.stats.multicomp import pairwise_tukeyhsd
    code = f'''# [목적] 세 그룹 이상({group_col})의 {value_col} 평균 차이 검정 (일원분산분석)
# 귀무가설 H0: 모든 그룹의 평균이 같다 / 대립가설 H1: 적어도 한 그룹은 다르다
from statsmodels.formula.api import ols
from statsmodels.stats.anova import anova_lm
from statsmodels.stats.multicomp import pairwise_tukeyhsd
data = sub[[{group_col!r}, {value_col!r}]].dropna()
model = ols("Q('{value_col}') ~ C(Q('{group_col}'))", data=data).fit()   # 그룹을 범주형 변수로
table = anova_lm(model, typ=2)                             # 분산분석표: 집단 간 / 집단 내 제곱합, F, p
eta2 = table["sum_sq"].iloc[0] / table["sum_sq"].sum()     # 효과 크기 에타제곱 = SS집단간 / SS전체
tukey = pairwise_tukeyhsd(data[{value_col!r}], data[{group_col!r}], alpha={alpha})  # 사후검정: 어느 쌍이 다른지
print(table, eta2, tukey)'''
    _check_cols(df, group_col, value_col)
    data = df[[group_col, value_col]].dropna().copy()
    data[value_col] = pd.to_numeric(data[value_col], errors="coerce")
    data = data.dropna()
    k = data[group_col].nunique()
    if k < 2:
        return AnalysisResult("일원분산분석 (ANOVA)", FAIL, f"그룹이 2개 이상 필요합니다 (현재 {k}개).", code=code)
    if data.groupby(group_col, observed=True)[value_col].var().fillna(0).eq(0).all():
        # 그룹 안 분산이 모두 0이면 F = 집단간/0 으로 정의되지 않음 (계산하면 엉터리 p값이 나옴)
        return AnalysisResult("일원분산분석 (ANOVA)", FAIL, constant_message(value_col) +
                              " (그룹 안의 값이 모두 같아 그룹 내 분산이 0입니다.)", code=code)
    if data.groupby(group_col).size().min() < 2:
        return AnalysisResult("일원분산분석 (ANOVA)", FAIL, "각 그룹에 값이 2개 이상 필요합니다.", code=code)
    model = ols(f"Q('{value_col}') ~ C(Q('{group_col}'))", data=data).fit()
    table = anova_lm(model, typ=2)
    table.index = ["집단 간", "집단 내 (잔차)"]
    table.columns = ["제곱합", "자유도", "F", "p값"]
    f_val, p = table.loc["집단 간", "F"], table.loc["집단 간", "p값"]
    eta2 = table.loc["집단 간", "제곱합"] / table["제곱합"].sum()
    groups = {str(n): g[value_col] for n, g in data.groupby(group_col)}
    lev_p = stats.levene(*groups.values()).pvalue
    tables = {"분산분석표": table.round(4),
              "그룹별 요약": data.groupby(group_col)[value_col].agg(["count", "mean", "std"]).round(4)
              .rename(columns={"count": "개수", "mean": "평균", "std": "표준편차"})}
    notes = ["정규성 (Shapiro-Wilk): " + " / ".join(_normality_by_group(groups, alpha)),
             f"등분산 검정 (Levene/Brown-Forsythe) p = {fmt_p(lev_p)}"
             + (" → 등분산 가정이 의심됩니다. Welch ANOVA가 더 적절할 수 있습니다." if lev_p < alpha else ""),
             EFFECT_NOTE]
    if posthoc and p < alpha and k >= 3:
        tk = pairwise_tukeyhsd(data[value_col], data[group_col].astype(str), alpha=alpha)
        tk_df = pd.DataFrame(tk.summary().data[1:], columns=tk.summary().data[0])
        tk_df.columns = ["그룹1", "그룹2", "평균차", "보정 p", "하한", "상한", "유의"]
        tables["사후검정 (Tukey HSD)"] = tk_df
        pairs = tk_df[tk_df["유의"]]
        notes.append(f"Tukey HSD: 유의한 차이가 있는 쌍 {len(pairs)}개"
                     + (f" ({', '.join(f'{a}–{b}' for a, b in zip(pairs['그룹1'], pairs['그룹2']))})" if len(pairs) else ""))
    conclusion = interpret_p(p, alpha, f"모든 {group_col}의 {value_col} 평균이 같다",
                             f"적어도 한 {group_col}의 {value_col} 평균이 다르다")
    return AnalysisResult(
        "일원분산분석 (ANOVA)", SUCCESS, conclusion,
        metrics={"그룹 수": k, "F 통계량": round(f_val, 4), "p값": fmt_p(p), "유의수준": alpha,
                 "에타제곱 η²": f"{eta2:.3f} ({effect_label(eta2, 'eta2')})"},
        tables=tables,
        figures={f"{group_col}별 {value_col}": _group_boxplot(data, group_col, value_col,
                                                            f"{group_col}별 {value_col} (◆ 평균, 막대 95% CI)")},
        notes=notes, code=code,
    )


# ---------------- 범주형 × 범주형 ----------------
def chi_square(df, row_col, col_col, alpha=0.05):
    code = f'''# [목적] 두 범주형 변수({row_col}, {col_col})가 서로 관련이 있는지 검정
# 귀무가설 H0: 두 변수는 독립이다(관련 없음) / 대립가설 H1: 관련이 있다
table = pd.crosstab(sub[{row_col!r}], sub[{col_col!r}])    # 교차표 (관측빈도)
chi2, p, dof, expected = stats.chi2_contingency(table)    # 2×2 표는 Yates 연속성 보정이 자동 적용됨
low = (expected < 5).mean()                               # 기대빈도 5 미만 칸의 비율 (20% 넘으면 부정확)
n = table.to_numpy().sum()
v = np.sqrt(chi2 / (n * (min(table.shape) - 1)))           # 효과 크기 Cramér's V
print(table, chi2, p, dof, low, v)'''
    _check_cols(df, row_col, col_col)
    table = pd.crosstab(df[row_col], df[col_col])
    if min(table.shape) < 2:
        return AnalysisResult("카이제곱 독립성 검정", FAIL, "두 변수 모두 범주가 2개 이상이어야 합니다.", code=code)
    chi2, p, dof, expected = stats.chi2_contingency(table)
    n = table.to_numpy().sum()
    v = np.sqrt(chi2 / (n * (min(table.shape) - 1)))
    low = float((expected < 5).mean())
    notes = [EFFECT_NOTE]
    metrics = {"카이제곱 χ²": round(chi2, 4), "자유도": int(dof), "p값": fmt_p(p), "유의수준": alpha,
               "Cramér's V": f"{v:.3f} ({effect_label(v, 'cramer_v')})",
               "기대빈도 5 미만 칸 비율": f"{low:.0%}"}
    if table.shape == (2, 2):
        notes.append("2×2 표라서 Yates 연속성 보정을 적용했습니다.")
    if low > 0.2:
        notes.append("기대빈도가 5 미만인 칸이 20%를 넘어 카이제곱 근사가 부정확할 수 있습니다.")
        if table.shape == (2, 2):
            _, fp = stats.fisher_exact(table)
            metrics["Fisher 정확검정 p"] = fmt_p(fp)
            notes.append("2×2 표이므로 Fisher 정확검정 결과도 함께 보세요.")
        else:
            notes.append("범주를 합치거나 표본을 늘리는 것을 검토하세요.")
    ratio = pd.crosstab(df[row_col], df[col_col], normalize="index").round(4)  # 행 기준 비율
    fig, ax = charts.new_figure()
    import seaborn as sns
    sns.heatmap(table, annot=True, fmt="d", cmap="Blues", cbar=False, ax=ax)
    ax.set_title(f"{row_col} × {col_col} 교차표")
    fig.tight_layout()
    charts.plt.close(fig)
    conclusion = interpret_p(p, alpha, f"{josa(row_col, '과/와')} {josa(col_col, '은/는')} 관련이 없다", f"{josa(row_col, '과/와')} {josa(col_col, '은/는')} 관련이 있다")
    return AnalysisResult(
        "카이제곱 독립성 검정", SUCCESS, conclusion, metrics=metrics,
        tables={"교차표 (관측빈도)": table, "행 기준 비율": ratio,
                "기대빈도": pd.DataFrame(expected, index=table.index, columns=table.columns).round(2)},
        figures={"교차표 히트맵": fig}, notes=notes, code=code,
    )


# ---------------- 수치형 × 수치형 ----------------
def correlation_test(df, x, y, alpha=0.05):
    code = f'''# [목적] 두 수치형 변수({x}, {y})의 상관계수와 유의성
# 귀무가설 H0: 상관계수 = 0 / 대립가설 H1: 상관계수 ≠ 0
d = sub[[{x!r}, {y!r}]].dropna()
r, p = stats.pearsonr(d[{x!r}], d[{y!r}])                 # Pearson: 직선 관계의 강도
rho, p_s = stats.spearmanr(d[{x!r}], d[{y!r}])            # Spearman: 순위 기반, 이상치·비선형에 덜 민감
print(r, p, rho, p_s)'''
    _check_cols(df, x, y)
    d = df[[x, y]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(d) < 3:
        return AnalysisResult("상관분석 (검정)", FAIL, "짝지어진 값이 3개 이상 필요합니다.", code=code)
    for c in (x, y):
        if d[c].nunique() < 2:
            return AnalysisResult("상관분석 (검정)", FAIL, constant_message(c), code=code)
    r, p = stats.pearsonr(d[x], d[y])
    rho, p_s = stats.spearmanr(d[x], d[y])
    import seaborn as sns
    fig, ax = charts.new_figure()
    sns.scatterplot(data=charts.sample(d), x=x, y=y, ax=ax, color=charts.PRIMARY, alpha=0.7)
    ax.set_title(f"{x} vs {y} (Pearson r = {r:.3f})")
    fig.tight_layout()
    charts.plt.close(fig)
    return AnalysisResult(
        "상관분석 (검정)", SUCCESS,
        interpret_p(p, alpha, f"{josa(x, '과/와')} {y}의 상관계수 = 0", f"{josa(x, '과/와')} {y} 사이에 선형 상관이 있다"),
        metrics={"표본 크기": len(d), "Pearson r": f"{r:.4f} ({effect_label(r, 'r')})", "Pearson p": fmt_p(p),
                 "Spearman ρ": f"{rho:.4f}", "Spearman p": fmt_p(p_s), "결정계수 r²": round(r ** 2, 4)},
        figures={"산점도": fig},
        notes=["상관관계는 인과관계가 아닙니다.",
               "Pearson과 Spearman이 크게 다르면 이상치나 비선형 관계를 의심하세요.", EFFECT_NOTE],
        code=code,
    )


def simple_regression(df, x, y, alpha=0.05):
    import statsmodels.api as sm
    code = f'''# [목적] 단순회귀: {x}(으)로 {josa(y, '을/를')} 설명하는 직선 y = b0 + b1·x 찾기 (최소제곱법)
import statsmodels.api as sm
d = sub[[{x!r}, {y!r}]].dropna()
X = sm.add_constant(d[{x!r}])                             # 절편(b0)을 넣기 위해 상수항 열 추가
model = sm.OLS(d[{y!r}], X).fit()                         # 잔차 제곱합이 최소가 되는 b0, b1
print(model.summary())                                    # 계수, 표준오차, t, p, R² 등 전체 결과'''
    _check_cols(df, x, y)
    d = df[[x, y]].apply(pd.to_numeric, errors="coerce").dropna()
    if len(d) < 3:
        return AnalysisResult("단순회귀", FAIL, "짝지어진 값이 3개 이상 필요합니다.", code=code)
    for c in (x, y):
        if d[c].nunique() < 2:
            return AnalysisResult("단순회귀", FAIL, constant_message(c), code=code)
    X = sm.add_constant(d[x])
    m = sm.OLS(d[y], X).fit()
    coef = pd.DataFrame({"계수": m.params, "표준오차": m.bse, "t": m.tvalues, "p값": m.pvalues,
                         "95% 하한": m.conf_int()[0], "95% 상한": m.conf_int()[1]}).round(4)
    coef["p값"] = p_column(m.pvalues).to_numpy()
    coef.index = ["절편 (b0)", f"{x} (b1)"]
    b0, b1, p1 = m.params.iloc[0], m.params.iloc[1], m.pvalues.iloc[1]
    import seaborn as sns
    fig, ax = charts.new_figure()
    sns.regplot(data=charts.sample(d), x=x, y=y, ax=ax, color=charts.PRIMARY, line_kws={"color": "#E07B39"})
    ax.set_title(f"{y} = {b0:.3f} + {b1:.3f}·{x}  (R² = {m.rsquared:.3f})")
    fig.tight_layout()
    charts.plt.close(fig)
    resid_fig = _residual_plot(m)
    return AnalysisResult(
        "단순회귀", SUCCESS,
        f"{y} = {b0:.4f} + {b1:.4f} × {x}. " + interpret_p(p1, alpha, f"{x}의 기울기 = 0", f"{josa(x, '이/가')} {josa(y, '을/를')} 설명한다"),
        metrics={"회귀식": f"{y} = {b0:.4f} + {b1:.4f}·{x}", "기울기 b1": round(b1, 4), "기울기 p값": fmt_p(p1),
                 "결정계수 R²": round(m.rsquared, 4), "표본 크기": int(m.nobs)},
        tables={"회귀계수": coef},
        figures={"산점도와 회귀선": fig, "잔차 vs 예측값": resid_fig},
        notes=[f"기울기 b1 = {josa(x, '이/가')} 1 늘 때 {josa(y, '이/가')} 평균적으로 {b1:.4f}만큼 변한다는 뜻입니다.",
               f"R² = {m.rsquared:.3f}: {y} 변동의 {m.rsquared:.1%}를 {x}로 설명합니다.",
               "잔차 그림에 패턴(곡선, 깔때기 모양)이 보이면 선형·등분산 가정을 의심하세요.",
               "회귀는 관계를 설명할 뿐 인과를 증명하지 않습니다."],
        code=code,
    )


def _residual_plot(model):
    fig, ax = charts.new_figure()
    idx = charts.sample(model.fittedvalues).index  # 큰 데이터는 표본 점만
    ax.scatter(model.fittedvalues.loc[idx], model.resid.loc[idx], color=charts.PRIMARY, alpha=0.7)
    ax.axhline(0, color="#E07B39", linewidth=1.5)
    ax.set_xlabel("예측값")
    ax.set_ylabel("잔차")
    ax.set_title("잔차 vs 예측값")
    fig.tight_layout()
    charts.plt.close(fig)
    return fig
