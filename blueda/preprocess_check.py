"""A: 전처리 판단 체크리스트.

항상 같은 순서로 점검합니다.
  1) 타입  2) 결측  3) 중복  4) 이상치  5) 범주 불일치  6) 단위

각 점검은 실제로 실행한 pandas 코드를 로그에 남깁니다.
자동 판단은 '의심 신호'입니다. 최종 판단은 사람이 결과를 보고 내립니다.
"""

import re

import pandas as pd

# 숫자 뒤에 단위가 붙은 값을 찾는 패턴 (예: "10kg", "1,000원", "3.5 %")
UNIT_PATTERN = re.compile(r"^\s*-?[\d,]+(\.\d+)?\s*([A-Za-z%가-힣]+)\s*$")

# 글자 값이 들어 있는 자료형. 메모리 최적화로 바뀐 category도 포함해야 점검이 빠지지 않습니다.
TEXT_DTYPES = ["object", "string", "category"]

# 판단 기준값(이산값 기준, 표본 크기, 단위 비율, 숫자·날짜 비율)은 limits.py에 있습니다.
from .limits import DISCRETE_MAX_UNIQUE, NUMERIC_TEXT_RATIO, TYPE_SAMPLE, UNIT_MIN_RATIO  # noqa: E402

# 값 종류가 이 개수 이하인 숫자 열은 IQR 이상치 판단에서 뺍니다 (0/1, 할인율 단계, 수량 등).
# 값이 몇 단계뿐이면 사분위수가 같은 값에 몰려 정상 값까지 이상치로 잡히기 때문입니다.

# 타입 점검에서 값 종류가 이보다 많으면 표본으로 비율을 계산합니다.

# 값(고유값 기준) 중 이 비율 이상이 "숫자+단위" 모양일 때만 단위 문제로 봅니다.


def _text_values(s):
    """글자 열의 값(결측 제외)을 문자열로 돌려줍니다. category는 고유값만 써서 큰 데이터에서도 빠릅니다."""
    if isinstance(s.dtype, pd.CategoricalDtype):
        used = s.cat.remove_unused_categories().cat.categories
        return pd.Series(used.astype(str), dtype=object)
    return s.dropna().astype(str)


# 열 이름에 들어 있으면 코드로 보는 단서. 짧은 영어 단어(id, tel)는 단어 단위로만 봅니다 (paid, hotel 오판 방지).
CODE_NAME_PARTS = ("우편", "zip", "postal", "code", "코드", "번호", "phone", "전화")
CODE_NAME_WORDS = ("id", "tel", "no")


def _looks_like_code(col, s):
    """숫자처럼 보여도 코드인 열인지: 이름에 코드 단서가 있거나, 앞자리가 0인 값이 있으면 코드."""
    name = str(col).lower()
    words = re.split(r"[^0-9a-z가-힣]+", name)
    if any(h in name for h in CODE_NAME_PARTS) or any(w in CODE_NAME_WORDS for w in words):
        return True
    digits = s[s.str.fullmatch(r"\d+")]
    return bool(len(digits) and ((digits.str.len() > 1) & digits.str.startswith("0")).any())


def _digit_length_note(full):
    """숫자로만 된 코드의 자릿수가 섞여 있으면 알려줍니다 (예: 우편번호 4자리·5자리 → 앞자리 0 손실 의심).
    full: 열 전체 (행 단위로 셉니다)"""
    counts = full.astype(str).value_counts() if not isinstance(full.dtype, pd.CategoricalDtype) \
        else full.value_counts()
    counts.index = counts.index.astype(str)
    counts = counts[counts.index.str.fullmatch(r"\d+")]
    lens = counts.groupby(counts.index.str.len()).sum()
    if len(lens) > 1:
        detail = ", ".join(f"{k}자리 {v:,}개" for k, v in lens.sort_index().items())
        return f". 자릿수가 섞여 있습니다({detail}) → 앞자리 0이 사라졌는지 확인"
    return ""


def _row_weights(col):
    """_text_values와 같은 순서로, 각 값이 몇 행에 나오는지. 일반 문자열 열은 None(행 그대로)."""
    if isinstance(col.dtype, pd.CategoricalDtype):
        used = col.cat.remove_unused_categories()
        return used.value_counts(sort=False).reindex(used.cat.categories).to_numpy()
    return None


