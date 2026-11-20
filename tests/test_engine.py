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
