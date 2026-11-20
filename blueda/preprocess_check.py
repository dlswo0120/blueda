"""A: 전처리 판단 체크리스트.

항상 같은 순서로 점검합니다.
  1) 타입  2) 결측  3) 중복  4) 이상치  5) 범주 불일치  6) 단위

각 점검은 실제로 실행한 pandas 코드를 로그에 남깁니다.
자동 판단은 '의심 신호'입니다. 최종 판단은 사람이 결과를 보고 내립니다.
"""

import re

import numpy as np
import pandas as pd

# 숫자 뒤에 단위가 붙은 값을 찾는 패턴 (예: "10kg", "1,000원", "3.5 %")
UNIT_PATTERN = re.compile(r"^\s*-?[\d,]+(\.\d+)?\s*([A-Za-z%가-힣]+)\s*$")


def _check_types(df):
    """숫자나 날짜처럼 보이는데 문자열(object)로 저장된 컬럼을 찾습니다."""
    code = '''# [목적] 컬럼별 자료형 확인 + 문자열로 저장된 숫자/날짜 컬럼 찾기
print(df.dtypes)                                       # 컬럼별 자료형
for col in df.select_dtypes(include=["object", "string"]):  # 문자열 컬럼만 검사
    s = df[col].dropna().astype(str).str.replace(",", "")
    num_ratio = pd.to_numeric(s, errors="coerce").notna().mean()             # 숫자로 바뀌는 비율
    date_ratio = pd.to_datetime(s, errors="coerce", format="mixed").notna().mean()  # 날짜로 바뀌는 비율
    print(col, round(num_ratio, 2), round(date_ratio, 2))'''
    issues = []
    for col in df.select_dtypes(include=["object", "string"]):
        s = df[col].dropna().astype(str).str.replace(",", "")
        if s.empty:
            continue
        num_ratio = pd.to_numeric(s, errors="coerce").notna().mean()
        date_ratio = pd.to_datetime(s, errors="coerce", format="mixed").notna().mean()
        if num_ratio >= 0.9:
            issues.append(f"{col}: 문자열이지만 값의 {num_ratio:.0%}가 숫자로 변환됩니다 → 숫자형 변환 검토")
        elif date_ratio >= 0.9:
            issues.append(f"{col}: 문자열이지만 값의 {date_ratio:.0%}가 날짜로 변환됩니다 → 날짜형 변환 검토")
    result = df.dtypes.to_string()
    return "1. 타입", code, result, issues


def _check_missing(df, warn_ratio):
    code = '''# [목적] 컬럼별 결측치 개수와 비율 확인
missing = df.isnull().sum()               # 컬럼별 결측치 개수
missing_ratio = missing / len(df)         # 전체 행 대비 결측 비율
print(missing_ratio[missing_ratio > 0].sort_values(ascending=False))  # 결측 있는 컬럼만 큰 순서로'''
    ratio = df.isnull().mean()
    ratio = ratio[ratio > warn_ratio].sort_values(ascending=False)
    issues = [f"{c}: 결측 {r:.1%}" for c, r in ratio.items()]
    result = ratio.to_string() if len(ratio) else "결측치 없음"
    return "2. 결측", code, result, issues


def _check_duplicates(df):
    code = '''# [목적] 완전히 같은 행(중복 행) 개수 확인
dup_count = df.duplicated().sum()         # duplicated(): 앞에 같은 행이 있으면 True
print(dup_count)'''
    n = int(df.duplicated().sum())
    issues = [f"중복 행 {n}개 → 제거 여부 검토"] if n else []
    return "3. 중복", code, f"중복 행: {n}개", issues


def _check_outliers(df, k):
    code = f'''# [목적] 숫자 컬럼의 이상치 후보를 IQR 기준으로 찾기
num = df.select_dtypes(include="number")
q1, q3 = num.quantile(0.25), num.quantile(0.75)        # 1사분위수, 3사분위수
iqr = q3 - q1                                          # IQR = Q3 - Q1
lower, upper = q1 - {k} * iqr, q3 + {k} * iqr          # 이 범위를 벗어나면 이상치 후보
outlier_count = ((num < lower) | (num > upper)).sum()  # 컬럼별 이상치 후보 개수
print(outlier_count[outlier_count > 0])'''
    num = df.select_dtypes(include="number")
    if num.empty:
        return "4. 이상치", code, "숫자 컬럼 없음", []
    q1, q3 = num.quantile(0.25), num.quantile(0.75)
    iqr = q3 - q1
    lower, upper = q1 - k * iqr, q3 + k * iqr
    counts = ((num < lower) | (num > upper)).sum()
    counts = counts[counts > 0]
    issues = [f"{c}: 이상치 후보 {n}개 (IQR×{k} 기준) → 실제 오류인지 극단값인지 확인 필요" for c, n in counts.items()]
    result = counts.to_string() if len(counts) else "이상치 후보 없음"
    return "4. 이상치", code, result, issues


