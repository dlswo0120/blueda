"""분석 메뉴 정의와 실행 전 점검.

화면은 이 목록만 보고 메뉴(방법별·질문별), 설정 줄의 드롭다운, 실행 버튼 상태를 만듭니다.
- 드롭다운에는 각 칸에 맞는 종류의 열만 나옵니다 (그룹 → 범주형, 값 → 수치형 등).
- precheck()가 실행 전에 조건을 확인해서, 맞지 않으면 이유와 대안 분석을 알려줍니다.
"""

from dataclasses import dataclass, field

from .interpret import josa
from .variables import CATEGORICAL, DATETIME, ID, NUMERIC, TEXT, infer_kind

# 칸 종류
COL_NUM, COL_CAT, COL_ANY, COL_MULTI, NUMBER, INT, VALUE = (
    "numeric", "categorical", "any", "multi", "number", "int", "value")


@dataclass
class Param:
    name: str          # 메서드 인자 이름
    label: str         # 화면 표시 이름
    kind: str          # 위 칸 종류
    default: object = None


@dataclass
class Method:
    key: str
    group: str
    label: str
    desc: str
    params: list = field(default_factory=list)
    question: str = ""     # 질문별 보기 문장 (없으면 질문별에 안 나옴)
    available: bool = True


GROUPS = ["표·차트 만들기", "데이터 이해", "기술통계", "추론통계", "이변량", "다변량"]

METHODS = [
    Method("pivot_table", "표·차트 만들기", "피벗 표", "행·열·값·집계를 골라 요약표", available=False),
    Method("crosstab", "표·차트 만들기", "교차표", "두 범주의 개수·비율 표", available=False),
    Method("chart_builder", "표·차트 만들기", "차트", "종류·X·Y를 골라 그리기", available=False),

    Method("variable_types", "데이터 이해", "변수 종류", "열마다 수치·범주 판정"),
    Method("analysis_unit", "데이터 이해", "분석 단위", "한 행이 무엇인지 확인",
           [Param("key_columns", "기준 열", COL_ANY)]),
    Method("check", "데이터 이해", "전처리 점검", "타입·결측·중복·이상치 확인"),

    Method("describe", "기술통계", "요약 통계", "평균·중앙값·빈도", question="데이터가 어떻게 생겼나요?"),
    Method("zscore", "기술통계", "z점수 · 정규분포", "평균에서 얼마나 먼지"),

    Method("sampling_distribution", "추론통계", "표본분포", "표본평균이 어떻게 퍼지는지",
           [Param("column", "값 (수치형)", COL_NUM), Param("sample_size", "표본 크기", INT, 30)]),
    Method("confidence_interval", "추론통계", "신뢰구간", "평균의 범위 추정",
           [Param("column", "값 (수치형)", COL_NUM)], question="평균은 어느 범위에 있나요?"),
    Method("ci_proportion", "추론통계", "비율 신뢰구간", "한 범주의 비율 범위",
           [Param("column", "열 (범주형)", COL_CAT), Param("category", "범주 값", VALUE)]),
    Method("one_sample_ttest", "추론통계", "단일표본 t검정", "기준값과 비교",
           [Param("column", "값 (수치형)", COL_NUM), Param("mu0", "기준값", NUMBER)],
           question="평균이 기준값과 다른가요?"),

    Method("t_test", "이변량", "t검정", "두 그룹 평균 비교",
           [Param("group_col", "그룹 (범주형)", COL_CAT), Param("value_col", "값 (수치형)", COL_NUM)],
           question="두 그룹의 평균이 다른가요?"),
    Method("anova", "이변량", "분산분석", "세 그룹 이상 평균 비교",
           [Param("group_col", "그룹 (범주형)", COL_CAT), Param("value_col", "값 (수치형)", COL_NUM)],
           question="여러 그룹의 평균이 다른가요?"),
    Method("chi_square", "이변량", "카이제곱", "두 범주의 관련성",
           [Param("row_col", "범주 1", COL_CAT), Param("col_col", "범주 2", COL_CAT)],
           question="두 범주가 서로 관련 있나요?"),
    Method("correlation_test", "이변량", "상관 분석", "두 수치가 함께 움직이는지",
           [Param("x", "수치 1", COL_NUM), Param("y", "수치 2", COL_NUM)],
           question="두 수치가 함께 움직이나요?"),
    Method("simple_regression", "이변량", "단순회귀", "한 수치로 다른 수치 설명",
           [Param("x", "설명 변수 (수치형)", COL_NUM), Param("y", "결과 변수 (수치형)", COL_NUM)]),

    Method("multiple_regression", "다변량", "다중회귀", "여러 변수로 하나를 설명",
           [Param("y", "결과 변수 (수치형)", COL_NUM), Param("xs", "설명 변수들", COL_MULTI)],
           question="무엇이 결과에 영향을 주나요?"),
    Method("logistic_regression", "다변량", "로지스틱 회귀", "예/아니오 예측", available=False),
]

