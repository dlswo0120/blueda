"""변수의 종류와 분석 단위.

- 변수의 종류: 수치형은 크기를 잰 값, 범주형은 종류를 나타내는 값.
  자료형만 보면 '1=남, 2=여'처럼 숫자로 적힌 범주를 수치형으로 착각하므로
  고유값 개수와 값 모양을 함께 보고 판정합니다. 사용자가 직접 바꿀 수 있습니다.
- 분석 단위: 한 행이 무엇을 뜻하는지(예: 고객 1명, 주문 1건)를 먼저 정하고,
  기준 열에 중복이 있는지 확인합니다.
"""

import pandas as pd

from .result import FAIL, SUCCESS, AnalysisResult

NUMERIC, CATEGORICAL, DATETIME, ID, TEXT = "수치형", "범주형", "날짜", "ID 후보", "텍스트"
KINDS = (NUMERIC, CATEGORICAL, DATETIME, ID, TEXT)


def infer_kind(s, max_categories=10, text_unique_ratio=0.5):
    """열 하나의 종류와 판정 이유를 돌려줍니다."""
    n = s.notna().sum()
    nunique = s.nunique(dropna=True)
    if pd.api.types.is_bool_dtype(s):
        return CATEGORICAL, "참/거짓 값"
    if pd.api.types.is_datetime64_any_dtype(s):
        return DATETIME, "날짜 자료형"
    if pd.api.types.is_numeric_dtype(s):
        is_int = pd.api.types.is_integer_dtype(s) or (s.dropna() % 1 == 0).all()
        if is_int and n > 0 and nunique == n and nunique > max_categories:
            return ID, "정수이고 모든 값이 다름 → 번호·ID일 수 있음"
        if is_int and nunique <= max_categories and n > max_categories * 2:
            return CATEGORICAL, f"숫자지만 고유값 {nunique}개뿐 → 코드로 적힌 범주일 수 있음"
        return NUMERIC, "숫자 자료형"
    # 문자열 계열
    sample = s.dropna().astype(str)
    if len(sample) and pd.to_datetime(sample.head(200), errors="coerce", format="mixed").notna().mean() > 0.9:
        return DATETIME, "문자열이지만 날짜 형식"
    if n > 0 and nunique == n and nunique > max_categories:
        return ID, "모든 값이 다름 → 이름·코드 등 ID일 수 있음"
    if n > 0 and nunique / n > text_unique_ratio and nunique > 50:
        return TEXT, "고유값 비율이 높음 → 자유 입력 텍스트일 수 있음"
    return CATEGORICAL, "문자열 자료형"


def variable_types(df, overrides=None):
    overrides = overrides or {}
    code = '''# [목적] 열마다 변수 종류 판정 (수치형=크기를 잰 값, 범주형=종류를 나타내는 값)
for col in sub.columns:
    s = sub[col]
    print(col, s.dtype,                     # 저장된 자료형
          s.nunique(dropna=True),           # 고유값 개수: 적으면 범주일 가능성
          s.isna().sum())                   # 결측 개수'''
    rows = []
    for c in df.columns:
        kind, reason = infer_kind(df[c])
        if c in overrides:
            kind, reason = overrides[c], f"사용자 지정 (자동 판정: {kind})"
        rows.append({"열": c, "자료형": str(df[c].dtype), "판정": kind,
                     "고유값 수": df[c].nunique(dropna=True), "결측": int(df[c].isna().sum()), "이유": reason})
    table = pd.DataFrame(rows).set_index("열")
    counts = table["판정"].value_counts().to_dict()
    notes = []
    coded = table.index[table["이유"].str.contains("코드로 적힌 범주")].tolist()
    if coded:
        notes.append(f"숫자로 적힌 범주로 보이는 열: {coded}. 평균을 내면 의미가 없을 수 있습니다. "
                     "수치형이 맞다면 set_variable_type()으로 바꿔주세요.")
    return AnalysisResult("변수 종류 판정", SUCCESS, ", ".join(f"{k} {v}개" for k, v in counts.items()),
                          metrics=counts, tables={"변수 종류": table}, notes=notes, code=code)


def check_analysis_unit(df, key_columns, unit_name=""):
    """기준 열 조합이 행마다 유일한지 확인합니다. 유일하면 '한 행 = 분석 단위 1개'가 성립합니다."""
    unit = unit_name or " + ".join(key_columns)
    code = f'''# [목적] 분석 단위 확인: 한 행 = {unit} 1개가 맞는지
dup_mask = sub.duplicated(subset={key_columns!r}, keep=False)  # 기준 열 값이 겹치는 행 모두 True
print(dup_mask.sum())                                           # 단위가 겹치는 행 수
print(sub.groupby({key_columns!r}).size().max())                # 한 단위가 최대 몇 행인지'''
    missing = [c for c in key_columns if c not in df.columns]
    if missing:
        return AnalysisResult("분석 단위 확인", FAIL, f"데이터에 없는 열: {missing}", code=code)
    dup_mask = df.duplicated(subset=key_columns, keep=False)
    sizes = df.groupby(key_columns, dropna=False).size()
    metrics = {"분석 단위": unit, "행 수": len(df), "단위 개수": int(len(sizes)),
               "겹치는 행": int(dup_mask.sum()), "한 단위 최대 행 수": int(sizes.max()) if len(sizes) else 0}
    if not dup_mask.any():
        return AnalysisResult("분석 단위 확인", SUCCESS, f"한 행 = {unit} 1개가 맞습니다.", metrics=metrics, code=code)
    examples = df[dup_mask].sort_values(key_columns).head(20)
    return AnalysisResult(
        "분석 단위 확인", SUCCESS,
        f"같은 {unit}에 여러 행이 있습니다 ({int(len(sizes))}개 단위, {len(df)}행).",
        metrics=metrics, tables={"겹치는 행 예시": examples},
        notes=[f"{unit} 단위로 분석하려면 합계·평균 등으로 묶어야 합니다 (groupby). "
               "행 단위(예: 주문 1건)가 맞다면 기준 열을 바꿔주세요."],
        code=code,
    )