def _check_categories(df):
    code = '''# [목적] 같은 범주인데 공백·대소문자만 다른 값 찾기 (예: "Seoul", "seoul ", "SEOUL")
for col in df.select_dtypes(include=["object", "string"]):
    raw = df[col].dropna().astype(str)
    normalized = raw.str.strip().str.lower()           # 앞뒤 공백 제거 + 소문자 통일
    if normalized.nunique() < raw.nunique():           # 정리 후 종류가 줄면 표기 불일치가 있다는 뜻
        print(col, raw.nunique(), "→", normalized.nunique())'''
    issues, lines = [], []
    for col in df.select_dtypes(include=["object", "string"]):
        raw = df[col].dropna().astype(str)
        normalized = raw.str.strip().str.lower()
        if normalized.nunique() < raw.nunique():
            groups = raw.groupby(normalized).unique()
            examples = [list(v) for v in groups if len(v) > 1][:3]
            issues.append(f"{col}: 표기 불일치 {raw.nunique()}종 → 정리 후 {normalized.nunique()}종, 예: {examples}")
            lines.append(f"{col}: {raw.nunique()} → {normalized.nunique()}")
    return "5. 범주 불일치", code, "\n".join(lines) or "불일치 없음", issues


def _check_units(df):
    code = r'''# [목적] 숫자 뒤에 단위가 붙어 문자열이 된 값 찾기 (예: "10kg", "1,000원")
import re
pattern = re.compile(r"^\s*-?[\d,]+(\.\d+)?\s*([A-Za-z%가-힣]+)\s*$")
for col in df.select_dtypes(include=["object", "string"]):
    units = df[col].dropna().astype(str).str.extract(pattern)[1].dropna()  # 단위 부분만 뽑기
    if len(units):
        print(col, units.value_counts().to_dict())      # 단위 종류별 개수'''
    issues, lines = [], []
    for col in df.select_dtypes(include=["object", "string"]):
        units = df[col].dropna().astype(str).str.extract(UNIT_PATTERN)[1].dropna()
        if len(units):
            counts = units.value_counts().to_dict()
            msg = "단위가 여러 종류 → 단위 통일 필요" if len(counts) > 1 else "단위 제거 후 숫자형 변환 검토"
            issues.append(f"{col}: {counts} → {msg}")
            lines.append(f"{col}: {counts}")
    return "6. 단위", code, "\n".join(lines) or "단위 문제 없음", issues


def check_preprocessing(df, logger=None, outlier_iqr_k=1.5, missing_warn_ratio=0.0):
    """6개 항목을 순서대로 점검하고, 전처리가 필요한지 판단합니다.

    반환값: {"needs_preprocessing": bool, "items": {항목명: [이슈, ...]}}
    """
    checks = [
        _check_types(df),
        _check_missing(df, missing_warn_ratio),
        _check_duplicates(df),
        _check_outliers(df, outlier_iqr_k),
        _check_categories(df),
        _check_units(df),
    ]
    report = {"shape": df.shape, "items": {}}
    for name, code, result, issues in checks:
        report["items"][name] = issues
        if logger is not None:
            interp = "문제 없음" if not issues else " / ".join(issues)
            logger.log(f"[전처리 점검] {name}", code, result, interp)
    report["needs_preprocessing"] = any(report["items"].values())
    return report


def format_report(report):
    """점검 결과를 사람이 읽기 좋은 요약 문장으로 바꿉니다."""
    verdict = "전처리 필요" if report["needs_preprocessing"] else "전처리 없이 분석 가능"
    lines = [f"[BLUEDA 전처리 판단] {report['shape'][0]}행 × {report['shape'][1]}열 → {verdict}"]
    for name, issues in report["items"].items():
        mark = "✔" if not issues else "⚠"
        lines.append(f" {mark} {name}")
        lines += [f"     - {i}" for i in issues]
    lines.append("※ 자동 판단은 의심 신호입니다. 처리 방법은 결과를 보고 직접 결정해 주세요.")
    return "\n".join(lines)


def check_result(df, outlier_iqr_k=1.5, missing_warn_ratio=0.0):
    """화면·결과 세션용: 전처리 점검 결과를 AnalysisResult로 돌려줍니다."""
    from .result import SUCCESS, AnalysisResult
    report = check_preprocessing(df, None, outlier_iqr_k, missing_warn_ratio)
    rows = []
    for name, issues in report["items"].items():
        rows.append({"항목": name, "상태": "확인 필요" if issues else "문제 없음",
                     "내용": " / ".join(issues) if issues else "-"})
    table = pd.DataFrame(rows).set_index("항목")
    n_issue = sum(1 for v in report["items"].values() if v)
    codes = [c for _, c, _, _ in (
        _check_types(df), _check_missing(df, missing_warn_ratio), _check_duplicates(df),
        _check_outliers(df, outlier_iqr_k), _check_categories(df), _check_units(df))]
    return AnalysisResult(
        "전처리 점검", SUCCESS,
        f"6개 항목 중 {n_issue}개 확인 필요" + (" → 전처리 필요" if n_issue else " → 바로 분석 가능"),
        metrics={"행 수": f"{len(df):,}", "열 수": df.shape[1], "확인 필요 항목": n_issue},
        tables={"전처리 점검": table},
        notes=["자동 판단은 의심 신호입니다. 처리 방법은 결과를 보고 직접 정하세요."],
        code="\n\n".join(codes),
    )
