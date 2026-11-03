THEMES = {
    "light": {
        "name": "Light",
        "bg": "#FFFFFF",
        "fg": "#1E1E1E",
        "accent": "#0078D4",
        "sub_bg": "#F3F3F3",
        "border": "#CCCCCC",
        "btn_disabled_fg": "#A0A0A0",
        "btn_disabled_bg": "#ECECEC",
        "btn_primary_fg": "#FFFFFF",
        "btn_close": "#E53935",
        "btn_close_fg": "#FFFFFF",
        "btn_start": "#FFB300",
        "btn_start_fg": "#FFFFFF",
    },
    "dark": {
        "name": "Dark",
        "bg": "#121212",
        "fg": "#EAEAEA",
        "accent": "#4FC3F7",
        "sub_bg": "#1E1E1E",
        "border": "#2A2A2A",
        "btn_disabled_fg": "#5C5C5C",
        "btn_disabled_bg": "#0E0E0E",
        "btn_primary_fg": "#121212",
    },
    "One Dark Pro": {
        "name": "One Dark Pro",
        "bg": "#282c34",
        "fg": "#abb2bf",
        "accent": "#61afef",
        "sub_bg": "#3e4451",
        "border": "#181a1f",
        "btn_disabled_fg": "#4b5263",
        "btn_disabled_bg": "#21252b",
        "btn_primary_fg": "#282c34",
    },
    "Night Owl": {
        "name": "Night Owl",
        "bg": "#011627",
        "fg": "#d6deeb",
        "accent": "#82aaff",
        "sub_bg": "#0b2942",
        "border": "#010e17",
        "btn_disabled_fg": "#425065",
        "btn_disabled_bg": "#0a1929",
        "btn_primary_fg": "#011627",
    },
    "Gruvbox Dark": {
        "name": "Gruvbox Dark",
        "bg": "#282828",
        "fg": "#ebdbb2",
        "accent": "#fabd2f",
        "sub_bg": "#3c3836",
        "border": "#1d2021",
        "btn_disabled_fg": "#665c54",
        "btn_disabled_bg": "#1d2021",
        "btn_primary_fg": "#1d2021",
    },
    "Tokyo Night": {
        "name": "Tokyo Night",
        "bg": "#24283b",
        "fg": "#a9b1d6",
        "accent": "#7aa2f7",
        "sub_bg": "#2f3549",
        "border": "#1a1b26",
        "btn_disabled_fg": "#565f89",
        "btn_disabled_bg": "#1f2335",
        "btn_primary_fg": "#1a1b26",
    },
    "Catppuccin Mocha": {
        "name": "Catppuccin Mocha",
        "bg": "#1e1e2e",
        "fg": "#cdd6f4",
        "accent": "#b4befe",
        "sub_bg": "#313244",
        "border": "#181825",
        "btn_disabled_fg": "#585b70",
        "btn_disabled_bg": "#181825",
        "btn_primary_fg": "#1e1e2e",
    },
}

LIGHT_QSS = """
QWidget {
    background-color: #FFFFFF;
    color: #1E1E1E;
}
QPushButton {
    background-color: #F3F3F3;
    color: #1E1E1E;
    border: 1px solid #CCCCCC;
    border-radius: 6px;
    padding: 6px;
}
QPushButton:hover {
    background-color: #E1E1E1;
}
QPushButton:disabled {
    background-color: #ECECEC;
    color: #A0A0A0;
    border: 1px solid #CCCCCC;
}
QPushButton[btnRole="primary"]:enabled {
    background-color: #0078D4;
    color: #FFFFFF;
    border: 1px solid #0078D4;
    font-weight: bold;
}
QPushButton[btnRole="primary"]:enabled:hover {
    background-color: #F3F3F3;
    color: #0078D4;
    border: 1px solid #0078D4;
}
QPushButton[btnRole="primary"]:disabled {
    background-color: #ECECEC;
    color: #A0A0A0;
    border: 1px solid #CCCCCC;
    font-weight: normal;
}
QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #FFFFFF;
    color: #1E1E1E;
    border: 1px solid #CCCCCC;
    border-radius: 4px;
    padding: 2px 4px;
}
QGroupBox {
    background-color: #F3F3F3;
    border: 1px solid #CCCCCC;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}
QTabWidget::pane {
    border: 1px solid #CCCCCC;
    background-color: #FFFFFF;
}
QTabBar::tab {
    background-color: #F3F3F3;
    color: #1E1E1E;
    border: 1px solid #CCCCCC;
    padding: 6px 12px;
}
QTabBar::tab:selected {
    background-color: #0078D4;
    color: #FFFFFF;
}
QMenuBar, QMenu, QMenu::item {
    background-color: #FFFFFF;
    color: #1E1E1E;
}
QMenu::item:selected {
    background-color: #0078D4;
    color: #FFFFFF;
}
QSlider::groove:horizontal {
    background: #E1E1E1;
    height: 6px;
    border-radius: 3px;
}
QSlider::groove:horizontal:disabled {
    background: #ECECEC;
}
QSlider::handle:horizontal {
    background: #0078D4;
    width: 14px;
    margin: -4px 0;
    border-radius: 7px;
}
QSlider::handle:horizontal:disabled {
    background: #A0A0A0;
}
QLabel:disabled {
    color: #A0A0A0;
}
"""

