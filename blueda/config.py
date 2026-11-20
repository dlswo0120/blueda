"""BLUEDA 설정값.

기본 기능(A·B·C)은 항상 동작하고,
선택 기능(E·F·G)은 여기 값으로 켜고 끕니다.
"""

from dataclasses import dataclass, field

# F 옵션에서 고를 수 있는 통계 가정 검사 목록
AVAILABLE_STAT_CHECKS = ("normality", "equal_variance", "correlation")


@dataclass
class BluedaConfig:
    # ---------- 선택 기능 ----------
    check_source_license: bool = True          # E: 데이터 출처·이용조건 확인
    stat_checks: list = field(default_factory=list)  # F: 실행할 통계 검사 (빈 리스트면 실행 안 함)
    link_lecture_concepts: bool = True         # G: 강의 개념 연결 표시 (부캠 기간 True, 출시 시 False)

    # ---------- 기본 기능 세부 설정 ----------
    random_seed: int = 42                      # C: 재현성을 위한 랜덤 시드
    log_dir: str = "logs"                      # B: 로그 저장 폴더
    outlier_iqr_k: float = 1.5                 # A: IQR 이상치 기준 배수 (보통 1.5)
    missing_warn_ratio: float = 0.0            # A: 이 비율을 넘는 결측 컬럼을 '전처리 필요'로 판단
    print_code: bool = True                    # B: 실행한 코드를 콘솔에도 출력할지
    alpha: float = 0.05                        # 가설검정 유의수준 (관례 기준, 바꿀 수 있음)
    z_threshold: float = 3.0                   # |z| 이상값 후보 기준 (관례)
    chart_sample_size: int = 100_000           # 이보다 행이 많으면 차트만 표본으로 그림 (통계는 전체)
    category_max_unique: int = 10              # 숫자 열의 고유값이 이 이하면 '코드로 적힌 범주'일 수 있다고 판단
    dropdown_max_values: int = 20              # 범주형 값이 이 이하면 바로 목록, 넘으면 검색 우선

    def __post_init__(self):
        # [목적] 잘못된 검사 이름이 들어오면 바로 알려주기
        unknown = [c for c in self.stat_checks if c not in AVAILABLE_STAT_CHECKS]
        if unknown:
            raise ValueError(
                f"알 수 없는 stat_checks 값: {unknown}. 사용 가능: {AVAILABLE_STAT_CHECKS}"
            )


def release_config(**overrides) -> BluedaConfig:
    """정식 출시용 기본 설정. G(강의 개념 연결)를 끈 상태로 시작합니다."""
    params = {"link_lecture_concepts": False}
    params.update(overrides)
    return BluedaConfig(**params)
