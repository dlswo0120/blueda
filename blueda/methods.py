"""분석 메뉴 정의와 실행 전 점검.

화면은 이 목록만 보고 메뉴(방법별·질문별), 설정 줄의 드롭다운, 실행 버튼 상태를 만듭니다.
- 드롭다운에는 각 칸에 맞는 종류의 열만 나옵니다 (그룹 → 범주형, 값 → 수치형 등).
- precheck()가 실행 전에 조건을 확인해서, 맞지 않으면 이유와 대안 분석을 알려줍니다.
"""

from dataclasses import dataclass, field

from .limits import BAR_TOP_N, MAX_PIVOT_COLUMNS, MAX_SERIES, MIN_VALUES  # 기준값은 limits.py에서
from .interpret import josa
from .variables import CATEGORICAL, DATETIME, ID, NUMERIC, TEXT, infer_kind

# 칸 종류
COL_NUM, COL_CAT, COL_ANY, COL_MULTI, NUMBER, INT, VALUE = (
    "numeric", "categorical", "any", "multi", "number", "int", "value")
COL_GROUP = "group"    # 묶을 기준: 범주형 또는 날짜
COL_XY = "xy"          # 차트 X축: 수치·범주·날짜
CHOICE = "choice"      # 정해진 선택지

COLUMN_KINDS = (COL_NUM, COL_CAT, COL_ANY, COL_GROUP, COL_XY)   # 열 하나를 고르는 칸


@dataclass
class Param:
    """분석 입력칸 하나의 정의.

    name 메서드 인자 이름, label 화면 이름, kind 칸 종류(COL_NUM 등), default 기본값,
    optional 비워도 되는지, choices 선택지, show_if 다른 칸 값에 따라 보이기, date_only 날짜 열을 골랐을 때만 보이기
    """
    name: str          # 메서드 인자 이름
    label: str         # 화면 표시 이름
    kind: str          # 위 칸 종류
    default: object = None
    optional: bool = False         # 비워도 되는 칸 ("없음" 선택 가능)
    choices: tuple = ()            # CHOICE 칸의 선택지
    show_if: dict = None           # {"chart_type": ("막대", "선")}: 다른 칸 값에 따라 보이기
    date_only: bool = False        # 고른 열 중 날짜가 있을 때만 보이기 (날짜 단위)


@dataclass
class Method:
    """분석 하나의 정의: key(고유 이름), group(메뉴 그룹), label·desc(화면 이름·한 줄 설명), params(입력칸), question(질문별 보기 문장), available(지원 여부)."""
    key: str
    group: str
    label: str
    desc: str
    params: list = field(default_factory=list)
    question: str = ""     # 질문별 보기 문장 (없으면 질문별에 안 나옴)
    available: bool = True


AGG_CHOICES = ("합계", "평균", "개수", "중앙값", "최솟값", "최댓값")
DATE_CHOICES = ("일", "주", "월", "분기", "연")
CHART_CHOICES = ("막대", "선", "산점도", "히스토그램", "상자그림", "상관 히트맵")

GROUPS = ["표·차트 만들기", "데이터 이해", "기술통계", "추론통계", "이변량", "다변량"]

METHODS = [
    Method("pivot_table", "표·차트 만들기", "피벗 표", "행·열·값·집계를 골라 요약표",
           [Param("rows", "행 기준", COL_GROUP),
            Param("columns", "열 기준", COL_GROUP, optional=True),
            Param("values", "값 (수치형)", COL_NUM, optional=True),
            Param("agg", "집계", CHOICE, "합계", choices=AGG_CHOICES),
            Param("date_unit", "날짜 단위", CHOICE, "월", choices=DATE_CHOICES, date_only=True)],
           question="그룹별 합계·평균을 표로 보고 싶어요"),
    Method("crosstab", "표·차트 만들기", "교차표", "두 범주의 개수·비율 표",
           [Param("rows", "행 범주", COL_GROUP), Param("columns", "열 범주", COL_GROUP),
            Param("normalize", "표시", CHOICE, "개수", choices=("개수", "행 %", "열 %", "전체 %")),
            Param("date_unit", "날짜 단위", CHOICE, "월", choices=DATE_CHOICES, date_only=True)]),
    Method("chart_builder", "표·차트 만들기", "차트", "종류·X·Y를 골라 그리기",
           [Param("chart_type", "종류", CHOICE, "막대", choices=CHART_CHOICES),
            Param("x", "X", COL_XY, optional=True, show_if={"chart_type": ("막대", "선", "산점도", "히스토그램", "상자그림")}),
            Param("y", "Y (수치형)", COL_NUM, optional=True, show_if={"chart_type": ("막대", "선", "산점도", "상자그림")}),
            Param("color", "색 구분", COL_CAT, optional=True, show_if={"chart_type": ("막대", "선", "산점도", "히스토그램")}),
            Param("agg", "집계", CHOICE, "합계", choices=AGG_CHOICES, show_if={"chart_type": ("막대", "선")}),
            Param("date_unit", "날짜 단위", CHOICE, "월", choices=DATE_CHOICES, date_only=True)],
           question="차트로 그려 보고 싶어요"),

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
    COL_GROUP: {CATEGORICAL, DATETIME},
    COL_XY: {NUMERIC, CATEGORICAL, DATETIME},
}


