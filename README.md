# BLUEDA

데이터를 받으면 전처리가 필요한지부터 판단하고, 분석에 쓴 코드를 목적 → 코드 → 결과 → 해석 순서로 기록하는 EDA 도우미입니다.

## 주요 기능

| 구분 | 기능 | 설명 |
|---|---|---|
| 기본 | A. 전처리 판단 | 타입, 결측, 중복, 이상치, 범주 불일치, 단위를 항상 같은 순서로 점검합니다 |
| 기본 | B. 분석 로그 | 실행한 코드를 한국어 주석과 함께 `.md`와 `.py`로 저장합니다 |
| 기본 | C. 재현성 기록 | 라이브러리 버전, 랜덤 시드, 데이터 경로와 해시를 `.json`으로 남깁니다 |
| 선택 | E. 출처·이용조건 확인 | 데이터 출처와 라이선스를 기록하고 빠진 항목을 알려줍니다 |
| 선택 | F. 통계 가정 점검 | 정규성, 등분산, 상관 중 원하는 검사만 실행합니다 |
| 선택 | G. 학습 개념 연결 | 분석 단계마다 적용한 개념과 출처를 로그에 표시합니다 |

## 설치 (VS Code)

1. 이 폴더를 VS Code로 엽니다. 추천 확장(Python, Jupyter) 설치 알림이 뜨면 설치합니다.
2. 터미널(`Ctrl + ~`)에서 가상환경을 만들고 켭니다.

   ```bash
   # Windows
   python -m venv .venv
   .venv\Scripts\activate

   # macOS / Linux
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. 패키지를 설치합니다. `-e`는 코드를 고치면 바로 반영되는 개발용 설치입니다.

   ```bash
   pip install -r requirements.txt
   pip install -e .
   ```

4. `Ctrl + Shift + P` → `Python: Select Interpreter` → `.venv`를 선택합니다.
5. 예제를 실행해 봅니다.

   ```bash
   python examples/quickstart.py
   pytest
   ```

## 사용법

```python
from blueda import Blueda, BluedaConfig

config = BluedaConfig(
    check_source_license=True,                  # E
    stat_checks=["normality", "correlation"],   # F: 원하는 검사만
    link_lecture_concepts=True,                 # G
)

bd = Blueda.from_csv("data/my_data.csv", config=config)
bd.check()                          # A: 전처리 판단
bd.set_source(name="...", provider="...", url="...", license="공공누리 1유형", checked_date="2026-11-20")
step = bd.run("지역별 평균", 'print(df.groupby("region")["score"].mean())')
bd.stats(columns=["age", "score"])  # F
bd.save()                           # logs/ 폴더에 저장
```

정식 배포용으로 쓸 때는 `release_config()`로 시작하면 G가 꺼진 상태가 됩니다.

## 폴더 구조

```
blueda/            패키지 본체
examples/          사용 예제
tests/             기능 테스트 (pytest)
logs/              분석 로그 저장 위치 (GitHub에는 올라가지 않음)
data/              원본 데이터 위치 (GitHub에는 올라가지 않음)
```

## 주의사항

- 전처리 판단은 의심 신호를 알려주는 기능입니다. 처리 방법은 결과를 보고 직접 결정해야 합니다.
- 라이선스는 자동으로 확인할 수 없습니다. 데이터 제공처의 원문 조건을 직접 확인해 주세요.
- 상관관계는 인과관계가 아닙니다.
