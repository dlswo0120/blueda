"""조회 히스토리 테스트: 저장 형식, 용량 상한, 값 가림, 복원."""
import json
import os
from datetime import datetime, timedelta

import pandas as pd

from blueda.history import MEMORY_LIMIT, HistoryStore, describe_entry
from blueda.scope import Filter

DF = pd.DataFrame({"name": ["홍길동", "김철수", "이영희", "박민수"] * 5,
                   "region": pd.Categorical(["서울", "부산"] * 10),
                   "age": range(20, 40)})


def test_add_appends_one_line_each(tmp_path):
    h = HistoryStore(tmp_path)
    h.add("file", "a.csv 열기", rows=20, file="a.csv")
    h.add("filter", "age 25~30", rows=6, file="a.csv")
    lines = open(h.path, encoding="utf-8").read().strip().split("\n")
    assert len(lines) == 2 and json.loads(lines[1])["rows"] == 6
    assert describe_entry(h.entries[-1])[2].endswith("→ 6행")


def test_masked_values_not_in_file_and_restorable(tmp_path):
    h = HistoryStore(tmp_path, mask=True)
    f = Filter("name", "in", values=["홍길동", "이영희"])
    st = h.state([f], "", ["name", "age"])
    h.add("filter", h.filter_text(f), rows=10, file="a.csv", state=st)
    raw = open(h.path, encoding="utf-8").read()
    assert "홍길동" not in raw and "이영희" not in raw           # 원문 값이 파일에 없음
    assert "name in [값 2개]" in raw
    filters, problems = h.unpack_filters(st["filters"], DF)
    assert filters[0].values == ["홍길동", "이영희"] and not problems


def test_mask_off_keeps_plain_values(tmp_path):
    h = HistoryStore(tmp_path, mask=False)
    f = Filter("name", "in", values=["홍길동"])
    st = h.state([f], "age > 30", ["name"])
    assert st["filters"][0]["values"] == ["홍길동"] and st["query"] == "age > 30"


def test_masked_query_not_saved(tmp_path):
    h = HistoryStore(tmp_path, mask=True)
    st = h.state([], "name == '홍길동'", ["name"])
    assert "query" not in st and st["query_hidden"]


def test_restore_reports_missing_values_and_columns(tmp_path):
    h = HistoryStore(tmp_path, mask=True)
    st = h.state([Filter("name", "in", values=["홍길동", "없는사람"]), Filter("gone", "between", lo=1, hi=2)], "", [])
    filters, problems = h.unpack_filters(st["filters"], DF)
    assert filters[0].values == ["홍길동"]
    assert any("1개를 지금 파일에서 찾지 못했습니다" in p for p in problems)
    assert any("'gone' 열이 지금 파일에 없습니다" in p for p in problems)


def test_category_values_and_ranges_restore(tmp_path):
    h = HistoryStore(tmp_path, mask=True)
    st = h.state([Filter("region", "in", values=["부산"]), Filter("age", "between", lo=25, hi=30)], "", [])
    filters, _ = h.unpack_filters(json.loads(json.dumps(st))["filters"], DF)
    assert filters[0].values == ["부산"] and (filters[1].lo, filters[1].hi) == (25, 30)


def test_salt_is_per_install_and_persistent(tmp_path):
    a = HistoryStore(tmp_path / "a")
    b = HistoryStore(tmp_path / "b")
    assert a.hide("홍길동") != b.hide("홍길동")                   # PC마다 다른 가림 값
    assert HistoryStore(tmp_path / "a").hide("홍길동") == a.hide("홍길동")


def test_trim_by_count_and_days_on_load(tmp_path):
    h = HistoryStore(tmp_path, max_entries=50, max_days=90)
    old = (datetime.now() - timedelta(days=120)).isoformat(timespec="seconds")
    with open(h.path, "a", encoding="utf-8") as f:
        for i in range(10):
            f.write(json.dumps({"t": old, "kind": "file", "text": f"old{i}"}) + "\n")
    for i in range(80):
        h.add("filter", f"new{i}")
    h2 = HistoryStore(tmp_path, max_entries=50, max_days=90)
    assert h2.count() == 50                                        # 오래된 10건 + 넘친 30건 정리
    assert all(e["text"].startswith("new") for e in h2.entries)


def test_memory_holds_only_recent(tmp_path):
    h = HistoryStore(tmp_path, max_entries=1000)
    for i in range(MEMORY_LIMIT + 50):
        h.add("filter", f"f{i}")
    assert len(h.entries) == MEMORY_LIMIT and h.count() == MEMORY_LIMIT + 50
    assert h.size_bytes() < (MEMORY_LIMIT + 50) * 300                # 한 줄 300바이트 미만


def test_broken_line_is_skipped(tmp_path):
    h = HistoryStore(tmp_path)
    h.add("file", "ok")
    with open(h.path, "a", encoding="utf-8") as f:
        f.write('{"t": "2026-11-23T10:00:00", "kind": "fil')       # 강제 종료로 잘린 줄
    assert [e["text"] for e in HistoryStore(tmp_path).entries] == ["ok"]


def test_clear(tmp_path):
    h = HistoryStore(tmp_path)
    h.add("file", "x")
    h.clear()
    assert h.count() == 0 and not os.path.exists(h.path)


def test_value_params_masked_and_restored(tmp_path):
    h = HistoryStore(tmp_path, mask=True)
    st = h.state([], "", [], method="ci_proportion", params={"column": "name", "category": "홍길동"},
                 value_params=("category",))
    assert "홍길동" not in json.dumps(st, ensure_ascii=False)
    p = h.unpack_params(st["params"], DF, {"category": "name"})
    assert p == {"column": "name", "category": "홍길동"}
