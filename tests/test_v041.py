"""v0.4.1 수정 사항 테스트 — 실습 데이터 없이도 돌아가는 가상 데이터 버전."""
import numpy as np
import pandas as pd

from blueda.loader import optimize_dtypes
from blueda.preprocess_check import check_result


def _df(n=2000, seed=0):
    rng = np.random.default_rng(seed)
    return pd.DataFrame({
        "id": np.arange(1, n + 1),                                   # ID 후보
        "fail": (rng.random(n) < 0.03).astype(int),                  # 0/1, 1이 드묾
        "discount": rng.choice([0, 0.1, 0.2, 0.8], n, p=[.6, .2, .15, .05]),  # 이산값
        "speed": np.r_[rng.normal(1500, 100, n - 5), [3000] * 5],    # 연속형 + 진짜 극단값 5개
        "region": rng.choice(["East", "West", "South"], n),
        "date": pd.date_range("2024-01-01", periods=n, freq="h").strftime("%Y-%m-%d"),
    })


def test_binary_discrete_id_skipped_in_outliers():
    r = check_result(_df())
    txt = r.tables["전처리 점검"].loc["4. 이상치", "내용"]
    assert "speed:" in txt
    for c in ("fail:", "discount:", "id:"):
        assert c not in txt
    assert any("fail(" in n and "discount(" in n for n in r.notes)   # 뺀 열은 안내 문구로 알림


def test_outliers_only_gives_review_not_preprocessing():
    df = _df().drop(columns=["date"])
    r = check_result(df)
    assert r.tables["전처리 점검"].loc["4. 이상치", "상태"] == "확인 권장"
    assert "전처리 필요" not in r.message and "확인 권장" in r.message


def test_category_columns_checked_after_optimize():
    df = _df()
    df.loc[0, "region"] = "west "                    # 표기 오류
    df, changed = optimize_dtypes(df)
    assert {"region", "date"} <= set(changed["category"])
    r = check_result(df)
    t = r.tables["전처리 점검"]
    assert "region" in t.loc["5. 범주 불일치", "내용"]
    assert "date" in t.loc["1. 타입", "내용"]
    assert "전처리 필요" in r.message                 # 진짜 문제가 있으면 여전히 '전처리 필요'


def test_category_check_uses_unused_categories_safely():
    """필터 등으로 안 쓰이게 된 범주는 점검에 넣지 않는다"""
    df = _df()
    df, _ = optimize_dtypes(df)
    df["region"] = df["region"].cat.add_categories(["west "])   # 값으로는 안 쓰이는 범주
    t = check_result(df).tables["전처리 점검"]
    assert t.loc["5. 범주 불일치", "상태"] == "문제 없음"


def test_postal_code_not_converted_to_number():
    """우편번호처럼 숫자 모양 코드는 '숫자형 변환'을 권하지 않고, 자릿수 섞임을 알린다"""
    codes = ["2151", "02151", "77095", "60540"] * 40 + ["M7A"] * 4      # 캐나다식 코드 2.4%
    df = pd.DataFrame({"Postal Code": codes, "amount": [f"{i}" for i in range(len(codes))]})
    t = check_result(df).tables["전처리 점검"]
    txt = t.loc["1. 타입", "내용"]
    assert "Postal Code" in txt and "문자열로 두세요" in txt and "4자리 40개, 5자리 120개" in txt
    assert "amount: 문자열이지만" in txt                       # 진짜 숫자 열은 계속 변환 권장


def test_code_name_hint_word_boundary():
    from blueda.preprocess_check import _looks_like_code
    s = pd.Series(["10", "20", "30"])
    assert _looks_like_code("Customer ID", s) and _looks_like_code("주문번호", s)
    assert not _looks_like_code("paid", s) and not _looks_like_code("hotel_price", s)
    assert _looks_like_code("x", pd.Series(["007", "12"]))   # 앞자리 0


def test_unit_check_ignores_rare_number_prefix():
    names = ["Pen", "Paper", "4009 Highlighters", "Binder"] * 10
    t = check_result(pd.DataFrame({"name": names})).tables["전처리 점검"]
    assert t.loc["6. 단위", "상태"] == "문제 없음"
    t2 = check_result(pd.DataFrame({"w": ["10kg", "3kg", "5 kg", "7g"] * 5})).tables["전처리 점검"]
    assert t2.loc["6. 단위", "상태"] == "확인 필요"
