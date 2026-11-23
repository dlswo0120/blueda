"""E (선택): 데이터 출처·이용조건 확인.

라이선스는 자동으로 알아낼 수 없습니다.
사용자가 데이터 제공처에서 확인한 내용을 기록하고,
포트폴리오 공개 전에 빠진 항목이나 주의할 조건을 알려줍니다.
"""

from dataclasses import asdict, dataclass

# 자주 만나는 라이선스와 주의사항 (최종 확인은 반드시 제공처 원문으로)
KNOWN_LICENSES = {
    "공공누리 1유형": "출처표시 조건. 상업적 이용과 변경 가능",
    "공공누리 2유형": "출처표시 + 상업적 이용 금지",
    "공공누리 3유형": "출처표시 + 변경 금지",
    "공공누리 4유형": "출처표시 + 상업적 이용 금지 + 변경 금지",
    "CC0": "권리 포기. 출처표시 없이 이용 가능 (표시하는 것을 권장)",
    "CC BY 4.0": "출처표시 조건으로 자유 이용",
    "CC BY-SA 4.0": "출처표시 + 2차 저작물도 같은 라이선스로 공개",
    "CC BY-NC 4.0": "출처표시 + 비상업적 이용만 가능",
}


@dataclass
class SourceInfo:
    """데이터 출처 정보: 이름, 제공 기관, URL, 라이선스, 받은 날짜, 메모."""
    name: str                       # 데이터 이름
    provider: str = ""              # 제공 기관/사이트
    url: str = ""                   # 다운로드 주소
    license: str = ""               # 라이선스 (예: "공공누리 1유형")
    commercial_use: str = "미확인"   # 상업적 이용 가능 여부
    redistribution: str = "미확인"   # 원본 재배포(GitHub 업로드) 가능 여부
    checked_date: str = ""          # 확인한 날짜
    note: str = ""


def review_source(info: SourceInfo):
    """빠진 항목과 주의사항을 목록으로 돌려줍니다."""
    warnings = []
    for field_name in ("provider", "url", "license", "checked_date"):
        if not getattr(info, field_name):
            warnings.append(f"'{field_name}' 항목이 비어 있습니다.")
    if info.license and info.license not in KNOWN_LICENSES:
        warnings.append(f"'{info.license}'는 목록에 없는 라이선스입니다. 원문 조건을 직접 확인해 주세요.")
    elif info.license:
        warnings.append(f"{info.license}: {KNOWN_LICENSES[info.license]}")
    if info.redistribution != "가능":
        warnings.append("원본 재배포 가능 여부가 확인되지 않았습니다. GitHub에는 원본 대신 다운로드 링크만 올리는 것을 권장합니다.")
    return warnings


def source_markdown(info: SourceInfo):
    """README에 붙일 수 있는 출처 표기 문단을 만듭니다."""
    d = asdict(info)
    return "\n".join([
        "## 데이터 출처",
        f"- 데이터: {d['name']}",
        f"- 제공: {d['provider'] or '(미기재)'}",
        f"- 링크: {d['url'] or '(미기재)'}",
        f"- 라이선스: {d['license'] or '(미확인)'}",
        f"- 확인일: {d['checked_date'] or '(미기재)'}",
    ])
