"""USB device combo with three-line item display."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPainter, QPalette
from PySide6.QtWidgets import (
    QComboBox,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionComboBox,
    QStyleOptionViewItem,
    QWidget,
)

_USB_COMBO_ITEM_HEIGHT = 66
USB_DETAIL_ROLE = Qt.ItemDataRole.UserRole + 1
USB_SN_ROLE = Qt.ItemDataRole.UserRole + 2


def split_text_rect(rect, line_count: int):
    if line_count <= 1:
        return [rect]
    strips = []
    top = rect.top()
    height = rect.height() / line_count
    for index in range(line_count):
        strip = rect.adjusted(0, 0, 0, 0)
        strip.setTop(top + index * height)
        strip.setBottom(top + (index + 1) * height)
        strips.append(strip)
    return strips


class ThreeLineComboItemDelegate(QStyledItemDelegate):
    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        self.initStyleOption(option, index)
        painter.save()

        if option.state & QStyle.StateFlag.State_Selected:
            painter.fillRect(option.rect, option.palette.highlight())
            title_color = option.palette.highlightedText().color()
            detail_color = title_color
        else:
            if option.state & QStyle.StateFlag.State_MouseOver:
                painter.fillRect(option.rect, option.palette.alternateBase())
            title_color = option.palette.color(QPalette.ColorRole.Text)
            detail_color = option.palette.color(QPalette.ColorRole.PlaceholderText)

        title = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        detail = index.data(USB_DETAIL_ROLE)
        sn = index.data(USB_SN_ROLE)
        text_rect = option.rect.adjusted(6, 2, -6, -2)

        if detail is not None or sn is not None:
            title_rect, detail_rect, sn_rect = split_text_rect(text_rect, 3)
            title_font = option.font
            detail_font = option.font
            detail_font.setPointSize(max(8, title_font.pointSize() - 1))

            painter.setPen(title_color)
            painter.setFont(title_font)
            painter.drawText(
                title_rect,
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                title,
            )
            painter.setPen(detail_color)
            painter.setFont(detail_font)
            if detail is not None:
                painter.drawText(
                    detail_rect,
                    int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                    str(detail),
                )
            if sn is not None:
                painter.drawText(
                    sn_rect,
                    int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                    str(sn),
                )
        else:
            painter.setPen(title_color)
            painter.setFont(option.font)
            painter.drawText(
                text_rect,
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                title,
            )

        painter.restore()

    def sizeHint(self, option: QStyleOptionViewItem, index) -> QSize:
        size = super().sizeHint(option, index)
        if (
            index.data(USB_DETAIL_ROLE) is not None
            or index.data(USB_SN_ROLE) is not None
        ):
            return QSize(size.width(), _USB_COMBO_ITEM_HEIGHT)
        return size


class UsbDeviceComboBox(QComboBox):
    scan_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setItemDelegate(ThreeLineComboItemDelegate(self))
        self.setMinimumHeight(_USB_COMBO_ITEM_HEIGHT)
        self.setIconSize(QSize(0, _USB_COMBO_ITEM_HEIGHT - 8))
        self.view().setUniformItemSizes(False)

    def showPopup(self) -> None:
        self.scan_requested.emit()
        super().showPopup()

    def paintEvent(self, event) -> None:  # noqa: ANN001
        painter = QPainter(self)
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        option.currentText = ""
        self.style().drawComplexControl(
            QStyle.ComplexControl.CC_ComboBox, option, painter, self
        )

        edit_rect = (
            self.style()
            .subControlRect(
                QStyle.ComplexControl.CC_ComboBox,
                option,
                QStyle.SubControl.SC_ComboBoxEditField,
                self,
            )
            .adjusted(2, 1, -2, -1)
        )

        index = self.currentIndex()
        title = self.itemText(index) if index >= 0 else self.placeholderText()
        detail = self.itemData(index, USB_DETAIL_ROLE) if index >= 0 else None
        sn = self.itemData(index, USB_SN_ROLE) if index >= 0 else None
        enabled = bool(option.state & QStyle.StateFlag.State_Enabled)
        title_color = option.palette.color(
            QPalette.ColorGroup.Active if enabled else QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.Text,
        )
        detail_color = option.palette.color(
            QPalette.ColorGroup.Active if enabled else QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.PlaceholderText,
        )

        if detail is not None or sn is not None:
            title_rect, detail_rect, sn_rect = split_text_rect(edit_rect, 3)
            title_font = self.font()
            detail_font = self.font()
            detail_font.setPointSize(max(8, title_font.pointSize() - 1))

            painter.setPen(title_color)
            painter.setFont(title_font)
            painter.drawText(
                title_rect,
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                title,
            )
            painter.setPen(detail_color)
            painter.setFont(detail_font)
            if detail is not None:
                painter.drawText(
                    detail_rect,
                    int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                    str(detail),
                )
            if sn is not None:
                painter.drawText(
                    sn_rect,
                    int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                    str(sn),
                )
        else:
            painter.setPen(title_color)
            painter.setFont(self.font())
            painter.drawText(
                edit_rect,
                int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                title,
            )