DARK_QSS = """
QWidget {
    background-color: #121212;
    color: #EAEAEA;
}
QPushButton {
    background-color: #1E1E1E;
    color: #EAEAEA;
    border: 1px solid #2A2A2A;
    border-radius: 6px;
    padding: 6px;
}
QPushButton:hover {
    background-color: #2A2A2A;
}
QPushButton:disabled {
    background-color: #0E0E0E;
    color: #5C5C5C;
    border: 1px solid #2A2A2A;
}
QPushButton[btnRole="primary"]:enabled {
    background-color: #4FC3F7;
    color: #121212;
    border: 1px solid #4FC3F7;
    font-weight: bold;
}
QPushButton[btnRole="primary"]:enabled:hover {
    background-color: #1E1E1E;
    color: #4FC3F7;
    border: 1px solid #4FC3F7;
}
QPushButton[btnRole="primary"]:disabled {
    background-color: #0E0E0E;
    color: #5C5C5C;
    border: 1px solid #2A2A2A;
    font-weight: normal;
}
QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {
    background-color: #1E1E1E;
    color: #EAEAEA;
    border: 1px solid #2A2A2A;
    border-radius: 4px;
    padding: 2px 4px;
}
QGroupBox {
    background-color: #1E1E1E;
    border: 1px solid #2A2A2A;
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 8px;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}
QTabWidget::pane {
    border: 1px solid #2A2A2A;
    background-color: #121212;
}
QTabBar::tab {
    background-color: #1E1E1E;
    color: #EAEAEA;
    border: 1px solid #2A2A2A;
    padding: 6px 12px;
}
QTabBar::tab:selected {
    background-color: #4FC3F7;
    color: #121212;
}
QMenuBar, QMenu, QMenu::item {
    background-color: #121212;
    color: #EAEAEA;
}
QMenu::item:selected {
    background-color: #4FC3F7;
    color: #121212;
}
QSlider::groove:horizontal {
    background: #2A2A2A;
    height: 6px;
    border-radius: 3px;
}
QSlider::groove:horizontal:disabled {
    background: #0E0E0E;
}
QSlider::handle:horizontal:disabled {
    background: #5C5C5C;
}
QLabel:disabled {
    color: #5C5C5C;
}
QSlider::handle:horizontal {
    background: #4FC3F7;
    width: 14px;
    margin: -4px 0;
    border-radius: 7px;
}
"""


