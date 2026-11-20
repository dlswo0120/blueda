"""차트 공통 설정.

- 화면이 없는 환경에서도 그림을 만들 수 있게 Agg 백엔드를 씁니다.
- 한글 열 이름이 깨지지 않도록 설치된 한글 폰트를 찾아 적용합니다.
  (윈도우: 맑은 고딕 / 맥: AppleGothic / 리눅스: 나눔고딕·Noto CJK)
"""

import matplotlib

matplotlib.use("Agg")  # 창을 띄우지 않고 그림만 만드는 모드

import matplotlib.pyplot as plt  # noqa: E402
from matplotlib import font_manager  # noqa: E402

KOREAN_FONTS = ("Malgun Gothic", "AppleGothic", "NanumGothic", "Noto Sans CJK KR", "Noto Sans KR")

# 기본 색: 부드러운 파랑 계열 (BLUEDA)
PRIMARY = "#4A78B5"
EDGE = "#2F4F7F"

_font_ready = False


def setup_korean_font():
    """설치된 폰트 중 첫 번째 한글 폰트를 기본 폰트로 지정합니다. 찾은 폰트 이름을 반환."""
    global _font_ready
    installed = {f.name for f in font_manager.fontManager.ttflist}
    chosen = next((name for name in KOREAN_FONTS if name in installed), None)
    if chosen:
        plt.rcParams["font.family"] = chosen
    plt.rcParams["axes.unicode_minus"] = False  # 한글 폰트에서 마이너스(-) 기호 깨짐 방지
    _font_ready = True
    return chosen


def new_figure(width=6, height=4):
    if not _font_ready:
        setup_korean_font()
    fig, ax = plt.subplots(figsize=(width, height), dpi=110)
    ax.spines[["top", "right"]].set_visible(False)  # 위·오른쪽 테두리 제거로 깔끔하게
    return fig, ax


def histogram(series, bins="auto", normal_curve=True):
    """히스토그램. normal_curve=True면 같은 평균·표준편차의 정규분포 곡선을 겹쳐 그립니다."""
    import numpy as np
    from scipy import stats

    x = series.dropna()
    fig, ax = new_figure()
    counts, edges, _ = ax.hist(x, bins=bins, color=PRIMARY, edgecolor="white", label="관측값")
    if normal_curve and len(x) >= 3 and x.std(ddof=1) > 0:
        grid = np.linspace(edges[0], edges[-1], 200)
        width = edges[1] - edges[0]
        # 정규분포 밀도 × 표본 수 × 구간 폭 = 히스토그램과 같은 '빈도' 눈금으로 맞춤
        ax.plot(grid, stats.norm.pdf(grid, x.mean(), x.std(ddof=1)) * len(x) * width,
                color="#E07B39", linewidth=2, label="정규분포 (같은 평균·표준편차)")
        ax.legend(frameon=False, fontsize=8)
    ax.set_title(f"{series.name} 히스토그램")
    ax.set_xlabel(str(series.name))
    ax.set_ylabel("빈도")
    fig.tight_layout()
    plt.close(fig)  # 메모리 누수 방지 (그림 객체는 반환해서 계속 사용 가능)
    return fig


def boxplot(series, k=1.5):
    fig, ax = new_figure(width=4, height=4)
    ax.boxplot(series.dropna(), whis=k, patch_artist=True,
               boxprops={"facecolor": "#DCE6F2", "edgecolor": EDGE},
               medianprops={"color": EDGE, "linewidth": 2})
    ax.set_title(f"{series.name} 박스플롯 (수염 = IQR×{k})")
    ax.set_xticks([])
    fig.tight_layout()
    plt.close(fig)
    return fig


def bar_counts(counts, title):
    fig, ax = new_figure()
    counts.plot.bar(ax=ax, color=PRIMARY)
    ax.set_title(title)
    ax.set_ylabel("빈도")
    ax.tick_params(axis="x", rotation=45)
    fig.tight_layout()
    plt.close(fig)
    return fig
