"""기능 레지스트리: 툴이 할 수 있는 분석과 아직 없는 분석의 목록.

사용자가 아직 없는 기능을 요청하면
  1) 결과 세션 창에 [UNSUPPORTED] 알림을 띄우고
  2) 필요한 기능과 필요한 학습 내용을 보여주고
  3) 업데이트 요청 목록(update_requests.csv)에 기록합니다.
새 기능을 만들면 status를 "available"로 바꾸기만 하면 됩니다.
"""

import csv
import os
from datetime import datetime

from .result import UNSUPPORTED, AnalysisResult

AVAILABLE, PLANNED = "available", "planned"

# key: (학습 영역, 이름, 상태, 예정 단계, 필요한 기능, 필요한 학습 내용)
CAPABILITIES = {
    # 표·차트 만들기 (3단계 다음 순서로 예정)
    "pivot_table":          ("표·차트 만들기", "피벗 표", AVAILABLE, "3+",
                             "행·열·값·집계를 고르는 pivot_table 화면", "집계 함수(개수·합계·평균·중앙값), 롱/와이드 형식"),
    "crosstab":             ("표·차트 만들기", "교차표", AVAILABLE, "3+",
                             "두 범주의 개수·비율 표 (crosstab, 비율 기준 선택)", "행 비율·열 비율·전체 비율의 차이"),
    "chart_builder":        ("표·차트 만들기", "차트 만들기", AVAILABLE, "3+",
                             "종류·X·Y·색 구분을 고르는 차트 화면", "자료 종류에 맞는 차트 고르기"),
    # 0) 데이터 이해
    "variable_types":       ("데이터 이해", "변수 종류 판정 (수치형·범주형·날짜·ID)", AVAILABLE, 1, "", ""),
    "analysis_unit":        ("데이터 이해", "분석 단위 확인 (한 행이 무엇인지)", AVAILABLE, 1, "", ""),
    # 1) 기술통계
    "zscore":               ("기술통계", "z점수 표준화·이상값 후보", AVAILABLE, 1, "", ""),
    "normal_curve":         ("기술통계", "정규분포 곡선 비교 (히스토그램 겹쳐 그리기)", AVAILABLE, 1, "", ""),
    "describe_numeric":    ("기술통계", "수치형 요약 (평균·중앙값·표준편차)", AVAILABLE, 1, "", ""),
    "describe_categorical": ("기술통계", "범주형 요약 (빈도·비율·최빈값)", AVAILABLE, 1, "", ""),
    "histogram":            ("기술통계", "히스토그램", AVAILABLE, 1, "", ""),
    "boxplot":              ("기술통계", "박스플롯", AVAILABLE, 1, "", ""),
    # 2) 추론통계 기초
    "sampling_distribution": ("추론통계", "표본분포 시뮬레이션", AVAILABLE, 2,
                              "부트스트랩 재표본 추출 모듈", "모집단·표본·표본분포, 중심극한정리"),
    "confidence_interval":  ("추론통계", "신뢰구간 추정", AVAILABLE, 2,
                             "평균·비율 신뢰구간 계산 모듈", "표준오차, t분포, 신뢰수준의 의미"),
    "one_sample_ttest":     ("추론통계", "단일표본 t검정 + p값 해석", AVAILABLE, 2,
                             "가설검정 모듈과 p값 해석 문장 생성기", "귀무가설·대립가설, 유의수준, 1종·2종 오류"),
    # 3) 이변량
    "t_test":               ("이변량", "독립표본 t검정 (범주×수치)", AVAILABLE, 2,
                             "두 그룹 평균 비교 모듈 (Student / Welch 자동 선택)", "등분산 가정, Welch 보정"),
    "anova":                ("이변량", "일원분산분석 ANOVA (범주×수치)", AVAILABLE, 2,
                             "세 그룹 이상 평균 비교 모듈 + 사후검정", "F분포, 집단 간·집단 내 분산, 사후검정(Tukey HSD)"),
    "chi_square":           ("이변량", "교차표·카이제곱 검정 (범주×범주)", AVAILABLE, 2,
                             "교차표 생성 + 독립성 검정 모듈", "기대빈도, 자유도, 기대빈도 5 미만 문제"),
    "correlation":          ("이변량", "상관분석 (수치×수치)", AVAILABLE, 1, "", ""),
    "correlation_test":     ("이변량", "상관 검정 (두 변수, p값 포함)", AVAILABLE, 2, "", ""),
    "simple_regression":    ("이변량", "단순회귀 (수치×수치)", AVAILABLE, 2,
                             "최소제곱 회귀 모듈 + 잔차 진단", "회귀계수, 결정계수 R², 잔차 가정"),
    # 4) 다변량
    "multiple_regression":  ("다변량", "다중회귀", AVAILABLE, 2,
                             "다중회귀 모듈 + 다중공선성(VIF) 점검", "편회귀계수, 수정 R², 다중공선성"),
    # 범위 밖 (요청이 오면 알림)
    "logistic_regression":  ("다변량", "로지스틱 회귀 (분류)", PLANNED, None,
                             "이진 분류 회귀 모듈", "오즈비, 로짓 함수, 분류 성능 지표"),
    "time_series":          ("기타", "시계열 분석", PLANNED, None,
                             "날짜 인덱스 처리 + 추세·계절성 분해 모듈", "이동평균, 자기상관, 계절성"),
    "clustering":           ("다변량", "군집 분석", PLANNED, None,
                             "K-means 등 군집 모듈", "거리 척도, 표준화, 군집 수 결정"),
}


def get(key):
    return CAPABILITIES.get(key)


def is_available(key):
    cap = get(key)
    return cap is not None and cap[2] == AVAILABLE


def list_capabilities(status=None):
    """기능 목록을 표 형태(리스트)로 돌려줍니다. status로 걸러볼 수 있습니다."""
    rows = []
    for key, (area, name, st, phase, feature, learning) in CAPABILITIES.items():
        if status and st != status:
            continue
        rows.append({"key": key, "학습영역": area, "기능": name, "상태": st,
                     "예정 단계": f"{phase}단계" if phase else "-", "필요 기능": feature, "필요 학습": learning})
    return rows


def unsupported_notice(key, request_log_dir="logs", user_text=""):
    """아직 없는 기능 요청 → 알림 결과를 만들고 업데이트 요청 목록에 기록합니다."""
    cap = get(key)
    if cap is None:
        area, name, phase, feature, learning = "미분류", key, None, "검토 필요", "검토 필요"
    else:
        area, name, _, phase, feature, learning = cap
    when = f"{phase}단계 예정" if phase else "개발 계획에 없음 (요청 목록에 추가)"
    result = AnalysisResult(
        name=name,
        status=UNSUPPORTED,
        message=f"아직 지원하지 않는 기능입니다 ({when}).",
        metrics={"학습영역": area, "필요 기능": feature, "필요 학습": learning},
        notes=["업데이트 요청 목록(update_requests.csv)에 기록했습니다."],
    )
    _record_request(request_log_dir, key, name, area, user_text)
    return result


def _record_request(log_dir, key, name, area, user_text):
    os.makedirs(log_dir, exist_ok=True)
    path = os.path.join(log_dir, "update_requests.csv")
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8-sig") as f:  # utf-8-sig: 엑셀에서 한글 안 깨짐
        w = csv.writer(f)
        if new:
            w.writerow(["요청시각", "key", "기능", "학습영역", "사용자 입력"])
        w.writerow([datetime.now().isoformat(timespec="seconds"), key, name, area, user_text])
