"""날짜 문자열 열 찾기와 날짜형 변환.

실습에서 하는 `df[col] = pd.to_datetime(df[col])`을 그대로 합니다.
자동으로 바꾸지 않고, 사용자가 고른 열만 바꿉니다.
날짜처럼 보여도 코드일 수 있기 때문입니다 (예: 20230103이 주문번호인 경우).
"""

import numpy as np
import pandas as pd

from .result import FAIL, SUCCESS, AnalysisResult
from .variables import DATETIME, infer_kind


def date_candidates(df):
    """글자 값으로 저장돼 있지만 날짜로 보이는 열 목록 (이미 날짜형인 열은 제외)."""
    out = []
    for c in df.select_dtypes(include=["object", "string", "category"]).columns:
        if infer_kind(df[c])[0] == DATETIME:
            out.append(c)
    return out


def _parse(values):
    """문자열 → 날짜. 먼저 빠른 방식(형식 자동 추정), 실패한 값이 있으면 그 값만 여러 형식 허용으로 다시 시도.
    반환: (날짜 Series, 사용한 방식 설명)"""
    first = pd.to_datetime(values, errors="coerce")
    bad = first.isna() & values.notna()
    if not bad.any():
        return first, "형식 자동 추정"
    retry = pd.to_datetime(values[bad], errors="coerce", format="mixed")
    first = first.copy()
    first[bad] = retry
    return first, "형식 자동 추정 + 일부 값은 여러 형식 허용(format='mixed')"


def to_datetime_column(s):
    """열 하나를 날짜형으로. category는 고유값만 변환해 큰 데이터에서도 빠르게 합니다."""
    if isinstance(s.dtype, pd.CategoricalDtype):
        cats = pd.Series(s.cat.categories.astype(str))
        parsed, how = _parse(cats)
        codes = s.cat.codes.to_numpy()
        vals = parsed.to_numpy()[np.where(codes >= 0, codes, 0)]
        out = pd.Series(vals, index=s.index, name=s.name)
        out[codes < 0] = pd.NaT
        return pd.to_datetime(out), how
    return _parse(s)


def convert_dates(df, columns):
    """고른 열을 날짜형으로 바꿉니다 (df를 직접 바꿈). 결과 표와 실행 코드를 돌려줍니다."""
    columns = [c for c in columns if c in df.columns]
    lines = ["# [목적] 날짜 문자열을 날짜형으로 변환 (기간 필터, 월별 집계에 필요)",
             "# errors='coerce': 날짜로 못 읽은 값은 NaT(날짜 결측)로 바꾸고 아래 표에 개수를 남깁니다"]
    if not columns:
        return AnalysisResult("날짜형 변환", FAIL, "변환할 열을 고르지 않았습니다.", code="\n".join(lines))
    rows = []
    for c in columns:
        before_na = int(df[c].isna().sum())
        conv, how = to_datetime_column(df[c])
        failed = int(conv.isna().sum()) - before_na
        df[c] = conv
        lines.append(f"df[{c!r}] = pd.to_datetime(df[{c!r}], errors='coerce')"
                     + ("" if how == "형식 자동 추정" else "   # 일부 값은 format='mixed'로 다시 읽음"))
        valid = conv.dropna()
        rows.append({"열": c, "변환된 값": len(conv) - int(conv.isna().sum()),
                     "날짜로 못 읽은 값": failed,
                     "가장 이른 날짜": valid.min().date() if len(valid) else "-",
                     "가장 늦은 날짜": valid.max().date() if len(valid) else "-",
                     "방식": how})
    table = pd.DataFrame(rows).set_index("열")
    n_fail = int(table["날짜로 못 읽은 값"].sum())
    notes = ["이제 이 열로 기간 필터를 걸고, 표·차트에서 연·월 단위로 묶을 수 있습니다."]
    if n_fail:
        notes.insert(0, f"날짜로 못 읽은 값 {n_fail:,}개가 결측(NaT)이 됐습니다. 원본 값을 확인하세요.")
    return AnalysisResult(
        "날짜형 변환", SUCCESS,
        f"{len(columns)}개 열을 날짜형으로 변환" + (f" (못 읽은 값 {n_fail:,}개)" if n_fail else ""),
        metrics={"변환한 열 수": len(columns), "날짜로 못 읽은 값": n_fail},
        tables={"날짜형 변환": table}, notes=notes, code="\n".join(lines),
    )
