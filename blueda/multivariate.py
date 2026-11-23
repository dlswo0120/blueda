"""4) 다변량 분석: 여러 독립변수와 종속변수의 관계.

다중회귀 y = b0 + b1·x1 + b2·x2 + ... (최소제곱법, statsmodels OLS)
- 범주형 독립변수는 더미 변수로 바꿉니다 (첫 범주를 기준으로 빼서 다중공선성 방지).
- 다중공선성: VIF(분산팽창계수). 10 이상이면 심각, 5 이상이면 주의 (관례 기준).
- 수정 R²: 변수를 많이 넣을수록 R²가 저절로 커지는 문제를 보정한 값.
"""

import pandas as pd

from .bivariate import _check_cols, _residual_plot
from .interpret import fmt_p, interpret_p, josa, p_column
from .result import constant_message, FAIL, SUCCESS, AnalysisResult


def multiple_regression(df, y, xs, alpha=0.05, standardize=False):
    import statsmodels.api as sm
    from statsmodels.stats.outliers_influence import variance_inflation_factor
    code = f'''# [목적] 다중회귀: 독립변수 {', '.join(xs)} → 종속변수 {y}
import statsmodels.api as sm
from statsmodels.stats.outliers_influence import variance_inflation_factor
d = sub[{[y] + list(xs)!r}].dropna()
X = pd.get_dummies(d[{list(xs)!r}], drop_first=True, dtype=float)  # 범주형 → 더미 변수 (첫 범주는 기준)
{"X = (X - X.mean()) / X.std(ddof=1)                        # 표준화: 계수 크기를 서로 비교하기 위해" if standardize else "# (표준화 안 함: 계수는 원래 단위 기준)"}
X = sm.add_constant(X)                                    # 절편 추가
model = sm.OLS(d[{y!r}].astype(float), X).fit()
vif = [variance_inflation_factor(X.values, i) for i in range(1, X.shape[1])]  # 다중공선성 점검
print(model.summary(), vif)'''
    _check_cols(df, y, *xs)
    if not xs:
        return AnalysisResult("다중회귀", FAIL, "독립변수를 1개 이상 지정하세요.", code=code)
    d = df[[y] + list(xs)].dropna()
    d[y] = pd.to_numeric(d[y], errors="coerce")
    d = d.dropna()
    if len(d) < 3:
        return AnalysisResult("다중회귀", FAIL, f"모든 변수에 값이 있는 행이 {len(d)}개뿐이라 계산할 수 없습니다 (3개 이상 필요).", code=code)
    if d[y].nunique() < 2:
        return AnalysisResult("다중회귀", FAIL, constant_message(y), code=code)
    X = pd.get_dummies(d[list(xs)], drop_first=True, dtype=float)
    flat = [c for c in X.columns if X[c].nunique() < 2]
    if flat:
        return AnalysisResult("다중회귀", FAIL, f"독립변수 {', '.join(map(str, flat))}의 값이 모두 같아 계수를 구할 수 없습니다. "
                              "이 변수를 빼거나 조건을 확인하세요.", code=code)
    if len(d) <= X.shape[1] + 1:
        return AnalysisResult("다중회귀", FAIL,
                              f"행 수({len(d)})가 변수 수({X.shape[1]})보다 충분히 많아야 합니다.", code=code)
    if standardize:
        X = (X - X.mean()) / X.std(ddof=1)
    X = sm.add_constant(X)
    m = sm.OLS(d[y].astype(float), X).fit()
    ci = m.conf_int()
    coef = pd.DataFrame({"계수": m.params, "표준오차": m.bse, "t": m.tvalues, "p값": m.pvalues,
                         "95% 하한": ci[0], "95% 상한": ci[1]}).round(4)
    vif = pd.Series([variance_inflation_factor(X.values, i) for i in range(1, X.shape[1])],
                    index=X.columns[1:], name="VIF").round(3)
    coef["VIF"] = vif
    sig = coef.index[(m.pvalues < alpha) & (coef.index != "const")].tolist()
    coef["p값"] = p_column(m.pvalues)
    notes = ["각 계수는 '다른 변수를 고정했을 때' 그 변수가 1 늘면 종속변수가 얼마나 변하는지(편회귀계수)입니다.",
             "범주형 변수는 더미로 바뀌었고, 빠진 첫 범주가 비교 기준입니다.",
             f"수정 R² = {m.rsquared_adj:.3f}: 변수 개수를 고려한 설명력입니다."]
    high = vif[vif >= 10].index.tolist()
    mid = vif[(vif >= 5) & (vif < 10)].index.tolist()
    if high:
        notes.append(f"다중공선성 심각 (VIF ≥ 10): {high}. 비슷한 변수를 빼거나 합치는 것을 검토하세요.")
    if mid:
        notes.append(f"다중공선성 주의 (5 ≤ VIF < 10): {mid}")
    notes.append("VIF 5·10 기준은 관례입니다. 회귀는 인과를 증명하지 않습니다.")
    conclusion = (interpret_p(m.f_pvalue, alpha, "모든 회귀계수 = 0", f"독립변수들이 {josa(y, '을/를')} 설명한다")
                  + f" 유의한 변수: {', '.join(sig) if sig else '없음'}.")
    return AnalysisResult(
        "다중회귀", SUCCESS, conclusion,
        metrics={"종속변수": y, "독립변수 수 (더미 포함)": X.shape[1] - 1, "표본 크기": int(m.nobs),
                 "R²": round(m.rsquared, 4), "수정 R²": round(m.rsquared_adj, 4),
                 "F 통계량": round(m.fvalue, 4), "F 검정 p값": fmt_p(m.f_pvalue),
                 "표준화": "예" if standardize else "아니오"},
        tables={"회귀계수": coef.rename(index={"const": "절편"})},
        figures={"잔차 vs 예측값": _residual_plot(m)},
        notes=notes, code=code,
    )
