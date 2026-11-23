"""F (선택): 통계 가정 점검. 설정에서 고른 검사만 실행합니다.

- normality      : 정규성 (Shapiro-Wilk, 표본이 5000개를 넘으면 D'Agostino K²)
- equal_variance : 등분산 (Levene, 그룹 컬럼 필요)
- correlation    : 상관계수 (Pearson, Spearman) + 인과 해석 주의 문구

p-value는 표본 크기에 민감합니다. 표본이 크면 아주 작은 차이도
'정규성 위배'로 나올 수 있으니 히스토그램·Q-Q plot과 함께 보세요.
"""

import pandas as pd
from scipy import stats

ALPHA = 0.05  # 유의수준


def normality(df, columns):
    """정규성 검정: 5,000개 이하는 Shapiro-Wilk, 넘으면 D'Agostino(normaltest). 표본이 크면 작은 차이도 유의하게 나오니 그림과 함께 보세요."""
    code = f'''# [목적] 숫자 컬럼이 정규분포를 따르는지 검정 (귀무가설: 정규분포를 따른다)
from scipy import stats
for col in {columns!r}:
    x = df[col].dropna()
    if len(x) <= 5000:
        stat, p = stats.shapiro(x)        # 표본이 작을 때: Shapiro-Wilk
    else:
        stat, p = stats.normaltest(x)     # 표본이 클 때: D'Agostino K²
    print(col, round(p, 4), "정규성 위배" if p < {ALPHA} else "정규성 가정 가능")'''
    rows = []
    for col in columns:
        x = df[col].dropna()
        if len(x) < 3:
            rows.append((col, None, None, "표본 부족 (Shapiro 최소 3개)"))
            continue
        # normaltest(D'Agostino)는 최소 8개가 필요하지만, 여기서는 5000개 초과일 때만 쓰므로 해당 없음
        test = "Shapiro-Wilk" if len(x) <= 5000 else "D'Agostino K²"
        _, p = stats.shapiro(x) if len(x) <= 5000 else stats.normaltest(x)
        rows.append((col, test, round(float(p), 4), "정규성 위배" if p < ALPHA else "정규성 가정 가능"))
    result = pd.DataFrame(rows, columns=["column", "test", "p_value", "판단"])
    return "정규성 검정", code, result


def equal_variance(df, columns, group_col):
    """등분산 검정 (Levene, center=median = Brown-Forsythe). t검정·분산분석의 Student/Welch 선택에 씁니다."""
    code = f'''# [목적] 그룹({group_col!r})별 분산이 같은지 검정 (귀무가설: 분산이 같다)
from scipy import stats
for col in {columns!r}:
    groups = [g[col].dropna() for _, g in df.groupby({group_col!r})]  # 그룹별로 값 나누기
    stat, p = stats.levene(*groups)       # SciPy 기본 center='median' → Brown-Forsythe 검정 (정규성이 약해도 안정적)
    print(col, round(p, 4), "등분산 아님" if p < {ALPHA} else "등분산 가정 가능")'''
    rows = []
    for col in columns:
        groups = [g[col].dropna() for _, g in df.groupby(group_col)]
        groups = [g for g in groups if len(g) >= 2]
        if len(groups) < 2:
            rows.append((col, None, "그룹 부족"))
            continue
        _, p = stats.levene(*groups)
        rows.append((col, round(float(p), 4), "등분산 아님" if p < ALPHA else "등분산 가정 가능"))
    result = pd.DataFrame(rows, columns=["column", "p_value", "판단"])
    return "등분산 검정 (Levene, center=median = Brown-Forsythe)", code, result


def correlation(df, columns):
    """수치형 열들의 상관행렬 (Pearson). 상관은 인과가 아님(CAUSATION_NOTE)을 함께 안내합니다."""
    code = f'''# [목적] 숫자 컬럼 간 상관관계 확인
sub = df[{columns!r}]
pearson = sub.corr(method="pearson")      # 선형 관계의 강도
spearman = sub.corr(method="spearman")    # 순위 기반. 이상치·비선형에 덜 민감
print(pearson.round(3))
print(spearman.round(3))'''
    sub = df[columns]
    pearson = sub.corr(method="pearson").round(3)
    spearman = sub.corr(method="spearman").round(3)
    result = f"[Pearson]\n{pearson}\n\n[Spearman]\n{spearman}"
    return "상관 분석", code, result


def correlation_result(df):
    """분석 범위 안의 수치형 열로 상관분석을 하고 AnalysisResult로 돌려줍니다."""
    from .result import FAIL, SUCCESS, AnalysisResult
    cols = df.select_dtypes(include="number").columns.tolist()
    if len(cols) < 2:
        return AnalysisResult("상관분석", FAIL, f"수치형 열이 2개 이상 필요합니다 (현재 {len(cols)}개).")
    _, code, _ = correlation(df, cols)
    sub = df[cols]
    return AnalysisResult(
        "상관분석", SUCCESS, f"수치형 {len(cols)}개 열 상관계수 계산 완료",
        tables={"Pearson 상관": sub.corr("pearson").round(3), "Spearman 상관": sub.corr("spearman").round(3)},
        notes=[CAUSATION_NOTE], code=code,
    )


CAUSATION_NOTE = (
    "상관관계는 인과관계가 아닙니다. 두 변수가 함께 움직여도 "
    "제3의 변수(교란변수)나 우연일 수 있습니다. 보고서에는 '관련이 있다'로 표현하세요."
)


def run_stat_checks(df, checks, columns=None, group_col=None, logger=None):
    """설정에서 고른 검사만 실행합니다."""
    if columns is None:
        columns = df.select_dtypes(include="number").columns.tolist()
    outputs = {}
    for name in checks:
        if name == "normality":
            title, code, res = normality(df, columns)
            interp = "p < 0.05면 정규성 위배. 표본이 크면 그래프와 함께 판단하세요."
        elif name == "equal_variance":
            if group_col is None:
                print("[BLUEDA] equal_variance는 group_col이 필요해서 건너뜁니다.")
                continue
            title, code, res = equal_variance(df, columns, group_col)
            interp = "등분산이 아니면 t-test 대신 Welch's t-test를 고려하세요."
        elif name == "correlation":
            if len(columns) < 2:
                continue
            title, code, res = correlation(df, columns)
            interp = CAUSATION_NOTE
        else:
            continue
        outputs[name] = res
        if logger is not None:
            logger.log(f"[통계 가정 점검] {title}", code, res, interp)
    return outputs
