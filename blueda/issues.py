"""파일의 현재 이슈 목록 (상단 [!] 버튼용).

파일을 열거나 데이터가 바뀌면(날짜 변환 등) 전처리 점검을 다시 돌려 이슈를 모읍니다.
사용자가 이슈를 모른 채 분석하지 않도록 알리는 것이 목적이고, 고치는 것은 사용자가 정합니다.
"""

from dataclasses import dataclass

from .dates import date_candidates
from .preprocess_check import REVIEW_ONLY, check_preprocessing

NEED, REVIEW = "확인 필요", "확인 권장"


@dataclass
class Issue:
    level: str        # 확인 필요 / 확인 권장
    item: str         # 점검 항목 (예: "1. 타입")
    text: str         # 이슈 문장
    action: str = ""  # 바로 가는 동작: "dates"(날짜 변환 창), "check"(점검 결과 보기)


def collect_issues(df, outlier_iqr_k=1.5, missing_warn_ratio=0.05):
    """이슈 목록. 확인 필요가 먼저, 확인 권장이 뒤에 옵니다."""
    report = check_preprocessing(df, None, outlier_iqr_k, missing_warn_ratio)
    dates = set(date_candidates(df))
    out = []
    for item, lines in report["items"].items():
        level = REVIEW if item in REVIEW_ONLY else NEED
        for line in lines:
            col = line.split(":", 1)[0]
            action = "dates" if (col in dates and "날짜" in line) else "check"
            out.append(Issue(level, item, line, action))
    out.sort(key=lambda i: i.level != NEED)
    return out


def summary(issues):
    """버튼 글자와 수준. 이슈가 없으면 ("", "")."""
    if not issues:
        return "", ""
    level = NEED if any(i.level == NEED for i in issues) else REVIEW
    return f"[!] 이슈 {len(issues)}", level
