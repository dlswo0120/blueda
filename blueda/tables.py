"""표·차트 만들기: 피벗 표, 교차표, 차트.

원칙
- 집계(합계·평균·개수)는 항상 전체 데이터로 계산합니다. 표본은 점을 하나하나 그리는 차트(산점도·히스토그램·상자그림)에만 씁니다.
- 날짜 열은 고른 단위(일·주·월·분기·연)로 묶습니다. 글자로 저장된 날짜도 그 자리에서 날짜로 읽어 묶습니다(원본은 바꾸지 않음).
- 모든 차트 결과에는 그 차트를 그린 집계표를 같이 남깁니다 (색만으로 읽지 않도록, 표로도 확인 가능).
- 실행 코드는 pandas 코드로 남겨 Colab 등에서 그대로 재현할 수 있게 합니다.
"""

import numpy as np
import pandas as pd

from . import charts
from .limits import (BAR_TOP_N, BOX_MAX_GROUPS, HIST_MAX_BINS, LINE_MARKERS_MAX, LINE_NUMERIC_BIN_FROM,  # 기준값
                     LINE_NUMERIC_BINS, MAX_PIVOT_COLUMNS, MAX_SERIES, VIEW_QUANTILES)
from .result import SUCCESS, AnalysisResult, UserFacingError
from .safedate import to_dates

DATE_UNITS = {"일": "D", "주": "W", "월": "M", "분기": "Q", "연": "Y"}
AGGS = {"합계": "sum", "평균": "mean", "개수": "count", "중앙값": "median", "최솟값": "min", "최댓값": "max"}
NORMALIZE = {"개수": False, "행 %": "index", "열 %": "columns", "전체 %": "all"}
CHART_TYPES = ["막대", "선", "산점도", "히스토그램", "상자그림", "상관 히트맵"]

# 여러 계열 색 (밝은 배경에서 색각 이상 구분 점검 통과). 순서대로 쓰고 돌려쓰지 않습니다.
SERIES_COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"]
OTHER_COLOR = "#9AA3AF"
TOTAL = "전체"


# ── 공통 도우미 ──────────────────────────────────────────────
def is_date_like(s):
    """날짜 열인지: 이미 날짜형이거나, 글자인데 날짜처럼 읽히면 True."""
    if pd.api.types.is_datetime64_any_dtype(s):
        return True
    if s.dtype == object or isinstance(s.dtype, pd.CategoricalDtype) or pd.api.types.is_string_dtype(s):
        from .variables import DATETIME, infer_kind
        return infer_kind(s)[0] == DATETIME
    return False


def group_key(df, col, date_unit="월"):
    """묶을 기준 값과 그 코드. 날짜는 단위별 기간(예: 2024-03)으로 바꿉니다."""
    s = df[col]
    if is_date_like(s):
        unit = DATE_UNITS.get(date_unit, "M")
        if pd.api.types.is_datetime64_any_dtype(s):
            expr = f"sub[{col!r}].dt.to_period({unit!r})"
        else:
            s = to_dates(s.astype(str) if isinstance(s.dtype, pd.CategoricalDtype) else s)
            expr = f"pd.to_datetime(sub[{col!r}], errors='coerce').dt.to_period({unit!r})"
        return s.dt.to_period(unit).astype(str).where(s.notna()), expr, True
    if isinstance(s.dtype, pd.CategoricalDtype):
        s = s.cat.remove_unused_categories()
    return s, f"sub[{col!r}]", False


def _agg_code(agg):
    """한국어 집계 이름 → pandas 집계 이름 (예: '합계' → 'sum')."""
    return AGGS.get(agg, "sum")


def _round(t):
    """표 숫자를 소수 4자리로 반올림 (표가 아니면 그대로)."""
    return t.round(4) if hasattr(t, "round") else t