def visible(param, params, kinds=None, method=None):
    """이 칸을 지금 보여줄지 (차트 종류에 따라, 날짜 열을 골랐는지에 따라).
    method: 이 칸이 속한 분석. 같은 모양의 칸(날짜 단위)이 여러 분석에 있으므로 꼭 넘깁니다."""
    if param.show_if:
        for k, vals in param.show_if.items():
            if params.get(k) not in vals:
                return False
    if param.date_only:
        kinds = kinds or {}
        m = method or next((m for m in METHODS if any(q is param for q in m.params)), None)
        cols = [params.get(p.name) for p in (m.params if m else [])
                if p.kind in COLUMN_KINDS and visible_basic(p, params)]
        return any(c is not None and kinds.get(c) == DATETIME for c in cols)
    return True


def visible_basic(param, params):
    """show_if 조건만 보고 칸을 보일지 (날짜 단위 칸 조건은 제외). 실행·점검에서 '쓰는 칸'을 고를 때 씁니다."""
    return not param.show_if or all(params.get(k) in v for k, v in param.show_if.items())


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
    """실행 전 점검 결과: ok(실행 가능), message(안내 문장, 경고가 없으면 빈 문자열), alternative(대안 분석 키)."""
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
        if not visible_basic(p, params):
            continue
        if p.kind in COLUMN_KINDS and not v and not p.optional:
            return Check(False, f"{_name(p.label)} 고르세요.")
        if p.kind == COL_MULTI and not v:
            return Check(False, f"{_name(p.label)} 1개 이상 고르세요.")
        if p.kind in (NUMBER, INT, VALUE) and v in (None, ""):
            return Check(False, f"{_name(p.label)} 입력하세요.")
        cols = v if isinstance(v, list) else [v] if (p.kind in COLUMN_KINDS and v) else []
        for c in cols:
            if c not in df.columns:
                return Check(False, f"'{c}' 열이 분석 범위에 없습니다. 왼쪽 열 목록에서 선택하세요.")
            if p.kind in ALLOWED and kinds.get(c) not in ALLOWED[p.kind]:
                return Check(False, f"{josa(c, '은/는')} {kinds.get(c)}이라 {p.label.split(' (')[0]} 칸에 쓸 수 없습니다.")
    if len(df) == 0:
        return Check(False, "조건에 맞는 행이 없습니다. 행 조건을 넓혀 주세요.")

    # 값이 있는 행이 너무 적으면 실행 전에 막음 (실행해도 '값이 부족' FAIL만 나오므로)
    need = MIN_VALUES.get(key)
    if need:
        used = [params.get(p.name) for p in m.params
                if p.kind in COLUMN_KINDS and visible_basic(p, params) and params.get(p.name)]
        used += [c for p in m.params if p.kind == COL_MULTI for c in (params.get(p.name) or [])]
        used = [c for c in dict.fromkeys(used) if c in df.columns]
        if used:
            n_ok = int(df[used].notna().all(axis=1).sum())
            if n_ok < need:
                return Check(False, f"고른 열에 모두 값이 있는 행이 {n_ok}개뿐입니다. 이 분석은 {need}개 이상 필요합니다. "
                                    "조건(필터)을 넓히거나 결측을 확인하세요.")

    if key in ("pivot_table", "crosstab", "chart_builder"):
        return _precheck_tables(key, params, df, kinds)

    if key == "chi_square":
        for c in (params["row_col"], params["col_col"]):
            k = df[c].nunique()
            if k < 2:
                return Check(False, f"{josa(c, '은/는')} 지금 조건에서 범주가 {k}개뿐입니다. 카이제곱은 두 열 모두 범주가 2개 이상 필요합니다.")

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


# MAX_PIVOT_COLUMNS, MIN_VALUES 등 기준값은 limits.py에 있습니다.


