# BLUEDA 코드 구조 안내

직접 고칠 때 어디를 열어야 하는지 정리한 문서입니다. 파일마다 맨 위에 설명이 있고, 모든 함수·클래스에 역할·인자·반환 설명(docstring)이 있습니다.

## 1. 전체 흐름

```
파일 끌어다 놓기
  → loader.detect_file      형식·인코딩 판별
  → loader.load_file        읽기 (20만 행씩, 진행률·취소, 메모리 최적화)
  → methods.column_kinds    열마다 변수 종류 판단 (variables.infer_kind)
  → core.Blueda             분석 엔진 (원본 df + 분석 범위 scope + 결과 세션 results)
  → 화면에서 열·필터 고르기 → scope.AnalysisScope
  → 분석 고르기 → methods.precheck (실행 전 점검)
  → methods.run → Blueda.<분석>() → 분석 함수(bivariate.anova 등)
  → AnalysisResult (지표·표·차트·안내·코드)
  → 결과 탭·결과 세션·로그·히스토리
```

화면(gui)은 엔진을 부르기만 합니다. 통계 계산은 모두 화면 밖(blueda/*.py)에 있어서 파이썬·Colab에서도 같은 결과를 얻습니다.

## 2. 파일 지도

### 엔진 (blueda/)

| 파일 | 하는 일 |
|---|---|
| core.py | 분석 엔진 Blueda: 범위 적용, 분석 실행(_run), 결과 세션, 내보내기·로그 |
| methods.py | 화면에 보이는 분석 목록(METHODS), 입력칸 정의(Param), 실행 전 점검(precheck), 실행 연결(run) |
| limits.py | 판단 기준값 모음 (이상치 제외 기준, 표본 크기, 차트 상한 등) |
| config.py | 설정 창에서 바꾸는 값 (유의수준, IQR 배수 등) |
| loader.py | 파일 판별·읽기·메모리 최적화 |
| variables.py | 변수 종류 판단 (수치형·범주형·날짜·ID 후보·텍스트) |
| scope.py | 분석 범위: 필터(Filter), 범위(AnalysisScope) |
| preprocess_check.py | 전처리 점검 6항목 |
| issues.py | [!] 이슈 목록 (전처리 점검 결과를 이슈로) |
| dates.py | 날짜 문자열 찾기·변환 |
| descriptive.py | 기술통계 (수치형·범주형 요약, z점수) |
| inferential.py | 표본분포, 신뢰구간, 단일표본 t검정 |
| bivariate.py | t검정, 분산분석, 카이제곱, 상관, 단순회귀 |
| multivariate.py | 다중회귀 |
| tables.py | 표·차트 만들기 (피벗 표, 교차표, 차트 6종) |
| charts.py | 차트 공통 (한글 폰트, 표본, 히스토그램·상자그림, 꼬리 긴 분포 처리) |
| interpret.py | 해석 문장 (p값 문장, 효과 크기, 조사 josa) |
| result.py | 결과 객체(AnalysisResult), 차트 PNG 보관(ChartImage), 사용자 안내 오류(UserFacingError) |
| history.py | 조회 히스토리 저장소 (값 가림 포함) |
| logger.py | 분석 로그 (.md, .py) |
| export.py | CSV·Excel 내보내기 |
| registry.py | 기능 목록과 미지원 기능 요청 기록 |
| settings.py | 설정 저장·불러오기 |
| stat_checks.py | 통계 가정 점검 (정규성, 등분산, 상관) |
| reproducibility.py, source_check.py | 재현성 기록, 출처·라이선스 기록 |

### 화면 (blueda/gui/)

| 파일 | 하는 일 |
|---|---|
| app.py | 메인 창: 창 구성·신호 연결, 창 닫기, 상단 바, 화면 모드·설정 |
| window/loading.py | 파일 열기 → 읽기 → 시작 화면 → 분석 화면 시작 |
| window/analysis.py | 분석 범위, 메뉴 선택, 실행 전 점검, 실행·결과 표시 |
| window/issues.py | [!] 이슈 버튼 |
| window/dates.py | 날짜형 변환 창 |
| window/history.py | 조회 히스토리 기록·되돌리기 |
| window/commands.py | 결과 세션 명령, 내보내기 |
| dialogs.py | 설정 창, 열 고르기 창 |
| pages.py | 시작 화면(StartPage), 메인 화면 배치(MainPage) |
| widgets/ | 화면 부품 (base, columns, menu, filters, analysis_bar, results, session) |
| models.py | 데이터 탭 표 모델 (1,000행씩 불러오기) |
| theme.py | 색·글꼴·스타일시트 (라이트/다크) |

## 3. 이걸 바꾸려면 여기를 고치세요

| 바꾸고 싶은 것 | 고칠 곳 |
|---|---|
| 이상치 점검에서 빼는 기준(값 종류 15개 이하) | limits.py `DISCRETE_MAX_UNIQUE` |
| 막대 차트 최대 범주 수, 색 구분 최대 수 | limits.py `BAR_TOP_N`, `MAX_SERIES` |
| 분석별 최소 행 수 | limits.py `MIN_VALUES` |
| 꼬리가 긴 분포 판단 기준 | limits.py `HEAVY_TAIL_RATIO`, `VIEW_QUANTILES` |
| 유의수준·IQR 배수 기본값 | config.py `BluedaConfig` (사용자는 설정 창에서) |
| 설정 창에 항목 추가 | settings.py `EDITABLE` + config.py 필드 |
| 색·글꼴·여백 | gui/theme.py (색 토큰은 파일 위쪽 상수) |
| 차트 색 순서 | tables.py `SERIES_COLORS` (색각 이상 구분 점검을 통과한 순서) |
| 해석 문장 말투 | interpret.py (`interpret_p`, `effect_label`) |
| 메뉴 순서·그룹·설명 | methods.py `GROUPS`, `METHODS` |
| 결과 세션 명령 추가 | gui/window/commands.py `HELP`와 `_command` |
| 전처리 점검 문구 | preprocess_check.py의 `_check_*` 함수 |

## 4. 새 분석을 추가하는 순서 (예: 로지스틱 회귀)

1. **계산 함수**: 알맞은 파일(예: multivariate.py)에 `def logistic_regression(df, y, xs, alpha=0.05)` 작성
   - `AnalysisResult`를 돌려줌: `metrics`(핵심 숫자), `tables`(결과 표), `figures`(matplotlib 그림), `notes`(안내), `code`(재현 코드)
   - 계산할 수 없는 조건이면 `AnalysisResult(..., FAIL, "한국어 이유")`를 돌려주거나 `UserFacingError("이유")`를 냄
   - 값이 모두 같은 열 등은 `constant_message(열)`로 안내 (엉터리 값 방지)
2. **엔진 연결**: core.py `Blueda`에 메서드 추가 → `return self._run(multivariate.logistic_regression, y=y, xs=xs, alpha=self.config.alpha)`
3. **화면 연결**: methods.py `METHODS`에 `Method("logistic_regression", "다변량", "로지스틱 회귀", "한 줄 설명", [Param(...)])` (이미 준비 중으로 있으면 `available=False`를 지우고 params 채우기). 실행 연결은 `run()`이 자동으로 같은 이름의 Blueda 메서드를 부름 (이름이 다르거나, 숫자 입력칸처럼 글자로 넘어오는 값을 숫자로 바꿔야 하면 `run`에 분기 추가)
4. **실행 전 점검**: 필요하면 methods.py `precheck`에 조건 추가, 최소 행 수는 limits.py `MIN_VALUES`
5. **기능 목록**: registry.py `CAPABILITIES` 상태를 AVAILABLE로
6. **테스트**: scipy·statsmodels로 직접 계산한 값과 비교하는 테스트 + tests/test_robustness.py `CASES`에 추가 (이상 데이터 7종과 코드 로그 재실행을 자동으로 검사)

## 5. 지켜야 할 규칙 (어기면 실제로 문제가 났던 것들)

- **작업 스레드 참조**: 실행 중인 `Worker`를 담은 변수를 덮어쓰면 프로그램이 강제 종료됩니다. 뒤 작업은 `_bg_workers`처럼 끝날 때까지 참조를 잡아 두세요.
- **스레드 중 데이터 변경 금지**: 분석 스레드가 도는 동안 `self.df`를 바꾸지 마세요 (날짜 변환은 이 이유로 막음).
- **위젯 지우기**: 칩·입력칸을 지울 때는 `hide()` → `setParent(None)` → `deleteLater()` 순서로. `deleteLater()`만 하면 잔상이 남습니다.
- **필터 유지**: 데이터 내용만 바뀌면 `FilterBar.update_data`를 쓰세요. `set_data`는 새 파일용이라 필터를 지웁니다.
- **집계는 전체, 그림만 표본**: 표·지표·통계값은 전체 데이터로 계산하고, 점을 하나하나 그리는 차트만 `charts.sample`로 표본을 씁니다.
- **차트 메모리**: 결과에 담긴 그림은 세션에 쌓일 때 PNG(ChartImage)로 바뀝니다. 그림 객체를 따로 들고 있지 마세요.
- **같은 숫자를 두 곳에 쓰지 않기**: 기준값은 limits.py에서 가져다 씁니다.
- **코드 로그는 실행 가능해야 함**: `result.code`는 `sub`(범위 적용 데이터)로 그대로 실행돼야 합니다. tests/test_robustness.py가 모든 분석을 다시 실행해 확인합니다.
- **한국어 조사**: 열 이름 뒤 조사는 `interpret.josa(이름, "을/를")`로. 영어 이름은 받침을 알 수 없어 "을(를)"로 나옵니다.

## 6. 테스트

```bash
pytest -q                                   # 전체 (실습 데이터 없으면 해당 테스트는 건너뜀)
BLUEDA_TEST_DATA=C:\경로\testdata pytest -q  # 실습 데이터 비교 포함 (ai4i2020.csv, superstore.csv)
pytest tests/test_robustness.py -q          # 이상 데이터·코드 로그 재실행
```

| 테스트 파일 | 확인하는 것 |
|---|---|
| test_blueda.py, test_engine.py, test_stage2.py, test_stage3_engine.py | 엔진 기능, scipy·statsmodels와 같은 값인지 |
| test_v041.py | 전처리 점검 오판 수정 사항 |
| test_tables.py | 피벗 표·교차표·차트 (pandas와 같은 값인지) |
| test_issues.py, test_history.py | 이슈 목록, 히스토리 저장·가림·복원 |
| test_robustness.py | 이상 데이터 7종 × 분석 23종, 코드 로그 재실행, 차트 PNG 보관 |
| test_practice_data.py | 실습 파일로 pandas·numpy 직접 계산값과 비교 |
| test_gui.py | 화면 동작 (pytest-qt) |
