"""큰 표를 화면에 보여주는 모델.

120만 행을 한 번에 그리면 화면이 멈추므로, 처음 1,000행만 보여주고
스크롤이 끝에 닿을 때마다 1,000행씩 더 불러옵니다 (Qt의 canFetchMore/fetchMore).
"""

import math

import pandas as pd
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal

CHUNK = 1000


def format_value(v):
    """표 칸에 보여줄 글자. 결측은 빈칸, 실수는 소수 4자리까지."""
    if isinstance(v, float):
        if math.isnan(v):
            return ""
        return f"{v:,.4f}".rstrip("0").rstrip(".") if abs(v) < 1e15 else f"{v:.4g}"
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):   # 리스트 등 pd.isna가 칸 하나로 판단 못 하는 값
        pass
    return str(v)


class DataFrameModel(QAbstractTableModel):
    """데이터 탭 표 모델. 아주 큰 데이터도 화면이 멈추지 않도록 CHUNK(1,000)행씩 나눠 보여줍니다.

    스크롤이 끝에 가까워지면 Qt가 canFetchMore/fetchMore를 불러 다음 묶음을 붙입니다.
    """
    loadedChanged = Signal(int, int)   # (불러온 행 수, 전체 행 수)

    def __init__(self, df=None, chunk=CHUNK, show_index=False, parent=None):
        """show_index: 왼쪽에 원래 행 번호를 보일지"""
        super().__init__(parent)
        self._chunk = chunk
        self._show_index = show_index
        self._df = pd.DataFrame()
        self._loaded = 0
        if df is not None:
            self.set_dataframe(df)

    # ---- 데이터 교체 ----
    def set_dataframe(self, df):
        """보여줄 데이터를 바꾸고 처음 CHUNK행만 올립니다. 정렬 계산 캐시도 새로 만듭니다."""
        self.beginResetModel()
        self._df = df if df is not None else pd.DataFrame()
        self._loaded = min(self._chunk, len(self._df))
        self._cache_alignment()
        self.endResetModel()
        self.loadedChanged.emit(self._loaded, len(self._df))

    def _cache_alignment(self):
        """열마다 정렬(숫자는 오른쪽)을 한 번만 계산. 칸마다 dtypes를 다시 만들면 큰 표에서 느려짐."""
        right = int(Qt.AlignRight | Qt.AlignVCenter)
        left = int(Qt.AlignLeft | Qt.AlignVCenter)
        self._align = [right if pd.api.types.is_numeric_dtype(t) and not pd.api.types.is_bool_dtype(t) else left
                       for t in self._df.dtypes]

    def dataframe(self):
        """지금 보여주는 데이터(DataFrame)를 돌려줍니다."""
        return self._df

    # ---- Qt 모델 기본 ----
    def rowCount(self, parent=QModelIndex()):
        """지금까지 불러온 행 수 (전체 행 수가 아님)."""
        return 0 if parent.isValid() else self._loaded

    def columnCount(self, parent=QModelIndex()):
        """열 수."""
        return 0 if parent.isValid() else self._df.shape[1]

    def data(self, index, role=Qt.DisplayRole):
        """칸 하나의 표시 글자·정렬을 돌려줍니다. 숫자는 오른쪽 정렬, 결측은 빈칸."""
        if not index.isValid():
            return None
        if role == Qt.DisplayRole:
            return format_value(self._df.iat[index.row(), index.column()])
        if role == Qt.TextAlignmentRole:
            return self._align[index.column()]
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        """열 이름(가로)과 행 번호(세로) 머리글."""
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return str(self._df.columns[section])
        if self._show_index:
            return str(self._df.index[section])
        return f"{section + 1:,}"

    # ---- 나눠 불러오기 ----
    def canFetchMore(self, parent=QModelIndex()):
        """아직 안 불러온 행이 남았는지."""
        return not parent.isValid() and self._loaded < len(self._df)

    def fetchMore(self, parent=QModelIndex()):
        """다음 CHUNK행을 붙입니다."""
        if parent.isValid():
            return
        add = min(self._chunk, len(self._df) - self._loaded)
        if add <= 0:
            return
        self.beginInsertRows(QModelIndex(), self._loaded, self._loaded + add - 1)
        self._loaded += add
        self.endInsertRows()
        self.loadedChanged.emit(self._loaded, len(self._df))

    # ---- 열 이름 눌러 정렬 ----
    def sort(self, column, order=Qt.AscendingOrder):
        """열 머리글을 누르면 그 열로 정렬합니다 (mergesort: 같은 값의 원래 순서 유지)."""
        if self._df.empty:
            return
        col = self._df.columns[column]
        self.beginResetModel()
        self._df = self._df.sort_values(col, ascending=(order == Qt.AscendingOrder),
                                        kind="mergesort", na_position="last")
        self._cache_alignment()
        self._loaded = min(max(self._loaded, self._chunk), len(self._df))
        self.endResetModel()
        self.loadedChanged.emit(self._loaded, len(self._df))