def _precheck_tables(key, p, df, kinds):
    """표·차트 만들기 실행 전 점검."""
    def n(c):
        """열의 값 종류 수 (줄여 쓰기용)."""
        return df[c].nunique()

    if key == "pivot_table":
        if p.get("columns") and p["columns"] == p["rows"]:
            return Check(False, "행 기준과 열 기준에 서로 다른 열을 고르세요.")
        if p.get("columns") and kinds.get(p["columns"]) != DATETIME and n(p["columns"]) > MAX_PIVOT_COLUMNS:
            return Check(False, f"{josa(p['columns'], '은/는')} 범주가 {n(p['columns'])}개라 표가 너무 넓어집니다. "
                                f"행 기준으로 옮기거나 조건으로 줄이세요 ({MAX_PIVOT_COLUMNS}개 이하).")
        if not p.get("values"):
            return Check(True, "값을 고르지 않아 행 개수를 셉니다.")
        if p.get("agg") == "개수":
            return Check(True, "집계가 '개수'면 값이 비어 있지 않은 행 수를 셉니다.")
        return Check(True)
    if key == "crosstab":
        if p["rows"] == p["columns"]:
            return Check(False, "서로 다른 두 열을 고르세요.")
        big = [c for c in (p["rows"], p["columns"]) if kinds.get(c) != DATETIME and n(c) > MAX_PIVOT_COLUMNS]
        if big:
            return Check(False, f"{josa(big[0], '은/는')} 범주가 {n(big[0])}개라 표가 너무 큽니다. 조건으로 줄이세요 ({MAX_PIVOT_COLUMNS}개 이하).")
        return Check(True, "두 범주가 관련 있는지는 카이제곱 검정으로 확인할 수 있습니다.", "chi_square")

    t, x, y, c = p.get("chart_type"), p.get("x"), p.get("y"), p.get("color")
    kx = kinds.get(x)
    if t == "상관 히트맵":
        nums = [col for col in df.columns if kinds.get(col) == NUMERIC]
        if len(nums) < 2:
            return Check(False, "상관 히트맵은 왼쪽 열 목록에서 수치형 열을 2개 이상 고르면 그립니다.")
        if len(df) < 3:
            return Check(False, f"지금 조건에 맞는 행이 {len(df)}개뿐이라 상관계수를 계산할 수 없습니다 (3개 이상 필요).")
        return Check(True, f"왼쪽에서 고른 수치형 열 {len(nums)}개로 그립니다.")
    if t in ("막대", "선", "산점도", "히스토그램") and not x:
        return Check(False, "X를 고르세요.")
    if t == "막대" and kx == NUMERIC:
        return Check(False, f"{josa(x, '은/는')} 수치형입니다. 막대는 범주·날짜 X에 쓰고, 수치 분포는 히스토그램을 쓰세요.")
    if t == "선" and kx == CATEGORICAL:
        return Check(False, f"{josa(x, '은/는')} 범주형입니다. 선은 날짜·수치 X에 쓰고, 범주 비교는 막대를 쓰세요.")
    if t in ("산점도", "히스토그램") and kx != NUMERIC:
        return Check(False, f"{t}에는 수치형 X가 필요합니다.")
    if t == "산점도":
        if not y:
            return Check(False, "Y를 고르세요.")
        if x == y:
            return Check(False, "X와 Y에 서로 다른 열을 고르세요.")
    if t == "상자그림":
        if not y:
            return Check(False, "Y(수치형)를 고르세요. X는 그룹으로 나눠 볼 때만 고릅니다.")
        if x and kx == NUMERIC:
            return Check(False, "상자그림의 X는 그룹(범주·날짜)이어야 합니다. 비워 두면 Y 하나만 그립니다.")
    if c and c == x:
        return Check(False, "X와 색 구분에 서로 다른 열을 고르세요.")
    msgs = []
    if c and n(c) > MAX_SERIES:
        msgs.append(f"색 구분 범주가 {n(c)}개라 많은 순 {MAX_SERIES - 1}개 + 기타로 묶습니다.")
    if t == "막대" and kx == CATEGORICAL and n(x) > BAR_TOP_N:
        msgs.append(f"X 범주가 {n(x)}개라 값이 큰 {BAR_TOP_N}개만 그립니다.")
    if t in ("막대", "선") and not y:
        msgs.append("Y를 고르지 않아 행 개수를 그립니다.")
    return Check(True, " ".join(msgs))


def run(bd, key, params):
    """메뉴 key와 칸 값으로 Blueda 메서드를 실행합니다."""
    p = dict(params)
    if key in ("pivot_table", "crosstab", "chart_builder"):
        m = BY_KEY[key]
        p = {q.name: p.get(q.name) for q in m.params if visible_basic(q, params)}
        if key == "chart_builder":
            return bd.chart(**p)
        return getattr(bd, key)(**p)
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
