"""분석 범위(scope.py) 규칙 테스트 — 돌연변이 테스트(v0.5.3 이후 첫 측정)에서 살아남은 부분을 메운다.

살아남은 돌연변이가 알려 준 빈틈: 이상값 후보 제외 경계, 행 구간, 날짜 한쪽 끝·잘못된 날짜 글자,
글자로 저장된 숫자 열, 특정 열만 결측 제외, 그리고 '코드 로그를 실행하면 같은 행이 나오는지'.
"""
import numpy as np
import pandas as pd
import pytest

from blueda.scope import AnalysisScope, Filter


def run_code(df, lines):
    """row_mask가 남긴 코드 줄을 실제로 실행해 마스크를 돌려준다 (사용자가 Colab에 붙여 넣는 것과 같음)"""
    env = {"df": df, "pd": pd, "np": np}
    exec("mask = pd.Series(True, index=df.index)\n" + "\n".join(lines), env)
    return env["mask"].fillna(False).to_numpy(dtype=bool)


def check(df, scope, expected_rows):
    """툴 결과 = 기대 행, 그리고 코드 로그 실행 결과 = 툴 결과"""
    mask, lines = scope.row_mask(df)
    got = list(np.flatnonzero(mask.to_numpy(dtype=bool)))
    assert got == expected_rows, (got, expected_rows)
    assert list(np.flatnonzero(run_code(df, lines))) == got, f"코드 로그 결과가 다름: {lines}"


# ── 이상값 후보 제외: 경계 = Q1 − k·IQR ~ Q3 + k·IQR ──
def test_iqr_bounds_exact():
    # 값 0~20 + 아주 크고 작은 값: 경계는 공식으로 계산한 값과 같아야 하고, 양끝 극단값만 빠져야 함
    v = list(range(21)) + [-100, 100, -20]           # -20: 경계(-11) 밖. 경계 공식이 틀리면 남게 됨
    df = pd.DataFrame({"v": v})
    q1, q3 = pd.Series(v).quantile([.25, .75])
    lo, hi = q1 - 1.5 * (q3 - q1), q3 + 1.5 * (q3 - q1)
    expect = [i for i, x in enumerate(v) if lo <= x <= hi]
    check(df, AnalysisScope(filters=[Filter("v", "iqr_inside")]), expect)
    assert expect == list(range(21))                              # 0~20은 모두 남고 ±100, -20은 빠짐


def test_iqr_k_changes_bounds():
    df = pd.DataFrame({"v": [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 20]})
    n15 = AnalysisScope(filters=[Filter("v", "iqr_inside", k=1.5)]).count_rows(df)
    n3 = AnalysisScope(filters=[Filter("v", "iqr_inside", k=3.0)]).count_rows(df)
    assert (n15, n3) == (11, 12)


def test_iqr_on_numbers_stored_as_text():
    df = pd.DataFrame({"v": ["1", "2", "3", "4", "100", "없음"]})
    m, _ = Filter("v", "iqr_inside").mask_and_code(df)
    assert list(m) == [True, True, True, True, False, False]


# ── 행 구간 ──
@pytest.mark.parametrize("start,end,expect", [
    (2, 5, [2, 3, 4]), (None, 3, [0, 1, 2]), (7, None, [7, 8, 9]), (0, 0, []), (8, 100, [8, 9]),
])
def test_row_range(start, end, expect):
    df = pd.DataFrame({"v": range(10)}, index=range(100, 110))   # 인덱스가 0부터가 아니어도 위치 기준
    check(df, AnalysisScope(row_start=start, row_end=end), expect)


def test_row_range_with_filter():
    df = pd.DataFrame({"v": range(10)})
    check(df, AnalysisScope(row_start=2, row_end=8, filters=[Filter("v", "between", lo=5)]), [5, 6, 7])


# ── 수치 범위 ──
def test_between_one_side_and_both():
    df = pd.DataFrame({"v": [1.0, 2, 3, np.nan, 5]})
    check(df, AnalysisScope(filters=[Filter("v", "between", lo=2)]), [1, 2, 4])
    check(df, AnalysisScope(filters=[Filter("v", "between", hi=3)]), [0, 1, 2])
    check(df, AnalysisScope(filters=[Filter("v", "between", lo=2, hi=3)]), [1, 2])
    check(df, AnalysisScope(filters=[Filter("v", "between")]), [0, 1, 2, 3, 4])   # 조건 없음 = 모든 행


# ── 날짜 범위 (실습처럼 글자로 저장된 날짜 포함) ──
DATES = ["2024-01-15", "2024-06-01", "2024-07-20", "2025-03-31", "2025-04-01"]