def _weighted_mean(flags, weights):
    """참/거짓 목록의 비율. weights가 있으면 행 수로 가중 (category 열을 행 기준으로 세기 위해)."""
    if weights is None:
        return float(flags.mean())
    return float((flags.to_numpy() * weights).sum() / weights.sum())


def _check_types(df):
    """숫자나 날짜처럼 보이는데 문자열(object·category)로 저장된 컬럼을 찾습니다."""
    code = '''# [목적] 컬럼별 자료형 확인 + 문자열로 저장된 숫자/날짜 컬럼 찾기
print(df.dtypes)                                       # 컬럼별 자료형
for col in df.select_dtypes(include=["object", "string", "category"]):  # 글자 값 컬럼만 검사
    s = df[col].dropna().astype(str).str.replace(",", "")
    num_ratio = pd.to_numeric(s, errors="coerce").notna().mean()             # 숫자로 바뀌는 비율
    date_ratio = pd.to_datetime(s, errors="coerce", format="mixed").notna().mean()  # 날짜로 바뀌는 비율
    print(col, round(num_ratio, 2), round(date_ratio, 2))'''
    issues = []
    for col in df.select_dtypes(include=TEXT_DTYPES):
        s = _text_values(df[col]).str.replace(",", "")
        if s.empty:
            continue
        w = _row_weights(df[col])                       # category는 고유값마다 행 수로 가중 → 행 기준 비율
        if len(s) > TYPE_SAMPLE:
            # 값 종류가 아주 많으면(메모·주소 등) 모든 값을 날짜로 읽어보는 데 몇 초가 걸립니다.
            # 비율 판단에는 무작위 표본으로 충분하므로 행 기준 표본 2만 개로 계산합니다.
            s = df[col].dropna().sample(TYPE_SAMPLE, random_state=0).astype(str).str.replace(",", "")
            w = None
        num_ratio = _weighted_mean(pd.to_numeric(s, errors="coerce").notna(), w)
        date_ratio = _weighted_mean(pd.to_datetime(s, errors="coerce", format="mixed").notna(), w)
        if num_ratio >= NUMERIC_TEXT_RATIO and _looks_like_code(col, s):
            # 우편번호·ID·전화번호 같은 코드는 숫자로 바꾸면 앞자리 0이 사라지고, 글자가 섞인 값은 결측이 됩니다.
            issues.append(f"{col}: 값의 {num_ratio:.0%}가 숫자지만 코드(우편번호·ID 등)로 보입니다 "
                          "→ 숫자로 바꾸지 말고 문자열로 두세요" + _digit_length_note(df[col].dropna()))
        elif num_ratio >= NUMERIC_TEXT_RATIO:
            issues.append(f"{col}: 문자열이지만 값의 {num_ratio:.0%}가 숫자로 변환됩니다 → 숫자형 변환 검토")
        elif date_ratio >= NUMERIC_TEXT_RATIO:
            issues.append(f"{col}: 문자열이지만 값의 {date_ratio:.0%}가 날짜로 변환됩니다 → 날짜형 변환 검토")
    result = df.dtypes.to_string()
    return "1. 타입", code, result, issues


def _check_missing(df, warn_ratio):
    """2. 결측: 열마다 결측 비율. warn_ratio(기본 5%)를 넘으면 이슈."""
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
    """3. 중복: 모든 열이 같은 행의 수."""
    code = '''# [목적] 완전히 같은 행(중복 행) 개수 확인
dup_count = df.duplicated().sum()         # duplicated(): 앞에 같은 행이 있으면 True
print(dup_count)'''
    n = int(df.duplicated().sum())
    issues = [f"중복 행 {n}개 → 제거 여부 검토"] if n else []
    return "3. 중복", code, f"중복 행: {n}개", issues


def _outlier_columns(df):
    """IQR 판단이 의미 있는 숫자 열과, 뺀 열(이유 포함)을 나눕니다."""
    from .variables import is_strong_id
    use, skipped = [], {}
    for c in df.select_dtypes(include="number").columns:
        s = df[c]
        if pd.api.types.is_bool_dtype(s):
            continue
        nunique = s.nunique(dropna=True)
        if nunique <= 2:
            skipped[c] = "값 2종 이하(0/1 등)"
        elif nunique <= DISCRETE_MAX_UNIQUE:
            skipped[c] = f"값 {nunique}종뿐인 이산값"
        elif is_strong_id(s, c):
            skipped[c] = "ID 후보"
        else:
            use.append(c)
    return use, skipped


