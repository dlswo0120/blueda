"""1단계 분석 엔진 테스트: 파일 판별, 분석 범위, 기술통계, 레지스트리, 내보내기."""

import numpy as np
import openpyxl
import pandas as pd
import pytest

from blueda import Blueda, BluedaConfig
from blueda.loader import detect_file
from blueda.result import FAIL, SUCCESS, UNSUPPORTED


@pytest.fixture
def sample_df():
    rng = np.random.default_rng(0)
    return pd.DataFrame({
        "지역": rng.choice(["서울", "부산", "대구"], 60),
        "나이": rng.integers(20, 60, 60),
        "매출": rng.normal(100, 20, 60).round(1),
    })


@pytest.fixture
def cfg(tmp_path):
    return BluedaConfig(log_dir=str(tmp_path / "logs"), print_code=False)


# ---------- 파일 형식 판별 ----------
@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "cp949"])
def test_csv_encoding_detected(tmp_path, sample_df, encoding):
    p = tmp_path / "d.csv"
    sample_df.to_csv(p, index=False, encoding=encoding)
    info = detect_file(str(p))
    assert info.file_type == "csv" and info.supported
    df = pd.read_csv(p, encoding=info.encoding)
    assert "지역" in df.columns  # 한글 헤더가 깨지지 않음


def test_tab_delimiter_detected(tmp_path, sample_df):
    p = tmp_path / "d.tsv"
    sample_df.to_csv(p, index=False, sep="\t")
    assert detect_file(str(p)).delimiter == "\t"


def test_excel_detected_even_with_wrong_extension(tmp_path, sample_df):
    p = tmp_path / "d.xlsx"
    sample_df.to_excel(p, sheet_name="시트A", index=False)
    wrong = tmp_path / "d.dat"
    wrong.write_bytes(p.read_bytes())          # 확장자를 틀리게 바꿔도
    info = detect_file(str(wrong))
    assert info.file_type == "excel" and info.sheets == ["시트A"]  # 내용으로 판별


def test_pdf_detected_but_unsupported(tmp_path, cfg):
    p = tmp_path / "doc.pdf"
    p.write_bytes(b"%PDF-1.4 dummy")
    info = detect_file(str(p))
    assert info.file_type == "pdf" and not info.supported
    assert Blueda.from_file(str(p), config=cfg) is None


# ---------- 분석 범위 ----------
def test_scope_columns_and_query(sample_df, cfg):
    bd = Blueda(sample_df, cfg)
    sub = bd.set_scope(columns=["지역", "매출"], query="나이 >= 40")
    assert list(sub.columns) == ["지역", "매출"]
    assert len(sub) == (sample_df["나이"] >= 40).sum()
    assert len(bd.df) == 60  # 원본은 그대로


def test_scope_wrong_column_raises(sample_df, cfg):
    with pytest.raises(KeyError):
        Blueda(sample_df, cfg).set_scope(columns=["없는열"])


# ---------- 기술통계 ----------
def test_describe_numeric_values(sample_df, cfg):
    bd = Blueda(sample_df, cfg)
    r = bd.describe("numeric", with_charts=False)[0]
    assert r.status == SUCCESS
    t = r.tables["수치형 요약"]
    assert np.isclose(t.loc["매출", "표준편차"], sample_df["매출"].std(ddof=1), atol=1e-4)
    assert np.isclose(t.loc["매출", "중앙값"], sample_df["매출"].median(), atol=1e-4)


def test_describe_categorical_mode_and_ratio(cfg):
    df = pd.DataFrame({"색": ["빨강", "빨강", "파랑", None]})
    r = Blueda(df, cfg).describe("categorical", with_charts=False)[0]
    assert r.tables["범주형 요약"].loc["색", "최빈값"] == "빨강"
    assert np.isclose(r.tables["색 빈도표"]["비율"].sum(), 1.0)


def test_describe_fails_gracefully(cfg):
    r = Blueda(pd.DataFrame({"a": ["x", "y"]}), cfg).describe("numeric")[0]
    assert r.status == FAIL  # 멈추지 않고 FAIL로 기록


def test_charts_created(sample_df, cfg):
    r = Blueda(sample_df, cfg).describe("numeric")[0]
    assert "매출 히스토그램" in r.figures and "매출 박스플롯" in r.figures


