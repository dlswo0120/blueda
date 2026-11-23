"""[!] 파일 이슈 목록 테스트"""
import numpy as np
import pandas as pd

from blueda.dates import convert_dates
from blueda.issues import NEED, REVIEW, collect_issues, summary


def _df():
    rng = np.random.default_rng(0)
    n = 500
    return pd.DataFrame({"date": pd.date_range("2024-01-01", periods=n).strftime("%Y-%m-%d"),
                         "v": np.r_[rng.normal(0, 1, n - 3), [50, 60, 70]],
                         "flag": (rng.random(n) < .03).astype(int)})


def test_issues_order_actions_and_summary():
    issues = collect_issues(_df())
    assert [i.level for i in issues] == sorted([i.level for i in issues], key=lambda x: x != NEED)
    date_issue = next(i for i in issues if i.text.startswith("date:"))
    assert date_issue.level == NEED and date_issue.action == "dates"
    assert any(i.level == REVIEW and i.text.startswith("v:") for i in issues)
    assert not any(i.text.startswith("flag:") for i in issues)          # 0/1 열은 이슈 아님
    assert summary(issues) == (f"[!] 이슈 {len(issues)}", NEED)


def test_issues_update_after_date_conversion():
    df = _df()
    convert_dates(df, ["date"])
    issues = collect_issues(df)
    assert not any(i.action == "dates" for i in issues)
    assert summary(issues)[1] == REVIEW                                  # 이상치만 남음 → 회색


def test_no_issues_hides_button():
    df = pd.DataFrame({"a": np.arange(100) * 1.5, "b": ["x", "y"] * 50})     # 중복·결측·이상치 없음
    assert summary(collect_issues(df)) == ("", "")
