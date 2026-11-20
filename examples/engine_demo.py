"""1단계 분석 엔진 예제: 파일 판별 → 분석 범위 → 기술통계 → 미지원 알림 → 내보내기.

실행: python examples/engine_demo.py
"""

import os

import numpy as np
import pandas as pd

from blueda import Blueda

# 0. 예제용 가상 데이터를 CP949 CSV로 저장 (공공기관 파일에서 흔한 인코딩)
os.makedirs("data", exist_ok=True)
rng = np.random.default_rng(0)
pd.DataFrame({
    "지역": rng.choice(["서울", "부산", "대구"], 150),
    "나이": rng.integers(20, 65, 150),
    "매출": rng.normal(100, 20, 150).round(1),
    "등급": rng.choice(["A", "B", "C"], 150),
}).to_csv("data/sample_cp949.csv", index=False, encoding="cp949")

# 1. 파일 형식 자동 판별 + 불러오기
bd = Blueda.from_file("data/sample_cp949.csv")

# 2. 분석 범위 지정: 30세 이상, 지역·매출·등급 열만
bd.set_scope(columns=["지역", "매출", "등급"], query="나이 >= 30")

# 3. 기술통계 (수치형 + 범주형 + 차트)
bd.describe()

# 4. 아직 없는 기능 요청 → 알림 + 업데이트 요청 기록
print(bd.request("anova", "지역별 매출 평균 차이 검정"))

# 5. 기능 목록 확인
print(Blueda.capabilities()[["학습영역", "기능", "상태", "예정 단계"]])

# 6. 내보내기
bd.export_excel()
bd.export_csv()
bd.save()
