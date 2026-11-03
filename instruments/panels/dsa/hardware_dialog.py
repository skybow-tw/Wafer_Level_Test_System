"""DSA Hardware Selection dialog."""

from __future__ import annotations

from dataclasses import replace

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from instruments.panels.common import mark_close_button, mark_primary_button
from instruments.panels.widgets.ni_device_combo import NiDeviceComboBox
from instruments.pxi4461 import (
    PXI4461_MAX_SAMPLE_RATE_HZ,
    PXI4461_VOLTAGE_SPIN_MAX,
    PXI4461_VOLTAGE_SPIN_MIN,
    TERMINAL_CONFIG_LABELS,
    DsaHardwareSettings,
    list_dsa_ai_channels,
    list_dsa_ao_channels,
)
from theme_config import THEMES, generate_theme_qss

_CHANNEL_WIDTH = 260
_SPIN_WIDTH = 120
_AO_COLOR = "#1565C0"
_STIM_COLOR = "#1565C0"
_RESP_COLOR = "#E65100"


def _section_label(text: str, color: str) -> QLabel:
    label = QLabel(text)
    label.setStyleSheet(f"color: {color}; font-weight: bold;")
    return label


def _labeled_combo(label_text: str) -> tuple[QVBoxLayout, NiDeviceComboBox]:
    layout = QVBoxLayout()
    layout.setSpacing(2)
    layout.setContentsMargins(0, 0, 0, 0)
    label = QLabel(label_text)
    combo = NiDeviceComboBox()
    combo.setEditable(False)
    combo.setMinimumWidth(_CHANNEL_WIDTH)
    combo.setSizeAdjustPolicy(
        QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
    )
    combo.setMinimumContentsLength(22)
    combo.setPlaceholderText("按下選單掃描通道…")
    layout.addWidget(label)
    layout.addWidget(combo)
    return layout, combo


def _voltage_spin(value: float) -> QDoubleSpinBox:
    spin = QDoubleSpinBox()
    spin.setDecimals(2)
    spin.setRange(PXI4461_VOLTAGE_SPIN_MIN, PXI4461_VOLTAGE_SPIN_MAX)
    spin.setSingleStep(0.1)
    spin.setValue(value)
    spin.setFixedWidth(_SPIN_WIDTH)
    return spin


def _labeled_spin(label_text: str, spin: QWidget) -> QVBoxLayout:
    layout = QVBoxLayout()
    layout.setSpacing(2)
    layout.setContentsMargins(0, 0, 0, 0)
    label = QLabel(label_text)
    layout.addWidget(label)
    layout.addWidget(spin)
    return layout


def _terminal_combo(current: str) -> QComboBox:
    combo = QComboBox()
    combo.addItems(list(TERMINAL_CONFIG_LABELS))
    index = combo.findText(current)
    combo.setCurrentIndex(max(0, index))
    combo.setFixedWidth(_SPIN_WIDTH + 40)
    return combo


def _channel_panel(
    title: str,
    title_color: str,
    channel_label: str,
    settings_max: float,
    settings_min: float,
    settings_terminal: str,
) -> tuple[QFrame, NiDeviceComboBox, QDoubleSpinBox, QDoubleSpinBox, QComboBox]:
    frame = QFrame()
    frame.setFrameShape(QFrame.Shape.StyledPanel)
    frame.setFrameShadow(QFrame.Shadow.Sunken)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(10, 8, 10, 10)
    layout.setSpacing(6)
    layout.addWidget(_section_label(title, title_color))

    channel_row, combo = _labeled_combo(channel_label)
    layout.addLayout(channel_row)

    spin_max = _voltage_spin(settings_max)
    spin_min = _voltage_spin(settings_min)
    cmb_term = _terminal_combo(settings_terminal)
    layout.addLayout(_labeled_spin("max value [V]", spin_max))
    layout.addLayout(_labeled_spin("min value [V]", spin_min))
    layout.addLayout(_labeled_spin("terminal configuration", cmb_term))
    layout.addStretch()
    return frame, combo, spin_max, spin_min, cmb_term