# ---------- 레지스트리 ----------
def test_unsupported_request_logged(sample_df, cfg, tmp_path):
    bd = Blueda(sample_df, cfg)
    r = bd.request("anova", "지역별 매출 차이")
    assert r.status == UNSUPPORTED and "필요 학습" in r.metrics
    log = (tmp_path / "logs" / "update_requests.csv").read_text(encoding="utf-8-sig")
    assert "anova" in log and "지역별 매출 차이" in log


def test_unknown_request_logged(sample_df, cfg):
    r = Blueda(sample_df, cfg).request("deep_learning")
    assert r.status == UNSUPPORTED


def test_correlation_respects_scope(sample_df, cfg):
    bd = Blueda(sample_df, cfg)
    bd.set_scope(columns=["매출"])
    assert bd.request("correlation").status == FAIL      # 수치형 1개뿐
    bd.set_scope(columns=["나이", "매출"])
    assert bd.request("correlation").status == SUCCESS


# ---------- 내보내기 ----------
def test_export_excel_and_csv(sample_df, cfg, tmp_path):
    bd = Blueda(sample_df, cfg)
    bd.describe()
    xlsx = bd.export_excel(str(tmp_path / "out.xlsx"))
    sheets = openpyxl.load_workbook(xlsx).sheetnames
    assert sheets[0] == "요약" and "수치형 요약" in sheets and "차트" in sheets
    csvs = bd.export_csv(str(tmp_path / "csv"))
    assert len(csvs) >= 2
    numeric_csv = next(p for p in csvs if "수치형" in p)
    assert "평균" in open(numeric_csv, encoding="utf-8-sig").read()


# ---------- 변수 종류 · 분석 단위 · z점수 ----------
def test_variable_types_detects_coded_category_and_id(cfg):
    rng = np.random.default_rng(1)
    df = pd.DataFrame({
        "고객ID": np.arange(1, 101),                    # 모두 다른 정수 → ID 후보
        "성별코드": rng.choice([1, 2], 100),             # 숫자지만 범주
        "매출": rng.normal(100, 10, 100),                # 수치형
        "가입일": pd.date_range("2025-01-01", periods=100).astype(str),  # 문자열 날짜
        "지역": rng.choice(["서울", "부산"], 100),
    })
    bd = Blueda(df, cfg)
    t = bd.variable_types().tables["변수 종류"]["판정"]
    assert t["고객ID"] == "ID 후보" and t["성별코드"] == "범주형"
    assert t["매출"] == "수치형" and t["가입일"] == "날짜" and t["지역"] == "범주형"


def test_override_changes_describe(cfg):
    df = pd.DataFrame({"코드": [1, 2, 1, 2, 3, 1] * 5, "값": np.arange(30.0)})
    bd = Blueda(df, cfg)
    bd.set_variable_type("코드", "범주형")
    num, cat = bd.describe(with_charts=False)
    assert "코드" not in num.tables["수치형 요약"].index      # 평균을 내지 않음
    assert "코드" in cat.tables["범주형 요약"].index           # 빈도로 요약


def test_analysis_unit(cfg):
    df = pd.DataFrame({"고객ID": [1, 1, 2, 3], "주문번호": [10, 11, 12, 13]})
    bd = Blueda(df, cfg)
    r = bd.analysis_unit("고객ID", "고객")
    assert r.metrics["겹치는 행"] == 2 and r.metrics["한 단위 최대 행 수"] == 2
    assert bd.analysis_unit("주문번호", "주문").metrics["겹치는 행"] == 0


def test_zscore_flags_extreme_value(cfg):
    df = pd.DataFrame({"x": [10.0] * 20 + [11.0] * 20 + [100.0]})
    r = Blueda(df, cfg).zscore(threshold=3)
    assert r.metrics["후보 행 수"] == 1
    z = r.tables["z점수 전체"]["x"]
    assert np.isclose(z.mean(), 0, atol=1e-3)                   # z점수 평균은 0


def test_histogram_has_normal_curve(sample_df, cfg):
    fig = Blueda(sample_df, cfg).describe("numeric")[0].figures["매출 히스토그램"]
    assert len(fig.axes[0].lines) == 1                         # 정규분포 곡선 1개
