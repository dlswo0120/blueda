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


class ChartImage:
    """차트를 PNG 이미지로 보관합니다.

    matplotlib 그림 객체를 결과마다 들고 있으면 분석 한 번에 약 15MB씩 메모리가 늘어
    (200회 분석에 3GB 이상) 오래 쓰면 느려지거나 꺼질 수 있습니다.
    그래서 결과에 담기는 순간 PNG(차트 하나에 약 50~150KB)로 바꾸고 그림 객체는 닫습니다.
    savefig()를 지원해 내보내기 코드는 그대로 씁니다.
    """
    DPI = 120

    def __init__(self, fig):
        """그림을 DPI 해상도의 PNG로 바꾸고, 크기(픽셀)를 기억한 뒤 그림 객체를 닫습니다."""
        import io
        import matplotlib.pyplot as plt
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=self.DPI)
        self.png = buf.getvalue()
        w, h = fig.get_size_inches()
        self.size = (int(w * self.DPI), int(h * self.DPI))
        plt.close(fig)

    def savefig(self, f, format="png", **_):
        """matplotlib Figure.savefig와 같은 모양 (PNG만, 해상도는 만들 때 정해짐)."""
        if isinstance(f, (str, bytes)) or hasattr(f, "__fspath__"):
            with open(f, "wb") as out:
                out.write(self.png)
        else:
            f.write(self.png)

    def __len__(self):
        """PNG 크기(바이트)."""
        return len(self.png)


def to_images(figures):
    """결과의 그림 객체들을 PNG로 바꿉니다 (이미 바뀐 것은 그대로)."""
    return {name: (f if isinstance(f, ChartImage) else ChartImage(f)) for name, f in figures.items()}


class UserFacingError(ValueError):
    """사용자에게 그대로 보여줄 안내 문장을 담은 오류 (프로그램 용어 없이 표시)."""


def constant_message(column):
    """값이 모두 같은 열로는 검정·상관·회귀를 계산할 수 없을 때의 안내."""
    return (f"{column}의 값이 모두 같습니다(분산 0). 이 경우 검정 통계량이 정의되지 않아 계산하지 않습니다. "
            "조건(필터)이나 열 선택을 확인하세요.")


@dataclass
class AnalysisResult:
    """분석 결과 하나.

    name 분석 이름, status SUCCESS/FAIL/UNSUPPORTED, message 결과 세션 한 줄 요약,
    metrics 핵심 숫자(지표), tables 결과 표들, figures 차트들(세션에 쌓일 때 PNG로), notes 안내 문구, code 실행 코드
    """
    name: str                                     # 분석 이름 (예: "기술통계 - 수치형")
    status: str = SUCCESS
    message: str = ""                             # 결과 세션 창에 보여줄 한 줄 요약
    metrics: dict = field(default_factory=dict)   # 지표 탭: 핵심 숫자 (예: {"p_value": 0.03})
    tables: dict = field(default_factory=dict)    # 데이터 탭: 이름 → DataFrame
    figures: dict = field(default_factory=dict)   # 차트 탭: 이름 → 그림 (세션에 쌓일 때 ChartImage(PNG)로 바뀜)
    notes: list = field(default_factory=list)     # 해석 주의사항
    code: str = ""                                # 실행에 쓴 코드 (로그용)
    created_at: str = field(default_factory=lambda: datetime.now().strftime("%H:%M:%S"))

    @property
    def ok(self):
        """SUCCESS면 True."""
        return self.status == SUCCESS

    def session_line(self):
        """결과 세션 창에 찍힐 한 줄."""
        return f"[{self.created_at}] [{self.status}] {self.name}: {self.message}"

    def __repr__(self):
        """파이썬에서 출력하면 요약(이름·상태·문장·표·차트 이름)을 보여줍니다."""
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
