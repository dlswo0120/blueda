"""BLUEDA 빠른 시작 예제.

일부러 지저분하게 만든 가상 데이터로 기능을 한 번씩 실행해 봅니다.
실행: VS Code에서 이 파일을 열고 ▶ 버튼, 또는 터미널에서
    python examples/quickstart.py
"""

import numpy as np
import pandas as pd

from blueda import Blueda, BluedaConfig

# ------------------------------------------------------------
# 0. 예제용 가상 데이터 만들기 (실제 데이터 아님)
# ------------------------------------------------------------
rng = np.random.default_rng(0)
n = 200
df = pd.DataFrame({
    "region": rng.choice(["Seoul", "seoul ", "Busan", "BUSAN"], n),   # 표기 불일치
    "age": rng.integers(20, 60, n).astype(float),
    "price": [f"{v:,}원" for v in rng.integers(1000, 50000, n)],     # 단위가 붙은 문자열
    "score": rng.normal(70, 10, n),
})
df.loc[rng.choice(n, 15, replace=False), "age"] = np.nan              # 결측
df.loc[[3, 7], "score"] = [200, -80]                                  # 이상치
df = pd.concat([df, df.iloc[:5]], ignore_index=True)                  # 중복 5행

# ------------------------------------------------------------
# 1. 설정: 원하는 선택 기능만 켜기
# ------------------------------------------------------------
config = BluedaConfig(
    check_source_license=True,                   # E 켜기
    stat_checks=["normality", "correlation"],    # F: 원하는 검사만
    link_lecture_concepts=True,                  # G: 부캠 기간 동안 켜기
)
bd = Blueda(df, config=config, session_name="quickstart")

# ------------------------------------------------------------
# 2. A: 전처리 판단
# ------------------------------------------------------------
bd.check()

# ------------------------------------------------------------
# 3. E: 출처 기록 (예제라 일부러 비워둔 항목이 있습니다)
# ------------------------------------------------------------
bd.set_source(name="예제 가상 데이터", provider="BLUEDA 예제", license="CC0")

# ------------------------------------------------------------
# 4. B: 직접 작성한 분석 코드도 로그에 남기기
# ------------------------------------------------------------
step = bd.run(
    "지역 표기 통일 후 지역별 평균 점수",
    '''# [목적] 지역 이름의 공백·대소문자를 통일하고 지역별 평균 점수 보기
df["region_clean"] = df["region"].str.strip().str.title()   # 공백 제거 + 첫 글자만 대문자
print(df.groupby("region_clean")["score"].mean().round(2))  # 지역별 평균''',
    interpretation="표기 통일 후 4개였던 지역이 2개로 정리됨",
)
bd.link_lecture(step, "groupby 집계", "(강의명 / 출처)")

# ------------------------------------------------------------
# 5. F: 선택한 통계 가정 검사
# ------------------------------------------------------------
bd.stats(columns=["age", "score"])

# ------------------------------------------------------------
# 6. B·C: 로그, 코드 모음, 환경 정보 저장
# ------------------------------------------------------------
bd.save()
