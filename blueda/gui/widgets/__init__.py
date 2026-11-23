"""화면 부품 모음.

예전에는 widgets.py 한 파일(약 1,400줄)이었고, 고칠 곳을 찾기 쉽도록 화면 위치별로 나눴습니다.
`from blueda.gui.widgets import FilterBar`처럼 예전 방식 그대로 가져다 쓸 수 있습니다.

| 파일            | 화면 위치               | 주요 부품 |
|-----------------|-------------------------|-----------|
| base.py         | 공통                    | label, button, panel, repolish, Worker(작업 스레드), FlowLayout, Popup |
| columns.py      | 왼쪽 위 열 상자          | ColumnPanel |
| menu.py         | 왼쪽 아래 분석 메뉴      | MethodMenu |
| filters.py      | 가운데 위 행 조건        | FilterBar, Chip, ColumnPickerPopup, ValuePopup, RangePopup |
| analysis_bar.py | 가운데 분석 설정 줄      | AnalysisBar, MultiColumnButton |
| results.py      | 가운데 아래 결과 탭      | ResultTabs, ChartView, table_view, fit_table_height |
| session.py      | 맨 아래 결과 세션        | SessionPanel (결과 줄 · 히스토리 탭 · 명령 입력) |
"""

from .analysis_bar import AnalysisBar, MultiColumnButton
from .base import FlowLayout, Popup, Worker, button, label, panel, repolish
from .columns import KIND_ORDER, KIND_TITLE, ColumnPanel, column_detail
from .filters import Chip, ColumnPickerPopup, FilterBar, RangePopup, ValuePopup
from .menu import MethodMenu
from .results import ChartView, ResultTabs, fit_table_height, table_view
from .session import SessionPanel

__all__ = [
    "AnalysisBar", "MultiColumnButton", "FlowLayout", "Popup", "Worker", "button", "label", "panel", "repolish",
    "KIND_ORDER", "KIND_TITLE", "ColumnPanel", "column_detail", "Chip", "ColumnPickerPopup", "FilterBar",
    "RangePopup", "ValuePopup", "MethodMenu", "ChartView", "ResultTabs", "fit_table_height", "table_view",
    "SessionPanel",
]