def _check_outliers(df, k):
    """4. 이상치: IQR×k 경계 밖 값의 수 (이산값·0/1·ID 열 제외). 이상치는 '확인 권장'이며 '전처리 필요'로 보지 않습니다."""
    code = f'''# [목적] 숫자 컬럼의 이상치 후보를 IQR 기준으로 찾기
# 값 종류가 {DISCRETE_MAX_UNIQUE}개 이하인 열(0/1, 단계형 값)과 ID 후보 열은 제외합니다.
num = df.select_dtypes(include="number")
num = num.loc[:, num.nunique() > {DISCRETE_MAX_UNIQUE}]          # 이산값·이분형 열 제외
q1, q3 = num.quantile(0.25), num.quantile(0.75)        # 1사분위수, 3사분위수
iqr = q3 - q1                                          # IQR = Q3 - Q1
lower, upper = q1 - {k} * iqr, q3 + {k} * iqr          # 이 범위를 벗어나면 이상치 후보
outlier_count = ((num < lower) | (num > upper)).sum()  # 컬럼별 이상치 후보 개수
print(outlier_count[outlier_count > 0])'''
    cols, skipped = _outlier_columns(df)
    skip_note = ""
    if skipped:
        skip_note = "제외: " + ", ".join(f"{c}({why})" for c, why in skipped.items())
    if not cols:
        return "4. 이상치", code, skip_note or "숫자 컬럼 없음", []
    num = df[cols]
    q1, q3 = num.quantile(0.25), num.quantile(0.75)
    iqr = q3 - q1
    lower, upper = q1 - k * iqr, q3 + k * iqr
    counts = ((num < lower) | (num > upper)).sum()
    counts = counts[counts > 0]
    issues = [f"{c}: 이상치 후보 {n:,}개 (IQR×{k} 기준) → 오류인지 실제 극단값인지 확인" for c, n in counts.items()]
    result = counts.to_string() if len(counts) else "이상치 후보 없음"
    if skip_note:
        result += "\n" + skip_note
    return "4. 이상치", code, result, issues


def _check_categories(df):
    """5. 범주 불일치: 앞뒤 공백·대소문자만 다른 값(예: 'Seoul'과 'seoul ')이 있는 열."""
    code = '''# [목적] 같은 범주인데 공백·대소문자만 다른 값 찾기 (예: "Seoul", "seoul ", "SEOUL")
for col in df.select_dtypes(include=["object", "string", "category"]):
    raw = df[col].dropna().astype(str)
    normalized = raw.str.strip().str.lower()           # 앞뒤 공백 제거 + 소문자 통일
    if normalized.nunique() < raw.nunique():           # 정리 후 종류가 줄면 표기 불일치가 있다는 뜻
        print(col, raw.nunique(), "→", normalized.nunique())'''
    issues, lines = [], []
    for col in df.select_dtypes(include=TEXT_DTYPES):
        raw = _text_values(df[col])
        normalized = raw.str.strip().str.lower()
        if normalized.nunique() < raw.nunique():
            groups = raw.groupby(normalized).unique()
            examples = [list(v) for v in groups if len(v) > 1][:3]
            issues.append(f"{col}: 표기 불일치 {raw.nunique()}종 → 정리 후 {normalized.nunique()}종, 예: {examples}")
            lines.append(f"{col}: {raw.nunique()} → {normalized.nunique()}")
    return "5. 범주 불일치", code, "\n".join(lines) or "불일치 없음", issues