# ── 1. 피벗 표 ───────────────────────────────────────────────
def pivot_table(df, rows, columns=None, values=None, agg="합계", date_unit="월"):
    """행·열·값·집계로 요약표. 값이 없으면 행 개수를 셉니다."""
    if values is None:
        agg = "개수"
    func = _agg_code(agg)
    r, r_expr, r_date = group_key(df, rows, date_unit)
    tmp = pd.DataFrame({"__r": r})
    lines = ["# [목적] 피벗 표: 행·열 기준으로 묶어 요약"]
    lines.append(f"rows = {r_expr}")
    if columns:
        c, c_expr, _ = group_key(df, columns, date_unit)
        tmp["__c"] = c
        lines.append(f"cols = {c_expr}")
        if c.nunique() > MAX_PIVOT_COLUMNS:
            raise UserFacingError(f"'{columns}' 범주가 {c.nunique()}개라 표가 너무 넓습니다 ({MAX_PIVOT_COLUMNS}개 이하). 행과 열을 바꾸거나 조건으로 줄이세요.")
    if values is not None:
        tmp["__v"] = df[values]

    tmp = tmp.dropna(subset=["__r"] + (["__c"] if columns else []))
    if columns:
        if values is None:
            table = pd.crosstab(tmp["__r"], tmp["__c"], margins=True, margins_name=TOTAL)
            lines.append(f"table = pd.crosstab(rows, cols, margins=True, margins_name={TOTAL!r})")
        else:
            table = pd.pivot_table(tmp, index="__r", columns="__c", values="__v", aggfunc=func,
                                   margins=True, margins_name=TOTAL, observed=True)
            lines.append(f"table = pd.pivot_table(sub.assign(_r=rows, _c=cols), index='_r', columns='_c', "
                         f"values={values!r}, aggfunc={func!r}, margins=True, margins_name={TOTAL!r}, observed=True)")
    else:
        g = tmp.groupby("__r", observed=True)
        col_name = f"{values} {agg}" if values is not None else "개수"
        series = g.size() if values is None else g["__v"].agg(func)
        total = len(tmp) if values is None else tmp["__v"].agg(func)
        table = series.to_frame(col_name)
        table.loc[TOTAL] = total
        lines.append("table = sub.groupby(rows, observed=True)" +
                     (".size()" if values is None else f"[{values!r}].agg({func!r})"))
    table.index.name = rows
    if columns:
        table.columns.name = columns

    notes = []
    if agg == "평균" and values is not None:
        notes.append("'전체' 칸은 해당 행·열 전체 데이터의 평균입니다. 그룹 평균들을 다시 평균 낸 값이 아닙니다.")
    if r_date:
        notes.append(f"'{rows}'는 {date_unit} 단위로 묶었습니다.")
    n_missing = len(df) - len(tmp)
    if n_missing:
        notes.append(f"기준 열이 비어 있는 {n_missing:,}행은 표에서 빠졌습니다.")
    shape = f"{table.shape[0] - 1}행" + (f" × {table.shape[1] - 1}열" if columns else "")
    return AnalysisResult(
        "피벗 표", SUCCESS,
        f"{rows}" + (f" × {columns}" if columns else "") + f" 기준 {values or '행'} {agg} ({shape})",
        metrics={"행 기준": rows, "열 기준": columns or "-", "값": values or "(행 개수)", "집계": agg},
        tables={"피벗 표": _round(table)}, notes=notes, code="\n".join(lines))


# ── 2. 교차표 ────────────────────────────────────────────────
def crosstab(df, rows, columns, normalize="개수", date_unit="월"):
    """두 범주의 개수 또는 비율 표. 비율은 % 단위."""
    r, r_expr, _ = group_key(df, rows, date_unit)
    c, c_expr, _ = group_key(df, columns, date_unit)
    norm = NORMALIZE.get(normalize, False)
    if not (r.notna() & c.notna()).any():   # 두 열에 함께 값이 있는 행이 없으면 빈 표가 되어 '전체' 칸을 찾지 못함
        raise UserFacingError(f"{rows}와 {columns}에 함께 값이 있는 행이 없어 교차표를 만들 수 없습니다.")
    counts = pd.crosstab(r, c, margins=True, margins_name=TOTAL)
    counts.index.name, counts.columns.name = rows, columns
    lines = ["# [목적] 교차표: 두 범주를 함께 세기",
             f"rows, cols = {r_expr}, {c_expr}",
             f"counts = pd.crosstab(rows, cols, margins=True, margins_name={TOTAL!r})"]
    tables = {}
    if norm:
        pct = pd.crosstab(r, c, normalize=norm, margins=True, margins_name=TOTAL) * 100
        pct.index.name, pct.columns.name = rows, columns
        tables[f"교차표 ({normalize})"] = pct.round(1)
        lines.append(f"pct = pd.crosstab(rows, cols, normalize={norm!r}, margins=True) * 100   # {normalize}")
    tables["교차표 (개수)"] = counts
    basis = {"index": "행마다 합이 100%", "columns": "열마다 합이 100%", "all": "전체 합이 100%"}
    notes = []
    if norm:
        notes.append(f"{normalize}: {basis[norm]}입니다.")
    notes.append("두 범주가 서로 관련 있는지 확인하려면 '카이제곱' 검정을 이어서 실행하세요.")
    return AnalysisResult(
        "교차표", SUCCESS,
        f"{rows} × {columns} ({counts.shape[0] - 1}×{counts.shape[1] - 1}, {normalize})",
        metrics={"행 범주 수": counts.shape[0] - 1, "열 범주 수": counts.shape[1] - 1,
                 "전체 행 수": int(counts.loc[TOTAL, TOTAL])},
        tables=tables, notes=notes, code="\n".join(lines))


