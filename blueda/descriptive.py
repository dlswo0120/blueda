"""1) 기술통계: 관측한 데이터의 특성과 분포 요약.

- 수치형: 개수, 평균, 중앙값, 표준편차, 최솟값, Q1, Q3, 최댓값, 왜도, 첨도
- 범주형: 빈도, 비율, 최빈값
- 시각화: 히스토그램, 박스플롯, 범주 빈도 막대

추정량 표기 (레퍼런스 문서 기준):
- 표준편차: 표본 표준편차 (ddof=1, n−1로 나눔)
- 왜도: 편향 보정 G₁ / 첨도: 편향 보정 초과첨도 G₂ (정규분포 = 0)
- 사분위수: linear 방식 (Hyndman & Fan 7번)
"""

import pandas as pd

from . import charts
from .result import FAIL, SUCCESS, AnalysisResult

ESTIMATOR_NOTE = (
    "표준편차는 표본 표준편차(n−1), 왜도·첨도는 편향 보정값(pandas 기본), "
    "사분위수는 linear 방식입니다. NumPy·SciPy 기본값과 다를 수 있습니다."
)


def _numeric_cols(df, var_types=None):
    """수치형 열. 사용자가 범주형·ID로 지정한 숫자 열은 뺍니다.
    지정이 없으면 ID 후보(행 번호·일련번호)도 뺍니다. 평균·표준편차가 의미 없는 값이기 때문입니다.
    사용자가 '수치형'으로 지정하면 다시 포함됩니다."""
    return _split_numeric(df, var_types)[0]


def _split_numeric(df, var_types=None):
    """(분석할 수치형 열, 자동으로 뺀 ID 후보 열)"""
    from .variables import is_strong_id
    var_types = var_types or {}
    use, skipped = [], []
    for c in df.select_dtypes(include="number").columns:
        kind = var_types.get(c)
        if kind is None and is_strong_id(df[c], c):
            skipped.append(c)
        elif (kind or "수치형") == "수치형":
            use.append(c)
    return use, skipped


def _id_note(skipped):
    """기술통계에서 자동으로 뺀 ID 열이 있으면 안내 문장을, 없으면 None을 돌려줍니다."""
    if not skipped:
        return None
    return (f"ID 후보로 판단해 뺀 열: {', '.join(map(str, skipped))} (모든 값이 다른 연속 번호 또는 ID 이름 → 평균이 의미 없음). "
            "실제 측정값이면 열 이름을 오른쪽 클릭해 '수치형'으로 바꾸세요.")


def _categorical_cols(df, max_unique=50, var_types=None):
    """문자열·범주·불리언 열 + 사용자가 범주형으로 지정한 숫자 열."""
    var_types = var_types or {}
    cols = df.select_dtypes(include=["object", "string", "category", "bool"]).columns.tolist()
    cols = [c for c in cols if var_types.get(c, "범주형") == "범주형"]
    cols += [c for c, k in var_types.items() if k == "범주형" and c in df.columns and c not in cols]
    return [c for c in cols if df[c].nunique(dropna=True) <= max_unique]


def zscores(df, threshold=3.0, var_types=None):
    """z점수 = (값 − 평균) ÷ 표준편차. |z|가 기준보다 큰 값을 이상값 후보로 표시합니다."""
    cols = _numeric_cols(df, var_types)
    code = f'''# [목적] z점수로 표준화하고 평균에서 멀리 떨어진 값 찾기
num = sub.select_dtypes(include="number")
z = (num - num.mean()) / num.std(ddof=1)     # z점수: 평균 0, 표준편차 1로 바꾼 값
flag = z.abs() > {threshold}                  # |z| > {threshold}: 이상값 후보 (관례 기준)
print(flag.sum())                             # 열별 이상값 후보 개수
print(sub[flag.any(axis=1)])                  # 이상값 후보가 있는 행'''
    if not cols:
        return AnalysisResult("z점수", FAIL, "분석 범위에 수치형 열이 없습니다.", code=code)
    num = df[cols]
    z = (num - num.mean()) / num.std(ddof=1)
    flag = z.abs() > threshold
    counts = flag.sum()
    flagged = df[flag.any(axis=1)].copy()
    for c in cols:
        flagged[f"{c}_z"] = z.loc[flagged.index, c].round(3)
    summary = pd.DataFrame({"평균": num.mean(), "표준편차": num.std(ddof=1),
                            f"|z|>{threshold} 개수": counts, "최대 |z|": z.abs().max()}).round(4)
    return AnalysisResult(
        "z점수", SUCCESS, f"|z| > {threshold} 이상값 후보 {int(flag.any(axis=1).sum())}행",
        metrics={"기준": f"|z| > {threshold}", "후보 행 수": int(flag.any(axis=1).sum())},
        tables={"z점수 요약": summary, "이상값 후보 행": flagged.head(200), "z점수 전체": z.round(4)},
        notes=[f"|z| > {threshold} 기준은 관례입니다. 분포가 치우쳐 있으면 IQR 기준(박스플롯)도 함께 보세요.",
               "z점수는 정규분포에 가까울 때 해석이 자연스럽습니다 (|z|>3 비율 ≈ 0.27%)."],
        code=code,
    )


