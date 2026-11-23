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

# 행이 이보다 많으면 차트는 표본으로 그립니다 (통계값은 항상 전체 데이터). Blueda가 설정값으로 바꿉니다.
SAMPLE_N = 100_000


# 박스플롯 이상값 후보 점: 데이터가 크면 수천 개가 겹치므로 작고 옅게
FLIER = {"marker": "o", "markersize": 2.5, "markerfacecolor": "#3B4656", "markeredgecolor": "none", "alpha": 0.35}


def integer_bins(x, max_bins=60):
    """값이 모두 정수면 구간 경계를 n.5에 두어, 한 구간에 정수가 1개 또는 2개씩 섞여 생기는
    '막대 높이가 번갈아 높고 낮아지는' 착시를 막습니다. 정수가 아니면 'auto'."""
    import numpy as np
    v = np.asarray(x, dtype=float)
    if len(v) == 0 or not np.all(np.mod(v, 1) == 0):
        return "auto"
    lo, hi = v.min(), v.max()
    step = max(1, int(np.ceil((hi - lo + 1) / max_bins)))
    return np.arange(lo - 0.5, hi + step + 0.5, step)


def sample(data, n=None, seed=0):
    """차트용 표본. 행이 n 이하면 그대로, 넘으면 무작위 n개 (시드 고정으로 매번 같은 그림)."""
    n = n or SAMPLE_N
    if len(data) <= n:
        return data
    return data.sample(n=n, random_state=seed)


def sample_note(n_rows):
    """표본으로 그렸을 때 결과에 붙일 안내 문구. 표본이 아니면 None."""
    if n_rows > SAMPLE_N:
        return f"차트는 {n_rows:,}행 중 표본 {SAMPLE_N:,}행으로 그렸습니다. 통계값은 전체 데이터로 계산했습니다."
    return None


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


def heavy_tail(x):
    """꼬리가 아주 긴지: 1~99% 범위가 전체 범위의 25%도 안 되면 True
    (정규분포는 약 60%, 지수분포도 약 50%라 걸리지 않고, 극단값 몇 개가 축을 늘린 경우만 걸림)"""
    import pandas as pd
    x = pd.Series(x).dropna()
    if len(x) < 20:
        return False
    lo, hi = x.quantile([0.01, 0.99])
    full = x.max() - x.min()
    return bool(full > 0 and (hi - lo) < 0.25 * full)


def fit_box_axis(ax, values):
    """상자그림 세로축 맞추기. 꼬리가 아주 길면 상자가 바닥에 눌려 안 보이므로
    - 값이 모두 양수: 로그 눈금
    - 음수가 있으면: 가운데 99% 범위만 보이게 (밖의 점은 그림 밖)
    반환: 제목에 붙일 짧은 설명 (없으면 "")"""
    import pandas as pd
    allv = pd.concat([pd.Series(v, dtype=float) for v in values]) if len(values) else pd.Series(dtype=float)
    if not heavy_tail(allv):
        return ""
    if (allv > 0).all():
        ax.set_yscale("log")
        return " · 로그 눈금"
    lo, hi = allv.quantile([0.005, 0.995])
    if hi <= lo:                                          # 값 대부분이 한 값이면 범위를 줄일 수 없음
        return ""
    pad = (hi - lo) * 0.05
    ax.set_ylim(lo - pad, hi + pad)
    out = int(((allv < lo - pad) | (allv > hi + pad)).sum())
    return f" · 가운데 99% 범위 (밖의 점 {out:,}개 생략)" if out else " · 가운데 99% 범위"


def histogram(series, bins="auto", normal_curve=True):
    """히스토그램. normal_curve=True면 같은 평균·표준편차의 정규분포 곡선을 겹쳐 그립니다."""
    import numpy as np
    from scipy import stats

    x = sample(series.dropna())   # 큰 데이터는 표본으로 (평균·표준편차 곡선도 표본 기준)
    suffix = ""
    lo, hi = x.quantile([0.005, 0.995]) if len(x) else (0, 0)
    if heavy_tail(x) and hi > lo:
        # 꼬리가 아주 길면 거의 모든 값이 막대 하나에 몰려 분포가 안 보임 → 가운데 99%만 그림
        out = int(((x < lo) | (x > hi)).sum())
        x = x[(x >= lo) & (x <= hi)]
        suffix = f" (가운데 99%, 밖의 값 {out:,}개 생략)"
    if bins == "auto":
        bins = integer_bins(x)
        if isinstance(bins, str):
            edges = np.histogram_bin_edges(x, bins="auto")
            bins = edges if len(edges) <= 101 else 100
    fig, ax = new_figure()
    counts, edges, _ = ax.hist(x, bins=bins, color=PRIMARY, edgecolor="white", label="관측값")
    if normal_curve and len(x) >= 3 and x.std(ddof=1) > 0:
        grid = np.linspace(edges[0], edges[-1], 200)
        width = edges[1] - edges[0]
        # 정규분포 밀도 × 표본 수 × 구간 폭 = 히스토그램과 같은 '빈도' 눈금으로 맞춤
        ax.plot(grid, stats.norm.pdf(grid, x.mean(), x.std(ddof=1)) * len(x) * width,
                color="#E07B39", linewidth=2, label="정규분포 (같은 평균·표준편차)")
        ax.set_ylim(0, max(ax.get_ylim()[1], counts.max() * 1.22))   # 위쪽에 범례 자리 확보
        ax.legend(loc="upper right", fontsize=8, frameon=True, framealpha=0.9, edgecolor="none")
    ax.set_title(f"{series.name} 히스토그램{suffix}", fontsize=10 if suffix else None)
    ax.set_xlabel(str(series.name))
    ax.set_ylabel("빈도")
    fig.tight_layout()
    plt.close(fig)  # 메모리 누수 방지 (그림 객체는 반환해서 계속 사용 가능)
    return fig


def boxplot(series, k=1.5):
    fig, ax = new_figure(width=4, height=4)
    v = sample(series.dropna())
    ax.boxplot(v, whis=k, patch_artist=True, flierprops=FLIER,
               boxprops={"facecolor": "#DCE6F2", "edgecolor": EDGE},
               medianprops={"color": EDGE, "linewidth": 2})
    suffix = fit_box_axis(ax, [v])
    ax.set_title(f"{series.name} 박스플롯 (수염 = IQR×{k}{suffix})", fontsize=10 if suffix else None)
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
