"""BMT value-array display using QTableView + model (scrollbar-friendly)."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableView,
)

BASE_CELL_SIZE = 18
COLUMN_WIDTH = 30
# Wide enough for signed 5-digit values (e.g. -1234 / 32767).
DATA_ARRAY_COLUMN_WIDTH = 52
ROW_HEIGHT = BASE_CELL_SIZE
EMPTY_COLOR = QColor("#FFFFFF")
NONZERO_YELLOW = QColor(255, 246, 0)

VALUE_COLORS: dict[int, QColor] = {
    0: QColor(255, 246, 0),
    1: QColor(255, 0, 0),
    2: QColor(0, 255, 0),
    3: QColor(0, 0, 255),
    4: QColor(128, 0, 0),
    5: QColor(128, 128, 0),
    6: QColor(128, 0, 128),
    7: QColor(255, 128, 128),
    8: QColor(128, 255, 0),
    9: QColor(128, 128, 255),
    10: QColor(255, 255, 255),
}

DEFAULT_ARRAY_ROWS = 512
DEFAULT_ARRAY_COLS = 640
REGISTER_MAP_SIZE = 16


def register_map_column_headers() -> list[str]:
    return [f"0x{col:02X}" for col in range(REGISTER_MAP_SIZE)]


def register_map_row_headers() -> list[str]:
    return [f"0x{row:02X}" for row in range(0, 256, 16)]


class BmtArrayModel(QAbstractTableModel):
    """Sparse-friendly table model for a large 2D value array."""

    def __init__(self, rows: int = 0, cols: int = 0, parent=None) -> None:
        super().__init__(parent)
        self._rows = 0
        self._cols = 0
        self._values: list[object | None] = []
        self._custom_colors: dict[tuple[int, int], QColor] = {}
        self._row_headers: list[str] | None = None
        self._col_headers: list[str] | None = None
        # Register Map: non-zero → yellow, zero → white. Data Array keeps VALUE_COLORS.
        self._nonzero_yellow = False
        if rows > 0 and cols > 0:
            self.reset_size(rows, cols)

    def set_nonzero_yellow_mode(self, enabled: bool) -> None:
        self._nonzero_yellow = enabled

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return self._rows

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        if parent.isValid():
            return 0
        return self._cols

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            if self._col_headers is not None and 0 <= section < len(self._col_headers):
                return self._col_headers[section]
            return str(section)
        if self._row_headers is not None and 0 <= section < len(self._row_headers):
            return self._row_headers[section]
        return str(section)

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:  # noqa: N802
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole):  # noqa: N802
        if not index.isValid():
            return None
        row = index.row()
        col = index.column()
        if role == Qt.ItemDataRole.DisplayRole:
            value = self._value_at(row, col)
            return "" if value is None else str(value)
        if role == Qt.ItemDataRole.BackgroundRole:
            return QBrush(self._color_at(row, col))
        if role == Qt.ItemDataRole.TextAlignmentRole:
            return int(Qt.AlignmentFlag.AlignCenter)
        if role == Qt.ItemDataRole.ToolTipRole:
            value = self._value_at(row, col)
            shown = "" if value is None else str(value)
            col_label = self.headerData(col, Qt.Orientation.Horizontal) or col
            row_label = self.headerData(row, Qt.Orientation.Vertical) or row
            return f"{row_label}+{col_label}  Value={shown}"
        return None

    def reset_size(
        self,
        rows: int,
        cols: int,
        values: list[list[object]] | None = None,
        *,
        row_headers: list[str] | None = None,
        col_headers: list[str] | None = None,
    ) -> None:
        self.beginResetModel()
        self._rows = rows
        self._cols = cols
        self._values = [None] * (rows * cols)
        self._custom_colors.clear()
        self._row_headers = list(row_headers) if row_headers is not None else None
        self._col_headers = list(col_headers) if col_headers is not None else None
        if values is not None:
            for y, row_values in enumerate(values):
                if y >= rows:
                    break
                for x, value in enumerate(row_values):
                    if x >= cols:
                        break
                    self._values[y * cols + x] = value
        self.endResetModel()

    def _index_of(self, row: int, col: int) -> int:
        return row * self._cols + col

    def _value_at(self, row: int, col: int) -> object | None:
        if not (0 <= row < self._rows and 0 <= col < self._cols):
            return None
        return self._values[self._index_of(row, col)]

    @staticmethod
    def _parse_numeric(value: object) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            pass
        try:
            text = str(value).strip()
            if text.lower().startswith("0x"):
                text = text[2:]
            return int(text, 16)
        except (TypeError, ValueError):
            return None

    def _color_at(self, row: int, col: int) -> QColor:
        custom = self._custom_colors.get((col, row))
        if custom is not None:
            return custom
        value = self._value_at(row, col)
        as_int = self._parse_numeric(value)
        if as_int is None:
            return EMPTY_COLOR
        if self._nonzero_yellow:
            return NONZERO_YELLOW if as_int != 0 else EMPTY_COLOR
        return VALUE_COLORS.get(as_int, EMPTY_COLOR)

    def set_cell_value(
        self,
        x_idx: int,
        y_idx: int,
        value: object | None,
        *,
        auto_color: bool = True,
    ) -> None:
        if not (0 <= y_idx < self._rows and 0 <= x_idx < self._cols):
            return
        self._values[self._index_of(y_idx, x_idx)] = value
        if auto_color:
            self._custom_colors.pop((x_idx, y_idx), None)
        index = self.index(y_idx, x_idx)
        self.dataChanged.emit(index, index, [])

    def set_cell_color(self, x_idx: int, y_idx: int, color: QColor) -> None:
        if not (0 <= y_idx < self._rows and 0 <= x_idx < self._cols):
            return
        self._custom_colors[(x_idx, y_idx)] = color
        index = self.index(y_idx, x_idx)
        self.dataChanged.emit(index, index, [Qt.ItemDataRole.BackgroundRole])

    def cell_value(self, x_idx: int, y_idx: int) -> object | None:
        return self._value_at(y_idx, x_idx)


class BmtArrayView(QTableView):
    """Table view with coordinate headers, coloring and scrollbar navigation."""

    cell_clicked = Signal(int, int, object)  # x_idx, y_idx, value

    def __init__(self, parent=None, *, column_width: int = COLUMN_WIDTH) -> None:
        super().__init__(parent)
        self._model = BmtArrayModel(parent=self)
        self.setModel(self._model)
        self._column_width = max(1, int(column_width))

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.setWordWrap(False)
        self.setSortingEnabled(False)
        self.setAlternatingRowColors(False)
        self.setShowGrid(True)
        self.setCornerButtonEnabled(False)

        self.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().setHighlightSections(False)
        self.verticalHeader().setHighlightSections(False)

        self._apply_cell_size()

        self.clicked.connect(self._on_clicked)

    def set_column_width(self, width: int) -> None:
        self._column_width = max(1, int(width))
        self._apply_cell_size()

    @property
    def rows(self) -> int:
        return self._model.rowCount()

    @property
    def cols(self) -> int:
        return self._model.columnCount()

    def load_array(
        self,
        rows: int,
        cols: int,
        values: list[list[object]] | None = None,
        *,
        row_headers: list[str] | None = None,
        col_headers: list[str] | None = None,
    ) -> None:
        if rows < 1 or cols < 1:
            raise ValueError("rows/cols must be >= 1")
        self._model.reset_size(
            rows,
            cols,
            values,
            row_headers=row_headers,
            col_headers=col_headers,
        )
        self._apply_cell_size()
        self.scrollToTop()
        self.horizontalScrollBar().setValue(0)

    def load_register_map(self) -> None:
        self._model.set_nonzero_yellow_mode(True)
        self.load_array(
            REGISTER_MAP_SIZE,
            REGISTER_MAP_SIZE,
            row_headers=register_map_row_headers(),
            col_headers=register_map_column_headers(),
        )
        # Hex labels need a slightly wider row header.
        self.verticalHeader().setFixedWidth(42)

    def set_values(self, values: list[list[object]]) -> None:
        if not values:
            self.load_array(DEFAULT_ARRAY_ROWS, DEFAULT_ARRAY_COLS)
            return
        rows = len(values)
        cols = max((len(row) for row in values), default=0)
        if cols < 1:
            self.load_array(rows, 1)
            return
        self.load_array(rows, cols, values)

    def set_cell_value(
        self,
        x_idx: int,
        y_idx: int,
        value: object | None,
        *,
        auto_color: bool = True,
    ) -> None:
        self._model.set_cell_value(x_idx, y_idx, value, auto_color=auto_color)

    def set_cell_color(self, x_idx: int, y_idx: int, color: QColor) -> None:
        self._model.set_cell_color(x_idx, y_idx, color)

    def select_cell(self, x_idx: int, y_idx: int) -> None:
        index = self._model.index(y_idx, x_idx)
        if index.isValid():
            self.setCurrentIndex(index)
            self.scrollTo(index, QAbstractItemView.ScrollHint.EnsureVisible)

    def _apply_cell_size(self) -> None:
        self.verticalHeader().setDefaultSectionSize(ROW_HEIGHT)
        self.horizontalHeader().setDefaultSectionSize(self._column_width)
        if self._model.rowCount() > 0:
            self.verticalHeader().resizeSections()
        if self._model.columnCount() > 0:
            self.horizontalHeader().resizeSections()

    def _on_clicked(self, index: QModelIndex) -> None:
        if not index.isValid():
            return
        x_idx = index.column()
        y_idx = index.row()
        self.cell_clicked.emit(x_idx, y_idx, self._model.cell_value(x_idx, y_idx))