def generate_theme_qss(theme):
    btn_disabled_fg = theme.get("btn_disabled_fg", "#888888")
    btn_disabled_bg = theme.get("btn_disabled_bg", theme["sub_bg"])
    btn_primary_fg = theme.get("btn_primary_fg", theme["bg"])
    btn_close = theme.get("btn_close", theme["accent"])
    btn_close_fg = theme.get("btn_close_fg", btn_primary_fg)
    btn_start_qss = ""
    if "btn_start" in theme:
        btn_start = theme["btn_start"]
        btn_start_fg = theme.get("btn_start_fg", "#FFFFFF")
        btn_start_qss = f"""
QPushButton[btnRole="start"]:enabled {{
    background-color: {btn_start};
    color: {btn_start_fg};
    border: 1px solid {btn_start};
    font-weight: bold;
}}
QPushButton[btnRole="start"]:enabled:hover {{
    background-color: {theme['sub_bg']};
    color: {btn_start};
    border: 1px solid {btn_start};
}}
QPushButton[btnRole="start"]:disabled {{
    background-color: {btn_disabled_bg};
    color: {btn_disabled_fg};
    border: 1px solid {theme['border']};
    font-weight: normal;
}}
"""
    return f"""
QWidget {{
    background-color: {theme['bg']};
    color: {theme['fg']};
}}
QPushButton {{
    background-color: {theme['sub_bg']};
    color: {theme['fg']};
    border: 1px solid {theme['border']};
    border-radius: 6px;
    padding: 6px;
}}
QPushButton:hover {{
    background-color: {theme['accent']};
    color: {theme['bg']};
}}
QPushButton:disabled {{
    background-color: {btn_disabled_bg};
    color: {btn_disabled_fg};
    border: 1px solid {theme['border']};
}}
QPushButton[btnRole="primary"]:enabled {{
    background-color: {theme['accent']};
    color: {btn_primary_fg};
    border: 1px solid {theme['accent']};
    font-weight: bold;
}}
QPushButton[btnRole="primary"]:enabled:hover {{
    background-color: {theme['sub_bg']};
    color: {theme['accent']};
    border: 1px solid {theme['accent']};
}}
QPushButton[btnRole="primary"]:disabled {{
    background-color: {btn_disabled_bg};
    color: {btn_disabled_fg};
    border: 1px solid {theme['border']};
    font-weight: normal;
}}
QPushButton[btnRole="close"]:enabled {{
    background-color: {btn_close};
    color: {btn_close_fg};
    border: 1px solid {btn_close};
    font-weight: bold;
}}
QPushButton[btnRole="close"]:enabled:hover {{
    background-color: {theme['sub_bg']};
    color: {btn_close};
    border: 1px solid {btn_close};
}}
QPushButton[btnRole="close"]:disabled {{
    background-color: {btn_disabled_bg};
    color: {btn_disabled_fg};
    border: 1px solid {theme['border']};
    font-weight: normal;
}}
{btn_start_qss}QLineEdit, QTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
    background-color: {theme['bg']};
    color: {theme['fg']};
    border: 1px solid {theme['border']};
    border-radius: 4px;
    padding: 2px 4px;
}}
QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QLineEdit:disabled, QTextEdit:disabled {{
    background-color: {btn_disabled_bg};
    color: {btn_disabled_fg};
    border: 1px solid {theme['border']};
}}
QGroupBox {{
    background-color: {theme['sub_bg']};
    border: 1px solid {theme['border']};
    border-radius: 4px;
    margin-top: 8px;
    padding-top: 8px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 8px;
    padding: 0 4px;
}}
QTabWidget::pane {{
    border: 1px solid {theme['border']};
    background-color: {theme['bg']};
}}
QTabBar::tab {{
    background-color: {theme['sub_bg']};
    color: {theme['fg']};
    border: 1px solid {theme['border']};
    padding: 6px 12px;
}}
QTabBar::tab:selected {{
    background-color: {theme['accent']};
    color: {theme['bg']};
}}
QMenuBar, QMenu, QMenu::item {{
    background-color: {theme['bg']};
    color: {theme['fg']};
}}
QMenu::item:selected {{
    background-color: {theme['accent']};
    color: {theme['bg']};
}}
QSlider::groove:horizontal {{
    background: {theme['border']};
    height: 6px;
    border-radius: 3px;
}}
QSlider::groove:horizontal:disabled {{
    background: {btn_disabled_bg};
}}
QSlider::handle:horizontal {{
    background: {theme['accent']};
    width: 14px;
    margin: -4px 0;
    border-radius: 7px;
}}
QSlider::handle:horizontal:disabled {{
    background: {btn_disabled_fg};
}}
QLabel:disabled {{
    color: {btn_disabled_fg};
}}
"""
