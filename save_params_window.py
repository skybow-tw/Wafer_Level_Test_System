"""Manual save-parameter panel and companion window."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from datalog import (
    last_created_save_dir,
    register_save_dir_listener,
    save_dir_created_this_session,
    unregister_save_dir_listener,
)
from save_params import SaveParams, get_save_params, set_save_params
from theme_config import THEMES, generate_theme_qss

_PANEL_WIDTH = 180
_CONTROL_WIDTH = 148
_WINDOW_WIDTH = 200


class SaveParamsPanel(QWidget):
    """Folder name, prefix/suffix, and XY controls used for manual file naming."""

    def __init__(
        self,
        work_dir: Path,
        parent: QWidget | None = None,
        *,
        compact: bool = False,
    ) -> None:
        super().__init__(parent)
        self._work_dir = work_dir
        self._updating = False
        control_width = 100 if compact else _CONTROL_WIDTH
        panel_width = 128 if compact else _PANEL_WIDTH

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        title = QLabel("手動存檔參數:")
        title.setAlignment(Qt.AlignmentFlag.AlignLeft)
        root.addWidget(title)

        box = QFrame()
        box.setFrameShape(QFrame.Shape.StyledPanel)
        box.setFrameShadow(QFrame.Shadow.Sunken)
        form = QVBoxLayout(box)
        form.setContentsMargins(8, 8, 8, 8)
        form.setSpacing(8)

        self.edit_folder = QPlainTextEdit()
        line_height = self.fontMetrics().height() + 8
        self.edit_folder.setFixedHeight(line_height * 2)
        self.edit_folder.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.edit_folder.setHorizontalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        self.edit_folder.setVerticalScrollBarPolicy(
            Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        )
        form.addWidget(self._labeled_field("資料夾名稱:", self.edit_folder, control_width))

        self.edit_prefix = QLineEdit()
        form.addWidget(self._labeled_field("檔名前綴:", self.edit_prefix, control_width))

        self.spin_x = QSpinBox()
        self.spin_y = QSpinBox()
        for spin in (self.spin_x, self.spin_y):
            spin.setRange(0, 9999)
            spin.setValue(1)
            spin.setButtonSymbols(QSpinBox.ButtonSymbols.UpDownArrows)

        coord_frame = QFrame()
        coord_frame.setFrameShape(QFrame.Shape.StyledPanel)
        coord_frame.setFrameShadow(QFrame.Shadow.Sunken)
        coord_layout = QVBoxLayout(coord_frame)
        coord_layout.setContentsMargins(8, 8, 8, 8)
        coord_layout.setSpacing(8)
        coord_layout.addWidget(QLabel("元件座標"))
        coord_layout.addWidget(self._labeled_field("X座標", self.spin_x, control_width))
        coord_layout.addWidget(self._labeled_field("Y座標", self.spin_y, control_width))
        form.addWidget(coord_frame)

        self.edit_suffix = QLineEdit()
        form.addWidget(self._labeled_field("檔名後綴:", self.edit_suffix, control_width))
        root.addWidget(box)

        self.btn_open_folder = QPushButton("Open Folder")
        self.btn_open_folder.setMinimumHeight(36)
        self.btn_open_folder.setFixedWidth(control_width + 20)
        self.btn_open_folder.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon)
        )
        self.btn_open_folder.setEnabled(save_dir_created_this_session())
        self.btn_open_folder.clicked.connect(self.open_save_folder)
        root.addWidget(self.btn_open_folder, alignment=Qt.AlignmentFlag.AlignLeft)

        self.setFixedWidth(panel_width)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Minimum)
        self._load_from_store()
        self._wire_store_updates()
        register_save_dir_listener(self._on_save_dir_created)
        self.destroyed.connect(self._unregister_save_dir_listener)

    def params(self) -> SaveParams:
        return SaveParams(
            folder_name=self.edit_folder.toPlainText(),
            prefix=self.edit_prefix.text(),
            x=self.spin_x.value(),
            y=self.spin_y.value(),
            suffix=self.edit_suffix.text(),
        )

    def set_xy(self, x: int, y: int) -> None:
        self._updating = True
        try:
            self.spin_x.setValue(x)
            self.spin_y.setValue(y)
        finally:
            self._updating = False
        self._commit_to_store()

    def open_save_folder(self) -> None:
        directory = last_created_save_dir()
        if directory is None or not directory.is_dir():
            QMessageBox.warning(self, "Open Folder", "尚無可開啟的 Datalog 目錄。")
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(directory)))

    def _on_save_dir_created(self, _path: Path) -> None:
        try:
            self.btn_open_folder.setEnabled(True)
        except RuntimeError:
            unregister_save_dir_listener(self._on_save_dir_created)

    def _unregister_save_dir_listener(self, *_args) -> None:
        unregister_save_dir_listener(self._on_save_dir_created)

    def _labeled_field(self, label_text: str, widget: QWidget, width: int) -> QWidget:
        field = QWidget()
        layout = QVBoxLayout(field)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        layout.addWidget(QLabel(label_text))
        widget.setFixedWidth(width)
        layout.addWidget(widget)
        return field

    def _wire_store_updates(self) -> None:
        self.edit_folder.textChanged.connect(self._commit_to_store)
        self.edit_prefix.textChanged.connect(self._commit_to_store)
        self.edit_suffix.textChanged.connect(self._commit_to_store)
        self.spin_x.valueChanged.connect(self._commit_to_store)
        self.spin_y.valueChanged.connect(self._commit_to_store)

    def _load_from_store(self) -> None:
        params = get_save_params()
        self._updating = True
        try:
            self.edit_folder.setPlainText(params.folder_name)
            self.edit_prefix.setText(params.prefix)
            self.edit_suffix.setText(params.suffix)
            self.spin_x.setValue(params.x)
            self.spin_y.setValue(params.y)
        finally:
            self._updating = False

    def _commit_to_store(self, *_args) -> None:
        if self._updating:
            return
        set_save_params(self.params())


class SaveParamsWindow(QWidget):
    """Standalone window matching the LabVIEW manual-save parameter panel."""

    def __init__(self, work_dir: Path, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("手動存檔參數")
        self.setWindowFlag(Qt.WindowType.Tool, True)
        self.setStyleSheet(generate_theme_qss(THEMES["light"]))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        self.panel = SaveParamsPanel(work_dir, self)
        layout.addWidget(self.panel)
        layout.addStretch()
        self.setFixedWidth(_WINDOW_WIDTH)
        self.adjustSize()

    def align_to_host(self, host: QWidget) -> None:
        geo = host.frameGeometry()
        self.move(geo.right() + 8, geo.top())
