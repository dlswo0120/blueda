"""BLUEDA 메인 클래스. 기능들을 한곳에서 부릅니다."""

import pandas as pd

from .config import BluedaConfig
from .logger import AnalysisLogger
from .preprocess_check import check_preprocessing, format_report
from .reproducibility import record_environment, save_environment, set_seed
from .source_check import SourceInfo, review_source, source_markdown
from .stat_checks import run_stat_checks
from . import descriptive, export, registry, variables
from .loader import load_file
from .result import FAIL, AnalysisResult
from .scope import AnalysisScope


class Blueda:
    """사용 예:

    bd = Blueda.from_csv("data/sample.csv")
    bd.check()                       # A: 전처리 판단
    bd.stats(group_col="region")     # F: 선택한 통계 검사
    bd.save()                        # B·C: 로그와 환경 정보 저장
    """

    def __init__(self, df, config=None, data_path=None, session_name=None):
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
    def set_scope(self, columns=None, query="", row_start=None, row_end=None, dropna=False):
        self.scope = AnalysisScope(columns or [], query, row_start, row_end, dropna)
        sub, _ = self.scope.apply(self.df)  # 잘못된 열 이름이면 여기서 바로 에러
        print(f"[BLUEDA] 분석 범위: {self.scope.describe()} → {len(sub):,}행 × {sub.shape[1]}열")
        return sub

    def scoped(self):
        sub, _ = self.scope.apply(self.df)
        return sub

    # ---------- 결과 세션 ----------
    def _record(self, result, scope_code=""):
        """결과를 세션에 쌓고, 결과 줄을 출력하고, 코드를 로그에 남깁니다."""
        self.results.append(result)
        print(result.session_line())
        if result.code:
            code = f"{scope_code}\n\n{result.code}" if scope_code else result.code
            first_table = next(iter(result.tables.values()), "")
            self.log.log(result.name, code, first_table, result.message)
        return result

    def _run(self, func, **kwargs):
        try:
            sub, scope_code = self.scope.apply(self.df)
            return self._record(func(sub, **kwargs), scope_code)
        except Exception as e:  # 실패해도 툴이 멈추지 않고 FAIL로 기록
            return self._record(AnalysisResult(getattr(func, "__name__", "분석"), FAIL, f"{type(e).__name__}: {e}"))

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
        print(f"[BLUEDA] '{column}' → {kind}로 지정")

    def analysis_unit(self, key_columns, unit_name=""):
        """한 행이 무엇인지(예: 고객 1명) 정하고, 기준 열에 중복이 없는지 확인합니다."""
        if isinstance(key_columns, str):
            key_columns = [key_columns]
        return self._run(variables.check_analysis_unit, key_columns=key_columns, unit_name=unit_name)

    def zscore(self, threshold=3.0):
        return self._run(descriptive.zscores, threshold=threshold, var_types=self.var_types)

    # ---------- 기능 레지스트리 ----------
    def request(self, key, user_text=""):
        """기능 이름(key)으로 분석을 요청합니다. 없는 기능이면 알림 + 업데이트 요청 기록."""
        simple = {"describe_numeric": ("numeric",), "describe_categorical": ("categorical",),
                  "histogram": ("numeric",), "boxplot": ("numeric",)}
        if registry.is_available(key) and key in simple:
            return self.describe(*simple[key])
        if registry.is_available(key) and key in ("variable_types", "zscore", "normal_curve"):
            return self.variable_types() if key == "variable_types" else (
                self.zscore() if key == "zscore" else self.describe("numeric"))
        if key == "analysis_unit":
            return self._record(AnalysisResult("분석 단위 확인", FAIL,
                                               "기준 열이 필요합니다. 예: analysis_unit(['고객ID'], '고객')"))
        if registry.is_available(key) and key == "correlation":
            from .stat_checks import correlation_result
            return self._run(correlation_result)
        return self._record(registry.unsupported_notice(key, self.config.log_dir, user_text))

    @staticmethod
    def capabilities(status=None):
        return pd.DataFrame(registry.list_capabilities(status))

    # ---------- 내보내기 ----------
    def export_csv(self, out_dir=None):
        out_dir = out_dir or f"{self.config.log_dir}/export_{self.log.session_name}"
        paths = export.to_csv(self.results, out_dir)
        print(f"[BLUEDA] CSV {len(paths)}개 저장: {out_dir}")
        return paths

    def export_excel(self, path=None, include_charts=True):
        path = path or f"{self.config.log_dir}/result_{self.log.session_name}.xlsx"
        export.to_excel(self.results, path, include_charts)
        print(f"[BLUEDA] Excel 저장: {path}")
        return path

    # ---------- A ----------
    def check(self):
        self.report = check_preprocessing(
            self.df, self.log, self.config.outlier_iqr_k, self.config.missing_warn_ratio
        )
        print("\n" + format_report(self.report))
        return self.report

    # ---------- E (선택) ----------
    def set_source(self, **kwargs):
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
        if not self.config.link_lecture_concepts:
            return
        self.log.link_lecture(step_no, concept, source)

    # ---------- B·C 저장 ----------
    def save(self):
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