# ── 3. 차트 ──────────────────────────────────────────────────
def _legend(ax, title, n, **kw):
    """범례는 그림 영역 위쪽 바깥에 가로로 (막대·점을 가리지 않게)."""
    ax.legend(title=title, fontsize=8, title_fontsize=8, frameon=False, ncol=min(4, n),
              loc="lower left", bbox_to_anchor=(0, 1.01), borderaxespad=0, alignment="left", **kw)


def _comma_axis(axis):
    """축 숫자에 천 단위 쉼표 (40000 → 40,000)"""
    from matplotlib.ticker import FuncFormatter
    axis.set_major_formatter(FuncFormatter(lambda v, _: f"{v:,.0f}" if abs(v) >= 1000 else f"{v:g}"))


def heavy_tail(x):
    """charts.heavy_tail과 같음 (차트 공통 기준)."""
    return charts.heavy_tail(x)


def _style(ax, title, xlabel="", ylabel=""):
    """차트 공통 모양: 왼쪽 정렬 제목(범례가 위에 있으면 간격을 둠), 옅은 가로 격자, 천 단위 쉼표 축."""
    has_legend = ax.get_legend() is not None
    ax.set_title(title, loc="left", fontsize=11, pad=44 if has_legend else 6)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.grid(axis="y", color="#E5E7EB", linewidth=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(colors="#4B5563", labelsize=9)
    if ax.get_yscale() == "linear":
        _comma_axis(ax.yaxis)


def _limit_series(keys_series, weights=None, k=MAX_SERIES):
    """색 구분 계열이 많으면 상위 k-1개 + '기타'."""
    counts = keys_series.value_counts() if weights is None else weights
    if len(counts) <= k:
        return keys_series, None
    keep = counts.index[: k - 1]
    out = keys_series.astype(object).where(keys_series.isin(keep), "기타")
    return out, f"색 구분 범주가 {len(counts)}개라 많은 순 {k - 1}개만 보이고 나머지는 '기타'로 묶었습니다."


def _colors(names):
    """계열 이름 순서대로 색을 줍니다 ('기타'는 회색). 같은 순서면 항상 같은 색입니다."""
    cols, i = [], 0
    for n in names:
        if n == "기타":
            cols.append(OTHER_COLOR)
        else:
            cols.append(SERIES_COLORS[i % len(SERIES_COLORS)])
            i += 1
    return cols


def chart(df, chart_type, x=None, y=None, color=None, agg="합계", date_unit="월", top_n=BAR_TOP_N):
    """고른 종류의 차트를 그립니다. 차트를 그린 집계표도 함께 돌려줍니다."""
    fn = {"막대": _bar, "선": _line, "산점도": _scatter, "히스토그램": _hist,
          "상자그림": _box, "상관 히트맵": _heatmap}[chart_type]
    fig, table, code, notes, msg = fn(df, x=x, y=y, color=color, agg=agg, date_unit=date_unit, top_n=top_n)
    import matplotlib.pyplot as plt
    fig.tight_layout()
    plt.close(fig)
    return AnalysisResult(
        f"차트: {chart_type}", SUCCESS, msg,
        metrics={k: v for k, v in {"차트": chart_type, "X": x, "Y": y, "색 구분": color}.items() if v},
        tables={"차트 데이터": table}, figures={f"{chart_type} 차트": fig},
        notes=notes, code="# [목적] " + chart_type + " 차트\n" + code)


def _aggregate(df, keys, y, agg, names=None):
    """keys(Series 목록)로 묶어 y를 집계. y가 없으면 개수. names: 결과 표에 보일 기준 열 이름."""
    g = pd.DataFrame({f"__k{i}": k for i, k in enumerate(keys)})
    if y is not None:
        g["__y"] = df[y]
    g = g.dropna(subset=[f"__k{i}" for i in range(len(keys))])
    grp = g.groupby([f"__k{i}" for i in range(len(keys))], observed=True)
    out = grp.size() if y is None else grp["__y"].agg(_agg_code(agg))
    out.index.names = names or [k.name for k in keys]
    return out


def _bar(df, x, y, color, agg, date_unit, top_n):
    """막대 차트: X(범주·날짜)별 Y 집계. 범주면 큰 값부터 정렬하고 상위 top_n개만, 색 구분이 있으면 묶음 막대."""
    xs, x_expr, x_date = group_key(df, x, date_unit)
    ylabel = f"{y} {agg}" if y else "개수"
    notes = []
    if color:
        cs, c_expr, _ = group_key(df, color, date_unit)
        cs, note = _limit_series(cs)
        notes += [note] if note else []
        table = _aggregate(df, [xs, cs], y, agg, [x, color]).unstack(fill_value=0)
    else:
        table = _aggregate(df, [xs], y, agg, [x]).to_frame(ylabel)
    if table.empty:
        raise UserFacingError(f"{x}에 값이 있는 행이 없어 막대를 그릴 수 없습니다.")
    if not x_date:
        table = table.loc[table.sum(axis=1).sort_values(ascending=False).index]   # 큰 값부터
    if len(table) > top_n:
        notes.append(f"'{x}' 범주가 {len(table)}개라 값이 큰 {top_n}개만 그렸습니다. 전체는 차트 데이터 표에 있습니다.")
    plot = table.head(top_n) if not x_date else table
    fig, ax = charts.new_figure(7.5, 4.2)
    cols = _colors(plot.columns)
    if color:
        plot.plot.bar(ax=ax, color=cols, width=0.8, edgecolor="white", linewidth=1)
        _legend(ax, color, len(cols))
    else:
        ax.bar(plot.index.astype(str), plot.iloc[:, 0], color=charts.PRIMARY, width=0.7, edgecolor="white")
    ax.tick_params(axis="x", rotation=45 if len(plot) > 6 else 0)
    for lab in ax.get_xticklabels():
        lab.set_ha("right" if len(plot) > 6 else "center")
    _style(ax, f"{x}별 {ylabel}", x, ylabel)
    code = (f"key = {x_expr}\n" + (f"color = {c_expr}\n" if color else "")
            + f"table = sub.groupby([key{', color' if color else ''}], observed=True)"
            + (".size()" if y is None else f"[{y!r}].agg({_agg_code(agg)!r})")
            + (".unstack(fill_value=0)" if color else ".to_frame()") + "\n"
            + ("table = table.loc[table.sum(axis=1).sort_values(ascending=False).index]   # 큰 값부터\n" if not x_date else "")
            + f"table.head({top_n}).plot.bar()")
    return fig, _round(table), code, notes, f"{x}별 {ylabel} 막대 ({len(table)}개 범주)"


def _line(df, x, y, color, agg, date_unit, top_n):
    """선 차트: X(날짜·수치) 순서대로 Y 집계. 날짜는 단위별로 묶고, 값 종류가 많은 수치 X는 구간으로 묶습니다."""
    xs, x_expr, x_date = group_key(df, x, date_unit)
    ylabel = f"{y} {agg}" if y else "개수"
    notes = []
    if not x_date and pd.api.types.is_numeric_dtype(df[x]) and df[x].nunique() > LINE_NUMERIC_BIN_FROM:
        xs = pd.cut(df[x], LINE_NUMERIC_BINS)
        x_expr = f"pd.cut(sub[{x!r}], {LINE_NUMERIC_BINS})"
        notes.append(f"'{x}' 값 종류가 많아 50개 구간으로 묶었습니다.")
    if color:
        cs, c_expr, _ = group_key(df, color, date_unit)
        cs, note = _limit_series(cs)
        notes += [note] if note else []
        table = _aggregate(df, [xs, cs], y, agg, [x, color]).unstack()
    else:
        table = _aggregate(df, [xs], y, agg, [x]).to_frame(ylabel)
    table = table.sort_index()
    if table.empty:
        raise UserFacingError(f"{x}에 값이 있는 행이 없어 선을 그릴 수 없습니다.")
    fig, ax = charts.new_figure(7.5, 4.2)
    labels = table.index.astype(str)
    pos = np.arange(len(table))
    for col, cl in zip(table.columns, _colors(table.columns)):
        ax.plot(pos, table[col].to_numpy(dtype=float), color=cl if color else charts.PRIMARY,
                linewidth=2, marker="o" if len(table) <= LINE_MARKERS_MAX else None, markersize=4, label=str(col))
    step = max(1, len(pos) // 12)
    ax.set_xticks(pos[::step])
    ax.set_xticklabels(labels[::step], rotation=45 if len(pos) > 6 else 0, ha="right" if len(pos) > 6 else "center")
    if color:
        _legend(ax, color, table.shape[1])
    if (table.min(numeric_only=True).min() or 0) >= 0:
        ax.set_ylim(bottom=0)
    _style(ax, f"{x}에 따른 {ylabel}", x + (f" ({date_unit})" if x_date else ""), ylabel)
    code = (f"key = {x_expr}\n" + (f"color = {c_expr}\n" if color else "")
            + f"table = sub.groupby([key{', color' if color else ''}], observed=True)"
            + (".size()" if y is None else f"[{y!r}].agg({_agg_code(agg)!r})")
            + (".unstack()" if color else "") + ".sort_index()\ntable.plot.line(marker='o')")
    return fig, _round(table), code, notes, f"{x}에 따른 {ylabel} 선 ({len(table)}개 지점)"


def _scatter(df, x, y, color, agg, date_unit, top_n):
    """산점도: 점은 표본으로 그리고, Pearson r은 전체 데이터로 계산합니다 (점 3개 미만·상수 열이면 '계산 불가')."""
    cols = [x, y] + ([color] if color else [])
    data = df[cols].dropna()
    if data.empty:
        raise UserFacingError(f"{x}와 {y}에 함께 값이 있는 행이 없어 산점도를 그릴 수 없습니다.")
    s = charts.sample(data)
    notes = []
    fig, ax = charts.new_figure(6.5, 4.6)
    alpha = 0.7 if len(s) < 2000 else 0.35 if len(s) < 20000 else 0.15
    size = 14 if len(s) < 2000 else 6
    if color:
        cs, note = _limit_series(s[color].astype(object))
        notes += [note] if note else []
        names = list(cs.value_counts().index)
        for n, cl in zip(names, _colors(names)):
            m = cs == n
            ax.scatter(s.loc[m, x], s.loc[m, y], s=size, color=cl, alpha=alpha, linewidths=0, label=str(n))
        _legend(ax, color, len(names), markerscale=2.5)
    else:
        ax.scatter(s[x], s[y], s=size, color=charts.PRIMARY, alpha=alpha, linewidths=0)
    _style(ax, f"{x}와 {y}", x, y)
    ax.grid(axis="x", color="#E5E7EB", linewidth=0.8)
    ok_r = len(data) > 2 and data[x].nunique() > 1 and data[y].nunique() > 1
    r = data[x].corr(data[y]) if ok_r else None
    r_text = f"{r:.3f}" if r is not None else "계산 불가(점 3개 미만 또는 값이 모두 같음)"
    # 점 개수는 숫자로 둠 (글자로 바꾸면 Excel로 내보낼 때 숫자 계산이 안 됨. 쉼표는 화면이 붙임)
    table = pd.DataFrame({"값": [len(data), r_text if r is None else round(r, 4)]},
                         index=["점 개수(전체)", "Pearson r (전체)"], dtype=object)
    note = charts.sample_note(len(data))
    if note:
        notes.append(note)
    notes.append("상관이 있어도 원인과 결과를 뜻하지는 않습니다.")
    code = (f"data = sub[{cols!r}].dropna()\n"
            f"data.plot.scatter(x={x!r}, y={y!r}, alpha={alpha})\n"
            f"data[{x!r}].corr(data[{y!r}])   # Pearson r")
    return fig, table, code, notes, f"{x}–{y} 산점도 (r = {r_text}, {len(data):,}점)"


def _hist(df, x, y, color, agg, date_unit, top_n):
    """히스토그램: 정수 데이터는 구간 경계를 n.5에 맞추고, 꼬리가 아주 길면 가운데 99%만 그립니다."""
    col = x or y
    data = df[[col] + ([color] if color else [])].dropna()
    if data.empty:
        raise UserFacingError(f"{col}에 값이 없어 히스토그램을 그릴 수 없습니다.")
    s = charts.sample(data)
    notes = []
    fig, ax = charts.new_figure(7, 4.2)
    lo, hi = data[col].quantile(list(VIEW_QUANTILES))
    if heavy_tail(data[col]) and hi > lo:
        # 꼬리가 아주 길면 대부분의 값이 막대 하나에 몰려 분포가 안 보입니다 → 가운데 99%만 그림
        out = int(((data[col] < lo) | (data[col] > hi)).sum())
        s = s[(s[col] >= lo) & (s[col] <= hi)]
        notes.append(f"값의 꼬리가 아주 길어 하위 0.5%~상위 0.5% 범위({lo:,.2f} ~ {hi:,.2f})만 그렸습니다. "
                     f"범위 밖 {out:,}개는 그림에서만 뺐고 아래 통계에는 포함됩니다.")
    bins = charts.integer_bins(s[col])
    if isinstance(bins, str):
        bins = np.histogram_bin_edges(s[col], bins="auto")
        if len(bins) > HIST_MAX_BINS + 1:
            bins = np.histogram_bin_edges(s[col], bins=HIST_MAX_BINS)
    if color:
        cs, note = _limit_series(s[color].astype(object))
        notes += [note] if note else []
        names = list(cs.value_counts().index)
        for n, cl in zip(names, _colors(names)):
            ax.hist(s.loc[cs == n, col], bins=bins, histtype="step", linewidth=2, color=cl, label=str(n))
        _legend(ax, color, len(names))
    else:
        ax.hist(s[col], bins=bins, color=charts.PRIMARY, edgecolor="white", linewidth=0.6)
    _style(ax, f"{col} 분포", col, "빈도")
    desc = data[col].describe()
    table = desc.to_frame("값").round(4)
    table.index = ["개수", "평균", "표준편차", "최솟값", "Q1", "중앙값", "Q3", "최댓값"]
    note = charts.sample_note(len(data))
    if note:
        notes.append(note)
    code = ("import matplotlib.pyplot as plt\n"
            f"plt.hist(sub[{col!r}].dropna(), bins='auto')   # 구간 수 자동 결정"
            + (f"\n# 색 구분: for k, g in sub.groupby({color!r}): plt.hist(g[{col!r}].dropna(), bins='auto', histtype='step', label=k)" if color else "")
            + f"\nsub[{col!r}].describe()")
    return fig, table, code, notes, f"{col} 히스토그램 ({len(data):,}개 값)"


def _box(df, x, y, color, agg, date_unit, top_n):
    """상자그림: X를 고르면 그룹별(행 수 많은 순 최대 BOX_MAX_GROUPS개), 아니면 Y 하나. 양수이고 꼬리가 길면 로그 축."""
    col = y or x
    group = x if (y and x) else None
    notes = []
    fig, ax = charts.new_figure(7, 4.2)
    if group:
        gs, g_expr, _ = group_key(df, group, date_unit)
        data = pd.DataFrame({"g": gs, "v": df[col]}).dropna()
        if data.empty:
            raise UserFacingError(f"{group}와 {col}에 함께 값이 있는 행이 없어 상자그림을 그릴 수 없습니다.")
        order = data["g"].value_counts().index[:min(top_n, BOX_MAX_GROUPS)]
        if data["g"].nunique() > len(order):
            notes.append(f"'{group}' 그룹이 많아 행 수가 많은 {len(order)}개만 그렸습니다.")
        s = charts.sample(data)
        ax.boxplot([s.loc[s["g"] == k, "v"] for k in order], tick_labels=[str(k) for k in order],
                   patch_artist=True, flierprops=charts.FLIER,
                   boxprops={"facecolor": "#DCE7F5", "edgecolor": charts.EDGE},
                   medianprops={"color": charts.EDGE, "linewidth": 2})
        ax.tick_params(axis="x", rotation=45 if len(order) > 6 else 0)
        table = data.groupby("g", observed=True)["v"].describe().loc[order].round(4)
        table.columns = ["개수", "평균", "표준편차", "최솟값", "Q1", "중앙값", "Q3", "최댓값"]
        table.index.name = group
        code = f"sub.boxplot(column={col!r}, by={group!r})\nsub.groupby({group!r})[{col!r}].describe()"
        title = f"{group}별 {col}"
    else:
        data = df[col].dropna()
        if data.empty:
            raise UserFacingError(f"{col}에 값이 없어 상자그림을 그릴 수 없습니다.")
        s = charts.sample(data)
        ax.boxplot(s, patch_artist=True, flierprops=charts.FLIER,
                   boxprops={"facecolor": "#DCE7F5", "edgecolor": charts.EDGE},
                   medianprops={"color": charts.EDGE, "linewidth": 2})
        ax.set_xticks([1], [col])
        table = data.describe().to_frame("값").round(4)
        table.index = ["개수", "평균", "표준편차", "최솟값", "Q1", "중앙값", "Q3", "최댓값"]
        code = f"sub.boxplot(column={col!r})\nsub[{col!r}].describe()"
        title = f"{col} 상자그림"
    vals = data["v"] if group else data
    if (vals > 0).all() and heavy_tail(vals):
        ax.set_yscale("log")
        notes.append(f"{col} 값의 꼬리가 아주 길어 세로축을 로그 눈금(1, 10, 100…)으로 그렸습니다. 표의 값은 원래 단위입니다.")
    _style(ax, title, group or "", col)
    note = charts.sample_note(len(data))
    if note:
        notes.append(note)
    notes.append("상자는 Q1~Q3, 가운데 선은 중앙값, 점은 IQR×1.5 밖의 이상값 후보입니다.")
    return fig, table, code, notes, title


def _heatmap(df, x, y, color, agg, date_unit, top_n):
    """상관 히트맵: 고른 수치형 열(ID·0/1·상수 제외)의 Pearson 상관. 파랑 음수, 빨강 양수, 12열 이하면 숫자 표시."""
    num = df.select_dtypes(include="number")
    from .variables import is_strong_id
    num = num[[c for c in num.columns if not is_strong_id(num[c], c) and num[c].nunique() > 2]]   # 빈 열·상수·0/1 제외
    if num.shape[1] < 2:
        raise UserFacingError("상관 히트맵에는 값이 있는 수치형 열이 2개 이상 필요합니다 (ID·0/1 열 제외).")
    corr = num.corr()
    n = corr.shape[0]
    fig, ax = charts.new_figure(max(5, 0.6 * n + 2.5), max(4, 0.5 * n + 1.8))
    ax.spines[["left", "bottom"]].set_visible(False)
    im = ax.imshow(corr.to_numpy(), cmap="RdBu_r", vmin=-1, vmax=1)
    ax.set_xticks(range(n), [str(c) for c in corr.columns], rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(n), [str(c) for c in corr.index], fontsize=8)
    if n <= 12:
        for i in range(n):
            for j in range(n):
                v = corr.iat[i, j]
                ax.text(j, i, f"{v:.2f}", ha="center", va="center", fontsize=7,
                        color="white" if abs(v) > 0.6 else "#1F2937")
    fig.colorbar(im, ax=ax, shrink=0.8)
    ax.set_title("수치형 열 상관계수 (Pearson)", loc="left", fontsize=11)
    notes = ["파랑은 음의 상관, 빨강은 양의 상관, 흰색은 0 근처입니다.",
             "ID 열과 0/1 열은 뺐습니다. 상관이 있어도 원인과 결과를 뜻하지는 않습니다."]
    code = f"corr = sub[{list(num.columns)!r}].corr()\nimport seaborn as sns; sns.heatmap(corr, cmap='RdBu_r', vmin=-1, vmax=1, annot=True)"
    return fig, corr.round(4), code, notes, f"수치형 {n}개 열 상관 히트맵"
