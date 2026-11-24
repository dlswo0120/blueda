"""BLUEDA 메인 클래스. 기능들을 한곳에서 부릅니다."""

import pandas as pd

from .config import BluedaConfig
from .logger import AnalysisLogger
from .preprocess_check import check_preprocessing, format_report
from .reproducibility import record_environment, save_environment, set_seed
from .source_check import SourceInfo, review_source, source_markdown
from .stat_checks import run_stat_checks
from . import bivariate, charts, descriptive, export, inferential, multivariate, registry, variables
from .loader import load_file
from .result import UserFacingError, to_images, FAIL, AnalysisResult
from .scope import AnalysisScope


class Blueda:
    """사용 예:

    bd = Blueda.from_csv("data/sample.csv")
    bd.check()                       # A: 전처리 판단
    bd.stats(group_col="region")     # F: 선택한 통계 검사
    bd.save()                        # B·C: 로그와 환경 정보 저장
    """

    def __init__(self, df, config=None, data_path=None, session_name=None):
        """분석 세션을 만듭니다.

        주요 속성
        - df: 원본 데이터 (분석 범위를 적용해도 바뀌지 않음, 날짜 변환만 직접 바꿈)
        - scope: 분석 범위(열·필터). 각 분석은 scope를 적용한 데이터(sub)로 계산
        - config: 설정값(BluedaConfig)
        - results: 실행한 결과가 순서대로 쌓이는 목록 (결과 세션)
        - log: 목적→코드→결과→해석 로그
        - var_types: 사용자가 직접 지정한 변수 종류 {열: 종류}
        """
        self.df = df
        self.config = config or BluedaConfig()
        self.data_path = data_path
        self.log = AnalysisLogger(self.config.log_dir, self.config.print_code, session_name)
        self.source = None
        self.report = None
        self.file_info = None
        self.scope = AnalysisScope()      # 분석 범위 (기본: 전체)
        self.var_types = {}               # 사용자가 직접 지정한 변수 종류 (열 → 수치형/범주형/...)
        self.results = []                 # 결과 세션: 실행한 분석 결과가 순서대로 쌓임
        set_seed(self.config.random_seed)  # C: 시작할 때 시드 고정
        charts.SAMPLE_N = self.config.chart_sample_size  # 큰 데이터 차트 표본 크기

    @classmethod
    def from_csv(cls, path, config=None, encoding="utf-8", **read_kwargs):
        """CSV를 읽으면서 읽은 코드도 로그 첫 줄에 남깁니다."""
        df = pd.read_csv(path, encoding=encoding, **read_kwargs)
        bd = cls(df, config=config, data_path=path)
        code = f'''# [목적] 원본 데이터 불러오기
import pandas as pd
df = pd.read_csv({path!r}, encoding={encoding!r})   # CSV 파일을 DataFrame으로 읽기
print(df.shape)                                     # (행 수, 열 수)
print(df.head())                                    # 앞 5행 미리보기'''
        bd.log.log("데이터 불러오기", code, f"{df.shape}\n{df.head()}", "")
        return bd

    @classmethod
    def from_file(cls, path, sheet=None, config=None):
        """형식을 자동 판별해서 불러옵니다 (CSV, Excel). Word·PDF는 형식만 판별하고 알림."""
        info, df, code = load_file(path, sheet)
        if df is None:
            print(f"[BLUEDA] {info.summary()}")
            print(f"[UNSUPPORTED] {info.detail}")
            return None
        bd = cls(df, config=config, data_path=path)
        bd.file_info = info
        print(f"[BLUEDA] {info.summary()} · {df.shape[0]:,}행 × {df.shape[1]}열")
        bd.log.log("데이터 불러오기", code, f"{df.shape}", info.summary())
        return bd

    # ---------- 분석 범위 ----------
    def set_scope(self, columns=None, query="", row_start=None, row_end=None, dropna=False, filters=None):
        """분석 범위를 정합니다. 이후 모든 분석은 이 범위의 데이터로 계산합니다.

        인자: columns 쓸 열(비우면 전체), filters 필터 칩 목록(scope.Filter), query pandas query 문법(고급),
              row_start/row_end 행 구간, dropna 고른 열에 결측 있는 행 제외
        """
        self.scope = AnalysisScope(columns=columns or [], filters=filters or [], query=query,
                                   row_start=row_start, row_end=row_end, dropna=dropna)
        sub, _ = self.scope.apply(self.df)  # 잘못된 열 이름이면 여기서 바로 에러
        print(f"[BLUEDA] 분석 범위: {self.scope.describe()} → {len(sub):,}행 × {sub.shape[1]}열")
        return sub

    def scoped(self):
        """분석 범위를 적용한 데이터(DataFrame)를 돌려줍니다."""
        sub, _ = self.scope.apply(self.df)
        return sub

    # ---------- 결과 세션 ----------
    def _record(self, result, scope_code=""):
        """결과를 세션에 쌓고, 결과 줄을 출력하고, 코드를 로그에 남깁니다."""
        if result.figures:
            result.figures = to_images(result.figures)   # 그림 객체 대신 PNG로 보관 (메모리 누적 방지)
        self.results.append(result)
        print(result.session_line())
        if result.code:
            code = f"{scope_code}\n\n{result.code}" if scope_code else result.code
            first_table = next(iter(result.tables.values()), "")
            self.log.log(result.name, code, first_table, result.message)
        return result

    def _run(self, func, **kwargs):
        """분석 함수를 범위 적용 데이터로 실행하고 결과를 세션에 쌓습니다.

        어떤 오류가 나도 프로그램이 멈추지 않도록 FAIL 결과로 바꿔 기록합니다.
        - UserFacingError: 조건이 맞지 않는 경우 → 안내 문장만
        - 그 밖의 오류: '예상하지 못한 오류' + 오류 이름 (원인 파악용)
        """
        try:
            sub, scope_code = self.scope.apply(self.df)
            if len(sub) == 0:   # 필터 결과 0행: 분석마다 다른 오류가 나지 않게 여기서 한 번에 안내 (화면은 실행 전 점검에서도 막음)
                raise UserFacingError("조건에 맞는 행이 없습니다. 행 조건을 넓혀 주세요.")
            result = func(sub, **kwargs)
            note = charts.sample_note(len(sub))
            if result.figures and note and note not in result.notes:
                result.notes.append(note)
            return self._record(result, scope_code)
        except UserFacingError as e:   # 조건이 맞지 않아 계산할 수 없는 경우: 안내 문장만
            return self._record(AnalysisResult(getattr(func, "__name__", "분석"), FAIL, str(e)))
        except Exception as e:  # 예상하지 못한 오류도 툴이 멈추지 않고 FAIL로 기록 (원인 파악용으로 오류 이름 포함)
            return self._record(AnalysisResult(getattr(func, "__name__", "분석"), FAIL,
                                               f"예상하지 못한 오류로 계산하지 못했습니다 ({type(e).__name__}: {e})"))

    # ---------- 표·차트 만들기 ----------
    def pivot_table(self, rows, columns=None, values=None, agg="합계", date_unit="월"):
        """피벗 표. values가 없으면 행 개수를 셉니다. agg: 합계·평균·개수·중앙값·최솟값·최댓값"""
        from . import tables
        return self._run(tables.pivot_table, rows=rows, columns=columns or None, values=values or None,
                         agg=agg, date_unit=date_unit)

    def crosstab(self, rows, columns, normalize="개수", date_unit="월"):
        """교차표. normalize: 개수·행 %·열 %·전체 %"""
        from . import tables
        return self._run(tables.crosstab, rows=rows, columns=columns, normalize=normalize, date_unit=date_unit)

    def chart(self, chart_type, x=None, y=None, color=None, agg="합계", date_unit="월"):
        """차트 만들기. chart_type: 막대·선·산점도·히스토그램·상자그림·상관 히트맵"""
        from . import tables
        return self._run(tables.chart, chart_type=chart_type, x=x or None, y=y or None, color=color or None,
                         agg=agg, date_unit=date_unit)

    # ---------- 1) 기술통계 ----------
    def describe(self, kind="all", with_charts=True):
        """kind: 'numeric' / 'categorical' / 'all'"""
        out = []
        if kind in ("numeric", "all"):
            out.append(self._run(descriptive.describe_numeric, with_charts=with_charts,
                                 iqr_k=self.config.outlier_iqr_k, var_types=self.var_types))
        if kind in ("categorical", "all"):
            out.append(self._run(descriptive.describe_categorical, with_charts=with_charts,
                                 var_types=self.var_types))
        return out

    # ---------- 변수 종류 · 분석 단위 · z점수 ----------
    def variable_types(self):
        """열마다 수치형/범주형/날짜/ID 후보/텍스트를 판정합니다."""
        return self._run(variables.variable_types, overrides=self.var_types)

    def set_variable_type(self, column, kind):
        """자동 판정이 틀렸을 때 직접 지정합니다. 예: set_variable_type("성별코드", "범주형")"""
        if kind not in variables.KINDS:
            raise ValueError(f"kind는 {variables.KINDS} 중 하나여야 합니다.")
        if column not in self.df.columns:
            raise KeyError(column)
        self.var_types[column] = kind
        from .interpret import josa
        print(f"[BLUEDA] '{column}' → {josa(kind, '으로/로')} 지정")

    # ---------- 날짜형 변환 (사용자가 고른 열만) ----------
    def date_candidates(self):
        """날짜 문자열로 보이는 열 목록. 바꿀지는 사용자가 정합니다."""
        from .dates import date_candidates
        return date_candidates(self.df)

    def convert_dates(self, columns):
        """고른 열을 pd.to_datetime으로 바꿉니다. 원본 데이터(self.df)를 바꾸고 로그에 코드를 남깁니다."""
        from .dates import convert_dates
        try:
            return self._record(convert_dates(self.df, list(columns)))
        except Exception as e:
            return self._record(AnalysisResult("날짜형 변환", FAIL, f"{type(e).__name__}: {e}"))

    def analysis_unit(self, key_columns, unit_name=""):
        """한 행이 무엇인지(예: 고객 1명) 정하고, 기준 열에 중복이 없는지 확인합니다."""
        if isinstance(key_columns, str):
            key_columns = [key_columns]
        return self._run(variables.check_analysis_unit, key_columns=key_columns, unit_name=unit_name)

    def zscore(self, threshold=None):
        """z점수 = (값 − 평균) / 표준편차. |z|가 기준(설정 z_threshold, 관례 3)보다 큰 행을 이상값 후보로 보여줍니다."""
        threshold = threshold if threshold is not None else self.config.z_threshold
        return self._run(descriptive.zscores, threshold=threshold, var_types=self.var_types)

    # ---------- 2) 추론통계 ----------
    def sampling_distribution(self, column, sample_size=30, n_samples=1000):
        """표본분포 실험: 크기 sample_size 표본을 n_samples번 뽑아 표본평균의 분포를 그립니다 (중심극한정리 확인)."""
        return self._run(inferential.sampling_distribution, column=column, sample_size=sample_size,
                         n_samples=n_samples, seed=self.config.random_seed)

    def confidence_interval(self, column, level=0.95, category=None):
        """수치형 열이면 평균의 신뢰구간, category를 주면 그 범주 비율의 신뢰구간."""
        if category is not None:
            return self._run(inferential.confidence_interval_proportion, column=column, category=category, level=level)
        return self._run(inferential.confidence_interval_mean, column=column, level=level)

    def one_sample_ttest(self, column, mu0, alternative="two-sided"):
        """단일표본 t검정: 평균이 기준값 mu0과 다른지 검정합니다. alternative: two-sided / greater / less"""
        return self._run(inferential.one_sample_ttest, column=column, mu0=mu0,
                         alpha=self.config.alpha, alternative=alternative)

    # ---------- 3) 이변량 ----------
    def t_test(self, group_col, value_col, groups=None, method="auto", alternative="two-sided"):
        """독립표본 t검정 (그룹 2개). method='auto'면 등분산 검정 결과로 Student/Welch를 고릅니다."""
        return self._run(bivariate.t_test, group_col=group_col, value_col=value_col, groups=groups,
                         alpha=self.config.alpha, method=method, alternative=alternative)

    def anova(self, group_col, value_col, posthoc=True):
        """일원분산분석 (그룹 2개 이상). posthoc=True면 Tukey 사후검정을 붙입니다."""
        return self._run(bivariate.anova, group_col=group_col, value_col=value_col,
                         alpha=self.config.alpha, posthoc=posthoc)

    def chi_square(self, row_col, col_col):
        """카이제곱 독립성 검정 (범주형 2개)."""
        return self._run(bivariate.chi_square, row_col=row_col, col_col=col_col, alpha=self.config.alpha)

    def correlation_test(self, x, y):
        """상관 검정 (수치형 2개): Pearson과 Spearman."""
        return self._run(bivariate.correlation_test, x=x, y=y, alpha=self.config.alpha)

    def simple_regression(self, x, y):
        """단순회귀: x로 y를 설명하는 직선."""
        return self._run(bivariate.simple_regression, x=x, y=y, alpha=self.config.alpha)

    # ---------- 4) 다변량 ----------
    def multiple_regression(self, y, xs, standardize=False):
        """다중회귀: 여러 독립변수 xs로 y를 설명. 범주형은 더미 변수로 바꾸고 VIF(다중공선성)를 함께 봅니다."""
        return self._run(multivariate.multiple_regression, y=y, xs=list(xs),
                         alpha=self.config.alpha, standardize=standardize)

    # ---------- 기능 레지스트리 ----------
    def request(self, key, user_text="", **params):
        """기능 이름(key)으로 분석을 요청합니다. 없는 기능이면 알림 + 업데이트 요청 기록.

        예: request("t_test", group_col="성별", value_col="매출")
        """
        methods = {"sampling_distribution": self.sampling_distribution,
                   "confidence_interval": self.confidence_interval,
                   "one_sample_ttest": self.one_sample_ttest, "t_test": self.t_test, "anova": self.anova,
                   "chi_square": self.chi_square, "correlation_test": self.correlation_test,
                   "simple_regression": self.simple_regression, "multiple_regression": self.multiple_regression,
                   "analysis_unit": self.analysis_unit, "pivot_table": self.pivot_table,
                   "crosstab": self.crosstab, "chart_builder": self.chart}
        if registry.is_available(key) and key in methods:
            import inspect
            try:
                inspect.signature(methods[key]).bind(**params)   # 필요한 값이 다 들어왔는지 먼저 확인
            except TypeError:
                usage = f"{key}{inspect.signature(methods[key])}"
                return self._record(AnalysisResult(registry.get(key)[1], FAIL, f"필요한 값이 빠졌습니다. 사용법: {usage}"))
            return methods[key](**params)
        simple = {"describe_numeric": ("numeric",), "describe_categorical": ("categorical",),
                  "histogram": ("numeric",), "boxplot": ("numeric",)}
        if registry.is_available(key) and key in simple:
            return self.describe(*simple[key])
        if registry.is_available(key) and key in ("variable_types", "zscore", "normal_curve"):
            return self.variable_types() if key == "variable_types" else (
                self.zscore() if key == "zscore" else self.describe("numeric"))
        if registry.is_available(key) and key == "correlation":
            from .stat_checks import correlation_result
            return self._run(correlation_result)
        return self._record(registry.unsupported_notice(key, self.config.log_dir, user_text))

    @staticmethod
    def capabilities(status=None):
        """지원하는 기능 목록(registry)을 표로 돌려줍니다. status로 '지원'/'예정'만 볼 수 있습니다."""
        return pd.DataFrame(registry.list_capabilities(status))

    # ---------- 내보내기 ----------
    def export_csv(self, out_dir=None):
        """지금까지의 결과 표를 CSV 파일들로 저장합니다 (표마다 한 파일, 엑셀에서 한글이 깨지지 않게 utf-8-sig)."""
        out_dir = out_dir or f"{self.config.log_dir}/export_{self.log.session_name}"
        paths = export.to_csv(self.results, out_dir)
        print(f"[BLUEDA] CSV {len(paths)}개 저장: {out_dir}")
        return paths

    def export_excel(self, path=None, include_charts=True):
        """지금까지의 결과를 Excel 한 파일로 저장합니다 (요약 시트 + 표마다 시트 + 차트 시트)."""
        path = path or f"{self.config.log_dir}/result_{self.log.session_name}.xlsx"
        export.to_excel(self.results, path, include_charts)
        print(f"[BLUEDA] Excel 저장: {path}")
        return path

    # ---------- A ----------
    def preprocess_check(self):
        """분석 범위 안에서 전처리 점검 (화면·결과 세션용)."""
        from .preprocess_check import check_result
        return self._run(check_result, outlier_iqr_k=self.config.outlier_iqr_k,
                         missing_warn_ratio=self.config.missing_warn_ratio)

    def check(self):
        """전처리 점검을 실행하고 판단 결과(dict)를 돌려줍니다. 화면에서는 preprocess_check()를 씁니다."""
        self.report = check_preprocessing(
            self.df, self.log, self.config.outlier_iqr_k, self.config.missing_warn_ratio
        )
        print("\n" + format_report(self.report))
        return self.report

    # ---------- E (선택) ----------
    def set_source(self, **kwargs):
        """데이터 출처·라이선스 정보를 기록합니다 (보고서·로그에 출처 표기용)."""
        if not self.config.check_source_license:
            print("[BLUEDA] E(출처·이용조건 확인)이 꺼져 있습니다. config.check_source_license=True로 켜세요.")
            return []
        self.source = SourceInfo(**kwargs)
        warnings = review_source(self.source)
        print("[BLUEDA 출처 확인]")
        for w in warnings:
            print(" -", w)
        return warnings

    # ---------- F (선택) ----------
    def stats(self, columns=None, group_col=None, checks=None):
        """통계 가정 점검(정규성·등분산·상관)을 원하는 것만 골라 실행합니다."""
        checks = checks if checks is not None else self.config.stat_checks
        if not checks:
            print("[BLUEDA] 선택한 통계 검사가 없습니다. config.stat_checks에 원하는 검사를 넣으세요.")
            return {}
        return run_stat_checks(self.df, checks, columns, group_col, self.log)

    # ---------- B: 사용자 코드 기록 ----------
    def run(self, purpose, code, namespace=None, interpretation=""):
        """직접 작성한 분석 코드를 실행하고 로그에 남깁니다. df 변수를 바로 쓸 수 있습니다."""
        ns = namespace if namespace is not None else {"df": self.df, "pd": pd}
        return self.log.run(purpose, code, ns, interpretation)

    # ---------- G (선택) ----------
    def link_lecture(self, step_no, concept, source):
        """분석 단계에 강의 개념을 연결해 로그에 남깁니다 (설정 link_lecture_concepts가 켜져 있을 때)."""
        if not self.config.link_lecture_concepts:
            return
        self.log.link_lecture(step_no, concept, source)

    # ---------- B·C 저장 ----------
    def save(self):
        """분석 로그를 .md(읽기용)·.py(재실행용)·환경 정보 .json으로 저장하고 경로를 돌려줍니다."""
        md, py = self.log.save(include_lecture_links=self.config.link_lecture_concepts)
        env = record_environment(self.config.random_seed, self.data_path)
        env_path = save_environment(env, self.config.log_dir, self.log.session_name)
        paths = {"log": md, "code": py, "env": env_path}
        if self.source is not None:
            src_path = md.replace("log_", "source_")
            with open(src_path, "w", encoding="utf-8") as f:
                f.write(source_markdown(self.source))
            paths["source"] = src_path
        print("[BLUEDA 저장 완료]")
        for k, v in paths.items():
            print(f" - {k}: {v}")
        return paths
