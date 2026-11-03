"""Wafer map display using QGraphicsView / QGraphicsScene."""

from __future__ import annotations

from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import (
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
)

from excel_loader import WaferMapData

# Bin value -> default fill color (R, G, B)
BIN_COLORS: dict[int, QColor] = {
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
    11: QColor(220, 220, 220),  # outside wafer / no die
}

DIE_SIZE = 18
LABEL_MARGIN = 28
AXIS_COLOR = QColor("#333333")
SELECTED_PEN = QPen(QColor("#0066CC"), 2)


class DieItem(QGraphicsRectItem):
    """Single die square; color can be changed independently."""

    def __init__(self, x_idx: int, y_idx: int, bin_value: int, size: float):
        super().__init__(0, 0, size, size)
        self.x_idx = x_idx
        self.y_idx = y_idx
        self.bin_value = bin_value
        self._custom_color: QColor | None = None
        self.setAcceptHoverEvents(True)
        self.setPen(QPen(QColor("#888888"), 0.5))
        self._apply_color()
        self.setToolTip(f"X{x_idx} Y{y_idx}  Bin={bin_value}")

    def _apply_color(self) -> None:
        color = self._custom_color or BIN_COLORS.get(self.bin_value, QColor("#FFFFFF"))
        self.setBrush(QBrush(color))

    def set_bin_value(self, value: int) -> None:
        self.bin_value = value
        self._custom_color = None
        self._apply_color()
        self.setToolTip(f"X{self.x_idx} Y{self.y_idx}  Bin={value}")

    def set_custom_color(self, color: QColor) -> None:
        self._custom_color = color
        self._apply_color()

    def set_selected(self, selected: bool) -> None:
        self.setPen(SELECTED_PEN if selected else QPen(QColor("#888888"), 0.5))


class WaferMapView(QGraphicsView):
    """Interactive wafer map with coordinate axes and zoom support."""

    die_clicked = Signal(int, int, int)  # x_idx, y_idx, bin_value

    def __init__(self, parent=None):
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setBackgroundBrush(QBrush(QColor("#FFFFFF")))

        self._dies: dict[tuple[int, int], DieItem] = {}
        self._selected: tuple[int, int] | None = None
        self._zoom_factor = 1.0
        self._map_data: WaferMapData | None = None

    def load_map(self, data: WaferMapData) -> None:
        self._map_data = data
        self._scene.clear()
        self._dies.clear()
        self._selected = None

        cols, rows = data.width, data.height
        map_w = LABEL_MARGIN + cols * DIE_SIZE
        map_h = LABEL_MARGIN + rows * DIE_SIZE

        font = QFont("Arial", 7)
        for c, label in enumerate(data.x_labels):
            text = QGraphicsTextItem(label)
            text.setFont(font)
            text.setDefaultTextColor(AXIS_COLOR)
            text.setPos(LABEL_MARGIN + c * DIE_SIZE + 2, 2)
            self._scene.addItem(text)

        for r, label in enumerate(data.y_labels):
            text = QGraphicsTextItem(label)
            text.setFont(font)
            text.setDefaultTextColor(AXIS_COLOR)
            text.setPos(2, LABEL_MARGIN + r * DIE_SIZE + 2)
            self._scene.addItem(text)

        for (cx, cy), value in data.grid.items():
            die = DieItem(cx, cy, value, DIE_SIZE)
            die.setPos(LABEL_MARGIN + cx * DIE_SIZE, LABEL_MARGIN + cy * DIE_SIZE)
            die.setZValue(1)
            self._scene.addItem(die)
            self._dies[(cx, cy)] = die

        border = QGraphicsRectItem(
            LABEL_MARGIN - 1,
            LABEL_MARGIN - 1,
            cols * DIE_SIZE + 2,
            rows * DIE_SIZE + 2,
        )
        border.setPen(QPen(QColor("#AAAAAA"), 1))
        border.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        border.setZValue(0)
        self._scene.addItem(border)

        self._scene.setSceneRect(0, 0, map_w + 4, map_h + 4)
        self.resetTransform()
        self._zoom_factor = 1.0
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)

    def set_zoom_percent(self, percent: int) -> None:
        scale = percent / 100.0
        self.resetTransform()
        self.scale(scale, scale)
        self._zoom_factor = scale

    def set_die_color(self, x_idx: int, y_idx: int, color: QColor) -> None:
        die = self._dies.get((x_idx, y_idx))
        if die:
            die.set_custom_color(color)

    def set_die_bin(self, x_idx: int, y_idx: int, bin_value: int) -> None:
        die = self._dies.get((x_idx, y_idx))
        if die:
            die.set_bin_value(bin_value)

    def die_count(self) -> int:
        if not self._map_data:
            return 0
        return self._map_data.die_count

    def _die_at(self, event) -> DieItem | None:
        scene_pos = self.mapToScene(event.position().toPoint())
        item = self._scene.itemAt(scene_pos, self.transform())
        return item if isinstance(item, DieItem) else None

    def mousePressEvent(self, event) -> None:
        die = self._die_at(event)
        if die and event.button() == Qt.MouseButton.LeftButton:
            self._select_die(die.x_idx, die.y_idx)
            self.die_clicked.emit(die.x_idx, die.y_idx, die.bin_value)
            return
        if die and event.button() == Qt.MouseButton.RightButton and die.bin_value != 11:
            cycle = [1, 2, 99]
            if die.bin_value in cycle:
                nxt = cycle[(cycle.index(die.bin_value) + 1) % len(cycle)]
            else:
                nxt = 1
            if nxt == 99:
                die.set_custom_color(QColor("#FF4444"))
                die.bin_value = 99
            else:
                die.set_bin_value(nxt)
            self.die_clicked.emit(die.x_idx, die.y_idx, die.bin_value)
            return
        super().mousePressEvent(event)

    def select_die(self, x_idx: int, y_idx: int) -> None:
        self._select_die(x_idx, y_idx)

    def _select_die(self, x_idx: int, y_idx: int) -> None:
        if self._selected and self._selected in self._dies:
            self._dies[self._selected].set_selected(False)
        self._selected = (x_idx, y_idx)
        if self._selected in self._dies:
            self._dies[self._selected].set_selected(True)
