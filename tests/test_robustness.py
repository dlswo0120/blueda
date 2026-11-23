"""견고성 테스트 (v0.5.1 검토에서 추가)

1. 모든 분석을 이상한 데이터(0행·1행·2행·한 그룹·전부 결측·상수 열)로 돌려도
   - 예외가 밖으로 새지 않고
   - 실행 전 점검이 통과시킨 경우에도 FAIL 문구에 nan·영어 오류 이름이 나오지 않아야 한다.
2. 모든 분석의 코드 로그를 원본 데이터에 그대로 실행하면 돌아가야 한다 (Colab 재현).
특수문자 열 이름(대괄호, 따옴표, 숫자 이름)을 일부러 넣었다.
"""
import contextlib
import io
import warnings

import matplotlib
import numpy as np
import pandas as pd
import pytest
from scipy import stats

from blueda import Blueda
from blueda import methods as M
from blueda.config import BluedaConfig
from blueda.scope import Filter

matplotlib.use("Agg")
rng = np.random.default_rng(0)
N = 300
BASE = pd.DataFrame({
    "온도 [K]": rng.normal(300, 2, N), "it's \"q\"": rng.normal(0, 1, N),
    "grp": rng.choice(["A", "B", "C"], N), "g2": rng.choice(["x", "y"], N),
    "cnt": rng.integers(1, 20, N),
    "date": pd.date_range("2024-01-01", periods=N, freq="D").strftime("%Y-%m-%d"),
    "allnan": np.nan, "const": 5.0, 123: rng.normal(0, 1, N),
})
T, Q = "온도 [K]", "it's \"q\""
CASES = {
    "describe": {}, "variable_types": {}, "check": {}, "zscore": {},
    "analysis_unit": {"key_columns": ["grp"], "unit_name": "그룹"},
    "sampling_distribution": {"column": T, "sample_size": 30, "n_samples": 200},
    "confidence_interval": {"column": T, "level": 0.95},
    "ci_proportion": {"column": "grp", "category": "A", "level": 0.95},
    "one_sample_ttest": {"column": T, "mu0": 300},
    "t_test": {"group_col": "g2", "value_col": T}, "anova": {"group_col": "grp", "value_col": T},
    "chi_square": {"row_col": "grp", "col_col": "g2"},
    "correlation_test": {"x": T, "y": Q}, "simple_regression": {"x": T, "y": Q},
    "multiple_regression": {"y": T, "xs": [Q, "grp"]},
    "pivot_table": {"rows": "grp", "columns": "g2", "values": T, "agg": "평균", "date_unit": "월"},
    "crosstab": {"rows": "grp", "columns": "g2", "normalize": "행 %", "date_unit": "월"},
}
for t, a in [("막대", dict(x="grp", y=T)), ("선", dict(x="date", y="cnt")), ("산점도", dict(x=T, y=Q)),
             ("히스토그램", dict(x=T)), ("상자그림", dict(x="grp", y=T)), ("상관 히트맵", {})]:
    CASES[f"chart_builder:{t}"] = dict(chart_type=t, **a)


def _scenario(name):
    d = BASE.copy()
    filters = None
    if name == "0행":
        filters = [Filter("grp", "in", values=["없음"])]
    elif name == "1행":
        d = d.head(1)
    elif name == "2행":
        d = d.head(2)
    elif name == "한 그룹":
        filters = [Filter("grp", "in", values=["A"])]
    elif name == "전부 결측":
        d[T] = np.nan
    elif name == "상수":
        d[T] = 7.0
    return d, filters


def _run(d, filters, case):
    key = case.split(":")[0]
    params = CASES[case]
    bd = Blueda(d, BluedaConfig(print_code=False))
    if filters:
        bd.set_scope(filters=filters)
    mask, _ = bd.scope.row_mask(bd.df)
    chk = M.precheck(key, params, bd.df.loc[mask.to_numpy(dtype=bool)], M.column_kinds(bd.df))
    with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings(record=True) as wl:
        warnings.simplefilter("always")
        r = M.run(bd, key, params)
    return chk, (r if isinstance(r, list) else [r]), [w for w in wl if "Glyph" not in str(w.message)]


@pytest.mark.parametrize("scenario", ["정상", "0행", "1행", "2행", "한 그룹", "전부 결측", "상수"])
@pytest.mark.parametrize("case", list(CASES))
def test_no_crash_no_raw_errors(scenario, case):
    d, filters = _scenario(scenario)
    chk, results, warns = _run(d, filters, case)
    if not chk.ok:
        return                                   # 화면에서는 실행 버튼이 꺼지는 경우
    for r in results:
        assert r.status == "SUCCESS", f"점검을 통과했는데 실패: {r.message}"
        assert not any(t in r.message for t in ("nan", "inf", "Error", "Traceback")), r.message
    assert not warns, [str(w.message) for w in warns]


@pytest.mark.parametrize("case", list(CASES))
def test_code_log_reruns_on_raw_data(case):
    _, results, _ = _run(BASE.copy(), None, case)
    for r in results:
        ns = {"pd": pd, "np": np, "stats": stats, "sub": BASE.copy(), "df": BASE.copy()}
        with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
            warnings.simplefilter("ignore")
            exec(r.code, ns)


def test_session_results_hold_png_not_figures():
    """세션에 쌓인 결과는 그림 객체가 아니라 PNG로 보관 (메모리 누적 방지)"""
    from blueda.result import ChartImage
    import matplotlib.pyplot as plt
    bd = Blueda(BASE.copy(), BluedaConfig(print_code=False))
    before = len(plt.get_fignums())                     # 다른 테스트가 열어 둔 그림 수
    with contextlib.redirect_stdout(io.StringIO()):
        r = bd.chart("막대", x="grp", y=T)
        bd.describe()
    img = r.figures["막대 차트"]
    assert isinstance(img, ChartImage) and img.png[:4] == b"\x89PNG" and 5_000 < len(img) < 400_000
    assert len(plt.get_fignums()) == before             # 분석 후 열린 그림 객체가 늘지 않음
    buf = io.BytesIO()
    img.savefig(buf, format="png", dpi=90)              # 내보내기와 같은 사용법
    assert buf.getvalue() == img.png
