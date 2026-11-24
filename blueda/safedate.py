"""날짜 읽기를 한곳에서: pd.to_datetime(errors="coerce")로도 막히지 않는 오류까지 막습니다.

errors="coerce"는 형식이 틀린 값을 NaT로 바꾸지만, 시간대가 섞인 값
(예: '2024-01-01T09:00+09:00'과 '...+00:00', 또는 '0a-0'처럼 시간대로 읽히는 코드 값)은 그래도 ValueError를 냅니다.
v0.5.4 속성 기반 테스트(Hypothesis)에서 찾았습니다. 범주 값 '001', '0a-0'이 섞인 열로 피벗하면 멈췄습니다.

시간대가 섞이면 pandas 안내대로 UTC로 맞춘 뒤 시간대 표시를 떼서(naive) 돌려줍니다.
그래야 기간 필터의 pd.Timestamp('2024-06-01') 같은 값과 비교할 수 있습니다.
"""
import pandas as pd

_ERRORS = (ValueError, TypeError, OverflowError)


def _naive(res):
    """시간대가 붙은 결과면 UTC 기준으로 바꾸고 시간대 표시를 뗀다."""
    if isinstance(res, pd.Series) and isinstance(res.dtype, pd.DatetimeTZDtype):
        return res.dt.tz_convert(None)
    if isinstance(res, pd.DatetimeIndex) and res.tz is not None:
        return res.tz_convert(None)
    return res


def to_dates(values, format=None, report=False):
    """values를 날짜로. 못 읽는 값은 NaT. report=True면 (결과, UTC로 맞췄는지)를 돌려준다.

    format: None(자동 추정) 또는 "mixed"(값마다 형식이 달라도 허용)
    """
    kw = {"errors": "coerce"}
    if format:
        kw["format"] = format
    utc = False
    try:
        res = pd.to_datetime(values, **kw)
    except _ERRORS:
        try:
            res, utc = pd.to_datetime(values, utc=True, **kw), True     # 시간대가 섞인 경우
        except _ERRORS:                                                  # 그래도 안 되면 전부 날짜 아님으로
            index = getattr(values, "index", None)
            res = pd.Series(pd.NaT, index=index, dtype="datetime64[ns]") if index is not None \
                else pd.to_datetime(pd.Series([pd.NaT] * len(values)))
    res = _naive(res)
    return (res, utc) if report else res