BY_KEY = {m.key: m for m in METHODS}

ALLOWED = {
    COL_NUM: {NUMERIC},
    COL_CAT: {CATEGORICAL},
    COL_ANY: {NUMERIC, CATEGORICAL, DATETIME, ID, TEXT},
    COL_MULTI: {NUMERIC, CATEGORICAL},
}


def column_kinds(df, overrides=None, max_categories=10):
    """열 → 종류. 사용자가 지정한 종류(overrides)가 자동 판정보다 우선합니다."""
    overrides = overrides or {}
    return {c: overrides.get(c) or infer_kind(df[c], max_categories=max_categories)[0] for c in df.columns}


def columns_for(param_kind, kinds, selected=None):
    """이 칸의 드롭다운에 보여줄 열 목록. selected를 주면 분석 범위에서 고른 열 안에서만."""
    allowed = ALLOWED.get(param_kind)
    if allowed is None:
        return []
    cols = [c for c, k in kinds.items() if k in allowed]
    if selected:
        cols = [c for c in cols if c in selected]
    return cols


@dataclass
class Check:
    ok: bool
    message: str = ""
    alternative: str = ""   # 대안 분석 key (예: t검정 → 분산분석)


def _name(label_text):
    """'그룹 (범주형)' → '그룹을'. 괄호 설명은 빼고 조사를 붙입니다."""
    return josa(label_text.split(" (")[0], "을/를")


def precheck(key, params, df, kinds):
    """실행 전 점검. df는 분석 범위가 적용된 데이터."""
    m = BY_KEY.get(key)
    if m is None or not m.available:
        return Check(False, "아직 지원하지 않는 기능입니다.")
    for p in m.params:
        v = params.get(p.name)
        if p.kind in (COL_NUM, COL_CAT, COL_ANY) and not v:
            return Check(False, f"{_name(p.label)} 고르세요.")
        if p.kind == COL_MULTI and not v:
            return Check(False, f"{_name(p.label)} 1개 이상 고르세요.")
        if p.kind in (NUMBER, INT, VALUE) and v in (None, ""):
            return Check(False, f"{_name(p.label)} 입력하세요.")
        cols = v if isinstance(v, list) else [v] if p.kind in (COL_NUM, COL_CAT, COL_ANY) else []
        for c in cols:
            if c not in df.columns:
                return Check(False, f"'{c}' 열이 분석 범위에 없습니다. 왼쪽 열 목록에서 선택하세요.")
            if p.kind in ALLOWED and kinds.get(c) not in ALLOWED[p.kind]:
                return Check(False, f"{josa(c, '은/는')} {kinds.get(c)}이라 {p.label.split(' (')[0]} 칸에 쓸 수 없습니다.")
    if len(df) == 0:
        return Check(False, "조건에 맞는 행이 없습니다. 행 조건을 넓혀 주세요.")

    if key in ("t_test", "anova"):
        k = df[params["group_col"]].dropna().nunique()
        if key == "t_test" and k != 2:
            alt = "anova" if k > 2 else ""
            return Check(False, f"{josa(params['group_col'], '은/는')} 그룹이 {k}개라 t검정을 쓸 수 없습니다 (2개 필요).", alt)
        if key == "anova" and k < 2:
            return Check(False, f"{josa(params['group_col'], '은/는')} 그룹이 {k}개입니다. 2개 이상 필요합니다.")
        if key == "anova" and k == 2:
            return Check(True, "그룹이 2개면 t검정과 같은 결론입니다. t검정을 써도 됩니다.", "t_test")
    if key in ("chi_square", "correlation_test", "simple_regression"):
        a, b = [params[p.name] for p in m.params]
        if a == b:
            return Check(False, "서로 다른 두 열을 고르세요.")
    if key == "multiple_regression":
        if params["y"] in params["xs"]:
            return Check(False, "결과 변수를 설명 변수에 같이 넣을 수 없습니다.")
    if key in ("anova", "chi_square"):
        many = [c for c in (params.get("group_col"), params.get("row_col"), params.get("col_col"))
                if c and df[c].nunique() > 50]
        if many:
            return Check(True, f"{many[0]} 범주가 50개를 넘습니다. 결과 표가 매우 길어질 수 있습니다.")
    return Check(True)


def run(bd, key, params):
    """메뉴 key와 칸 값으로 Blueda 메서드를 실행합니다."""
    p = dict(params)
    if key == "describe":
        return bd.describe()
    if key == "check":
        return bd.preprocess_check()
    if key == "ci_proportion":
        return bd.confidence_interval(p["column"], category=p["category"])
    if key == "sampling_distribution":
        p["sample_size"] = int(p.get("sample_size") or 30)
    if key == "one_sample_ttest":
        p["mu0"] = float(p["mu0"])
    if key == "analysis_unit":
        p["key_columns"] = [p["key_columns"]] if isinstance(p["key_columns"], str) else p["key_columns"]
    return getattr(bd, key)(**p)