def _fill_combo(
    combo: QComboBox, channels: list[str], current: str, empty_text: str
) -> None:
    combo.blockSignals(True)
    combo.clear()
    if not channels:
        combo.addItem(empty_text, "")
        combo.blockSignals(False)
        return
    restore = 0
    for index, name in enumerate(channels):
        combo.addItem(name, name)
        if name == current:
            restore = index
    combo.setCurrentIndex(restore)
    combo.blockSignals(False)


class DsaHardwareDialog(QDialog):
    """Standalone Hardware Selection window for DSA AO / AI channels."""

    def __init__(
        self,
        settings: DsaHardwareSettings,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("硬體設定")
        self.setModal(True)
        self._settings = replace(settings)
        self._result_settings = replace(settings)
        self.setStyleSheet(generate_theme_qss(THEMES["light"]))
        self._build_ui()
        self._wire()
        self.resize(760, 520)
        self._refresh_ao_channels()
        self._refresh_ai_channels()

    def selected_settings(self) -> DsaHardwareSettings:
        return replace(self._result_settings)

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 12, 12, 12)
        outer.setSpacing(10)

        group = QGroupBox("硬體設定")
        grid = QGridLayout(group)
        grid.setContentsMargins(12, 16, 12, 12)
        grid.setHorizontalSpacing(16)
        grid.setVerticalSpacing(12)

        (
            ao_panel,
            self._cmb_ao,
            self._spin_ao_max,
            self._spin_ao_min,
            self._cmb_ao_term,
        ) = _channel_panel(
            "類比輸出(信號源)：",
            _AO_COLOR,
            "AO excitation channel",
            self._settings.ao_max_v,
            self._settings.ao_min_v,
            self._settings.ao_terminal,
        )

        sample_frame = QFrame()
        sample_frame.setFrameShape(QFrame.Shape.StyledPanel)
        sample_frame.setFrameShadow(QFrame.Shadow.Sunken)
        sample_layout = QVBoxLayout(sample_frame)
        sample_layout.setContentsMargins(10, 8, 10, 10)
        self._spin_sample_rate = QDoubleSpinBox()
        self._spin_sample_rate.setDecimals(0)
        self._spin_sample_rate.setRange(0.0, PXI4461_MAX_SAMPLE_RATE_HZ)
        self._spin_sample_rate.setSingleStep(100.0)
        self._spin_sample_rate.setValue(self._settings.sample_rate_hz)
        self._spin_sample_rate.setFixedWidth(_SPIN_WIDTH)
        sample_layout.addLayout(
            _labeled_spin("sampling frequency", self._spin_sample_rate)
        )
        sample_layout.addStretch()
        sample_frame.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred
        )

        (
            stim_panel,
            self._cmb_stim,
            self._spin_stim_max,
            self._spin_stim_min,
            self._cmb_stim_term,
        ) = _channel_panel(
            "類比輸入(驅動)：",
            _STIM_COLOR,
            "AI stimulus channel",
            self._settings.ai_stimulus_max_v,
            self._settings.ai_stimulus_min_v,
            self._settings.ai_stimulus_terminal,
        )
        (
            resp_panel,
            self._cmb_resp,
            self._spin_resp_max,
            self._spin_resp_min,
            self._cmb_resp_term,
        ) = _channel_panel(
            "類比輸入(響應)：",
            _RESP_COLOR,
            "AI response channel",
            self._settings.ai_response_max_v,
            self._settings.ai_response_min_v,
            self._settings.ai_response_terminal,
        )

        grid.addWidget(ao_panel, 0, 0)
        grid.addWidget(sample_frame, 0, 1, alignment=Qt.AlignmentFlag.AlignTop)
        grid.addWidget(stim_panel, 1, 0)
        grid.addWidget(resp_panel, 1, 1)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btn_ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        btn_cancel = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        btn_ok.setText("OK")
        btn_cancel.setText("Cancel")
        for button in (btn_ok, btn_cancel):
            button.setMinimumSize(120, 44)
        mark_primary_button(btn_ok)
        mark_close_button(btn_cancel)
        buttons.accepted.connect(self._on_ok)
        buttons.rejected.connect(self.reject)

        outer.addWidget(group, stretch=1)
        button_row = QHBoxLayout()
        button_row.addWidget(buttons)
        outer.addLayout(button_row)

    def _wire(self) -> None:
        self._cmb_ao.scan_requested.connect(self._refresh_ao_channels)
        self._cmb_stim.scan_requested.connect(self._refresh_ai_channels)
        self._cmb_resp.scan_requested.connect(self._refresh_ai_channels)

    def _refresh_ao_channels(self) -> None:
        current = self._cmb_ao.currentData() or self._settings.ao_channel
        try:
            channels = list_dsa_ao_channels()
        except Exception as exc:
            _fill_combo(self._cmb_ao, [], "", "掃描失敗")
            QMessageBox.warning(self, "NI 掃描失敗", str(exc))
            return
        _fill_combo(self._cmb_ao, channels, current, "未偵測到 DSA AO 通道")

    def _refresh_ai_channels(self) -> None:
        stim_current = self._cmb_stim.currentData() or self._settings.ai_stimulus_channel
        resp_current = self._cmb_resp.currentData() or self._settings.ai_response_channel
        try:
            channels = list_dsa_ai_channels()
        except Exception as exc:
            _fill_combo(self._cmb_stim, [], "", "掃描失敗")
            _fill_combo(self._cmb_resp, [], "", "掃描失敗")
            QMessageBox.warning(self, "NI 掃描失敗", str(exc))
            return
        _fill_combo(self._cmb_stim, channels, stim_current, "未偵測到 DSA AI 通道")
        _fill_combo(self._cmb_resp, channels, resp_current, "未偵測到 DSA AI 通道")
        if channels and not resp_current:
            default_resp = channels[1] if len(channels) > 1 else channels[0]
            index = self._cmb_resp.findData(default_resp)
            if index >= 0:
                self._cmb_resp.setCurrentIndex(index)
        if channels and not stim_current:
            index = self._cmb_stim.findData(channels[0])
            if index >= 0:
                self._cmb_stim.setCurrentIndex(index)

    def _on_ok(self) -> None:
        ao_channel = str(self._cmb_ao.currentData() or "")
        stim_channel = str(self._cmb_stim.currentData() or "")
        resp_channel = str(self._cmb_resp.currentData() or "")
        if not ao_channel:
            QMessageBox.information(
                self, "硬體設定", "請選擇 AO excitation channel。"
            )
            return
        if not resp_channel:
            QMessageBox.information(
                self, "硬體設定", "請選擇 AI response channel。"
            )
            return
        if self._spin_ao_max.value() <= self._spin_ao_min.value():
            QMessageBox.warning(self, "硬體設定", "AO max 必須大於 min。")
            return
        self._result_settings = DsaHardwareSettings(
            ao_channel=ao_channel,
            ao_max_v=self._spin_ao_max.value(),
            ao_min_v=self._spin_ao_min.value(),
            ao_terminal=self._cmb_ao_term.currentText(),
            sample_rate_hz=self._spin_sample_rate.value(),
            ai_stimulus_channel=stim_channel,
            ai_stimulus_max_v=self._spin_stim_max.value(),
            ai_stimulus_min_v=self._spin_stim_min.value(),
            ai_stimulus_terminal=self._cmb_stim_term.currentText(),
            ai_response_channel=resp_channel,
            ai_response_max_v=self._spin_resp_max.value(),
            ai_response_min_v=self._spin_resp_min.value(),
            ai_response_terminal=self._cmb_resp_term.currentText(),
        )
        self.accept()
