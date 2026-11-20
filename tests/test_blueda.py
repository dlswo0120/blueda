import numpy as np
import pandas as pd
import pytest

from blueda import Blueda, BluedaConfig, check_preprocessing, release_config


@pytest.fixture
def dirty_df():
    return pd.DataFrame({
        "city": ["Seoul", "seoul ", "Busan", "Busan", "Busan"],
        "num_str": ["1", "2", "3", "4", "5"],
        "price": ["1,000원", "2,000원", "3,000원", "4,000원", "4,000원"],
        "value": [1.0, 2.0, np.nan, 3.0, 3.0],
    })


def test_detects_all_issue_types(dirty_df):
    df = pd.concat([dirty_df, dirty_df.iloc[[0]]], ignore_index=True)
    report = check_preprocessing(df)
    items = report["items"]
    assert report["needs_preprocessing"]
    assert items["1. 타입"]          # num_str 숫자형 변환 필요
    assert items["2. 결측"]          # value 결측
    assert items["3. 중복"]          # 중복 1행
    assert items["5. 범주 불일치"]    # Seoul / seoul
    assert items["6. 단위"]          # 원


def test_clean_data_needs_no_preprocessing():
    df = pd.DataFrame({"a": [1, 2, 3, 4], "b": ["x", "y", "z", "w"]})
    assert not check_preprocessing(df)["needs_preprocessing"]


def test_logger_records_code_and_result(tmp_path, dirty_df):
    bd = Blueda(dirty_df, BluedaConfig(log_dir=str(tmp_path), print_code=False), session_name="t")
    bd.check()
    no = bd.run("행 수 확인", "print(len(df))")
    assert bd.log.steps[no - 1]["result"] == "5"
    paths = bd.save()
    text = open(paths["log"], encoding="utf-8").read()
    assert "목적" in text or "STEP" in text
    assert "print(len(df))" in open(paths["code"], encoding="utf-8").read()


def test_stat_checks_only_selected(tmp_path):
    df = pd.DataFrame({"x": np.arange(30.0), "y": np.arange(30.0) * 2, "g": ["a", "b"] * 15})
    bd = Blueda(df, BluedaConfig(stat_checks=["correlation"], log_dir=str(tmp_path), print_code=False))
    out = bd.stats(columns=["x", "y"])
    assert list(out) == ["correlation"]


def test_invalid_stat_check_name():
    with pytest.raises(ValueError):
        BluedaConfig(stat_checks=["wrong"])


def test_release_config_turns_off_lecture_links():
    assert release_config().link_lecture_concepts is False
