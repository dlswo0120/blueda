"""BLUEDA 메인 클래스. 기능들을 한곳에서 부릅니다."""

import pandas as pd

from .config import BluedaConfig
from .logger import AnalysisLogger
from .preprocess_check import check_preprocessing, format_report
from .reproducibility import record_environment, save_environment, set_seed
from .source_check import SourceInfo, review_source, source_markdown
from .stat_checks import run_stat_checks


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
