"""조회 히스토리: 사용자가 "확정한" 동작을 한 줄씩 기록합니다.

기록하는 것: 파일 열기, 필터·범위 적용, 분석 실행, 날짜 변환, 명령, 내보내기
기록하지 않는 것: 데이터 자체, 결과 값, 검색창 입력, 스크롤

용량과 메모리
- 한 줄 약 200~500바이트, 파일 끝에 덧붙이기만 합니다 (전체를 다시 쓰지 않음).
- 화면(메모리)에는 최근 200건만 올립니다.
- 최근 1,000건 또는 90일까지만 보관하고, 프로그램을 시작할 때 오래된 기록을 정리합니다.

값 가림 (기본 켜짐)
- 필터에 고른 값(예: 고객 이름)은 원문 대신 "가림 값"으로 저장합니다.
  가림 값 = 이 PC에만 있는 임의 문자열(salt)을 붙여 만든 SHA-256 앞 16자리입니다.
- 복원할 때는 지금 열린 파일의 값들로 같은 계산을 해서 원래 값을 찾습니다.
  그래서 같은 파일을 열었을 때만 복원되고, 기록 파일만으로는 값을 바로 읽을 수 없습니다.
- 이것은 "보이지 않게 가림"이지 암호화가 아닙니다. 같은 PC의 salt와 후보 값 목록이 있으면 맞춰볼 수 있습니다.
- 직접 입력 조건(query)은 글 전체에 값이 섞일 수 있어 가림 모드에서는 저장하지 않습니다(복원 안 됨).
- 열 이름은 가리지 않습니다 (복원에 필요).
"""

import hashlib
import json
import os
import secrets
from dataclasses import asdict
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

from .limits import HISTORY_MEMORY_LIMIT
from .scope import IN, Filter

MEMORY_LIMIT = HISTORY_MEMORY_LIMIT   # 화면(메모리)에 올리는 최근 기록 수 (limits.py)
KINDS = {"file": "파일", "filter": "필터", "analysis": "분석", "dates": "날짜", "command": "명령", "export": "내보내기"}


def _plain(v):
    """JSON으로 저장할 수 있는 값으로 (numpy 숫자, 날짜 등)."""
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (pd.Timestamp, datetime)):
        return v.isoformat()
    if isinstance(v, (list, tuple)):
        return [_plain(x) for x in v]
    return v