def _check_units(df):
    """6. 단위: '10kg', '1,000원'처럼 숫자에 단위가 붙은 값이 대부분인 열 (숫자로 계산하려면 단위를 떼야 함)."""
    code = r'''# [목적] 숫자 뒤에 단위가 붙어 문자열이 된 값 찾기 (예: "10kg", "1,000원")
import re
pattern = re.compile(r"^\s*-?[\d,]+(\.\d+)?\s*([A-Za-z%가-힣]+)\s*$")
for col in df.select_dtypes(include=["object", "string", "category"]):
    values = df[col].dropna().astype(str)
    units = values.str.extract(pattern)[1].dropna()     # 단위 부분만 뽑기
    if len(units) / len(values) >= 0.5:                 # 값 대부분이 "숫자+단위"일 때만 (상품명 속 숫자 제외)
        print(col, units.value_counts().to_dict())      # 단위 종류별 개수'''
    issues, lines = [], []
    for col in df.select_dtypes(include=TEXT_DTYPES):
        values = _text_values(df[col])
        units = values.str.extract(UNIT_PATTERN)[1].dropna()
        # 값 대부분이 "숫자+단위"일 때만 단위 문제로 봅니다.
        # 상품명 "4009 Highlighters"처럼 일부 값만 우연히 모양이 같은 경우는 제외합니다.
        if len(values) and len(units) / len(values) < UNIT_MIN_RATIO:
            continue
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
    report = {"shape": df.shape, "items": {}, "codes": {}}
    for name, code, result, issues in checks:
        report["items"][name] = issues
        report["codes"][name] = code
        if logger is not None:
            interp = "문제 없음" if not issues else " / ".join(issues)
            logger.log(f"[전처리 점검] {name}", code, result, interp)
    # 이상치 후보는 오류가 아니라 '확인 권장' 신호입니다. 실제 극단값일 수 있으므로
    # 이상치만 있을 때는 "전처리 필요"로 결론 내리지 않습니다.
    report["needs_preprocessing"] = any(v for k, v in report["items"].items() if k not in REVIEW_ONLY)
    report["needs_review"] = any(report["items"][k] for k in REVIEW_ONLY if k in report["items"])
    return report


REVIEW_ONLY = ("4. 이상치",)


def _verdict(report):
    """최종 판단 문구: 전처리 필요 / 바로 분석 가능(이상치 확인 권장) / 전처리 없이 분석 가능."""
    if report["needs_preprocessing"]:
        return "전처리 필요"
    if report["needs_review"]:
        return "바로 분석 가능 (이상치 후보는 확인 권장)"
    return "전처리 없이 분석 가능"


def format_report(report):
    """점검 결과를 사람이 읽기 좋은 요약 문장으로 바꿉니다."""
    verdict = _verdict(report)
    lines = [f"[BLUEDA 전처리 판단] {report['shape'][0]}행 × {report['shape'][1]}열 → {verdict}"]
    for name, issues in report["items"].items():
        mark = "✔" if not issues else ("△" if name in REVIEW_ONLY else "⚠")
        lines.append(f" {mark} {name}")
        lines += [f"     - {i}" for i in issues]
    lines.append("※ 자동 판단은 의심 신호입니다. 처리 방법은 결과를 보고 직접 결정해 주세요.")
    return "\n".join(lines)


def check_result(df, outlier_iqr_k=1.5, missing_warn_ratio=0.0):
    """화면·결과 세션용: 전처리 점검 결과를 AnalysisResult로 돌려줍니다."""
    from .result import SUCCESS, AnalysisResult
    report = check_preprocessing(df, None, outlier_iqr_k, missing_warn_ratio)   # 점검은 한 번만 실행
    rows = []
    for name, issues in report["items"].items():
        state = "문제 없음" if not issues else ("확인 권장" if name in REVIEW_ONLY else "확인 필요")
        rows.append({"항목": name, "상태": state, "내용": "\n".join(issues) if issues else "-"})
    table = pd.DataFrame(rows).set_index("항목")
    n_need = sum(1 for k, v in report["items"].items() if v and k not in REVIEW_ONLY)
    n_review = sum(1 for k, v in report["items"].items() if v and k in REVIEW_ONLY)
    _, skipped = _outlier_columns(df)
    notes = ["자동 판단은 의심 신호입니다. 처리 방법은 결과를 보고 직접 정하세요.",
             "이상치 후보는 오류가 아닐 수 있습니다(실제 큰 주문, 높은 회전 속도 등). 원인 확인 없이 지우지 마세요."]
    if skipped:
        notes.append(f"이상치 점검에서 뺀 열 (값 종류가 {DISCRETE_MAX_UNIQUE}개 이하이거나 ID 후보): "
                     + ", ".join(f"{c}({why})" for c, why in skipped.items()) + " → 빈도표로 확인하세요.")
    return AnalysisResult(
        "전처리 점검", SUCCESS,
        f"6개 항목 중 확인 필요 {n_need}개, 확인 권장 {n_review}개 → {_verdict(report)}",
        metrics={"행 수": f"{len(df):,}", "열 수": df.shape[1], "확인 필요 항목": n_need, "확인 권장 항목": n_review},
        tables={"전처리 점검": table},
        notes=notes,
        code="\n\n".join(report["codes"].values()),
    )
