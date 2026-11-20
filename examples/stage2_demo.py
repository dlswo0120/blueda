"""2단계 예제: 추론통계 · 이변량 · 다변량.

실행: python examples/stage2_demo.py
가상 데이터: 광고비·방문수·지역이 매출에 영향을 주도록 만든 예제입니다 (실제 데이터 아님).
"""

import numpy as np
import pandas as pd

from blueda import Blueda

rng = np.random.default_rng(7)
n = 200
region = rng.choice(["서울", "부산", "대구"], n)
gender = rng.choice(["남", "여"], n)
ad = rng.normal(50, 10, n)
visits = rng.normal(30, 5, n)
df = pd.DataFrame({
    "지역": region, "성별": gender, "광고비": ad.round(1), "방문수": visits.round(1),
    "매출": (20 + 1.5 * ad + 0.8 * visits + np.where(region == "서울", 15, 0) + rng.normal(0, 8, n)).round(1),
    "구매": np.where(gender == "여", rng.choice(["Y", "N"], n, p=[0.7, 0.3]), rng.choice(["Y", "N"], n, p=[0.4, 0.6])),
})

bd = Blueda(df, session_name="stage2_demo")
bd.config.print_code = False          # 콘솔에는 결과 줄만 (코드는 로그 파일에 저장됨)
bd.log.print_code = False

print("\n===== 2) 추론통계 =====")
bd.sampling_distribution("매출", sample_size=30)
bd.confidence_interval("매출", level=0.95)
bd.confidence_interval("구매", category="Y")
bd.one_sample_ttest("매출", mu0=120)

print("\n===== 3) 이변량 =====")
bd.t_test("성별", "매출")                     # 범주(2그룹) × 수치
bd.anova("지역", "매출")                      # 범주(3그룹) × 수치 + Tukey 사후검정
bd.chi_square("성별", "구매")                 # 범주 × 범주
bd.correlation_test("광고비", "매출")          # 수치 × 수치
bd.simple_regression("광고비", "매출")

print("\n===== 4) 다변량 =====")
r = bd.multiple_regression("매출", ["광고비", "방문수", "지역"])
print(r.tables["회귀계수"])

print("\n===== 결과 세션 전체 =====")
for res in bd.results:
    print(res.session_line()[:110])

bd.export_excel()
bd.save()