@pytest.mark.parametrize("fmt", ["%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "datetime"])
@pytest.mark.parametrize("lo,hi,expect", [
    ("2024-06-01", "2025-03-31", [1, 2, 3]),
    ("2024-06-01", None, [1, 2, 3, 4]),
    (None, "2024-07-20", [0, 1, 2]),
])
def test_date_range_text_and_datetime(fmt, lo, hi, expect):
    t = pd.to_datetime(pd.Series(DATES))
    col = t if fmt == "datetime" else t.dt.strftime(fmt)
    df = pd.DataFrame({"d": col})
    check(df, AnalysisScope(filters=[Filter("d", "between", lo=lo, hi=hi)]), expect)


def test_date_range_ignores_unparseable_text():
    df = pd.DataFrame({"d": ["2024-06-10", "모름", "", None, "2024-13-45", "2024-07-01"]})
    check(df, AnalysisScope(filters=[Filter("d", "between", lo="2024-06-01", hi="2024-06-30")]), [0])


# ── 결측 제외 ──
def test_notna_specific_columns():
    df = pd.DataFrame({"a": [1, np.nan, 3, 4], "b": [1, 2, np.nan, 4], "c": [np.nan, 2, 3, 4]})
    check(df, AnalysisScope(filters=[Filter(op="notna", columns=["a", "b"])]), [0, 3])
    check(df, AnalysisScope(filters=[Filter("c", "notna")]), [1, 2, 3])
    check(df, AnalysisScope(filters=[Filter(op="notna")]), [3])


def test_unknown_filter_op_is_reported():
    with pytest.raises(ValueError, match="알 수 없는 조건: 비슷함"):
        Filter("v", "비슷함").mask_and_code(pd.DataFrame({"v": [1]}))


# ── 화면에 보이는 범위 문장 ──
def test_scope_and_chip_text():
    assert Filter("지역", "in", values=["서울", "부산", "대구"]).label() == "지역: 서울 외 2"
    assert Filter("지역", "in", values=["서울", "부산"]).label() == "지역: 서울, 부산"
    assert Filter("지역", "in", values=[]).label() == "지역: 없음"
    assert Filter("나이", "between", lo=20).label() == "나이: 20 ~ "
    assert Filter("나이", "iqr_inside").label() == "나이: 이상값 후보 제외"
    s = AnalysisScope(columns=["a", "b"], filters=[Filter(op="notna")], query="a > 1", row_start=None, row_end=50, dropna=True)
    assert s.describe() == "열 2개 · 결측 제외 · 조건 [a > 1] · 행 0~50 · 결측 행 제외"
    assert AnalysisScope(row_start=10).describe() == "전체 열 · 행 10~끝"
    assert AnalysisScope().describe() == "전체 열"


def test_date_range_blank_side_means_open():
    """화면에서 시작·끝 칸을 비워 두면 빈 글자("")가 온다 → 그쪽은 제한 없음"""
    df = pd.DataFrame({"d": DATES})
    check(df, AnalysisScope(filters=[Filter("d", "between", lo="", hi="2024-07-20")]), [0, 1, 2])
    check(df, AnalysisScope(filters=[Filter("d", "between", lo="2025-01-01", hi="")]), [3, 4])
    assert Filter("d", "between", hi="2024-07-20").label() == "d:  ~ 2024-07-20"


# ── apply(): 결과 데이터와 범위 코드 전체 ──
@pytest.mark.parametrize("scope", [
    AnalysisScope(),
    AnalysisScope(columns=["v", "d"]),
    AnalysisScope(filters=[Filter("g", "in", values=["a"]), Filter("d", "between", lo="2024-06-01")], columns=["g", "v"]),
    AnalysisScope(row_start=1, row_end=4, dropna=True),
    AnalysisScope(query="v > 1", dropna=True, columns=["v", "w"]),
], ids=["전체", "열만", "필터+열", "행 구간+결측", "직접 입력+결측"])
def test_apply_code_rebuilds_same_sub(scope):
    """apply가 돌려주는 코드를 실행하면 같은 sub가 나와야 한다 (결과 탭 코드 맨 앞에 붙는 부분)"""
    df = pd.DataFrame({"g": ["a", "b", "a", "a", "b"], "v": [1.0, 2, np.nan, 4, 5], "w": [1, np.nan, 3, 4, 5],
                       "d": ["2024/01/15", "2024/06/01", "2024/07/20", "2025/03/31", "2025/04/01"]})
    sub, code = scope.apply(df)
    assert code.startswith("# [목적]")
    env = {"df": df.copy(), "pd": pd, "np": np}
    exec(code, env)
    pd.testing.assert_frame_equal(env["sub"].reset_index(drop=True), sub.reset_index(drop=True), check_dtype=False)


def test_apply_reports_missing_columns():
    df = pd.DataFrame({"a": [1]})
    with pytest.raises(KeyError, match=r"데이터에 없는 열: \['x', 'y'\]"):
        AnalysisScope(columns=["x"], filters=[Filter("y", "in", values=[1])]).apply(df)