class HistoryStore:
    """조회 히스토리 저장소 (history.jsonl, 한 줄에 기록 하나).

    주요 속성: entries(메모리에 올린 최근 기록), mask(값 가림 여부), max_entries·max_days(보관 상한)
    """
    def __init__(self, folder, max_entries=1000, max_days=90, mask=True):
        """folder에 기록 파일과 salt 파일을 둡니다. 만들 때 오래된 기록을 정리하고 최근 기록만 올립니다."""
        os.makedirs(folder, exist_ok=True)
        self.path = os.path.join(folder, "history.jsonl")
        self.salt_path = os.path.join(folder, "history_salt")
        self.max_entries, self.max_days, self.mask = max_entries, max_days, mask
        self.entries = []                     # 최근 MEMORY_LIMIT건만
        self._salt = None
        self.load()

    # ── 저장·불러오기 ───────────────────────────────────────
    def load(self):
        """파일을 읽어 오래된 기록을 정리하고, 최근 기록만 메모리에 올립니다."""
        if not os.path.exists(self.path):
            self.entries = []
            return
        lines = []
        with open(self.path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    lines.append(json.loads(line))
                except json.JSONDecodeError:
                    continue                  # 깨진 줄은 건너뜀 (강제 종료 중 저장 등)
        kept = self._trim(lines)
        if len(kept) != len(lines):
            self._rewrite(kept)
        self.entries = kept[-MEMORY_LIMIT:]

    def _trim(self, items):
        """보관 기간(max_days)이 지난 기록을 빼고 최근 max_entries건만 남깁니다."""
        cutoff = (datetime.now() - timedelta(days=self.max_days)).isoformat(timespec="seconds")
        items = [e for e in items if e.get("t", "") >= cutoff]
        return items[-self.max_entries:]

    def _rewrite(self, items):
        """정리한 기록으로 파일을 다시 씁니다. 임시 파일에 쓴 뒤 바꿔치기해서 중간에 꺼져도 깨지지 않게 합니다."""
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            for e in items:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        os.replace(tmp, self.path)            # 중간에 꺼져도 기존 파일이 깨지지 않게

    def add(self, kind, text, rows=None, file=None, state=None):
        """기록 한 줄을 파일 끝에 덧붙이고 메모리 목록에도 추가합니다.

        kind: file/filter/analysis/dates/command/export, text: 보일 문구, rows: 남은 행 수, state: 되돌리기용 상태
        """
        e = {"t": datetime.now().isoformat(timespec="seconds"), "kind": kind, "text": text}
        if rows is not None:
            e["rows"] = int(rows)
        if file:
            e["file"] = file
        if state:
            e["state"] = state
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps(e, ensure_ascii=False, default=str) + "\n")
        self.entries.append(e)
        if len(self.entries) > MEMORY_LIMIT:
            del self.entries[0]
        return e

    def clear(self):
        """기록 파일과 메모리 목록을 모두 지웁니다 (salt는 남김)."""
        if os.path.exists(self.path):
            os.remove(self.path)
        self.entries = []

    def size_bytes(self):
        """기록 파일 크기(바이트)."""
        return os.path.getsize(self.path) if os.path.exists(self.path) else 0

    def count(self):
        """파일에 저장된 기록 수."""
        if not os.path.exists(self.path):
            return 0
        with open(self.path, encoding="utf-8") as f:
            return sum(1 for line in f if line.strip())

    # ── 값 가림 ─────────────────────────────────────────────
    @property
    def salt(self):
        """이 PC 전용 임의 문자열. 처음 쓸 때 만들고 파일에 저장합니다 (값 가림에 사용)."""
        if self._salt is None:
            if os.path.exists(self.salt_path):
                with open(self.salt_path, encoding="utf-8") as f:
                    self._salt = f.read().strip()
            else:
                self._salt = secrets.token_hex(16)
                with open(self.salt_path, "w", encoding="utf-8") as f:
                    f.write(self._salt)
        return self._salt

    def hide(self, value):
        """값 → 가림 값 'h:' + SHA-256(salt + 값) 앞 16자리."""
        return "h:" + hashlib.sha256((self.salt + str(value)).encode("utf-8")).hexdigest()[:16]

    def filter_text(self, f):
        """기록에 보일 필터 문구. 가림 모드에서는 고른 값을 개수로만 표시."""
        if self.mask and f.op == IN:
            return f"{f.column} in [값 {len(f.values)}개]"
        return f.label()

    def pack_filters(self, filters):
        """필터 목록을 JSON으로 저장할 수 있게 바꿉니다. 가림 모드면 고른 값(in 조건)을 가림 값으로."""
        out = []
        for f in filters:
            d = {k: _plain(v) for k, v in asdict(f).items()}
            if self.mask and f.op == IN:
                d["values"] = [self.hide(v) for v in f.values]
            out.append(d)
        return out

    def pack_value(self, v):
        """입력값 하나를 저장용으로 (가림 모드면 {'__h': 가림 값})."""
        return {"__h": self.hide(v)} if (self.mask and v is not None) else _plain(v)

    def state(self, filters, query, columns, method=None, params=None, value_params=()):
        """복원에 필요한 상태. value_params: 데이터 값이 들어가는 칸 이름 (가림 대상)."""
        st = {"filters": self.pack_filters(filters), "columns": list(map(str, columns))}
        if query:
            if self.mask:
                st["query_hidden"] = True
            else:
                st["query"] = query
        if method:
            st["method"] = method
            st["params"] = {k: (self.pack_value(v) if k in value_params else _plain(v))
                            for k, v in (params or {}).items()}
        return st

    # ── 복원 ────────────────────────────────────────────────
    def _lookup(self, df, column):
        """지금 파일의 column 값들로 가림 값 → 원래 값 표를 만듭니다."""
        if column not in df.columns:
            return {}
        s = df[column]
        uniq = s.cat.categories if isinstance(s.dtype, pd.CategoricalDtype) else s.dropna().unique()
        return {self.hide(v): v for v in uniq}

    def unpack_filters(self, packed, df):
        """저장된 필터를 지금 파일에 맞게 되살립니다. (필터 목록, 되살리지 못한 이유 목록)"""
        filters, problems = [], []
        for d in packed:
            col = d.get("column", "")
            if col and col not in df.columns and d.get("op") != "notna":
                problems.append(f"'{col}' 열이 지금 파일에 없습니다.")
                continue
            vals = d.get("values", [])
            if d.get("op") == IN and any(str(v).startswith("h:") for v in vals):
                table = self._lookup(df, col)
                found = [table[v] for v in vals if v in table]
                if len(found) < len(vals):
                    problems.append(f"'{col}'의 값 {len(vals) - len(found)}개를 지금 파일에서 찾지 못했습니다.")
                if not found:
                    continue
                vals = found
            filters.append(Filter(column=col, op=d.get("op", IN), values=list(vals), lo=d.get("lo"),
                                  hi=d.get("hi"), columns=d.get("columns") or [], k=d.get("k", 1.5)))
        return filters, problems

    def unpack_params(self, params, df, value_columns):
        """가린 값 칸을 되살립니다. value_columns: {칸 이름: 그 값이 들어 있는 열 이름}"""
        out = {}
        for k, v in (params or {}).items():
            if isinstance(v, dict) and "__h" in v:
                col = value_columns.get(k) or params.get("column")
                table = self._lookup(df, col) if col else {}
                v = table.get(v["__h"])
            out[k] = v
        return out


def same_file_name(entry, current):
    """기록의 파일 이름이 지금 파일과 같은지 (기록에 파일 이름이 없으면 같다고 봄)."""
    return not entry.get("file") or entry.get("file") == current


def describe_entry(e):
    """히스토리 목록 한 줄: 시각 · 종류 · 내용 → 행 수"""
    t = e.get("t", "")
    when = t[11:16] if t[:10] == datetime.now().date().isoformat() else t[5:10].replace("-", "/") + " " + t[11:16]
    rows = f"  → {e['rows']:,}행" if "rows" in e else ""
    return when, KINDS.get(e.get("kind"), e.get("kind", "")), e.get("text", "") + rows
