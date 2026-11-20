"""분석 범위 지정.

사용자가 고른 열, 행 조건, 행 구간만 남긴 데이터를 만들어서 분석에 넘깁니다.
원본 데이터는 바꾸지 않습니다.
"""

from dataclasses import dataclass, field


@dataclass
class AnalysisScope:
    columns: list = field(default_factory=list)  # 분석할 열 (비우면 전체)
    query: str = ""                              # 행 조건 (pandas query 문법, 예: "나이 >= 30 and 지역 == '서울'")
    row_start: int = None                        # 행 구간 시작 (0부터, 포함)
    row_end: int = None                          # 행 구간 끝 (미포함)
    dropna: bool = False                         # 선택한 열에 결측이 있는 행 제외 여부

    def describe(self):
        parts = [f"열 {len(self.columns)}개" if self.columns else "전체 열"]
        if self.query:
            parts.append(f"조건 [{self.query}]")
        if self.row_start is not None or self.row_end is not None:
            parts.append(f"행 {self.row_start or 0}~{self.row_end if self.row_end is not None else '끝'}")
        if self.dropna:
            parts.append("결측 행 제외")
        return " · ".join(parts)

    def apply(self, df):
        """범위를 적용한 새 DataFrame과, 같은 결과를 내는 코드를 돌려줍니다."""
        missing = [c for c in self.columns if c not in df.columns]
        if missing:
            raise KeyError(f"데이터에 없는 열: {missing}")

        code = ["# [목적] 사용자가 지정한 분석 범위만 남기기", "sub = df.copy()  # 원본은 그대로 두고 복사본에서 작업"]
        sub = df.copy()
        if self.row_start is not None or self.row_end is not None:
            sub = sub.iloc[self.row_start:self.row_end]
            code.append(f"sub = sub.iloc[{self.row_start}:{self.row_end}]  # 행 구간 자르기")
        if self.query:
            sub = sub.query(self.query, engine="python")
            code.append(f"sub = sub.query({self.query!r}, engine='python')  # 조건에 맞는 행만")
        if self.columns:
            sub = sub[self.columns]
            code.append(f"sub = sub[{self.columns!r}]  # 선택한 열만")
        if self.dropna:
            sub = sub.dropna()
            code.append("sub = sub.dropna()  # 결측이 있는 행 제외")
        return sub, "\n".join(code)
