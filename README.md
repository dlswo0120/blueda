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

## 분석 엔진 (v0.2.0, 1단계)

공공기관·사기업 데이터를 PC 안에서만 분석하는 것을 목표로 합니다. 모든 처리는 로컬에서 이루어지고 외부로 데이터를 보내지 않습니다.

| 기능 | 설명 |
|---|---|
| 파일 자동 판별 | 확장자와 파일 앞부분(매직 바이트)을 함께 확인합니다. CSV는 인코딩(utf-8, cp949 등)과 구분자를 자동으로 찾습니다. Excel은 시트 목록을 읽습니다. Word·PDF는 형식만 판별합니다 (표 추출은 5단계) |
| 분석 범위 지정 | 열 선택, 행 조건(`나이 >= 30`), 행 구간, 결측 행 제외. 원본 데이터는 바뀌지 않습니다 |
| 기술통계 | 수치형(평균·중앙값·표준편차·사분위수·왜도·첨도), 범주형(빈도·비율·최빈값), 히스토그램·박스플롯·빈도 막대 |
| 결과 세션 | 모든 분석은 `[SUCCESS]` / `[FAIL]` / `[UNSUPPORTED]` 한 줄로 기록됩니다. 실패해도 프로그램이 멈추지 않습니다 |
| 미지원 기능 알림 | 아직 없는 분석을 요청하면 필요한 기능과 필요한 학습 내용을 보여주고 `update_requests.csv`에 기록합니다 |
| 내보내기 | Excel(요약·표·차트 시트), CSV(표별 파일, 엑셀 한글 호환) |

```python
from blueda import Blueda

bd = Blueda.from_file("data/매출.csv")             # 형식·인코딩 자동 판별
bd.set_scope(columns=["지역", "매출"], query="나이 >= 30")
bd.describe()                                       # 기술통계 + 차트
bd.request("anova", "지역별 매출 차이")              # 미지원 → 알림 + 요청 기록
Blueda.capabilities()                               # 전체 기능 목록과 개발 단계
bd.export_excel()
```

예제: `python examples/engine_demo.py`

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
