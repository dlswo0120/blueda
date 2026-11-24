"""무작위 검증 (살충제 패러독스 대응 1): 실행할 때마다 다른 데이터·필터로 BLUEDA 결과를 pandas·scipy 직접 계산과 비교합니다.

- 고정 테스트는 같은 입력만 반복해서 새 버그를 못 찾게 됩니다. 이 파일은 실행마다 시드를 바꿉니다.
- 실패하면 메시지에 시드가 나옵니다. 같은 시드로 다시 돌리면 같은 데이터가 만들어져 재현됩니다.
    BLUEDA_FUZZ_SEED=<시드> pytest tests/test_fuzz.py
- 고친 버그의 시드는 FOUND_SEEDS에 추가합니다 (그 뒤로는 매번 고정으로 확인).
- 횟수 조절: BLUEDA_FUZZ_TRIALS (기본 25회, 단계 마무리 때는 400회 이상 권장)
"""
import contextlib
import io
import os
import secrets
import warnings

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from blueda import Blueda
from blueda.config import BluedaConfig
from blueda.loader import optimize_dtypes
from blueda.scope import Filter

# 무작위 검증에서 실제로 버그를 찾은 시드 (v0.5.3: 0행 범위 → 범주형 요약 IndexError). 고친 뒤 고정 회귀 테스트로 계속 확인
# 생성기(make_data·make_filters)를 바꾸면 같은 시드가 다른 데이터를 만드므로, 예전 코드로 다시 찾아 갱신할 것
FOUND_SEEDS = [1, 4, 5, 10, 14]

# 열 이름도 바꿔 가며 넣음 (한글·공백·숫자로 시작하는 이름에서만 나는 문제를 찾기 위해)
NAME_POOLS = {
    "g": ["g", "지역", "고객 등급", "1분류"],
    "h": ["h", "상태", "처리 결과", "Type"],
    "v": ["v", "매출", "처리 일수", "Torque [Nm]"],
    "w": ["w", "수량", "점수", "2차값"],
    "date": ["date", "주문일", "Order Date", "접수 일자"],
}


def make_data(rng):
    """무작위 데이터 1개와 열 이름 표를 만든다. 행 수·결측·범주 수·날짜 형식·메모리 최적화 여부를 매번 바꿈"""
    n = int(rng.integers(1, 3000)) if rng.random() < 0.9 else int(rng.integers(1, 6))   # 가끔 아주 작은 데이터
    cats = [f"c{i}" for i in range(int(rng.integers(2, 7)))]
    d = pd.DataFrame({
        "g": rng.choice(cats, n),
        "h": rng.choice(["x", "y", "z"], n, p=[.6, .3, .1]),
        "v": rng.normal(rng.uniform(-100, 100), rng.uniform(0.1, 50), n).round(int(rng.integers(0, 4))),
        "w": rng.integers(-50, 50, n).astype(float),
        "date": pd.Timestamp("2024-01-01") + pd.to_timedelta(rng.integers(0, 900, n), unit="D"),
    })
    for c in ("g", "v", "w"):                                   # 무작위 결측
        d.loc[rng.random(n) < rng.uniform(0, 0.3), c] = np.nan
    if rng.random() < 0.5:                                      # 날짜를 글자로 (실습 파일처럼)
        d["date"] = d["date"].dt.strftime(str(rng.choice(["%Y-%m-%d", "%Y/%m/%d"])))
    if rng.random() < 0.5:                                      # 화면처럼 메모리 최적화
        d, _ = optimize_dtypes(d)
    names = {k: str(rng.choice(pool)) for k, pool in NAME_POOLS.items()}
    return d.rename(columns=names), names


def make_filters(rng, N):
    """필터 0~4개를 무작위로 조합"""
    fs = []
    if rng.random() < 0.6:
        vals = [str(v) for v in rng.choice(["c0", "c1", "c2", "c3", "없음"], int(rng.integers(1, 3)), replace=False)]
        fs.append(Filter(N["g"], "in", values=vals))
    if rng.random() < 0.5:
        lo, hi = sorted(rng.uniform(-120, 120, 2))
        fs.append(Filter(N["v"], "between", lo=float(lo), hi=float(hi)))
    if rng.random() < 0.4:
        fs.append(Filter(N["date"], "between", lo="2024-06-01", hi="2025-03-31"))
    if rng.random() < 0.3:
        fs.append(Filter(op="notna"))
    return fs


def expected_mask(d, fs, N):
    """필터를 pandas로 직접 적용한 기대 행"""
    m = pd.Series(True, index=d.index)
    for f in fs:
        if f.op == "notna":
            m &= d.notna().all(axis=1)
            continue
        s = d[f.column]
        if f.op == "in":
            m &= s.astype(object).isin(f.values)
        elif f.column == N["date"]:
            t = pd.to_datetime(s.astype(object), errors="coerce")
            m &= t.between(pd.Timestamp(f.lo), pd.Timestamp(f.hi))
        else:
            m &= s.between(f.lo, f.hi)
    return m


