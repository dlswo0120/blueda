"""속성 기반 테스트 (살충제 패러독스 대응 2): Hypothesis가 입력을 만들고, 어떤 입력에도 성립해야 하는 '속성'을 확인합니다.

- 사람이 고른 예시 대신 빈 글자, 공백, 한글, "001" 같은 숫자 모양 글자, 결측, 음수, 아주 큰 수를 Hypothesis가 섞어 넣습니다.
- 실패하면 가장 작은 실패 입력으로 줄여서 보여 줍니다 (Falsifying example).
- 한 번 찾은 실패 입력은 .hypothesis 폴더에 저장돼 다음 실행에 먼저 다시 시도합니다 (저장소에는 올리지 않음).
- 실행 수 조절: HYPOTHESIS_PROFILE=thorough (단계 마무리 때, 예시 500개)
"""
import contextlib
import io
import os
import warnings

import numpy as np
import pandas as pd
import pytest

hyp = pytest.importorskip("hypothesis")        # 설치 안 돼 있으면 건너뜀: pip install -e .[dev]
from hypothesis import HealthCheck, given, settings, strategies as st   # noqa: E402

from blueda import Blueda, descriptive, tables   # noqa: E402
from blueda.config import BluedaConfig           # noqa: E402
from blueda.loader import optimize_dtypes        # noqa: E402
from blueda.scope import Filter                  # noqa: E402

settings.register_profile("default", max_examples=60, deadline=None,
                          suppress_health_check=[HealthCheck.too_slow])
settings.register_profile("thorough", max_examples=500, deadline=None,
                          suppress_health_check=[HealthCheck.too_slow])
# 돌연변이 테스트용: 입력을 고정 (무작위로 새 버그가 나오면 돌연변이를 '잡았다'고 잘못 셈)
settings.register_profile("fixed", max_examples=60, deadline=None, derandomize=True, database=None,
                          suppress_health_check=[HealthCheck.too_slow])
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))

# 범주 값: 흔한 값 + 까다로운 글자 (빈 글자, 공백, 한글, 숫자 모양, 특수문자)
KEYS = st.one_of(st.sampled_from(["A", "B", "서울", "부산", "001", "1", " ", "", "a b", "N/A", "None"]),
                 st.text(alphabet="가나다abc019 _-", min_size=1, max_size=4))
NUMS = st.one_of(st.floats(-1e6, 1e6, allow_nan=False, allow_infinity=False), st.integers(-1000, 1000).map(float),
                 st.just(np.nan))


@st.composite
def frames(draw, min_rows=1, max_rows=40):
    """범주 2개(g, h) + 수치 2개(v, w) 데이터. 결측 포함, 가끔 메모리 최적화(category) 적용"""
    n = draw(st.integers(min_rows, max_rows))
    d = pd.DataFrame({
        "g": draw(st.lists(st.one_of(KEYS, st.none()), min_size=n, max_size=n)),
        "h": draw(st.lists(st.one_of(KEYS, st.none()), min_size=n, max_size=n)),
        "v": draw(st.lists(NUMS, min_size=n, max_size=n)),
        "w": draw(st.lists(NUMS, min_size=n, max_size=n)),
    })
    if draw(st.booleans()):
        d, _ = optimize_dtypes(d)
    return d


def quiet():
    """엔진이 찍는 범위 안내·경고를 숨김"""
    stack = contextlib.ExitStack()
    stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
    stack.enter_context(warnings.catch_warnings())
    warnings.simplefilter("ignore")
    return stack


@given(frames())
def test_pivot_total_equals_plain_sum(d):
    """피벗 '전체' 합계 = 행 키가 있는 행들의 값 합계 (키 글자가 무엇이든)"""
    ok = d["g"].notna()
    if not ok.any() or d.loc[ok, "v"].notna().sum() == 0:
        return
    r = tables.pivot_table(d, "g", None, "v", "합계")
    total = float(r.tables["피벗 표"].loc["전체"].iloc[0])
    assert np.isclose(total, d.loc[ok, "v"].sum(), rtol=1e-6, atol=1e-2)


