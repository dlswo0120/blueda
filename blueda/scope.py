"""분석 범위 지정.

사용자가 고른 열과 행 조건만 남긴 데이터를 만들어서 분석에 넘깁니다.
원본 데이터는 바꾸지 않습니다.

행 조건은 두 가지로 줄 수 있습니다.
- filters: 화면의 필터 칩과 같은 구조 (코드를 몰라도 되는 방식)
- query  : pandas query 문법 직접 입력 (고급)

큰 데이터에서도 메모리를 아끼도록, 원본 전체를 복사하지 않고
조건에 맞는 행을 먼저 고른 뒤 그 부분만 꺼냅니다.
"""

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

IN, BETWEEN, NOTNA, IQR_INSIDE = "in", "between", "notna", "iqr_inside"


@dataclass
class Filter:
    """필터 칩 하나.

    op = "in"         : column 값이 values 중 하나 (범주형)
    op = "between"    : lo <= column <= hi (수치형·날짜, 한쪽만 줘도 됨)
    op = "notna"      : columns(없으면 column)에 결측이 없는 행
    op = "iqr_inside" : column이 IQR×k 경계 안에 있는 행 (이상값 후보 제외)
    """
    column: str = ""
    op: str = IN
    values: list = field(default_factory=list)
    lo: object = None
    hi: object = None
    columns: list = field(default_factory=list)
    k: float = 1.5

    def label(self):
        if self.op == IN:
            v = [str(x) for x in self.values]
            shown = ", ".join(v) if len(v) <= 2 else f"{v[0]} 외 {len(v) - 1}"
            return f"{self.column}: {shown or '없음'}"
        if self.op == BETWEEN:
            lo = "" if self.lo is None else self.lo
            hi = "" if self.hi is None else self.hi
            return f"{self.column}: {lo} ~ {hi}"
        if self.op == NOTNA:
            return "결측 제외"
        return f"{self.column}: 이상값 후보 제외"

    def mask_and_code(self, df):
        """조건에 맞는 행(True/False)과 같은 결과를 내는 코드 한 줄."""
        c = self.column
        if self.op == IN:
            return df[c].isin(self.values), f"df[{c!r}].isin({list(self.values)!r})  # {c} 값 선택"
        if self.op == BETWEEN:
            s = df[c]
            lo, hi = self.lo, self.hi
            if pd.api.types.is_datetime64_any_dtype(s) or isinstance(lo, str) or isinstance(hi, str):
                s = pd.to_datetime(s, errors="coerce")
                lo = pd.Timestamp(lo) if lo not in (None, "") else None
                hi = pd.Timestamp(hi) if hi not in (None, "") else None
            m = pd.Series(True, index=df.index)
            parts = []
            if lo is not None:
                m &= s >= lo
                parts.append(f"(df[{c!r}] >= {self.lo!r})")
            if hi is not None:
                m &= s <= hi
                parts.append(f"(df[{c!r}] <= {self.hi!r})")
            return m, " & ".join(parts) + f"  # {c} 범위" if parts else "True"
        if self.op == NOTNA:
            cols = self.columns or ([c] if c else list(df.columns))
            return df[cols].notna().all(axis=1), f"df[{cols!r}].notna().all(axis=1)  # 결측 없는 행만"
        if self.op == IQR_INSIDE:
            s = pd.to_numeric(df[c], errors="coerce")
            q1, q3 = s.quantile(0.25), s.quantile(0.75)
            lo, hi = q1 - self.k * (q3 - q1), q3 + self.k * (q3 - q1)
            return s.between(lo, hi), (f"df[{c!r}].between({lo:.4g}, {hi:.4g})  "
                                       f"# IQR×{self.k} 경계 안 (이상값 후보 제외)")
        raise ValueError(f"알 수 없는 조건: {self.op}")


@dataclass
class AnalysisScope:
    columns: list = field(default_factory=list)   # 분석할 열 (비우면 전체)
    filters: list = field(default_factory=list)   # 필터 칩 조건 (모두 만족하는 행만)
    query: str = ""                               # 고급: pandas query 문법
    row_start: int = None                         # 행 구간 시작 (0부터, 포함)
    row_end: int = None                           # 행 구간 끝 (미포함)
    dropna: bool = False                          # 선택한 열에 결측이 있는 행 제외 여부

    def describe(self):
        parts = [f"열 {len(self.columns)}개" if self.columns else "전체 열"]
        parts += [f.label() for f in self.filters]
        if self.query:
            parts.append(f"조건 [{self.query}]")
        if self.row_start is not None or self.row_end is not None:
            parts.append(f"행 {self.row_start or 0}~{self.row_end if self.row_end is not None else '끝'}")
        if self.dropna:
            parts.append("결측 행 제외")
        return " · ".join(parts)

    def row_mask(self, df):
        """행 조건만 적용한 True/False 마스크와 코드 줄 목록 (열 선택 전)."""
        mask = pd.Series(True, index=df.index)
        lines = []
        if self.row_start is not None or self.row_end is not None:
            pos = np.zeros(len(df), dtype=bool)
            pos[slice(self.row_start, self.row_end)] = True
            mask &= pos
            lines.append(f"mask &= np.isin(np.arange(len(df)), range(len(df))[{self.row_start}:{self.row_end}])  # 행 구간")
        for f in self.filters:
            m, code = f.mask_and_code(df)
            mask &= m.fillna(False).to_numpy(dtype=bool)
            lines.append(f"mask &= {code}")
        if self.query:
            matched = df.query(self.query, engine="python").index
            mask &= df.index.isin(matched)
            lines.append(f"mask &= df.index.isin(df.query({self.query!r}, engine='python').index)  # 직접 입력 조건")
        return mask, lines

    def count_rows(self, df):
        """조건에 맞는 행 수만 빠르게 셉니다 (화면의 '→ N행' 표시용)."""
        mask, _ = self.row_mask(df)
        return int(mask.sum())

    def apply(self, df):
        """범위를 적용한 새 DataFrame과, 같은 결과를 내는 코드를 돌려줍니다."""
        missing = [c for c in self.columns if c not in df.columns]
        missing += [f.column for f in self.filters if f.column and f.column not in df.columns]
        if missing:
            raise KeyError(f"데이터에 없는 열: {missing}")

        code = ["# [목적] 사용자가 지정한 분석 범위만 남기기"]
        mask, lines = self.row_mask(df)
        if lines:
            code.append("mask = pd.Series(True, index=df.index)  # 처음엔 모든 행 선택")
            code += lines
            code.append("sub = df.loc[mask]  # 조건에 맞는 행만 (원본 전체를 복사하지 않음)")
            sub = df.loc[mask.to_numpy(dtype=bool)]
        else:
            code.append("sub = df")
            sub = df
        if self.columns:
            sub = sub[self.columns]
            code.append(f"sub = sub[{self.columns!r}]  # 선택한 열만")
        if self.dropna:
            sub = sub.dropna()
            code.append("sub = sub.dropna()  # 결측이 있는 행 제외")
        sub = sub.copy()  # 고른 부분만 복사해서 원본을 보호
        # 범주형(category) 열은 조건으로 빠진 값이 '빈 그룹'으로 남지 않게 정리
        for c in sub.select_dtypes(include="category").columns:
            sub[c] = sub[c].cat.remove_unused_categories()
        return sub, "\n".join(code)
