"""분석 결과 객체.

모든 분석 기능은 AnalysisResult를 돌려줍니다.
화면(3단계)의 결과 세션 창은 이 객체를 그대로 받아서
[SUCCESS] / [FAIL] / [UNSUPPORTED] 한 줄과 차트·지표·데이터 탭으로 보여줍니다.
"""

from dataclasses import dataclass, field
from datetime import datetime

SUCCESS = "SUCCESS"            # 정상 실행
FAIL = "FAIL"                  # 실행했지만 조건이 맞지 않아 실패 (예: 숫자 열이 없음)
UNSUPPORTED = "UNSUPPORTED"    # 아직 툴에 없는 기능


@dataclass
class AnalysisResult:
    name: str                                     # 분석 이름 (예: "기술통계 - 수치형")
    status: str = SUCCESS
    message: str = ""                             # 결과 세션 창에 보여줄 한 줄 요약
    metrics: dict = field(default_factory=dict)   # 지표 탭: 핵심 숫자 (예: {"p_value": 0.03})
    tables: dict = field(default_factory=dict)    # 데이터 탭: 이름 → DataFrame
    figures: dict = field(default_factory=dict)   # 차트 탭: 이름 → matplotlib Figure
    notes: list = field(default_factory=list)     # 해석 주의사항
    code: str = ""                                # 실행에 쓴 코드 (로그용)
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))

    @property
    def ok(self):
        return self.status == SUCCESS

    def session_line(self):
        """결과 세션 창에 찍힐 한 줄."""
        return f"[{self.created_at}] [{self.status}] {self.name}: {self.message}"

    def __repr__(self):
        parts = [self.session_line()]
        for k, v in self.metrics.items():
            parts.append(f"  - {k}: {v}")
        for n in self.notes:
            parts.append(f"  ※ {n}")
        if self.tables:
            parts.append(f"  표: {', '.join(self.tables)}")
        if self.figures:
            parts.append(f"  차트: {', '.join(self.figures)}")
        return "\n".join(parts)