@given(frames())
def test_crosstab_counts_and_row_percent(d):
    """교차표 전체 개수 = 두 열 모두 값이 있는 행 수, 행 %는 행마다 합 100"""
    both = d["g"].notna() & d["h"].notna()
    if not both.any():
        with pytest.raises(Exception, match="함께 값이 있는 행이 없어"):
            tables.crosstab(d, "g", "h", "행 %")
        return
    r = tables.crosstab(d, "g", "h", "행 %")
    assert int(r.tables["교차표 (개수)"].loc["전체", "전체"]) == int(both.sum())
    pct = r.tables["교차표 (행 %)"].drop(index="전체", errors="ignore").drop(columns="전체", errors="ignore")
    assert np.allclose(pct.sum(axis=1), 100, atol=0.6)          # 반올림(소수 1자리) 오차 허용


@given(frames(min_rows=2))
def test_describe_numeric_is_consistent(d):
    """최솟값 ≤ Q1 ≤ 중앙값 ≤ Q3 ≤ 최댓값, 평균도 범위 안, 표준편차 ≥ 0, 개수 = 결측 아닌 값 수"""
    r = descriptive.describe_numeric(d, with_charts=False)
    if r.status != "SUCCESS":
        return
    t = r.tables["수치형 요약"]
    for c in t.index:
        row, x = t.loc[c], d[c].dropna()
        assert int(row["개수"]) == len(x)
        if len(x) == 0:                       # 값이 모두 결측: 개수 0, 통계는 빈칸 (pandas와 같음)
            continue
        lo, hi = row["최솟값"] - 1e-3, row["최댓값"] + 1e-3
        assert lo <= row["평균"] <= hi and lo <= row["중앙값"] <= hi
        assert lo <= row["Q1"] <= row["중앙값"] + 1e-3 <= row["Q3"] + 2e-3 <= hi + 2e-3   # 사분위 순서
        assert np.isnan(row["표준편차"]) or row["표준편차"] >= 0


@given(frames(), st.lists(KEYS, min_size=1, max_size=3, unique=True))
def test_filter_in_matches_isin(d, values):
    """값 필터 행 수 = pandas isin 행 수 (category·글자 열 모두)"""
    with quiet():
        bd = Blueda(d.copy(), BluedaConfig(print_code=False))
        bd.set_scope(filters=[Filter("g", "in", values=values)])
        mask, _ = bd.scope.row_mask(bd.df)
    assert int(mask.sum()) == int(d["g"].astype(object).isin(values).sum())


@given(frames(), st.floats(-1e6, 1e6), st.floats(0, 1e6))
def test_range_filter_is_monotonic(d, lo, width):
    """범위를 넓히면 남는 행이 줄지 않는다"""
    with quiet():
        bd = Blueda(d.copy(), BluedaConfig(print_code=False))
        bd.set_scope(filters=[Filter("v", "between", lo=lo, hi=lo + width)])
        narrow = int(bd.scope.row_mask(bd.df)[0].sum())
        bd.set_scope(filters=[Filter("v", "between", lo=lo - 1, hi=lo + width + 1)])
        wide = int(bd.scope.row_mask(bd.df)[0].sum())
    assert narrow <= wide


@given(frames())
def test_optimize_dtypes_keeps_values(d):
    """메모리 최적화 전후 값이 같다 (결측 위치 포함)"""
    o, _ = optimize_dtypes(d.copy())
    for c in d.columns:
        a, b = d[c].astype(object), o[c].astype(object)
        assert (a.isna() == b.isna()).all()
        assert (a[a.notna()] == b[b.notna()]).all()


@given(frames())
def test_any_input_gives_clean_messages(d):
    """어떤 입력이든 결과 문장에 nan·inf·예상 못 한 오류가 나오지 않는다"""
    with quiet():
        bd = Blueda(d.copy(), BluedaConfig(print_code=False))
        bd.describe(with_charts=False)
        bd.pivot_table("g", "h", "v", "평균")
        bd.crosstab("g", "h", "개수")
        bd.anova("g", "v")
        bd.correlation_test("v", "w")
    for r in bd.results:
        assert "예상하지 못한 오류" not in r.message, (r.name, r.message)
        assert not any(t in r.message for t in ("nan", "inf")), (r.name, r.message)