def describe_numeric(df, with_charts=True, iqr_k=1.5, var_types=None):
    """수치형 열 요약: 개수·평균·표준편차·사분위수·왜도·첨도·결측·이상값 후보 수, 열마다 히스토그램·상자그림.

    인자: with_charts 차트 여부, iqr_k 이상값 경계 배수, var_types 사용자가 지정한 변수 종류
    ID 열(연속 번호·ID 이름)은 자동으로 빼고 안내합니다.
    """
    cols, skipped = _split_numeric(df, var_types)
    code = ('# [목적] 수치형 열의 분포 요약\n'
            + (f'# ID 후보 열 {skipped!r}은(는) 평균이 의미 없어 제외\n' if skipped else '')
            + f'num = sub[{cols!r}]\n') + '''summary = pd.DataFrame({
    "개수": num.count(),               # 결측 제외 개수
    "평균": num.mean(),
    "중앙값": num.median(),
    "표준편차": num.std(ddof=1),        # 표본 표준편차 (n-1로 나눔)
    "최솟값": num.min(),
    "Q1": num.quantile(0.25),          # 1사분위수 (linear 방식)
    "Q3": num.quantile(0.75),          # 3사분위수
    "최댓값": num.max(),
    "왜도": num.skew(),                 # 편향 보정 G1, 0에 가까울수록 대칭
    "첨도": num.kurt(),                 # 편향 보정 초과첨도 G2, 정규분포 = 0
}).round(4)
print(summary)'''
    if not cols:
        return AnalysisResult("기술통계 - 수치형", FAIL, "분석 범위에 수치형 열이 없습니다.", code=code)
    num = df[cols]
    summary = pd.DataFrame({
        "개수": num.count(), "평균": num.mean(), "중앙값": num.median(),
        "표준편차": num.std(ddof=1), "최솟값": num.min(),
        "Q1": num.quantile(0.25), "Q3": num.quantile(0.75), "최댓값": num.max(),
        "왜도": num.skew(), "첨도": num.kurt(),
    }).round(4)
    figures = {}
    if with_charts:
        for c in cols:
            figures[f"{c} 히스토그램"] = charts.histogram(df[c])
            figures[f"{c} 박스플롯"] = charts.boxplot(df[c], iqr_k)
    notes = [ESTIMATOR_NOTE]
    if _id_note(skipped):
        notes.append(_id_note(skipped))
    if with_charts and charts.sample_note(len(df)):
        notes.append(charts.sample_note(len(df)))
    small = summary.index[summary["개수"] < 4].tolist()
    if small:
        notes.append(f"값이 4개 미만인 열은 왜도·첨도를 계산할 수 없습니다: {small}")
    return AnalysisResult(
        "기술통계 - 수치형", SUCCESS, f"수치형 {len(cols)}개 열 요약 완료",
        metrics={"분석 열 수": len(cols), "행 수": len(df)},
        tables={"수치형 요약": summary}, figures=figures, notes=notes, code=code,
    )


def describe_categorical(df, with_charts=True, top_n=20, max_unique=50, var_types=None):
    """범주형 열 요약: 범주 수·최빈값·결측, 열마다 빈도표와 빈도 막대.

    값 종류가 max_unique보다 많은 열은 범주로 보기 어려워 뺍니다. 막대는 상위 top_n개만 그립니다.
    """
    cols = _categorical_cols(df, max_unique, var_types)
    code = f'''# [목적] 범주형 열의 빈도·비율·최빈값
for col in sub.select_dtypes(include=["object", "string", "category", "bool"]):
    counts = sub[col].value_counts(dropna=False)          # 값별 빈도 (결측 포함)
    ratio = sub[col].value_counts(normalize=True, dropna=False)  # 값별 비율
    mode = sub[col].mode(dropna=True)                     # 최빈값 (여러 개일 수 있음)
    print(col, counts.head({top_n}), ratio.head({top_n}).round(4), list(mode))'''
    if not cols:
        return AnalysisResult("기술통계 - 범주형", FAIL,
                              f"분석 범위에 범주형 열이 없습니다 (고유값 {max_unique}개 이하 기준).", code=code)
    if len(df) == 0:                                   # 필터 결과 0행: 빈 막대를 그리다 멈추지 않게 먼저 안내
        return AnalysisResult("기술통계 - 범주형", FAIL, "조건에 맞는 행이 없습니다. 행 조건을 넓혀 주세요.", code=code)
    rows, tables, figures = [], {}, {}
    for c in cols:
        counts = df[c].value_counts(dropna=False)
        ratio = df[c].value_counts(normalize=True, dropna=False)
        mode = df[c].mode(dropna=True).tolist()
        tables[f"{c} 빈도표"] = pd.DataFrame({"빈도": counts, "비율": ratio.round(4)}).head(top_n)
        rows.append({"열": c, "고유값 수": df[c].nunique(dropna=True), "결측": int(df[c].isna().sum()),
                     "최빈값": ", ".join(map(str, mode[:3])) + (" 외" if len(mode) > 3 else ""),
                     # 최빈값 빈도는 결측을 뺀 빈도로 센다 (결측이 가장 많으면 counts 첫 줄이 결측이라서)
                     "최빈값 빈도": int(df[c].value_counts(dropna=True).max()) if df[c].notna().any() else 0})
        if with_charts and len(counts):
            figures[f"{c} 빈도"] = charts.bar_counts(counts.head(top_n), f"{c} 빈도 (상위 {top_n})")
    overview = pd.DataFrame(rows).set_index("열")
    tables = {"범주형 요약": overview, **tables}
    notes = []
    multi = [r["열"] for r in rows if " 외" in r["최빈값"] or "," in r["최빈값"]]
    if multi:
        notes.append(f"최빈값이 여러 개인 열: {multi}")
    return AnalysisResult(
        "기술통계 - 범주형", SUCCESS, f"범주형 {len(cols)}개 열 요약 완료",
        metrics={"분석 열 수": len(cols)}, tables=tables, figures=figures, notes=notes, code=code,
    )