def run_trial(seed):
    """시드 1개로 데이터·필터를 만들고 BLUEDA 결과를 직접 계산과 비교. 틀리면 AssertionError"""
    rng = np.random.default_rng(seed)
    d, N = make_data(rng)
    fs = make_filters(rng, N)
    g, h, v, w, dt = N["g"], N["h"], N["v"], N["w"], N["date"]
    ctx = f"seed={seed}, 행={len(d)}, 열={list(N.values())}, 필터={[f.label() for f in fs]}"
    with warnings.catch_warnings(), contextlib.redirect_stdout(io.StringIO()):
        warnings.simplefilter("ignore")
        bd = Blueda(d.copy(), BluedaConfig(print_code=False))
        bd.set_scope(filters=fs)
        exp = expected_mask(d, fs, N)
        mask, _ = bd.scope.row_mask(bd.df)
        assert int(mask.sum()) == int(exp.sum()), f"필터 행 수 {int(mask.sum())} ≠ {int(exp.sum())} ({ctx})"
        sub = d[exp.to_numpy()]
        _, lines = bd.scope.row_mask(bd.df)                     # 코드 로그를 실행해도 같은 행이 나와야 함 (Colab에 붙여 넣는 경우)
        env = {"df": bd.df, "pd": pd, "np": np}
        exec("mask = pd.Series(True, index=df.index)\n" + "\n".join(lines), env)
        assert int(env["mask"].fillna(False).sum()) == int(exp.sum()), f"코드 로그 행 수 다름 {lines} ({ctx})"

        num = bd.describe()[0].tables.get("수치형 요약")         # 기술통계: 개수·평균·표준편차
        for c in (v, w):
            x = sub[c].dropna()
            if len(x) >= 2 and num is not None and c in num.index:
                assert int(num.loc[c, "개수"]) == len(x), f"{c} 개수 ({ctx})"
                assert np.isclose(num.loc[c, "평균"], x.mean(), atol=1e-3), f"{c} 평균 ({ctx})"
                assert np.isclose(num.loc[c, "표준편차"], x.std(), atol=1e-3), f"{c} 표준편차 ({ctx})"

        pv = bd.pivot_table(g, h, v, "합계")                     # 피벗: 합계 (전체 포함)
        if pv.status == "SUCCESS":
            ep = pd.pivot_table(sub.astype({g: object, h: object}), index=g, columns=h, values=v,
                                aggfunc="sum", margins=True, margins_name="전체")
            got = pv.tables["피벗 표"].loc[ep.index, ep.columns].to_numpy(dtype=float)
            assert np.allclose(got, ep.to_numpy(dtype=float), atol=1e-3, equal_nan=True), f"피벗 값 ({ctx})"

        ct = bd.crosstab(g, h, "행 %")                          # 교차표: 개수
        if ct.status == "SUCCESS":
            e = pd.crosstab(sub[g].astype(object), sub[h].astype(object), margins=True, margins_name="전체")
            assert (ct.tables["교차표 (개수)"].loc[e.index, e.columns].to_numpy() == e.to_numpy()).all(), f"교차표 ({ctx})"

        pm = bd.pivot_table(dt, None, w, "개수", "월")            # 월별 개수
        if pm.status == "SUCCESS":
            t = pd.to_datetime(sub[dt].astype(object), errors="coerce")
            em = (sub.assign(_k=t.dt.to_period("M").astype(str).where(t.notna()))
                  .dropna(subset=["_k"]).groupby("_k")[w].count())
            got = pm.tables["피벗 표"].drop(index="전체").iloc[:, 0]
            assert list(got.index) == list(em.index) and (got.to_numpy() == em.to_numpy()).all(), f"월별 개수 ({ctx})"

        an = bd.anova(g, v)                                     # 분산분석 F
        if an.status == "SUCCESS":
            groups = [x[v].dropna().to_numpy() for _, x in sub.groupby(sub[g].astype(object))]
            f, _ = stats.f_oneway(*[x for x in groups if len(x)])
            assert np.isclose(float(an.metrics["F 통계량"]), f, atol=1e-3, rtol=1e-4), f"F ({ctx})"

        co = bd.correlation_test(v, w)                          # 상관계수
        if co.status == "SUCCESS":
            pair = sub[[v, w]].dropna()
            got = float(str(co.metrics["Pearson r"]).split()[0])
            assert np.isclose(got, pair[v].corr(pair[w]), atol=1e-3), f"r ({ctx})"

    for r in bd.results:                                        # 어떤 결과든 사용자 문장이 깨지면 안 됨
        assert not any(t in r.message for t in ("nan", "inf", "Traceback")), f"{r.name}: {r.message} ({ctx})"
        assert "예상하지 못한 오류" not in r.message, f"{r.name} 예상 못 한 오류: {r.message} ({ctx})"


@pytest.mark.parametrize("seed", FOUND_SEEDS)
def test_fuzz_found_seeds(seed):
    """예전에 버그를 찾은 시드는 고정으로 계속 확인"""
    run_trial(seed)


def test_fuzz_rotating_seeds():
    """실행할 때마다 새 시드 구간. 실패 메시지의 seed로 재현"""
    base = int(os.environ.get("BLUEDA_FUZZ_SEED") or secrets.randbelow(10**9))
    trials = int(os.environ.get("BLUEDA_FUZZ_TRIALS", "25"))
    print(f"[무작위 검증] 시작 시드 {base}, {trials}회")    # pytest -s 로 보면 이번 시드가 보임
    for seed in range(base, base + trials):
        run_trial(seed)
